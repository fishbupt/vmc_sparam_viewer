# v1.10.0 高边 LO 验证（2026-10-22）

基线 Enhanced ea8f2bd；工作台版本 1.10.0，算法 / 报告版本 1.8.0。

## 数值验证

`uv run python -m unittest discover -s tests -v`：80 项通过。

新增 `tests/vmc/test_high_side.py` 的 6 项覆盖：

- 三种变频关系与 LO≤RF 非法输入。
- RF 10～15 GHz / LO 20 GHz 的非理想 SOL；独立物理反射公式对照实线性波量生成器；不共轭标准的负例出现明显相位错误。
- 原始 / 第一轮已校准第二轮路径、幅相线性 / 三次样条插值、递减 IF 和导出标注；最大允许复数差 5e-14。
- CalTHRU 和 MUT 的物理 SM21 与独立解析表达式对照，最大允许差 8e-16。
- RF / IF / dual 三种文件轴、非理想 SOL、独立端口误差盒、IF 轴导入的校准混频器、校准包保存 / 重载、MUT 恢复；最大允许差 4e-14。
- RF/IF 端点接触的 dual 拒绝、无重叠 dual 的噪声样本一致性、随机种子复现。

原有非反转 up/down、Keysight 历史样本、插值、解析与结构回归一并通过。高边生成器未调用反演函数。数值模型中的 LO 相位规范为 0，验证的是明确约定下的有效传输，不是绝对 LO 相位。

## GUI 验证

Qt offscreen：以下 7 项脚本通过：

- gui_simulation_smoke.py
- gui_vmc_calibration_smoke.py
- gui_viewer_display_smoke.py
- gui_vmc_simulation_smoke.py
- gui_workbench_smoke.py
- gui_analysis_smoke.py
- gui_high_side_smoke.py

高边脚本覆盖两个预设按钮、后台文件生成、表征窗口联动、VMC 校准与 MUT 联动、设置恢复及切换模式后结果失效。

## 外部验证边界

未连接用户 PNA / Windows 环境，未声明 Keysight 高边 LO 表征或 VC21 对比通过。请按高边 LO 使用说明加载相同标准，并核对物理与输入参考相位规范。仍无独立开关项 / 隔离采集；MUT 使用单向模型。
