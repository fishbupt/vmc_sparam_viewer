"""Shared finite/nonzero numerical guard."""

import numpy as np

def check_nonzero(value, label):
    if not np.all(np.isfinite(value)) or np.any(np.abs(value) < 1e-12):
        raise ValueError(label+'：存在非有限值或近零分母。')
