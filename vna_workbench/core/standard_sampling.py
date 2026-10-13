"""Standard evaluation in magnitude and unwrapped-phase coordinates."""

import numpy as np

SAMPLING_METHODS = {
    'cubic_ri': '三次样条插值（幅度 / 解缠绕相位）',
    'linear_ri': '线性插值（幅度 / 解缠绕相位）',
}


INTERPOLATION_COORDINATES = {
    'linear_ri': 'linear_magnitude_unwrapped_phase',
    'cubic_ri': 'cubic_magnitude_unwrapped_phase',
}


def sample_standard(std, target, method='linear_ri', tolerance=0.001):
    """Preserve exact nodes; interpolate inside the band, never extrapolate.

    Linear: interpolate linear magnitude and unwrapped phase (radians).
    Cubic: interpolate linear magnitude and unwrapped phase with not-a-knot
    boundaries. Reject negative interpolated magnitudes rather than clamping.
    A zero Load stays zero; mixed zero/nonzero phase interpolation is rejected.
    """
    target = np.asarray(target, dtype=float)
    if target.ndim != 1 or not np.all(np.isfinite(target)):
        raise ValueError('目标频率必须为一维有限数数组。')
    if method not in SAMPLING_METHODS:
        raise ValueError('未知标准件求值方法。')
    if tolerance < 0 or not np.isfinite(tolerance):
        raise ValueError('频率容差必须为非负有限数。')
    lo = np.searchsorted(std.frequency, target-tolerance, 'left')
    hi = np.searchsorted(std.frequency, target+tolerance, 'right')
    if np.any(hi-lo > 1):
        raise ValueError(f'{std.name}: 容差内有多个标准定义点，请减小容差。')
    exact = hi-lo == 1
    missing = ~exact
    result = np.empty(target.shape, complex)
    result[exact] = std.gamma[lo[exact]]
    if not np.any(missing):
        return result, 0
    if np.any((target[missing] < std.frequency[0]) | (target[missing] > std.frequency[-1])):
        raise ValueError(f'{std.name}: 所需频率超出标准定义范围，禁止外推。')
    x = target[missing]
    if np.all(std.gamma == 0):
        result[missing] = 0
    else:
        magnitude = np.abs(std.gamma)
        if np.any(magnitude == 0):
            raise ValueError(f'{std.name}: 非恒零标准含零幅度，无法定义相位插值；请提供有效标准定义。')
        phase = np.unwrap(np.angle(std.gamma))
        if method == 'cubic_ri':
            from scipy.interpolate import CubicSpline
            interpolated_magnitude = CubicSpline(std.frequency, magnitude,
                bc_type='not-a-knot', extrapolate=False)(x)
            interpolated_phase = CubicSpline(std.frequency, phase,
                bc_type='not-a-knot', extrapolate=False)(x)
            if np.any(interpolated_magnitude < 0):
                raise ValueError(f'{std.name}: 三次样条幅度插值产生负值；请使用幅相线性插值或提供更合适的标准定义。')
        else:
            interpolated_magnitude = np.interp(x, std.frequency, magnitude)
            interpolated_phase = np.interp(x, std.frequency, phase)
        result[missing] = interpolated_magnitude * np.exp(1j*interpolated_phase)
    if not np.all(np.isfinite(result)):
        raise ValueError(f'{std.name}: 标准插值产生非有限值。')
    return result, int(np.count_nonzero(missing))
