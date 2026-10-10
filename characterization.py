"""Two SOL rounds -> reciprocal non-inverting converter characterization.

Pure numerical/file layer; the input is S11 at RF in all six acquisition files.
Standards are evaluated at RF for round 1 and mapped IF (RF +/- LO) for round 2.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import io
import json
import zipfile
import numpy as np
from parser import Dataset, UNITS, number, to_complex, load_file
from frequency_mapping import output_frequencies, frequency_relation

ROLES = ('input_open', 'input_short', 'input_load',
         'output_open', 'output_short', 'output_load')
LABELS = ('输入端 Open', '输入端 Short', '输入端 Load',
          '混频器输出端 Open', '混频器输出端 Short', '混频器输出端 Load')

SAMPLING_METHODS = {
    'cubic_ri': '三次样条插值（幅度 / 解缠绕相位）',
    'linear_ri': '线性插值（幅度 / 解缠绕相位）',
}
# Keep historical API / QSettings keys, recording their actual coordinates.
# v1.5.1 changes linear and v1.5.2 changes cubic interpolation to polar form.
INTERPOLATION_COORDINATES = {
    'linear_ri': 'linear_magnitude_unwrapped_phase',
    'cubic_ri': 'cubic_magnitude_unwrapped_phase',
}

@dataclass
class Standard:
    name: str
    frequency: np.ndarray
    gamma: np.ndarray
    z0: float

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


def read_text(path):
    raw = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'gb18030', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError(f'{path}: 无法识别文本编码。')


def parse_s1p(text, name='standard.s1p'):
    fmt, scale, z0 = 'MA', 1e9, 50.
    tokens = []
    seen = False
    for line_no, line in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        line = line.partition('!')[0].strip()
        if not line:
            continue
        if line.startswith('['):
            raise ValueError(f'{name}: 当前仅支持 Touchstone 1.x S1P。')
        if line.startswith('#'):
            if seen or tokens:
                raise ValueError(f'{name}: 选项行重复或位置错误。')
            opts = line[1:].upper().split()
            defaults = ['GHZ', 'S', 'MA', 'R', '50']
            if len(opts) > 5:
                raise ValueError(f'{name}: 无效选项行。')
            defaults[:len(opts)] = opts
            unit, param, fmt, r, impedance = defaults
            if unit not in UNITS or param != 'S' or fmt not in ('DB', 'MA', 'RI') or r != 'R':
                raise ValueError(f'{name}: 仅支持 S / RI、MA、DB。')
            scale, z0 = UNITS[unit], number(impedance)
            seen = True
            continue
        try:
            tokens.extend(number(t) for t in line.split())
        except ValueError as exc:
            raise ValueError(f'{name}: 第 {line_no} 行不是数值。') from exc
    if not tokens or len(tokens) % 3:
        raise ValueError(f'{name}: S1P 每点应为频率及两个参数，共三个数。')
    arr = np.asarray(tokens).reshape(-1, 3)
    freq = arr[:, 0] * scale
    gamma = to_complex(arr[:, 1:], fmt)
    if not np.isfinite(z0) or z0 <= 0 or not np.all(np.isfinite(freq)) or not np.all(np.isfinite(gamma)):
        raise ValueError(f'{name}: 参考阻抗/频率/反射系数必须为有效有限数。')
    if np.any(freq < 0):
        raise ValueError(f'{name}: 不能含负频率。')
    order = np.argsort(freq, kind='stable')
    freq, gamma = freq[order], gamma[order]
    if np.any(np.diff(freq) <= 0):
        raise ValueError(f'{name}: 标准定义含重复频点，无法唯一求值。')
    return Standard(name, freq, gamma, z0)


def load_standard(path):
    return parse_s1p(read_text(path), str(path))


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
    z0s = [float(d.metadata['参考阻抗'].split()[0]) for d in datasets] + [s.z0 for s in standards]
    if not np.allclose(z0s, z0s[0], rtol=1e-12, atol=0):
        raise ValueError('测量与标准定义的参考阻抗不一致；不自动重归一化。')
    gs, counts = [], []
    for n, std in enumerate(standards):
        g, count = sample_standard(std, freq if n < 3 else ifreq,
                                   options.standard_sampling, options.frequency_tolerance_hz)
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
    diagnostics = {'SOL1_condition': cond1, 'SOL2_condition': cond2,
                   'Direct_fit_condition': direct_cond, 'SOL1_residual': residual1,
                   'SOL2_residual': residual2, 'Two_path_complex_difference': cross_error}
    manifest = {'algorithm': 'SOL Mobius composition / reciprocal converter', 'version': '1.6.2',
                'lo_hz': options.lo_hz, 'frequency_conversion': options.frequency_conversion,
                'if_relation': frequency_relation(options.frequency_conversion)+' (non-inverting)',
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


def s2p_text(result):
    d = result.dataset
    lines = ['! VMC calibration mixer + filter characterization',
             f'! Stimulus=RF; {result.manifest["if_relation"]}; reciprocal S21=S12',
             f'! LO_Hz={result.manifest["lo_hz"]:.17g}',
             f'! SecondRound={result.manifest["second_round"]}; StandardSampling={result.manifest["standard_sampling"]}',
             f'! InterpolationCoordinates={result.manifest["interpolation_coordinates"]}',
             f'! SharedKit={result.manifest["standard_kit"]}; CubicBoundary={result.manifest["interpolation_boundary"]}; Extrapolation=False',
             f'! GlobalRootSign={result.manifest["root_sign"]}; absolute sign not identified by SOL reflection',
             f'# Hz S RI R {result.manifest["z0_ohm"]:.17g}']
    for i, freq in enumerate(d.axes['StimulusFreq']):
        row = [freq]
        for p in ('S11', 'S21', 'S12', 'S22'):
            z = d.s[p][i]; row.extend((z.real, z.imag))
        lines.append(' '.join(format(float(x), '.17g') for x in row))
    return '\n'.join(lines)+'\n'


def s2px_text(result):
    d = result.dataset
    out = io.StringIO()
    out.write('!CSV A.01.00\n!Source: Self-developed Mixer Characterization (not a Keysight-generated file)\n')
    out.write(f'!Reference Impedance: {result.manifest["z0_ohm"]:.17g} ohm\n')
    writer = csv.writer(out)
    writer.writerow(['SegIndex', 'InputFreq', 'OutputFreq', 'LO1Freq']+
                    [h for p in ('S11', 'S21', 'S12', 'S22') for h in (f'{p} Mag (dB)', f'{p} Phase (Deg)')])
    for i in range(d.count):
        row = [0, d.axes['InputFreq'][i], d.axes['OutputFreq'][i], d.axes['LO1Freq'][i]]
        for p in ('S11', 'S21', 'S12', 'S22'):
            z = d.s[p][i]
            # RI S2P remains authoritative for zero magnitudes; DB cannot encode
            # a defined phase at zero. Avoid producing non-readable S2PX.
            if abs(z) == 0:
                raise ValueError('S2PX 幅相格式无法表示零幅度的有效相位；请仅导出 RI S2P。')
            row += [20*np.log10(abs(z)), np.rad2deg(np.angle(z))]
        writer.writerow([format(float(x), '.17g') for x in row])
    return out.getvalue()


def diagnostic_csv(result):
    columns = dict(result.dataset.axes)
    for key, z in result.terms.items():
        columns[key+'_Real'], columns[key+'_Imag'] = z.real, z.imag
    for i, role in enumerate(ROLES):
        z, m = result.evaluated_standards[:, i], result.measured[:, i]
        columns[role+'_Gamma_Real'], columns[role+'_Gamma_Imag'] = z.real, z.imag
        columns[role+'_S11_Real'], columns[role+'_S11_Imag'] = m.real, m.imag
    columns.update(result.diagnostics)
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(columns)
    writer.writerows([[format(float(x), '.17g') for x in row] for row in zip(*columns.values())])
    return '\ufeff'+out.getvalue()


def export_s2p(result, path):
    Path(path).write_text(s2p_text(result), encoding='ascii')


def export_bundle(result, path):
    """Complete reproducible record; S2P is authoritative, optional DB CSV."""
    manifest = dict(result.manifest)
    payloads = {'characterized_mixer.s2p': s2p_text(result), 'sol_diagnostics.csv': diagnostic_csv(result)}
    try:
        payloads['characterized_mixer.s2px'] = s2px_text(result)
    except ValueError as exc:
        manifest['s2px_export_note'] = str(exc)
    payloads['characterization_report.json'] = json.dumps(manifest, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            archive.writestr(name, content.encode('utf-8'))
