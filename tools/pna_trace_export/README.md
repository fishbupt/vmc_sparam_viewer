# PNA 窗口 Trace 导出工具 · v1.0.5

独立命令行脚本，可复制此目录到其他电脑运行，无需安装 VNA Calibration Workbench 或 GUI 依赖。Python 3.10+，需安装支持 HiSLIP 的 VISA 实现（例如 Keysight IO Libraries Suite）。

## 运行

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后，进入工具目录运行：

```powershell
cd tools/pna_trace_export
uv run --locked python export_window_traces.py --output D:/PNA_Traces
```

`uv run` 自动在工具目录创建 `.venv` 并安装锁定的依赖，无需手动激活环境。本工具有独立的 `pyproject.toml` / `uv.lock`，不安装工作台的 PyQt6 等依赖。复制到其他电脑时请保留整个工具目录。

也可在仓库根目录运行：

```powershell
uv run --directory tools/pna_trace_export --locked python export_window_traces.py --output D:/PNA_Traces
```

`--directory` 将工作目录切换到工具目录；省略 `--output` 时结果保存在该目录下的 `PNA_Traces`。

只准备环境、不连接仪器：

```powershell
uv sync --locked
uv run --locked python export_window_traces.py --help
```

PyCharm 可选择 `tools/pna_trace_export/.venv/Scripts/python.exe` 作为解释器并直接运行脚本。VISA 驱动仍需单独安装，uv 仅管理 Python 依赖。

| 选项 | 默认值 | 含义 |
| --- | --- | --- |
| `--resource` | `TCPIP::127.0.0.1::hislip0` | VISA 资源；PNA 软件需在本机运行并启用 HiSLIP |
| `--window` | `2` | 激活并导出的窗口编号 |
| `--output` | 当前工作目录下的 `PNA_Traces` | 保存到运行脚本的电脑 |
| `--timeout` | `30000` | VISA 超时，毫秒 |

每次创建 `Window2_日期_时间_微秒` 子目录，包含各 Trace 的 `.s1p` 和 `manifest.json`。退出码 0 为全部成功，1 表示有错误；错误及已成功文件会记录在 manifest 中。

## 命名与文件含义

- `Tr1_S11.s1p`、`Tr6_a2_over_b2,1.s1p`，不包含显示格式 LogM。
- 窗口内部 Trace ID 与屏幕 Tr 编号可能不同；脚本逐条选择目标窗口的 Trace、等待命令完成并确认活动窗口，再查询当前测量编号和测量所属通道。
- Windows 不允许文件名包含 `/`，替换为 `_over_`；原参数保留在文件注释和 manifest 中。仪器可能返回等价物理接收机名称，而非屏幕上的逻辑 a/b 名称。
- 每个文件仅有频率、实部、虚部，使用 `# Hz S RI R 50` 和 17 位有效数字，不丢失相位。
- **S21、接收机比值等借用 S1P 的 S11 列存储，并非真实单端口网络。** R 50 仅为文件约定，未进行重归一化，不能直接当作物理 S11 使用。
- 导出 SDATA，校准状态遵循仪器当前设置；不等同于显示变换、平滑、Data/Memory 运算后的屏幕曲线。不导出 Memory 曲线；启用 Equation 的 Trace 会报错跳过。
- 面向默认频率横轴（Hz）的 LIN / LOG / SEGM 扫描；要求频率严格递增。功率 / CW / 非默认横轴不属于支持范围。
- 脚本不触发新扫频、不冻结扫频，读取现有测量数据；如要求各 Trace 对应同一完整采集状态，请先在 PNA 完成扫频并 Hold。
- 激活窗口 2 并逐条选择 Trace，等待命令完成后回读活动窗口；不匹配时停止该 Trace 导出。数据使用选中 Trace 对应的显式测量编号读取。临时切换 ASCII 数据传输，正常结束时恢复原 FORM:DATA。查询超时后立即停止，不继续使用可能失步的会话，也不发送格式恢复命令。

## SCPI 流程

`DISP:WIND2:CAT?` → 对每个 Trace 执行 `DISP:WIND2:TRAC<t>:SEL` → 等待 `*OPC?` 并确认 `SYST:ACT:WIND?` → `SYST:ACT:MEAS:NUMB?` → `SYST:MEAS<m>:CHAN?` → `CALC<c>:MEAS<m>:PAR?` → `DATA:X?` / `DATA:SDATA?`。

通道编号必须大于 0；无效或缺失映射明确报错，不默认猜测 Channel 1。控制台打印实际窗口 Trace / 测量 / 通道映射，查询失败包含具体命令。依据 [Keysight System SCPI 文档](https://helpfiles.keysight.com/csg/NA520xA/Programming/GP-IB_Command_Finder/System.htm)。

窗口激活流程为 `SYST:ACT:WIND 2` → `DISP:WIND2:TRAC<t>:SEL` → `*OPC?` → `SYST:ACT:WIND?`。不再使用 `window_measurements()` 或 `SYST:MEAS<m>:WIND?` 的全局归属筛选。控制台打印活动窗口和选中 Trace 对应的测量 / 通道编号，排查时保留完整输出。

依赖 Keysight PNA 固件对这些命令的支持；遇到不支持命令会报错，不编造或补零数据。

## 验证

v1.0.5：移除全局测量归属筛选；模拟验证逐条选择并获取真实测量编号，拒绝测量 0 / 通道 0，且不发送全局目录及所属窗口查询。未完成真实 PNA 验证。

v1.0.4：新增窗口 / Trace 激活、完成等待和回读检查；模拟验证成功及回读不匹配时停止。未完成真实仪器验证。

v1.0.3：回归覆盖多通道与其他窗口的 Trace 映射、拒绝通道 0、单曲线实虚部及文件名、查询失败报告具体命令。尚待实际 PNA 验证。

v1.0.2：修复 PyVISA ResourceManager 不支持上下文管理器的问题；使用 `contextlib.closing`，先关闭仪器连接，再关闭资源管理器。回归覆盖正常导出、查询失败和连接失败的资源释放。可运行 `uv run --locked python -m unittest discover -s tests -v`。

2026-10-14：模拟仪器响应检查通过，覆盖窗口 Trace 12 映射测量 6、带源端口逗号的接收机比值文件名、Hz / RI 数值保留及重复文件保护；命令行 `--help` 可运行。未连接实际 PNA，尚未完成 Windows / PNA 现场验证。

v1.0.1：检查独立 uv 锁定环境同步、PyVISA 导入，以及工具目录与仓库根目录两种 `--help` 入口；不改变采集和导出逻辑。
