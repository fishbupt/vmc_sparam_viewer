# VMC 校准误差项计算

**入口：** [vmc/error_terms.py](../../../vna_workbench/calibration/vmc/error_terms.py) → `calibrate()`。

## 1 四组 SOL 误差项

对 P1_RF、P1_IF、P2_RF、P2_IF 分别调用 [共用 SOL](../common/sol.md) 的 `solve_sol()`：

\[
EDF=D,\qquad ESF=S,\qquad ERF=R.
\]

**对应代码：** `calibrate()` 的 `for group in GROUPS` 循环。每组三项，共 12 项。

## 2 普通 THRU 的负载匹配与传输跟踪

**函数：** [core/sol.py](../../../vna_workbench/core/sol.py) → `correct_reflection()`；[vmc/error_terms.py](../../../vna_workbench/calibration/vmc/error_terms.py) → `calibrate()` 的 RF / IF THRU 循环。

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

## 3 变频传输跟踪 VMC_ETF

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
