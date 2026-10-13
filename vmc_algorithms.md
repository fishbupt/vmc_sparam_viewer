# VMC 核心算法代码说明

整理日期：2026-10-13。分支：`Enhanced`。
源码基准：`0bd7f3abc2a93fb32ee2c6af254abc801326e4a3`；GUI / 包版本 1.8.3，算法报告版本 1.7.0。

本文按当前源码提取算法，不修改实现。覆盖校准混频器表征、VMC 校准误差项计算及被测混频器误差补偿；GUI 中第三步命名为“校准 MUT”。公式均为逐频点复数运算，乘法不是 dB 相加。

## 1. 模块边界与整体流程

| 阶段 | 入口 / 代码 | 主要输出 |
| --- | --- | --- |
| 校准混频器表征 | [characterization.py](characterization.py)：`characterize()` | 有效四参数 C11、C22、互易假设下 C12=C21，及两轮 SOL 诊断 |
| 标准求值 / SOL | `sample_standard()`、`solve_sol()` | 在实际频率求值的标准反射及 D / S / R |
| 输入误差盒消除 | `mobius()`、`continuous_root()` | 混频器反射、传输乘积和连续开方 |
| VMC 误差项计算 | [vmc_calibration.py](vmc_calibration.py)：`calibrate()` | 21 条复数误差项、频率映射和追溯记录 |
| MUT 误差补偿 | `correct_reflection()`、`calibrate_mut()` | S11、S22、VC21；S12 为未校准零占位 |
| 频率映射 | [frequency_mapping.py](frequency_mapping.py)：`output_frequencies()` | 成对 RF / IF 频点 |
| 文件与展示适配 | `save_calibration()`、`load_calibration()`、`export_mut()`、`term_dataset()` | 校准包、MUT 结果包、误差项曲线数据 |

调用顺序：先表征校准混频器并导出 S2P，再以该定义与 SOL / 普通 THRU / CalTHRU raw 求误差项，最后用同一校准包修正 MUT raw。已知完整校准混频器定义时可直接从第二阶段开始。

GUI 在 `characterize_gui.py` / `vmc_calibration_gui.py` 收集配置并调用后台 worker；数学公式集中在上述核心模块，页面切换不产生另一套算法。

## 2. 符号、频率与数据层级

| 符号 | 含义 |
| --- | --- |
| m / SMij | 原始、未补偿的复数测量比值 |
| Gamma（Γ） | 已定义的标准反射系数 |
| D / EDF | 一端口方向性 |
| S / ESF | 一端口源匹配；此处 S 不是四参数矩阵 |
| R / ERF | 一端口反射跟踪；不是单程传输系数 |
| Cij | 已表征网络的有效参数；普通 THRU 和校准混频器分别使用自己的 C |
| ELF / ELR | 正向 / 反向负载匹配 |
| ETF / ETR | 正向 / 反向传输跟踪 |
| VC21 | MUT 校准后的正向有效变频传输系数 |

### 2.1 频率映射

固定正 LO 下：

\[
f_{IF}=f_{RF}+f_{LO}\quad(\texttt{up}),\qquad
f_{IF}=f_{RF}-f_{LO}\quad(\texttt{down}).
\]

下变频要求所有 RF>LO。当前两种模式都属于非反转分支；不支持 LO−RF，不用 abs(RF−LO) 替代，也不隐式共轭或重排采样。

表征阶段以第一份测量文件的 RF 网格为准；六份网格须逐行一致且严格递增。VMC 误差项阶段由 `CalibrationOptions` 的 RF 起止及点数生成 `linspace`，在每份原始文件中做容差内唯一匹配。

### 2.2 两种“六份文件”不可混淆

| 用途 | 文件构成 | 读取规则 |
| --- | --- | --- |
| 两轮 SOL 表征 | input_open / input_short / input_load / output_open / output_short / output_load | 六份都读取 S11，横轴都为 RF；第二轮是从输入端观测输出端标准负载的反射 |
| 默认 VMC Dummy DUT 流程 | open_raw / short_raw / load_raw / thru_raw / cal_mixer_raw / mut_raw | 前五份用于 `calibrate()`，mut_raw 用于随后 `calibrate_mut()`；另需标准定义和已表征校准混频器 |

第二轮表征文件中的 S11 不能被理解成在 IF 端直接测量的 S22；输出标准 Γ 应在映射 IF 求值，但该采集行仍是 RF 索引。

### 2.3 标准求值与原始测量匹配

`sample_standard()` 的历史键名与实际数学坐标如下：

| 配置键 | 实际行为 |
| --- | --- |
| `linear_ri` | 分别线性插值线性幅度 abs(Γ) 和解缠绕相位，再重构复数 |
| `cubic_ri` | 对上述两个坐标做 not-a-knot 三次样条，再重构复数 |

两者都不是实虚部插值，也不是 dB 插值。容差内命中单个标准节点时保留节点原值；多节点匹配拒绝；禁止外推。恒零 LOAD 保持零。需要插值时，非恒零标准含零幅度会因相位未定义而拒绝；样条出现负幅度会报错，不取绝对值或裁剪。

`parse_s1p()` 会排序标准定义并拒绝重复点；这是定义处理，不等于允许重排原始测量。VMC `_Reader.measured()` 对 raw 只做唯一匹配，不插值；所有文件参考阻抗须与配置一致，不自动重归一化。

实现边界：VMC 原始 S1P 复用 `parse_s1p()`，因此也会先排序，再进入 `_Reader` 的递增检查；当前不能声称原始 S1P 的非递增文件顺序必被拒绝。原始 S2P 不经过这一步标准排序。此处记录实际行为，不改变本轮算法或解析器。

## 3. 共用一端口 SOL 核心

源码：`characterization.solve_sol(measured, gamma, max_condition)`。两个输入均为 `(N,3)`，三列按 OPEN、SHORT、LOAD 排列。

### 3.1 模型与线性化

\[
m=D+\frac{R\Gamma}{1-S\Gamma}.
\]

定义 B=R−DS，则：

\[
m=D+B\Gamma+S\,m\Gamma.
\]

每个频点构造三行方程：

\[
\begin{bmatrix}
1&\Gamma_O&m_O\Gamma_O\\
1&\Gamma_S&m_S\Gamma_S\\
1&\Gamma_L&m_L\Gamma_L
\end{bmatrix}
\begin{bmatrix}D\\B\\S\end{bmatrix}
=\begin{bmatrix}m_O\\m_S\\m_L\end{bmatrix},
\qquad R=B+DS.
\]

对应核心代码：

```python
matrix = np.stack((np.ones_like(gamma), gamma, measured*gamma), axis=-1)
abc = np.linalg.solve(matrix, measured[..., None])[..., 0]
d, b, s = abc.T
r = b + d*s
```

输出 `(d,s,r)`、每点条件数及三个标准最大回代残差。`R` 是反射跟踪；例如简单互易输入误差盒单程传输为 t 时，反射往返跟踪可为 t²，不能把 ERF 当作 t。

### 3.2 反射补偿

令 Δ=m−D：

\[
\Gamma_{corrected}=\frac{\Delta}{R+S\Delta}.
\]

`vmc_calibration.correct_reflection()` 实现如下：

```python
def correct_reflection(measured, d, s, r):
    delta = measured - d
    denom = r + s*delta
    _check_nonzero(denom, '反射校准')
    return delta / denom
```

`solve_sol()` 拒绝标准间复数距离小于 1e−12、非有限 / 超阈值条件数和小于 1e−14 的回代分母。默认条件数上限为 1e12，频率容差为 0.001 Hz；这些是当前数值防护参数，不是仪器精度指标。

## 4. 校准混频器两轮 SOL 表征

入口：`characterize(measurement_paths, standard_paths, options=Options())`。

### 4.1 输入与两轮求解

- measurement_paths：六份 S2P，固定顺序见第 2.2 节；仅 S11 参与求解。
- standard_paths：GUI 使用共用 OPEN / SHORT / LOAD 三份 S1P；API 兼容两轮各三份的六路径方式。
- 第一轮将标准求值到 RF，第二轮将标准求值到映射 IF；共用标准套必须覆盖两频段。
- `Options` 控制 LO、上下变频、求值方式、容差、条件数、第二轮层级和整体开方符号。API 默认 `standard_sampling='linear_ri'`，不要与 VMC `CalibrationOptions` 默认 `cubic_ri` 混淆。

两轮分别得到 `(D1,S1,R1)` 和 `(D2,S2,R2)`。第一轮是输入误差盒；第二轮 raw 对应“输入误差盒＋混频器／滤波器整体”的复合反射映射。

### 4.2 第二轮为 raw：Mobius 矩阵消除输入误差

对于上述一端口映射，定义：

\[
M(D,S,R)=\begin{bmatrix}R-DS&D\\-S&1\end{bmatrix},
\qquad m=\frac{M_{11}\Gamma+M_{12}}{M_{21}\Gamma+M_{22}}.
\]

令校准混频器有效反射映射为：

\[
g(\Gamma)=C_{11}+\frac{P\Gamma}{1-C_{22}\Gamma},
\qquad P=C_{12}C_{21}.
\]

raw 第二轮满足 M2 与 M1·MC 成比例。因此代码计算并归一化：

\[
\widetilde M_C=M_1^{-1}M_2,\qquad
M_C=\frac{\widetilde M_C}{(\widetilde M_C)_{22}}.
\]

源码使用 `np.linalg.solve`，不显式求逆：

```python
mix = np.linalg.solve(mobius(first), mobius(second))
mix /= mix[:, 1, 1][:, None, None]
c11 = mix[:, 0, 1]
c22 = -mix[:, 1, 0]
product = mix[:, 0, 0] - mix[:, 0, 1]*mix[:, 1, 0]
```

以上为带归一化含义的核心摘录；实际函数在除法前检查矩阵条件数和归一化分母。

为便于审查，与该矩阵运算等价的标量表达为：

\[
Q=R_1+S_1(D_2-D_1),
\]

\[
C_{11}=\frac{D_2-D_1}{Q},\qquad
C_{22}=S_2-\frac{S_1R_2}{Q},\qquad
P=\frac{R_1R_2}{Q^2}.
\]

这些标量公式是现有实现的等价说明，源码执行路径仍为 Mobius 矩阵消除。

### 4.3 第二轮已做第一轮校准：禁止重复消除

当 `options.second_round='corrected'` 时，第二轮求解直接得到：

\[
C_{11}=D_2,\quad C_{22}=S_2,\quad P=R_2.
\]

这条路径不会再计算 M1⁻¹M2。误把已修正数据标为 raw，会再次消除输入误差；误把 raw 标为 corrected，则残留输入误差。软件依靠显式配置，不自动猜测层级。

### 4.4 两条路径交叉诊断

raw 路径另将第二轮三个测量逐一用第一轮 D1/S1/R1 修正，再对输出标准求 SOL：

\[
g_k=\frac{m_{2,k}-D_1}{R_1+S_1(m_{2,k}-D_1)}.
\]

`solve_sol(g, gamma_output, ...)` 得到的 `(D,S,R)` 应与 `(C11,C22,P)` 相同。`Two_path_complex_difference` 记录两条提取路径每点最大复数差；这是内部一致性诊断，不代替独立正向模型和厂商验证。

### 4.5 互易假设与连续开方

反射测量只确定 P，不分别识别 C12 和 C21。当前采用 C12=C21 的互易假设：

\[
C_{12}=C_{21}
=\sigma\sqrt{|P|}\exp\left(\frac{j}{2}\operatorname{unwrap}(\arg P)\right),
\quad \sigma\in\{+1,-1\}.
\]

```python
def continuous_root(product, sign=1):
    if sign not in (-1, 1):
        raise ValueError('传输开方符号必须为 +1 或 -1。')
    return sign*np.sqrt(np.abs(product))*np.exp(.5j*np.unwrap(np.angle(product)))
```

`root_sign` 只允许全局 ±1，不逐点选择主值开方，也不拟合相位。稀疏采样可能导致传输乘积相位混叠，连续开方不能保证恢复真实分支；整体符号需要独立参考。改变全局符号会同时翻转表征 C12/C21，乘积不变，但 C21 的符号会影响 VMC_ETF 及最终 VC21 的绝对相位，因此不能用曲线相似代替符号确认。P 接近零时发出相位 / 分支不可靠警告。

结果为混频器＋滤波器整体参考面的有效参数，输入误差盒已消除；不声称拆出了独立混频器或滤波器。输出 S2P 横轴为 RF，并附 InputFreq / OutputFreq / LO 映射与互易假设说明。

## 5. VMC 校准误差项求解

入口：`calibrate(inputs, options=CalibrationOptions())`。

默认配置：RF 10～20 GHz、201 点、固定 LO 20 GHz、上变频 IF 30～40 GHz、50 Ω、幅相三次样条、`raw_axis='dual'`、`mixer_definition_axis='rf'`。

### 5.1 四组 SOL：12 条误差项

按 `GROUPS=('P1_RF','P1_IF','P2_RF','P2_IF')` 循环：

| 组 | 频率 | 原始 S2P 读取参数 | 标准定义 |
| --- | --- | --- | --- |
| P1_RF | RF | S11 | P1 OPEN / SHORT / LOAD，在 RF 求值 |
| P1_IF | IF | S11 | P1 标准，在 IF 求值 |
| P2_RF | RF | S22 | P2 标准，在 RF 求值 |
| P2_IF | IF | S22 | P2 标准，在 IF 求值 |

每组求 EDF、ESF、ERF，共 4×3=12 条。独立 raw S1P 的唯一反射列表示所选物理端口；其列名 S11 不表示只能给 P1 使用。两端可配置不同标准和不同测量路径，默认 `shared_inputs()` 共用三份标准和三份 SOL raw。

### 5.2 普通同频 THRU：RF / IF 各四条

每个频段读取普通 THRU 四个原始参数 m11/m21/m12/m22。THRU 定义为 C；未提供定义时采用理想 Flush：C11=C22=0、C12=C21=1，即零延迟、零损耗。

先用对应频段 P1 / P2 SOL 修正两个反射：

\[
g_1=\operatorname{correct\_reflection}(m_{11},D_{P1},S_{P1},R_{P1}),\qquad
g_2=\operatorname{correct\_reflection}(m_{22},D_{P2},S_{P2},R_{P2}).
\]

令 Δ1=g1−C11、Δ2=g2−C22、P=C12C21，则：

\[
ELF=\frac{\Delta_1}{P+C_{22}\Delta_1},\qquad
ELR=\frac{\Delta_2}{P+C_{11}\Delta_2}.
\]

令 SF=P1_band_ESF、SR=P2_band_ESF：

\[
F_F=1-C_{11}SF-C_{22}ELF+(C_{11}C_{22}-C_{12}C_{21})SF\,ELF,
\]

\[
F_R=1-C_{22}SR-C_{11}ELR+(C_{11}C_{22}-C_{12}C_{21})SR\,ELR,
\]

\[
ETF=\frac{m_{21}F_F}{C_{21}},\qquad
ETR=\frac{m_{12}F_R}{C_{12}}.
\]

允许已定义 THRU 为非理想、非互易四参数网络，不将 C12 默认替换为 C21。Flush 特例中 ELF=g1、ELR=g2，ETF=m21·(1−SF·ELF)、ETR=m12·(1−SR·ELR)；raw THRU 仍包含测量误差，不是理想定义本身。

保留 RF_ELF / ELR / ETF / ETR 和 IF_ELF / ELR / ETF / ETR 共 8 条。**源匹配 ESF 与负载匹配 ELF 不默认相等。**

### 5.3 变频 CalTHRU：第 21 条 VMC_ETF

此节 C 指已表征校准混频器，m21 指该混频器接入测量系统后的原始正向变频测量。取：

\[
SF=P1\_RF\_ESF,\qquad LF=IF\_ELF.
\]

完整失配因子：

\[
F_{cal}=(1-C_{11}SF)(1-C_{22}LF)-C_{12}C_{21}SF\,LF.
\]

于是：

\[
\boxed{VMC\_ETF=\frac{S_{M21}^{cal}}{C_{21}}F_{cal}}.
\]

源码：

```python
sf = terms['P1_RF_ESF']
lf = terms['IF_ELF']
den = (1-c['S11']*sf)*(1-c['S22']*lf) - c['S12']*c['S21']*sf*lf
terms['VMC_ETF'] = m['S21']*den/c['S21']
```

展开后交叉项是 `(C11*C22−C12*C21)*SF*LF`。此前公式中类似 `C11*C21−C21*C12` 的写法不对应当前代码；不能以 C11*C21 代替 C11*C22。

LF 使用普通 IF THRU 求得的 `IF_ELF`，不是 `P2_IF_ESF`。`RF_ETF` 和 `IF_ETF` 是普通同频跟踪，`VMC_ETF` 是 RF→IF 的变频跟踪，三者不混用。

当前此步骤数值上使用 CalTHRU raw 的 S21；raw S11/S12/S22 仍随文件读取并参与格式 / 有限值 / dual 一致性检查，未被用于额外求解方向性或反向变频跟踪。校准混频器定义的四参数均参与失配因子，C12 可以非零。

### 5.4 21 条误差项与 MUT 使用关系

| 误差项组 | 数量 | 当前 MUT 公式使用 |
| --- | --- | --- |
| P1_RF_EDF / ESF / ERF | 3 | S11 反射修正；ESF 还进入 VC21 |
| P1_IF_EDF / ESF / ERF | 3 | 保留，不直接用于当前 MUT 单向修正 |
| P2_RF_EDF / ESF / ERF | 3 | 保留，不直接用于当前 MUT 单向修正 |
| P2_IF_EDF / ESF / ERF | 3 | S22 反射修正 |
| RF_ELF / ELR / ETF / ETR | 4 | 保留，不直接用于当前 MUT 单向修正 |
| IF_ELF / ELR / ETF / ETR | 4 | 其中 IF_ELF 进入 VC21 |
| VMC_ETF | 1 | VC21 传输跟踪补偿 |
| 合计 | 21 | 求得 21 条不等于完成全双向 MUT 校准 |

`term_dataset()` 将单条误差项放在显示 Dataset 的 S21，其余三参数填零；它是标量曲线适配，不是物理四参数网络。IF 组 StimulusFreq 为实际 IF，其他组及 VMC_ETF 为 RF。

## 6. MUT 误差补偿：校准 MUT

入口：`calibrate_mut(cal, path, raw_axis=None)`。先验证校准包，再按 RF / IF 映射读取 MUT raw。raw_axis 可覆盖新 MUT 的编码方式，不改变已经计算的误差项。

### 6.1 校准反射

\[
S_{11}^{MUT}=\frac{S_{M11}^{MUT}-P1\_RF\_EDF}
{P1\_RF\_ERF+P1\_RF\_ESF(S_{M11}^{MUT}-P1\_RF\_EDF)},
\]

\[
S_{22}^{MUT}=\frac{S_{M22}^{MUT}-P2\_IF\_EDF}
{P2\_IF\_ERF+P2\_IF\_ESF(S_{M22}^{MUT}-P2\_IF\_EDF)}.
\]

这两个结果是后续失配因子的输入。不能把 raw S11 / raw S22 代入校准后的反射位置。

### 6.2 校准正向变频传输

\[
\boxed{VC_{21}^{MUT}=\frac{S_{M21}^{MUT}
(1-S_{11}^{MUT}P1\_RF\_ESF)
(1-S_{22}^{MUT}IF\_ELF)}{VMC\_ETF}}.
\]

源码核心：

```python
c11 = correct_reflection(m['S11'], t['P1_RF_EDF'], t['P1_RF_ESF'], t['P1_RF_ERF'])
c22 = correct_reflection(m['S22'], t['P2_IF_EDF'], t['P2_IF_ESF'], t['P2_IF_ERF'])
vc21 = m['S21']*(1-c11*t['P1_RF_ESF'])*(1-c22*t['IF_ELF'])/t['VMC_ETF']
```

MUT 校准公式只有两个乘积失配因子，**没有**校准混频器求 ETF 时的 `−C12*C21*SF*LF` 项。这是当前已批准的单向／忽略反向耦合模型边界，不是遗漏某条代码后可以据此声称完整双向修正。

raw S21 保留为 `SM21_raw`，校准结果 S21 列代表 VC21，辅助字段另保存 VC21。S12 输出为零并标记“未校准，占位零”，不表示实际反向传输为零。S11 / S22 单端口修正也不代表有明显反向耦合时已完成全网络去嵌。

### 6.3 适用范围

当前未独立采集 isolation、switch terms 或 receiver ratios，传输泄漏假设为零。适用的是当前测量比值、标准定义和单向 MUT 模型；不据此保证全部 Keysight VMC 模式的系数约定一致。

校准混频器本身可有非零反向传输，ETF 求解保留其完整交叉项；这与 MUT 采用受限修正是两个不同阶段。存在明显双向 DUT 耦合、接收机比值差异、非零泄漏或开关项时，需要额外模型 / 输入及独立验证，本代码未覆盖。

## 7. 文件横轴、数值保护与追溯

### 7.1 VMC `_Reader` 的三种 raw 横轴

| raw_axis | 配对含义 |
| --- | --- |
| `rf` | 四参数都按 RF 频率行匹配；每行代表成对 RF→IF 响应 |
| `if` | 四参数都按 IF 行匹配；每行仍代表同一 RF→IF 响应 |
| `dual` | RF / IF 两段不重叠，两段对应四参数数值一致，校验后使用 RF 段 |

`dual` 一致性用 `rtol=1e−10, atol=1e−12`；两频段重叠报错。双频段复制是文件编码约定，不是普通同频 S2P 自动执行频率转换。

已表征混频器的 `mixer_definition_axis` 只允许 rf / if；四参数均按同一成对索引轴求值，不将 C11 / C22 另行当作互不对应的两份普通网络采样。

### 7.2 防护及默认值

- `_axes()`：RF 起止、阻抗、容差、条件数须有效；点数为 2～200001 整数，IF 为正有限值。
- `_Reader.measured()`：每个目标点容差内恰好一个 raw 节点，且目标映射不能重复使用同一节点。
- VMC `_check_nonzero()`：要求有限且绝对值不小于 1e−12，用于 ERF、反射修正分母、普通 THRU / CalTHRU 分母及传输跟踪等。
- 表征阶段第一轮矩阵条件数超限报错；归一化元素绝对值小于矩阵最大元素的 1e−14 倍时报错；第一轮反射修正分母小于 1e−14 报错。
- `continuous_root()` 对 |P|<1e−14 发出不可靠警告；表征结果及 MUT VC21 均检查非有限值。

上述门限在代码中针对不同计算分别使用，不能概括为一个统一“相对容差”；也不能解释为硬件误差规格。

### 7.3 输出及追溯边界

| 对象 | 文件 / 内容 |
| --- | --- |
| 表征结果 | `characterized_mixer.s2p`、可用时自研 S2PX、`sol_diagnostics.csv`、`characterization_report.json` |
| VMC 校准包 | ZIP：`calibration.json`、无 pickle 的 `arrays.npz`、`error_terms.csv` |
| MUT 结果包 | ZIP：`calibrated_mut.s2p` / CSV、raw CSV、频率映射、`report.json` |

Touchstone 四参数输出顺序为 S11 / S21 / S12 / S22，使用 Hz / S / RI。MUT CSV 保留 S11 / VC21 / S22 的复数坐标；文件注释明确未校准 S12。

校准包 `_validate_calibration()` 检查 schema、配置频率、精确 21 项集合、形状及有限值；保存时记录数组 SHA256，载入时验证哈希，`np.load(...,allow_pickle=False)`。VMC 校准包和 MUT 结果包通过临时文件＋`os.replace()` 原子发布。

VMC `_Reader.read()` 每条路径只读一次，解析和源 SHA256 来自同一字节快照。**两轮表征 `characterize()` 当前是先读取 / 解析，建立 manifest 时又读取源路径计算 SHA256，尚非同一字节快照；表征 `export_bundle()` 也直接写 ZIP，未采用 VMC 的原子发布函数。** 不应在说明中把后两者描述为已经具有同等保证。

本次只记录上述真实实现，不改动文件 I/O 或算法。正式追溯使用时应保持源文件稳定，并在需要时独立修复 / 验证这些边界。

## 8. API 使用关系示例

下面展示接口连接方式；文件路径为示例，执行前需准备满足频率和层级要求的实际数据。两轮表征输入与 VMC 默认六文件不相同。

```python
from characterization import Options, characterize, export_s2p
from vmc_calibration import (
    CalibrationOptions, shared_inputs, calibrate, calibrate_mut,
    save_calibration, export_mut,
)

standards = ['open.s1p', 'short.s1p', 'load.s1p']
measurements = [
    'input_open.s2p', 'input_short.s2p', 'input_load.s2p',
    'output_open.s2p', 'output_short.s2p', 'output_load.s2p',
]
characterization = characterize(measurements, standards, Options(
    lo_hz=20e9, frequency_conversion='up', second_round='raw',
    standard_sampling='cubic_ri', root_sign=1,
))
export_s2p(characterization, 'calibration_mixer.s2p')

inputs = shared_inputs(
    standards,
    ['open_raw.s2p', 'short_raw.s2p', 'load_raw.s2p'],
    'thru_raw.s2p', 'calibration_mixer.s2p', 'cal_mixer_raw.s2p',
)
options = CalibrationOptions(
    rf_start_hz=10e9, rf_stop_hz=20e9, points=201, lo_hz=20e9,
    frequency_conversion='up', raw_axis='dual',
    mixer_definition_axis='rf', standard_sampling='cubic_ri',
)
cal = calibrate(inputs, options)
save_calibration(cal, 'vmc_calibration.zip')
mut = calibrate_mut(cal, 'mut_raw.s2p')
export_mut(mut, 'mut_calibrated.zip')
```

此例使用理想 Flush THRU；实际 THRU 非零长度 / 损耗时，应在 `shared_inputs(..., thru_definition=...)` 提供完整定义。整体开方符号 +1 仅为示例选择，不等于绝对符号已由反射数据确定。

## 9. 现有验证代码与审查顺序

| 测试文件 | 主要证据 |
| --- | --- |
| [tests/test_characterization.py](tests/test_characterization.py) | 独立波量输入、非理想标准、连续开方、全局符号、raw / corrected 不重复修正、导出 / 频率 / 阻抗 / 病态输入 |
| [tests/test_frequency_conversion.py](tests/test_frequency_conversion.py) | 上下变频及非法映射输入 |
| [tests/test_shared_kit_sampling.py](tests/test_shared_kit_sampling.py) | 幅相求值、精确节点、零幅度及边界检查 |
| [tests/test_vmc_calibration.py](tests/test_vmc_calibration.py) | 独立波量构造、上下变频、三种横轴、非互易 defined THRU、非对称端口误差、21 项、MUT、包 / 异常检查 |
| [tests/test_vmc_simulation.py](tests/test_vmc_simulation.py) | 独立正向闭式参考、生成 / 校准闭环、噪声、真值与文件追溯 |

审查时优先核对标准求值和频率映射，再核对 SOL、表征层级、普通 THRU、VMC ETF 和 MUT 因子。

判断 Keysight VC21 差异时，按以下顺序保留证据：

1. 标准 / raw / 表征文件身份、SHA256 和参数列顺序；两轮表征 raw / corrected 层级。
2. RF / IF / LO、raw 编码、阻抗、标准求值、Flush / defined THRU 和参考面。
3. 校准混频器 C11/C22/C21/C12、开方符号，以及 P1_RF_ESF 和 IF_ELF。
4. 展开后的完整 CalTHRU 失配因子与 VMC_ETF；禁止把普通 RF / IF ETF 误用为变频 ETF。
5. MUT 补偿使用的是已校准反射还是 raw 反射，及仪器与自研数据的接收机 / 开关项 / 泄漏层级。

S11 / S22 对上不能单独证明 VC21 跟踪、负载匹配或混频器表征完全一致。本文不宣称此前 Keysight VC21 差异已解决；需要同一组真实输入与明确的厂商数据约定。现有数值 / 离屏测试也不代表 Windows 或 PNA-X 现场验证。

本次文档核对：71 项现有数值 / 文件测试通过，文档链接与 Python 摘录语法检查通过，Mobius 标量等价式已与源码矩阵路径核对。本次未重跑 GUI 或执行仪器现场验证。
