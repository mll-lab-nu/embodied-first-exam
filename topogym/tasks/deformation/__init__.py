"""Deformable Shape & Self-Arrangement (类别 1) —— 可形变物体自身的形状、铺展与层叠关系。

docx `TopoGym_tasks.docx` 第 1 节列了五个候选任务，本目录的进度：

| docx | 任务 | 状态 |
|---|---|---|
| 1.1 | 对折／折角 | `cloth_fold.py`，2026-08-21 跑通并标定 |
| 1.2 | 展开单个褶皱 | `cloth_unpleat.py`，建设中 |
| 1.3 | 展开自身卷曲的布带 | `cloth_unroll.py`，代码已落地，待 GPU 标定 |
| 1.4 | 将软管弯成 U 形 | 不属于本目录，走 FEM+IPC 管（见下） |
| 1.5 | 铺展桌布并形成目标垂坠 | 未开工 |

建模方案（1.1 在 2026-08-17 至 08-21 期间标定，1.2 起沿用）：

- **布**（1.1／1.2／1.3／1.5）走 PBD Cloth。抓取用接近触发的运动学吸附，
  手指与布不做硬接触 —— 见 `docs/develop/physics/peeling/peeling_segfault_debug_zh.md`
  记录的 native segfault。让粒子跟着夹爪走的方式是 `fix_particles_to_link`
  （`primitives/cloth_link_attach_drag.py`），2026-08-20 四种方式实测后选定：
  跟随率 1.00、边最大拉伸只有其余的一半到五分之一、且不会把布压到桌面以下。
  布↔桌面的持续摩擦 Genesis 不提供，由 `world/rope.py` 的 `TabletopParticleFriction` 补上。
  护栏数值的测量在 `tests/pbd_cloth_spike.py`，取值与推导在
  `configs/task_configs/cloth_fold_topogym_tabletop_v1.yaml`。
- **不平铺的起始形状**（1.2／1.3／1.5）由 `cloth_profile_mesh.py` 生成：
  一条 x-z 剖面折线沿 y 扫掠，平铺是它的特例。
- **软管**（1.4）走已有的 FEM+IPC 管，与 rope_winding／cable_routing 同一条管线。

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
from .cloth_profile_mesh import (
    edge_report,
    pleat_landmarks,
    pleat_profile,
    polyline_length,
    resample_polyline,
    spiral_landmarks,
    spiral_profile,
    sweep_profile_mesh,
    texture_size_m,
)
from .cloth_unpleat import (
    ClothUnpleatLayout,
    ClothUnpleatScene,
    ClothUnpleatSceneBuilder,
    band_particles,
    settle_band,
)
from .cloth_unroll import (
    ClothUnrollLayout,
    ClothUnrollScene,
    ClothUnrollSceneBuilder,
)

__all__ = [
    "ClothFoldLayout",
    "ClothFoldScene",
    "ClothFoldSceneBuilder",
    "cloth_particles",
    "cloth_sheet_mesh",
    "remesh_report",
    "settle_cloth",
    "ClothUnpleatLayout",
    "ClothUnpleatScene",
    "ClothUnpleatSceneBuilder",
    "band_particles",
    "settle_band",
    "edge_report",
    "pleat_landmarks",
    "pleat_profile",
    "polyline_length",
    "resample_polyline",
    "spiral_landmarks",
    "spiral_profile",
    "sweep_profile_mesh",
    "texture_size_m",
    "ClothUnrollLayout",
    "ClothUnrollScene",
    "ClothUnrollSceneBuilder",
]
