"""One-to-one frequency matching without interpolation or ambiguous matches."""
from dataclasses import dataclass
import csv
import numpy as np
from parser import PARAMS

@dataclass
class Comparison:
    left: object
    right: object
    axis: str
    tolerance: float
    i: np.ndarray
    j: np.ndarray
    delta: dict
    ambiguous: int


def compare(left, right, axis='InputFreq', tolerance=0.001):
    if tolerance < 0 or not np.isfinite(tolerance):
        raise ValueError('频率容差必须是非负有限数。')
    a = left.axes['StimulusFreq']
    b = right.axes[axis]
    order = np.argsort(b, kind='stable')
    sorted_b = b[order]
    low = np.searchsorted(sorted_b, a-tolerance, 'left')
    high = np.searchsorted(sorted_b, a+tolerance, 'right')
    candidate = high-low == 1
    i = np.flatnonzero(candidate)
    j = order[low[i]]
    counts = np.bincount(j, minlength=len(b))
    unique = counts[j] == 1
    ambiguous = int(np.count_nonzero(high-low > 1) + np.count_nonzero(~unique))
    i, j = i[unique], j[unique]
    if not len(i):
        raise ValueError('没有可唯一匹配的频点。请检查比较频率轴/容差；重复频率不会按行号强行配对。')
    delta = {}
    for p in PARAMS:
        x, y = left.s[p][i], right.s[p][j]
        diff = x-y
        valid = (np.abs(x)>0) & (np.abs(y)>0)
        db = np.full(len(i), np.nan)
        phase = np.full(len(i), np.nan)
        db[valid] = 20*np.log10(np.abs(x[valid])) - 20*np.log10(np.abs(y[valid]))
        phase[valid] = (np.rad2deg(np.angle(x[valid])-np.angle(y[valid]))+180)%360-180
        delta[p] = {'幅度差 (dB)': db, '相位差 (°)': phase, '复数差模值': np.abs(diff),
                    '实部差': diff.real, '虚部差': diff.imag}
    return Comparison(left,right,axis,tolerance,i,j,delta,ambiguous)


def stats(array):
    finite = array[np.isfinite(array)]
    if not len(finite):
        return np.nan,np.nan,0
    return float(np.max(np.abs(finite))),float(np.sqrt(np.mean(finite**2))),len(finite)


def export_comparison(result, path):
    r=result
    right_prefix = 'S2PX' if r.right.kind.startswith('S2PX') else 'Reference'
    cols={'S2P_Row':r.i+1,right_prefix+'_Row':r.j+1,'S2P_Stimulus_Hz':r.left.axes['StimulusFreq'][r.i],
          right_prefix+'_'+r.axis+'_Hz':r.right.axes[r.axis][r.j],
          'Frequency_Delta_Hz':r.left.axes['StimulusFreq'][r.i]-r.right.axes[r.axis][r.j],
          right_prefix+'_SegIndex':r.right.segment[r.j]}
    for p in PARAMS:
        for prefix,z in [('S2P',r.left.s[p][r.i]),(right_prefix,r.right.s[p][r.j])]:
            cols[f'{p}_{prefix}_Real']=z.real
            cols[f'{p}_{prefix}_Imag']=z.imag
        for metric,v in r.delta[p].items():
            cols[p+'_'+metric]=v
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(cols)
        writer.writerows(zip(*cols.values()))
