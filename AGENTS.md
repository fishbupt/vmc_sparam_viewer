# VMC S-Parameter Viewer 开发约定

本工程用于校准混频器算法的正式验证：查看 S2P / Keysight S2PX、生成可追溯的 SOL 仿真输入、从两轮 SOL 提取表征、与真值及 Keysight 输出比较。正确性优先于界面装饰。先读 README.md、CHANGELOG.md 和相关测试，再修改。

## 环境与入口

- Python 3.10+；依赖见 pyproject.toml / requirements.txt：NumPy、SciPy、PyQt6、Matplotlib。
- 在仓库根目录运行 `uv run python main.py`，或用虚拟环境安装 requirements.txt 后直接运行 main.py。
- 支持 Windows / PyCharm 直接运行 main.py；保持当前根目录模块导入方式，不引入必须用 `python -m` 才能启动的相对导入。
- 不提交 .venv、__pycache__、IDE 配置、个人标准套、真实采集记录和本次生成的结果目录。

## 模块边界

| 文件 | 职责 |
| --- | --- |
| frequency_mapping.py | 生成、表征共用的 RF / LO / IF 映射及验证 |
| characterization.py | 标准解析 / 求值、SOL 求解、输入误差消除、连续开方、结果与诊断导出 |
| simulation.py | 独立正向模型、可复现噪声、真值及六个测量文件生成 |
| parser.py | Dataset、Touchstone / S2PX 解析、数据变换 |
| comparison.py | 唯一频率匹配、复数 / 幅度 / 相位差、统计与导出 |
| main.py | 主窗口、查看与绘图、功能入口 |
| characterize_gui.py / simulate_gui.py / compare_gui.py | 参数收集、QThread 调用、结果展示与交互 |
| tests/ | 数值、文件回归；独立的 Qt offscreen 联动检查 |
| examples/ | 已注明来源及限制的演示 / Keysight 回归输入 |

GUI 不得复制另一套算法公式。耗时计算和文件 I/O 继续放到后台线程。控件修改后使当前结果及导出失效；已载入主窗口的数据是独立快照。QSettings 记录最近参数和目录，非法旧插值设置回退为 cubic_ri，不能恢复已删除的选项。

## 必须保留的数学约定

1. 六个采集输入按 `[input_open,input_short,input_load,output_open,output_short,output_load]` 排列，均读取 S11，横轴均为 RF。生成文件的 S21 / S12 / S22 是零占位，不代表完整标准网络。
2. GUI 输入共用 `[OPEN,SHORT,LOAD]` 三个 S1P。第一轮标准在 RF 求值，第二轮在映射 IF 求值。数值 API 兼容旧六标准路径，但不得默认使用两套不同标准。
3. `frequency_conversion='down'`：IF=RF−LO，所有 RF 必须大于正 LO。`'up'`：IF=RF+LO，允许 LO 高于 RF。两者是非反转分支，固定 LO 下 dIF/dRF=+1。不用 abs(RF−LO) 代替，也不把 LO−RF 反转分支当作已支持功能。
4. 仅保留 `linear_ri` / `cubic_ri`：v1.5.1 起 `linear_ri` 是历史兼容键，实际对线性幅度 `abs(Gamma)` 和 `unwrap(angle(Gamma))` 分别线性插值，再重构复数；不要退回实虚部线性，也不要改成 dB 插值。`cubic_ri` 仍为实部和虚部分别三次样条插值。精确节点优先；默认容差 0.001 Hz；禁止外推；拒绝容差内多节点、重复节点。三次样条边界为 not-a-knot；不要改成 natural 或偷偷裁剪标准频带。恒零 LOAD 保持零；非恒零标准含零幅度且需要线性插值时拒绝，不给零幅度虚构相位；全部命中精确节点则保留原值。
5. 测量数据不插值、不自动重排 / 丢点；六个网格必须一致且严格递增。标准和测量参考阻抗须一致，不自动重归一化。病态标准、分母近零、非有限值明确报错。
6. 一端口模型 `m=D+R*Gamma/(1-E*Gamma)`，D=EDF、R=ERF、E=ESF。线性解 `m=A+B*Gamma+E*m*Gamma`，恢复 `D=A, R=B+A*E`。ERF 不是单程 S21。
7. 原始第二轮：`Q=R1+E1*(D2-D1)`；`C11=(D2-D1)/Q`，`P=C12*C21=R1*R2/Q**2`，`C22=E2-E1*R2/Q`。实际核心使用等价 Mobius 矩阵消除，并以先修正第二轮反射 / 再 SOL 的路径交叉核验。
8. 第二轮若已做第一轮修正，直接取其 D/E/R 为 C11/C22/P，禁止再次消除误差盒。
9. 反射 SOL 只确定 P，不分别识别 C12、C21。采用互易假设：`C12=C21=sign*sqrt(abs(P))*exp(0.5j*unwrap(angle(P)))`；整体 ± 符号依赖独立参考。不得逐点主值开方、拟合相位使结果强行吻合。稀疏采样的相位混叠不是整体符号可修正的问题。
10. 生成器只用正向模型，不调用 characterize 反推出测量。Mixer.s2p 是无噪声有效变频系数真值，普通 S2P 不执行频率转换。

## 噪声、导出及可追溯性

- 噪声在最终输入误差映射后加入，各频点 / 各状态独立圆对称复高斯；`sigma=10**(L/20)/sqrt(N)`，I/Q 标准差 sigma/sqrt(2)。L 是相对于无量纲 S=1 的复数 RMS dB，不是 dBm / dBm/Hz / IFBW 模型。
- 用明确种子的 NumPy PCG64；报告保留种子、NumPy 版本、平均次数和有效 RMS。Mixer 真值始终无噪声。
- 七个 S2P 文件名保持 README 约定；每轮新建独立目录；失败清理暂存目录，不覆盖之前的运行。
- S2P 用 Hz / S / RI、17 位有效数字、顺序 S11/S21/S12/S22。保留 RF 横轴，并在注释和 JSON 记录实际上下变频关系。CSV / Dataset / S2PX 的 OutputFreq 必须使用同一映射。
- 仿真报告和诊断记录实际输入路径 / SHA256、标准求值规则及实际 interpolation_coordinates、变频方向、第二轮修正层级、符号与警告。自研 S2PX 不能标为 Keysight 生成文件。
- 比较仅采用容差内一对一唯一匹配；不插值或自动拟合幅度 / 相位 / 时延。区分未匹配点和参与统计的点。

## 验证要求

在根目录运行：

```text
uv run python -m unittest discover -s tests -v
uv run python tests/gui_simulation_smoke.py
```

算法 / 映射修改需覆盖上下变频、两种插值、幅相线性跨 ±180° / 多圈解缠绕、线性幅度而非 dB、零幅度相位拒绝、精确节点原值保留、非理想标准、无噪声闭环、原始 / 已修正第二轮、输出轴 / 注释 / JSON 一致性、外推拒绝及独立正向波量方程。不要仅以生成器和提取器相互吻合作为正确性依据。

GUI 检查控件只有两种插值、方向改变后的结果失效、生成到表征方向联动、设置保存 / 迁移和演示恢复下变频。Qt offscreen 检查不能宣称 Windows / PNA 现场验证已完成。

当前 Keysight 回归样本是下变频，201 点 cubic_ri 最大复数差约 1.87e−7；这不是仪器精度规格或上变频 Keysight 实测验证。SHORT 文件仅为 5～20 GHz 摘录，正式验证需完整原始标准文件。改动后更新版本、README、CHANGELOG 与验证记录，区分已验证事实、模型假设及待验证限制。
