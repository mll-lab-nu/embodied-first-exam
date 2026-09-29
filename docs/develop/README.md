# 开发文档

当前阶段先建设 simulator 核心。agent/API 暂缓；13/13 基础任务及两个公共机制已通过 CUDA 短程实测，报告与真实录像见下方记录。

- [基础环境实现、实测结果与录像](dev-logs/simulator_base_runtime_implementation_zh.md)：当前运行和回溯状态以此记录及 runs/test_results 为准。
- [最新恢复与基础运行计划](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_base_task_runtime_plan_zh.md)：恢复 textures/fem、接回 Blanket 纹理；规划所有 13 个 base 的生命周期、FEM/IPC 回溯与跨任务一致性测试。
- [本轮精简：无调用脚本、唯一 compact_lab 与资产工具归并](dev-logs/simulator_simplification_20260923_zh.md)：当前目录和机器人默认值以此为准。
- [本轮 13 项任务接入与缺口](dev-logs/simulator_task_integration_20260923_zh.md)：上一阶段接入记录，保留当时的缺口；后续实测状态见最新记录。
- [整理计划与实施目标](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_structure_followup_plan_zh.md)：13 项基础任务统一接入；任务变体、现有双臂/单臂机器人、Sensors/Camera、PBD/FEM/IPC、历史 reset 与 planning 目录整改。
- [2026-09-23 核心重构记录](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_core_consolidation_20260923_zh.md)：实际模块、任意已有状态 reset、任务状态及能力边界。
- [逐测试脚本说明](dev-logs/simulator_test_scripts_zh.md)：23 个测试脚本的目的、真实物理与夹具的区别。
- [全项目脚本清单](../../legacy/cleanup_20260929/docs/develop/dev-logs/script_inventory_zh.md) · [历史源码完整附录](../../legacy/cleanup_20260929/docs/develop/dev-logs/script_snapshots_inventory_zh.md)
- [当前模块职责](modules/README.md) · [开发分析记录索引](dev-logs/README.md)
- [原收敛计划](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_consolidation_plan_zh.md) · [原验收计划](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_validation_plan_zh.md)：保留设计依据，当前范围以本轮任务接入记录为准。
- [命名语义审计](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_naming_audit_zh.md) · [首次目录迁移](../../legacy/cleanup_20260929/docs/develop/dev-logs/structure_move_20260923_zh.md)：历史问题与路径映射，不是当前接口文档。

已有的[任务说明](tasks/README.md)、[demo 进度](../progress/current_zh.md)、[rollout 手册](../../legacy/cleanup_20260929/docs/develop/modules/agent_rollout_usage_zh.md)和[旧 HDF5 格式](../../legacy/cleanup_20260929/docs/develop/data_pipeline/h5_data_format_zh.md)保留为历史资料；其中 CLI、import、成功结论和数据格式不能直接套用于新核心。
