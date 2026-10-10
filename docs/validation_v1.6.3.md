# v1.6.3 主界面显示与 Y 轴检查

2026-10-10，Linux / Qt offscreen。

- `python -m unittest discover -s tests -v`：62 项数值回归通过。
- `python tests/gui_viewer_display_smoke.py`：主界面幅度 / 相位 / 解缠绕相位菜单切换与控件同步；相位跨 ±180°、连续分段、零幅度断点；单个 / 全部 Y 轴手动范围和 AutoScale；非法输入拒绝；模式独立范围；文件 / 分段切换后保留范围；旧显示设置迁移。全部通过。
- `python tests/gui_simulation_smoke.py` 与 `python tests/gui_vmc_calibration_smoke.py`：后台工作流及主界面联动通过。
- `git diff --check`：通过。

手动范围按显示模式和 S 参数保存在当前会话中。右键“显示”作用于全部四个子图；Y 轴可单独或统一设置。相位处理复用 parser.values，未修改校准算法和导出格式。本记录不代表 Windows 或 Keysight 现场验证。
