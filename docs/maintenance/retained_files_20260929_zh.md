# 必要文件保留清单与 Git 忽略范围

核对日期：2026-09-29。依据当前工作树、实际读取路径、包发行配置和当前 Harbor 手册。
本清单最初用于归档前审阅。用户随后授权迁移：128 项旧候选已移入 `legacy/cleanup_20260929/`，见[执行记录](legacy_cleanup_20260929_zh.md)。原始内容保留，未取消跟踪或操作 Git 索引。

“保留”包含两种情况：源码、协议、配置和正式交付继续允许进入 Git；运行输入、原始证据及本地环境继续保存在磁盘，但可以被 Git 忽略。ignore 不代表可以删除。下表未列到的历史文件也不自动成为可删除项。

## 1. 当前源码与工程文件

目录项包含该目录内的源码、必要配置和资源，不包含字节码、缓存或构建产物。

| 保留路径 | 必要性 |
|---|---|
| `README.md`、`AGENTS.md`、`CLAUDE.md` | 项目入口与开发约定；旧说明应更新，不整份丢弃 |
| `pyproject.toml`、`env_setup_gs121.sh`、`requirements/`、`ruff.toml` | 安装、依赖与开发环境 |
| `.gitignore`、`.gitattributes`、`.dockerignore`、`.env.example`、`.github/` | 版本管理、镜像构建、公开配置模板与 CI |
| `topogym/__init__.py`、`topogym/README.md` | 包入口与模块说明 |
| `topogym/simulator/`、`topogym/config/` | 公共 API、生命周期、历史、权限、任务登记与随包 profiles |
| `topogym/simulator/rollout_simulation/` | 当前本地 SegmentRunner、policy 调度、观测投影和产物管理，仍被 planning 与测试使用 |
| `topogym/world/`、`topogym/robot/`、`topogym/solvers/` | Genesis 物理、机器人控制、FK/IK、状态恢复 |
| `topogym/tasks/` 的活动任务与公共模块 | 当前任务、变体、初态和成功判据；包内 legacy 的处理见第 4 节 |
| `topogym/assets/`、`topogym/sensors/` | 几何、材质、模板、随包资产及相机观测 |
| `topogym/planning/`、`topogym/evaluation/`、`topogym/recording/`、`topogym/data/`、`topogym/utils/` | 当前策略、测量、录制、transition 数据和共用工具 |
| `assets/robots/` | 镜像 `.dockerignore` 明确纳入的机器人资源 |
| `tests/`、`scripts/` | 当前 simulator 测试、资产准备、策略执行、证据生成、任务生成及批处理工具 |

原 `topogym/agents/deferred/` 已移入 `legacy/cleanup_20260929/`，不属于当前运行层。根目录 `assets/tasks/` 与 `configs/` 暂保留，理由见第 4 节；核心随包配置是 `topogym/config/profiles/`。

## 2. 当前 Harbor 层

| 保留路径 | 必要性 |
|---|---|
| `tasks/` | 当前 28 个任务及 `dataset.toml`；保留 instruction、task.toml、environment、tests、solution 与任务结果资料 |
| `images/` | 当前基础镜像 Dockerfile、版本及裁剪逻辑 |
| `harbor_agents/` | 当前模型接入与网关 |
| `ci_checks/` | 任务目录、协议、隔离等静态检查 |
| `scripts/topogym_mk_task.py`、`scripts/topogym_mk_limited.py` | unlimited / limited 任务生成 |
| `scripts/build_images.sh`、`scripts/push_images.sh`、`scripts/vendor_rcb.py` | 镜像与参考代码维护 |
| `scripts/run_agent_batch.sh`、`scripts/regrade_trials.sh`、`scripts/collect_batch_results.py`、`scripts/write_task_results.py`、`scripts/make_two_mode_report_zh.py` | 运行、复评、结果整理 |
| `scripts/mem_guard.py`、`scripts/log_mirror.py`、`scripts/account_failure_check.py`、`scripts/set_agent_egress.py`、`scripts/scan_secrets.py` | 批处理配套工具；保留不表示本轮启动了它们 |
| `docs/rcb/README.md`、`PROTOCOL.md`、`LIMITED_MODE_PROTOCOL.md`、`TAXONOMY.md` | 当前运行手册与协议；后面三个文件也在 `docs/rcb/` |

旧 `harbor_tasks/` 和两版 `legacy/harbor*` 与当前 `tasks/` 不同，不应仅按名称中含 Harbor 就一起忽略或移动。

## 3. 必要文档

保留文档入口 `docs/README.md`、`docs/develop/README.md`、`docs/develop/modules/README.md`、`docs/develop/tasks/README.md`、`docs/develop/dev-logs/README.md`、`docs/progress/current_zh.md`，以及各活动源码目录的 README。它们含部分过时段落，后续归档时修正链接和状态说明。

### 公共接口与模块

以下文件位于 `docs/develop/modules/`：

- `simulator_api_zh.md`
- `simulator_interaction_contract_zh.md`
- `simulator_segment_execution_plan_20260925_zh.md`
- `scripted_policy_execution_plan_20260926_zh.md`
- `recording_module_usage_zh.md`
- `dual_arm_aloha_zh.md`
- `grasp_assist_zh.md`
- `soft_grasp_assist_engineering_plan_20260927_zh.md`
- `final_settling_zh.md`

另保留：

- `docs/develop/framework/genesis_world_coordinates_zh.md`
- `docs/debug_logs/README.md`、`docs/debug_logs/scene_lifecycle_rgb_repro_20260925_zh.md`
- `docs/vla_doc/README.md`、`docs/vla_doc/vla_eval_demo.py`
- `topogym/data/README.md`：当前 transition schema 为 2.0.0；旧 `docs/develop/data_pipeline/h5_data_format_zh.md` 的 0.3.0 不作为当前合同。

### 各任务主页与仍在推进的工作

以下文件位于 `docs/develop/tasks/`：

- 13 个任务主页：`blanket_flatten_zh.md`、`buzz_wire_3d_zh.md`、`cast_coil_zh.md`、`cast_keyhole_zh.md`、`fiber_bundling_zh.md`、`hedgehog_in_cage_zh.md`、`horseshoe_ring_zh.md`、`interlocked_claws_zh.md`、`knot_untying_zh.md`、`lock_picking_zh.md`、`orbits_zh.md`、`rope_threading_zh.md`、`slotted_post_ring_zh.md`。
- 家族与场景：`buzz_wire_3d_family_space_zh.md`、`knot_untying_family_space_zh.md`、`blanket_frozen_initialization_plan_20260926_zh.md`、`initial_scene_feedback_20260927_zh.md`、`three_tier_setting_completion_plan_20260925_zh.md`、`variation_deployment_implementation_20260925_zh.md`。
- 抓持、判据及策略：`assist_integration_engineering_plan_20260925_zh.md`、`terminal_judgement_engineering_plan_20260925_zh.md`、`hedgehog_claws_scripted_policy_plan_20260927_zh.md`。
- 解法与证据索引：`task_variant_solutions_action_ik_zh.md`、`task_variant_solutions_action_ik_inventory_20260927.json`。

这些资料包含当前场景、剩余问题或后续实施内容；不能仅凭文件名日期判断过时。被这些文档引用的历史研究来源可迁入 legacy，但应同步链接并保留来源。

### 实施与验证依据

以下文件位于 `docs/develop/dev-logs/`，保留其实际验证范围，不能把历史结果当作最新工作树全部通过：

- `simulator_public_api_and_validation_plan_20260924_zh.md`
- `simulator_public_api_implementation_20260924_zh.md`
- `simulator_base_runtime_implementation_zh.md`
- `simulator_task_integration_20260923_zh.md`
- `simulator_simplification_20260923_zh.md`
- `simulator_nyx_runtime_20260923_zh.md`
- `simulator_test_scripts_zh.md`
- `simulator_segment_implementation_20260925_zh.md`
- `scripted_policy_execution_implementation_20260926_zh.md`
- `task_success_control_and_solvability_plan_20260924_zh.md`
- `task_terminal_independent_implementation_20260925_zh.md`
- `task_terminal_integration_20260926_zh.md`
- `scene_preset_restoration_20260924_zh.md`
- `scene_preset_restoration_implementation_20260924_zh.md`
- `scene_preset_restoration_20260924/`：上述场景材料的截图与来源。

## 4. 必须保留的本地输入与证据

| 保留路径 | 引用或保留理由 | Git 策略 |
|---|---|---|
| `runs/task_build/` | `scripts/topogym_mk_limited.py` 直接读取 `describe.json`；task 生成器 `--reuse-describe` 也使用 | 继续 ignore，保留磁盘文件 |
| `runs/test_results/buzz_staged_inputs_20260929/` | 当前 Buzz planner 引用 `medium_traverse_guide.json` | 继续 ignore，保留输入 |
| `runs/test_results/cast_keyhole_policy_20260928/` | 当前 `qualification.py` 中的资格证据路径 | 继续 ignore，保留证据 |
| `runs/test_results/harbor_rcb_parity_20260929/` | 当前 Harbor 对齐实现的验收依据 | 继续 ignore，保留证据 |
| `runs/test_results/base_acceptance_final/` 及索引引用的场景批次 | 根 README 的当前初始化录像入口 | 继续 ignore，保留索引及其真实目标 |
| `task_rollouts/cast_coil_assist_20260927/`、`task_rollouts/lock_assist_20260927/` | 当前 planning README 引用；包含成功范围、失败和后续调查 | 继续 ignore，保留证据 |
| `task_rollouts/scripted_policy_pick_place_20260926/`、`task_rollouts/blanket_stable_initial_20260926/`、`task_rollouts/blanket_stable_initial_repeat02_20260926/` | 本地 policy 与初态记录 | 继续 ignore，保留证据 |
| `solvability_proof/` | 正式可解性证明、目录、manifest 和校验结果 | 文档与清单可进 Git；`*/*/evidence/` 保持本地 |
| `demos/`、`runs/demo_metadata/` | 正式视频及对应配置、状态、来源和哈希 | 视频可进 Git；metadata 继续本地保留 |
| `.venv-harbor/`、`.venv-gs121/`、`.venv-gs121-nyx/` | 当前本地工具与仿真环境 | 继续 ignore |
| `.env`、`.env.*`、`.secrets/` 中实际使用的本地配置 | 运行配置与凭据；本清单不收录内容 | 继续 ignore，`.env.example` 例外 |

以下范围需区分已完成的迁移与仍保留的输入：

- 原 `topogym/tasks/legacy/` 已整体归档；回归测试改读 `tests/fixtures/retired_variations.json`，不再依赖旧 manifest 的位置。
- 根 `configs/`（旧 `configs/agent_rollout/` 已单独归档）、`assets/tasks/`：有历史实例输入、规划来源和资产；部分测试工具还会打包根 configs，不能整棵删除。
- 其余 `runs/test_results/`、`runs/environment*`、`runs/recordings/`、`runs/scene_preset_restoration_20260924_work/`：混有当前恢复点、输入或最后一份证据。需要逐批核对，不能用统一目录规则判旧。
- 当前实施文档引用的旧 `runs/research/` 来源和旧审计材料已归档，活动文档链接已同步；归档原件保持正文与哈希不变。

## 5. 本次 `.gitignore` 对齐

参考本地 `robot_coding_bench/.gitignore`，并保留 TopoGym 特有的运行产物与环境规则：

- 补齐参考仓库的 `*.log`；`/jobs/`、`/exps/`、Python 缓存、`.venv/` 与环境文件规则已覆盖。
- `.env.*` 与 `!.env.example` 集中放在环境文件部分。
- 新增 `/outputs/`、`/MUJOCO_LOG.TXT`，对应历史 Hydra 输出和根目录模拟器日志。
- 新增 `/legacy/harbor_tasks/`，使旧生成任务将来若移动到该处仍保持 ignored；原 `/harbor_tasks/` 只匹配根目录。
- 保留 `/legacy/runs/`、`/legacy/reports/`；legacy 源码、配置和文档继续允许版本化。
- 移除已被末尾视频例外覆盖的任务专属 MP4 忽略规则，保留 `!/demos/**/*.mp4`；正式视频的有效规则不变。
- 不增加对当前 `tasks/`、任务 `results/`、`docs/`、`images/`、源码或所有媒体文件的统一忽略。

已有 Git 跟踪不因 ignore 变化而自动取消。当前 `outputs/2026-09-17/` 的 8 个文件和 `MUJOCO_LOG.TXT` 仍在索引中；本轮不操作索引、不执行 `git rm --cached`。后续归档时再明确这些文件保留版本化历史还是只保留本地副本。
