# Knot Untying oracle

`robot_oracle.py` 在任务目录的 `rcb_topogym.Session` 中执行 ALOHA 纯摩擦抓取，
`route_rule.py` 从实测材料中心线选择删交叉／两端拉开的动作，`kinematics.py` 提供 IK。
执行入口统一在 `scripts/oracle_runners/`。几何交叉减少不等于成功；必须得到原生
`task_success`，随后用正式冻结实例在新进程回放。

当前证据、导入产物与剩余物理验证见 [任务页](../../../docs/develop/tasks/knot_untying_zh.md)。
2026-10-03 交接包已导入 `runs/test_results/knot_handoff_20261003/`，保留原始字节和 SHA-256 清单。
统一归档在 [solvability_proof/knot_untying](../../../solvability_proof/knot_untying/README.md)。
未指定 `--instance` 时优先使用归档内与当前代码兼容的 i00 实例；完整 `evidence/` 需随项目传递。

## 执行和回放

下列命令需要有兼容 Genesis 1.2.1、Nyx 和 CUDA IPC 的 Python；正式 IPC 存档还核对
pyuipc 版本和 libuipc build，不绕过身份检查。

本机已验证的容器入口如下；在仓库根目录运行。随后可将最后的 Python 命令替换为下方的
medium、hard 或 audit 命令。编译与 Nyx 缓存使用可写目录，容器内沿用当前用户身份。

```bash
docker run --rm --runtime nvidia --gpus all --user "$(id -u):$(id -g)" \
  -e NVIDIA_DRIVER_CAPABILITIES=all -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/work \
  -e XDG_CACHE_HOME=/work/runs/knot_cache \
  -e NUMBA_CACHE_DIR=/work/runs/knot_cache/numba \
  -e MPLCONFIGDIR=/work/runs/knot_cache/matplotlib \
  -v "$PWD":/work -w /work ghcr.io/luigivamper/rcb-topogym:0.2.6-cu128 \
  python scripts/oracle_runners/run_knot_oracle.py \
    --variation knot_untying_easy --output runs/test_results/knot_easy_new
```

```bash
KNOT_INPUT=solvability_proof/knot_untying/2026-10-03_frozen_replay/evidence

python scripts/oracle_runners/run_knot_oracle.py \
  --variation knot_untying_medium \
  --instance "$KNOT_INPUT/instances/medium/instance_norgb.json" \
  --output runs/test_results/knot_medium_new

python scripts/audit_knot_oracle.py \
  --instance "$KNOT_INPUT/instances/medium/instance.json" \
  --traj "$KNOT_INPUT/runs/medium03/trajectory.npz" \
  --repeat 2 --output runs/test_results/knot_medium_replay_new

python scripts/oracle_runners/run_knot_branching.py \
  --variation knot_untying_hard \
  --instance "$KNOT_INPUT/instances/hard/instance_norgb.json" \
  --output runs/test_results/knot_hard_new
```

所有输出目录必须尚不存在。入口冻结实际源码、任务工具和机器人资源，worker 使用该快照；
`resources.jsonl` 记录 CPU／内存，只有系统内存达到 90% 才停止本轮子进程。
正式回放须使用启用 RGB 的 `instance.json`，开发可使用同物理配置的 `instance_norgb.json`。
Nyx 初始化不等于已录视频；本套工具记录动作与中心线，不另外实现录像流程。

运行产物为 `report.json`、`steps.jsonl`、`centerlines.npz`、`trajectory.npz`。
轨迹保留每条 action 的实际物理 tick 数；原生成功会使最后一个控制步短于 25 ms。
只在原生成功时执行器返回 0。`audit_knot_oracle.py` 调用任务工具原有 `replay --strict`，
检查所有回放原生成功、正式初态 exact 和动作身份，写 `replay_audit.json`，失败返回非零。
只读观察器每 20 个 action 及不足一个控制步的末尾 action 更新 `replay_progress.json`，
同时记录原生终态指标，每遍完成写 `replay_passes.jsonl`；
动作、实际 tick 请求、原生 replay 循环和结束规则保持由任务工具处理。
单次回放的 `deterministic=true` 不表示重复运行已确定；至少两次才记录 determinism_tested。
GPU 非逐位确定性本身不否决全部回放的原生成功，与任务 verifier 保持一致。

## 分支与经验

- 默认闭合开口为 **5 mm**，是两指之间的实际宽度；旧 Env 执行器的原生夹爪坐标不可直接搬来。
  零开口曾压翻绳的四面体，CLI 拒绝零值。两端拉开默认离端头 **35 mm**，避开 medium 的端头压坏。
- hard 默认 `full_pull=True, max_pull=.55`。交叉刚从 4 降到 3 就停会留下拉紧小卷；完整拉绳
  来自物体路线经验，机器人成功须另验。`--no-full-pull` 可显式复现旧策略。
- 分支候选包含 0.65 m 完整拉绳、方向调整和端部抓点调整；跨度接近抓点间材料长度的 95%
  或 IK 到达边界时停止延伸，不放宽原生体积有效性或终态门槛。
- `branching.py` 在每个决策点补全 Env checkpoint；当前动作或后续决策失败都会回退并换候选。
  `branching.json` 保留全部尝试，最终 trajectory 只保留当前有效分支，仍须新进程回放认证。
- 搜索默认允许连续 **2 次操作未取得本分支更低的交叉数**（`--max-nonprogress-decisions 2`），
  支持交叉暂时不变或增加后的恢复。取得新低会刷新预算，`4→5→4` 的振荡不会刷新；
  超过预算只表示该搜索分支耗尽，不是原生物理失败。8 层决策／30 次总尝试的上限仍保留。
  小于 12 cm 的紧圈只写诊断标记，不再直接回退；`--tight-curl-m` 仅调诊断阈值。
  medium / hard 在每个节点交替尝试删交叉和两端拉开的候选，旧规则只决定优先级。
  `branching.json.search_policy` 标明 `bounded_nonmonotonic_v1`；旧运行快照不随工作区修改。
- `checkpoints/d<k>_a<n>.pkl` 是受信本地控制器存档及动作前缀，不是跨进程原生物理存档。
  `--resume <文件>` 重建同一实例，回放全部前缀，核对绳形和关节后继续；需要原来的模拟时间。
  不接收缺少身份与 tick 校验的旧格式 checkpoint。
- 默认自动候选耗尽即退出；`--wait-hours 6` 会在根决策候选耗尽后等 `control/next.json`。
  文件须为候选对象列表，例如 `[{"max_pull": 0.7, "full_pull": true}]`；只收参数，不热加载代码。
  子决策耗尽先返回上游，不会因等待新参数而阻止上游回溯。

## 冻结实例

仓库旧 `tasks/` knot 存档早于 `contact_eps_velocity=.001` 修正，与当前代码的
physics_options 不同。已有交接实例可直接用；确需重新生成时：

```bash
python scripts/prepare_knot_instances.py \
  --variations easy medium hard --seed 0 --output runs/test_results/knot_instances_new
```

该入口串行调用 `export-ipc-state` 和 `make-instance`，保存完整 IPC 原生存档和正式／开发两份配置。
输出新的实例，不改 `tasks/` 的冻结 benchmark。重建后须重新核对轨迹身份及回放结果。

CPU 回归：`python ci_checks/test-knot-oracle.py` 和 `python ci_checks/test-oracle-runners.py`。
它们不授予物理成功资格。当前范围也不包括多 seed、网格／步长收敛或逐子步机器人禁碰审计。
