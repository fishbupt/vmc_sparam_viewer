from __future__ import annotations
from vna_workbench.data.models import Standard
from pathlib import Path
import numpy as np
from vna_workbench.data.touchstone import UNITS, number, to_complex

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
