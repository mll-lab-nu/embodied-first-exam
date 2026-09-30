# 本地 rollout 共享夹具

2026-09-29：独立 `unit`、`contracts`、`architecture`、`recording_data`、`integration` 测试、
公共测试配置及研究证据工具已移入 [研究工具归档](../legacy/research_tools_20260929/README.md)。
这些历史测试不再由活动目录默认收集；原测试说明保存在 [归档说明](../legacy/research_tools_20260929/tests/README.md)。

当前 `fixtures/` 保留本地 rollout 使用的临时任务、策略和材料夹具。
`control_targets.py` 中的 `rotation()` 与 `targets_and_action()` 从旧 integration 测试提取，
由 `scripts/test_policy_cube_transfer.py` 直接导入，函数行为保持一致。
不将 `legacy/` 加入 `PYTHONPATH`，不从归档中加载运行依赖。

## Scripted policy 管理调度验收

```bash
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py --case pick_place --seed 0
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py --suite
```

管理方使用 `SegmentRunner.run_policy()` 执行 `obs → policy.act(obs) → env.step(action)`。
每次创建新的 `task_rollouts/` 目录，保存源码身份、实际轨迹与 Nyx 视频。
默认长流程使用显式 25 ms tick / decimation 1 / 40 solver substeps；不改变 simulator 默认时序。

## Segment 与低层方块 policy 验收

```bash
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/cube_transfer_new --seeds 0 --split \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/segment_default_matrix_new --matrix --jobs 1 \
  --tracking-hold-seconds 0
```

这些命令要求实际 Genesis / CUDA / Nyx，输出目录须不存在；它们不是 CPU 静态检查。
Harbor 的任务检查与评分文件在 `ci_checks/` 和 `tasks/*/tests/`，仍按 [Harbor 手册](../docs/rcb/README.md)执行。
