# 模块结构与迁移映射

## 入口与边界

直接运行 `python main.py`，包括 Windows / PyCharm；根入口仅调用 `vna_workbench.app.application.main()`。内部采用包绝对导入。安装项目后可使用 `vna-calibration-workbench` 命令，文件参数仍传入默认数据查看页。

| 包 | 职责 |
| --- | --- |
| `app` | 启动、校准类型注册、仿真结果到校准配置的显式映射 |
| `data` | Dataset / Standard、Touchstone / S2PX / S1P、公共 S2P 写出、归档和结果包 |
| `core` | 标准求值、SOL / 反射补偿、频率转换及数值防护 |
| `calibration.vmc` | 表征、误差项、DUT 修正、输入验证及领域校准包 |
| `calibration.trl` | 仅预留包；菜单仍为待实现 |
| `simulation` | 两轮表征及 VMC 的独立正向生成 |
| `analysis` | 幅相与分段变换、唯一匹配、统计及查看数据 CSV |
| `gui` | 主窗口、工作区、页面、工作流、主题、表格模型和 worker |

GUI 调用数值 / 数据层。core、data、analysis 和 calibration 不依赖 Qt 或 GUI。文件解析不依赖专用校准器；共用 SOL 和标准求值不再从混频器表征模块借用。

仿真正向函数不调用求解器。`SavedVMCSimulation.calibration_inputs()` / `calibration_options()` 保留已有签名，只将生成完成后的显式一键载入委托给 `app/workflows.py`；该适配层组装路径和配置，不计算 raw 或误差项。

## 旧文件映射

| 原文件 | 当前位置 |
| --- | --- |
| `main.py` | 根入口；主窗口在 `gui/main_window.py`，启动在 `app/application.py` |
| `parser.py` | `data/models.py`、`data/touchstone.py`、`analysis/transforms.py`、`analysis/csv_exports.py` |
| `characterization.py` | `calibration/vmc/mixer_characterization.py`、`characterization_io.py`；共用部分见 core 和 data |
| 共用 SOL / Mobius / 反射修正 | `core/sol.py` |
| 标准 S1P 解析 / 模型 | `data/standard_definitions.py`、`data/models.py` |
| 标准求值 | `core/standard_sampling.py` |
| `frequency_mapping.py` | `core/frequency_conversion.py` |
| `vmc_calibration.py` | `calibration/vmc/models.py`、`input_reader.py`、`error_terms.py`、`dut_correction.py`、`package_io.py` |
| VMC 结果包 / 归档函数 | `data/result_exports.py`、`data/archives.py` |
| `simulation.py` | `simulation/mixer_characterization.py` |
| `vmc_simulation.py` | `simulation/vmc.py`，显式载入映射在 `app/workflows.py` |
| 仿真器私有 `_s2p()` | 共用 `data/touchstone.py::s2p_text()` |
| `comparison.py` | `analysis/comparison.py` |
| `viewer_gui.py` 与主窗口的查看 / 绘图方法 | `gui/pages/sparameter_viewer.py` |
| `comparison_page.py` | `gui/pages/sparameter_comparison.py` |
| `compare_gui.py` | `gui/dialogs/same_name_comparison.py`；worker、标签移到共用 GUI 模块 |
| `workbench_gui.py` | `gui/workspace.py`；类型注册移到 `app/calibration_registry.py` |
| `characterize_gui.py` | `gui/workflows/vmc/mixer_characterization.py` |
| `simulate_gui.py` | `gui/workflows/vmc/characterization_simulation.py` |
| `vmc_calibration_gui.py` | `gui/workflows/vmc/calibration.py` |
| `vmc_simulation_gui.py` | `gui/workflows/vmc/simulation.py` |
| 分散的 Task / Worker / Work | `gui/workers.py`，保留不同构造参数和错误信号约定 |
| 表格模型、粘贴与 Y 范围弹窗 | `gui/models.py`、`gui/dialogs/data_view.py` |

表内未标前缀的当前路径均位于 `vna_workbench/`。旧根目录模块被迁移，不保留平铺兼容副本；外部脚本需按此表更新 import，函数签名和数据语义保持。

```python
from vna_workbench.calibration.vmc.mixer_characterization import characterize
from vna_workbench.calibration.vmc.models import Options, CalibrationOptions
from vna_workbench.calibration.vmc.error_terms import calibrate
from vna_workbench.calibration.vmc.dut_correction import calibrate_mut
from vna_workbench.calibration.vmc.package_io import save_calibration, load_calibration
from vna_workbench.data.result_exports import export_mut
```

## 测试与文档

- `tests/core/`：解析、比较、共用标准求值和结构边界。
- `tests/vmc/`：两轮表征、频率转换联动、VMC 校准与正向生成。
- `tests/gui/`：既有六组离屏联动；新增启动入口检查。
- 全部数值检查：`python -m unittest discover -s tests -v`。
- 单个 GUI 脚本：`python tests/gui/gui_workbench_smoke.py`。

算法文档在 `docs/algorithms/common/` 和 `docs/algorithms/vmc/`，仅保留公式、必要假设和对应函数。操作放 `guides/`，测试条件与结果放 `validation/releases/`，计划放 `plans/`。历史验证结果不因移动目录而被改写为本次验证。

结构版本为 1.9.0；算法报告版本仍为 1.7.0。数学公式、文件名 / schema / 参数顺序、默认配置与旧 QSettings 命名空间保持；不把包目录创建视为新增 TRL 或通用 N 端口能力。
