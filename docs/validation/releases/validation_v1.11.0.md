# v1.11.0 共享 VMC 配置验证（2026-10-23）

基线 Enhanced 16e112a。工作台 1.11.0，算法 / 报告仍为 1.8.0。

## 数值

`uv run python -m unittest discover -s tests -q`：82 项通过。

新增两项独立标准回归：75 Ω、两套不同的非理想 SOL、up/down/high_side 三种关系；六定义生成→表征恢复→已表征混频器导入→VMC 原始测量生成→校准→MUT 恢复。复数差限值 3e-14，检查 P1/P2 原始反射确有区别、映射未合并。

频段错误负例覆盖高边 LO 的 RF 文件误选 IF（10～15 GHz 文件被要求覆盖 5～10 GHz），以及全局 RF 扩大到 16 GHz；报错包含横轴和两种频段，禁止外推。

## GUI

原有 7 项 GUI 脚本和新增 gui_vmc_shared_workflow_smoke.py 通过（Qt offscreen）。导航断言按五步流程更新。

新增脚本完成 75 Ω、高边 LO、独立端口 2 标准的真实后台五步闭环，检查全局参数、六定义交接、表征 RF 横轴自动传入、校准后真值、换页不失效、全局修改级联失效及设置重启恢复。实际控件截图检查全局配置、独立标准、表征和生成页面；使用 Noto Sans CJK 字体验证中文。

未连接 Keysight 仿真或真实仪器，未声明 Keysight 高边相位约定或 Windows 高 DPI 验证通过。
