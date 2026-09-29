# Cast Coil

更新：2026-09-28。全项目进度见[当前进度](../../progress/current_zh.md)，历史视频直链见[Demo 目录](../../../demos/README.md)。

## 当前三档 policy 与可解性验收

按 [action / IK 计划](task_variant_solutions_action_ik_zh.md#coil)，本轮验收要求是具名变体的 policy 经 `SegmentRunner → Env.step → Genesis IK → 物理执行` 达到真实 `task_success`。关闭 RGB 和视频，保留全部当前配置 tick 的状态、动作、冻结源码和资产哈希。使用 unlimited 对象状态及自动 `contact_weld_v1` 抓持，不能称为纯摩擦抓持证明。

当前入口：[CastCoilPolicy](../../../topogym/planning/cast_coil/policy.py)、[执行 CLI](../../../scripts/run_cast_coil_policy.py)、[独立复核 CLI](../../../scripts/audit_cast_coil_policy.py)。从默认 home 接近桌面自由零件，双指接触后取得自动抓持；以实测对象/TCP 关系执行装配，放桌、解除辅助、撤手，等待原 Task 的释放与稳定判据。

| 注册入口 | 几何／反向装配路线 |
|---|---|
| `cast_coil_easy` | `baseline_assembly`；插入 → 逆 90° → 闭合 |
| `cast_coil_medium` | `axial_screw_turn`；插入 → 旋转同时撤销模板指定的 9 mm 轴向位移 → 闭合 |
| `cast_coil_hard` | `split_turn_offset`；插入 → 逆后 45° → 撤销 9 mm 错位 → 逆前 45° → 闭合 |

phase 时钟受实测对象误差约束；超出预算暂停推进，超时明确失败。不能用名义路线已走完代替对象到位。模板与路线一起选择，medium/hard 不使用 `variant_route` 的 6 mm 默认参数。

medium/hard 的放置目标使用**抓取前实测的桌面稳定姿态**。抓取后的金件可能倾斜；将这一姿态直接向下平移，会要求装配后的银件进入桌面约 0.268 / 0.393 mm，导致到位检查无法通过。[目标几何核对](../../../runs/test_results/cast_coil_ik_20260928/placement_geometry_check.json)和两项回归测试覆盖这个问题；修正不改变任务几何或 success 阈值。

快速运行配置为 CPU、无 RGB、25 ms tick、40 solver 子步/tick、1 tick/action：保留 40 Hz 动作和 0.625 ms 积分子步，但 Task、assist 检查及历史记录为 40 Hz，**不同于默认的 400 Hz**。完整默认时序仍可不传三项时间参数直接运行。两种配置的证据不互相替代；同一有限实例的 success 不扩展为随机参数域保证或半步物理资格。

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 QD_NUM_THREADS=1 \
  .venv-gs121-nyx/bin/python scripts/run_cast_coil_policy.py \
  --variant medium --seed 0 --no-rgb --compute-backend cpu \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40 \
  --output runs/test_results/cast_coil_medium_new_run

.venv-gs121-nyx/bin/python scripts/audit_cast_coil_policy.py \
  runs/test_results/cast_coil_medium_new_run
```

**三档已完成物理仿真验收：`task_success=true`，独立复核全部通过。** easy / medium / hard 的模拟时间分别为 162.900 / 181.300 / 167.250 s，最终相对位置误差分别为 0.176 / 0.206 / 0.190 mm，均已解除辅助、撤手并稳定放桌。详见 [2026-09-28 验收报告](../../../solvability_proof/cast_coil/2026-09-28/README.md)和[机器汇总](../../../solvability_proof/cast_coil/2026-09-28/summary.json)。easy 的最终策略在成功日志上逐项复现全部 6516 次 action；medium/hard 使用最终源码实际执行。三条理想对象路线另有 [连续几何证书](../../../runs/test_results/cast_coil_ik_20260928/reference_geometry.json)，它不代替机器人运行。碰撞盒采样仍有微米级重叠，详见报告；本轮不声称连续时间无穿透。

CPU 快照复制增加了保留独立数组的 layout-aware 读取，仍逐 tick 读取原有状态，不删历史。实际 579 个引擎缓冲区通过 [逐字节对比及恢复](../../../runs/test_results/cast_coil_ik_20260928/fast_copy_probe.json)；同场景 [20 次快照对照](../../../runs/test_results/cast_coil_ik_20260928/copy_benchmark.json)由 2.0–2.3 s 降到 0.96–1.00 s。该性能数字不含完整 rollout、IK、证据写入或建场景。

## 任务与实现

ALOHA 双臂将分离的金银卷绕零件装配成整体，放桌、释放、撤手并静置；也保留拆解目标。当前原型不等于官方八步路线复刻。

源码：[几何](../../../topogym/assets/geometry/cast_coil.py) · [Task 与原成功判据](../../../topogym/tasks/cast_coil/common.py) · [对象参考运动](../../../topogym/planning/motions/cast_coil.py)。
参数入口：[任务卡](../../../configs/task_cards/cast_coil.yaml)；当前场景通过 `topogym.simulator.Env` 创建，上述 CLI 提供完整机器人执行。

视频按 `demos/cast_coil/varaition_<变体 ID>/<camera>/` 保存，`varaition_` 沿用项目约定拼写；基础装配版为 `varaition_baseline_assembly`。每个视角只保留一份独立 MP4，配置、轨迹和验收报告放在 `runs/demo_metadata/cast_coil/`。`robot_archive` 支持 `--variant-id` 指定代表款目录，默认按实际几何 ID 区分实例；保持双步长物理验收要求，生成直接视频链接，不生成 HTML。单步长通过的补录会单独注明资格范围。

## 2026-09-21 历史状态与边界

基础装配版有 33.15 秒五视角和半时间步检查，含预抓取及接触后辅助抓持。agent adapter 从 home 与桌面自由物体开始，不启用相同的辅助抓持；其 pilot evaluator 通过也不等于完整物理资格。

9 月 21 日三个固定代表分别重新完成连续物理装配、放桌、解除辅助与静置，并补齐五路同步视频：`varaition_eccentric_turn`（33.15 s）、`varaition_split_turn_offset`（35.15 s）、`varaition_axial_screw_turn`（33.15 s）。本次偏心代表使用 1.25 ms，另两族使用 2.5 ms；每族只执行一档时间步，不视为新双步长验收或随机参数域合格。视频从各自实测状态重渲染，基础版仍单独保留。

2026-09-21 已补齐三个固定家族的完整装配视频，每族五视角，与基础版合计 20 个 MP4。偏心回转 33.15 秒、分段回转错位 35.15 秒、轴向螺旋回转 33.15 秒；均从双轴分离初态执行至落桌、释放、撤手和静置。新增视频为各自连续物理状态的重渲染，15 路均通过哈希、完整解码、帧数同步和首末状态检查。偏心回转本次使用 1.25 ms，另两族使用 2.5 ms；三者通过对应单次执行检查，本次未重新完成成对半时间步验收。

## 变体与下一步

cast_coil_seed_v2 固定三种 9 mm 核心：偏心回转、45°回转→错位→45°回转、轴向螺旋回转；族内尺寸、位置/yaw、质量条件域联动。48 个几何样本、12 个随机双臂规划通过；新代表 6 次物理运行仅 4 次满足严格归档门槛，尚无全随机域物理保证。

## 当前证据

- [2026-09-17_aloha_full](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full)
- [2026-09-19_seed_generator_validation_v2](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2)
- [2026-09-21_variation_restore_v1](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1)
- [2026-09-21 三族完整执行与录制](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1)
- [目录、录制与来源检查](../../../runs/demo_metadata/cast_coil/2026-09-21_publication_review_v1/validation.json)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

新验证必须使用新输出目录，不能覆盖既有运行。旧 `topogym.tasks.cast_coil.variants` 和 `demos.environment_bootstrap.cast_coil` 已不再是当前可用入口。
