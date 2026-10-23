# 高边 LO 验证流程

工作台 1.11.0，算法 / 报告 1.8.0。全局共享和五步操作见 [共享 VMC 流程](vmc_shared_workflow.md)。新增模式 `high_side`，IF=LO−RF，要求全部 RF<LO。原 up/down 含义不变。

## 第一步：验证校准混频器表征

1. 在“VMC 全局配置”点击“高边 LO 预设”，进入“1. 生成两轮 SOL”；测试时可勾选内置非理想 SOL。
2. 预设为 RF 10～15 GHz、LO 20 GHz、201 点、无噪声；IF 按点序为 10～5 GHz。预设保留已设置的混频器和误差盒参数。
3. 默认使用内置非理想 SOL：OPEN 幅度 0.98、反射延迟 18 ps；SHORT 幅度 0.96、初相位 180°、反射延迟 28 ps；LOAD 幅度 0.04、初相位 0.5 rad、反射延迟 12 ps。均按实际物理频率计算。这是合成验证套，不是 Keysight 的物理校准套。
4. 选择输出目录并生成。产出六个 SOL 原始测量 S2P、Mixer.s2p 真值、三个标准定义、CSV 和报告。
5. 两轮原始文件均以 RF 为横轴且只含有效 S11。标准 S1P 是物理定义，不要提前共轭；Keysight 和自研程序应使用同一套定义及 LO−RF 设置。
6. 点击“将本轮文件载入表征窗口”，计算后与 Mixer.s2p 和 Keysight 导出结果比较。

取消内置 SOL 后，可以导入共用实际 OPEN/SHORT/LOAD；标准频带须覆盖全部 RF 和 IF，不能外推。内置标准可以检出漏共轭，理想 +1/−1/0 标准不能。

## 第二步：验证 VMC 误差项和校准 MUT

1. 保持同一份全局配置，进入“3. 生成 VMC 原始测量 SNP”，可先从步骤 2 将已表征结果送入。
2. 预设选择 RF 横轴、内置非理想 SOL、Flush Thru、模型校准混频器、无噪声，保留模型参数。
3. 可勾选导入已表征校准混频器，并选择上一步的 Mixer.s2p（RF 横轴）；这样两阶段使用同一个混频器。
4. 生成 open_raw.s2p、short_raw.s2p、load_raw.s2p、thru_raw.s2p、cal_mixer_raw.s2p、mut_raw.s2p，以及标准定义、calibration_mixer.s2p、mut_truth.s2p 和报告。
5. 使用“将本轮文件载入 VMC 校准窗口”，计算误差项并校准 MUT。用主界面单文件查看 / 双文件比较检查结果。

RF 10～15 和 IF 10～5 GHz 在 10 GHz 接触，当前禁止 dual 编码；使用 RF 或 IF 横轴。若需要双频段复制，可改成 RF 11～15 GHz、IF 9～5 GHz。IF 横轴文件按 IF 递增写出，所有列同步重排；内部计算仍按 RF→IF 配对。两个频段的 dual 复制含同一噪声样本。

## 相位和文件约定

- S11、S22：各自物理频率下的端口反射。
- 表征文件 S21、S12 和 MUT 真值 VC21：输入参考等效传输。
- 原始 CalTHRU / MUT 文件 SM21：物理接收响应；校准计算将它共轭到输入参考。
- 因此高边模式下，raw SM21 与真值 VC21 的相位可能呈相反斜率，不能直接归因于误差盒。
- `high_side_phase_reference.csv` 同时提供等效 VC21 和零 LO 相位规范下的物理 K21=conj(VC21)，帮助与 Keysight 相位定义对照。不要为了吻合结果自动拟合或更改相位。
- 标准文件、原始测量、表征真值分别保存；普通 S2P 只承载数值，不自行执行变频。Keysight Dummy DUT 采用何种频率检索、参考混频器和相位处理，需外部对比确认。
- 校准包记录相位规范，读取高边 LO 校准包时校验；原非反转包仍兼容。
- 仍无 isolation / switch-term 独立采集，MUT 采用 S12=0 单向模型，不声明完整双向校准。

## 依据

- [Dunsmore、Hubert、Williams：Vector Mixer Characterization for Image Mixers](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=31630)
- 公式与实现对应见 [频率转换](../algorithms/common/frequency_conversion.md)、[混频器表征](../algorithms/vmc/mixer_characterization.md)、[误差项](../algorithms/vmc/error_terms.md)、[校准 MUT](../algorithms/vmc/dut_correction.md)。

目前已完成独立正向模型和数值恢复验证；未宣称 Keysight 仿真 / 真机验证通过。
