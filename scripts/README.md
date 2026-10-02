# 当前运行工具

2026-09-29：独立研究、诊断、初态预览、验收与源码盘点脚本已移入
[研究工具归档](../legacy/research_tools_20260929/README.md)。原始内容与路径映射保留在归档中，
当前 rollout 和 Harbor 不导入归档代码。

## Rollout 准备

- `prepare_nyx_studio.py`：准备并核验运行时 Nyx HDRI 和纹理；镜像构建也会调用。
- `prepare_blanket_initial_states.py`、`install_blanket_initial_state.py`：离线准备并安装 Blanket 初态资源。
- `import_rope_threading_reference.py`：从外部参考数据提取 Rope 几何与初态参数。
- `compile_buzz_wire_actions.py`：将已选研究轨迹编译为后续 Buzz rollout 可读取的动作文件；编译本身不授予成功资格。

## 本地 Rollout

- 10 个 oracle／参考策略执行入口已集中在 [oracle_runners/](oracle_runners/README.md)，包括 Buzz、Coil、Keyhole、Lock、Hedgehog、Horseshoe、Claws、共享刚体 runner 和分阶段 workflow；命令改为 `python scripts/oracle_runners/<脚本名>.py ...`。源码快照内的 worker 入口同步迁移。
- `plan_lock_picking_oracle.py`：冻结当前 Lock 三档物体路径与 1／2／3 次回退证书，`--ik` 加做从 home 起步的当前 Genesis 只读 IK，不推进物理。`oracle_runners/run_lock_picking_policy.py --route-mode reindex --variation <variant> --audit-ik --part solve` 实际执行，原生 Task 成功即正常结束，允许仍抓持；`audit_lock_picking_robot.py` 独立复核连续状态、关节、抓持、碰撞及 success 时间窗口。历史完整释放流程及原证据不改写。
- `plan_hedgehog_object_oracle.py`、`audit_hedgehog_oracle.py`：物体证书与独立逐 tick 审计工具仍在本目录；执行入口为 `oracle_runners/run_hedgehog_oracle.py`。[已验收范围](../solvability_proof/hedgehog_in_cage/README.md)。
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
- `build_images.sh`、`push_images.sh`、`vendor_rcb.py`、`set_agent_egress.py`：镜像、参考工具及任务出网配置。
- `run_agent_batch.sh`、`regrade_trials.sh`：批量运行与重评分。
- `account_failure_check.py`、`log_mirror.py`、`mem_guard.py`、`scan_secrets.py`：账号异常检测、日志镜像、资源监控与产物密钥检查。
- `collect_batch_results.py`、`write_task_results.py`、`make_two_mode_report_zh.py`：收集结果并生成报告。

完整命令见 [Harbor 手册](../docs/rcb/README.md)。任务静态检查仍为 `bash ci_checks/run_all.sh`。

## 设计辅助（非物理证据）

[design_viewer/](design_viewer/) 为 Hedgehog、Horseshoe、Slotted Post Ring 的变体设计提供可交互的 3D 场景，计划见 [实施计划](../docs/tasks_simplifications/interactive_3d_impl_plan_zh.md)。它只读调用任务生成器，用 MuJoCo 3.14 Web Viewer（CPU，仅绑定 127.0.0.1）和 python-fcl 检查。结果只用于设计直觉，**不能**作为可解性证据、qualification 或成功标签，也不进入 simulator / rollout / 评分链路；Genesis 仍是唯一物理途径。变体注册进 registry 后自动出现在场景列表中。

```bash
conda activate topogym && export PYTHONNOUSERSITE=1   # 在 worktree 根目录运行
python -m scripts.design_viewer.view --scene hedgehog_in_cage_easy --port 18080
# VS Code「端口」面板转发 18080，浏览器打开 http://localhost:18080/
python -m scripts.design_viewer.exit_check --scene hedgehog_in_cage_very_easy --grasp 180 --roll 90 --lift-mm 5
python -m scripts.design_viewer.scenes --list                        # 构建并列出所有场景（结果缓存）
python -m scripts.design_viewer.mjcf --seconds 1                     # 每个场景的步长耗时、初始穿透、漂移
python -m pytest scripts/design_viewer -q                            # 行为测试（CPU）
```

- 浏览器：左键拖动旋转视角，右键平移，滚轮缩放；双击选中物体；Ctrl+右键拖动拉动物体（加 Shift 为水平面内），Ctrl+左键拖动旋转；空格暂停。
- 「TopoGym design」面板与终端使用同一套命令（终端输入 `help`）：切换场景、开关 2F-85 夹爪、放置夹爪（方位角、roll）、开合手指、夹持（grip）或固定（pin）选中物体、刺球出笼检查（结果方向显示为绿色箭头）、保存/读取位姿。
- `--set key=value` 覆盖 Hedgehog 模板（如 `window_widths=24`）、Horseshoe 模板或 Slotted 几何参数，不修改生成器。
- 产物：`runs/design_viewer/`（缓存、位姿、检查报告）。
