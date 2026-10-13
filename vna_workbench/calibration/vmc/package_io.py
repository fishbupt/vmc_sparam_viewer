import hashlib
import io
import json
import zipfile
import numpy as np
from vna_workbench.calibration.vmc.models import GROUPS, CalibrationOptions, Calibration
from vna_workbench.calibration.vmc.input_reader import validate_axes
from vna_workbench.core.numerics import check_nonzero
from vna_workbench.data.archives import csv_record, atomic_zip

def validate_calibration(cal):
    if cal.manifest.get('schema')!='vmc-calibration-1': raise ValueError('不支持的 VMC 校准包版本。')
    rf,iff=validate_axes(CalibrationOptions(**cal.manifest['options']))
    if not np.array_equal(rf,cal.frequency) or not np.array_equal(iff,cal.if_frequency):
        raise ValueError('校准包的频率轴与配置不一致。')
    expected={g+'_'+n for g in GROUPS for n in ('EDF','ESF','ERF')}
    expected|={b+'_'+n for b in ('RF','IF') for n in ('ELF','ELR','ETF','ETR')};expected.add('VMC_ETF')
    if set(cal.terms)!=expected: raise ValueError('校准包误差项缺失或不支持。')
    for name,v in cal.terms.items():
        if np.shape(v)!=np.shape(rf) or not np.isfinite(v).all(): raise ValueError(name+'：校准数组无效。')
        if name.endswith(('ERF','ETF','ETR')): check_nonzero(v,name)


def save_calibration(cal,path):
    validate_calibration(cal)
    buf=io.BytesIO();np.savez(buf,RF=cal.frequency,IF=cal.if_frequency,**cal.terms)
    manifest={**cal.manifest,'arrays_sha256':hashlib.sha256(buf.getvalue()).hexdigest()}
    return atomic_zip(path,{'calibration.json':json.dumps(manifest,ensure_ascii=False,indent=2),
        'arrays.npz':buf.getvalue(),'error_terms.csv':csv_record({'RF_Hz':cal.frequency,'IF_Hz':cal.if_frequency},cal.terms)})


def load_calibration(path):
    with zipfile.ZipFile(path) as z:
        if any(i.file_size>128*1024*1024 for i in z.infolist()): raise ValueError('校准包文件过大。')
        manifest=json.loads(z.read('calibration.json'));blob=z.read('arrays.npz')
        if hashlib.sha256(blob).hexdigest()!=manifest.get('arrays_sha256'): raise ValueError('校准包数组校验失败。')
        with np.load(io.BytesIO(blob),allow_pickle=False) as a:
            cal=Calibration(a['RF'].copy(),a['IF'].copy(),{k:a[k].copy() for k in a.files if k not in ('RF','IF')},manifest)
    validate_calibration(cal);return cal
