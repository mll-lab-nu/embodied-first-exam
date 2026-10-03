# Oracle 执行入口

从仓库根目录执行 `python scripts/oracle_runners/<脚本名>.py --help`。原有参数不变；每个管理入口冻结当前源码，然后从快照中的同一子目录启动 worker。目录迁移不修改 `runs/`、`task_rollouts/`、`solvability_proof/` 的源码快照、历史命令、哈希或结果。

| 脚本 | 职责 |
| --- | --- |
| `run_lock_picking_policy.py` | 三档 Lock reindex 策略及历史 medium 策略，标准 Env 执行，可录制逐动作 IK/FK |
| `run_cast_coil_policy.py` | Coil 原三档策略，以及 very_easy 大齿直插、easier 挡板加横移装配策略 |
| `run_cast_keyhole_policy.py` | Keyhole 拾取、换抓和放置策略 |
| `run_buzz_wire_policy.py` | Buzz 策略及已编译参考动作执行 |
| `run_hedgehog_oracle.py` | 从 home 执行带显式辅助抓持选项的 Hedgehog oracle |
| `run_horseshoe_policy.py` | Horseshoe 几何、IK 和机器人分阶段诊断 |
| `run_interlocked_claws_policy.py` | Claws very_easy / easier 的辅助抓持参考策略；旧三档仍调用原几何及摩擦抓持诊断 |
| `run_interlocked_claws_simplified_policy.py` | 两档简化 Claws 的源码冻结、连续几何检查、双臂预检和 SegmentRunner 执行 |
| `run_hedgehog_policy.py` | Hedgehog 旧几何／反馈诊断入口，保留其原有阶段限制 |
| `run_rigid_reference_policy.py` | Hedgehog／Claws 共用的几何、抓持诊断管理器 |
| `run_solvability_workflow.py` | 按任务提供的 stage factory 执行诊断或连续证明候选 |

只读规划器 `scripts/plan_*`、独立审计器 `scripts/audit_*`、通用接口测试及源码快照工具 `scripts/test_*` 继续放在上级目录。difficulty trials 使用独立的 Harbor 执行链，不调用这些 oracle runner。

## Claws 两档简化变体

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_interlocked_claws_policy.py \
  --variant very_easy --seed 0 \
  --output runs/test_results/claws_very_easy_new

.venv-gs121-nyx/bin/python scripts/oracle_runners/run_interlocked_claws_policy.py \
  --variant easier --seed 0 \
  --output runs/test_results/claws_easier_new
```

默认从任务已确认的双臂预抓姿态开始，使用原 ALOHA、`contact_weld_v1`、CUDA、Nyx 四视角和默认物理时序。策略先通过双指接触取得辅助抓持，再执行两件相对通路，最后让棕色件整体进入绿色目标区并满足当前 Task 的低速保持条件。该流程不包含 home 到预抓姿态的接近动作，也不以“已分离”代替 Task success。

`--part geometry` 只检查物体通路，`--part acquire` 只执行辅助抓持准入，默认 `--part solve` 要求 Task success 且执行证据完整。`--no-rgb` 显式关闭录像；若使用非默认 `--physics-dt` / `--control-decimation` / `--solver-substeps`，结果仅代表所记录的时序。输出目录必须尚不存在。

输出保存源码快照和哈希、几何报告、原生 IK／网格碰撞预检、逐 tick 状态、资源占用、阶段误差、Task 结果及公共录制产物。物体通路做连续检查；机械臂预检是采样检查，二者不能混称连续机器人无碰撞证明。系统内存达到 90% 时仅停止本次 worker，保留失败证据。

回归入口：`.venv-gs121-nyx/bin/python ci_checks/test-interlocked-claws-simplifications.py`。实际验收状态和形状说明见 [Claws 任务页](../../docs/develop/tasks/interlocked_claws_zh.md)。两档先作为独立具名入口接入，保留旧 `base` / `seeded` 三档含义。

## Coil 正方体变体

`--variant very_easy` 和 `--variant easier` 选择两套已确认形状。102 mm 的源模型等比缩为 51 mm，供 ALOHA 从两侧外壁抓取；easier 的 18 mm 横移随之缩为 9 mm。两者要求 `--policy feedback`（默认值），保留原任务的落桌、释放、撤手与稳定判据。`base` / `seeded` 仍选择原三档。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_cast_coil_policy.py \
  --variant very_easy --seed 0 \
  --output runs/test_results/cast_coil_very_easy_new

.venv-gs121-nyx/bin/python scripts/oracle_runners/run_cast_coil_policy.py \
  --variant easier --seed 0 --compute-backend cpu --no-rgb \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40 \
  --output runs/test_results/cast_coil_easier_cpu_new
```

第一条使用默认时序、CUDA 和 Nyx 四视角录制；第二条显式选择 CPU 无 RGB 及 25 ms tick，不能将其结果称为默认时序或录像验收。输出目录必须尚不存在。入口冻结源码、记录资源占用，并在系统内存达到 90% 时只停止本轮 worker。`run_report.json` 包含实例、资产哈希、抓持事件、阶段到位误差和 Task 结果；实际执行资格见 [Coil 任务页](../../docs/develop/tasks/cast_coil_zh.md)。

回归：`python ci_checks/test-cast-coil-simplifications.py` 与 `python ci_checks/test-cast-coil-variants.py`。这些检查覆盖几何、连续平移通路、夹爪尺寸、注册和终态反例，不代替完整物理执行。

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
