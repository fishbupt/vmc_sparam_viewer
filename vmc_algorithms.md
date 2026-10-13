# VMC 算法公式与代码对应

公式均为逐频点复数运算。m 为原始测量，Γ 为标准反射，D / S / R 分别为方向性、源匹配和反射跟踪；Cij 为校准网络的已表征参数。

## 1. 校准混频器表征

### 1.1 两轮 SOL

**函数：** [characterization.py](characterization.py) → `solve_sol()`；由 `characterize()` 分别调用得到两轮 `(D1,S1,R1)`、`(D2,S2,R2)`。

\[
m=D+\frac{R\Gamma}{1-S\Gamma}
=D+B\Gamma+S\,m\Gamma,\qquad R=B+DS.
\]

```python
matrix = np.stack((np.ones_like(gamma), gamma, measured*gamma), axis=-1)
abc = np.linalg.solve(matrix, measured[..., None])[..., 0]
d, b, s = abc.T
r = b + d*s
```

### 1.2 消除第一轮输入误差

**函数：** `characterization.py` → `mobius()`、`characterize()` 的 `second_round == 'raw'` 分支。

\[
M(D,S,R)=\begin{bmatrix}R-DS&D\\-S&1\end{bmatrix},\qquad
\widetilde M_C=M_1^{-1}M_2,\qquad
M_C=\frac{\widetilde M_C}{(\widetilde M_C)_{22}}.
\]

\[
C_{11}=(M_C)_{12},\qquad C_{22}=-(M_C)_{21},\qquad
P=C_{12}C_{21}=(M_C)_{11}-(M_C)_{12}(M_C)_{21}.
\]

```python
mix = np.linalg.solve(mobius(first), mobius(second))
mix /= mix[:, 1, 1][:, None, None]
c11, c22 = mix[:, 0, 1], -mix[:, 1, 0]
product = mix[:, 0, 0] - mix[:, 0, 1]*mix[:, 1, 0]
```

上述矩阵运算的等价标量公式为：

\[
Q=R_1+S_1(D_2-D_1),\qquad
C_{11}=\frac{D_2-D_1}{Q},\qquad
C_{22}=S_2-\frac{S_1R_2}{Q},\qquad
P=\frac{R_1R_2}{Q^2}.
\]

若第二轮已做第一轮修正，则直接使用：

\[
C_{11}=D_2,\qquad C_{22}=S_2,\qquad P=R_2.
\]

**对应代码：** `characterize()` 的 `second_round == 'corrected'` 路径：

```python
c11, c22, product = second
```

### 1.3 从传输乘积求 C12、C21

**函数：** `characterization.py` → `continuous_root()`。

反射 SOL 仅确定 P=C12C21；在互易假设 C12=C21 下：

\[
C_{12}=C_{21}=\sigma\sqrt{|P|}
\exp\left[\frac{j}{2}\operatorname{unwrap}(\arg P)\right],
\qquad \sigma=\pm1.
\]

```python
transfer = sign*np.sqrt(np.abs(product))*np.exp(.5j*np.unwrap(np.angle(product)))
```

`characterize()` 将 `transfer` 同时作为结果的 S12 和 S21。

## 2. VMC 校准误差项计算

**入口：** [vmc_calibration.py](vmc_calibration.py) → `calibrate()`。

### 2.1 四组 SOL 误差项

对 P1_RF、P1_IF、P2_RF、P2_IF 分别调用 `solve_sol()`：

\[
EDF=D,\qquad ESF=S,\qquad ERF=R.
\]

**对应代码：** `calibrate()` 的 `for group in GROUPS` 循环。每组三项，共 12 项。

### 2.2 普通 THRU 的负载匹配与传输跟踪

**函数：** `vmc_calibration.py` → `correct_reflection()`、`calibrate()` 的 RF / IF THRU 循环。

先校准 THRU 的两端反射：

\[
g_1=\frac{m_{11}-D_1}{R_1+S_1(m_{11}-D_1)},\qquad
g_2=\frac{m_{22}-D_2}{R_2+S_2(m_{22}-D_2)}.
\]

令 Δ1=g1−C11、Δ2=g2−C22、P=C12C21，其中 C 为普通 THRU 定义：

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
ETF=\frac{m_{21}F_F}{C_{21}},\qquad ETR=\frac{m_{12}F_R}{C_{12}}.
\]

**对应代码变量：** `lf / lr` 对应 ELF / ELR，`df / dr` 对应 FF / FR，`tf / tr` 对应 ETF / ETR。

RF、IF 各求四项，共 8 项。

### 2.3 变频传输跟踪 VMC_ETF

**对应代码：** `calibrate()` 中 `terms['VMC_ETF']` 的计算。

此处 C 为已表征校准混频器；取 SF=P1_RF_ESF、LF=IF_ELF：

\[
\boxed{VMC\_ETF=\frac{S_{M21}^{cal}}{C_{21}}
\left[(1-C_{11}SF)(1-C_{22}LF)-C_{12}C_{21}SF\,LF\right]}.
\]

```python
sf = terms['P1_RF_ESF']
lf = terms['IF_ELF']
den = (1-c['S11']*sf)*(1-c['S22']*lf) - c['S12']*c['S21']*sf*lf
terms['VMC_ETF'] = m['S21']*den/c['S21']
```

展开后的交叉项为 `(C11*C22−C12*C21)*SF*LF`。全部误差项数量为 12+8+1=21。

## 3. 被测混频器误差补偿（校准 MUT）

**入口：** `vmc_calibration.py` → `calibrate_mut()`。

### 3.1 反射校准

**函数：** `correct_reflection()`。

\[
S_{11}^{MUT}=\frac{S_{M11}^{MUT}-P1\_RF\_EDF}
{P1\_RF\_ERF+P1\_RF\_ESF(S_{M11}^{MUT}-P1\_RF\_EDF)},
\]

\[
S_{22}^{MUT}=\frac{S_{M22}^{MUT}-P2\_IF\_EDF}
{P2\_IF\_ERF+P2\_IF\_ESF(S_{M22}^{MUT}-P2\_IF\_EDF)}.
\]

```python
c11 = correct_reflection(m['S11'], t['P1_RF_EDF'], t['P1_RF_ESF'], t['P1_RF_ERF'])
c22 = correct_reflection(m['S22'], t['P2_IF_EDF'], t['P2_IF_ESF'], t['P2_IF_ERF'])
```

### 3.2 正向变频传输校准

**对应代码：** `calibrate_mut()` 中 `vc21` 的计算。

\[
\boxed{VC_{21}^{MUT}=\frac{S_{M21}^{MUT}
(1-S_{11}^{MUT}P1\_RF\_ESF)
(1-S_{22}^{MUT}IF\_ELF)}{VMC\_ETF}}.
\]

```python
vc21 = m['S21']*(1-c11*t['P1_RF_ESF'])*(1-c22*t['IF_ELF'])/t['VMC_ETF']
```

这里 c11、c22 是已校准反射，m['S21'] 是未补偿原始传输。该公式采用单向／忽略反向耦合模型；S12 未校准，输出零仅为占位。
