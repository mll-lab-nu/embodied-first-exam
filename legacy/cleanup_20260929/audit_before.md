# TopoGym 旧 Harbor 与研究中间产物盘点

核对日期：2026-09-29。范围：当前工作树（包括未提交文件与 ignored 产物），没有按 Git HEAD 回退。仅静态阅读、路径/引用核对与 Git ignore 检查；没有移动、删除或修改项目文件，没有运行仿真、测试或模型。此清单保存在 /tmp，供 review。

A = 已有明确退役或历史快照证据，可列入第一批归档候选；B = 历史研究/实施记录，仍有参考或追溯价值，归档需同步索引；C = 当前使用或混有当前依赖，保留或拆分。目录条目表示整棵目录，文档逐文件列出。

当前 Harbor 以 tasks/、images/、harbor_agents/、ci_checks/、docs/rcb/ 为准。legacy/harbor_20260929 与 legacy/harbor_native_20260929 已归档，无需再次移动。第一份 archive README 仍把 topogym/benchmark 当作替代实现，这是当时状态，09-29 下午第二次迁移已覆盖它。

## A1. 旧 Harbor 文档（12 篇及 5 个流程图源文件）

仍引用 harbor_runners、topogym.agents.rollout/usage、configs/harbor 或已退役的 topogym/benchmark。rcb_harbor_implementation 文首明确说明已移入 legacy/harbor_native_20260929；project_three_flows 包含仍有参考价值的本地 segment，但整套图描述的是旧三条流程。

| 路径 | Git 状态 |
|---|---|
| [docs/develop/modules/harbor_coding_agent_pipeline_guide_zh.md](/home/jianwen/topogym/docs/develop/modules/harbor_coding_agent_pipeline_guide_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/harbor_docker_delivery_and_runner_layout_zh.md](/home/jianwen/topogym/docs/develop/modules/harbor_docker_delivery_and_runner_layout_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/harbor_rollout_protocol_v1_draft_20260926_zh.md](/home/jianwen/topogym/docs/develop/modules/harbor_rollout_protocol_v1_draft_20260926_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/harbor_shared_image_pipeline_plan_20260925_zh.md](/home/jianwen/topogym/docs/develop/modules/harbor_shared_image_pipeline_plan_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/harbor_token_budget_design_20260927_zh.md](/home/jianwen/topogym/docs/develop/modules/harbor_token_budget_design_20260927_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/harbor_usage_implementation_and_gpu_tests_zh.md](/home/jianwen/topogym/docs/develop/modules/harbor_usage_implementation_and_gpu_tests_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/opencode_model_key_implementation_20260928_zh.md](/home/jianwen/topogym/docs/develop/modules/opencode_model_key_implementation_20260928_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/opencode_model_key_rollout_plan_20260928_zh.md](/home/jianwen/topogym/docs/develop/modules/opencode_model_key_rollout_plan_20260928_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/usage_pipeline_agent_adapters_plan_20260928_zh.md](/home/jianwen/topogym/docs/develop/modules/usage_pipeline_agent_adapters_plan_20260928_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/rcb_harbor_migration_plan_20260929_zh.md](/home/jianwen/topogym/docs/develop/modules/rcb_harbor_migration_plan_20260929_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/rcb_harbor_implementation_20260929_zh.md](/home/jianwen/topogym/docs/develop/modules/rcb_harbor_implementation_20260929_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/project_three_flows_20260928_zh.md](/home/jianwen/topogym/docs/develop/modules/project_three_flows_20260928_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/project_three_flows_20260928/01_segment.mmd](/home/jianwen/topogym/docs/develop/modules/project_three_flows_20260928/01_segment.mmd) | 未跟踪、未 ignore |
| [docs/develop/modules/project_three_flows_20260928/01_segment_teaser.mmd](/home/jianwen/topogym/docs/develop/modules/project_three_flows_20260928/01_segment_teaser.mmd) | 未跟踪、未 ignore |
| [docs/develop/modules/project_three_flows_20260928/02_cli_teaser.mmd](/home/jianwen/topogym/docs/develop/modules/project_three_flows_20260928/02_cli_teaser.mmd) | 未跟踪、未 ignore |
| [docs/develop/modules/project_three_flows_20260928/02_harbor_session.mmd](/home/jianwen/topogym/docs/develop/modules/project_three_flows_20260928/02_harbor_session.mmd) | 未跟踪、未 ignore |
| [docs/develop/modules/project_three_flows_20260928/03_prepare_experiment.mmd](/home/jianwen/topogym/docs/develop/modules/project_three_flows_20260928/03_prepare_experiment.mmd) | 未跟踪、未 ignore |

## A2. 更早的 agent bridge / rollout / adapter 材料（17 篇）

这些文档对应 topogym/agent_bridge、topogym/agent_rollout、旧 task agent_adapter/agent_spec 等入口，相关实现已延期或归档。当前 Harbor 使用 docs/rcb。

| 路径 | Git 状态 |
|---|---|
| [docs/develop/modules/agent_adapter_architecture_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_adapter_architecture_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_bridge_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_bridge_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_rollout_pipeline_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_rollout_pipeline_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_rollout_segments_v1_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_rollout_segments_v1_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_rollout_target_gap_review_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_rollout_target_gap_review_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_rollout_usage_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_rollout_usage_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_solver_prompt_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_solver_prompt_zh.md) | 已跟踪 |
| [docs/develop/modules/agent_test_demos_zh.md](/home/jianwen/topogym/docs/develop/modules/agent_test_demos_zh.md) | 已跟踪 |
| [docs/develop/modules/buzz_wire_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/buzz_wire_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/cast_keyhole_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/cast_keyhole_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/hedgehog_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/hedgehog_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/horseshoe_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/horseshoe_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/interlocked_claws_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/interlocked_claws_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/knot_untying_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/knot_untying_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/lock_picking_agent_adapter_zh.md](/home/jianwen/topogym/docs/develop/modules/lock_picking_agent_adapter_zh.md) | 已跟踪 |
| [docs/develop/modules/model_service_design_zh.md](/home/jianwen/topogym/docs/develop/modules/model_service_design_zh.md) | 已跟踪 |
| [docs/develop/modules/rollout_pipeline_refactor_plan_zh.md](/home/jianwen/topogym/docs/develop/modules/rollout_pipeline_refactor_plan_zh.md) | 未跟踪、未 ignore |

## A3. 旧源码与示例配置

agents/README 明确 deferred 是历史材料；pyproject.toml 排除 topogym.agents.deferred。configs/agent_rollout 四个 JSON 属于旧 rollout 示例。

| 路径 | Git 状态 |
|---|---|
| [topogym/agents/deferred](/home/jianwen/topogym/topogym/agents/deferred) | 已跟踪 0；未跟踪 58 |
| [configs/agent_rollout](/home/jianwen/topogym/configs/agent_rollout) | 已跟踪 4；未跟踪 0 |

## A4. 已撤回的方案及旧协议说明

高层动作计划明确“已撤出当前开发范围”；旧架构仍写 Genesis/MuJoCo、agent_bridge/agent_rollout；旧 HDF5 文档声明 0.3.0，当前 topogym/data/h5_schema.py 为 2.0.0 且 README 明确退出旧 RoboMME 格式。

| 路径 | Git 状态 |
|---|---|
| [docs/develop/modules/simulator_high_level_actions_plan_20260925_zh.md](/home/jianwen/topogym/docs/develop/modules/simulator_high_level_actions_plan_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/framework/architecture_zh.md](/home/jianwen/topogym/docs/develop/framework/architecture_zh.md) | 已跟踪 |
| [docs/develop/data_pipeline/h5_data_format_zh.md](/home/jianwen/topogym/docs/develop/data_pipeline/h5_data_format_zh.md) | 已跟踪 |

## A5. 旧 Harbor 生成任务、运行结果

harbor_tasks 约 3.6 GiB，是已退役第二版生成的 26 个任务；runs/harbor 约 590 MiB；三个 cube_tasks 目录各约 282 MiB；harbor_tasks_native_20260929 约 3.6 GiB。当前任务为 tasks/ 下 28 个任务。这里是归档候选，不是可删除或已验证可脱离旧绝对路径运行的承诺。

| 路径 | Git 状态 |
|---|---|
| [harbor_tasks](/home/jianwen/topogym/harbor_tasks) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/harbor](/home/jianwen/topogym/runs/harbor) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/harbor_cube_tasks](/home/jianwen/topogym/runs/harbor_cube_tasks) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/harbor_cube_tasks_fixed](/home/jianwen/topogym/runs/harbor_cube_tasks_fixed) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/harbor_cube_tasks_native](/home/jianwen/topogym/runs/harbor_cube_tasks_native) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/harbor_jobs](/home/jianwen/topogym/runs/harbor_jobs) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/harbor_tasks_native_20260929](/home/jianwen/topogym/runs/harbor_tasks_native_20260929) | 已跟踪 0；未跟踪 0；目录受 ignore |

## A6. task_rollouts 中的旧 Harbor 实验

这些目录与旧 runs/harbor 的运行/rollout_index 对应。不要把整个 task_rollouts 一起移动；其余本地策略/初始化证据列在 C 类。

| 路径 | Git 状态 |
|---|---|
| [task_rollouts/coil_sweep_01](/home/jianwen/topogym/task_rollouts/coil_sweep_01) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/harbor_openrouter_api_01](/home/jianwen/topogym/task_rollouts/harbor_openrouter_api_01) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/harbor_scripted_04](/home/jianwen/topogym/task_rollouts/harbor_scripted_04) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/muse_pickup_30k_10k_01](/home/jianwen/topogym/task_rollouts/muse_pickup_30k_10k_01) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/muse_pickup_30k_10k_02](/home/jianwen/topogym/task_rollouts/muse_pickup_30k_10k_02) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/run_20260929T034512Z_f4c195a8](/home/jianwen/topogym/task_rollouts/run_20260929T034512Z_f4c195a8) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/segment_history_v2_prepare_20260928](/home/jianwen/topogym/task_rollouts/segment_history_v2_prepare_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [task_rollouts/usage_muse_prepare_20260928T173447980566784Z](/home/jianwen/topogym/task_rollouts/usage_muse_prepare_20260928T173447980566784Z) | 已跟踪 0；未跟踪 0；目录受 ignore |

## A7. 旧 Harbor 专属验收/准备结果

这些记录对应已退役的 runner/usage 或 09-29 上午 native 实现，应随旧实现保留。harbor_rcb_parity_20260929 是当前实现证据，明确不在本组。harbor_audit_20260929 与 rollout_history_access_20260928 未据名字直接判旧，暂保留。

| 路径 | Git 状态 |
|---|---|
| [runs/test_results/agent_profile_creator_20260928](/home/jianwen/topogym/runs/test_results/agent_profile_creator_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/agent_profiles_layout_20260928](/home/jianwen/topogym/runs/test_results/agent_profiles_layout_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/fiber_opencode_migration_20260928](/home/jianwen/topogym/runs/test_results/fiber_opencode_migration_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_cancel_prepare_check](/home/jianwen/topogym/runs/test_results/harbor_cancel_prepare_check) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_delivery_prepare_v1](/home/jianwen/topogym/runs/test_results/harbor_delivery_prepare_v1) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_implementation_prepare](/home/jianwen/topogym/runs/test_results/harbor_implementation_prepare) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_isolation_01](/home/jianwen/topogym/runs/test_results/harbor_isolation_01) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_openrouter_api_01](/home/jianwen/topogym/runs/test_results/harbor_openrouter_api_01) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_pipeline_cpu_20260926](/home/jianwen/topogym/runs/test_results/harbor_pipeline_cpu_20260926) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_scripted_01](/home/jianwen/topogym/runs/test_results/harbor_scripted_01) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_scripted_02](/home/jianwen/topogym/runs/test_results/harbor_scripted_02) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_scripted_03](/home/jianwen/topogym/runs/test_results/harbor_scripted_03) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_scripted_04](/home/jianwen/topogym/runs/test_results/harbor_scripted_04) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_usage_20260927](/home/jianwen/topogym/runs/test_results/harbor_usage_20260927) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/harbor_verifier_fix_20260929](/home/jianwen/topogym/runs/test_results/harbor_verifier_fix_20260929) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/opencode_model_key_implementation_20260928](/home/jianwen/topogym/runs/test_results/opencode_model_key_implementation_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/rcb_migration_20260929](/home/jianwen/topogym/runs/test_results/rcb_migration_20260929) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/rollout_output_report_rename](/home/jianwen/topogym/runs/test_results/rollout_output_report_rename) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/task_rollout_config_20260928](/home/jianwen/topogym/runs/test_results/task_rollout_config_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/task_rollout_sweep_migration_20260928](/home/jianwen/topogym/runs/test_results/task_rollout_sweep_migration_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/usage_muse_prepare_20260928T172222103262105Z](/home/jianwen/topogym/runs/test_results/usage_muse_prepare_20260928T172222103262105Z) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/usage_muse_prepare_20260928T173447980566784Z](/home/jianwen/topogym/runs/test_results/usage_muse_prepare_20260928T173447980566784Z) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/usage_refactor_20260928](/home/jianwen/topogym/runs/test_results/usage_refactor_20260928) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/test_results/usage_refactor_20260928_prepare_local](/home/jianwen/topogym/runs/test_results/usage_refactor_20260928_prepare_local) | 已跟踪 0；未跟踪 0；目录受 ignore |

## A8. 更早的 agent 运行资料

与 deferred bridge/rollout 对应：agent_bridge 约 1.3 MiB、agent_bridge_validation 约 361 MiB、agent_rollouts 约 32 MiB、agent_test_demos 约 11 GiB。当前代码未发现对这些目录的输入引用；归档时仍要保留队列、状态和历史证据，不按 ignore 状态删除。

| 路径 | Git 状态 |
|---|---|
| [runs/agent_bridge](/home/jianwen/topogym/runs/agent_bridge) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/agent_bridge_validation](/home/jianwen/topogym/runs/agent_bridge_validation) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/agent_rollouts](/home/jianwen/topogym/runs/agent_rollouts) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/agent_test_demos](/home/jianwen/topogym/runs/agent_test_demos) | 已跟踪 0；未跟踪 0；目录受 ignore |

## A9. 研究源码快照和原始调查产物

runs/research 总计约 1.8 MiB。assist_survey 保存外部项目、已安装 Genesis、旧任务源码的调查副本及来源 manifest；terminal_judgement 保存 lock_stop_audit.json。当前运行源码未发现读取这里；assist/terminal 设计文档有引用，移动时改文档链接。

| 路径 | Git 状态 |
|---|---|
| [runs/research/assist_survey_20260925](/home/jianwen/topogym/runs/research/assist_survey_20260925) | 已跟踪 0；未跟踪 0；目录受 ignore |
| [runs/research/terminal_judgement_20260925](/home/jianwen/topogym/runs/research/terminal_judgement_20260925) | 已跟踪 0；未跟踪 0；目录受 ignore |

## A10. 历史汇报与杂项运行产物

reports/presentation 约 14 MiB，其中 build.py/harbor-teaser-command.sh 仍执行旧 harbor_runners；目录也含模拟器进展、视频副本，应整套归档保留。三份周报共约 347 MiB。docx 为 09-23 三档规划，Horseshoe 等条目已被后来选择覆盖。outputs 是 09-17 Hydra 参数快照与 demo.log；MUJOCO_LOG.TXT 是旧根目录日志。

| 路径 | Git 状态 |
|---|---|
| [reports/presentation](/home/jianwen/topogym/reports/presentation) | 已跟踪 0；未跟踪 114 |
| [reports/weekly/2026-09-17](/home/jianwen/topogym/reports/weekly/2026-09-17) | 已跟踪 13；未跟踪 0 |
| [reports/weekly/2026-09-19](/home/jianwen/topogym/reports/weekly/2026-09-19) | 已跟踪 135；未跟踪 0 |
| [reports/weekly/2026-09-22](/home/jianwen/topogym/reports/weekly/2026-09-22) | 已跟踪 0；未跟踪 367 |
| [TopoGym_变体规划清单.docx](/home/jianwen/topogym/TopoGym_变体规划清单.docx) | 未跟踪、未 ignore |
| [outputs/2026-09-17](/home/jianwen/topogym/outputs/2026-09-17) | 已跟踪 8；未跟踪 0 |
| [MUJOCO_LOG.TXT](/home/jianwen/topogym/MUJOCO_LOG.TXT) | 已跟踪 |

## B1. 旧审计、目录迁移、源码清单、实施前计划

这些是 09-22 至 09-24 的研究/审计快照，部分自称“当前”但统计已落后，部分正文明确被后续记录覆盖。可以从活动文档移入 legacy/docs 作为历史依据；当前 README、AGENTS 或其他记录仍引用其中多项，需同步链接。保留现行 API、实现和验证文档。

| 路径 | Git 状态 |
|---|---|
| [docs/develop/dev-logs/genesis_only_codebase_review_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/genesis_only_codebase_review_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/mujoco_dependencies_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/mujoco_dependencies_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_modularity_audit_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_modularity_audit_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_naming_audit_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_naming_audit_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_naming_inventory_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_naming_inventory_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_naming_counts_20260923.json](/home/jianwen/topogym/docs/develop/dev-logs/simulator_naming_counts_20260923.json) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/structure_move_20260923_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/structure_move_20260923_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/structure_move_files_20260923_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/structure_move_files_20260923_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/structure_move_manifest_20260923.json](/home/jianwen/topogym/docs/develop/dev-logs/structure_move_manifest_20260923.json) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/structure_move_verification_20260923.json](/home/jianwen/topogym/docs/develop/dev-logs/structure_move_verification_20260923.json) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/script_inventory_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/script_inventory_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/script_snapshots_inventory_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/script_snapshots_inventory_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/script_inventory_20260923.json](/home/jianwen/topogym/docs/develop/dev-logs/script_inventory_20260923.json) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_consolidation_plan_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_consolidation_plan_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_structure_followup_plan_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_structure_followup_plan_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_validation_plan_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_validation_plan_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_core_consolidation_20260923_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_core_consolidation_20260923_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_deleted_code_review_and_variations_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_deleted_code_review_and_variations_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_base_task_runtime_plan_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_base_task_runtime_plan_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/simulator_core_readiness_audit_20260924_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/simulator_core_readiness_audit_20260924_zh.md) | 未跟踪、未 ignore |
| [docs/develop/dev-logs/robot_policy_reference_comparison_20260924_zh.md](/home/jianwen/topogym/docs/develop/dev-logs/robot_policy_reference_comparison_20260924_zh.md) | 未跟踪、未 ignore |

## B2. 任务研究/旧执行记录

包括部署前变体盘点、planner/assist 调查、09-17 至 21 的 Knot/Rope/Slotted 执行记录。slotted_post_ring_fem 文首明确下文为旧 MuJoCo FEM 记录。这些仍可追溯研究和失败原因；不要连带移走当前任务主页及其原始证据。

| 路径 | Git 状态 |
|---|---|
| [docs/develop/tasks/variant_difficulty_review_20260924_zh.md](/home/jianwen/topogym/docs/develop/tasks/variant_difficulty_review_20260924_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/variant_asset_code_inventory_20260925_zh.md](/home/jianwen/topogym/docs/develop/tasks/variant_asset_code_inventory_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/variation_deployment_plan_20260925_zh.md](/home/jianwen/topogym/docs/develop/tasks/variation_deployment_plan_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/variation_deployment_sources_20260925.json](/home/jianwen/topogym/docs/develop/tasks/variation_deployment_sources_20260925.json) | 未跟踪、未 ignore |
| [docs/develop/tasks/horseshoe_existing_candidates_tier_review_20260925_zh.md](/home/jianwen/topogym/docs/develop/tasks/horseshoe_existing_candidates_tier_review_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/planner_oracle_inventory_20260925_zh.md](/home/jianwen/topogym/docs/develop/tasks/planner_oracle_inventory_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/planner_oracle_sources_20260925.json](/home/jianwen/topogym/docs/develop/tasks/planner_oracle_sources_20260925.json) | 未跟踪、未 ignore |
| [docs/develop/tasks/planner_recovery_and_standard_execution_plan_20260925_zh.md](/home/jianwen/topogym/docs/develop/tasks/planner_recovery_and_standard_execution_plan_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/assist_grasp_recovery_and_agent_contract_review_20260925_zh.md](/home/jianwen/topogym/docs/develop/tasks/assist_grasp_recovery_and_agent_contract_review_20260925_zh.md) | 未跟踪、未 ignore |
| [docs/develop/tasks/knot_untying_physics_demo_plan_zh.md](/home/jianwen/topogym/docs/develop/tasks/knot_untying_physics_demo_plan_zh.md) | 已跟踪 |
| [docs/develop/tasks/knot_untying_recording_attempt_zh.md](/home/jianwen/topogym/docs/develop/tasks/knot_untying_recording_attempt_zh.md) | 已跟踪 |
| [docs/develop/tasks/rope_threading_feedback_ik_zh.md](/home/jianwen/topogym/docs/develop/tasks/rope_threading_feedback_ik_zh.md) | 已跟踪 |
| [docs/develop/tasks/slotted_post_ring_fem_zh.md](/home/jianwen/topogym/docs/develop/tasks/slotted_post_ring_fem_zh.md) | 已跟踪 |
| [docs/develop/modules/recording_module_plan_zh.md](/home/jianwen/topogym/docs/develop/modules/recording_module_plan_zh.md) | 未跟踪、未 ignore |
| [docs/develop/modules/terminal_support_stability_plan_20260927_zh.md](/home/jianwen/topogym/docs/develop/modules/terminal_support_stability_plan_20260927_zh.md) | 未跟踪、未 ignore |

## B3. 包内已标 legacy 的旧 Task 入口

37 个旧入口已退出 registry 和发行，但 tests/unit/test_task_variations.py:77 会读取此目录的 manifest.json；若统一移到根 legacy，需改测试路径和 manifest 中的归档定位。不是无需联动即可移动。

| 路径 | Git 状态 |
|---|---|
| [topogym/tasks/legacy](/home/jianwen/topogym/topogym/tasks/legacy) | 已跟踪 0；未跟踪 39 |

## C. 本轮不要整体归档

| 路径 | 原因 |
|---|---|
| `tasks/`、`images/`、`harbor_agents/`、`ci_checks/`、`docs/rcb/` | 当前 Harbor；参考仓库也没有 ignore tasks/results/docs/images。 |
| `.venv-harbor/` | 当前 Harbor 仍使用，已经 ignore；名字包含 Harbor 不代表旧环境。 |
| `topogym/simulator/rollout_simulation/`、`topogym/planning/`、相关脚本和合同测试 | 本地 SegmentRunner / policy 仍有实际导入与调用。 |
| `docs/vla_doc/` | 当前 simulator API 的 VLA 侧示例与使用说明。 |
| `docs/develop/modules/{simulator_api,simulator_interaction_contract,scripted_policy_execution_plan_20260926,simulator_segment_execution_plan_20260925,grasp_assist,final_settling,recording_module_usage}_zh.md` | 当前 simulator、段执行、抓持、终态与录制说明；有历史段落不代表整份失效。 |
| `docs/develop/tasks/*_zh.md` 中各任务主页、`three_tier_setting_completion_plan`、`variation_deployment_implementation`、`task_variant_solutions_action_ik*` | 包含 09-28/29 新场景、现有解法和未完成工作，不能按文件名日期整体判旧。 |
| `solvability_proof/`、`demos/`、`runs/demo_metadata/` | 正式可解性证明、视频及核心证据；不是临时 research 文件。 |
| `runs/test_results/harbor_rcb_parity_20260929/` | 当前 RCB 对齐实现的验收证据。 |
| `runs/task_build/` | 当前 scripts/topogym_mk_limited.py:33 直接读取 describe.json；task 生成器 --reuse-describe 也使用。 |
| `runs/test_results/buzz_staged_inputs_20260929/` | 当前 topogym/planning/buzz_wire_3d/stages.py:278 指向 medium_traverse_guide.json。 |
| `runs/test_results/cast_keyhole_policy_20260928/` | 当前 qualification.py 记录任务资格证据路径。 |
| `task_rollouts/{cast_coil_assist_20260927,lock_assist_20260927,scripted_policy_pick_place_20260926,blanket_stable_initial_20260926,blanket_stable_initial_repeat02_20260926}/` | 本地策略/初态证据，其中 Coil 和 Lock 在当前 planning/README 直接引用。 |
| 其余 `runs/test_results/`、`runs/environment*`、`runs/recordings/`、`runs/scene_preset_restoration_20260924_work/`、`assets/tasks/` | 既有历史内容也有当前输入、恢复点或证据。本轮没有证明可整棵归档。 |
| 根 `configs/`（除 A3） | 多数是旧 Hydra 实验参数，核心配置已在 topogym/config/profiles，但仍被部分报告/源码快照工具打包且与历史资产复现相关；适合第二批逐项映射，不能依据无直接 import 就整棵移动。 |

## Gitignore 对照

已找到本地 `/home/jianwen/robot_coding_bench/.gitignore`；也读取了本地保存的 `origin/dev/qineng@fa59c1a6`，内容相同。没有 fetch，不声称核对了远端最新状态。

参考仓库全部规则：

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
.venv/
/exps/
/jobs/
*.log
.env
.env.*
!.env.example
```

| 类别 | robot_coding_bench | TopoGym |
|---|---|
| Python 字节码、egg-info、.venv | ignore | ignore，另有多个命名 venv/cache/build 目录 |
| `/jobs/`、`/exps/` | ignore | ignore（74–75 行） |
| `.env`、`.env.*` | ignore，保留 `.env.example` | 相同，另忽略 `.secrets/` |
| `*.log` | ignore | **缺失**。这是参考仓库规则中唯一未覆盖的规则 |
| `runs/`、`task_rollouts/`、`harbor_tasks/` | 无这些规则 | ignore |
| `tasks/`、任务内 `results/`、`docs/`、`images/` | 不整体 ignore | 不整体 ignore |
| `reports/`、`outputs/`、`MUJOCO_LOG.TXT` | 无专项规则（仅 .log 命中） | 当前不整体 ignore；outputs 与 MUJOCO_LOG.TXT 已跟踪 |
| `legacy/runs/`、`legacy/reports/` | 无专项规则 | ignore；legacy 下的源码/文档保留版本化 |
| `demos/**/*.mp4` | 无通用视频忽略规则 | 第 71 行 `!/demos/**/*.mp4` 重新允许，覆盖前面的任务专属视频忽略项 |

已用 git check-ignore --no-index 验证规则行为，并用 git ls-files 核对跟踪状态。参考仓库实际跟踪了任务 results/ 与 docs/results 的 129 个文件（46 Markdown、1 JSON、41 PNG、41 MP4），因此不应照抄成“所有结果与视频都 ignore”。

建议后续添加 `*.log`，并根据希望保留在 Git 的范围考虑 `/outputs/`、`/MUJOCO_LOG.TXT`。这轮未修改 .gitignore。已跟踪文件即使新添 ignore 规则也不会自动退出 Git；移动到 ignored 目录也应明确是保留版本化历史还是只保留本地副本。

**迁移落点的具体差异：** `/harbor_tasks/` 只匹配仓库根。若改放 `legacy/harbor_tasks/`，现有规则不会忽略它，约 3.6 GiB 可能变成未跟踪待提交文件。建议旧运行产物统一放 `legacy/runs/`，旧报告放 `legacy/reports/`；源码和文档放 `legacy/` 对应位置。

## 归档时需同步的引用（本轮未修改）

- 根 README.md、docs/README.md、docs/develop/README.md、docs/develop/modules/README.md：指向旧计划和旧 Harbor 的链接；保留入口文档，改内部链接。
- scripts/README.md:31 与 tests/README.md:112：仍保留旧 Harbor runner 命令和已不存在的测试路径。
- topogym/agents/__init__.py:1：注释仍称 active integration 为 topogym.benchmark，已过时；agents/README.md 应随 deferred 移动后更新。
- tests/unit/test_task_variations.py:77：如果归并 topogym/tasks/legacy，更新 manifest 路径；同时维护 manifest 的 archived_path 与相关索引。
- scripts/inventory_sources.py：移动 deferred 后应更新分类逻辑；旧清单若保留为历史快照，不应伪称实时清单。
- assist_integration_engineering_plan 等文档：引用 runs/research 下调查源码，需要对应改链接。
- reports/presentation 和历史运行 manifest 内含旧绝对路径。归档保留原始证据，不对历史 manifest 随意改写；另加路径映射说明更清晰。

本轮只把已确认的旧实现/快照与当前依赖区分出来，没有执行全机活跃进程、打开文件、队列和全部二进制证据的迁移前审计。后续真正移动大型 runs 时按所选清单再核对。
