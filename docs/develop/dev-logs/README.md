# 开发分析与重构记录

2026-09-29：本目录历史记录涉及的独立研究、诊断与测试入口已按用户授权移入
[统一归档](../../../legacy/research_tools_20260929/README.md)。历史操作命令不作为当前入口；
原路径可通过归档 `manifest.json` 查询，当前入口见 [scripts/README](../../../scripts/README.md)。

- [Scripted policy 调度与方块 rollout 实施记录](scripted_policy_execution_implementation_20260926_zh.md)：用户已授权本地被动策略实现与真实 Genesis/Nyx 验收；源码迁入 rollout_simulation，输出遵循 task_rollouts 下的实验／任务／rollout 层级。下文的暂停记录保留原日期，不适用于本次已授权验收。

- [Task成功判据、四种操作模式与可解性验证计划](task_success_control_and_solvability_plan_20260924_zh.md)：逐项核对13任务；Coil保留两件分离初态、以操作拼装完成为目标，规划零奖励占位、统一成功规则、共享机械臂操作及可重复的机器人成功见证；本轮仅文档，GPU继续暂停。

当前方向：仅 Genesis，先统一 simulator 核心及本地公共接口；agent/网络 API 延期。上一阶段13/13基础任务及两个公共机制已有 CUDA 短程实测和真实录像；其证据不等于新权限合同或最新场景已验收。本轮 GPU 验收现按用户要求暂停，优先让场景会话运行。

- [默认场景预设恢复计划与 demo 参考截图](scene_preset_restoration_20260924_zh.md)：解释成功判据缺口、材质/夹具/布局迁移遗漏，核查 Horseshoe 自由环，并列出九项场景目标、文件清单、目录与验收计划；当前仅文档及参考截图。

- [公共接口实施、脚本坐标与当前结构](simulator_public_api_implementation_20260924_zh.md)：接口实施完成；174项非引擎测试、16控制/观察组合、两种相机和ALOHA G2通过；Panda G2及其余验收未完成，附失败/中断证据与恢复命令。
- [公共接口、特权回溯与验证实施计划](simulator_public_api_and_validation_plan_20260924_zh.md)：最新要求；普通 reset 与特权 rewind 分离、回溯后旧未来失效、全随机源 seed 控制、EE/JOINT 模式、4/3 路相机、G2 必做；逐脚本列开发与测试内容，实际结果见本轮实施报告。
- [核心接口、状态历史与相机验收缺口](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_core_readiness_audit_20260924_zh.md)：162 项当前用例的证据核对、26 项缺少通过记录、tick/分支回溯语义、尚未落实的 4/3 相机配置与八组后续验收。
- [运行时统一 Nyx + compact_lab](simulator_nyx_runtime_20260923_zh.md)：运行时观测与录像共用 Nyx；历史 Rasterizer 结果与新的 Nyx 验证分别记录。

- [基础环境实现、实测结果与录像](simulator_base_runtime_implementation_zh.md)：FEM/IPC、完整回溯、永久连接、各任务测试和复现命令的当前记录。
- [两项共享功能恢复与 13 个基础 Task 运行计划](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_base_task_runtime_plan_zh.md)：纹理/FEM 已恢复及 Blanket 接线；保留当时的基础环境/完整回溯目标及测试缺口，该计划的实施进展见上方最新记录。
- [已删代码复核与 Variation 设计](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_deleted_code_review_and_variations_zh.md)：逐项复核 26 份原件，区分尚未接入与冗余；其中 textures/fem 已在后续恢复。
- [本轮精简：无调用脚本、唯一 compact_lab 与资产工具归并](simulator_simplification_20260923_zh.md)：当前目录和机器人默认值以此为准。
- [13 项任务接入与缺口](simulator_task_integration_20260923_zh.md)：实际目录、共享模块、逐任务缺口与测试状态；文件位置和默认值已由本轮精简更新。
- [后续整理计划：全部任务统一迁入 Genesis Simulator](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_structure_followup_plan_zh.md)：参考 RoboWits 分离任务变体，接入现有 ALOHA 双臂与 Panda+Robotiq 单臂、集中 Sensors/Camera，补齐 PBD/FEM/IPC 与回溯，统一 planning 命名；首个整体里程碑覆盖 13 项基础任务，已开始实施，阶段边界见上条记录。
- [核心重构记录](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_core_consolidation_20260923_zh.md)：上一阶段的代码布局、6 项定义与 7 项待迁移状态；保留历史依据。
- [逐测试脚本说明](simulator_test_scripts_zh.md)：当前全部测试脚本及公共证据支持，区分单元/合同与真实物理验证。
- [当前/延期脚本清单](../../../legacy/cleanup_20260929/docs/develop/dev-logs/script_inventory_zh.md) · [历史源码逐路径附录](../../../legacy/cleanup_20260929/docs/develop/dev-logs/script_snapshots_inventory_zh.md) · [完整机器可读清单](../../../legacy/cleanup_20260929/docs/develop/dev-logs/script_inventory_20260923.json)：由 `scripts/inventory_sources.py` 根据当前工作树生成。
- [原功能收敛计划](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_consolidation_plan_zh.md) · [原测试交付计划](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_validation_plan_zh.md)：设计依据；本轮实际范围及最新要求见任务接入记录。
- [命名语义审计](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_naming_audit_zh.md) · [审计时的名称索引](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_naming_inventory_zh.md)：记录整理前 adapter、Env、Task、状态、数据等语义问题。
- [第一次只移动文件的记录](../../../legacy/cleanup_20260929/docs/develop/dev-logs/structure_move_20260923_zh.md) · [旧路径映射](../../../legacy/cleanup_20260929/docs/develop/dev-logs/structure_move_files_20260923_zh.md) · [当时的哈希](../../../legacy/cleanup_20260929/docs/develop/dev-logs/structure_move_manifest_20260923.json)：历史快照，不是最终文件位置。
- [Genesis-only 分析](../../../legacy/cleanup_20260929/docs/develop/dev-logs/genesis_only_codebase_review_zh.md) · [旧 MuJoCo 依赖清单](../../../legacy/cleanup_20260929/docs/develop/dev-logs/mujoco_dependencies_zh.md) · [第一轮模块化审计](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_modularity_audit_zh.md)：旧问题证据与重构依据。

返回：[开发文档](../README.md) · [当前模块职责](../modules/README.md)。
