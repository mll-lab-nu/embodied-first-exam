# 当前运行工具

2026-10-06：按用户要求，`run_agent_batch.sh` 已逐字恢复为 `ci_checks/rcb_vendor.json` 固定的原版（blob `a74bf7cc16e35b3b86ae23595c3e0b63d6bff102`）。新增的 Python 派单 runner、安装/构建/封存工具、helper 包装入口及其任务单已归档到本机 Git 忽略目录 `legacy/run_agent_batch_extensions_20261006/`，活动代码不导入该目录。

原入口直接调用 Harbor，使用已准备好的 `tasks/<base>-privileged` / `tasks/<base>-standard`；重复次数通过 `K` 指定，默认 1。它不再读取 helper assignment，也不自动安装工具、重建冻结镜像或生成 native-batch 封存清单。以前的 helper 操作单仅适用于各自固定的旧 release。独立 difficulty 流程、任务包、镜像材料和已有结果保留。

新实验统一使用 `ci_checks/topogym_active_release.json` 选定的 v15。
`topogym_versions.py tasks-root/list/check` 解析并校验任务；未生成完整候选时拒绝回退历史目录。
`topogym_merge_candidate.py --output <新目录>` 冻结构建输入；构建镜像后运行
`topogym_candidate_pipeline.py --candidate <目录> --phase all`，可按 build / preflight / harbor-smoke 分阶段恢复。
只有完整 39 实例、78 包的初态及 Harbor nop 验收通过才激活；oracle 成功资格单独取得。
`bash_scripts/run_difficulty_trials.sh` 的新 run 使用同一公开环境参数，随机 seed 仍独立采样；恢复旧 run 不改其锁。
`regrade_trials.sh` 只重评绑定 v15 的原任务路径，写新目录；新旧结果不会互相覆盖。


2026-09-29：独立研究、诊断、初态预览、验收与源码盘点脚本已移入
[研究工具归档](../legacy/research_tools_20260929/README.md)。原始内容与路径映射保留在归档中，
当前 rollout 和 Harbor 不导入归档代码。

## Rollout 准备

- `prepare_nyx_studio.py`：准备并核验运行时 Nyx HDRI 和纹理；镜像构建也会调用。
- `prepare_blanket_initial_states.py`、`install_blanket_initial_state.py`：离线准备并安装 Blanket 五档初态资源；very_easy / easier 使用独立折角资源版本。
- `check_blanket_corner_initial_states.py`：新两档的零推进恢复、完整粒子位置／速度回溯、home 静置及 Nyx 四路录像；第二次运行可用 `--compare <前次目录>/particle_checks.npz` 验证独立进程重建。不是完整机器人求解证明。
- `prepare_knot_instances.py`：按当前物理配置串行重建 knot 的 IPC 冻结实例，保存正式与无 RGB 开发副本，不覆盖 `tasks/`。
- `check_knot_initial_states.py`：核对 Knot 冻结实例的完整恢复、短时 home 静置、交叉结构和只读抓取 IK，保存共享四路 Nyx 视频；支持已确认的 very_easy / easier，不授予完整求解资格。新两档准备时显式指定当前 `--tooling`，见 [Knot oracle 用法](../topogym/planning/knot_untying/README.md#已确认的-very_easy--easier-变体)。
- `import_rope_threading_reference.py`：从外部参考数据提取 Rope 几何与初态参数。
- `compile_buzz_wire_actions.py`：将已选研究轨迹编译为后续 Buzz rollout 可读取的动作文件；编译本身不授予成功资格。
- `plan_rope_threading_oracle.py`、`plan_rope_threading_ik.py`：Wang 0° 三档的物体路径和双臂接力 IK；执行入口为 `oracle_runners/run_rope_threading_relay.py`，完整命令见 [Rope oracle](../topogym/planning/rope_threading/README.md)。

## 本地 Rollout

- 10 个 oracle／参考策略执行入口已集中在 [oracle_runners/](oracle_runners/README.md)，包括 Buzz、Coil、Keyhole、Lock、Hedgehog、Horseshoe、Claws、共享刚体 runner 和分阶段 workflow；命令改为 `python scripts/oracle_runners/<脚本名>.py ...`。源码快照内的 worker 入口同步迁移。
- `plan_lock_picking_oracle.py`：冻结当前 Lock 三档物体路径与 1／2／3 次回退证书，`--ik` 加做从 home 起步的当前 Genesis 只读 IK，不推进物理。`oracle_runners/run_lock_picking_policy.py --route-mode reindex --variation <variant> --audit-ik --part solve` 实际执行，原生 Task 成功即正常结束，允许仍抓持；`audit_lock_picking_robot.py` 独立复核连续状态、关节、抓持、碰撞及 success 时间窗口。历史完整释放流程及原证据不改写。
- `plan_hedgehog_object_oracle.py`、`audit_hedgehog_oracle.py`：物体证书与独立逐 tick 审计工具仍在本目录；执行入口为 `oracle_runners/run_hedgehog_oracle.py`。[已验收范围](../solvability_proof/hedgehog_in_cage/README.md)。
- `plan_claws_object_oracle.py`、`plan_claws_ik.py`、`audit_claws_oracle.py`：Claws 原三档的冻结几何、只读 IK 和执行审计；执行入口为 `oracle_runners/run_claws_oracle.py`，共享 Nyx 重渲染入口为 `render_claws_oracle.py`。[命令与范围](oracle_runners/README.md#claws-easy--medium--hard-交接路线)。
- `plan_blanket_object_oracle.py`、`audit_blanket_oracle.py`：Blanket 三档虚拟手见证与独立逐 tick 审计；执行入口为 `oracle_runners/run_blanket_oracle.py`，从默认 home 经双手局部辅助抓持、展平、释放撤手到原生 Task 判定。[命令与交接结果范围](oracle_runners/README.md#blanket-easy--medium--hard-双手展平路线)。
- `oracle_runners/run_knot_oracle.py`、`oracle_runners/run_knot_branching.py`：Knot 纯摩擦参考策略与决策回溯；`audit_knot_oracle.py` 在新进程调用任务原生 replay，可记录逐 tick 状态和共享四路视频；`audit_knot_physics.py` 离线检查体积、绳自交及机器人／绳／桌面几何分离。[命令与范围](../topogym/planning/knot_untying/README.md)。
- `test_scripted_policy_rollout.py`：`act(obs)` 样板执行入口，输出至 `task_rollouts/`。
- `test_policy_cube_transfer.py`：低层方块执行与控制模式矩阵入口；其 `snapshot()` 被多个 rollout 管理脚本复用。

以上两个 `test_` 命名脚本保留实际执行职责；共享夹具在 [tests/fixtures/](../tests/fixtures/)，不依赖已归档的测试套件。
用法见 [本地策略说明](../topogym/planning/README.md) 与 [本地执行入口](../tests/README.md)。

## Harbor 构建、运行及结果处理

- `topogym_versions.py`：读取 `ci_checks/topogym_active_release.json`，区分唯一开发目标与冻结正式版；缺少活动任务树时拒绝退回历史任务。
- `oracle_runners/harbor_oracle.py`：全任务共享的 `bind`、精确恢复 `preflight`、私有 oracle `package/check/run`；正式执行要求模拟器与 verifier 使用同一运行绑定。独立 Env runner 的产物仍是开发证据，完整接入步骤见 [Harbor oracle bridge](../topogym/planning/harbor_bridge/README.md)。
- `oracle_runners/test_harbor_oracles.py`：逐 oracle 的双模式 Harbor 评分回归；保存覆盖缺口，核验 privileged 至少两次回放、standard live 与独立回放以及实际轨迹，默认带 nop 负对照。候选单任务冒烟用 `--tasks-root <目录> --candidate --families cast_coil --tiers easy --execute`，完整参数见上面的 bridge 文档。
- `../bash_scripts/run_harbor_oracle_grades.sh`：easy–hard 的 11 类 oracle 串行实机评分交接入口；支持自动生成候选、单项选择、断点继续和逐项汇总。默认完整双模式评分，可用 `--smoke-steps 3` 进行明确区分的接线检查。[运行方式](../topogym/planning/harbor_bridge/README.md#逐项实机-grade-交接easyhard)。
- `topogym_merge_candidate.py`：保存合并候选的源码和 39 个实例构建配方，生成新镜像及 78 个候选包的构建命令，保留 v14 原包。
- `sample_difficulty_instances.py`：13 项编号选择器、每难度随机抽样、源码快照及冻结 manifest；默认全任务、每档 1 个样本。
- `difficulty_eval.py`：难度评测调度；解析参数、准备任务、物理 preflight、认证 canary、逐次 `harbor run`、中断处理和恢复；默认 agent 预算 21600 秒，使用公共 `harbor_templates/topogym/`。
- `../bash_scripts/run_difficulty_trials.sh`：默认自动准备并启动 Docker 控制器；`check`、容器内 `auth login` 与实验共用入口，默认工作目录为启动目录的 `topogym-work`；`--backend local` 显式保留宿主环境。
- `difficulty_delivery.py`：Docker 交付适配，管理固定镜像、共享路径检查、GPU UUID、daemon 内锁和所属容器清理，不复制实验阶段逻辑。
- `difficulty_hf_auth.py`：显式读取 HF_TOKEN 或私有 token 文件，不交互登录；校验参数并隔离评测子进程环境。
- `difficulty_results_hf.py`：白名单结果导出、快照身份、HF 分批 commit、恢复对账和上传日志；通过 difficulty_eval 的 `--results_to_hf` / `--phase upload` 使用，见 [HF 上传用法](../docs/rcb/docker_quickstart_zh.md#上传结果到私有-hf-dataset)。
- `difficulty_helper.py` / `helper_assignment.py`：`run_difficulty_trials.sh helper assign/retry-plan/export/verify/import/upload`，冻结任务清单、限制重跑；见 [helper 手册](../docs/rcb/helper_quickstart_zh.md)。
- `helper_runtime.py` / `helper_log_mirror.py`：helper 主机、时间和异常记录；每次 job 独立镜像 agent 日志，复用固定上游 `log_mirror.py` 的版本记录能力。
- `secret_scan.py` / `scan_secrets.py`：严格凭据扫描、文本脱敏与独立复扫；exit 0 clean / 1 residual / 2 incomplete，二进制命中阻止交付。
- `helper_bundle.py` / `helper_import.py` / `helper_upload.py`：本批完整原始证据封包、逐文件验包、异机 Markdown 审查入口、私有 HF 三文件传输；不调用模型。
- `trial_task_paths.py`：按导入包内映射定位原任务，避免依赖 helper 主机绝对路径；供报告与重评分共用。

- `difficulty_release.py`：无 Git 源码身份、build-info 与 Docker 源码发行包；使用方法见 [Docker 启动说明](../docs/rcb/docker_quickstart_zh.md)。
- `topogym_mk_task.py`、`topogym_mk_limited.py`：生成 unlimited / limited 任务。
- `check_builder_feedback.py`：Builder 反馈的持续回归入口，记录 seed 冷启动、夹爪保持／回放、IK 端点和 Lock 支架取件诊断；输出报告、逐 tick 记录与共享录制 MP4，不授予完整任务成功资格。见[修补计划](../docs/rcb/builder_feedback_repair_plan_zh.md)。
- `check_run_trials_repairs.py`：run-trials 修复的持续 GPU 回归入口，核对拒绝动作、实际 tick、终态后调用、可信轨迹回放和共享录制；须显式提供工具路径、任务和新的输出目录。短 hold 前缀不作为完整求解证据，见[实施报告](../docs/debug_logs/run_trials_post_merge_repair_20261001_zh.md)。
- `check_cast_keyhole_simplifications.py`：Cast Keyhole 五档的静置诊断，默认 3 个控制步，可用 `--steps 100` 检查 2.5 s；新两档支持 `--check-grasp` 进行只读 IK／完整网格接近检查。冻结源码并保存 Nyx 初始帧、共享录像和漂移报告，实际抓持与完整求解另行验证；CPU 只监控，系统内存达到 90% 停止本次子进程。见[修订文档](../docs/tasks_simplifications/cast_keyhole_very_easy_easier_revision_plan_zh.md)。
- `build_images.sh`、`push_images.sh`、`vendor_rcb.py`、`set_agent_egress.py`：镜像、参考工具及任务出网配置。
- `run_agent_batch.sh`、`regrade_trials.sh`：批量运行与重评分。
- `account_failure_check.py`、`log_mirror.py`、`scan_secrets.py`：账号异常检测、日志镜像与产物密钥检查。恢复后的原版批处理使用 `mem_guard.py`；`topogym_guarded.py` 仍供其他本地运行入口使用。扫描器不再依赖 native-batch inventory 或重新封存结果。
- `collect_batch_results.py`、`write_task_results.py`、`make_two_mode_report_zh.py`：收集结果并生成报告。

完整命令见 [Harbor 手册](../docs/rcb/README.md)。任务静态检查仍为 `bash ci_checks/run_all.sh`。
