#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出本地 Keysight PNA 窗口中的每条复数 Trace。

准备环境: uv sync --locked
运行: uv run --locked python export_window_traces.py
指定目录: uv run --locked python export_window_traces.py --output D:/PNA_Traces
需安装 Keysight IO Libraries Suite 或其他支持 HiSLIP 的 VISA 实现。

默认连接 TCPIP::127.0.0.1::hislip0，激活窗口 2。
每条曲线存为独立 .s1p (RI)，并输出 manifest.json 记录真实参数。
S21、接收机比值等借用 s1p 的单复数列格式；它们并非物理单端口 S11。
R 50 仅为存储约定，不进行阻抗重归一化。仅支持频率扫描。
导出 SDATA（保留相位），不是屏幕 LogM 的单列 dB 值。
不导出 Memory 曲线，也不将方程结果误作底层测量导出。
文件保存在运行此脚本的电脑，不是通过 MMEM 保存到仪器端。

SCPI 参考: Keysight VNA Help / Programming / GP-IB_Command_Finder /
Display.htm, System.htm, Calculate/MeasurePARameter.htm,
Calculate/MeasureDATA.htm。
"""

import argparse
from contextlib import closing
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys


def unquote(value):
    return value.strip().strip('"')


def safe_name(name):
    name = name.replace('/', '_over_')
    return re.sub(r'[\\:*?"<>|\x00-\x1f]', '_', name).rstrip(' .')


class ScpiTransportError(RuntimeError):
    """查询失败后停止使用可能已失步的响应流。"""


def read_response(inst, command):
    try:
        return inst.query(command).strip()
    except Exception as exc:
        raise ScpiTransportError(f'{command}: 查询失败 ({exc})；本次导出已停止') from exc


def check_error(inst, command):
    response = read_response(inst, 'SYST:ERR?')
    if int(response.split(',', 1)[0]) != 0:
        raise RuntimeError(f'{command}: {response}')


def query(inst, command):
    result = read_response(inst, command)
    check_error(inst, command)
    return result


def write(inst, command):
    inst.write(command)
    check_error(inst, command)


def numbers(inst, command):
    raw = query(inst, command)
    values = [float(x) for x in raw.split(',')]
    if not values or not all(math.isfinite(x) and abs(x) < 1e30 for x in values):
        raise ValueError(f'{command}: 返回空值、非有限值或仪器无效数据占位符')
    return values


def window_measurements(inst, window):
    """根据测量自身的所属窗口和 Trace ID 建立映射，不依赖前面板选择。"""
    catalogue = unquote(query(inst, 'SYST:MEAS:CAT?'))
    mapping = {}
    for value in catalogue.split(','):
        if not value.strip():
            continue
        measurement = int(value)
        if measurement <= 0:
            raise ValueError(f'测量目录返回非法编号: {measurement}')
        if int(query(inst, f'SYST:MEAS{measurement}:WIND?')) != window:
            continue
        trace = int(query(inst, f'SYST:MEAS{measurement}:TRAC?'))
        if trace <= 0 or trace in mapping:
            raise ValueError(f'窗口 {window} 的 Trace 映射非法或重复: {trace}')
        mapping[trace] = measurement
    return mapping


def export_trace(inst, window, trace, output, measurement=None):
    if measurement is None:
        measurement = window_measurements(inst, window).get(trace)
    if measurement is None or measurement <= 0:
        raise ValueError(f'窗口 {window} Trace {trace} 未找到有效测量编号')
    channel = int(query(inst, f'SYST:MEAS{measurement}:CHAN?'))
    if channel <= 0:
        raise ValueError(f'测量 {measurement} 返回无效通道 {channel}，不发送 CALC{channel} 命令')
    print(f'映射: Window {window} Trace {trace} → 测量 {measurement}, Channel {channel}')
    prefix = f'CALC{channel}:MEAS{measurement}'
    parameter = unquote(query(inst, f'{prefix}:PAR?'))
    # 参数中可能有逗号（源端口），不能把整个返回字符串再按逗号拆开。
    parameter = re.sub(r'\s+', '', parameter)
    if not parameter:
        raise ValueError('测量参数名称为空')
    sweep = unquote(query(inst, f'SENS{channel}:SWE:TYPE?')).upper()
    if sweep not in {'LIN', 'LOG', 'SEGM'}:
        raise ValueError(f'仅支持 LIN/LOG/SEGM 频率扫描，当前为 {sweep}')
    if int(query(inst, f'{prefix}:EQU:STAT?')):
        raise ValueError('当前 Trace 启用了 Equation；SDATA 不保证返回方程结果，已跳过')
    # Standard 频率扫描的默认 X 轴为 Hz；不使用显示缩放后的 GHz 数值。
    frequency = numbers(inst, f'{prefix}:DATA:X?')
    data = numbers(inst, f'{prefix}:DATA:SDATA?')
    if len(data) != 2 * len(frequency):
        raise ValueError(f'频率 {len(frequency)} 点，复数数据 {len(data)} 个数，长度不匹配')
    if any(f <= 0 for f in frequency):
        raise ValueError('频率必须大于零')
    if any(b <= a for a, b in zip(frequency, frequency[1:])):
        raise ValueError('频率不是严格递增；请检查分段扫描设置')
    name = f'Tr{measurement}_{parameter}'
    path = output / (safe_name(name) + '.s1p')
    if path.exists():
        path = output / (safe_name(name) + f'_W{window}T{trace}.s1p')
    header = [
        '! Keysight PNA single complex trace export',
        f'! Trace: {name}',
        f'! Parameter: {parameter}',
        f'! Window: {window}; window trace ID: {trace}; channel: {channel}; measurement: {measurement}',
        '! Data: SDATA; correction follows current instrument state.',
        '! One complex curve stored in the S11 column; original parameter is given above.',
        '! For transmission/receiver ratios, this is a curve container, not a physical one-port network.',
        '! R 50 is a file convention only; no impedance renormalization was performed.',
        '# Hz S RI R 50',
    ]
    # x 模式防止覆盖已有文件。
    with path.open('x', encoding='ascii', errors='backslashreplace', newline='\n') as handle:
        handle.write('\n'.join(header) + '\n')
        for i, f in enumerate(frequency):
            handle.write(f'{f:.17g} {data[2*i]:.17g} {data[2*i+1]:.17g}\n')
    return dict(window_trace_id=trace, channel=channel, measurement=measurement,
                parameter=parameter, trace_name=name, file=path.name,
                points=len(frequency), frequency_unit='Hz')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--resource', default='TCPIP::127.0.0.1::hislip0')
    parser.add_argument('--window', type=int, default=2)
    parser.add_argument('--output', type=Path, default=Path.cwd() / 'PNA_Traces')
    parser.add_argument('--timeout', type=int, default=30000, help='VISA 超时，毫秒')
    args = parser.parse_args()
    try:
        import pyvisa
    except ImportError:
        parser.exit(1, '请在工具目录运行: uv run --locked python export_window_traces.py\n')
    # 每次建立独立子目录，避免覆盖上一次导出。
    output = args.output.resolve() / f'Window{args.window}_{datetime.now():%Y%m%d_%H%M%S_%f}'
    output.mkdir(parents=True, exist_ok=False)
    report = dict(resource=args.resource, window=args.window, traces=[], errors=[])
    try:
        # ResourceManager 不提供 __enter__/__exit__，用 closing 显式调用 close。
        # 内层先关闭仪器连接，外层再关闭 VISA 资源管理器。
        with closing(pyvisa.ResourceManager()) as manager:
            with closing(manager.open_resource(args.resource)) as inst:
                inst.timeout = args.timeout
                inst.read_termination = '\n'
                inst.write_termination = '\n'
                inst.chunk_size = 1024 * 1024
                report['instrument'] = inst.query('*IDN?').strip()
                print('已连接:', report['instrument'])
                # 报告并清空连接前已有的错误，避免误判为本脚本命令错误。
                for _ in range(100):
                    old_error = inst.query('SYST:ERR?').strip()
                    if int(old_error.split(',', 1)[0]) == 0:
                        break
                    print('仪器原有错误:', old_error)
                else:
                    raise RuntimeError('仪器错误队列持续非空')
                write(inst, f'SYST:ACT:WIND {args.window}')
                catalogue = unquote(query(inst, f'DISP:WIND{args.window}:CAT?'))
                traces = [int(x.strip()) for x in catalogue.split(',') if x.strip()]
                if not traces or any(t <= 0 for t in traces):
                    raise RuntimeError('窗口中没有可导出的 Trace')
                print(f'窗口 {args.window}: {traces}')
                mapping = window_measurements(inst, args.window)
                old_format = query(inst, 'FORM:DATA?')
                transport_failed = False
                try:
                    write(inst, 'FORM:DATA ASC,0')
                    for trace in traces:
                        try:
                            if trace not in mapping:
                                raise ValueError(f'窗口 Trace {trace} 没有匹配测量，不猜测其通道')
                            record = export_trace(inst, args.window, trace, output, mapping[trace])
                            report['traces'].append(record)
                            print(f"已保存 {record['file']} ({record['points']} 点)")
                        except Exception as exc:
                            report['errors'].append(dict(window_trace_id=trace, error=str(exc)))
                            print(f'Trace {trace} 导出失败: {exc}', file=sys.stderr)
                            # 超时后响应流可能失步，不能继续把别的响应当作数据。
                            if isinstance(exc, (ScpiTransportError, pyvisa.errors.VisaIOError)):
                                transport_failed = True
                                raise
                except ScpiTransportError:
                    transport_failed = True
                    raise
                finally:
                    if not transport_failed:
                        inst.write(f'FORM:DATA {old_format}')
    except Exception as exc:
        report['errors'].append(dict(error=str(exc)))
        print(f'错误: {exc}', file=sys.stderr)
    finally:
        (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"完成: 成功 {len(report['traces'])} 条，错误 {len(report['errors'])} 项")
        print('保存目录:', output)
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
