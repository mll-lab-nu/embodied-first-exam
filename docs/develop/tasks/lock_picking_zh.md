# 开锁

2026-09-30 判据修正：v3 允许正常靠壁及几何上可穿孔的倾斜，取消额外 0.1 mm 空隙和独立 1° 倾角门槛，使用 10 μm 接触数值容差；同时要求有限钥匙杆仍贯穿全部四片板。前齿穿出 END 至少 1 mm、齿槽和转盘约束、连续 0.5 s 保留，不强制释放。三档共 4789 个已保存状态离线重算，释放后末态全部通过；没有新增物理执行。当前 `terminal_v4_bore_contact_default_success` 保留这些判据，并统一默认开启 `goal_complete=True`，不再受物理资格限制。详见[当前 success 条件](success_conditions_zh.md)和[重算结果](../../../runs/test_results/lock_contact_fix_20260930_01/replay.json)。历史报告与旧成绩不变；新实例使用新 terminal 参数，旧完整参数不能直接套用新修订。

2026-09-30 可解性补充：[三档完整机械臂流程与 IK 证明](../../../solvability_proof/lock_picking/2026-09-30_robot_process/README.md)。默认参数、seed 0 的 easy／medium／hard 已从 home 实际完成抓取、1／2／3 次回退、支撑换抓、END 插入、松手撤离与静置，仿真时间 124.7／159.2／194.7 秒，逐动作 IK 查询 972／1,270／1,571 次，独立逐 tick 复核通过。使用 CPU float32 和 `contact_weld_v1` 辅助抓持，显式无 RGB；原生 `task_success=False`，不增加正式 benchmark 成功数量。[上一批物体路径与名义 IK](../../../solvability_proof/lock_picking/2026-09-30_object_ik/README.md)及历史视频参考保留。

2026-09-29 相机：Panda 默认使用任务专属主机位，完整覆盖钥匙、三张圆盘与终点板；`front_oblique` 从机构另一侧放大圆盘孔槽区域。v2 两机位分别位于机构的 (+x, -y) 与 (-x, +y) 两侧。
[相机配置](../../../topogym/config/profiles/camera_configs/lock_picking_observation.yaml) ·
[最新两侧投影与检查](../../../runs/test_results/task_camera_study_20260929/opposite_sides_v2/README.md) ·
[Nyx 补拍命令](../../../runs/test_results/task_camera_study_20260929/README.md)。
当前通过几何取景及孔槽表面采样遮挡检查，尚未取得新机位 Nyx 初始化帧。

> 2026-09-27 用户授权恢复历史物理配置：medium 更新为 `historical_physics_v2`，保留当前实验室摆位，恢复 150 mm 盘距、495 mm 握柄偏移、7.5 mm 孔半径与历史两次回退槽形。公共机构恢复转盘／钥匙质量 0.12 kg、盘阻尼 0.03、接触摩擦 0.01、铰链附加惯量 0、接触时间常数 0.0025 s；参数计入实例身份。当前完整机器人验收以[本轮报告](../../../task_rollouts/lock_assist_20260927/README.md)为准，历史成功不自动继承。2026-09-26 的场景资产字节一致结论仅适用于当时版本。

场景入口核对：2026-09-26；下方历史演示记录：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

Panda + Robotiq 从承托架抓起钥匙，穿过被动锁片、执行必要回退，抵达 END 后释放静置。基础版盘距 150 mm、三齿、两次必要回退。

当前源码：[common.py](../../../topogym/tasks/lock_picking/common.py) · [easy](../../../topogym/tasks/lock_picking/lock_picking_easy.py) · [medium](../../../topogym/tasks/lock_picking/lock_picking_medium.py) · [hard](../../../topogym/tasks/lock_picking/lock_picking_hard.py)。参数入口：[任务卡](../../../configs/task_cards/lock_picking.yaml)。旧 runner、planner、certificate、evaluator、variants、verify_variants、agent_adapter 模块及 `demos.environment_bootstrap.lock_picking` 入口已不在当前目录，不能沿用旧启动命令。

当前三档执行入口为 `scripts/run_lock_picking_policy.py --variation easy|medium|hard --route-mode reindex --part solve --grasp-style side --grasp-roll-deg -45 --physics-dt .1 --solver-substeps 160 --control-decimation 1 --compute-backend cpu --no-rgb --audit-ik --output <new_run>`；hard 另加 `--endpoint-depth 4.10`，其余两档默认 4.08。随后使用 `scripts/audit_lock_picking_robot.py --run <run> --output <new_audit>` 独立复核。[完整可复制命令](../../../solvability_proof/lock_picking/2026-09-30_robot_process/README.md#复现)。三档策略为 `topogym/planning/lock_picking/reindex_policy.py`，复用既有拾取／换抓动作；原 medium 路线保留在默认 `--route-mode historical`。显式采用 100 ms World tick／160 子步，积分子步为 0.625 ms；不代表 simulator 默认时序资格。物理推进、自动 assist、segment 和可选录像全部使用公共模块，`--no-rgb` 不作为录像验收。

恢复后的 seed 0 已从默认 home 完成 CUDA／Nyx 连续执行，156.4 s，包含自动拾取、两次回退、支撑换抓、终点插入与释放静置：[完整视频](../../../task_rollouts/lock_assist_20260927/lock_picking/trail_12_medium/full_solve.mp4) · [状态与 assist 报告](../../../task_rollouts/lock_assist_20260927/lock_picking/trail_12_medium/README.md)。独立物理观测通过，正式 terminal 的资格门仍未完成，不宣告 benchmark success。

## 历史演示状态与边界

标准外观三视角 159.35 秒来自成功物理状态重渲染；夹爪被动连杆按记录开合量重建，没有新增一次动力学成功。当时 runner、planner、certificate、grasp、oracle、evaluator 由任务包持有；该历史组织方式不代表当前目录结构。

## 历史变体证据

F1/F2/F3 为 1/2/3 次回退家族，含 S/M/L 固定代表；支持具名 seed、条件尺寸域、确定性拒绝重试和保存/重载。256 个 seed 几何/IK 通过，随机后代的机器人场景碰撞、接触动力学与完整流程仍待验收。

## 历史演示证据

2026-09-21 按 `varaition_<id>/<camera>/` 整理视频。标准外观仍保留完整三视角；F1/F3 恢复已有正斜视角 IK 预演，文件名含 `kinematic`，不计为完整物理 demo。

- [2026-09-18_standard_150mm_purple_trace_v1](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1)
- [2026-09-19_seed_generator_v1](../../../runs/demo_metadata/lock_picking/2026-09-19_seed_generator_v1)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 历史生成入口（当前不可用）

以下为历史记录，所调用的 `variants` 模块已移除；当前场景选择请使用[三档部署记录](variation_deployment_implementation_20260925_zh.md)中的统一入口。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.lock_picking.variants --seed 42 --output runs/my_lock_instance
```
