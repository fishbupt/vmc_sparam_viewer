# 固定 LO 的频率转换

**函数：** `vna_workbench/core/frequency_conversion.py` → `output_frequencies()`、`is_inverting()`。

\[
f_{IF}=\begin{cases}
f_{RF}+f_{LO}&\texttt{up}\\
f_{RF}-f_{LO}&\texttt{down},\ f_{RF}>f_{LO}\\
f_{LO}-f_{RF}&\texttt{high_side},\ f_{LO}>f_{RF}
\end{cases}
\]

`high_side` 的 IF 按 RF 点序递减。`output_frequencies()` 只映射频率，不排序或共轭。

**函数：** `characterize()` 的标准求值循环。

\[
\Gamma_{used,1}=\Gamma(f_{RF}),\qquad
\Gamma_{used,2}=\begin{cases}\Gamma(f_{IF})^*&\texttt{high_side}\\\Gamma(f_{IF})&\text{其他}\end{cases}
\]
