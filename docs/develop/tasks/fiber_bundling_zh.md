# 光纤收束

更新：2026-09-28（terminal）；历史 demo 状态为 2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

固定电源终端和被动细线保持连续，机器人只操作粗护套，使分叉端先进入闭环并完成整束穿环；需要逐步检查细线禁碰、抓持及受载稳定性。

当前源码：[任务与判据](../../../topogym/tasks/fiber_bundling/common.py) · [几何生成](../../../topogym/assets/geometry/fiber_bundling.py) · [穿孔历史](../../../topogym/utils/geometry/passage.py) · [子步接触](../../../topogym/world/physics/rigid_contacts.py)。参数与成功定义见[任务卡](../../../configs/task_cards/fiber_bundling.yaml)，统一运行入口见 [Simulator API](../modules/simulator_api_zh.md)。旧 bootstrap、robot_sequence 和 recording_adapter 不再是当前入口。

## 当前自动终态

`terminal_v4_fiber_ring_plane` 对 base/easy/medium/hard 启用 `goal_complete=True`。所有细芯必须按尖端到根部的材料顺序穿过环心平面，穿过时离环轴小于圆管中心线半径（孔最窄半径 + 管半径 = 17.48 mm），最后全部离环心平面超过管半径 + 细芯半径（5.2 mm）、留在出口侧；前护套端面按同一规则穿过环心平面，并越过环心 16 mm 清出；实际弯折角不超过 60°，连续满足默认 0.5 s。允许保持粗护套抓持。前护套采用 [2026-09-25 设计 §5.3](terminal_judgement_engineering_plan_20260925_zh.md#53-fiber-bundling) 的端面通过条件；旧任务卡的额外 30 mm 深度不用于本版本，历史验收记录不追溯修改。

**为什么从 v3 改成 v4（2026-09-29）。** v3 在环心前后各 5.2 mm 的入口/出口平面上检查离轴距离，并且都用孔最窄处的尺寸：细芯 ≤ 12.18 mm（13.479 − 1.2 − 0.1），前护套 ≤ 1.379 mm。可是入口平面在环前表面再往前 1.2 mm，那里圆管还没收窄。细芯在那里离轴 13–15 mm，继续前进会被圆管前侧的弧面导进孔里，却被 v3 判成没穿过。

历史 4/8/16 芯完整成功轨迹按 v3 只算 1/4、2/8、7/16 根穿过，差的全是尖端：过入口平面时离轴 12.3–14.9 mm，过环心平面时 ≤ 12.2 mm，已经在孔内。

在环心平面上，细芯中心要么在孔里（≤ 12.28 mm），要么在环外（≥ 22.7 mm），两者之间就嵌进圆管了。取圆管中心线半径作阈值，正好在这个不可能区间的中间，从环外绕过去的情况仍然判不通过。按 v4 重放，历史三条轨迹全部判成功。证据和重放脚本见 [v4 验证](../../../runs/test_results/fiber_terminal_v4_20260929/)。

每个刚体 solver 子步收集 native narrowphase 接触，几何角色按 MJCF 所属 link、局部位姿、形状和尺寸在 build 前匹配。Genesis 会复用 primitive mesh 的 metadata 名称，不能把该名称或导入顺序作为身份。机器人描述中的夹爪根 link 覆盖全部后代，包括手指、外壳、连杆；机械臂保持独立分类。任何夹爪—细芯接触（包括零力接触）立即失败，复用 Task/Env 的终止锁存，公共失败码为 `task_failed`，管理方原因是 `fiber_gripper_contact`。接触摘要缺失或任一子步、细芯/机器人几何覆盖不完整时，当前分支不确认成功；回溯到缺口前可恢复完整覆盖。

`goal_complete` 表示实现启用，不表示机器人已经完成任务或 60° 等阈值已完成物理标定；`thresholds_calibrated=False` 保留。穿孔轨迹仍采用 physics tick 采样与线性插值，子步接触也不声称连续时间 CCD。成功时 Task 输出 `task_success=True`、`terminated=True`、`reward=1`，Harbor 还会独立检查运行证据和预算。

2026-09-28 验证：80 项相关测试通过；全量 unit/contracts/architecture 为 555 通过、3 项既有失败，三项均在恢复本轮改动前的独立基线中复现。easy/medium/hard（seed=0，Panda + Robotiq）的 9 项 CUDA/Nyx 机制测试全部通过：每档出生与 80 ticks、夹爪轻碰细芯即失败、轻碰护套继续运行，以及各自的回溯。接触探针包含管理方位姿干预；成功路径测试使用合成状态，本轮没有新增完整机器人穿环成功或阈值标定。源码快照、修改坐标、哈希、逐项报告及三视角录像见[本轮验证报告](../../../runs/test_results/fiber_terminal_delivery_20260928/README.md)。Harbor 使用旧镜像时须重建才能载入此实现。

## 当前状态与边界

正式视频已覆盖稀疏 4 芯、标准 8 芯、密集 16 芯三个代表，环内半径均为 13.5 mm、细铜杆支架，每个变体三路无 UI 完整视频。目录为 `demos/fiber_bundling/varaition_<实例名>/<视角>/`；每个相机叶子目录一份 MP4。8 芯原视频直接迁移，4/16 芯从各自成功物理轨迹补录；均以辅助夹持保持末态。三例的两种时间步均完成穿环，严格全程线形对照仅 4 芯通过；这些代表不为任意随机参数提供资格。

## 变体与下一步

稀疏/标准/密集是线数家族，不要求三种 IK 机制。fixed 使用 4/8/16 芯和 R=13.5 mm；parameterized 分别采样 4–6/7–10/11–16 芯及 R=12.8–15.0 mm。300 个 seed 初态几何通过；IK、禁碰、受载稳定性、完整穿环和时间步对照必须逐实例补齐。

## 当前证据

- [稀疏 4 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-21_sparse_04_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/agentview/2026-09-21_sparse_04_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/front_oblique/2026-09-21_sparse_04_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/wrist/2026-09-21_sparse_04_r13p5mm_clean_v1_wrist.mp4)，各 116.7 秒。
- [标准 8 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/agentview/2026-09-18_standard_08_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/front_oblique/2026-09-18_standard_08_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/wrist/2026-09-18_standard_08_r13p5mm_clean_v1_wrist.mp4)，各 177 秒。
- [密集 16 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-21_dense_16_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/agentview/2026-09-21_dense_16_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/front_oblique/2026-09-21_dense_16_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/wrist/2026-09-21_dense_16_r13p5mm_clean_v1_wrist.mp4)，各 237.15 秒。
- [2026-09-19_variant_generation_audit](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 历史生成入口（已退役）

以下命令仅记录旧 demo 的来源，当前工作区已移除该入口，不能作为现有三档运行方式。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.generation \
  --seed 42 --family standard --mode parameterized \
  --output runs/environment-solvability/fiber_bundling/generated_seed42
```
