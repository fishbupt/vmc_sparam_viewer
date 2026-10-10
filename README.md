# VNA Calibration Workbench · VNA 校准与验证工作台 · v1.8.1

启动默认进入 **S 参数查看与比较**，支持独立打开 S2P / Keysight Converter Sweep Data S2PX，勾选多文件叠加，以及匹配频点后的差异统计。还提供 VMC 研发流程：生成仿真数据、表征校准混频器、计算误差项和校准 MUT。Python 3.10+，PyQt6、NumPy、SciPy、Matplotlib；无需连接仪器。通用 SOLT / TRL / 多端口等算法仍属于升级规划，当前文件查看器仍面向双端口数据。

## 名称与使用说明

- 软件名称：**VNA Calibration Workbench**。
- 中文名称：**VNA 校准与验证工作台**。
- Python 项目名称：`vna-calibration-workbench`。
- [《VNA 校准与验证工作台 · VMC 使用说明》](docs/vmc_calibration.md)。
- [通用 VNA 校准验证功能升级清单](ToDo.md)。

GitHub 仓库地址保持 `fishbupt/vmc_sparam_viewer`，现有运行命令不变。界面设置继续使用原有配置存储，保留最近目录和窗口状态。

## v1.8.1：校准类型选择

顶栏 **校准类型** 下拉框与菜单栏 **校准类型** 菜单同步：VMC 继续使用已有流程；SMC、响应 / 增强响应、SOL、SOLT、QSOLT、SOLR、TRL、TRM、LRM / LRL、多线 TRL、功率、多端口、ECal 工作流和噪声类型均可选择，校准页面暂为空白占位，标记“待实现”。这些选项不表示新增算法已实现。

切换类型保留已配置的 VMC 输入与校准包；返回 VMC 后可以继续使用。所选类型通过 QSettings 保存，启动仍默认进入独立的查看与比较页；后台任务运行期间不能切换类型。工具菜单中的显式 VMC 生成入口会同步切回 VMC。数据查看与差异统计不受类型选择影响。

## v1.8.0：默认数据查看页与工作流程导航

左侧固定导航：**查看与比较 / 项目配置 / 标准件定义 / 原始测量 / 校准求解 / 校准 MUT / 验证报告**。启动无需创建项目；数据侧栏集中显示文件列表、显示勾选、频率轴与分段选择，右侧提供 2×2 曲线、数据表、元数据和原始文本。曲线按 S11 / S21（VC21）在上、S12 / S22 在下排列。

- 默认叠加所有勾选文件，可改为仅查看选中文件。每个数据集固定颜色与线型；取消勾选只隐藏曲线，不删除数据。选中文件仍负责表格、详情与 CSV 导出。
- 选中某个文件后为它设置横轴和分段；切换文件后保留本次会话的选择。**各文件横轴的 RF / IF 物理含义须由用户确认**，叠加不进行频点匹配、插值或时延拟合。点序号与频率轴不混画。
- 曲线工具栏集中放置幅度 / 相位 / 解缠绕相位以及 Y 轴 AutoScale / 手动设置；保留单图右键和各显示模式独立的 Y 轴范围。
- 校准流程页面共享同一个 VMC 配置、标准件输入和校准包，导航切换不重置状态。`项目配置` 是当前 VMC 的共用参数页，尚未实现独立通用项目文件保存。
- **原始测量 → 生成 VMC 原始测量 SNP** 在主工作区内生成；生成后的“一键载入”送到同一个校准求解页。两轮 SOL 生成与表征继续通过本页 / 工具菜单的独立窗口使用。
- **验证报告** 复用原有任意文件差异计算与 CSV 导出，不额外新增算法或自动容差结论。A 需有 StimulusFreq，B 显式选择实际频率轴；仅比较唯一匹配频点。校准结果和真值如需作为 A，可先导出 / 打开 S2P。
- 底部日志默认折叠，汇总主窗口与嵌入式 VMC 流程记录；后台线程运行时禁止关闭主窗口，状态栏显示进度。

界面框架与现有 VMC 能力先行迁移，通用校准算法按 [ToDo.md](ToDo.md) 后续扩展。校准 / 仿真数值模型与原有 v1.7.0 数据格式保持一致；算法报告内版本仍标识 v1.7.0。验证见 [docs/validation_v1.8.0.md](docs/validation_v1.8.0.md)。

## v1.7.0：生成 VMC 原始测量 SNP

主界面 **生成 VMC 原始测量 SNP** 打开独立的正向仿真窗口。默认复现此前 RF 10～20 GHz、LO 20 GHz、IF 30～40 GHz 的 Dummy DUT baseline，生成六个原始 S2P：

| 文件 | 用途 |
| --- | --- |
| `open_raw.s2p` / `short_raw.s2p` / `load_raw.s2p` | 两端口 SOL；S11 为 Port1、S22 为 Port2，交叉传输为零 |
| `thru_raw.s2p` | 两个实际频段的普通 Thru 原始测量 |
| `cal_mixer_raw.s2p` | 接入校准混频器后的 CalTHRU 原始测量 |
| `mut_raw.s2p` | 接入 MUT 后的原始测量 |

附带 `standard_open/short/load.s1p`、`thru_definition.s2p`、`calibration_mixer.s2p`、`mut_truth.s2p` / CSV、21 项 `expected_error_terms.csv`、频率映射、无 pickle 的 clean/raw NPZ、参数与源文件/输出哈希报告。**普通 Thru 默认是零反射、0 dB、零延迟 Flush；raw 文件包含端口误差，不是标准真值。**

支持上下变频、RF / IF / 非重叠双频段复制横轴、混频器幅相时延、相同或独立端口误差盒、可复现复高斯噪声，以及导入实际 SOL / THRU / 已表征校准混频器定义。MUT 固定 S12=0 的单向真值。所有表征输出归一为 RF 横轴；默认同一物理频率的两端口 SOL S11=S22，独立误差盒或独立噪声下不要求相等。

每次创建独立输出目录，不覆盖旧结果。**将本轮文件载入 VMC 校准窗口** 自动填入配套定义、原始测量、RF/LO/IF 与文件横轴；计算误差项后即可校准 MUT。右侧预览和主界面同时提供 MUT 真值与原始测量的 VC21/SM21。Keysight 与自研校准都必须使用与生成器一致的标准定义，不能直接套用机械校准套默认偏移。普通 S2P 不自行执行变频；Keysight 的 Dummy DUT 接收器读取行为仍需现场确认。

验证见 [docs/validation_v1.7.0.md](docs/validation_v1.7.0.md)。

## v1.6.3：主界面显示与 Y 轴范围

在任意 S 参数子图内右键，通过“显示”菜单统一切换幅度（dB / 线性）、相位、解缠绕相位、实部或虚部；与左侧“显示”选择同步。解缠绕按原始连续分段计算，零幅度处相位未定义，不跨这些位置展开。

右键可对当前子图选择 **Y 轴 AutoScale** 或输入手动最小 / 最大值；左侧 **Y 轴设置…** 可选择单个或全部 S 参数。手动范围必须是有限数值且最小值小于最大值；范围按显示模式分别保留，在本次会话内切换文件和分段后继续生效。AutoScale 恢复当前数据 / 分段的自动范围。验证见 [docs/validation_v1.6.3.md](docs/validation_v1.6.3.md)。

## v1.6.2：VMC 校准窗口左右布局

左侧集中放置 RF、固定 LO、变频方向、自动计算的 IF 起止频率、标准插值、文件横轴和校准操作。右侧按用途分为三个文件组：

- **标准件定义**：OPEN / SHORT / LOAD / THRU。
- **原始测量**：OPEN / SHORT / LOAD / THRU / CalTHRU；CalTHRU 为接入校准混频器的变频 Thru 原始数据。
- **已表征的校准混频器**：独立的表征 S2P 输入。

左右宽度可拖动调整，两侧独立滚动。共用 / 独立标准件、12 组独立 SOL、Flush / defined Thru 及校准包设置均保留。算法与校准数据格式不变。

## v1.6.0：计算 VMC 校准误差项 / 校准 MUT

主界面新增 **VMC 校准误差项 / 校准 MUT** 入口，包含两个页签：

- **计算 VMC 校准误差项**：四组端口 / 频段 SOL，普通 RF / IF Thru，校准混频器 RF→IF Thru，共 21 个误差项；误差项可载入主界面，复用已有幅度 / 相位视图。
- **校准 MUT**：计算 S11、S22、VC21，将原始 MUT 与校准结果同时载入主界面；无新增对比页面。本次不修改主界面相位比较功能。

支持共用三个 SOL S2P 或 12 组独立 S1P / S2P，两端口共用或独立标准定义，理想 Flush 或已定义 Thru。标准插值维持幅相线性 / 幅相三次样条；原始测量只精确匹配，不插值。

校准包包含 JSON 配置 / 输入映射 / SHA256 和复数误差项，可保存后独立重载，无需原始标准文件；MUT 结果包含 S2P、VC21 复数 CSV、原始数据、RF / IF / LO 映射和报告。**MUT 按单向 / 忽略反向耦合公式校准；S12 未校准，S2P 中的零值仅为明确标记的占位。** 本轮假设传输泄漏为零，未独立采集接收器 / 开关项。

详细操作、公式和输入要求见 [docs/vmc_calibration.md](docs/vmc_calibration.md)，验证记录见 [docs/validation_v1.6.0.md](docs/validation_v1.6.0.md)。

## v1.5.2 更新：两种插值均采用幅度 / 解缠绕相位

线性及三次样条均对**线性幅度（不是 dB）**和**解缠绕后的相位（弧度）**分别插值，然后重构复数。样条核心：

```python
magnitude = np.abs(std.gamma)
phase = np.unwrap(np.angle(std.gamma))
mag_interp = CubicSpline(std.frequency, magnitude,
    bc_type='not-a-knot', extrapolate=False)(x)
phase_interp = CubicSpline(std.frequency, phase,
    bc_type='not-a-knot', extrapolate=False)(x)
gamma_interp = mag_interp * np.exp(1j * phase_interp)
```

为兼容已有调用和 QSettings，保留历史 API 键 `linear_ri` / `cubic_ri`，**它们现在分别代表幅相线性 / 幅相三次样条，不再代表实虚部插值**。线性从 v1.5.1 改变，样条从 v1.5.2 改变。生成和表征均使用同一求值函数；JSON / S2P 注释的实际坐标分别记录为 `linear_magnitude_unwrapped_phase` 和 `cubic_magnitude_unwrapped_phase`，同时记录版本，避免与历史结果混淆。

精确节点优先、禁止外推、not-a-knot 边界不变。恒零 LOAD 保持零；非恒零标准含零幅度且需要插值时，两种方式都明确报错，因为相位无法定义；全部命中精确节点则返回原始值。样条产生负幅度时明确拒绝，不钳位、不取绝对值；可改用幅相线性或提供更合适的标准定义。解缠绕使用 NumPy 默认规则，不能恢复采样不足造成的真实相位混叠。

47 项数值测试通过，当前验证见 `docs/validation_v1.5.2.md`。v1.5.0 / v1.5.1 的验证记录保留，对应各自当时的求值行为。

## v1.5 更新

- 生成窗口和表征窗口新增 **IF 相对 RF 的变频方向**：下变频 `IF=RF−LO`，上变频 `IF=RF+LO`，默认下变频。
- API 在 `SimulationOptions` / `Options` 中新增 `frequency_conversion='down' / 'up'`，文件注释、JSON、真值 CSV 和导出频率轴同步记录。
- 标准件插值只保留 **线性插值** 与 **三次样条插值**。当前两者均为幅度 / 解缠绕相位。旧独立幅相、dB 和 exact API 键不作为额外选项；旧 GUI 保存的已删除键回退为 cubic_ri。
- 自动载入表征窗口时同步变频方向；修改方向后旧结果失效。演示输入恢复下变频。
- 新增 AGENTS.md 说明架构、数学约束、验证命令和接续研发要求。

## 生成校准套对应的 SOL 仿真数据

主界面新增 **生成 SOL 仿真文件 / Mixer 真值**。选择实际 OPEN、SHORT、LOAD 三个 S1P，设置参数并选择输出父目录，生成：

```text
01_Input_SOL_Open.s2p
01_Input_SOL_Short.s2p
01_Input_SOL_Load.s2p
02_Mixer_SOL_Open.s2p
02_Mixer_SOL_Short.s2p
02_Mixer_SOL_Load.s2p
Mixer.s2p
```

附带 `Standard_Open.s1p` / `Standard_Short.s1p` / `Standard_Load.s1p` 原始字节副本、`simulation_report.json` 和 `simulation_truth.csv`。每次生成使用独立 `vmc_sim_时间_标识` 子目录，不覆盖已有结果；写入失败清理本次临时目录。所有 S2P 使用 Hz / S / RI、17 位有效数字和校准套实际参考阻抗。

### 可配置参数和默认值

| 参数 | 默认值 | 含义 |
|---|---|---|
| RF 起点 / 终点 / 点数 | 10 / 20 GHz，201 点 | 包含端点的线性扫频 |
| LO | 5 GHz | 正的固定本振频率 |
| IF 相对 RF 的方向 | down（下变频） | down：IF=RF−LO，所有 RF>LO；up：IF=RF+LO，允许 LO>RF |
| 标准件求值 | cubic_ri | 两种插值，与表征模块一致，禁止外推 |
| Mixer S11 | −18 dB、−20°、20 ps | 输入反射幅度、起点相位和时延 |
| Mixer S22 | −20 dB、30°、15 ps | 输出反射幅度、起点相位和时延 |
| Mixer S21=S12 | −6 dB、−30°、80 ps | 互易转换幅度、起点相位和时延 |
| EDF | −35 dB、30°、5 ps | 方向性误差复响应 |
| ESF | −25 dB、−20°、10 ps | 源匹配误差复响应 |
| ERF | −1 dB、15°、40 ps | 反射跟踪误差复响应，不是单程误差盒 S21 |
| 噪声 | 默认关闭，底值 −90 dB | 加在六路最终测量 S11 上 |
| 随机种子 / 等效平均次数 | 20261009 / 1 | PCG64 可复现噪声；平均后 RMS 按 1/√N 缩放 |

每个复响应的幅度为常数；相位按 `Z(f)=10^(A_dB/20)*exp(j*(phi_start−2*pi*(RF−RF_start)*delay_ps*1e-12))` 变化。起点相位全部以 RF 起点为参考；固定 LO 时第二轮 IF 的相对频率增量与 RF 相同。

### 上变频配置示例

现有 `examples/keysight_validation/short_validation_band.s1p` 仅覆盖 5～20 GHz。可用 RF 10～15 GHz、LO 5 GHz、方向 up，使 IF 为 15～20 GHz。RF 10～20 GHz、LO 5 GHz 的上变频将需要 IF 15～25 GHz，必须换成覆盖该频带的完整标准文件；软件不会外推。

```python
options = SimulationOptions(
    rf_start_hz=10e9, rf_stop_hz=15e9, lo_hz=5e9,
    frequency_conversion='up', standard_sampling='cubic_ri',
)
```

生成和表征需要采用相同方向。两个非反转分支的 IF 增量都等于 RF 增量，现有按 RF 起点定义的相位 / 时延模型不变。六个测量和 Mixer.s2p 仍采用 RF 横轴；普通 Touchstone 不能编码双频轴，使用 accompanying JSON / CSV 或导出的 S2PX 确认真实 IF。

### 生成模型

读取标准文件的真实复数 Γ，不把它们替换为理想 +1/−1/0。第一轮在 RF 求值，第二轮在 IF 求值。

```text
m1 = EDF + ERF*Gamma_RF / (1−ESF*Gamma_RF)
r_mixer = S11 + S12*S21*Gamma_IF / (1−S22*Gamma_IF)
m2 = EDF + ERF*r_mixer / (1−ESF*r_mixer)
```

六个采集 S2P 的 **S11 是原始合成测量响应，其他三个列为零占位**，与已有 SOL 求解文件约定相同；它们不是完整的物理标准两端口网络。`Mixer.s2p` 含四个真实设定的有效系数，始终保持无噪声，以便独立比较算法恢复结果。其 RF 横轴和有效变频系数用于算法对比，普通 S2P 本身不执行频率转换。

本版合成模型为互易混频器＋输入误差盒，支持任意标准套相同且为正的参考阻抗。未自动引入谐波、LO 泄漏、压缩或非互易传输。配置允许正转换增益；有效 S 矩阵奇异值超过 1 时记录提示，不静默修改模型。分母近零、频带覆盖不足、参考阻抗不一致等错误明确拒绝。

### 基线噪声的定义

噪声为各频点、各 SOL 连接状态之间独立的零均值圆对称复高斯噪声，**在输入误差映射之后加入**：

```text
sigma = 10^(noise_floor_db/20) / sqrt(noise_averages)
noise = sigma/sqrt(2) * (normal_I + j*normal_Q)
measured = clean + noise
```

`noise_floor_db` 为相对于归一化 `S=1` 的复数 RMS，−90 dB 在平均次数 1 时对应 3.1623e−5。不是 dBm、dBm/Hz、仪器实际底噪或 IFBW 模型。平均次数采用高斯等效复数平均，没有额外的功率平均。相同输入、配置、种子及 NumPy 版本可复现；报告记录 PCG64、NumPy 版本和实际有效 RMS。

### 验证流程

1. 先关闭噪声，生成七个 S2P；右侧预览混频器真值及两轮三标准响应。
2. 点击“将本轮文件载入表征窗口”，自动填入六个测量文件、三个标准副本、LO、上下变频方向、插值方式和原始第二轮模式。全局开方符号按已知模拟真值的首点选择，并在报告中记录；这利用模拟真值，不代表反射测量能够识别绝对传输符号。
3. 计算得到表征，再与 `Mixer.s2p` 比较。生成与反演应使用同一标准定义和相同求值方式；若有意验证插值差异，可改变反演插值方式。
4. 启用噪声，改变噪声底、种子和平均次数，观察反演后的误差变化。噪声通常随 SOL 条件数和参数灵敏度被放大，表征误差不等于原始设置噪声 RMS。
5. 若采样间隔导致传输乘积每点相位变化 ≥180°，报告提示混叠；需加密频点，不能靠固定整体符号解决。

`simulation_truth.csv` 保留 RF/IF、实际 EDF/ESF/ERF、四个真值 S、每个标准的求值 Γ、每路无噪声响应、含噪声响应及实际加噪量。JSON 保留全部配置、标准原始路径与 SHA256、输出 SHA256、求值边界和噪声信息。

```python
from simulation import SimulationOptions, generate_files
saved = generate_files(
    [open_s1p, short_s1p, load_s1p],
    output_parent,  # 已存在目录；函数新建独立子目录
    SimulationOptions(
        rf_start_hz=10e9, rf_stop_hz=20e9, points=201, lo_hz=5e9,
        standard_sampling='cubic_ri', frequency_conversion='down',
        transmission_db=-6, transmission_delay_ps=80,
        noise_enabled=True, noise_floor_db=-90,
        noise_seed=20261009, noise_averages=1,
    ),
)
print(saved.directory)
```

新增 `simulation.py`（模型与文件层）、`simulate_gui.py`（配置/后台任务/预览），原查看、表征与比较功能保留。参数及最近标准/输出目录通过 QSettings 保存。

本版 47 项数值回归通过：包括上下变频、两种插值闭环、相位跨 ±180° / 多圈解缠绕、线性幅度规则、三次样条幅相多项式解析值 / 多圈相位 / 负幅度拒绝、精确节点原值保持、零幅度边界、导出实际插值坐标记录、解析 / 比较 / Keysight 下变频回归。Qt offscreen 联动检查通过。详见 `docs/validation_v1.5.2.md`；未在 Windows/PNA 现场运行，上变频 Keysight 对照待验证。

### 操作顺序

1. `uv run python main.py`，点击“两轮 SOL → 校准混频器表征”。
2. 在六行测量输入中选择第一轮 Input Open/Short/Load 与第二轮 Mixer Open/Short/Load 的 S2P；仅读取 S11，两轮文件横轴都是 RF。
3. 在共用标准区选择 OPEN、SHORT、LOAD 三个 S1P。第一轮按 RF 求标准值，第二轮按所选 IF=RF−LO 或 IF=RF+LO 求值；同一个标准文件须覆盖两个频段。
4. 选择插值方式、上下变频方向、固定 LO（默认 5 GHz）、第二轮修正层级和传输整体分支。点击“计算并载入主界面”。
5. 保存表征 S2P 或导出诊断包；打开 Keysight 结果，使用“比较任意两份表征文件”。差值 A−B，比较 S2P 通常选 StimulusFreq；S2PX 频率轴需按实际配置选择。

### 标准件求值选项

| 界面选项 | API 名称 | 行为 |
|---|---|---|
| 幅度 / 解缠绕相位三次样条 | `cubic_ri`（历史兼容键） | 线性幅度、解缠绕后的相位各自三次样条 |
| 幅度 / 解缠绕相位线性插值 | `linear_ri`（历史兼容键） | 线性幅度、解缠绕后的相位各自线性插值 |

所有方式优先使用容差内唯一命中的原定义值，默认容差 0.001 Hz，均禁止外推。三次样条用 SciPy CubicSpline 的 not-a-knot 边界；完整定义频带的边界会影响样条结果，建议使用原始完整标准文件。恒零 Load 保持为零；非恒零标准含零幅度且需要插值时，两种方式都拒绝；样条产生负幅度时拒绝，可改用幅相线性或提供更合适的标准定义。精确节点优先属于两种插值的共同规则，不是独立的“仅精确频点”选项。

测量数据本身不插值。六个测量须有同一严格递增网格；测量和标准参考阻抗须一致，不自动重归一化。拒绝重复/歧义标准节点、缺频段、退化标准及病态求解。

**GUI 首次默认 cubic_ri；纯数值 API 的 Options 默认仍为 linear_ri（现为幅相线性），保留调用键兼容，但两种插值的数值行为均已改变。**调用 API 时请显式指定所需模式。插值推荐基于本次仿真对比，不意味着已经确认 Keysight 的内部算法。

### 算法与边界

一端口：`m=D+R*Gamma/(1−S*Gamma)`，其中 D=EDF、R=ERF、S=ESF。线性求解 `m=A+B*Gamma+S*m*Gamma`，恢复 D=A、R=B+A*S。

第二轮为原始组合响应时，令 `Q=R1+S1*(D2−D1)`：

- `C11=(D2−D1)/Q`
- `P=C12*C21=R1*R2/Q**2`
- `C22=S2−S1*R2/Q`

代码使用数值等价的 Mobius 矩阵消除法，并用先修正反射、再直接求解的独立路径交叉核对。若第二轮已经第一轮校正，直接取其 D/S/R 为 C11/C22/P，不再消除输入误差盒。

反射 SOL 仅确定传输乘积 P；以互易假设取 `C21=C12=sign*sqrt(abs(P))*exp(0.5j*unwrap(angle(P)))`，整体 ± 分支需独立相位参考。不得逐点复数主值开方造成 180° 跳变。支持固定 LO 的非反转下变频 IF=RF−LO（全部 RF>LO）和上变频 IF=RF+LO（IF 高于 RF）。不支持 IF=LO−RF 的反转差频分支，目标参考面为混频器＋滤波器整体。SOL 回代和两路径一致性是数值自检，不替代外部验收。

### 输出和 API

输出高精度 Hz/S/RI S2P（17 位有效数字，顺序 S11/S21/S12/S22）、自研 CSV S2PX、`sol_diagnostics.csv`、`characterization_report.json`。S2PX 仿照已知布局，不是 Keysight 生成文件；零幅度无法完整表达 DB S2PX 时诊断包仍保留 RI S2P。

```python
from characterization import Options, characterize, export_s2p, export_bundle
result = characterize(
    measurement_paths,  # [input_O,input_S,input_L,output_O,output_S,output_L]
    [open_s1p, short_s1p, load_s1p],  # 两轮共用
    Options(lo_hz=5e9, frequency_conversion='down',
            standard_sampling='cubic_ri', second_round='raw', root_sign=1)
)
export_s2p(result, 'my_mixer.s2p')
export_bundle(result, 'my_mixer_validation.zip')
```

数值 API 仍兼容旧版六标准路径调用；界面只要求三个。报告中的六条 inputs 表示六个测量角色，共用标准的路径和 SHA256 在相应两轮重复记录，保证可追溯。

### 示例与验证

- `examples/characterization_demo`：六个合成测量＋三个明确标为理想演示的标准定义，覆盖 RF/IF；载入演示按钮可直接计算。不是用户物理校准件。
- `examples/keysight_validation`：本次会话的六个仿真文件、三个标准定义和当前 Keysight 表征。Short 是 5–20 GHz 验证频带摘录；来源与限制写在目录 README 和输入注释中。实际工作建议使用完整原始标准文件。
- 本次 Keysight 数据全 201 点使用 cubic_ri 的最大复数差约 1.87×10⁻⁷；不是仪器测量准确度规格，剩余残差和 Keysight 内部求值方式尚待核实。
- 当前数值和界面验证见 `docs/validation_v1.5.2.md`；旧版本记录保留。

## Windows 快速启动

解压整个目录后，在目录中打开终端：

```powershell
uv run python main.py
```

已安装 uv 时也可双击 `start_windows.bat`，首次运行自动准备依赖。

不用 uv：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

PyCharm：使用安装了 requirements.txt 的 Python 解释器，直接运行 main.py。
也可通过命令行打开文件：`python main.py "D:\data\mixer.s2px"`。

## 使用

- 打开、拖入一个或多个文件；左侧列表切换查看（不叠加）。
- **粘贴文件内容**：直接粘贴完整头部和数据，不必先保存文件。按内容识别格式。
- S11 / S12 位于上排，S21 / S22 位于下排。
- 显示幅度 dB、线性幅度、相位、展开相位、实部、虚部。
- 频率单位可选 Hz/kHz/MHz/GHz；S2PX 可选 InputFreq、OutputFreq、LO1Freq、可选 LO2Freq。另有点序号横轴。
- 分段筛选；不连接不同连续段，展开相位不跨段。点数少时显示数据标记。
- 绘图工具栏支持缩放、平移、恢复和保存图像；鼠标移动显示最近横坐标数据点。
- 数据表显示完整复数数据、幅相、频率和功率列；文件信息页显示元数据；原始文本页便于核查。
- CSV 导出**全部点和全部参数**，不受显示模式及分段筛选影响。CSV 包括 RI、dB/相位以及实际频率列，可在 Excel/Python 中分析。导出 CSV 为分析格式，不作为原始 S2PX 回读格式。
- 最近目录、窗口大小和显示模式自动保存；文件读取和 CSV 写入在工作线程执行。

## 格式和测量含义

### S2P

支持 Touchstone 1.x 二端口 S 参数的 DB/MA/RI、Hz/kHz/MHz/GHz、科学计数法与 Fortran D 指数、跨行记录及注释。
标准顺序为 S11、S21、S12、S22；程序不会按 GUI 四窗顺序误读。
当前不支持 Touchstone 2.x、噪声参数块、Y/Z/H/G 参数。遇到不支持的结构会报错。

MixerConfiguration XML 作为元数据提取。非分段模式读取 NonSegmentSweepFrequencies，而非备用 SegmentList。
S2P 仅以正文 StimulusFreq 作频率轴，**不依据 XML 自动补点或推断输入/输出频率**。
配置点数与正文不符时提示，以正文为准。参考阻抗显示选项行中的值，不作重归一化。

### S2PX

按本次提供的 Keysight `!CSV A.01.00` Converter Sweep Data 格式实现。
按 CSV 列名匹配，列顺序变化不影响解析。需要 InputFreq、OutputFreq 和四个 S 参数的 Mag (dB)/Phase (Deg) 列。
支持可选 SegIndex、LO1Freq/LO2Freq 及功率列；所有数据列须为数值。不按 `Data Column Index` 的位置猜测。
频率列按样例单位 Hz 读取。文件没有声明参考阻抗，程序显示“未声明”，不默认 50 Ω。
其他尚未提供的 Keysight S2PX 变体不保证兼容，缺字段会明确提示。

零幅度的 dB 为 -Inf、相位为 NaN；绘图留空，表格和 CSV 保留定义。展开相位需相邻点相位变化可辨识，不保证稀疏采样下的真实延迟恢复。查看模式不计算群时延、不自动修正打开的文件或强制互易；新增两轮SOL模块按明确选择的修正层级求解，并基于互易假设提取传输。

## 示例与验证

examples/pna_excerpt.s2p：用户贴出的两个真实数值记录，XML 缩减到相关配置，不是完整原文件。
examples/pna_excerpt.s2px：用户贴出的一个真实数值记录。单点显示散点，不能形成频率响应曲线。
两份示例首点幅相吻合至 S2PX 导出精度（六位小数）；不强行认为字节完全一致。

```powershell
python -m unittest discover -s tests -v
```

已验证：样例首点一致性、非对称 S12/S21 映射、跨行记录、MA/RI/DB 转换、CSV 列重排、分段相位解缠、异常数据拒绝及 CSV 导出。
GUI 在 Linux Qt offscreen 环境进行启动/绘图/各显示模式和轴切换检查；未在 Windows 或真实 PNA 主机现场运行。

## 文件结构

- main.py：PyQt6 主窗口、后台任务、Matplotlib 绘图。
- characterization.py：提取核心；simulate_gui.py / characterize_gui.py：配置及联动。
- simulation.py：正向仿真、噪声、文件生成。
- frequency_mapping.py：上下变频映射，生成和表征共用。
- comparison.py / compare_gui.py：唯一频率匹配、统计和比较界面。
- AGENTS.md：后续 AI / 开发者的工程约定。
- parser.py：数据模型、两种格式解析、数值变换和 CSV 导出，无 GUI 依赖。
- tests/test_parser.py：解析与数值回归用例。
- examples/：本次文本样例。
- pyproject.toml、requirements.txt：依赖声明。

参考格式：IBIS Touchstone 标准 https://www.ibis.org/touchstone_ver2.0/ 。
S2PX 解析依据用户提供文件结构；未假设其与标准 Touchstone 等价。

## v1.1：同名 S2P / S2PX 比较

1. 同时打开 `mixer.s2p` 与 `mixer.s2px`，点击左侧 **比较同名 S2P / S2PX**。
2. 选择文件对；以不区分大小写的文件主名匹配，列表显示完整路径便于区分不同目录的同名文件。重复打开的文件也会列出，请确认所选对象。粘贴数据可用同名加不同后缀命名。
3. 选择 S2P Stimulus 对应的 S2PX 频率列。初始为 InputFreq，**不保证所有文件的 Stimulus 都是输入频率，需用户确认**。
4. 默认绝对频率容差 0.001 Hz，可调整。点击“计算差异”。
5. 在 2×2 图中查看幅度差、相位差、复数差模值、实部差、虚部差或两文件幅度叠加。统计页给出各参数的最大绝对差及 RMS。导出匹配点差异 CSV，包括两文件原始行号、频率、复数值、段号和各类差值。

定义：ΔdB = 20log10(|S2P|) − 20log10(|S2PX|)；Δφ = wrap(arg(S2P) − arg(S2PX))，范围 [−180°,180°)；Δcomplex = S2P − S2PX。

匹配只采用频率的一对一唯一对应，不插值、不强行按行号配对；一对多、多对一及重复频率歧义点全部排除并统计。未匹配点不参与误差统计。当前不进行段号辅助匹配，因为 S2P 没有可靠的逐点段号。曲线在断点和段边界分开。
零幅度的 dB/相位差为 NaN，对应统计排除；复数差仍有效。程序不假定两文件的未知参考阻抗相同、不作重归一化，也不自动给出算法正确/错误或通过/失败判据。

本次样例匹配 1 点，S2P 余下 1 点未匹配；S21 幅度差约 +6.414e-7 dB，符合文件数值舍入差。已添加相位跨 ±180°、乱序/容差、重复频点、零幅度、无匹配以及差异导出回归测试。
