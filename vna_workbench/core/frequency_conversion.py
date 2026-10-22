

"""Explicit mixing products; frequency order and conjugation are separate."""

import numpy as np

CONVERSION_MODES = {
    'down': '下变频：IF = RF − LO',
    'up': '上变频：IF = RF + LO',
    'high_side': '高边 LO（频谱反转）：IF = LO − RF',
}


def frequency_relation(conversion='down'):
    if conversion not in CONVERSION_MODES:
        raise ValueError('变频方向必须为 down、up 或 high_side（高边 LO）。')
    return {'down': 'IF=RF-LO', 'up': 'IF=RF+LO', 'high_side': 'IF=LO-RF'}[conversion]


def is_inverting(conversion):
    frequency_relation(conversion)
    return conversion == 'high_side'


def phase_convention(conversion):
    if is_inverting(conversion):
        return ('high_side_input_equivalent_v1: S11/S22 are physical port reflections; '
                'S12/S21 are input-referred equivalent transfers; '
                'b1=S11*a1+S12*conj(a2); b2=conj(S21)*conj(a1)+S22*a2; '
                'raw SM21 is physical output/input at real unit excitation; '
                'VC21 and VMC_ETF are input-referred (conjugated output) quantities; LO phase gauge=0')
    return 'non-inverting: physical reflections and ordinary complex-linear transfer'


def bands_overlap(rf, iff):
    return max(np.min(rf), np.min(iff)) <= min(np.max(rf), np.max(iff))


def output_frequencies(rf_hz, lo_hz, conversion='down'):
    """Return positive IF frequencies; do not reorder, conjugate, or extrapolate."""
    frequency_relation(conversion)
    rf = np.asarray(rf_hz, dtype=float)
    if rf.ndim != 1 or not rf.size or not np.all(np.isfinite(rf)) or np.any(rf <= 0):
        raise ValueError('RF 必须为非空的一维正有限频率数组。')
    if not np.isfinite(lo_hz) or lo_hz <= 0:
        raise ValueError('LO 必须为正有限频率。')
    with np.errstate(over='ignore', invalid='ignore'):
        ifreq = (lo_hz - rf if conversion == 'high_side' else
                 rf - lo_hz if conversion == 'down' else rf + lo_hz)
    if not np.all(np.isfinite(ifreq)) or np.any(ifreq <= 0):
        raise ValueError('IF 必须为正有限频率；down 要求 RF > LO，high_side 要求 LO > RF。')
    return ifreq
