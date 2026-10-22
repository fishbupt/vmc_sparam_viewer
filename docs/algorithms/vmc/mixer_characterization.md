# 校准混频器表征

两轮 SOL 分别得到 `(D1,S1,R1)`、`(D2,S2,R2)`；公式见 [共用 SOL](../common/sol.md)。

## 消除第一轮输入误差

**函数：** [core/sol.py](../../../vna_workbench/core/sol.py) → `mobius()`；[vmc/mixer_characterization.py](../../../vna_workbench/calibration/vmc/mixer_characterization.py) → `characterize()` 的 `second_round == 'raw'` 分支。

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

## 从传输乘积求 C12、C21

**函数：** [vmc/mixer_characterization.py](../../../vna_workbench/calibration/vmc/mixer_characterization.py) → `continuous_root()`。

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

## 高边 LO 的物理量与等效量

**函数：** `core/frequency_conversion.py` → `phase_convention()`；`characterize()` 的 `inverted` 分支；`simulation/conjugate_waves.py` → `high_side_waves()`。

采用零 LO 相位规范，文件 S11/S22 为物理反射，S12/S21 为输入参考等效传输：


\[
b_1=S_{11}a_1+S_{12}a_2^*,\qquad
b_2=S_{21}^*a_1^*+S_{22}a_2.
\]

\[
\Gamma_{in}=S_{11}+\frac{S_{12}S_{21}\Gamma_L^*}{1-S_{22}^*\Gamma_L^*}.
\]

第二轮求解使用 `gamma[:, 3:] = conj(Gamma_IF)`；上述 Möbius 消除得到
\(C_{11}=S_{11}, C_{22}=S_{22}^*, P=S_{12}S_{21}\)。

```python
# 在两条提取路径交叉校验后，还原物理端口反射
if inverted:
    c22 = c22.conj()
transfer = continuous_root(product, options.root_sign)
```

第一轮标准和采集 S11 不共轭。`continuous_root()` 对等效互易网络开方；物理正向转换系数在本 LO 相位规范下为 `conj(transfer)`，绝对 LO 相位不由反射 SOL 确定。
