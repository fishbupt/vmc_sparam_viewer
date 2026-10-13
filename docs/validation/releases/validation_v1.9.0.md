# v1.9.0 结构重构验证

日期：2026-10-13。Enhanced 分支，Linux / Python 3.12 / PyQt6 6.11 离屏环境。

## 范围

代码迁入 vna_workbench 包，拆分数据、共用数值、VMC、独立仿真、分析与 GUI。根 main.py 保留直接运行。VMC 算法说明拆为公式 / 函数页；使用、历史验证、计划迁入分类目录。旧平铺 import 路径不再保留，外部脚本按架构迁移表更新。

本次不实现 TRL，不改变既有数值模型、文件格式、默认配置、QSettings 或算法报告版本 1.7.0。

## 结果

- 迁移前 71 项原有数值 / 文件测试通过。
- 迁移后 74 项测试通过：保留原有 71 项；新增三项检查 headless 数值层无 GUI 依赖、无旧平铺 import、仿真正向函数不调用校准求解器。
- 六组原有 Qt 离屏检查通过：生成两轮表征输入、VMC 校准、主查看幅相 / Y 轴、VMC 生成、持久工作流和独立单文件 / A-B 分析。
- 新增入口检查通过：从其他工作目录执行 root main.py 和安装后的命令脚本，加载 S2P、进入默认单文件页并正常关闭。
- `pip install --no-deps -e .` 成功；项目版本 1.9.0，提供 vna-calibration-workbench 命令入口。
- 对迁移前后 28 个数值 / 文件函数做 AST 核对，仅归一化包 import 和共用辅助函数名称后，函数体与签名相同，覆盖 SOL、标准求值、表征、误差项、MUT、仿真、解析、比较与校准包。
- Python 包编译、文档链接、算法页代码片段语法及 Git 空白检查通过。

历史 validation 文件保留当时的版本、结果及旧模块名称；移动目录后仅调整必要的 Markdown 链接，不据此宣称重新完成历史现场验证。

## 运行

```text
python -m unittest discover -s tests -v
python tests/gui/gui_simulation_smoke.py
python tests/gui/gui_vmc_calibration_smoke.py
python tests/gui/gui_viewer_display_smoke.py
python tests/gui/gui_vmc_simulation_smoke.py
python tests/gui/gui_workbench_smoke.py
python tests/gui/gui_analysis_smoke.py
python tests/gui/gui_entry_smoke.py
```

入口检查需先安装本项目。现有部分数值测试继续使用之前的个人 examples 基准，这些文件仍被忽略；未新增或上传真实采集文件。部分独立合成测试不依赖它们，不能把本次完整本地通过表述为全新克隆无需测试样本即可通过。

本次未新增数学测试门限、未执行 Windows / 高 DPI 或 Keysight 实机测量；已有 Keysight VC21 差异和双向 MUT 模型限制保持原状。
