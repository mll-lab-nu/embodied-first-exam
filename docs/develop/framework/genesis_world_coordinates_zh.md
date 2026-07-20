# Genesis World 坐标体系教程

这篇文档说明 TopoGym 当前 Genesis 场景里，物体尺寸和位置是怎么计算出来的。

## 0. 先用人的方向理解 `[x, y, z]`

后面所有“左/右/前/后”都采用机器人视角：站在 Franka 底座后方，和机械臂初始朝向同向看桌面。

```text
                 +x  前 / 远离机器人
                  ↑
+y 左侧  ←  robot base  →  -y 右侧
                  ↓
                 -x  后 / 靠近机器人

+z 上方，-z 下方
```

因此：

- 想让东西离机械臂更远：增大 `x`。
- 想让东西离机械臂更近：减小 `x`。
- 想让东西往机械臂左手边走：增大 `y`。
- 想让东西往机械臂右手边走：减小 `y`。
- 想让东西更高：增大 `z`。

录像里的左/右可能被相机角度影响。调配置时不要按画面左/右猜，先回到上面这个机器人视角。

## 1. 三套坐标

### Genesis world 坐标

Genesis 的世界坐标以米为单位：

- `+z` 向上；
- 重力是 `[0, 0, -9.81]`；
- `Box.pos` 是中心点；
- `Box.size` 是完整长宽高。

`size` 的三个数也按这个方向读：

```text
size[0] = x 方向长度，也就是前后深度
size[1] = y 方向长度，也就是左右宽度
size[2] = z 方向长度，也就是上下高度
```

在 `topogym_tabletop_v1` 中，桌子是一个固定 box：

```yaml
world.table.pos:  [-0.1356786, 0.0, 0.45982145]
world.table.size: [1.2090764, 1.2, 0.9196429]
```

所以桌面高度为：

```text
table_top_z = table.pos.z + table.size.z / 2
            = 0.45982145 + 0.9196429 / 2
            = 0.9196429
```

### table surface 坐标

`frames.table_surface.origin = [0, 0, 0.9196429]`。

它表示桌面中心在 Genesis world 里的位置。这个点的 `z` 正好等于桌面 top。

### task 坐标

`topogym_tabletop_v1` 让 task frame 和 table surface frame 重合：

```yaml
frames.task.origin: [0.0, 0.0, 0.9196429]
```

因此，在 task 坐标里：

- `z=0` 是桌面表面；
- `x=-0.570` 是 Franka 安装点；
- `x` 越大，越远离机器人底座，也就是越“往前”；
- `+y` 是机器人左侧，`-y` 是机器人右侧；
- 任务配置里的 `pos` 可以先当成“桌面上的局部坐标”理解。

task 到 world 的转换很简单：

```text
world_pos = frames.task.origin + task_pos
```

例如 task frame 中的棋盘中心是 `[0, 0, 0.0055]`，world 坐标就是：

```text
[0, 0, 0.9196429] + [0, 0, 0.0055]
= [0, 0, 0.9251429]
```

## 2. Box 的位置和高度

Genesis box 的 `pos.z` 是中心高度。一个高度为 `h` 的 box：

```text
bottom_z = pos.z - h / 2
top_z    = pos.z + h / 2
```

V1 的共享 stage：

```yaml
world.stage.pos:  [0.0, 0.0, 0.9206429]
world.stage.size: [0.70, 0.80, 0.002]
```

它的底面：

```text
0.9206429 - 0.002 / 2 = 0.9196429
```

正好贴在桌面上。

V1 的 task board：

```yaml
manipulation_space.board.pos:  [0.00, 0.00, 0.0055]
manipulation_space.board.size: [0.70, 0.80, 0.007]
```

它在 task 坐标里的底面和顶面：

```text
board_bottom_z = 0.0055 - 0.007 / 2 = 0.002
board_top_z    = 0.0055 + 0.007 / 2 = 0.009
```

所以一个高度 `0.038 m` 的方块如果要放在 board 顶面，中心高度应为：

```text
block_center_z = board_top_z + block_height / 2
               = 0.009 + 0.038 / 2
               = 0.028
```

## 3. 机器人位置

Franka MJCF 的 `pos` 是底座安装面中心，不是视觉模型中心。

V1 的 task-frame mount：

```yaml
robot_setup.mount.pos: [-0.570, 0.00, 0.00]
```

对应 world 坐标：

```yaml
robot_mount.pos: [-0.570, 0.0, 0.9196429]
```

builder 会检查：

1. robot mount 的 `z` 是否等于桌面高度；
2. Genesis 1.1.0 的真实 `link0.stl` footprint 是否完全在桌面范围内；
3. `robot_mount.mobility` 是否为 `fixed`。

当前约定下，机器人从 `x=-0.570` 面向 `+x` 的任务区域。任务物体通常放在 `x` 接近 `0` 或略正的位置。

## 4. 相机位置

Genesis 相机由 `pos`、`lookat`、`up`、`fov` 定义：

```yaml
cameras.base_camera:
  pos:    [0.30, 0.00, 1.3196429]
  lookat: [0.00, 0.00, 0.7196429]
  up:     [0.0, 0.0, 1.0]
  fov: 90
```

- `pos` 是相机位置，world 坐标；
- `lookat` 是相机看向的点，world 坐标；
- `up` 控制画面上方向；
- `fov` 单位是 degree。

当前常见相机名：

| 相机 | 人话解释 | 用途 |
|---|---|---|
| `base_camera` | 给学习策略/模型看的固定相机。`policy` 指的就是后续 RL/IL 的策略模型。 | observation / 数据集输入 |
| `oblique` | 斜俯视相机。 | 人看 viewer 或录制视频，检查机械臂动作最方便 |
| `topdown` | 正上方俯视相机。 | 检查布局、间距、是否对齐 |

所以如果你只是想让视频好看，优先调 `oblique`；如果要改训练 observation，才需要谨慎动 `base_camera`。

## 5. 网格类任务怎么算位置

OneStroke 和 Maze 使用 cell 网格。配置给的是左上角 cell 的中心：

```yaml
grid.top_left_cell_pos: [-0.070, 0.150, 0.016]
grid.cell_size: [0.070, 0.070, 0.014]
grid.cell_gap: 0.040
```

cell 中心公式：

```text
cell_x = top_left.x + col * (cell_size.x + cell_gap)
cell_y = top_left.y - row * (cell_size.y + cell_gap)
cell_z = top_left.z
```

也就是说：

- 列 `col` 增大，物体向 `+x` 移动；
- 行 `row` 增大，物体向 `-y` 移动；
- 相邻 cell 中心距是 `cell_size + cell_gap`。

wall block 放在两个相邻 cell 中心的中点：

```text
edge_center = 0.5 * (cell_a_center + cell_b_center)
```

Maze removal 的 discard 区域也在 task frame：

```yaml
discard.visible: false
discard.pos: [0.000, -0.340, 0.012]
discard.size: [0.700, 0.120, 0.006]
```

被取走的 wall block 会按 `columns / spacing_x / spacing_y` 排到这个逻辑区域，而不是落回 maze cell 上。
`visible=false` 表示不显示额外托盘；区域仍用于成功/invalid 判断。

## 6. 一个完整调参例子：把 Maze 放远、放大、把 discard 放到右前方

假设我们从这个配置开始：

```yaml
grid:
  top_left_cell_pos: [-0.100, 0.165, 0.016]
  cell_size: [0.070, 0.070, 0.014]
  cell_gap: 0.040

discard:
  visible: false
  pos: [0.000, -0.340, 0.012]
  size: [0.700, 0.120, 0.006]
```

### 例子 A：迷宫整体离机械臂再远 5 cm

“远”就是 `+x`。所以只改 `top_left_cell_pos.x`：

```yaml
top_left_cell_pos: [-0.050, 0.165, 0.016]  # -0.100 + 0.050
```

### 例子 B：迷宫整体往机器人右侧挪 3 cm

“右”就是 `-y`。所以把 `y` 减小：

```yaml
top_left_cell_pos: [-0.100, 0.135, 0.016]  # 0.165 - 0.030
```

### 例子 C：cell 做大，但 gap 不变

前后和左右都变大，所以改 `cell_size[0]` 和 `cell_size[1]`：

```yaml
cell_size: [0.078, 0.078, 0.014]
cell_gap: 0.040
```

这会让整个 maze footprint 变大。记得同步检查 wall block 长度是否还合适。

### 例子 D：discard 区域放到右前方

“前”是 `+x`，“右”是 `-y`：

```yaml
discard:
  pos: [0.050, -0.340, 0.012]
```

如果只是想让区域右移，主要改 `y`；如果想沿棋盘长边重新排布，改 `columns / spacing_x`。
为了不在视频中看到托盘，保持 `discard.visible=false`。

## 7. 路径类任务怎么算位置

Cable Routing 的 fixture 和 endpoint waypoints 都是 task-frame 点：

```yaml
fixtures.P1.pos: [-0.020, 0.110, 0.050]
routing.endpoint_oracle_waypoints:
  - {phase: green_lift_start, pos: [0.050, 0.165, 0.018], steps: 24, lifted: true}
```

PBD rope 不是简单 box。它会根据 route/waypoint 生成 tube mesh，再交给 Genesis PBD solver。这里的 `radius`、`particle_size`、`mesh.segment_length` 会同时影响外观、碰撞稳定性和构建速度。

Untangle 使用 hole 网格：

```yaml
holes.top_left_pos: [-0.157, 0.095, 0.010]
holes.spacing: [0.078, 0.072]
```

hole 中心公式：

```text
hole_x = top_left.x + col * spacing.x
hole_y = top_left.y - row * spacing.y
hole_z = top_left.z
```

rope 点可以引用 hole，并额外叠加 `layer_height` 和 `z_offset`。

## 8. 常见错误

### 把中心点当成底面

如果一个 box 高度是 `0.026`，把 `pos.z` 直接设成桌面高度，会有一半物体穿进桌子。

正确做法：

```text
pos.z = surface_z + height / 2
```

### 混用 world 和 task 坐标

`coordinate_frame: task` 的任务里，`z=0.016` 表示离桌面 16 mm；不是 world z=16 mm，也不是地面附近。

如果看到物体飞到地下或悬在高处，先检查任务配置是不是用了 task frame。

### 只隐藏视觉，没有关闭碰撞

`visualization: false` 只是不显示；如果 `collision: true`，实体仍然会参与物理。

Maze removal 当前默认 `edge_slots.visualization=false` 且 `edge_slots.collision=false`，所以 cell gap 里不会留下隐藏承托体。

### 改了 locked preset 但没更新校验常量

`topogym_tabletop_v1` 是 locked preset。桌子、底座、base camera 等 frozen 参数在 `topogym/world/tabletop.py` 里有校验常量。

如果确实要改桌子或 robot mount，需要同步更新：

- `configs/env_configs/topogym_tabletop_v1.yaml`
- `configs/common_configs/topogym_tabletop_v1.yaml`
- `topogym/world/tabletop.py` 中 `_V1_*` 常量
- `docs/develop/framework/tabletop_baseline_v1_zh.md`

普通任务物体位置不需要改 builder 常量，直接改对应 task config。

## 9. 调试建议

1. 先用 viewer 看静态布局，再跑物理动作。
2. 用 `--verbose` 看 demo 打印的 world/task 坐标。
3. 如果物体穿模，先检查 `pos.z +/- size.z/2`。
4. 如果机械臂姿态奇怪，先检查目标点是否太近、太低或超出保守 workspace。
5. 如果 PBD rope/cloth 崩溃，先降低几何复杂度和避免初始自交，再调 solver 参数。
