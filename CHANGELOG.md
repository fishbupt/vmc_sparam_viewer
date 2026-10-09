# v1.5.1

- 线性标准插值改为线性幅度 + 解缠绕相位分别插值，复数结果为 mag*exp(j*phase)，相位解缠绕采用 np.unwrap，单位弧度；不是 dB 插值。
- 历史 API / QSettings 键 linear_ri 保持兼容，但其数值行为改为幅相线性；GUI 文案与提示同步。三次样条实虚部插值不变，仍只有两种选项。
- 精确节点原值优先、恒零 LOAD、禁止外推不变；非恒零标准含零幅度且需要线性插值时拒绝，避免虚构相位。
- 生成报告 / 表征报告 / S2P 注释记录实际 interpolation_coordinates，区分历史 RI 线性结果。
- 更新 README 和 AGENTS，新增 v1.5.1 验证记录；44 项数值回归及 Qt offscreen 检查通过。

# v1.5.0

- 新增上下变频选择：down → IF=RF−LO；up → IF=RF+LO，默认 down。两者非反转；不将 LO−RF 分支自动取绝对值。
- frequency_mapping.py 统一生成 / 表征的频率验证和映射。API 的 SimulationOptions / Options 新增 frequency_conversion；保留原参数顺序。
- 生成窗口、表征窗口、自动载入、QSettings、结果失效及演示恢复方向同步；注释 / JSON / 真值 CSV / S2PX 的 OutputFreq 使用实际映射。
- 标准插值只保留 linear_ri 和 cubic_ri，实部 / 虚部分别求值；保留精确节点优先、not-a-knot、恒零 Load 及禁止外推。
- 删除幅相 / dB / exact API 选项，非法调用报错。旧 GUI 的已删除插值设置回退为 cubic_ri。
- 新增 AGENTS.md、.gitignore 及 docs/validation_v1.5.0.md；首次发布完整工程至 GitHub。
- 41 项数值回归及 Qt offscreen 联动检查通过。Keysight 对照仍为既有下变频样本；上变频 Keysight / Windows / 仪器现场未验证。

# v1.4.0

- 新增“生成 SOL 仿真文件 / Mixer 真值”，按真实校准套定义生成六个原始 S11 测量 S2P 和无噪声 Mixer.s2p。
- 可配置 RF 扫频、LO、标准求值方式、混频器 S11/S22/S21=S12 幅相时延、EDF/ESF/ERF 幅相时延。
- 可选独立复高斯基线噪声、种子和等效平均次数。
- 新增真值/测量预览和自动载入表征输入；整体开方符号取已知模拟真值首点分支。
- 独立输出目录、标准副本、全参数与文件哈希报告、逐点 Gamma/真值/净响应/实际噪声 CSV。
- 35 项数值回归通过，独立波量正向方程及非理想标准无噪声闭环验证；Qt offscreen 联动通过。

# v1.3.0

- GUI 标准件输入改为 OPEN/SHORT/LOAD 三个共用 S1P；六个测量输入保留。
- 新增六种标准件求值选项，GUI 默认三次 RI，保存实际计算使用的模式。
- 三次样条 not-a-knot、精确节点优先、禁止外推，零 Load 和含零幅度的极坐标异常显式处理。
- 数值 API 支持三标准路径，兼容旧六路径接口；API 默认 RI 线性不变。
- 导出记录求值方法、共享标准件和边界设置；新增 SciPy 依赖。
- 29 项数值回归通过；Qt offscreen 验证全部模式、三标准输入、后台计算、主界面载入、S2P/诊断包导出、设置迁移及保存。
- 当前 Keysight 201 点 cubic_ri 对比最大复数差约 1.87e-7；Keysight 内部插值算法未确认。

源码版，Python 3.10+；Windows/PNA 现场尚未验证。
