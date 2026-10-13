# 固定 LO 的频率转换

**函数：** [core/frequency_conversion.py](../../../vna_workbench/core/frequency_conversion.py) → `output_frequencies()`。

\[
f_{IF}=f_{RF}+f_{LO}\quad(\texttt{up}),\qquad
f_{IF}=f_{RF}-f_{LO}\quad(\texttt{down}).
\]

```python
ifreq = rf - lo_hz if conversion == 'down' else rf + lo_hz
```

下变频要求 RF>LO；当前不支持 LO−RF 反转分支，不用绝对值替代，不自动共轭。
