"""VMC configuration and result containers."""

from dataclasses import dataclass
import numpy as np
from vna_workbench.data.models import Dataset

VERSION = '1.8.0'


GROUPS = ('P1_RF', 'P1_IF', 'P2_RF', 'P2_IF')


KINDS = ('OPEN', 'SHORT', 'LOAD')


AXIS_MODES = {'dual': '双频段复制（RF / IF 不重叠）',
              'rf': '所有变频参数使用 RF 横轴', 'if': '所有变频参数使用 IF 横轴'}


@dataclass(frozen=True)
class CalibrationOptions:
    rf_start_hz: float = 10e9
    rf_stop_hz: float = 20e9
    points: int = 201
    lo_hz: float = 20e9
    frequency_conversion: str = 'up'
    z0: float = 50.
    standard_sampling: str = 'cubic_ri'
    frequency_tolerance_hz: float = .001
    max_condition: float = 1e12
    raw_axis: str = 'dual'
    mixer_definition_axis: str = 'rf'


@dataclass
class CalibrationInputs:
    standards: dict                 # P1 / P2 -> OPEN,SHORT,LOAD S1P paths
    sol: dict                       # each GROUP -> three raw S1P or S2P paths
    thru_raw: dict                  # RF / IF -> raw S2P paths
    calibration_mixer: str
    cal_mixer_raw: str
    thru_definition: dict | None = None  # RF / IF -> defined Thru; None=ideal Flush


@dataclass
class Calibration:
    frequency: np.ndarray
    if_frequency: np.ndarray
    terms: dict
    manifest: dict


@dataclass
class MUTResult:
    dataset: Dataset
    manifest: dict
    raw: dict


ROLES = ('input_open', 'input_short', 'input_load',
         'output_open', 'output_short', 'output_load')


LABELS = ('输入端 Open', '输入端 Short', '输入端 Load',
          '混频器输出端 Open', '混频器输出端 Short', '混频器输出端 Load')


@dataclass(frozen=True)
class Options:
    lo_hz: float = 5e9
    standard_sampling: str = 'linear_ri'
    frequency_tolerance_hz: float = 0.001
    second_round: str = 'raw'
    root_sign: int = 1
    max_condition: float = 1e12
    frequency_conversion: str = 'down'


@dataclass
class Characterization:
    dataset: Dataset
    terms: dict
    diagnostics: dict
    manifest: dict
    evaluated_standards: np.ndarray
    measured: np.ndarray
