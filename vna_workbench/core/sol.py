"""One-port SOL solver and Mobius representation."""

import numpy as np
from vna_workbench.core.numerics import check_nonzero

def solve_sol(measured, gamma, max_condition):
    """Arrays (N,3), solve m=A+B*gamma+S*m*gamma, R=B+A*S."""
    separation = np.minimum.reduce([np.abs(gamma[:, 0]-gamma[:, 1]),
                                    np.abs(gamma[:, 0]-gamma[:, 2]),
                                    np.abs(gamma[:, 1]-gamma[:, 2])])
    if np.any(separation < 1e-12):
        raise ValueError('SOL 标准定义退化/病态：存在相同或几乎相同的反射系数。')
    matrix = np.stack((np.ones_like(gamma), gamma, measured*gamma), axis=-1)
    cond = np.linalg.cond(matrix)
    bad = ~np.isfinite(cond) | (cond > max_condition)
    if np.any(bad):
        k = int(np.flatnonzero(bad)[0])
        raise ValueError(f'SOL 求解退化/病态：第 {k+1} 点，条件数 {cond[k]:.6g}。请检查标准件是否独立及测量值。')
    abc = np.linalg.solve(matrix, measured[..., None])[..., 0]
    d, b, s = abc.T
    r = b+d*s
    denom = 1-s[:, None]*gamma
    if np.any(np.abs(denom) < 1e-14):
        raise ValueError('SOL 回代分母接近零。')
    pred = d[:, None]+r[:, None]*gamma/denom
    return (d, s, r), cond, np.max(np.abs(pred-measured), axis=1)


def mobius(terms):
    d, s, r = terms
    result = np.empty((len(d), 2, 2), complex)
    result[:, 0, 0] = r-d*s
    result[:, 0, 1] = d
    result[:, 1, 0] = -s
    result[:, 1, 1] = 1
    return result


def correct_reflection(measured,d,s,r):
    delta=measured-d
    denom=r+s*delta
    check_nonzero(denom,'反射校准')
    return delta/denom
