# TopoGym 3D 尺寸与位置参数索引

这份文件是以后微调场景尺寸和位置时的入口地图。所有长度单位都是米。

## 先建立方向感

这里统一采用“站在 Franka 底座后方，和机械臂初始朝向同向看桌面”的视角：

```text
                 +x  前 / 远离机器人
                  ↑
+y 左侧  ←  robot base  →  -y 右侧
                  ↓
                 -x  后 / 靠近机器人

+z 上方，-z 下方
```

所以看到 `[x, y, z]` 时可以先这样读：

| 坐标 | 人话 | 数值变大时 |
|---|---|---|
| `x` | 前后 | 更靠前、更远离机器人 |
| `y` | 左右 | 更靠左；想往右挪就让 `y` 变小 |
| `z` | 上下 | 更高；想贴桌面就让 `z` 接近物体应有中心高度 |

注意：viewer/录像相机可能从斜侧看，画面里的左/右不一定等于这里的 `+y/-y`。调参数时以这个机器人视角为准。

## 基本约定

- `pos: [x, y, z]` 表示物体中心点，不是左下角，也不是底面中心。
- `size: [x, y, z]` 表示完整长宽高，不是半尺寸。
- `radius` 是圆柱/圆盘半径，`height` 是完整高度。
- `yaw` 绕 `+z` 旋转，常用于 wall block 或 plate 的平面朝向。
- `topogym_tabletop_v1` 的任务配置都使用 `coordinate_frame: task`：`z=0` 是桌面表面。
- 旧版/basic 配置通常使用 Genesis world 坐标，文件内会特别标注。

## 小词典

| 术语 | 简单解释 |
|---|---|
| `AABB` | axis-aligned bounding box，即“和坐标轴对齐的外接长方体”。文档里说桌面 AABB 尺寸，就是桌子碰撞体在 `x/y/z` 三个方向的完整占用范围。 |
| `policy camera` | 给学习策略/模型看的固定相机。它服务训练数据和 observation，不一定是最适合人看的角度。 |
| `oblique` | 斜俯视相机，主要给人看 viewer/录制视频；适合检查机械臂和任务物体的相对位置。 |
| `topdown` | 正上方俯视相机，主要检查布局是否对齐。 |
| `footprint` | 一个物体投影到桌面上的占地范围，比如机械臂底座 footprint。 |
| `task frame` | 桌面任务坐标。V1 中 `z=0` 是桌面，调任务物体时通常看这个。 |
| `world frame` | Genesis 全局坐标。桌子、机器人安装位、相机最终都在 world frame 里。 |

## 最常用的调参动作

| 目标 | 改法 |
|---|---|
| 把整个任务布局往前挪 | 对任务里的主要 `pos.x` 或 `top_left_cell_pos.x` 加正数，例如 `+0.05` 表示前移 5 cm。 |
| 把物体往机器人右侧挪 | 让 `y` 变小，例如 `y -= 0.05`。 |
| 把物体往机器人左侧挪 | 让 `y` 变大，例如 `y += 0.05`。 |
| 把物体抬高 | 让 `z` 变大。 |
| 把棋盘前后方向变大 | 增大 `size[0]`。 |
| 把棋盘左右方向变大 | 增大 `size[1]`。 |
| 让方块正确放在板上 | 中心高度用 `board_top_z + block_height / 2`，不要把中心高度写成桌面高度。 |

## 先改哪里

| 想调什么 | 推荐入口 | 说明 |
|---|---|---|
| 通用棋盘大小 | `configs/common_configs/topogym_tabletop_v1.yaml` 的 `manipulation_space.board.size` | 所有引用 `${common.manipulation_space.board.size}` 的 V1 任务都会跟着变。 |
| 通用棋盘位置 | `configs/common_configs/topogym_tabletop_v1.yaml` 的 `manipulation_space.board.pos` | task frame 中相对桌面中心的位置。 |
| 桌子大小/高度 | `configs/env_configs/topogym_tabletop_v1.yaml` 的 `world.table` | 当前 preset locked，改动会触发 builder 校验；如要改，需要同步更新 `topogym/world/tabletop.py` 的锁定常量。 |
| 机器人底座位置 | `configs/common_configs/topogym_tabletop_v1.yaml` 的 `robot_setup.mount.pos` 和 `configs/env_configs/topogym_tabletop_v1.yaml` 的 `robot_mount.pos` | V1 里底座固定，必须在桌面 footprint 内。 |
| 固定相机 | `configs/env_configs/topogym_tabletop_v1.yaml` 的 `cameras` | `base_camera` 给策略/模型看，`oblique/topdown` 给人看录制和调试。 |
| 任务内部物体布局 | `configs/task_configs/*_topogym_tabletop_v1.yaml` | 优先改对应任务自己的 task-frame 配置。 |
| 旧版/basic demo 布局 | `configs/common_configs/manipulation_space.yaml` | 这是 world-frame 旧入口，不是 frozen tabletop V1。 |

## 共享 tabletop V1 几何

| 参数 | 当前值 | 含义 |
|---|---:|---|
| `frames.task.origin` | `[0.0, 0.0, 0.9196429]` | task 坐标原点在世界中的位置；也是桌面表面中心。 |
| `world.table.pos` | `[-0.1356786, 0.0, 0.45982145]` | 桌子中心点。 |
| `world.table.size` | `[1.2090764, 1.2, 0.9196429]` | 桌子外接长方体完整尺寸，即 x/y/z 方向占用范围。 |
| `world.stage.pos` | `[0.0, 0.0, 0.9206429]` | 共享操作底板中心；底面贴桌面。 |
| `world.stage.size` | `[0.70, 0.80, 0.002]` | 共享操作底板完整尺寸。 |
| `manipulation_space.board.pos` | `[0.00, 0.00, 0.0055]` | 任务棋盘中心，task frame。 |
| `manipulation_space.board.size` | `[0.70, 0.80, 0.007]` | 任务棋盘完整尺寸。 |
| `robot_setup.mount.pos` | `[-0.570, 0.00, 0.00]` | Franka 安装面中心，task/table frame。 |
| `robot_mount.pos` | `[-0.570, 0.0, 0.9196429]` | 同一安装点的 world 坐标。 |

高度速查：

- 桌面 top：`world z = 0.9196429`
- stage top：`task z = 0.002`
- board top：`task z = 0.009`
- 如果一个高度 `h` 的物体要放在 board 上，中心高度应为 `0.009 + h / 2`。

## 任务布局入口

| 任务 | 文件 | 主要 3D 参数 | 计算方式 |
|---|---|---|---|
| Swap | `configs/task_configs/swap_topogym_tabletop_v1.yaml` | `slot_size`、`slots[*].pos`、`blocks.*.size` | block 中心高度由 `slot_pos.z + slot_size.z/2 + block_size.z/2` 计算。 |
| OneStroke | `configs/task_configs/onestroke_topogym_tabletop_v1.yaml` | `grid.top_left_cell_pos`、`grid.cell_size`、`grid.cell_gap`、`wall_block.size`、`supply.*`、`edge_slots.*` | cell 网格从左上角开始，`col` 沿 `+x`，`row` 沿 `-y`。 |
| Maze Removal | `configs/task_configs/maze_wall_removal_topogym_tabletop_v1.yaml` | `grid.top_left_cell_pos`、`grid.cell_size`、`grid.cell_gap`、`wall_block.*`、`discard.*` | 与 OneStroke 同一网格公式；移除后的 wall block 放到棋盘右侧不可见逻辑 `discard` 区。 |
| Cable Routing | `configs/task_configs/cable_routing_topogym_tabletop_v1.yaml` | `fixtures.*.pos/size/radius/height`、`routing.*`、`rope.*`、`physical_handle.*` | fixture 和 rope waypoint 都是 task-frame 点；physical demo 中夹爪只碰撞动态 rigid free-end handle，cable 端点通过 `fix_particles_to_link` 跟随 handle，终点插座 latch 只在插入后锁定。 |
| Untangle | `configs/task_configs/untangle_topogym_tabletop_v1.yaml` | `holes.top_left_pos`、`holes.spacing`、`rope.*`、`physical_handle.*` | hole 网格从左上角开始，`col` 沿 `+x`，`row` 沿 `-y`；physical demo 中夹爪只碰撞动态 rigid endpoint handle，rope 端点通过 `fix_particles_to_link` 跟随 handle。 |
| Peeling | `configs/task_configs/peeling_physical_single_topogym_tabletop_v1.yaml` | `substrate.pos/size`、`film.center/size`、`placement.center`、`physical.*` | PBD cloth 版本仍采用 sticky/contact abstraction；稳定 baseline 可改用 `peeling_rigid_patch_suction_demo.py` 的刚体方形 patch + 接触吸附。 |
| Band Untwist | `configs/task_configs/band_untwist_topogym_tabletop_v1.yaml` | `figure_eight.closed_lobe_radius/open_lobe_radius/end_gap/half_angle_deg/over_lift/base_z/center/heading_deg`、`pinch.lift_clearance/place_clearance`、`success.end_height_tolerance` | 8 字 = 两个泪滴在交叉点相接：切线长 = 半径 / tan(half_angle)，两股互成 2×half_angle 交叉；开口叶在底部截断使两绳头相距 end_gap，**end_gap ≥ rope.free_end_connector.min_clearance (0.07)** 否则 builder 拒建。抬升高度 = 场景顶 + 交叉点到绳头弧长 + lift_clearance（约 183mm）。改任何一个数先跑 `python tests/check_band_untwist_geometry.py`（无需 GPU）。 |
| Unlink C Ring | `configs/task_configs/unlink_c_ring_topogym_tabletop_v1.yaml` | `fixed_ring.center/major_radius/tube_radius`、`c_ring.major_radius/tube_radius/gap_deg/gap_azimuth_deg/tab.*`、`stand.yaw_deg/arm_length`、两处 `segment_deg` | 尺寸由五条不等式互相咬合，不能单改一条：C 环静置中心 = 固定环心 - major_radius - (C 孔半径 - 固定环管半径)，抽出行程 = 2×(两管半径之和)。改任何一个数先跑 `python tests/check_c_ring_clearance.py`（无需 GPU），它会打印每条余量。 |
| Stacked Plate | `configs/task_configs/stacked_plate_topogym_tabletop_v1.yaml` | `disks.*.center/radius/thickness/init_angle_deg`、`rod.*`、`sector.*`、`support.*`、`physical.grasp_rim_angle_deg/roll_sign` | 3 个竖直圆盘串在沿 Y 的横杆上，各为绕 Y 的 revolute joint compound URDF（完整圆柱碰撞 + 扇形纯视觉 mesh）；夹爪捏住盘缘薄边、靠指腹摩擦把盘向下滚转对齐缺口；支撑柱有 collision，横杆即真实转轴。 |

## 网格公式

OneStroke、Maze 和 Untangle 的网格都遵守同一方向习惯：

```text
x：远离 robot base，朝任务前方
y：桌面左右方向
row 增大：沿 -y
col 增大：沿 +x
```

OneStroke/Maze cell 中心：

```text
cell_x = top_left_cell_pos.x + col * (cell_size.x + cell_gap)
cell_y = top_left_cell_pos.y - row * (cell_size.y + cell_gap)
cell_z = top_left_cell_pos.z
```

Untangle hole 中心：

```text
hole_x = top_left_pos.x + col * spacing.x
hole_y = top_left_pos.y - row * spacing.y
hole_z = top_left_pos.z
```

## 调参纪律

1. 先确认当前文件是不是 `coordinate_frame: task`。如果是，`z=0` 是桌面，不是世界原点。
2. 改尺寸后同步检查相邻间隙，例如 `cell_gap > wall_block.size[1]`。
3. 改高度时用“顶面/底面”反推中心高度，避免把物体中心误当成底面。
4. 优先改配置；只有 locked tabletop preset 的桌子/底座/相机需要同步更新 builder 校验常量。
5. 如果 viewer 里物体穿模，先检查 z 中心高度和碰撞开关，再检查 solver/摩擦。

更多坐标计算示例见 `docs/develop/framework/genesis_world_coordinates_zh.md`。
