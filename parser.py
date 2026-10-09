"""Pure NumPy parsers for Touchstone 1.x S2P and Keysight converter CSV S2PX."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import csv
import io
import re
import xml.etree.ElementTree as ET
import numpy as np

PARAMS = ('S11', 'S12', 'S21', 'S22')
UNITS = {'HZ': 1., 'KHZ': 1e3, 'MHZ': 1e6, 'GHZ': 1e9}

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


def number(value: str) -> float:
    return float(value.strip().replace('D', 'E').replace('d', 'e'))


def to_complex(pairs, fmt):
    a = np.asarray(pairs, dtype=float)
    if fmt == 'RI':
        return a[..., 0] + 1j * a[..., 1]
    amplitude = 10 ** (a[..., 0] / 20) if fmt == 'DB' else a[..., 0]
    if fmt == 'MA' and np.any(amplitude < 0):
        raise ValueError('MA 幅度不能为负数。')
    return amplitude * np.exp(1j * np.deg2rad(a[..., 1]))


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


def parse_text(text: str, name='pasted.s2p') -> Dataset:
    text = text.lstrip('\ufeff')
    lines = text.splitlines()
    body = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith('!')]
    if not body:
        raise ValueError('没有找到数值数据。')
    first = body[0].lower()
    if ',' in first and 'inputfreq' in first:
        data = parse_s2px(text, name)
    else:
        data = parse_s2p(text, name)
    data.raw_text = text
    for key, array in {**data.axes, **data.s, **data.auxiliary}.items():
        if not np.all(np.isfinite(array)):
            raise ValueError(f'{key} 含有 NaN、Inf 或数值溢出。')
    for key, axis in data.axes.items():
        if np.any(axis < 0):
            raise ValueError(f'{key} 存在负频率。')
    if data.count == 1:
        data.warnings.append('文件仅含 1 个数据点：显示散点，不能据此判断频率响应趋势。')
    return data


def load_file(path):
    raw = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'gb18030', 'cp1252'):
        try:
            return parse_text(raw.decode(encoding), str(path))
        except UnicodeDecodeError:
            continue
    raise ValueError('无法识别文本编码。')


def parse_s2p(text, name):
    fmt, scale, z0 = 'MA', 1e9, 50.
    tokens, comments = [], []
    option_seen = False
    for lineno, line in enumerate(text.splitlines(), 1):
        content, sep, comment = line.partition('!')
        if sep:
            comments.append(comment)
        content = content.strip()
        if not content:
            continue
        if content.startswith('['):
            raise ValueError('当前版本仅支持 Touchstone 1.x 二端口；不支持带 [Version] 等关键字的 Touchstone 2.x。')
        if content.startswith('#'):
            if tokens or option_seen:
                raise ValueError(f'第 {lineno} 行：重复或位置不正确的选项行。')
            option_seen = True
            opts = content[1:].upper().split()
            defaults = ['GHZ', 'S', 'MA', 'R', '50']
            if len(opts) > 5:
                raise ValueError('无法识别 Touchstone 选项行。')
            defaults[:len(opts)] = opts
            unit, parameter, fmt, r, impedance = defaults
            if unit not in UNITS or parameter != 'S' or fmt not in ('DB', 'MA', 'RI') or r != 'R':
                raise ValueError('仅支持 Hz/kHz/MHz/GHz 的 S 参数及 DB/MA/RI 格式。')
            scale, z0 = UNITS[unit], number(impedance)
            if not np.isfinite(z0) or z0 <= 0:
                raise ValueError('参考阻抗必须为正有限数。')
            continue
        try:
            tokens.extend(number(x) for x in content.split())
        except ValueError as exc:
            raise ValueError(f'第 {lineno} 行不是有效数值记录。') from exc
    if not tokens or len(tokens) % 9:
        raise ValueError(f'S2P 应每点有 9 个数值；当前共 {len(tokens)} 个。文件可能截断或含不支持的噪声数据。')
    array = np.array(tokens).reshape(-1, 9)
    c = to_complex(array[:, 1:].reshape(-1, 4, 2), fmt)
    data = Dataset(name, 'S2P / Touchstone', dict(zip(('S11', 'S21', 'S12', 'S22'), c.T)),
                   {'StimulusFreq': array[:, 0] * scale}, np.zeros(len(array), dtype=int),
                   {'参考阻抗': f'{z0:g} Ω', '数据格式': fmt, '数据顺序': 'S11, S21, S12, S22'})
    comment_text = '\n'.join(comments)
    start, stop = comment_text.find('<MixerConfiguration>'), comment_text.find('</MixerConfiguration>')
    if start >= 0 and stop >= 0:
        try:
            root = ET.fromstring(comment_text[start:stop + len('</MixerConfiguration>')])
            for element in root.iter():
                if element.tag == 'BaseSettings':
                    for child in element:
                        data.metadata[f'Base/{child.tag}'] = child.get('value', '')
            segmented = root.find('./BaseSettings/SegmentSweepMode')
            is_segmented = segmented is not None and segmented.get('value', '').lower() == 'true'
            if is_segmented:
                segments = root.findall('./SegmentList/MixerSegment')
            else:
                segments = root.findall('./MixerSegment[@name="NonSegmentSweepFrequencies"]')
            for seg in segments:
                for child in seg:
                    if 'value' in child.attrib:
                        data.metadata[f'{seg.get("name")}/{child.tag}'] = child.get('value', '')
            if not is_segmented and segments:
                declared = segments[0].find('NumberOfPoints')
                if declared is not None and int(declared.get('value', '0')) != data.count:
                    data.warnings.append(f'XML 配置为 {declared.get("value")} 点，正文实际为 {data.count} 点；按正文显示。')
            data.warnings.append('S2P 仅提供 Stimulus 频率；XML 作为配置信息展示，不自动生成或推断 Input/Output/LO 频率轴。')
        except (ET.ParseError, ValueError) as exc:
            data.warnings.append(f'Mixer XML 无法完整解析：{exc}；S 参数仍按正文读取。')
    if not option_seen:
        data.warnings.append('未找到选项行：按 Touchstone 默认 GHz / S / MA / R 50 读取。')
    if np.any(np.diff(data.axes['StimulusFreq']) <= 0):
        data.warnings.append('Stimulus 频率包含重复点或非递增点；保留原始顺序。')
    return data


def parse_s2px(text, name):
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith('!')]
    reader = csv.reader(lines)
    header = [s.strip() for s in next(reader)]
    normalized = [re.sub(r'\s+', '', x).lower() for x in header]
    if len(set(normalized)) != len(normalized):
        raise ValueError('CSV 包含重复列名。')
    lookup = dict(zip(normalized, range(len(header))))
    def col(key):
        k = re.sub(r'\s+', '', key).lower()
        if k not in lookup:
            raise ValueError(f'S2PX 缺少列：{key}')
        return lookup[k]
    rows = []
    for index, row in enumerate(reader, 2):
        if len(row) != len(header):
            raise ValueError(f'CSV 第 {index} 行有 {len(row)} 列，表头为 {len(header)} 列。')
        try:
            rows.append([number(x) for x in row])
        except ValueError as exc:
            raise ValueError(f'CSV 第 {index} 行存在非数值字段。') from exc
    if not rows:
        raise ValueError('S2PX 有表头但没有数据。')
    array = np.array(rows)
    s = {p: to_complex(array[:, [col(f'{p} Mag (dB)'), col(f'{p} Phase (Deg)')]], 'DB') for p in PARAMS}
    axes = {'InputFreq': array[:, col('InputFreq')], 'OutputFreq': array[:, col('OutputFreq')]}
    for key in ('LO1Freq', 'LO2Freq'):
        if key.lower() in lookup:
            axes[key] = array[:, col(key)]
    seg = array[:, col('SegIndex')] if 'segindex' in lookup else np.zeros(len(array))
    if not np.all(np.isfinite(seg)) or not np.all(seg == np.floor(seg)):
        raise ValueError('SegIndex 必须为有限整数。')
    aux = {h: array[:, i] for i, h in enumerate(header) if h.lower().endswith('power')}
    meta = {'参考阻抗': '未在文件中声明（不假定为 50 Ω）', '数据格式': 'DB / Deg', '频率单位': 'Hz', '数据映射': '按 CSV 列名匹配'}
    for line in text.splitlines():
        if line.startswith('!') and ':' in line:
            key, val = line[1:].split(':', 1)
            meta[key.strip()] = val.strip()
    return Dataset(name, 'S2PX / Keysight CSV', s, axes, seg.astype(int), meta, auxiliary=aux)


def table_data(data):
    cols = {'SegIndex': data.segment, **{k + ' (Hz)': v for k, v in data.axes.items()}, **data.auxiliary}
    for p in PARAMS:
        z = data.s[p]
        cols[p + ' Real'] = z.real
        cols[p + ' Imag'] = z.imag
        cols[p + ' Mag (dB)'] = values(z, 'dB', data.segment)
        cols[p + ' Phase (Deg)'] = values(z, 'Phase', data.segment)
    return list(cols), list(cols.values())


def export_csv(data, path):
    headers, columns = table_data(data)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in zip(*columns):
            writer.writerow([format(float(x), '.17g') for x in row])
