"""Numerical data containers, without GUI dependencies."""

from dataclasses import dataclass, field
import numpy as np

PARAMS = ('S11', 'S12', 'S21', 'S22')


@dataclass
class Dataset:
    name: str
    kind: str
    s: dict[str, np.ndarray]
    axes: dict[str, np.ndarray]
    segment: np.ndarray
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    auxiliary: dict[str, np.ndarray] = field(default_factory=dict)
    raw_text: str = ''

    @property
    def count(self):
        return len(self.s['S11'])

@dataclass
class Standard:
    name: str
    frequency: np.ndarray
    gamma: np.ndarray
    z0: float
