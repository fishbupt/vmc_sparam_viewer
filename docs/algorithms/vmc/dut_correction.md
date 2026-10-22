# 被测混频器误差补偿（校准 MUT）

**入口：** [vmc/dut_correction.py](../../../vna_workbench/calibration/vmc/dut_correction.py) → `calibrate_mut()`。

## 1 反射校准

**函数：** [core/sol.py](../../../vna_workbench/core/sol.py) → `correct_reflection()`。

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

## 2 正向变频传输校准

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


## 3 高边 LO：输入参考的 VC21

**函数：** `calibrate_mut()` 的 `inverted` 分支。物理 S11/S22 的反射校准不变。

\[
VC_{21}=\frac{(S_{M21})^*(1-S_{11}ESF_{RF})(1-S_{22}ELF_{IF})^*}{ETF}.
\]

```python
sm21 = m['S21'].conj()
load_factor = (1-c22*t['IF_ELF']).conj()
vc21 = sm21*(1-c11*t['P1_RF_ESF'])*load_factor/t['VMC_ETF']
```

输出 VC21 为输入参考等效传输，零 LO 相位规范下的物理正向转换系数为 `conj(vc21)`。仍采用单向／忽略反向耦合模型。
