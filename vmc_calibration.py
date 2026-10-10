"""Mechanical SOLT VMC calibration and unilateral MUT correction.

No measured arrays are interpolated. Only standard definitions are sampled.
The mixed-frequency transmission calibration uses the full cal-mixer determinant;
MUT correction follows the approved unilateral/neglected reverse-coupling formula.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import hashlib
import io
import json
import os
import tempfile
import zipfile
import numpy as np
from parser import Dataset, parse_s2p
from characterization import (Standard, parse_s1p, sample_standard, solve_sol,
                             SAMPLING_METHODS, INTERPOLATION_COORDINATES)
from frequency_mapping import output_frequencies

VERSION = '1.6.3'
GROUPS = ('P1_RF', 'P1_IF', 'P2_RF', 'P2_IF')
KINDS = ('OPEN', 'SHORT', 'LOAD')
AXIS_MODES = {'dual': '双频段复制（RF / IF 不重叠）',
              'rf': '所有变频参数使用 RF 横轴', 'if': '所有变频参数使用 IF 横轴'}

@dataclass(frozen=True)
class CalibrationOptions:
    rf_start_hz: float = 10e9
    rf_stop_hz: float = 20e9
    points: int = 201
    lo_hz: float = 20e9
    frequency_conversion: str = 'up'
    z0: float = 50.
    standard_sampling: str = 'cubic_ri'
    frequency_tolerance_hz: float = .001
    max_condition: float = 1e12
    raw_axis: str = 'dual'
    mixer_definition_axis: str = 'rf'

@dataclass
class CalibrationInputs:
    standards: dict                 # P1 / P2 -> OPEN,SHORT,LOAD S1P paths
    sol: dict                       # each GROUP -> three raw S1P or S2P paths
    thru_raw: dict                  # RF / IF -> raw S2P paths
    calibration_mixer: str
    cal_mixer_raw: str
    thru_definition: dict | None = None  # RF / IF -> defined Thru; None=ideal Flush

@dataclass
class Calibration:
    frequency: np.ndarray
    if_frequency: np.ndarray
    terms: dict
    manifest: dict

@dataclass
class MUTResult:
    dataset: Dataset
    manifest: dict
    raw: dict

def _check_nonzero(value, label):
    if not np.all(np.isfinite(value)) or np.any(np.abs(value) < 1e-12):
        raise ValueError(label+'：存在非有限值或近零分母。')

def _axes(o):
    if (isinstance(o.points, bool) or int(o.points) != o.points or not 2 <= o.points <= 200001):
        raise ValueError('点数须为 2～200001 的整数。')
    if not np.isfinite([o.rf_start_hz,o.rf_stop_hz,o.z0,o.frequency_tolerance_hz,o.max_condition]).all():
        raise ValueError('配置必须为有限数。')
    if not 0 < o.rf_start_hz < o.rf_stop_hz or o.z0 <= 0 or o.frequency_tolerance_hz < 0 or o.max_condition <= 1:
        raise ValueError('RF 起止、参考阻抗、容差或条件数配置无效。')
    if o.standard_sampling not in SAMPLING_METHODS or o.raw_axis not in AXIS_MODES or o.mixer_definition_axis not in ('rf','if'):
        raise ValueError('未知插值方式或频率轴。')
    rf=np.linspace(o.rf_start_hz,o.rf_stop_hz,int(o.points))
    iff=output_frequencies(rf,o.lo_hz,o.frequency_conversion)
    if o.raw_axis=='dual' and max(rf[0],iff[0]) <= min(rf[-1],iff[-1]):
        raise ValueError('双频段复制编码要求 RF / IF 不重叠；请改用 RF 或 IF 横轴文件。')
    return rf,iff

class _Reader:
    def __init__(self, o):
        self.o=o; self.cache={}; self.sources={}; self.interpolated={}

    def read(self, path):
        path=str(Path(path).resolve())
        if path not in self.cache:
            blob=Path(path).read_bytes()
            for enc in ('utf-8-sig','gb18030','cp1252'):
                try: text=blob.decode(enc); break
                except UnicodeDecodeError: continue
            else: raise ValueError(path+'：无法解码。')
            data=parse_s1p(text,path) if Path(path).suffix.lower()=='.s1p' else parse_s2p(text,path)
            axis=data.frequency if isinstance(data,Standard) else data.axes['StimulusFreq']
            z0=data.z0 if isinstance(data,Standard) else float(data.metadata['参考阻抗'].split()[0])
            values=[data.gamma] if isinstance(data,Standard) else list(data.s.values())
            if (not np.isfinite(axis).all() or np.any(axis<0) or np.any(np.diff(axis)<=0)
                    or not all(np.isfinite(v).all() for v in values)):
                raise ValueError(path+'：频率必须非负、严格递增，数据须为有限数。')
            if not np.isclose(z0,self.o.z0,rtol=1e-12,atol=0):
                raise ValueError(path+'：参考阻抗不一致，不自动重归一化。')
            self.cache[path]=data
            self.sources[path]={'path':path,'sha256':hashlib.sha256(blob).hexdigest(),'z0':z0}
        return self.cache[path]

    def measured(self, path, param, target):
        d=self.read(path)
        freq=d.frequency if isinstance(d,Standard) else d.axes['StimulusFreq']
        lo=np.searchsorted(freq,target-self.o.frequency_tolerance_hz,'left')
        hi=np.searchsorted(freq,target+self.o.frequency_tolerance_hz,'right')
        if np.any(hi-lo != 1) or len(np.unique(lo)) != len(target):
            raise ValueError(f'{path}：所需频点缺失或容差匹配不唯一；原始测量不插值。')
        return (d.gamma if isinstance(d,Standard) else d.s[param])[lo].copy()

    def defined(self, path, param, target):
        d=self.read(path)
        if isinstance(d,Standard): std=d
        else: std=Standard(str(path)+'/'+param,d.axes['StimulusFreq'],d.s[param],self.o.z0)
        values,count=sample_standard(std,target,self.o.standard_sampling,self.o.frequency_tolerance_hz)
        self.interpolated[f'{path}/{param}/{target[0]:.17g}..{target[-1]:.17g}/{len(target)}pts']=count
        return values

    def mixed(self,path,rf,iff):
        d=self.read(path)
        if isinstance(d,Standard): raise ValueError('变频输入必须为包含四个参数的 S2P。')
        if self.o.raw_axis=='dual':
            first={p:self.measured(path,p,rf) for p in d.s}
            second={p:self.measured(path,p,iff) for p in d.s}
            if any(not np.allclose(first[p],second[p],rtol=1e-10,atol=1e-12) for p in d.s):
                raise ValueError('双频段复制编码的 RF / IF 对应四参数不一致；请检查横轴选择。')
            return first
        axis=rf if self.o.raw_axis=='rf' else iff
        return {p:self.measured(path,p,axis) for p in d.s}

def shared_inputs(standards, sol_files, thru_file, calibration_mixer, cal_mixer_raw, thru_definition=None):
    """Convenience mapping for the approved six-file Dummy DUT baseline."""
    return CalibrationInputs({'P1':list(standards),'P2':list(standards)},
        {g:list(sol_files) for g in GROUPS}, {'RF':thru_file,'IF':thru_file},
        calibration_mixer,cal_mixer_raw,
        {'RF':thru_definition,'IF':thru_definition} if thru_definition else None)

def correct_reflection(measured,d,s,r):
    delta=measured-d
    denom=r+s*delta
    _check_nonzero(denom,'反射校准')
    return delta/denom

def calibrate(inputs, options=CalibrationOptions()):
    rf,iff=_axes(options); reader=_Reader(options); terms={}; diagnostics={}
    for group in GROUPS:
        port,band=group.split('_'); axis=rf if band=='RF' else iff
        paths=inputs.sol.get(group,[]); standards=inputs.standards.get(port,[])
        if len(paths)!=3 or len(standards)!=3: raise ValueError(group+'：需要三个原始测量和三个标准定义。')
        measured=np.column_stack([reader.measured(p,'S11' if port=='P1' else 'S22',axis) for p in paths])
        gamma=np.column_stack([reader.defined(p,'S11',axis) for p in standards])
        (d,s,r),cond,res=solve_sol(measured,gamma,options.max_condition)
        for name,value in [('EDF',d),('ESF',s),('ERF',r)]:
            _check_nonzero(r,'SOL 反射跟踪')
            terms[group+'_'+name]=value
        diagnostics[group]={'max_condition':float(max(cond)),'max_SOL_residual':float(max(res))}
    for band,axis in [('RF',rf),('IF',iff)]:
        path=inputs.thru_raw[band]
        if isinstance(reader.read(path),Standard): raise ValueError('Thru 原始测量必须为 S2P。')
        m={p:reader.measured(path,p,axis) for p in ('S11','S21','S12','S22')}
        defined=(inputs.thru_definition or {}).get(band)
        if defined and isinstance(reader.read(defined),Standard):
            raise ValueError('已定义 Thru 必须为包含四参数的 S2P。')
        c=({p:reader.defined(defined,p,axis) for p in m} if defined else
           {'S11':np.zeros(len(rf),complex),'S22':np.zeros(len(rf),complex),
            'S21':np.ones(len(rf),complex),'S12':np.ones(len(rf),complex)})
        _check_nonzero(c['S21'],'Thru 正向定义');_check_nonzero(c['S12'],'Thru 反向定义')
        p1='P1_'+band; p2='P2_'+band
        g1=correct_reflection(m['S11'],terms[p1+'_EDF'],terms[p1+'_ESF'],terms[p1+'_ERF'])
        g2=correct_reflection(m['S22'],terms[p2+'_EDF'],terms[p2+'_ESF'],terms[p2+'_ERF'])
        delta1=g1-c['S11'];delta2=g2-c['S22'];product=c['S12']*c['S21']
        den1=product+c['S22']*delta1;den2=product+c['S11']*delta2
        _check_nonzero(den1,'Thru 正向负载匹配');_check_nonzero(den2,'Thru 反向负载匹配')
        lf=delta1/den1;lr=delta2/den2
        sf=terms[p1+'_ESF'];sr=terms[p2+'_ESF']
        determinant=c['S11']*c['S22']-product
        df=1-c['S11']*sf-c['S22']*lf+determinant*sf*lf
        dr=1-c['S22']*sr-c['S11']*lr+determinant*sr*lr
        _check_nonzero(df,'Thru 正向分母');_check_nonzero(dr,'Thru 反向分母')
        tf=m['S21']*df/c['S21'];tr=m['S12']*dr/c['S12']
        _check_nonzero(tf,'Thru 正向跟踪');_check_nonzero(tr,'Thru 反向跟踪')
        terms.update({band+'_ELF':lf,band+'_ELR':lr,band+'_ETF':tf,band+'_ETR':tr})
    definition_axis=rf if options.mixer_definition_axis=='rf' else iff
    if isinstance(reader.read(inputs.calibration_mixer),Standard):
        raise ValueError('校准混频器表征必须为包含四参数的 S2P。')
    c={p:reader.defined(inputs.calibration_mixer,p,definition_axis) for p in ('S11','S21','S12','S22')}
    m=reader.mixed(inputs.cal_mixer_raw,rf,iff)
    sf=terms['P1_RF_ESF'];lf=terms['IF_ELF']
    den=(1-c['S11']*sf)*(1-c['S22']*lf)-c['S12']*c['S21']*sf*lf
    _check_nonzero(c['S21'],'校准混频器 S21');_check_nonzero(den,'校准混频器变频分母')
    terms['VMC_ETF']=m['S21']*den/c['S21']
    _check_nonzero(terms['VMC_ETF'],'VMC ETF')
    manifest={'schema':'vmc-calibration-1','version':VERSION,'options':asdict(options),
        'input_mapping':asdict(inputs),'sources':list(reader.sources.values()),
        'interpolated_points':reader.interpolated,'interpolation_coordinates':INTERPOLATION_COORDINATES[options.standard_sampling],
        'diagnostics':diagnostics,'thru_method':'defined per band' if inputs.thru_definition else 'ideal flush',
        'ETF_formula':'SM21_cal*((1-C11*ESF_RF)*(1-C22*ELF_IF)-C12*C21*ESF_RF*ELF_IF)/C21',
        'limitations':['No isolation acquisition: transmission leakage is assumed zero.',
            'Receiver ratios / switch terms are not independently calibrated.',
            'MUT correction assumes unilateral or negligible reverse-coupling contribution.',
            'Keysight naming/conventions and Windows measurement workflow require external validation.']}
    return Calibration(rf,iff,terms,manifest)

def term_dataset(cal,name):
    """Display one scalar error term through the existing S21 magnitude/phase view."""
    value=cal.terms[name];zero=np.zeros_like(value)
    axis=cal.if_frequency if name.startswith(('P1_IF_','P2_IF_','IF_')) else cal.frequency
    return Dataset(name,'VMC error term',{'S11':zero.copy(),'S12':zero.copy(),'S21':value.copy(),'S22':zero.copy()},
        {'StimulusFreq':axis.copy(),'InputFreq':cal.frequency.copy(),'OutputFreq':cal.if_frequency.copy()},
        np.zeros(len(value),int),{'误差项':name,'说明':'误差项曲线显示在 S21；其余参数为显示占位。'},
        ['仅 S21 显示标量误差项；不是物理四参数网络。'])

def calibrate_mut(cal,path,raw_axis=None):
    _validate_calibration(cal)
    options=CalibrationOptions(**cal.manifest['options'])
    if raw_axis is not None: options=CalibrationOptions(**{**asdict(options),'raw_axis':raw_axis})
    rf,iff=_axes(options);reader=_Reader(options)
    m=reader.mixed(path,rf,iff);t=cal.terms
    c11=correct_reflection(m['S11'],t['P1_RF_EDF'],t['P1_RF_ESF'],t['P1_RF_ERF'])
    c22=correct_reflection(m['S22'],t['P2_IF_EDF'],t['P2_IF_ESF'],t['P2_IF_ERF'])
    _check_nonzero(t['VMC_ETF'],'VMC ETF')
    vc21=m['S21']*(1-c11*t['P1_RF_ESF'])*(1-c22*t['IF_ELF'])/t['VMC_ETF']
    if not np.isfinite(vc21).all(): raise ValueError('校准 MUT 产生非有限值。')
    warnings=['VC21 按单向 / 忽略反向耦合公式校准；S12 未校准，零值仅为文件占位。',
              'S11 / S22 使用单端口误差消除；存在反向耦合时不代表完整双向去嵌。']
    manifest={'schema':'vmc-mut-1','version':VERSION,'calibration':cal.manifest,
        'sources':list(reader.sources.values()),'raw_axis':options.raw_axis,
        'reverse_calibrated':False,'MUT_formula':'VC21=SM21*(1-S11*ESF_RF)*(1-S22*ELF_IF)/ETF',
        'warnings':warnings}
    data=Dataset(Path(path).stem+'_calibrated.s2p','VMC calibrated MUT',
        {'S11':c11,'S21':vc21,'S12':np.zeros_like(vc21),'S22':c22},
        {'StimulusFreq':rf,'InputFreq':rf.copy(),'OutputFreq':iff,'LO1Freq':np.full(len(rf),options.lo_hz)},
        np.zeros(len(rf),int),{'参考阻抗':f'{options.z0:g} Ω','S21':'VC21','S12':'未校准，占位零',
            '频率轴':'RF','算法版本':VERSION},warnings,{'VC21':vc21.copy(),'SM21_raw':m['S21'].copy()})
    return MUTResult(data,manifest,m)

def _validate_calibration(cal):
    if cal.manifest.get('schema')!='vmc-calibration-1': raise ValueError('不支持的 VMC 校准包版本。')
    rf,iff=_axes(CalibrationOptions(**cal.manifest['options']))
    if not np.array_equal(rf,cal.frequency) or not np.array_equal(iff,cal.if_frequency):
        raise ValueError('校准包的频率轴与配置不一致。')
    expected={g+'_'+n for g in GROUPS for n in ('EDF','ESF','ERF')}
    expected|={b+'_'+n for b in ('RF','IF') for n in ('ELF','ELR','ETF','ETR')};expected.add('VMC_ETF')
    if set(cal.terms)!=expected: raise ValueError('校准包误差项缺失或不支持。')
    for name,v in cal.terms.items():
        if np.shape(v)!=np.shape(rf) or not np.isfinite(v).all(): raise ValueError(name+'：校准数组无效。')
        if name.endswith(('ERF','ETF','ETR')): _check_nonzero(v,name)

def _csv(axes,values):
    out=io.StringIO();w=csv.writer(out);head=list(axes)
    for name in values: head.extend((name+'_real',name+'_imag'))
    w.writerow(head)
    for i in range(len(next(iter(axes.values())))):
        row=[v[i] for v in axes.values()]
        for v in values.values(): row.extend((v[i].real,v[i].imag))
        w.writerow(row)
    return out.getvalue()

def _atomic_zip(path,payload):
    path=Path(path);temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.zip',delete=False) as stream: temp=stream.name
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for name,blob in payload.items(): z.writestr(name,blob)
        os.replace(temp,path);temp=None
    finally:
        if temp is not None: Path(temp).unlink(missing_ok=True)
    return str(path)

def save_calibration(cal,path):
    _validate_calibration(cal)
    buf=io.BytesIO();np.savez(buf,RF=cal.frequency,IF=cal.if_frequency,**cal.terms)
    manifest={**cal.manifest,'arrays_sha256':hashlib.sha256(buf.getvalue()).hexdigest()}
    return _atomic_zip(path,{'calibration.json':json.dumps(manifest,ensure_ascii=False,indent=2),
        'arrays.npz':buf.getvalue(),'error_terms.csv':_csv({'RF_Hz':cal.frequency,'IF_Hz':cal.if_frequency},cal.terms)})

def load_calibration(path):
    with zipfile.ZipFile(path) as z:
        if any(i.file_size>128*1024*1024 for i in z.infolist()): raise ValueError('校准包文件过大。')
        manifest=json.loads(z.read('calibration.json'));blob=z.read('arrays.npz')
        if hashlib.sha256(blob).hexdigest()!=manifest.get('arrays_sha256'): raise ValueError('校准包数组校验失败。')
        with np.load(io.BytesIO(blob),allow_pickle=False) as a:
            cal=Calibration(a['RF'].copy(),a['IF'].copy(),{k:a[k].copy() for k in a.files if k not in ('RF','IF')},manifest)
    _validate_calibration(cal);return cal

def export_mut(result,path):
    data=result.dataset;f=data.axes['InputFreq'];iff=data.axes['OutputFreq']
    z0=result.manifest['calibration']['options']['z0']
    lines=['! VMC calibrated MUT; S21=VC21; RF axis; IF=see frequency_map.csv.',
        '! S12 is NOT calibrated; zero placeholder. Unilateral MUT model.',f'# Hz S RI R {z0:.17g}']
    for i,frequency in enumerate(f):
        row=[frequency]
        for p in ('S11','S21','S12','S22'):
            v=data.s[p][i];row.extend((v.real,v.imag))
        lines.append(' '.join(format(float(v),'.17g') for v in row))
    return _atomic_zip(path,{'calibrated_mut.s2p':'\n'.join(lines)+'\n',
        'calibrated_mut.csv':_csv({'RF_Hz':f,'IF_Hz':iff},{'S11':data.s['S11'],'VC21':data.s['S21'],'S22':data.s['S22']}),
        'raw_mut.csv':_csv({'RF_Hz':f,'IF_Hz':iff},result.raw),
        'frequency_map.csv':_csv({'RF_Hz':f,'IF_Hz':iff,'LO_Hz':data.axes['LO1Freq']},{}),
        'report.json':json.dumps(result.manifest,ensure_ascii=False,indent=2)})
