# 表外 Task 入口归档

2026-09-25：按用户要求，将三档构造已齐备任务的表外入口移入本目录。随后用户选定 Horseshoe 形状三档，其 21 个旧描述性候选及 reference 入口也移入本目录。

这里保存历史参数入口，**不参与当前 registry，不进入发行 wheel，活动源码不得导入本目录**。原位置的导入不再支持，旧具名 variation 请求会明确失败，不自动映射到近似的新档位。几何工具、随包资源、历史 demo 和执行证据继续保留。

| 子目录 | 归档数 | 内容 |
|---|---:|---|
| cast_keyhole | 1 | legacy_reference |
| cast_coil | 4 | face_small、depth_thick、corner_cut、eccentric_turn |
| hedgehog_in_cage | 3 | fixed_side_window、staggered_gates、helical_guide |
| lock_picking | 1 | two_unequal |
| buzz_wire_3d | 2 | legacy_spatial_maze、double_arch |
| interlocked_claws | 2 | 旧 helical_crown、orthogonal_gate；当前 balanced 三档保留 |
| knot_untying | 2 | figure_eight_original、left_overhand |
| horseshoe_ring | 22 | 原 reference、21 个描述性候选；选中三者的构造已进入难度脚本 |

总计 37 个入口。原注册记录、路径及迁移前后源码 SHA-256 见 [manifest.json](manifest.json)。文件只改变了共用 Task 的 import 坐标，变体参数未改；它们仍依赖当前共用构造，不是独立冻结的完整历史运行快照。复现旧执行应查看原 demo 元数据及其源码档案。

**默认入口变化：**Keyhole 的 `base` 改指 F1 easy；Buzz 的 `base` 改指 F1 三拱 easy。已核对 39 个难度文件源码及 29 个可实例化档位的 seed=7 实例身份均不变。Horseshoe 后续改为 `base=easy`（waist_mild），三个占位改为具体形状设置；Orbits 的 `base=reference85` 保留。前述 39 文件／29 身份不变指首批归档，后续只有 Horseshoe 三档变更。

**Coil 分类：**外形轴是 face_small（面内缩放 0.95）、depth_thick（厚度 1.10）、corner_cut（切角比例 0.25），会改变碰撞几何，不能视为纯贴图或保证 IK 不变。eccentric_turn 是偏心回转机构（冻结模板偏心量 9 mm），不属于外形轴；因与基础路线同为单自由度回转而退出主三档。

**Lock F2：**two_unequal 为两次回退、非等角槽位的旧候选。第一盘槽位 −60°、−32°、0°，两段角差为 28°、32°；第二／三盘槽位分别为 −60°、0°。它不是“两把钥匙”或“两个转盘”，也不是新增回退次数的难度档；已有几何／IK 记录不等于完整机器人解法。

Blanket、Rope、Slotted、Orbits 三档构造尚未全部齐备，本轮未整体清理其目录。主三档部署及后续判据／planner 缺口见 [部署记录](../../../docs/develop/tasks/variation_deployment_implementation_20260925_zh.md)。
