# 一端口 SOL 求解

**函数：** [vna_workbench/core/sol.py](../../../vna_workbench/core/sol.py) → `solve_sol()`。

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


## 反射校准

**函数：** 同文件 `correct_reflection()`。

\[
\Gamma=\frac{m-D}{R+S(m-D)}.
\]

```python
def correct_reflection(measured, d, s, r):
    delta = measured - d
    denom = r + s*delta
    check_nonzero(denom, '反射校准')
    return delta / denom
```
