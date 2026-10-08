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

## Oracle 对 GPU 数值噪声的敏感度（诊断，不是评分）

`oracle_noise_sensitivity.py` 跑一次 oracle（闭环）或回放一条已录轨迹（开环），用两种方式模拟换 GPU 型号后的数值差别：
`--action-noise-rad` 在每个控制步给机械臂关节目标加 N(0, σ)；`--tolerance-scale` 把 IPC 的 Newton 与线性求解容差乘以一个系数。
Session 由发布配置的环境输入构建，报告记录出生状态 hash 以确认与冻结实例一致。目前支持 rope_threading very_easy / easier。

```bash
python tests/oracle_noise_sensitivity.py --tier very_easy --mode closed --reference <评分轨迹.npz> \
  --output <新目录> --solution <打包 solution 目录> --action-noise-rad 1e-6 --noise-seed 1
```

不要用 `FiniteElementStateAccessorFeature.copy_from` 往 IPC 写回加噪的绳状态：即使噪声为 0，写回一次后下一步绳就偏 0.38 mm、
9.5 mm/s（回读的位置和速度不变），每步写回会让绳一直静止不下来（2026-10-07 实测）。
