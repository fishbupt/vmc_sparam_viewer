from dataclasses import asdict
from vna_workbench.core.frequency_conversion import is_inverting, phase_convention
import numpy as np
from vna_workbench.data.models import Dataset
from vna_workbench.data.models import Standard
from vna_workbench.core.standard_sampling import INTERPOLATION_COORDINATES
from vna_workbench.core.sol import solve_sol
from vna_workbench.core.sol import correct_reflection
from vna_workbench.calibration.vmc.models import VERSION, GROUPS, CalibrationOptions, Calibration
from vna_workbench.calibration.vmc.input_reader import validate_axes, VMCInputReader
from vna_workbench.core.numerics import check_nonzero

def calibrate(inputs, options=CalibrationOptions()):
    rf,iff=validate_axes(options); reader=VMCInputReader(options); terms={}; diagnostics={}
    for group in GROUPS:
        port,band=group.split('_'); axis=rf if band=='RF' else iff
        paths=inputs.sol.get(group,[]); standards=inputs.standards.get(port,[])
        if len(paths)!=3 or len(standards)!=3: raise ValueError(group+'：需要三个原始测量和三个标准定义。')
        measured=np.column_stack([reader.measured(p,'S11' if port=='P1' else 'S22',axis) for p in paths])
        gamma=np.column_stack([reader.defined(p,'S11',axis) for p in standards])
        (d,s,r),cond,res=solve_sol(measured,gamma,options.max_condition)
        for name,value in [('EDF',d),('ESF',s),('ERF',r)]:
            check_nonzero(r,'SOL 反射跟踪')
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
        check_nonzero(c['S21'],'Thru 正向定义');check_nonzero(c['S12'],'Thru 反向定义')
        p1='P1_'+band; p2='P2_'+band
        g1=correct_reflection(m['S11'],terms[p1+'_EDF'],terms[p1+'_ESF'],terms[p1+'_ERF'])
        g2=correct_reflection(m['S22'],terms[p2+'_EDF'],terms[p2+'_ESF'],terms[p2+'_ERF'])
        delta1=g1-c['S11'];delta2=g2-c['S22'];product=c['S12']*c['S21']
        den1=product+c['S22']*delta1;den2=product+c['S11']*delta2
        check_nonzero(den1,'Thru 正向负载匹配');check_nonzero(den2,'Thru 反向负载匹配')
        lf=delta1/den1;lr=delta2/den2
        sf=terms[p1+'_ESF'];sr=terms[p2+'_ESF']
        determinant=c['S11']*c['S22']-product
        df=1-c['S11']*sf-c['S22']*lf+determinant*sf*lf
        dr=1-c['S22']*sr-c['S11']*lr+determinant*sr*lr
        check_nonzero(df,'Thru 正向分母');check_nonzero(dr,'Thru 反向分母')
        tf=m['S21']*df/c['S21'];tr=m['S12']*dr/c['S12']
        check_nonzero(tf,'Thru 正向跟踪');check_nonzero(tr,'Thru 反向跟踪')
        terms.update({band+'_ELF':lf,band+'_ELR':lr,band+'_ETF':tf,band+'_ETR':tr})
    definition_axis=rf if options.mixer_definition_axis=='rf' else iff
    if isinstance(reader.read(inputs.calibration_mixer),Standard):
        raise ValueError('校准混频器表征必须为包含四参数的 S2P。')
    c={p:reader.defined(inputs.calibration_mixer,p,definition_axis) for p in ('S11','S21','S12','S22')}
    m=reader.mixed(inputs.cal_mixer_raw,rf,iff)
    sf=terms['P1_RF_ESF'];lf=terms['IF_ELF']
    inverted=is_inverting(options.frequency_conversion)
    sm21=m['S21']
    if inverted:
        c['S22']=c['S22'].conj();lf=lf.conj();sm21=sm21.conj()
    den=(1-c['S11']*sf)*(1-c['S22']*lf)-c['S12']*c['S21']*sf*lf
    check_nonzero(c['S21'],'校准混频器 S21');check_nonzero(den,'校准混频器变频分母')
    terms['VMC_ETF']=sm21*den/c['S21']
    check_nonzero(terms['VMC_ETF'],'VMC ETF')
    manifest={'schema':'vmc-calibration-1','version':VERSION,'options':asdict(options),
        'spectral_inversion':inverted,'phase_convention':phase_convention(options.frequency_conversion),
        'input_mapping':asdict(inputs),'sources':list(reader.sources.values()),
        'interpolated_points':reader.interpolated,'interpolation_coordinates':INTERPOLATION_COORDINATES[options.standard_sampling],
        'diagnostics':diagnostics,'thru_method':'defined per band' if inputs.thru_definition else 'ideal flush',
        'ETF_formula':('conj(SM21_cal)*((1-C11*ESF_RF)*(1-conj(C22)*conj(ELF_IF))-C12*C21*ESF_RF*conj(ELF_IF))/C21' if inverted else 'SM21_cal*((1-C11*ESF_RF)*(1-C22*ELF_IF)-C12*C21*ESF_RF*ELF_IF)/C21'),
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
