# v1.6.0 校准与校准 MUT 验证记录

日期：2026-10-10。环境：Linux / Python 3.12 / NumPy / SciPy / PyQt6；Qt 为 offscreen。

## 已完成检查

| 检查 | 结果 |
| --- | --- |
| 全部数值回归 | 62 项 unittest 通过；保留既有 47 项，新增 15 项 VMC 校准测试 |
| 新校准独立模型 | 显式四个内部波量方程构造原始测量；恢复四组 SOL、两频段负载匹配 / 传输跟踪和变频 ETF，最大复数差要求 <2e−14 |
| 组合覆盖 | 上 / 下变频 × RF / IF / dual 原始横轴 × Flush / defined Thru 共 12 组子用例；使用非对称误差盒、非理想 SOL 和非互易 defined Thru |
| 独立输入 | 12 组 S1P 采集、独立 Port2 定义路径、实际不同 Port2 标准响应 |
| 异常拒绝 | 丢失频点、Z0 不一致、非有限测量、双频段不一致、RF/IF 重叠的 dual 编码、零校准混频器 S21、非四参数表征 |
| 标准求值 | 两种幅相插值生效并记录插值点数；含 DC 节点的标准定义可使用 |
| 校准包 | 数组 / 配置 / 哈希验证；保存重载等值；删除标准定义源文件后仍能校准 MUT；篡改数组被拒绝 |
| MUT 导出 | S2P、VC21 复数 CSV、原始 CSV、RF / IF / LO 映射、报告；明确标记 S12 未校准 |
| 既有 GUI | 原有 SOL 生成、表征转接、噪声、设置和失效检查通过 |
| 新 GUI | 两页签名称、后台计算、输入禁用、主界面收到原始 / 校准结果、保存 / 重载 / 导出、设置保存和分级失效检查通过 |

命令：

```text
uv run python -m unittest discover -s tests -v
uv run python tests/gui_simulation_smoke.py
uv run python tests/gui_vmc_calibration_smoke.py
git diff --check
```

## 已生成的用户基线

单独用先前 `VMC_DummyDUT_RF10-20_IF30-40_baseline.zip` 的原始数据验证：RF=10～20 GHz，LO=20 GHz，IF=30～40 GHz，各201点；理想标准 / Flush、无噪声。

- 恢复21个复数误差项，校准包保存 / 重载成功。
- 单向 MUT 的 VC21 与真值最大复数差约 **3.6082e−16**。
- 校准混频器表征来自包内真值 CSV，参数与现有生成器一致。
- 此基线的用户文件没有新增提交到 examples，新增测试自建临时输入，不依赖该压缩包。

## 算法范围与未完成验证

1. 当前 MUT 公式按单向 / 忽略反向耦合计算；S12 不校准，结果文件零值为占位。不能将结果解释为完整双向 VMC 去嵌。
2. 普通 / 变频传输泄漏按零处理；没有独立采集 isolation、receiver ratio 或 switch terms。
3. 使用完整校准混频器分母，交叉项为 C11*C22−C12*C21；需结合 Keysight 实际导出的 ETF 核对其规范。
4. Windows / Keysight 仿真软件全量校准、CalSet 项目名称与原始波量规范、Dummy DUT 实际查表行为尚待用户对照。Qt offscreen 仅说明软件联动可运行，不证明仪器算法一致。
5. 主界面相位比较增强留给后续单独 commit，本次复用原有能力，没有新增“对比验证”页面。
