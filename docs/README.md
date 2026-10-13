# VNA 校准与验证工作台文档

| 分类 | 入口 | 内容 |
| --- | --- | --- |
| 架构 | [模块结构与迁移映射](architecture/module_structure.md) | 包边界、依赖方向、入口和旧文件映射 |
| 共用算法 | [SOL](algorithms/common/sol.md)、[标准求值](algorithms/common/standard_sampling.md)、[频率转换](algorithms/common/frequency_conversion.md) | 公式与代码 / 函数名 |
| VMC 算法 | [算法索引](algorithms/vmc/README.md) | 混频器表征、误差项求解及 DUT 校准 |
| 使用说明 | [VMC 操作](guides/vmc_calibration.md) | 输入文件、配置、执行与导出 |
| 验证记录 | [v1.9.0 结构回归](validation/releases/validation_v1.9.0.md) | 数值、GUI、入口、安装及结构检查 |
| 开发计划 | [通用路线图](plans/roadmap.md) | 未实现算法与工程任务 |

本分支的 [TRL 工作清单](plans/trl_worklist.md) 已按 v1.9.0 结构更新；TRL 算法仍未实现，不创建空的算法公式文档。

`validation/releases/` 保存各历史版本的真实验证记录。旧模块名和版本号保留当时语义；当前源文件路径和测试命令以架构说明及根目录 README 为准。
