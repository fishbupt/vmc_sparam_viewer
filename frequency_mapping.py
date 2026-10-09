"""Shared non-inverting RF -> IF mapping for generation and extraction.

`up` selects the sum product, `down` the RF-LO difference product.
LO-RF (spectral inversion) is intentionally not substituted with abs(RF-LO).
"""
import numpy as np

CONVERSION_MODES = {
    'down': '下变频：IF = RF − LO',
    'up': '上变频：IF = RF + LO',
}


def frequency_relation(conversion='down'):
    if conversion not in CONVERSION_MODES:
        raise ValueError('变频方向必须为 down（下变频）或 up（上变频）。')
    return 'IF=RF-LO' if conversion == 'down' else 'IF=RF+LO'


def output_frequencies(rf_hz, lo_hz, conversion='down'):
    """Return positive IF frequencies; do not reorder, conjugate, or extrapolate."""
    frequency_relation(conversion)
    rf = np.asarray(rf_hz, dtype=float)
    if rf.ndim != 1 or not rf.size or not np.all(np.isfinite(rf)) or np.any(rf <= 0):
        raise ValueError('RF 必须为非空的一维正有限频率数组。')
    if not np.isfinite(lo_hz) or lo_hz <= 0:
        raise ValueError('LO 必须为正有限频率。')
    with np.errstate(over='ignore', invalid='ignore'):
        ifreq = rf - lo_hz if conversion == 'down' else rf + lo_hz
    if not np.all(np.isfinite(ifreq)) or np.any(ifreq <= 0):
        raise ValueError('IF 必须为正有限频率；下变频要求所有 RF > LO，IF=RF−LO；不支持 LO−RF 反转分支。')
    return ifreq
