"""Synthetic complex SOL definitions for algorithm verification, not a real kit."""
import numpy as np


def verification_gamma(frequency):
    f = np.asarray(frequency)
    return (.98*np.exp(-2j*np.pi*f*18e-12),
            -.96*np.exp(-2j*np.pi*f*28e-12),
            .04*np.exp(.5j-2j*np.pi*f*12e-12))


def verification_blobs(frequency, z0=50):
    f = np.unique(frequency)
    blobs = []
    for name, gamma in zip(('OPEN', 'SHORT', 'LOAD'), verification_gamma(f)):
        lines = [f'! Synthetic nonideal {name}; algorithm verification only.',
                 f'# Hz S RI R {z0:.17g}']
        lines += [f'{x:.17g} {z.real:.17g} {z.imag:.17g}' for x,z in zip(f,gamma)]
        blobs.append(('\n'.join(lines)+'\n').encode('ascii'))
    return blobs
