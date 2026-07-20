# Cable Routing Demo 路线规划协作指南

这份文档记录 Cable Routing demo 里“机械臂抓住 rope 自由端并绕过两个 peg”的路线规划约定。核心经验是：不要只靠 viewer 截图和手画轨迹沟通，因为相机视角会旋转，屏幕里的上下左右不等于 Genesis world 坐标里的 `x/y`。更稳定的方式是用坐标、peg-relative offset 和 waypoint 表来描述。

## 1. 当前 demo 路线是怎么生成的

`endpoint-physics` oracle 不是直接规划整条 rope 的形状，而是规划 rope 自由端 handle 的轨迹。机械臂手爪通过 IK 跟随这个 handle，Genesis PBD 负责让 rope 剩余部分和 peg/board 发生物理交互。

主要配置在：

```text
configs/task_configs/cable_routing.yaml
```

关键字段是：

```yaml
routing:
  endpoint_oracle_waypoints:
    - {phase: green_lift_start, pos: [0.650, 0.165, 0.768], steps: 24, lifted: true}
    - {phase: green_P1_upper_right, pos: [0.650, 0.045, 0.768], steps: 36, lifted: true}
```

执行流程可以理解为：

```text
waypoint pos
 -> route point
 -> handle target = pos + endpoint_handle.z_offset + wrap_z_lift
 -> robot hand target = handle target + hand-to-handle offset
 -> controller.move_ee_to(...)
 -> scene.step()
```

`pos` 是 rope 自由端中心线的目标点。绕线阶段 `lifted: true` 会叠加 `--wrap-z-lift`，最终插入终点通常用 `lifted: false`。

## 2. Genesis/world 坐标和单位

Genesis 使用 SI 单位：

```text
1.0 = 1 meter
0.10 = 10 cm
0.01 = 1 cm
```

当前 Cable Routing 场景里的关键坐标：

```text
board center = (0.620,  0.000)
board size   = 0.700m x 0.800m

robot base   = (0.150,  0.000, 0.780)
S/start      = (0.470,  0.020)
C/end        = (0.755, -0.035)
P1           = (0.580,  0.110)
P2           = (0.660, -0.120)

free end rope point  = (0.650, 0.165, 0.768)
free end handle      = (0.650, 0.165, 0.778)
```

两个 peg 的中点：

```text
mid(P1, P2) = (0.620, -0.005)
```

注意：viewer 中“视觉上方/下方”不一定等于 world `+y/-y`。如果要表达屏幕方向，最好先把期望路线转换成具体 world 坐标，或者用相对 peg 的 offset 表达。

## 3. 机械臂抓手坐标和 handle 坐标

路线表里的 `pos` 是 rope 中心线点。自由端 handle 有一个高度偏移：

```yaml
endpoint_handle:
  z_offset: 0.010
```

如果命令里使用：

```bash
--wrap-z-lift 0.040
```

绕线阶段：

```text
route z  = 0.768
handle z = 0.768 + 0.010 + 0.040 = 0.818
hand z   ≈ 0.818 + 0.1029 = 0.9209
```

所以平面方向上，机械臂 hand 的 `[x, y]` 基本跟 waypoint `[x, y]` 一致；高度上 hand 比 handle 高一截。

## 4. 推荐的路线描述格式

以后不要只说“往左绕”“往上绕”，而是提供一张 waypoint 表。推荐格式：

```text
start = free_end_handle = (0.650, 0.165)

waypoints:
1. phase=lift_start,      xy=(0.650,  0.165), lifted=true
2. phase=P1_upper_right,  xy=(0.650,  0.045), lifted=true
3. phase=P1_top,          xy=(0.580, -0.010), lifted=true
4. phase=between_pegs,    xy=(0.620, -0.005), lifted=true
5. phase=P2_lower_left,   xy=(0.590, -0.170), lifted=true
6. phase=P2_bottom,       xy=(0.660, -0.240), lifted=true
7. phase=P2_lower_right,  xy=(0.740, -0.180), lifted=true
8. phase=C,               xy=(0.755, -0.035), lifted=false
```

也可以用 peg-relative offset：

```text
P1 = (0.580, 0.110)
P2 = (0.660, -0.120)

P1_top         = P1 + ( 0.000, -0.120)
P1_upper_right = P1 + ( 0.070, -0.065)
between_pegs   = midpoint(P1, P2)
P2_bottom      = P2 + ( 0.000, -0.120)
```

对 Codex 来说，最清楚的是同时给出：

```text
A. waypoint 坐标
B. 每个点相对哪个 peg：outside / inside / between / endpoint
C. 该段目标：拉 rope 通过 / 保持 rope 挂住 / 插入终点
```

## 5. 路线规划原则

### 区分机械臂轨迹和 rope 结果

机械臂轨迹走对，不等于 rope 物理绕住。验证时要同时看：

```text
endpoint_route_ok  handle/机械臂是否经过目标侧
rope_contact       rope 是否碰到 peg
rope_wrap_ok       rope 是否形成包角并留在 peg 上
```

### 先规划简单路径，再验证物理结果

对 rope demo 来说，路线应尽量少折返。多余的小圈会让 rope 被重新拉开，或者制造不必要的接触/碰撞。

推荐顺序：

```text
1. 原地 lift start
2. 绕 P1 的有效侧
3. 穿过 P1/P2 中间
4. 绕 P2 的有效侧
5. 去 C
```

### 用中点和 offset 定义“穿中间”

不要凭截图估计“中间”。当前中间点是：

```text
between_pegs = (0.620, -0.005)
```

需要从两 peg 之间穿过时，优先用这个点附近。

### 先看 top-down/marker，再录视频

调路线时使用 viewer 和 waypoint marker：

```bash
python -m prototypes.cable_routing_oracle_demo --viewer --keep-open --keep-open-no-step --run-oracle --lite --settle-steps 8 --oracle-steps 90 --hold-steps 140 --endpoint-drag-substeps 12 --wrap-z-lift 0.040 --verbose --debug-print-oracle-steps
```

录制正式视频时可以隐藏 marker：

```bash
python -m prototypes.cable_routing_oracle_demo --run-oracle --lite --settle-steps 8 --oracle-steps 90 --hold-steps 140 --endpoint-drag-substeps 12 --wrap-z-lift 0.040 --record-video runs/demo_cable_routing_robot_oracle.mp4 --record-fps 30 --record-every-n-steps 4 --record-camera oblique --record-res 960 960 --verbose --hide-oracle-waypoints
```

## 6. 后续建议

为了减少截图沟通成本，后续可以增加一个专门的 route planning debug mode：

```text
- top-down 2D 坐标网格
- 5cm/10cm ruler
- P1/P2/C/free-end 坐标标记
- waypoint 编号
- waypoint polyline
- 可选导出 PNG
```

这样可以先确认 2D 路线，再让 Genesis/Franka/PBD 真实执行。
