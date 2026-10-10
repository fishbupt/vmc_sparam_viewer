# VMC 校准与验证工作台使用说明

**VMC Calibration Workbench · v1.6.3**

本文说明全量 VMC 校准与校准 MUT；仿真数据生成、两轮 SOL 表征与主界面展示操作见仓库 README。

主界面点击 **VMC 校准误差项 / 校准 MUT**。此功能位于 `vmc_calibration.py`，GUI 位于 `vmc_calibration_gui.py`。原有两轮 SOL 的 `characterization.py` 仍负责表征校准混频器。

窗口左侧为 VMC / MUT 配置与校准操作：RF、LO、方向和自动显示的 IF 起止频率、标准插值、文件横轴、校准包与误差项。右侧“计算 VMC 校准误差项”页按 **标准件定义（OPEN / SHORT / LOAD / THRU）→ 原始测量（OPEN / SHORT / LOAD / THRU / CalTHRU）→ 已表征校准混频器** 排列。左右可拖动调整宽度，各自独立滚动；“校准 MUT”页仅放 MUT 文件与执行 / 导出操作，共享左侧配置。

CalTHRU 指接入校准混频器后的变频 Thru 原始测量，与其已表征 S2P 分开放置。THRU 定义可选择理想 Flush 或加载 defined Thru；两端口独立标准及12组独立 SOL 的高级输入方式保持不变。

## 操作流程

1. 在“计算 VMC 校准误差项”页设置 RF 起止、点数、固定 LO、上 / 下变频、参考阻抗和标准插值。
2. 选择三个标准 S1P；如两端口定义不同，勾选 Port2 独立标准件。每个定义须覆盖 RF 和 IF。
3. 导入 SOL 原始数据。默认共用 OPEN / SHORT / LOAD 三个 S2P：P1 读取 S11，P2 读取 S22，在各自 RF / IF 频点取值。若勾选逐项导入，分别指定 P1_RF / P1_IF / P2_RF / P2_IF 的三份 S1P / S2P；独立 S1P 的唯一反射列代表所选物理端口，不把其名字 S11 理解为端口1。
4. 导入普通 Thru 原始 S2P。IF 路径留空时复用 RF 路径，但该文件必须同时覆盖两频段。选择理想 Flush 或勾选 defined Thru 并提供完整四参数定义；定义可共用或分别导入。
5. 导入已表征校准混频器 S2P 和该混频器的变频 Thru 原始 S2P。明确表征文件和原始文件横轴含义。
6. 点击“计算 VMC 校准误差项”。求得 21 条复数误差项后可保存校准包；选择误差项并载入主界面，在 S21 中查看该标量误差项。普通 IF 误差项的 Stimulus 横轴为实际 IF，变频 ETF 的 Stimulus 横轴为 RF。
7. 切换到“校准 MUT”，选择原始 MUT S2P及横轴，点击“校准 MUT 并载入主界面”。原始与校准后数据会分别成为主界面的数据集；校准后 S21 代表 VC21。
8. 复用主界面已有视图 / 比较功能，或导出 MUT 结果包。本轮不另建对比页，也不修改主界面的相位比较行为。

校准包可通过“载入校准包”恢复频率配置、误差项和原始输入映射；即使原始标准 / 校准文件已移走，仍可用于新 MUT 数据校准。修改校准输入 / 配置后原校准和 MUT 结果失效；只修改 MUT 文件 / 横轴则保留校准，使 MUT 结果失效。

## 当前 Dummy DUT 基线的输入

| 项目 | 选择 |
| --- | --- |
| RF / 点数 | 10～20 GHz / 201 |
| LO / 方向 | 20 GHz / 上变频，IF=30～40 GHz |
| 阻抗 | 50 Ω |
| 标准定义 | 基线包 standard_definitions/open.s1p、short.s1p、load.s1p |
| 共用 SOL 原始 | open_raw.s2p、short_raw.s2p、load_raw.s2p |
| 普通 Thru | thru_raw.s2p，共用 RF / IF；理想 Flush |
| 已表征校准混频器 | 与基线参数匹配的 calibration_mixer.s2p；RF 横轴 |
| 校准混频器原始 | cal_mixer_raw.s2p；双频段复制横轴 |
| MUT 原始 | mut_raw.s2p；双频段复制横轴 |

校准混频器真值参数：S11=−18 dB/−20°/20 ps，S22=−20 dB/+30°/15 ps，S21=S12=−6 dB/−30°/80 ps。相位以 RF=10 GHz 为起点。用户文件 / 此基线不提交到公共仓库，测试使用独立合成输入。

## 数据与频率规则

- 原始测量只在配置频点容差内唯一匹配，不插值，不拟合，不自动重归一化；缺点、重复点或参考阻抗不一致报错。
- 标准件与 defined Thru / 校准混频器定义可按幅度和解缠绕相位线性 / 三次样条求值，精确节点优先、禁止外推。三次样条采用 not-a-knot；负幅度及非恒零数据中的零幅度相位插值报错。
- **RF 横轴**：变频原始 S11、S21、S12、S22 都按 RF 频率列匹配，每行代表对应 RF→IF 点。
- **IF 横轴**：四个参数都按 IF 列匹配，每行仍代表对应 RF→IF 点。
- **双频段复制**：RF 与 IF 不重叠，文件两段对应四参数一致。软件核对复制一致性后使用同一变频响应；不是普通同频 S2P 变成了频率转换器。
- 表征文件横轴显式选择 RF 或 IF，不能将普通原始文件的双频段模型直接当作表征真值。

## 计算公式

每个端口、每个频段独立 SOL：

\[
m=D+\frac{R\Gamma}{1-S\Gamma},\qquad
\Gamma_{corrected}=\frac{m-D}{R+S(m-D)}.
\]

保留 EDF=D、ESF=S、ERF=R；共 P1_RF / P1_IF / P2_RF / P2_IF 四组。

普通 Thru 定义为 C，先用对应 SOL 消除输入端反射误差得到 g1 和 g2；以正向为例：

\[
ELF=\frac{g_1-C_{11}}{C_{12}C_{21}+C_{22}(g_1-C_{11})},
\]

\[
ETF=\frac{m_{21}}{C_{21}}
\left[1-C_{11}ESF-C_{22}ELF+
(C_{11}C_{22}-C_{12}C_{21})ESF\,ELF\right].
\]

交换端口得到 ELR / ETR。RF / IF 各保留四项。方向性与反射跟踪分别来自两个端口的独立 SOL，源匹配和负载匹配分别保留，不默认二者相等。

变频校准采用已表征的校准混频器 C：

\[
ETF_{RF\to IF}=\frac{S_{M21}^{cal}}{C_{21}}
\left[(1-C_{11}ESF_{P1,RF})(1-C_{22}ELF_{IF})
-C_{12}C_{21}ESF_{P1,RF}ELF_{IF}\right].
\]

交叉项必须为 **C11*C22**，不是此前疑似笔误的 C11*C21。

MUT S11 使用 P1_RF SOL 校准，S22 使用 P2_IF SOL 校准；随后按确认的公式：

\[
VC_{21}^{MUT}=\frac{S_{M21}^{MUT}
(1-S_{11}^{MUT}ESF_{P1,RF})
(1-S_{22}^{MUT}ELF_{IF})}{ETF_{RF\to IF}}.
\]

**该 MUT 公式与单端口反射校正针对单向 / 忽略反向耦合模型；不宣称完整双向去嵌。** 校准混频器本身允许 C12 非零，ETF 求解保留完整交叉项。本轮没有独立 isolation、receiver ratio 或 switch term 输入；传输泄漏按零处理。不同 Keysight 模式的误差项约定须通过实际导出确认。

## 文件格式与追溯

校准包 ZIP：

- calibration.json：配置、公式、输入路径 / SHA256、标准插值、SOL 条件数 / 回代残差和限制。
- arrays.npz：RF / IF 及 21 个复数误差项；不使用 pickle，加载时校验 SHA256、数组形状和配置频率轴。
- error_terms.csv：逐点 RF / IF 与全部复数误差项，可与外部数据逐项比较。

校准 MUT 结果包 ZIP：

- calibrated_mut.s2p：RF 横轴、S11、VC21、S22；**S12=0 仅为未校准占位**，注释及报告明确说明。
- calibrated_mut.csv：校准后的 S11 / VC21 / S22，实部与虚部保存。
- raw_mut.csv：本轮匹配的四个原始参数。
- frequency_map.csv：RF / IF / LO 映射。
- report.json：算法版本、完整校准报告、MUT 原始文件哈希、横轴与限制。

保存操作使用临时文件再原子替换，GUI 文件处理和计算均在后台 QThread。输入更改不修改已载入主界面的独立数据快照。

## 本地验证

```powershell
uv run python -m unittest discover -s tests -v
uv run python tests/gui_simulation_smoke.py
uv run python tests/gui_vmc_calibration_smoke.py
```

新测试的标准、误差盒和 Thru 由独立内部波量方程构造，覆盖非理想标准、非互易 defined Thru、上下变频、三种原始横轴、非对称端口误差、文件重载和异常拒绝；不依赖个人 examples 数据。详见 validation_v1.6.0.md。
