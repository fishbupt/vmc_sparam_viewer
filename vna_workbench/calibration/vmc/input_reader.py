from pathlib import Path
import hashlib
import numpy as np
from vna_workbench.data.touchstone import parse_s2p
from vna_workbench.data.models import Standard
from vna_workbench.data.standard_definitions import parse_s1p
from vna_workbench.core.standard_sampling import sample_standard, SAMPLING_METHODS
from vna_workbench.core.frequency_conversion import output_frequencies
from vna_workbench.calibration.vmc.models import CalibrationInputs, GROUPS, AXIS_MODES

def validate_axes(o):
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


class VMCInputReader:
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
