# 当前运行工具

2026-09-29：独立研究、诊断、初态预览、验收与源码盘点脚本已移入
[研究工具归档](../legacy/research_tools_20260929/README.md)。原始内容与路径映射保留在归档中，
当前 rollout 和 Harbor 不导入归档代码。

## Rollout 准备

- `prepare_nyx_studio.py`：准备并核验运行时 Nyx HDRI 和纹理；镜像构建也会调用。
- `prepare_blanket_initial_states.py`、`install_blanket_initial_state.py`：离线准备并安装 Blanket 初态资源。
- `prepare_knot_instances.py`：按当前物理配置串行重建 knot 的 IPC 冻结实例，保存正式与无 RGB 开发副本，不覆盖 `tasks/`。
- `import_rope_threading_reference.py`：从外部参考数据提取 Rope 几何与初态参数。
- `compile_buzz_wire_actions.py`：将已选研究轨迹编译为后续 Buzz rollout 可读取的动作文件；编译本身不授予成功资格。
- `plan_rope_threading_oracle.py`、`plan_rope_threading_ik.py`：Wang 0° 三档的物体路径和双臂接力 IK；执行入口为 `oracle_runners/run_rope_threading_relay.py`，完整命令见 [Rope oracle](../topogym/planning/rope_threading/README.md)。

## 本地 Rollout

- 10 个 oracle／参考策略执行入口已集中在 [oracle_runners/](oracle_runners/README.md)，包括 Buzz、Coil、Keyhole、Lock、Hedgehog、Horseshoe、Claws、共享刚体 runner 和分阶段 workflow；命令改为 `python scripts/oracle_runners/<脚本名>.py ...`。源码快照内的 worker 入口同步迁移。
- `plan_lock_picking_oracle.py`：冻结当前 Lock 三档物体路径与 1／2／3 次回退证书，`--ik` 加做从 home 起步的当前 Genesis 只读 IK，不推进物理。`oracle_runners/run_lock_picking_policy.py --route-mode reindex --variation <variant> --audit-ik --part solve` 实际执行，原生 Task 成功即正常结束，允许仍抓持；`audit_lock_picking_robot.py` 独立复核连续状态、关节、抓持、碰撞及 success 时间窗口。历史完整释放流程及原证据不改写。
- `plan_hedgehog_object_oracle.py`、`audit_hedgehog_oracle.py`：物体证书与独立逐 tick 审计工具仍在本目录；执行入口为 `oracle_runners/run_hedgehog_oracle.py`。[已验收范围](../solvability_proof/hedgehog_in_cage/README.md)。
- `plan_claws_object_oracle.py`、`plan_claws_ik.py`、`audit_claws_oracle.py`：Claws 原三档的冻结几何、只读 IK 和执行审计；执行入口为 `oracle_runners/run_claws_oracle.py`，共享 Nyx 重渲染入口为 `render_claws_oracle.py`。[命令与范围](oracle_runners/README.md#claws-easy--medium--hard-交接路线)。
- `plan_blanket_object_oracle.py`、`audit_blanket_oracle.py`：Blanket 三档虚拟手见证与独立逐 tick 审计；执行入口为 `oracle_runners/run_blanket_oracle.py`，从默认 home 经双手局部辅助抓持、展平、释放撤手到原生 Task 判定。[命令与交接结果范围](oracle_runners/README.md#blanket-easy--medium--hard-双手展平路线)。
- `oracle_runners/run_knot_oracle.py`、`oracle_runners/run_knot_branching.py`：Knot 纯摩擦参考策略与决策回溯；`audit_knot_oracle.py` 在新进程调用任务原生 replay 评分。[命令与范围](../topogym/planning/knot_untying/README.md)。
- `test_scripted_policy_rollout.py`：`act(obs)` 样板执行入口，输出至 `task_rollouts/`。
- `test_policy_cube_transfer.py`：低层方块执行与控制模式矩阵入口；其 `snapshot()` 被多个 rollout 管理脚本复用。

以上两个 `test_` 命名脚本保留实际执行职责；共享夹具在 [tests/fixtures/](../tests/fixtures/)，不依赖已归档的测试套件。
用法见 [本地策略说明](../topogym/planning/README.md) 与 [本地执行入口](../tests/README.md)。

## Harbor 构建、运行及结果处理

- `sample_difficulty_instances.py`：13 项编号选择器、每难度随机抽样、源码快照及冻结 manifest；默认全任务、每档 1 个样本。
- `difficulty_eval.py`：难度评测调度；解析参数、准备任务、物理 preflight、认证 canary、逐次 `harbor run`、中断处理和恢复；默认 agent 预算 21600 秒，使用公共 `harbor_templates/topogym/`。
- `../bash_scripts/run_difficulty_trials.sh`：默认自动准备并启动 Docker 控制器；`check`、容器内 `auth login` 与实验共用入口，默认工作目录为启动目录的 `topogym-work`；`--backend local` 显式保留宿主环境。
- `difficulty_delivery.py`：Docker 交付适配，管理固定镜像、共享路径检查、GPU UUID、daemon 内锁和所属容器清理，不复制实验阶段逻辑。
- `difficulty_hf_auth.py`：显式读取 HF_TOKEN 或私有 token 文件，不交互登录；校验参数并隔离评测子进程环境。
- `difficulty_results_hf.py`：白名单结果导出、快照身份、HF 分批 commit、恢复对账和上传日志；通过 difficulty_eval 的 `--results_to_hf` / `--phase upload` 使用，见 [HF 上传用法](../docs/rcb/docker_quickstart_zh.md#上传结果到私有-hf-dataset)。
- `difficulty_release.py`：无 Git 源码身份、build-info 与 Docker 源码发行包；使用方法见 [Docker 启动说明](../docs/rcb/docker_quickstart_zh.md)。
- `topogym_mk_task.py`、`topogym_mk_limited.py`：生成 unlimited / limited 任务。
- `check_builder_feedback.py`：Builder 反馈的持续回归入口，记录 seed 冷启动、夹爪保持／回放、IK 端点和 Lock 支架取件诊断；输出报告、逐 tick 记录与共享录制 MP4，不授予完整任务成功资格。见[修补计划](../docs/rcb/builder_feedback_repair_plan_zh.md)。
- `check_run_trials_repairs.py`：run-trials 修复的持续 GPU 回归入口，核对拒绝动作、实际 tick、终态后调用、可信轨迹回放和共享录制；须显式提供工具路径、任务和新的输出目录。短 hold 前缀不作为完整求解证据，见[实施报告](../docs/debug_logs/run_trials_post_merge_repair_20261001_zh.md)。
- `check_cast_keyhole_simplifications.py`：Cast Keyhole 五档的静置诊断，默认 3 个控制步，可用 `--steps 100` 检查 2.5 s；新两档支持 `--check-grasp` 进行只读 IK／完整网格接近检查。冻结源码并保存 Nyx 初始帧、共享录像和漂移报告，实际抓持与完整求解另行验证；CPU 只监控，系统内存达到 90% 停止本次子进程。见[修订文档](../docs/tasks_simplifications/cast_keyhole_very_easy_easier_revision_plan_zh.md)。
- `build_images.sh`、`push_images.sh`、`vendor_rcb.py`、`set_agent_egress.py`：镜像、参考工具及任务出网配置。
- `run_agent_batch.sh`、`regrade_trials.sh`：批量运行与重评分。
- `account_failure_check.py`、`log_mirror.py`、`mem_guard.py`、`scan_secrets.py`：账号异常检测、日志镜像、资源监控与产物密钥检查。
- `collect_batch_results.py`、`write_task_results.py`、`make_two_mode_report_zh.py`：收集结果并生成报告。

完整命令见 [Harbor 手册](../docs/rcb/README.md)。任务静态检查仍为 `bash ci_checks/run_all.sh`。
