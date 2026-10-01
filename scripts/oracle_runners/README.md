# Oracle 执行入口

从仓库根目录执行 `python scripts/oracle_runners/<脚本名>.py --help`。原有参数不变；每个管理入口冻结当前源码，然后从快照中的同一子目录启动 worker。目录迁移不修改 `runs/`、`task_rollouts/`、`solvability_proof/` 的源码快照、历史命令、哈希或结果。

| 脚本 | 职责 |
| --- | --- |
| `run_lock_picking_policy.py` | 三档 Lock reindex 策略及历史 medium 策略，标准 Env 执行，可录制逐动作 IK/FK |
| `run_cast_coil_policy.py` | Coil 三档反馈策略与基础装配策略 |
| `run_cast_keyhole_policy.py` | Keyhole 拾取、换抓和放置策略 |
| `run_buzz_wire_policy.py` | Buzz 策略及已编译参考动作执行 |
| `run_hedgehog_oracle.py` | 从 home 执行带显式辅助抓持选项的 Hedgehog oracle |
| `run_horseshoe_policy.py` | Horseshoe 几何、IK 和机器人分阶段诊断 |
| `run_interlocked_claws_policy.py` | Claws 几何及摩擦抓持诊断，调用共享刚体入口 |
| `run_hedgehog_policy.py` | Hedgehog 旧几何／反馈诊断入口，保留其原有阶段限制 |
| `run_rigid_reference_policy.py` | Hedgehog／Claws 共用的几何、抓持诊断管理器 |
| `run_solvability_workflow.py` | 按任务提供的 stage factory 执行诊断或连续证明候选 |

只读规划器 `scripts/plan_*`、独立审计器 `scripts/audit_*`、通用接口测试及源码快照工具 `scripts/test_*` 继续放在上级目录。difficulty trials 使用独立的 Harbor 执行链，不调用这些 oracle runner。

## Lock 的结束规则

`--part solve` 以原生 Task 的 `task_success=True` 且 `terminated=True` 为完成标准。正常 `env_terminal` 会收尾并记录 `status="task_success"`；不再等待 policy 发出最后的松手／撤离动作，也不在终止后继续 step。任务失败、超时、策略错误或证据不完整仍会失败。

`policy_done` 只表示策略动作结束，不能代替 Task success。`--part pickup` 可以独立得到 `pickup_passed`，此时报告仍明确记录 `task_success=False`。`policy_completed` 和 `released_at_end` 分别记录动作完成和释放状态；成功时二者可以为 false。原先独立的 0.2 mm 释放验收不再作为 runner 的成功标准，几何判定统一使用当前 Task 的孔壁接触规则。

例如，使用已有 easy 参考流程的执行参数启动一个新实验：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_lock_picking_policy.py \
  --variation easy --route-mode reindex --part solve \
  --grasp-style side --grasp-roll-deg -45 \
  --physics-dt .1 --solver-substeps 160 --control-decimation 1 \
  --compute-backend cpu --no-rgb --audit-ik \
  --output runs/lock_oracle_success_new

.venv-gs121-nyx/bin/python scripts/audit_lock_picking_robot.py \
  --run runs/lock_oracle_success_new --output runs/lock_oracle_success_new_audit
```

medium 使用 `--variation medium`；hard 使用 `--variation hard --endpoint-depth 4.10`。这些参数来自历史物理流程，目录迁移及收尾回归不代表新增了三档真实执行验收。

新报告标记 `completion_contract="task_success"`。审计会从保存的每个 tick 重算 Task 稳定窗口并核对原生结果，同时保留 home 起点、连续性、IK/FK、双指接触、必要回退和碰撞检查；末次释放不是必需项。旧报告没有该字段，仍按原 `route_completed`、完整释放阶段和释放后静置规则审计，不追溯改判。复现旧流程应使用旧 run 自己的 `source_snapshot/scripts/...` 入口。

CPU 回归：`python ci_checks/test-oracle-runners.py`，覆盖成功时在松手前正常停止、失败／超时、未完成稳定窗口、仅拾取、历史审计边界，以及迁移入口与快照路径；不运行新的物理仿真。
