# VNA Calibration Workbench · VNA 校准与验证工作台 开发约定

本工程用于校准混频器算法的正式验证：查看 S2P / Keysight S2PX、生成可追溯的 SOL 仿真输入、从两轮 SOL 提取表征、与真值及 Keysight 输出比较。正确性优先于界面装饰。先读 README.md、CHANGELOG.md 和相关测试，再修改。

产品名称统一为 VNA Calibration Workbench / VNA 校准与验证工作台，Python 项目名为 vna-calibration-workbench。通用算法按 docs/plans/roadmap.md 规划，不因名称变化而宣称已支持。GitHub 仓库地址仍为 fishbupt/vmc_sparam_viewer。历史验证记录保留当时版本；QSettings 的已有命名空间是兼容标识，不随产品更名而改变。

## 环境与入口

- Python 3.10+；依赖见 pyproject.toml / requirements.txt：NumPy、SciPy、PyQt6、Matplotlib。
- 在仓库根目录运行 `uv run python main.py`，或用虚拟环境安装 requirements.txt 后直接运行 main.py。
- 支持 Windows / PyCharm 直接运行 main.py；根目录 main.py 只启动 vna_workbench.app.application；内部使用包绝对导入，不要求用户用 `python -m` 才能启动。
- 不提交 .venv、__pycache__、IDE 配置、个人标准套、真实采集记录和本次生成的结果目录。

## 模块边界

| 模块 | 职责 |
| --- | --- |
| vna_workbench/app/ | 应用启动、校准类型注册及显式生成结果到校准输入的映射 |
| vna_workbench/data/ | 数据容器、S1P/S2P/S2PX 解析、公共 S2P 写出、归档与结果包导出 |
| vna_workbench/core/ | 标准求值、SOL / 反射校准、频率转换与数值防护 |
| vna_workbench/calibration/vmc/ | 表征、21 项求解、MUT 修正、输入验证与 VMC 校准包 |
| vna_workbench/calibration/trl/ | 仅预留包，TRL 算法仍未实现 |
| vna_workbench/simulation/ | 两轮表征与 VMC 的独立正向生成；不调用校准求解数学 |
| vna_workbench/analysis/ | 显示变换、分段、匹配与比较、查看数据 CSV |
| vna_workbench/gui/ | 主窗口、持久工作区、查看 / 比较页面、VMC 工作流、通用 worker |
| tests/core/、tests/vmc/、tests/gui/ | 共用数值 / 文件、VMC 数值和 Qt 联动检查 |
| docs/algorithms/ | 仅公式与对应代码 / 函数；按 common / vmc 分类 |
| docs/guides/、docs/validation/、docs/plans/ | 使用说明、历史验证及开发计划，禁止混入算法公式页 |

当前映射及迁移方式见 [模块结构](docs/architecture/module_structure.md)，文档入口见 [docs/README.md](docs/README.md)。

GUI 不得复制另一套算法公式。耗时计算和文件 I/O 继续放到后台线程。控件修改后使当前结果及导出失效；已载入主窗口的数据是独立快照。QSettings 记录最近参数和目录，非法旧插值设置回退为 cubic_ri，不能恢复已删除的选项。

## 必须保留的数学约定

1. 六个采集输入按 `[input_open,input_short,input_load,output_open,output_short,output_load]` 排列，均读取 S11，横轴均为 RF。生成文件的 S21 / S12 / S22 是零占位，不代表完整标准网络。
2. GUI 默认共用 `[OPEN,SHORT,LOAD]` 三个 S1P；v1.11.0 支持显式选择 P2 独立标准，六路径按 P1 O/S/L、P2 O/S/L 排列。第一轮在 RF 求值，第二轮在映射 IF 求值。
3. `frequency_conversion='down'`：IF=RF−LO，所有 RF 必须大于正 LO。`'up'`：IF=RF+LO，允许 LO 高于 RF。两者是非反转分支，固定 LO 下 dIF/dRF=+1。不用 abs(RF−LO) 代替，LO−RF 使用独立 high_side 模式（v1.10.0 新增），要求 LO>全部 RF。
4. 仅保留 `linear_ri` / `cubic_ri`：v1.5.1 起 `linear_ri` 是历史兼容键，实际对线性幅度 `abs(Gamma)` 和 `unwrap(angle(Gamma))` 分别线性插值，再重构复数；不要退回实虚部线性，也不要改成 dB 插值。v1.5.2 起 `cubic_ri` 也是历史兼容键，实际对线性幅度和解缠绕相位分别三次样条插值，再重构复数；不要退回实虚部样条。精确节点优先；默认容差 0.001 Hz；禁止外推；拒绝容差内多节点、重复节点。三次样条边界为 not-a-knot；不要改成 natural 或偷偷裁剪标准频带。恒零 LOAD 保持零；非恒零标准含零幅度且需要任一种插值时拒绝，不给零幅度虚构相位；全部命中精确节点则保留原值。样条若产生负幅度须报错，不取绝对值、不钳位；可建议幅相线性或调整标准定义。
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
uv run python tests/gui/gui_simulation_smoke.py
uv run python tests/gui/gui_vmc_calibration_smoke.py
uv run python tests/gui/gui_viewer_display_smoke.py
uv run python tests/gui/gui_vmc_simulation_smoke.py
uv run python tests/gui/gui_workbench_smoke.py
uv run python tests/gui/gui_analysis_smoke.py
```

算法 / 映射修改需覆盖上下变频、两种插值、两种幅相插值跨 ±180° / 多圈解缠绕、样条幅相多项式解析恢复与负幅度拒绝、线性幅度而非 dB、零幅度相位拒绝、精确节点原值保留、非理想标准、无噪声闭环、原始 / 已修正第二轮、输出轴 / 注释 / JSON 一致性、外推拒绝及独立正向波量方程。不要仅以生成器和提取器相互吻合作为正确性依据。

GUI 检查控件只有两种插值、方向改变后的结果失效、生成到表征方向联动、设置保存 / 迁移和演示恢复下变频。Qt offscreen 检查不能宣称 Windows / PNA 现场验证已完成。

当前 Keysight 回归样本是下变频，201 点 cubic_ri 最大复数差约 1.87e−7；这不是仪器精度规格或上变频 Keysight 实测验证。SHORT 文件仅为 5～20 GHz 摘录，正式验证需完整原始标准文件。改动后更新版本、README、CHANGELOG 与验证记录，区分已验证事实、模型假设及待验证限制。

## VMC 全量校准约定（v1.6.0）

- 主界面保留展示与比较入口；不另建“对比验证”页。工作流名称为“校准 MUT”。主界面显示支持右键幅度 / 相位 / 解缠绕相位及独立 Y 轴范围；比较仍复用现有入口。
- VMC 校准窗口采用左右布局：左侧为 RF / LO / 自动派生 IF、求值 / 横轴配置与校准操作；右侧为标准件定义 OPEN / SHORT / LOAD / THRU、原始测量 OPEN / SHORT / LOAD / THRU / CalTHRU、独立的已表征校准混频器。MUT 页共享左侧配置；左右宽度可调，各自滚动。
- 保留 P1_RF / P1_IF / P2_RF / P2_IF 的 EDF、ESF、ERF；普通 Thru 求每频段 ELF / ELR / ETF / ETR，再以 P1_RF_ESF 和 IF_ELF 求 VMC_ETF。
- 校准混频器 ETF 的完整分母为 `(1-C11*ESF)*(1-C22*ELF)-C12*C21*ESF*ELF`，交叉项是 C11*C22，不能写成 C11*C21。
- MUT 用单端口反射校准及批准的 VC21 两失配因子公式；只承诺单向 / 忽略反向耦合模型，不能称为完整双向去嵌。反向 S12 不校准；导出零占位和报告必须明确标记。
- 变频原始文件横轴显式选择 RF / IF / dual；dual 要求频段不重叠且两段对应四参数一致。普通 SOL / Thru 按实际频段匹配。标准定义可插值，原始测量不插值；不拟合结果消除差异。
- 本轮没有 isolation、switch-term 和 receiver-ratio 独立采集，不假定 Keysight 与本模型误差项规范完全相同。GUI offscreen 不代表 Keysight / Windows 现场验证。
- 校准包使用无 pickle 的 NPZ 和 JSON，校验数组 SHA256、项目 / 形状 / 频率配置；原子写入；源文件哈希来自解析同一份字节快照。MUT 文件 / 横轴改动只使 MUT 结果失效；校准配置改动则使校准包与 MUT 结果均失效。

## VMC 原始测量生成约定（v1.7.0）

- 生成器以 `a=T+E*b; b=C*a; M=D+T*b` 独立正向求解；不得调用 calibrate / calibrate_mut 得出原始响应或期望误差项。只在一键载入适配层复用配置与输入映射类型。
- 普通 SOL / Thru 按物理频率生成，CalTHRU / MUT 按成对 RF→IF 生成。双频段复制仅允许不重叠频段；RF/IF两段必须复制同一噪声样本，间隔桥接值仅用于文件覆盖，不参与测量。
- 默认理想 SOL + Flush 零延迟/损耗；定义文件、raw 文件和真值文件严格区分。导入实际定义按同一幅相插值求值、禁止外推、阻抗一致，不更改原校准算法。
- MUT 固定 S12 真值为零，cal mixer 模型互易；单程 t 与 ERF=t² 区分，端口盒按实际 RF/IF 频率计算。默认同盒无噪声 SOL 两端口相等；独立盒/噪声允许不同。
- 输入文件只读一次，解析/归档副本/哈希来自同一字节快照。运行目录原子发布，失败清理暂存目录，不覆盖旧运行；保存无噪声真值、clean/raw、频率映射与参数/哈希。

## 主界面导航约定（v1.8.0）

- 默认进入查看与比较，无需先建项目。固定流程导航与数据侧栏分离，校准导航共享同一个 VMC 输入 / 校准实例；不因换页重复求解或使结果失效。
- v1.8.1 校准类型注册在 vna_workbench/app/calibration_registry.py；菜单与顶栏选择同步。未实现类型仅显示占位，不得复用 VMC 表单执行它们。数据查看 / 差异统计独立，切回 VMC 保留原状态，后台执行期间禁止切换类型。
- 双端口曲线位置为 S11 / S21 在上、S12 / S22 在下；`Window.axes` 数组仍按 PARAMS 顺序，避免破坏菜单、Y 轴和导出索引。
- 勾选控制叠加，选中控制表格 / 元数据 / 导出；颜色按数据集固定。叠加不匹配或插值，各文件的横轴 / 分段设置独立，必须提示确认 RF / IF 含义。
- 验证报告复用 CompareDialog 的数值计算与导出，不能绕过 A 的 StimulusFreq 约束。通用算法、项目文件与自动容差判定尚未实现。
- 底部日志汇总嵌入式工作流；关闭时检查所有页面后台线程。保留独立对话框用法和已有脚本联动。
- 本版 GUI / 包版本 1.8.0，算法及其报告版本保持 1.7.0；不因纯界面改动篡改历史算法可追溯性。

## 数据查看约定（v1.8.2，替代 v1.8.0 的勾选叠加约定）

- 默认进入单文件查看，文件库无显示勾选；只展示当前选中的一个数据集。双文件比较使用 ComparisonPage 显式选择 A/B，与单文件的横轴、分段、模式及 Y 范围独立。
- 叠加绘制两份文件各自原始网格，不要求匹配；差异复用 comparison.compare，显式选两側物理频率轴及分段，以原始行号记录匹配。不插值，不跨分段或缺失点连线；相位解缠绕复用 parser.values。
- 验证报告打开同一个 ComparisonPage，不复制计算实现。历史同名 CompareDialog 保留默认 StimulusFreq API；新比较不要求 A 含 StimulusFreq。
- A/B 或求解配置改变使结果失效；查看第三个文件、添加 / 移除无关文件不改变比较结果。所有页面后台任务进入主窗口 busy / 关闭保护。
- GUI / 包版本 1.8.2，校准算法与报告版本保持 1.7.0。

## 单文件样式约定（v1.8.3）

单文件曲线统一蓝色实线，不按文件 / 参数分配颜色和形状，不显示点标记；文件库文字颜色统一。仅比较模式用颜色、线型和图例区分 A/B。GUI / 包版本 1.8.3，算法报告版本保持 1.7.0。

## 结构重构约定（v1.9.0）

根目录仅保留 main.py 入口，旧平铺模块不继续作为导入入口；迁移映射见架构文档。公共算法函数签名、文件 schema、算法报告版本 1.7.0 和旧 QSettings 命名空间保持。不得引入从 core/data/analysis/calibration 到 GUI 的依赖。生成器只在 SavedVMCSimulation 的显式一键载入适配方法中委托 app/workflows.py，不在正向计算中调用校准器。历史验证记录的旧模块名与测试结果保留，链接指向实际迁移后的路径。


## 高边 LO 约定（v1.10.0，算法 / 报告 1.8.0）

- high_side=LO−RF；IF 按 RF 点序递减。标准 / 原始 IF 文件仍递增保存，数值列与频率一起排序；内部不打乱 RF→IF 配对。dual 用频段 min/max 判断交集，端点接触也禁止。
- 表征第一轮不共轭，第二轮仅将按 IF 求值后的标准共轭。Möbius 输出 C22 为输入参考等效反射，导出物理 S22 时共轭回来；两路径诊断在转换前比较。
- 文件反射 S11/S22 为物理量，S12/S21 为输入参考等效量：b1=S11*a1+S12*conj(a2)，b2=conj(S21)*conj(a1)+S22*a2（LO 相位规范 0）。传输开方仍基于等效互易假设，不宣称识别绝对 LO 相位。
- 原始 SM21 为物理接收响应；ETF / VC21 求解使用 conj(SM21)、conj(IF_ELF)、conj(S22)，物理端口 SOL/THRU 不共轭。不得把这一约定未经验证称为 Keysight 内部约定。
- 高边原始生成使用 simulation/conjugate_waves.py 的独立实线性波量求解，不调用反演算法。内置非理想 SOL 仅为测试用，用户和 Keysight 需加载生成的同一套定义。
- 高边预设为 RF 10～15 / LO 20 GHz、RF 横轴、无噪声；保留模型参数。旧默认仍为上变频，不改变已有文件含义。
- 新增测试：tests/vmc/test_high_side.py、tests/gui/gui_high_side_smoke.py。验证记录与使用条件不写入 docs/algorithms 公式页。


## 共享 VMC 与五步流程（v1.11.0）

- VMCSession 是工作台内 VMC 配置的唯一来源，保存于既有主窗口 QSettings 的 vmc_global/config。旧单页设置仅用于首次迁移，不覆盖已经恢复的全局配置。
- 导航按“全局配置 / 生成两轮 SOL / 表征 / 生成原始 SNP / 校准求解 / 校准 MUT”组织，默认仍进入数据查看。工具菜单复用持久页面；未实现校准类型仍为空占位。
- 全局 RF/LO/点数/阻抗/标准求值/容差/原始轴联动所有步骤。各步骤只读摘要，配置集中修改。修改全局配置时使有关结果失效，主界面快照和磁盘文件保留。后台执行期间禁止冲突编辑。
- 生成两轮 SOL 支持共用三标准或独立六标准，六个定义和哈希完整保存。传入表征不得丢失 P2；VMC 正向生成按 P1/P2 各自物理标准生成反射，并将独立标准映射到校准输入。
- 步骤 2 送入步骤 3 时以唯一名字保存当前表征，明确 RF 横轴；用户手动导入的外部 IF 轴文件仍需显式选择，不自动猜测。范围不足错误显示文件频段、所需频段及横轴，禁止外推。
- 新增 tests/vmc/test_independent_kits.py 与 tests/gui/gui_vmc_shared_workflow_smoke.py。工作台 1.11.0，算法报告仍为 1.8.0；此次不改变校准公式。


## 原始横轴兼容性（v1.11.1）

- VMCSession 在手动编辑、全局恢复和旧单页迁移中统一处理轴兼容：RF/IF 端点相接或重叠且 raw_axis=dual 时，改为全局 raw_axis=rf，保留有效频率、点数及其它配置，并在摘要显示原因。核心 dual 编码的严格拒绝规则不变。
- 工作台内两个生成器及校准求解的实际 Options 从共享配置取值，不以隐藏控件或各页历史设置为最终来源。独立对话框 API 保留自有参数。
- 摘要必须显示实际原始轴；生成日志记录后台参数。回归 tests/gui/gui_vmc_axis_sync_smoke.py 覆盖用户 RF 10～15 / LO 20 / IF 10→5 GHz 的三种配置来源、表征导入、真实生成与校准闭环。
