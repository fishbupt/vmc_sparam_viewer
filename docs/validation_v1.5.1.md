# v1.5.1 验证记录

日期：2026-10-09。Linux / Python 3.12 / Qt offscreen；未在 Windows / PNA 现场验证。

## 修改内容

标准件的线性求值改为对线性幅度与解缠绕相位分别插值：

```text
mag = abs(Gamma)
phase = unwrap(angle(Gamma))  # radians
Gamma(x) = interp(x, f, mag) * exp(j * interp(x, f, phase))
```

API / QSettings 的历史键 `linear_ri` 保留，但数值行为改变。GUI 显示“幅度 / 解缠绕相位”；JSON 和 S2P 注释记录实际坐标 `linear_magnitude_unwrapped_phase`。三次样条 `cubic_ri` 仍对实部 / 虚部求值，not-a-knot 边界。

## 已验证事实

- `python -m unittest discover -s tests -q`：44 项通过。
- `python tests/gui_simulation_smoke.py`：生成、方向联动、预览、结果失效、噪声 / 设置、演示重置和两处 GUI 线性插值文案检查通过。
- 新增已知解析幅相曲线测试：相位正 / 负方向跨 ±180° 及多圈变化，保持请求目标频率顺序，结果匹配解析值。
- 非恒幅跨 ±180° 用例：0.2∠170° 与 0.8∠−170° 的中点为 0.5∠180°，不等于复数笛卡尔平均，也不等于 dB 平均的幅度 0.4。
- 容差内精确节点直接保持原复数值；全部精确命中时不执行幅相重构。频带外目标拒绝外推。
- 恒零 LOAD 的两种求值都保持零；非恒零标准含零幅度且需要幅相线性插值时明确拒绝。全部精确命中的零节点直接保留；三次 RI 仍允许含零幅度标准。
- 上 / 下变频 × 两种插值的非理想标准闭环、独立波量正向模型、输出 IF / 记录 / 注释一致性和旧 Keysight 下变频三次样条回归继续通过。

## 边界与待验证

- 线性幅相结果与 v1.5.0 的 RI 线性结果可能不同；复现实验需同时记录版本及实际插值坐标。
- np.unwrap 根据相邻采样点恢复连续相位，不保证采样过稀时的真实相位分支。零幅度相位无法定义，不静默指定或跨越它解缠绕。
- 当前 Keysight 对照仍为已有下变频 cubic_ri 样本；不能据此声称新幅相线性就是 Keysight 的内部规则，或上变频 Keysight 对照已验证。
- Windows、真实仪器及完整校准套的外部验证尚待开展。
