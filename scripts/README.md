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

- `run_buzz_wire_policy.py`、`run_cast_coil_policy.py`、`run_cast_keyhole_policy.py`、`run_lock_picking_policy.py`：冻结源码并执行各任务策略。
- `run_hedgehog_policy.py`、`run_interlocked_claws_policy.py`、`run_rigid_reference_policy.py`：几何准备及已开放的反馈策略流程。
- `run_solvability_workflow.py`：按阶段执行候选策略与可解性研究；独立审计工具已归档，原有证据保留。
- `test_scripted_policy_rollout.py`：`act(obs)` 样板执行入口，输出至 `task_rollouts/`。
- `test_policy_cube_transfer.py`：低层方块执行与控制模式矩阵入口；其 `snapshot()` 被多个 rollout 管理脚本复用。

以上两个 `test_` 命名脚本保留实际执行职责；共享夹具在 [tests/fixtures/](../tests/fixtures/)，不依赖已归档的测试套件。
用法见 [本地策略说明](../topogym/planning/README.md) 与 [本地执行入口](../tests/README.md)。

## Harbor 构建、运行及结果处理

- `sample_difficulty_instances.py`：13 项编号选择器、每难度随机抽样、源码快照及冻结 manifest；默认全任务、每档 1 个样本。
- `difficulty_eval.py`：难度评测调度；解析参数、准备任务、物理 preflight、认证 canary、逐次 `harbor run`、中断处理和恢复；默认 agent 预算 21600 秒，使用公共 `harbor_templates/topogym/`。
- `../bash_scripts/run_difficulty_trials.sh`：兼容启动入口，仅选择 Python 解释器并透传参数给 `difficulty_eval.py`；原有命令保持可用。
- `topogym_mk_task.py`、`topogym_mk_limited.py`：生成 unlimited / limited 任务。
- `build_images.sh`、`push_images.sh`、`vendor_rcb.py`、`set_agent_egress.py`：镜像、参考工具及任务出网配置。
- `run_agent_batch.sh`、`regrade_trials.sh`：批量运行与重评分。
- `account_failure_check.py`、`log_mirror.py`、`mem_guard.py`、`scan_secrets.py`：账号异常检测、日志镜像、资源监控与产物密钥检查。
- `collect_batch_results.py`、`write_task_results.py`、`make_two_mode_report_zh.py`：收集结果并生成报告。

完整命令见 [Harbor 手册](../docs/rcb/README.md)。任务静态检查仍为 `bash ci_checks/run_all.sh`。
