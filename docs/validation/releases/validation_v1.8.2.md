# v1.8.2 单文件查看 / 双文件比较验证

日期：2026-10-10。分支：Enhanced。Python 3.12 / Linux Qt offscreen。

## 实现范围

默认数据查看分为独立的单文件查看与双文件比较，共用导入文件库。单文件无勾选叠加；比较明确选择 A/B 和两侧物理频率轴、分段。叠加使用各自全部原始采样，差异使用唯一匹配，数值核心不插值。验证报告使用同一比较实例；保留旧同名比较窗口。

单文件和比较的显示、单位、频率轴、分段及 Y 范围彼此独立。改变比较输入或容差使旧统计与 CSV 导出失效。追加或删除无关文件保留已有结果。双文件页增加 CSV / 图片导出，较小窗口通过滚动访问配置和曲线。

## 自动验证

- `python -m unittest discover -s tests -q`：71 项通过。新增两侧不同轴和所选分段的唯一匹配、原始行号保留、实际频率轴 CSV 导出；既有默认 API、默认 CSV 字段兼容。
- `python tests/gui_analysis_smoke.py`：通过。默认单文件、A/B 独立选择、未匹配点仍参与叠加、两个频率轴、分段、交换差值符号、状态保留、导出失效、CSV 与 PNG 文件内容、删除输入、无 StimulusFreq 数据和最小窗口滚动。
- `python tests/gui_workbench_smoke.py`：通过。更新默认单文件及持久比较实例断言；保持类型选择、共享 VMC 状态、线程保护、排队导入、完整生成 / 求解 / MUT 联动。
- `python tests/gui_viewer_display_smoke.py`、`gui_simulation_smoke.py`、`gui_vmc_calibration_smoke.py`、`gui_vmc_simulation_smoke.py`：通过。
- 检查真实 GUI 截图：1420×900 的单文件 / 双文件页，以及 1000×700 的滚动比较页。

## 限制

当前仍是双端口 S2P / S2PX 解析，未增加任意端口 SNP 支持、自动通过 / 失败容差判定、项目文件或通用校准引擎。相位差为归一化差值，解缠绕仅用于原始曲线显示；不拟合时延或相位偏移。RF / IF 轴物理含义由用户确认。不同阻抗不自动重归一化。Qt offscreen 不代表 Windows / Keysight 现场验证。

GUI / 包版本更新至 1.8.2；校准、仿真正向模型及其算法报告版本保持 1.7.0。
