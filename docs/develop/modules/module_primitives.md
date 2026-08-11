# `topogym/primitives` — 动作原语

可复用的具体物理动作，被各任务的 demo/runner 调用去"执行"一步动作，自己不决定该执行哪一步。

| 文件 | 提供什么 |
| --- | --- |
| `pick_place.py` | `PickPlacePrimitive` — 标准抓取-放置序列 |
| `handle_drag.py` | `HandleDragPrimitive` — 抓住可形变体上的**刚体** handle，沿多段航点搬运（与求解器无关；2026-08-12 从 `pbd_handle_drag.py` / `PBDHandleDragPrimitive` 更名，旧名早于 FEM+IPC 迁移，实际从不调用任何求解器 API） |
| `rope_endpoint_drag.py` | `RopeEndpointDragPrimitive` / `EndpointAttachmentManager` — 拖动绳子端点并管理端点附着关系 |
| `pbd_particle_pinch.py` | `PBDParticlePinchDragPrimitive` / `PBDCornerLiftPrimitive` 等 — 捏取/提起 PBD 粒子（布料四角等） |
| `attachment.py` | `AttachmentManager` / `RigidAttachment` — 抓取时把物体"粘"在夹爪上的刚性附着关系 |
| `connector_latch.py` | `ConnectorLatch` — 卡扣/连接件的锁定与释放逻辑 |
| `physical_contact.py` | 摩擦系数配置（`configure_gripper_contact_friction` 等）+ `print_collision_il_contract` 调试打印 |

**不负责**：决定整局任务该怎么随机化（`generation`）；决定这一步该抓哪个物体、走哪条路径（`planning`）。
