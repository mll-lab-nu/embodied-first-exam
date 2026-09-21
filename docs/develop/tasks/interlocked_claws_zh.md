# 双爪互锁

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

两件互锁刚体由 ALOHA 双臂完全拆开并短暂停稳即完成，允许继续抓持，不要求搬运、落桌或松爪。新建 agent 任务包采用 spec v5 / `pilot_claw_separation_v2`；历史任务包和结果不追溯改变。当前 A0 为 Genesis 原始爪；B0 同形双螺旋爪和 C0 等尺寸双窗为 MuJoCo 固定原型。

源码：[geometry.py](../../../topogym/tasks/interlocked_claws/geometry.py) · [scene.py](../../../topogym/tasks/interlocked_claws/scene.py) · [variants.py](../../../topogym/tasks/interlocked_claws/variants.py) · [agent_adapter.py](../../../topogym/tasks/interlocked_claws/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/interlocked_claws.yaml)；场景入口：`python -m demos.environment_bootstrap.interlocked_claws`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

B0 已替换为两件完全同形的三爪螺旋结构，单件约 15.06 × 15.06 × 19.17 cm、158.58 g。两边均有三条长螺旋爪臂、基环、辐条和轴向握持杆；双臂反向各转约 100°并拉开，分离后只保持 1.5 s。新视频 16.55 秒、五视角；dt 0.5 / 0.25 ms 的完整机器人执行均通过，无两件穿透或机器人禁碰，最大跟踪误差 0.694 mm。详见[本版证据与视频](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2/README.md)。

七项受力错误动作对照均被阻挡；初态另测 128 个固定姿态直拉方向，均有碰撞见证。旧 B0 到 6 s 已可直接沿轴抽出，新版在 8 s 仍被挡住。连续配合旋转／平移路径通过几何证书；这些检查不等于证明全局最短解或任意绕行动作的难度。单件侧放 20 s 静置在两个时间步下通过；5 s 的竖直握杆与侧放测试未稳定，失败记录也保存在本版归档。

C0 保留之前的 62.05 秒完整执行及半步长复验，A0 保留 158.60 秒参考执行；二者现有视频仍含旧放置／释放流程。三类共 15 路视频，B0 本轮重新执行和录制，A0/C0 未重录。均明确使用预抓取、理想辅助抓持；A0 的独立接触资格仍有缺口。九点外观代表规划尚未全部完成。

## 变体与下一步

`claw_seed_v1` 支持 A0 的共享 seed / EpisodeSpec、保存与恢复；当前接口仍拒绝 B/C。新固定原型完成不等于三族随机物理闭环完成。

## 当前证据

当前正式视频按变体分组：`demos/interlocked_claws/varaition_a0_original/<camera>/`、`varaition_b0_helical_crown/<camera>/`、`varaition_c0_orthogonal_gate/<camera>/`，每组五路完整视频。[当前全部直链](../../../demos/README.md)。旧 B0 视频移到旧归档的 `b0_render/retired_videos` 用于本次前后对照，不再作为当前正式结构。


- [2026-09-19_orthogonal_gate_balanced_physical_v1](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1)
- [2026-09-21_balanced_helical_separation_v2](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。
