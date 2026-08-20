"""Deformable Shape & Self-Arrangement (类别 1) —— 可形变物体自身的形状、铺展与层叠关系。

尚无实现。四类中唯一空缺的一类；候选任务见 `docs/develop/TopoGym_tasks.docx` 第 1 节
（对折／折角、展开单个褶皱、展开自身卷曲的布带、软管弯成 U 形、铺展桌布）。
落地前需先确定可形变布料／软管在 Genesis 中的建模方案。

建模方案的现状（2026-08-17）：
- **布**（1.1／1.2／1.3／1.5）走 PBD Cloth，抓取用接近触发的运动学吸附
  （`primitives/pbd_particle_pinch.py` 的 `PBDParticleAttachmentDragPrimitive`），
  不让手指与布做硬接触 —— 见 `docs/develop/physics/peeling/peeling_segfault_debug_zh.md`
  记录的 native segfault。定护栏数值的四项测量在 `tests/pbd_cloth_spike.py`，
  第一个任务是 1.1 对折，配置骨架在 `configs/task_configs/cloth_fold_topogym_tabletop_v1.yaml`。
- **软管**（1.4）走已有的 FEM+IPC 管，与 rope_winding／cable_routing 同一条管线，
  不属于上面这套。

See `docs/develop/framework/task_taxonomy_zh.md`.
"""

from .cloth_fold import (
    ClothFoldLayout,
    ClothFoldScene,
    ClothFoldSceneBuilder,
    cloth_particles,
    cloth_sheet_mesh,
    remesh_report,
    settle_cloth,
)

__all__ = [
    "ClothFoldLayout",
    "ClothFoldScene",
    "ClothFoldSceneBuilder",
    "cloth_particles",
    "cloth_sheet_mesh",
    "remesh_report",
    "settle_cloth",
]

