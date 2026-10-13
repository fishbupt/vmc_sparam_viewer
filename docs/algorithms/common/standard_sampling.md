# 标准求值

**函数：** [core/standard_sampling.py](../../../vna_workbench/core/standard_sampling.py) → `sample_standard()`。

令节点幅度和连续相位为：

\[
A_k=|\Gamma_k|,\qquad \theta_k=\operatorname{unwrap}(\arg\Gamma_k).
\]

目标频点 f 的求值为：

\[
\Gamma(f)=I_A(f)\exp[jI_\theta(f)].
\]

`linear_ri`：IA、Iθ 分别为线性幅度和解缠绕相位的线性插值；`cubic_ri`：分别为 not-a-knot 三次样条。键名保留兼容，不表示实虚部插值。精确节点保持原值。

```python
result[missing] = interpolated_magnitude * np.exp(1j*interpolated_phase)
```
