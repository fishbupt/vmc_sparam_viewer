# PNA 窗口 Trace 导出工具 · v1.0.0

独立命令行脚本，可复制此目录到其他电脑运行，无需安装 VNA Calibration Workbench 或 GUI 依赖。Python 3.10+，需安装支持 HiSLIP 的 VISA 实现（例如 Keysight IO Libraries Suite）。

## 运行

在仓库根目录执行：

```powershell
python -m pip install -r tools/pna_trace_export/requirements.txt
python tools/pna_trace_export/export_window_traces.py --output D:/PNA_Traces
```

也可进入此目录执行 `python export_window_traces.py`，或直接在 PyCharm 中运行该脚本。

| 选项 | 默认值 | 含义 |
| --- | --- | --- |
| `--resource` | `TCPIP::127.0.0.1::hislip0` | VISA 资源；PNA 软件需在本机运行并启用 HiSLIP |
| `--window` | `2` | 激活并导出的窗口编号 |
| `--output` | 当前工作目录下的 `PNA_Traces` | 保存到运行脚本的电脑 |
| `--timeout` | `30000` | VISA 超时，毫秒 |

每次创建 `Window2_日期_时间_微秒` 子目录，包含各 Trace 的 `.s1p` 和 `manifest.json`。退出码 0 为全部成功，1 表示有错误；错误及已成功文件会记录在 manifest 中。

## 命名与文件含义

- `Tr1_S11.s1p`、`Tr6_a2_over_b2,1.s1p`，不包含显示格式 LogM。
- 窗口内部 Trace ID 与屏幕 Tr 编号可能不同；脚本选择 Trace 后查询实际测量编号，不直接使用窗口目录编号命名。
- Windows 不允许文件名包含 `/`，替换为 `_over_`；原参数保留在文件注释和 manifest 中。仪器可能返回等价物理接收机名称，而非屏幕上的逻辑 a/b 名称。
- 每个文件仅有频率、实部、虚部，使用 `# Hz S RI R 50` 和 17 位有效数字，不丢失相位。
- **S21、接收机比值等借用 S1P 的 S11 列存储，并非真实单端口网络。** R 50 仅为文件约定，未进行重归一化，不能直接当作物理 S11 使用。
- 导出 SDATA，校准状态遵循仪器当前设置；不等同于显示变换、平滑、Data/Memory 运算后的屏幕曲线。不导出 Memory 曲线；启用 Equation 的 Trace 会报错跳过。
- 面向默认频率横轴（Hz）的 LIN / LOG / SEGM 扫描；要求频率严格递增。功率 / CW / 非默认横轴不属于支持范围。
- 脚本不触发新扫频、不冻结扫频，读取现有测量数据；如要求各 Trace 对应同一完整采集状态，请先在 PNA 完成扫频并 Hold。
- 激活窗口 2 后依次选择 Trace，结束时保留最后一次选择；临时切换 ASCII 数据传输，结束时恢复原 FORM:DATA。

## SCPI 流程

`DISP:WIND2:CAT?` → `DISP:WIND2:TRAC<t>:SEL` → `SYST:ACT:CHAN?` / `SYST:ACT:MEAS:NUMB?` → `CALC<c>:MEAS<m>:PAR?` → `DATA:X?` / `DATA:SDATA?`。

依赖 Keysight PNA 固件对这些命令的支持；遇到不支持命令会报错，不编造或补零数据。

## 验证

2026-10-14：模拟仪器响应检查通过，覆盖窗口 Trace 12 映射测量 6、带源端口逗号的接收机比值文件名、Hz / RI 数值保留及重复文件保护；命令行 `--help` 可运行。未连接实际 PNA，尚未完成 Windows / PNA 现场验证。
