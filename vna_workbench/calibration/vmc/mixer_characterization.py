from __future__ import annotations
from vna_workbench.calibration.vmc.models import ROLES, LABELS, Options, Characterization
from pathlib import Path
import hashlib
import numpy as np
from vna_workbench.data.models import Dataset
from vna_workbench.data.touchstone import load_file
from vna_workbench.core.frequency_conversion import output_frequencies, frequency_relation, is_inverting, phase_convention
from vna_workbench.core.standard_sampling import sample_standard, SAMPLING_METHODS, INTERPOLATION_COORDINATES
from vna_workbench.core.sol import solve_sol, mobius
from vna_workbench.data.standard_definitions import load_standard
from vna_workbench.calibration.vmc.characterization_io import s2p_text

def continuous_root(product, sign=1):
    if sign not in (-1, 1):
        raise ValueError('传输开方符号必须为 +1 或 -1。')
    # No arbitrary phase fitting: only unwrap the product and choose a global sign.
    return sign*np.sqrt(np.abs(product))*np.exp(.5j*np.unwrap(np.angle(product)))


def characterize(measurement_paths, standard_paths, options=Options()):
    if len(measurement_paths) != 6 or len(standard_paths) not in (3, 6):
        raise ValueError('需要六个 S2P 测量及 OPEN/SHORT/LOAD 三个 S1P 定义。')
    # Public GUI uses one shared kit; retain six-path API compatibility.
    shared_kit = len(standard_paths) == 3
    standard_paths = list(standard_paths)
    unique_standards = [load_standard(p) for p in standard_paths]
    if shared_kit:
        standard_paths = standard_paths * 2
    if options.standard_sampling not in SAMPLING_METHODS:
        raise ValueError('未知标准件求值方法。')
    if (not np.isfinite(options.lo_hz) or options.lo_hz <= 0
            or not np.isfinite(options.max_condition) or options.max_condition <= 1
            or not np.isfinite(options.frequency_tolerance_hz) or options.frequency_tolerance_hz < 0):
        raise ValueError('LO、条件数限制或频率容差无效。')
    if options.second_round not in ('raw', 'corrected'):
        raise ValueError('第二轮必须明确为原始数据或已经第一轮修正的数据。')
    datasets = [load_file(p) for p in measurement_paths]
    if any(not d.kind.startswith('S2P /') for d in datasets):
        raise ValueError('六个采集输入必须为两端口 S2P。')
    standards = unique_standards * 2 if shared_kit else unique_standards
    freq = datasets[0].axes['StimulusFreq']
    if np.any(np.diff(freq) <= 0):
        raise ValueError('测量 RF 频率必须严格递增且不重复；不自动重排或丢弃点。')
    for role, data in zip(LABELS, datasets):
        axis = data.axes['StimulusFreq']
        if data.count != len(freq) or np.any(np.diff(axis) <= 0) or not np.all(np.abs(axis-freq) <= options.frequency_tolerance_hz):
            raise ValueError(f'{role}: 六个测量的 RF 频率网格必须一致；测量数据不插值。')
    ifreq = output_frequencies(freq, options.lo_hz, options.frequency_conversion)
    inverted = is_inverting(options.frequency_conversion)
    z0s = [float(d.metadata['参考阻抗'].split()[0]) for d in datasets] + [s.z0 for s in standards]
    if not np.allclose(z0s, z0s[0], rtol=1e-12, atol=0):
        raise ValueError('测量与标准定义的参考阻抗不一致；不自动重归一化。')
    gs, counts = [], []
    for n, std in enumerate(standards):
        g, count = sample_standard(std, freq if n < 3 else ifreq,
                                   options.standard_sampling, options.frequency_tolerance_hz)
        if inverted and n >= 3:
            g = g.conj()
        gs.append(g); counts.append(count)
    gamma = np.column_stack(gs)
    measured = np.column_stack([d.s['S11'] for d in datasets])
    first, cond1, residual1 = solve_sol(measured[:, :3], gamma[:, :3], options.max_condition)
    second, cond2, residual2 = solve_sol(measured[:, 3:], gamma[:, 3:], options.max_condition)
    if options.second_round == 'raw':
        m1 = mobius(first)
        if np.any(np.linalg.cond(m1) > options.max_condition):
            raise ValueError('第一轮误差矩阵病态，无法消除输入误差。')
        mix = np.linalg.solve(m1, mobius(second))
        scale = mix[:, 1, 1]
        if np.any(np.abs(scale) < 1e-14*np.max(np.abs(mix), axis=(1, 2))):
            raise ValueError('混频器矩阵无法归一化，右下角接近零。')
        mix /= scale[:, None, None]
        c11, c22 = mix[:, 0, 1], -mix[:, 1, 0]
        product = mix[:, 0, 0]-mix[:, 0, 1]*mix[:, 1, 0]
        d1, s1, r1 = first
        delta = measured[:, 3:]-d1[:, None]
        denom = r1[:, None]+s1[:, None]*delta
        if np.any(np.abs(denom) < 1e-14):
            raise ValueError('第一轮反射修正分母接近零。')
        corrected = delta/denom
    else:
        c11, c22, product = second
        corrected = measured[:, 3:]
    # Independent extraction path on port-corrected reflection data.
    direct, direct_cond, _ = solve_sol(corrected, gamma[:, 3:], options.max_condition)
    cross_error = np.max(np.abs(np.column_stack((c11, c22, product))-np.column_stack(direct)), axis=1)
    effective_c22 = c22.copy()
    if inverted:
        c22 = c22.conj()  # Return the physical IF-port reflection.
    transfer = continuous_root(product, options.root_sign)
    warnings = ['反射 SOL 仅确定 S12×S21；S12=S21 基于互易假设，整体 ± 符号须单独确认。',
                '传输相位由乘积连续解缠后开方；稀疏采样不能保证真实相位分支。',
                '本结果为混频器＋滤波器整体参考面，不包含第一轮输入误差盒。']
    if any(counts):
        warnings.append(f'标准定义采用{SAMPLING_METHODS[options.standard_sampling]}；该规则未确认与 Keysight 内部求值相同。')
    if np.any(np.abs(product) < 1e-14):
        warnings.append('部分传输乘积接近零，传输相位/分支不可靠。')
    terms = dict(zip(('D1', 'S1', 'R1', 'D2', 'S2', 'R2'), (*first, *second)))
    terms['S12_times_S21'] = product
    terms['C22_input_equivalent'] = effective_c22
    if inverted:
        warnings.append('高边 LO：仅第二轮标准取共轭；S22 为物理 IF 反射，S21/S12 为输入参考等效传输，非绝对 LO 相位。')
    diagnostics = {'SOL1_condition': cond1, 'SOL2_condition': cond2,
                   'Direct_fit_condition': direct_cond, 'SOL1_residual': residual1,
                   'SOL2_residual': residual2, 'Two_path_complex_difference': cross_error}
    manifest = {'algorithm': 'SOL Mobius composition / reciprocal converter', 'version': '1.8.0',
                'lo_hz': options.lo_hz, 'frequency_conversion': options.frequency_conversion,
                'if_relation': frequency_relation(options.frequency_conversion),
                'spectral_inversion': inverted, 'phase_convention': phase_convention(options.frequency_conversion),
                'evaluated_standards': 'solver values; second round conjugated for high_side',
                'second_round': options.second_round, 'standard_sampling': options.standard_sampling,
                'interpolation_coordinates': INTERPOLATION_COORDINATES[options.standard_sampling],
                'standard_kit': 'shared_open_short_load' if shared_kit else 'per_round_legacy',
                'interpolation_boundary': 'not-a-knot' if options.standard_sampling.startswith('cubic_') else None,
                'extrapolation': False,
                'frequency_tolerance_hz': options.frequency_tolerance_hz,
                'max_condition': options.max_condition, 'root_sign': options.root_sign,
                'reciprocal_assumption': True, 'z0_ohm': z0s[0], 'points': len(freq),
                'warnings': warnings, 'interpolated_points_per_standard': dict(zip(ROLES, counts)),
                'max_diagnostics': {k: float(np.max(v)) for k, v in diagnostics.items()},
                'inputs': []}
    for role, mp, sp in zip(ROLES, measurement_paths, standard_paths):
        manifest['inputs'].append({'role': role, 'measurement_path': str(mp), 'standard_path': str(sp),
                                  'measurement_sha256': hashlib.sha256(Path(mp).read_bytes()).hexdigest(),
                                  'standard_sha256': hashlib.sha256(Path(sp).read_bytes()).hexdigest()})
    dataset = Dataset('characterized_mixer.s2p', 'S2P / Characterized',
                      {'S11': c11, 'S12': transfer.copy(), 'S21': transfer, 'S22': c22},
                      {'StimulusFreq': freq.copy(), 'InputFreq': freq.copy(), 'OutputFreq': ifreq,
                       'LO1Freq': np.full(len(freq), options.lo_hz)}, np.zeros(len(freq), dtype=int),
                      {'参考阻抗': f'{z0s[0]:g} Ω', '数据格式': 'RI', '频率映射': frequency_relation(options.frequency_conversion)+'；Stimulus=RF',
                       '第二轮': options.second_round, '标准插值': options.standard_sampling,
                       '互易开方符号': str(options.root_sign)}, warnings)
    if not all(np.all(np.isfinite(v)) for v in dataset.s.values()):
        raise ValueError('求解产生非有限值，未输出表征文件。')
    result = Characterization(dataset, terms, diagnostics, manifest, gamma, measured)
    dataset.raw_text = s2p_text(result)
    return result
