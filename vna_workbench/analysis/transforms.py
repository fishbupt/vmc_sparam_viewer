"""S-parameter display transforms and continuous segment runs."""

import numpy as np

def values(z, mode, segment):
    if mode == 'dB':
        with np.errstate(divide='ignore'):
            return 20 * np.log10(np.abs(z))
    if mode == 'Magnitude':
        return np.abs(z)
    if mode == 'Real':
        return z.real
    if mode == 'Imag':
        return z.imag
    phase = np.angle(z)
    phase[np.abs(z) == 0] = np.nan
    if mode == 'Unwrapped':
        # Never unwrap across segment boundaries or undefined phases.
        phase = phase.copy()
        for indices in runs(segment):
            good = indices[np.isfinite(phase[indices])]
            for group in np.split(good, np.where(np.diff(good) != 1)[0] + 1):
                if len(group):
                    phase[group] = np.unwrap(phase[group])
    return np.rad2deg(phase)


def runs(segment):
    return np.split(np.arange(len(segment)), np.where(segment[1:] != segment[:-1])[0] + 1)
