# v1.6.3

- 主界面曲线右键增加幅度、相位、解缠绕相位等显示选项，与左侧选择同步；迁移旧“展开相位”显示设置。
- Y 轴支持单个 / 全部 S 参数 AutoScale 和手动最小 / 最大值；拒绝非有限值及倒置范围。
- 手动范围按参数和显示模式分别保存于当前会话，重绘后保留；切换到其他模式自动使用其独立范围。
- 复用现有分段 / 零幅度相位处理，校准算法与导出格式不变。

# v1.6.2

- VMC 校准窗口改为左右可调布局：左侧配置与操作，右侧加载文件；两侧独立滚动。
- 标准件定义按 OPEN / SHORT / LOAD / THRU 分组；原始测量按 OPEN / SHORT / LOAD / THRU / CalTHRU 分组；已表征校准混频器独立分组。
- 左侧新增自动计算的 IF 起止频率只读显示；保留高级输入、校准包设置、后台计算与分级失效。
- THRU 定义关闭时浏览按钮与路径输入一起禁用。Qt 联动检查覆盖新分组、左右布局和较小窗口；截图默认写临时目录，可用 VMC_GUI_SCREENSHOT_DIR 指定。
- 校准算法与数据格式不变。

# v1.6.1

- 产品名称统一为 VMC Calibration Workbench / VMC 校准与验证工作台；更新窗口标题、README、开发约定和使用说明标题。
- Python 项目名改为 vmc-calibration-workbench；GitHub 仓库地址与运行入口保持不变。
- 保留既有 QSettings 命名空间，现有目录与窗口状态无需重新配置。算法与数据格式不变。

# v1.6.0

- 新增 vmc_calibration.py：四组 SOL、RF / IF 普通 Thru 的负载匹配 / 传输跟踪、校准混频器 ETF，以及单向 MUT 的 S11 / S22 / VC21 校准。
- 新增两个页签的 VMC 全量校准窗口；命名为“校准 MUT”，不新增对比页面；结果与原始响应接入既有主界面。本次不修改主界面相位比较行为。
- 支持共用 / 独立 SOL 文件及标准定义、Flush / defined Thru、上下变频、显式 RF / IF / 双频段复制横轴；原始测量禁止插值。
- 校准包原子写入，含配置、映射、输入哈希、NPZ 数组校验和复数 CSV；可离线重载。MUT 结果包含 RF / IF / LO 映射及未校准 S12 标识。
- 新增独立内部波量回归和 Qt 后台计算 / 保存 / 重载 / 失效 / 主界面联动检查。Windows / Keysight 全量校准对照尚待用户验证。

# v1.5.2

- 三次样条改为线性幅度与解缠绕相位分别插值，再用 mag*exp(j*phase) 重构；保留 not-a-knot、精确节点优先及禁止外推。
- 历史 cubic_ri 键保留，但实际坐标改为 cubic_magnitude_unwrapped_phase；界面、JSON、S2P 注释及开发约定同步，版本记录区分旧 RI 样条结果。
- 两种插值统一拒绝需要求值的非恒零 / 含零幅度标准；恒零 LOAD 保持零，全部精确节点保持原值。样条负幅度明确报错，不钳位或取绝对值。
- 新增幅相多项式解析恢复、双向多圈相位解缠绕、两节点样条和负幅度拒绝测试。47 项数值回归通过。
- 既有 Keysight 下变频 201 点的新幅相样条对照最大复数差约 1.8688e−7；并未据此确认 Keysight 内部插值规则。

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
