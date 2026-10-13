from vna_workbench.core.sol import correct_reflection
from dataclasses import asdict
from pathlib import Path
import numpy as np
from vna_workbench.data.models import Dataset
from vna_workbench.calibration.vmc.models import VERSION, CalibrationOptions, MUTResult
from vna_workbench.calibration.vmc.input_reader import validate_axes, VMCInputReader
from vna_workbench.core.numerics import check_nonzero
from vna_workbench.calibration.vmc.package_io import validate_calibration

def calibrate_mut(cal,path,raw_axis=None):
    validate_calibration(cal)
    options=CalibrationOptions(**cal.manifest['options'])
    if raw_axis is not None: options=CalibrationOptions(**{**asdict(options),'raw_axis':raw_axis})
    rf,iff=validate_axes(options);reader=VMCInputReader(options)
    m=reader.mixed(path,rf,iff);t=cal.terms
    c11=correct_reflection(m['S11'],t['P1_RF_EDF'],t['P1_RF_ESF'],t['P1_RF_ERF'])
    c22=correct_reflection(m['S22'],t['P2_IF_EDF'],t['P2_IF_ESF'],t['P2_IF_ERF'])
    check_nonzero(t['VMC_ETF'],'VMC ETF')
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
