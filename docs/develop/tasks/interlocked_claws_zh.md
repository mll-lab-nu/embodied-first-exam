# 双爪互锁

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

两件互锁刚体由 ALOHA 双臂拆开，放到承托面、松爪并静置。当前 A0 为 Genesis 原始爪；B0 螺旋冠及 C0 等尺寸双窗为 MuJoCo 固定原型。

源码：[geometry.py](../../../topogym/tasks/interlocked_claws/geometry.py) · [scene.py](../../../topogym/tasks/interlocked_claws/scene.py) · [variants.py](../../../topogym/tasks/interlocked_claws/variants.py) · [agent_adapter.py](../../../topogym/tasks/interlocked_claws/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/interlocked_claws.yaml)；场景入口：`python -m demos.environment_bootstrap.interlocked_claws`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

C0 等尺寸双窗完成 62.05 秒完整执行及半步长复验；B0 也有完整流程。均从预抓取状态开始，使用理想辅助抓持。A0 的独立接触资格仍有缺口。

2026-09-21 [尺寸与视频核查](../../../runs/demo_metadata/interlocked_claws/2026-09-21_size_demo_audit_v1/README.md)：B0 两件含握持部的尺寸分别约 24.48 × 15.36 × 6.32 cm、17.09 × 17.09 × 14.80 cm，确实不全等；最大边长未超过 A0 的约 26.37 cm。三类基础代表共 15 路完整视频重新核对哈希、帧数、时长和完整解码通过；九点外观代表规划尚未全部完成。

## 变体与下一步

`claw_seed_v1` 支持 A0 的共享 seed / EpisodeSpec、保存与恢复；当前接口仍拒绝 B/C。新固定原型完成不等于三族随机物理闭环完成。

## 当前证据

当前正式视频按变体分组：`demos/interlocked_claws/varaition_a0_original/<camera>/`、`varaition_b0_helical_crown/<camera>/`、`varaition_c0_orthogonal_gate/<camera>/`，每组五路完整视频。[目录与五视角直链](../../../runs/demo_metadata/interlocked_claws/2026-09-21_variation_layout_v1/README.md)。A0/B0 从原完整物理状态补录，C0 原文件迁移；不增加物理执行成功次数。


- [2026-09-19_orthogonal_gate_balanced_physical_v1](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1)
- [2026-09-19_helical_crown_physical_v1](../../../runs/demo_metadata/interlocked_claws/2026-09-19_helical_crown_physical_v1)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。
