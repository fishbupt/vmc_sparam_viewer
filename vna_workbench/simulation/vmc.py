

"""Independent forward wave model for six VMC Dummy DUT acquisitions.

No inverse calibration/extraction is used to generate observations or expected terms.
"""

from dataclasses import dataclass, asdict, field, fields
from datetime import datetime
from pathlib import Path
import csv
import hashlib
import io
import json
import shutil
import tempfile
import uuid
import numpy as np
from vna_workbench.data.models import Standard
from vna_workbench.data.standard_definitions import parse_s1p
from vna_workbench.core.standard_sampling import sample_standard, SAMPLING_METHODS, INTERPOLATION_COORDINATES
from vna_workbench.data.models import Dataset, PARAMS
from vna_workbench.data.touchstone import parse_s2p
from vna_workbench.core.frequency_conversion import output_frequencies, frequency_relation, is_inverting, phase_convention, bands_overlap
from vna_workbench.simulation.conjugate_waves import high_side_measurement
from vna_workbench.data.touchstone import s2p_text

VERSION = '1.8.0'
RAW_NAMES = ('open_raw.s2p', 'short_raw.s2p', 'load_raw.s2p', 'thru_raw.s2p',
             'cal_mixer_raw.s2p', 'mut_raw.s2p')

@dataclass(frozen=True)
class MixerModel:
    s11_db: float = -18
    s11_phase_deg: float = -20
    s11_delay_ps: float = 20
    s22_db: float = -20
    s22_phase_deg: float = 30
    s22_delay_ps: float = 15
    transmission_db: float = -6
    transmission_phase_deg: float = -30
    transmission_delay_ps: float = 80

@dataclass(frozen=True)
class PortModel:
    edf_db: float = -35
    edf_phase_deg: float = 30
    edf_delay_ps: float = 5
    esf_db: float = -25
    esf_phase_deg: float = -20
    esf_delay_ps: float = 10
    tracking_db: float = -.5
    tracking_phase_deg: float = 7.5
    tracking_delay_ps: float = 20

@dataclass(frozen=True)
class VMCSimulationOptions:
    rf_start_hz: float = 10e9
    rf_stop_hz: float = 20e9
    points: int = 201
    lo_hz: float = 20e9
    frequency_conversion: str = 'up'
    z0: float = 50
    raw_axis: str = 'dual'
    standard_sampling: str = 'cubic_ri'
    frequency_tolerance_hz: float = .001
    calibration_mixer: MixerModel = field(default_factory=MixerModel)
    mut: MixerModel = field(default_factory=lambda: MixerModel(-14,40,35,-16,-55,25,-9,15,110))
    port1: PortModel = field(default_factory=PortModel)
    port2: PortModel | None = None     # None: same box at the same physical frequency.
    synthetic_sol: bool = False     # Complex verification kit, never a physical kit.
    noise_enabled: bool = False
    noise_floor_db: float = -90
    noise_seed: int = 20261009
    noise_averages: int = 1

@dataclass
class VMCSimulation:
    options: VMCSimulationOptions
    frequency: np.ndarray
    if_frequency: np.ndarray
    physical_frequency: np.ndarray
    mixed_frequency: np.ndarray
    raw: dict
    clean: dict
    standards: dict
    thru: dict
    calibration_mixer: Dataset
    mut: Dataset
    expected_terms: dict
    source_bytes: dict
    manifest: dict

@dataclass
class SavedVMCSimulation:
    directory: Path
    simulation: VMCSimulation

    def calibration_options(self):
        from vna_workbench.app.workflows import vmc_calibration_options
        return vmc_calibration_options(self)

    def calibration_inputs(self):
        from vna_workbench.app.workflows import vmc_calibration_inputs
        return vmc_calibration_inputs(self)

    @property
    def mut_path(self):
        return self.directory/'mut_raw.s2p'


def response(f, db, phase, delay, anchor):
    return 10**(db/20)*np.exp(1j*(np.deg2rad(phase)-2*np.pi*(f-anchor)*delay*1e-12))


def port_box(f, model, anchor):
    return tuple(response(f,getattr(model,p+'_db'),getattr(model,p+'_phase_deg'),
                          getattr(model,p+'_delay_ps'),anchor) for p in ('edf','esf','tracking'))


def mixer_matrix(rf, model, reciprocal=True, if_frequency=None):
    c=np.zeros((len(rf),2,2),complex)
    for prefix,i,j in [('s11',0,0),('s22',1,1),('transmission',1,0)]:
        axis=if_frequency if prefix=='s22' and if_frequency is not None else rf
        c[:,i,j]=response(axis,getattr(model,prefix+'_db'),getattr(model,prefix+'_phase_deg'),
                          getattr(model,prefix+'_delay_ps'),axis[0])
    if reciprocal:c[:,0,1]=c[:,1,0]
    return c


def forward_wave(c, box1, box2):
    """Solve a = T + E b; b = C a for both independent port excitations."""
    n=len(c); e=np.zeros((n,2,2),complex);t=e.copy();d=e.copy()
    for i,(directionality,match,tracking) in enumerate((box1,box2)):
        d[:,i,i]=directionality;e[:,i,i]=match;t[:,i,i]=tracking
    system=np.eye(2)-e@c
    if not np.isfinite(system).all() or np.any(np.linalg.cond(system)>1e12):
        raise ValueError('正向波量方程病态，请调整误差盒或标准定义。')
    a=np.linalg.solve(system,t)
    result=d+t@c@a
    if not np.isfinite(result).all():raise ValueError('正向模型产生非有限值。')
    return result


def _params(c):
    return {'S11':c[:,0,0],'S21':c[:,1,0],'S12':c[:,0,1],'S22':c[:,1,1]}


def _matrix(values):
    return np.stack((np.stack((values['S11'],values['S12']),axis=-1),
                     np.stack((values['S21'],values['S22']),axis=-1)),axis=-2)


def _validate(o):
    for k in ('rf_start_hz','rf_stop_hz','lo_hz','z0','frequency_tolerance_hz','noise_floor_db'):
        if not np.isfinite(getattr(o,k)):raise ValueError(k+' 必须为有限数。')
    for k,low,high in [('points',2,200001),('noise_seed',0,2**32-1),('noise_averages',1,10000)]:
        v=getattr(o,k)
        if isinstance(v,bool) or not np.isfinite(v) or int(v)!=v or not low<=v<=high:
            raise ValueError(k+' 超出整数范围。')
    if not 0<o.rf_start_hz<o.rf_stop_hz or o.z0<=0 or o.frequency_tolerance_hz<0:
        raise ValueError('RF 起止频率、参考阻抗或频点容差无效。')
    if o.standard_sampling not in SAMPLING_METHODS or o.raw_axis not in ('rf','if','dual'):
        raise ValueError('未知插值方式或原始文件横轴。')
    if not -300<=o.noise_floor_db<=0:raise ValueError('噪声底须在 −300～0 dB。')
    for model in (o.calibration_mixer,o.mut,o.port1,o.port2 or o.port1):
        if not all(np.isfinite(getattr(model,f.name)) for f in fields(model)):
            raise ValueError('模型参数必须为有限数。')
        for f in fields(model):
            if f.name.endswith('_db'):
                v=getattr(model,f.name)
                hi=40 if f.name in ('transmission_db','tracking_db') else 0
                if not -300<=v<=hi or (hi==0 and v==0):raise ValueError(f.name+' 超出幅度范围。')
    rf=np.linspace(o.rf_start_hz,o.rf_stop_hz,int(o.points))
    iff=output_frequencies(rf,o.lo_hz,o.frequency_conversion)
    if np.any(np.diff(rf)<=0) or np.any((-1 if is_inverting(o.frequency_conversion) else 1)*np.diff(iff)<=0):
        raise ValueError('频率跨度或 LO 导致频点精度不足，请调整配置。')
    if o.raw_axis=='dual' and bands_overlap(rf,iff):
        raise ValueError('双频段复制要求 RF / IF 不重叠；请选择 RF 或 IF 横轴。')
    return rf,iff


def _physical_axis(rf,iff,tol):
    # Include exact requested nodes; fill a disjoint gap only for Dummy DUT coverage.
    low,high=sorted((np.sort(rf),np.sort(iff)),key=lambda f:f[0]);gap=np.array([])
    if low[-1]<high[0]:
        step=rf[1]-rf[0];count=int(np.ceil((high[0]-low[-1])/step))-1
        if count>200001:raise ValueError('RF / IF 间隔导致文件过大，请减少点数或调整 LO。')
        gap=low[-1]+step*np.arange(1,count+1)
        gap=gap[gap<high[0]-tol]
    merged=np.sort(np.concatenate((rf,iff,gap)))
    axis=[merged[0]]
    for v in merged[1:]:
        if v-axis[-1]>tol:axis.append(v)
    axis=np.asarray(axis)
    if np.any(np.diff(axis)<=2*tol):raise ValueError('频率容差相对网格过大，会产生歧义匹配。')
    return axis


class DefinitionReader:
    """Read and hash a single byte snapshot; only definition data may interpolate."""
    def __init__(self,o):self.o=o;self.blobs={};self.sources=[];self.counts={};self.cache={}
    def read(self,path,s1p=False):
        path=str(Path(path).resolve())
        if path in self.cache:
            d=self.cache[path]
            if isinstance(d,Standard)!=s1p:raise ValueError('同一文件不能同时用作 S1P 与 S2P 定义。')
            return d
        blob=Path(path).read_bytes()
        for enc in ('utf-8-sig','gb18030','cp1252'):
            try:text=blob.decode(enc);break
            except UnicodeDecodeError:continue
        else:raise ValueError('无法解码标准定义：'+path)
        d=parse_s1p(text,path) if s1p else parse_s2p(text,path)
        f=d.frequency if s1p else d.axes['StimulusFreq'];z0=d.z0 if s1p else float(d.metadata['参考阻抗'].split()[0])
        vals=[d.gamma] if s1p else list(d.s.values())
        if (not np.isfinite(f).all() or np.any(f<0) or np.any(np.diff(f)<=0)
            or not all(np.isfinite(v).all() for v in vals)):raise ValueError('定义频率须严格递增且数据有限。')
        if not np.isclose(z0,self.o.z0,rtol=1e-12,atol=0):raise ValueError('定义参考阻抗不一致，不自动重归一化。')
        self.cache[path]=d;self.blobs[path]=blob;self.sources.append({'path':path,'sha256':hashlib.sha256(blob).hexdigest()})
        return d
    def sample(self,d,param,target):
        std=d if isinstance(d,Standard) else Standard(d.name+'/'+param,d.axes['StimulusFreq'],d.s[param],self.o.z0)
        z,count=sample_standard(std,target,self.o.standard_sampling,self.o.frequency_tolerance_hz)
        self.counts[std.name]=count
        return z


def simulate_vmc(options=VMCSimulationOptions(), standard_paths=None, thru_path=None,
                 calibration_mixer_path=None, mixer_definition_axis='rf'):
    o=options;rf,iff=_validate(o);f=_physical_axis(rf,iff,o.frequency_tolerance_hz)
    if mixer_definition_axis not in ('rf','if'):raise ValueError('校准混频器定义横轴须为 RF 或 IF。')
    inverted=is_inverting(o.frequency_conversion)
    reader=DefinitionReader(o)
    if standard_paths is not None and len(standard_paths)!=3:raise ValueError('须选择 OPEN / SHORT / LOAD 三个 S1P。')
    if standard_paths is not None and o.synthetic_sol:
        raise ValueError('内置验证 SOL 与导入 SOL 不能同时使用。')
    # The same actual standards are used at both physical ports, as requested.
    standards={}
    for i,(k,g) in enumerate(zip(('open','short','load'),(1,-1,0))):
        standards[k]=(np.full(len(f),g,complex) if standard_paths is None else
                      reader.sample(reader.read(standard_paths[i],True),'S11',f))
    if o.synthetic_sol:
        from vna_workbench.simulation.verification_kit import verification_gamma
        standards=dict(zip(('open','short','load'),verification_gamma(f)))
    gamma=list(standards.values())
    if any(np.any(abs(gamma[i]-gamma[j])<1e-10) for i in range(3) for j in range(i)):
        raise ValueError('OPEN / SHORT / LOAD 定义在某些频点重合或过于接近。')
    zero=np.zeros(len(f),complex);one=np.ones(len(f),complex)
    if thru_path:
        td=reader.read(thru_path);thru={p:reader.sample(td,p,f) for p in PARAMS}
    else:thru={'S11':zero.copy(),'S22':zero.copy(),'S21':one.copy(),'S12':one.copy()}
    if np.any(abs(thru['S21'])<1e-12) or np.any(abs(thru['S12'])<1e-12):raise ValueError('THRU 定义传输不能为零。')
    if calibration_mixer_path:
        cd=reader.read(calibration_mixer_path);target=rf if mixer_definition_axis=='rf' else iff
        cal_values={p:reader.sample(cd,p,target) for p in PARAMS};cal=_matrix(cal_values)
    else:cal=mixer_matrix(rf,o.calibration_mixer,if_frequency=iff if inverted else None)
    if np.any(abs(cal[:,1,0])<1e-12):raise ValueError('校准混频器 S21 不能为零。')
    mut=mixer_matrix(rf,o.mut,False,if_frequency=iff if inverted else None)
    b1=port_box(f,o.port1,rf[0]);b2=port_box(f,o.port2 or o.port1,rf[0])
    mixed_b1=port_box(rf,o.port1,rf[0]);mixed_b2=port_box(iff,o.port2 or o.port1,rf[0])
    clean={}
    for k in standards:
        c=np.zeros((len(f),2,2),complex);c[:,0,0]=standards[k];c[:,1,1]=standards[k]
        clean[k+'_raw.s2p']=forward_wave(c,b1,b2)
    clean['thru_raw.s2p']=forward_wave(_matrix(thru),b1,b2)
    mixed_forward=high_side_measurement if inverted else forward_wave
    mixed_clean={'cal_mixer_raw.s2p':mixed_forward(cal,mixed_b1,mixed_b2),
                 'mut_raw.s2p':mixed_forward(mut,mixed_b1,mixed_b2)}
    sigma=10**(o.noise_floor_db/20)/np.sqrt(o.noise_averages) if o.noise_enabled else 0.
    rng=np.random.Generator(np.random.PCG64(int(o.noise_seed)))
    def noisy(c,sol=False):
        a=c.copy()
        if sigma:
            n=(rng.normal(size=c.shape)+1j*rng.normal(size=c.shape))*(sigma/np.sqrt(2))
            if sol:n[:,0,1]=0;n[:,1,0]=0  # disconnected SOL has no cross-port response.
            a+=n
        return a
    raw={k:noisy(c,k!='thru_raw.s2p') for k,c in clean.items()}
    mixed_raw={k:noisy(c) for k,c in mixed_clean.items()}
    if o.raw_axis=='dual':
        ixrf=np.searchsorted(f,rf);ixif=np.searchsorted(f,iff)
        # physical_axis may coalesce a rounding duplicate; disjoint dual nodes remain exact.
        order=np.argsort(np.concatenate((rf,iff)));nodes=np.concatenate((rf,iff))[order]
        def encode(c):
            result=np.empty((len(f),2,2),complex)
            for i in range(2):
                for j in range(2):result[:,i,j]=np.interp(f,nodes,np.concatenate((c[:,i,j],c[:,i,j]))[order])
            result[ixrf]=c;result[ixif]=c
            return result
        mixed_f=f
    else:
        mixed_f=rf if o.raw_axis=='rf' else iff
        order=np.argsort(mixed_f);mixed_f=mixed_f[order]
        def encode(c):return c[order].copy()
    for k in mixed_clean:clean[k]=encode(mixed_clean[k]);raw[k]=encode(mixed_raw[k])
    terms={}
    for band,axis in [('RF',rf),('IF',iff)]:
        boxes=[port_box(axis,p,rf[0]) for p in (o.port1,o.port2 or o.port1)]
        for port,(d,e,t) in enumerate(boxes,1):
            terms.update({f'P{port}_{band}_EDF':d,f'P{port}_{band}_ESF':e,f'P{port}_{band}_ERF':t*t})
        terms.update({band+'_ELF':boxes[1][1],band+'_ELR':boxes[0][1],
                      band+'_ETF':boxes[0][2]*boxes[1][2],band+'_ETR':boxes[0][2]*boxes[1][2]})
    terms['VMC_ETF']=mixed_b1[2]*(mixed_b2[2].conj() if inverted else mixed_b2[2])
    axes={'StimulusFreq':rf,'InputFreq':rf,'OutputFreq':iff,'LO1Freq':np.full(len(rf),o.lo_hz)}
    def dataset(name,c):
        return Dataset(name,'S2P / VMC simulated truth',_params(c),{k:v.copy() for k,v in axes.items()},
            np.zeros(len(rf),int),{'参考阻抗':f'{o.z0:g} Ω','频率轴':'RF','频率映射':frequency_relation(o.frequency_conversion)},[])
    warnings=['MUT S12 is exactly zero: unilateral truth, not missing data.',
              'Effective mixed-frequency matrix; ordinary S2P does not perform frequency conversion.',
              'Use only the configured RF/IF nodes; RI bridge values in the gap are not measurements.',
              'Keysight Dummy DUT receiver lookup/processing requires external validation.']
    if not np.allclose(cal[:,0,1],cal[:,1,0],rtol=1e-6,atol=1e-12):warnings.append('Imported calibration mixer is not reciprocal; Keysight VMC requires reciprocity.')
    for name,c in [('calibration_mixer',cal),('MUT',mut)]:
        effective=c.copy()
        if inverted:effective[:,1,1]=effective[:,1,1].conj()
        if np.max(np.linalg.svd(effective,compute_uv=False))>1+1e-10:
            warnings.append(name+' effective S-matrix singular value exceeds one; passivity is not enforced.')
    if inverted:
        warnings.append('High-side raw SM21 is physical; truth S21/VC21 is input-referred equivalent. Compare the documented convention before Keysight phase validation.')
        if standard_paths is None and not o.synthetic_sol:
            warnings.append('Ideal +1/-1/0 SOL cannot detect missing standard conjugation; use nonideal complex standards for characterization validation.')
    manifest={'version':VERSION,'spectral_inversion':inverted,'phase_convention':phase_convention(o.frequency_conversion),'options':asdict(o),'if_relation':frequency_relation(o.frequency_conversion),
              'sol_definition':('synthetic nonideal verification SOL; NOT a physical Keysight kit' if o.synthetic_sol else 'ideal +1/-1/0, zero offset' if standard_paths is None else 'imported actual shared S1P'),
              'thru_definition':'ideal Flush: S11=S22=0, S21=S12=1, zero delay/loss' if not thru_path else 'imported full S2P',
              'calibration_mixer_definition':'RF normalized output; '+('imported '+mixer_definition_axis if calibration_mixer_path else 'analytical reciprocal model'),
              'model':('Independent real-linear conjugate-wave solve; physical receivers M=D+T*b' if inverted else 'a=T+E*b; b=C*a; M=D+T*b, solved independently for both port excitations'),
              'phase_reference':'Mixer phases at first paired point; high_side S22 slope uses IF, transfers use RF; port-box phases at physical f=RF start',
              'standard_sampling':o.standard_sampling,'interpolation_coordinates':INTERPOLATION_COORDINATES[o.standard_sampling],
              'extrapolation':False,'source_inputs':reader.sources,'interpolated_points':reader.counts,
              'noise':{'enabled':o.noise_enabled,'effective_complex_rms':float(sigma),'seed':int(o.noise_seed),
                       'generator':'NumPy PCG64','numpy_version':np.__version__,'averages':int(o.noise_averages),
                       'model':'IID circular complex Gaussian after port errors; separate acquisitions; dual bands copy the same noisy matrix',
                       'reference':'dimensionless S=1, not dBm; SOL cross-port entries remain zero'},
              'warnings':warnings}
    return VMCSimulation(o,rf,iff,f,mixed_f,raw,clean,standards,thru,
                         dataset('calibration_mixer.s2p',cal),dataset('mut_truth.s2p',mut),terms,reader.blobs,manifest)


def csv_record(axes,complex_values):
    arrays=list(axes.values());header=list(axes)
    for name,z in complex_values.items():header.extend((name+'_real',name+'_imag'));arrays.extend((z.real,z.imag))
    stream=io.StringIO();w=csv.writer(stream);w.writerow(header);w.writerows(zip(*arrays));return stream.getvalue()


def generate_vmc_files(output_parent, options=VMCSimulationOptions(), standard_paths=None,
                       thru_path=None, calibration_mixer_path=None, mixer_definition_axis='rf'):
    """Atomically publish a unique run folder after all inputs have been validated."""
    parent=Path(output_parent)
    if not parent.is_dir():raise ValueError('请选择现有输出父目录。')
    sim=simulate_vmc(options,standard_paths,thru_path,calibration_mixer_path,mixer_definition_axis)
    folder=parent/('vmc_dummy_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    stage=Path(tempfile.mkdtemp(prefix='.vmc_dummy_staging_',dir=parent))
    try:
        o=options;common=[f'Synthetic VMC; {frequency_relation(o.frequency_conversion)}; LO_Hz={o.lo_hz:.17g}',
            'RawAxis='+o.raw_axis+'; measurements include port errors; definitions/truth are noise-free.',
            'Port-box phases anchored at physical RF start; mixer phases anchored at first paired point.',
            'PhaseConvention='+phase_convention(o.frequency_conversion)]
        for name in RAW_NAMES:
            f=sim.mixed_frequency if name in RAW_NAMES[4:] else sim.physical_frequency
            comments=common+[('Effective RF->IF matrix; dual bands are identical; gap bridge is not measured.' if name in RAW_NAMES[4:] else
                             'Physical-frequency acquisition; SOL S11=P1, S22=P2; disconnected S21=S12=0.' if name in RAW_NAMES[:3] else
                             'Ordinary physical-frequency THRU acquisition; definition in thru_definition.s2p.')]
            (stage/name).write_text(s2p_text(f,_params(sim.raw[name]),o.z0,comments),encoding='utf-8')
        for k,g in sim.standards.items():
            lines=['! Actual shared SOL definition used to generate raw observations.',f'# Hz S RI R {o.z0:.17g}']
            lines.extend(f'{f:.17g} {z.real:.17g} {z.imag:.17g}' for f,z in zip(sim.physical_frequency,g))
            (stage/f'standard_{k}.s1p').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        (stage/'thru_definition.s2p').write_text(s2p_text(sim.physical_frequency,sim.thru,o.z0,[sim.manifest['thru_definition']]),encoding='utf-8')
        for ds in (sim.calibration_mixer,sim.mut):
            text=s2p_text(sim.frequency,ds.s,o.z0,['Noise-free effective mixer truth; RF stimulus axis.']+[common[0],common[3]])
            (stage/ds.name).write_text(text,encoding='utf-8');ds.raw_text=text
            (stage/(Path(ds.name).stem+'.csv')).write_text(csv_record({'RF_Hz':sim.frequency,'IF_Hz':sim.if_frequency},ds.s),encoding='utf-8-sig')
        if is_inverting(o.frequency_conversion):
            (stage/'high_side_phase_reference.csv').write_text(csv_record(
                {'RF_Hz':sim.frequency,'IF_Hz':sim.if_frequency},
                {'MUT_VC21_input_equivalent':sim.mut.s['S21'],
                 'MUT_K21_physical_LO_gauge_zero':sim.mut.s['S21'].conj(),
                 'CAL_C21_input_equivalent':sim.calibration_mixer.s['S21'],
                 'CAL_K21_physical_LO_gauge_zero':sim.calibration_mixer.s['S21'].conj()}),encoding='utf-8-sig')
        (stage/'expected_error_terms.csv').write_text(csv_record({'RF_Hz':sim.frequency,'IF_Hz':sim.if_frequency},sim.expected_terms),encoding='utf-8-sig')
        mapping=io.StringIO();w=csv.writer(mapping);w.writerow(['RF_Hz','IF_Hz','LO_Hz']);w.writerows(zip(sim.frequency,sim.if_frequency,np.full(len(sim.frequency),o.lo_hz)))
        (stage/'frequency_map.csv').write_text(mapping.getvalue(),encoding='utf-8-sig')
        np.savez_compressed(stage/'forward_observations.npz',physical_frequency=sim.physical_frequency,
            mixed_frequency=sim.mixed_frequency,**{'clean_'+k.removesuffix('.s2p'):v for k,v in sim.clean.items()},
            **{'raw_'+k.removesuffix('.s2p'):v for k,v in sim.raw.items()})
        if sim.source_bytes:
            sources=stage/'source_definitions';sources.mkdir()
            for i,(path,blob) in enumerate(sim.source_bytes.items()):
                name=f'{i:02d}_'+Path(path).name;(sources/name).write_bytes(blob)
                next(s for s in sim.manifest['source_inputs'] if s['path']==path)['copied_path']='source_definitions/'+name
        (stage/'README.md').write_text(f'''# VMC Dummy DUT simulation

Six raw files: {', '.join(RAW_NAMES)}.
RF {sim.frequency[0]/1e9:g}..{sim.frequency[-1]/1e9:g} GHz; IF {sim.if_frequency[0]/1e9:g}..{sim.if_frequency[-1]/1e9:g} GHz; {frequency_relation(o.frequency_conversion)}.
Phase convention: {sim.manifest['phase_convention']}.
Raw mixer axis: {o.raw_axis}; calibration_mixer.s2p / mut_truth.s2p axis: RF.
SOL: {sim.manifest['sol_definition']}.
THRU: {sim.manifest['thru_definition']}.
Use standard_open/short/load.s1p and thru_definition.s2p in BOTH calibrations; do not substitute mechanical kit defaults.
Default Flush has zero offset delay and loss. Definition files are NOT raw acquisitions.
cal_mixer_raw.s2p = CalTHRU acquisition; calibration_mixer.s2p = known calibration mixer definition.
MUT reverse S12 truth is exactly zero; only S11, S22 and VC21 are covered by the unilateral calibration.
Gap bridge values are not acquisition nodes. Ordinary S2P does not perform frequency conversion.
forward_observations.npz contains clean/raw matrices and grids, with no pickle. expected_error_terms.csv contains independent box truth.
Noise-free truth and definitions are supplied alongside applied noise and hashes in simulation_report.json.
Keysight / Windows Dummy DUT receiver behavior has not been validated by this generation alone.
''',encoding='utf-8')
        sim.manifest['output_sha256']={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
        (stage/'simulation_report.json').write_text(json.dumps(sim.manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        stage.rename(folder)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise
    return SavedVMCSimulation(folder,sim)
