# `topogym/world` — 通用物理世界

在 Genesis 之上搭建和所有任务共享的场景基座，本身不知道具体任务是什么。

当前默认是 **Nyx + 完整封闭实验室 `compact_lab`**。
渲染、背景、共享材质、相机录制与数据来源的接线见
[`默认渲染说明`](../visual/default_nyx_lab_zh.md)。

| 文件 | 提供什么 | 简单说明 |
| --- | --- | --- |
| `presentation.py` / `nyx.py` / `nyx_lab.py` | `prepare_presentation` / `add_preview_camera` / `NyxCamera` / `add_lab` | 共享的构建前渲染接线、Nyx RGB 相机适配与无碰撞实验室；背景和灯光配置单源在 `configs/presentation_configs/nyx_lab.yaml` |
| `common_room.py` | `build_common_room` / `default_common_room_spec` / `CommonRoomSpec` / `BlockSpec` / `CameraSpec` / `BuiltRoom` / `init_genesis_once` | 最底层的通用房间：初始化 Genesis、加相机、加一些通用方块，返回一个 `BuiltRoom`（scene 句柄 + entity 表）。是最原始的"造世界"积木，一般任务用不到这么底层，直接用 `tabletop.py` |
| `tabletop.py` | `StandardTabletopSceneBuilder` / `TabletopBaseScene` / `TabletopFrames` / `RobotFootprintCheck` / `tabletop_frames_from_config` | 标准桌面 + 机械臂底座 + 任务坐标系到世界坐标系的转换（`TabletopFrames.task_to_world`）。各任务的 `XxxSceneBuilder`（在 `topogym/tasks` 里）都在这个基座上继续 `add_entity` 自己的道具 |
| `materials.py` | `plastic(role, color, vis_mode=None)` | 全库唯一的 surface 构造入口：9 个语义角色（table/stage/frame/board/marker/fixture/connector/object/deformable）各定一档 roughness，颜色仍由 config 驱动（2026-07-11 统一材质轮）|
| `rope.py` | `RopeMesh` / `RopeEndpointHandle` / `sample_polyline` / `make_elastic_tube_mesh`（平行传输帧）/ `write_obj` / `endpoint_particle_indices` / `pbd_options` / `elastic_material` / `tube_morph`；connector 族：`connector_mesh` / `connector_obj_path` / `connector_grasp_height` / `connector_cap_top` / `connector_anchor_indices` / `with_connector_entries` / `revolve_profile` | **PBD 弹性管绳 + 端点插头 prefab**（2026-07-12 从 untangle 抽取；同日 cable_routing 全面采用，见 `cable_routing_element_design_zh.md`）：管网格生成、PBD 材质/求解器构造、工业插头几何、顶部出线弧、柱形锚定带。参数单源在 `configs/prefab_configs/topogym_prefabs_v1.yaml`（`prefabs.rope_pbd` + `prefabs.rope_endpoint_connector`，任务 yaml 逐字段 `${prefabs.*}` 引用）。决策记录：**物理参数与端点建模统一**、**网格分辨率各任务自留**（cable 细管 0.0055/12；flyout 实验 #1 旧值在 cable yaml 注释留档）|

> 注：`common_room.py` 文件顶部的 docstring 还写着"TopoGym module A"，这是旧 A-G 命名法留下的痕迹，本轮只整理文档、不改代码，因此暂未清理。

**不负责**：根据 seed 随机生成任务布局（`generation`）；判断任务是否成功（`tasks` 的 evaluator）。
