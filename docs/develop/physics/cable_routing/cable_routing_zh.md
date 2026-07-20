# Cable Routing 开发记录

## 当前 MVP

第一版只放四个 fixture：

- `S`：起点固定端
- `C`：终点 connector
- `P1`：routing peg
- `P2`：routing peg

场景里只有一根 PBD cable。当前 viewer 支持两种 route：

- `initial`：从 `S` 到 `C` 的近似直线，routing relation 故意不满足目标。
- `goal`：按目标签名预成型，当前目标是 `P1:left -> P2:right -> C:endpoint`。

当前 oracle demo 从 `initial` 出发，默认使用 `endpoint-physics`：Franka 抓住 cable 自由端 handle，脚本保留 `scene.step()`，只驱动 end endpoint particles，rope 其余部分交给 Genesis PBD 演化。routing 子目标不再只是 `P1:left -> P2:right -> C` 三个稀疏点；对每个 peg 会生成一串绕柱弧线 waypoint，再落到目标侧。

统一任务语义：`initial` route 只有 start endpoint 固定在 S，另一端是躺在桌面上的自由端，不与 C 或任何 fixture 连接。机械臂先抓这个自由端，再绕过两个 peg，最后把自由端带到 C。`initial` 的长度必须大于目标 routing signature 的长度一点，否则 PBD 会强烈倾向于拉直切角，机械臂即使绕桩，绳子也会从 peg 上滑掉。

当前 `initial` 是一条温和的桌面 slack route，终点是独立 pickup/free-end 点，而不是 C。自由端放在 P1 上方/右上方附近，避免一开始就落在 P2 外侧；这样 demo 从“抓住就近自由端并先绕 P1”开始。为验证 P2 外侧失败是否来自绳长不足，初始路线在棋盘 viewer-upper 边缘加入了一个平滑外弧，长度从约 `0.552 m` 增加到约 `0.677 m`，增加约 `0.125 m`，但 S 和自由端位置保持不变。初始线仍不使用末端回折或卷尺式小半径 coil。

physical demo 的 setup 日志会打印 `initial_rope_length`、`goal_reference_length` 和 `reference_slack`。这里的 goal 只是目标签名中心线的参考长度，实际绕柱会消耗更多长度，因此不能把 `reference_slack` 当作精确剩余量；它主要用于确认不同实验配置确实使用了不同绳长。

Slack route 的控制点不能形成尖锐回折。Genesis/TetGen 会先把 rope centerline 生成 tube surface mesh，再四面体化；如果某个控制点让 tube 在局部近似 U-turn，surface mesh 会自交，报 `The input surface mesh contain self-intersections`。这种错误发生在 scene build 阶段，和 robot/PBD step 无关。解决方式是把 slack route 改成多段圆角外圈，避免在一个控制点上突然反向折回 endpoint。

机械臂轨迹和 rope 目标关系要分开理解：`side_clearance` 控制目标 routing signature 的 rope 侧点，`endpoint_side_clearance` 控制 Franka 抓着自由端绕 peg 时的外圈半径。后者需要更大，因为手爪本体有体积，太贴 peg 会导致绳子没有被带到柱子外侧，甚至让手爪/handle 与 peg 或 board 发生不稳定接触。当前默认先采用 red-line 调试值：`endpoint_side_clearance=0.150`、`wrap_arc_points=12`、`wrap_overshoot_degrees=130`、`peg_approach_scale=1.50`。另外，针对 P1 增加了显式前向拉线阶段：`peg_front_pull_targets.P1=[0.860,-0.210,0.768]`、`peg_front_pull_fixtures=[P1]`。这会在 `wrap_P1_left_*` 后插入 `front_pull_P1_left`，让机械臂直接走到 P2/C 象限的 red-line staging point，而不是靠相对方向猜。`peg_departure_extension=0.160` 会在绕完一个 peg 后额外向下一个 fixture 方向带出一段距离。最后从 P2 去 C 时还有 `connector_approach_extension=0.145`：它不是从外廊点短切回 C，而是沿 P2->C 方向越过 C 一段距离，再执行 `insert_at_C`，避免终点方向带出不够远。确认 rope 能物理绕住后，再逐步把这些极端值往回收。

不要在绕过 peg 后再直线回到精确的 `P*:left/right` 侧点：这会形成一个穿过 peg 内侧的 chord，把刚绕出的形态撤掉。endpoint oracle 现在让绕柱 arc 停在 overshoot 点，并在去下一个 peg 前先走 `transition_*` 外侧 approach waypoint，避免从两桩中间回切。如果某个 peg 已经插入 `front_pull_*`，后续 transition 会直接从 front-pull 后的位置出发，不再 snap back 到该 peg 的 side corridor；否则会把刚往前拉出的红线轨迹又撤掉。

如果 log 中某个 peg 的 `endpoint_route_ok=True` 但 `rope_contact=False`，要看后续 transition 是否把 rope 从该 peg 上拉掉。例如 P1 绕完后若直接以当前 overshoot 点的 x 坐标向 P2 方向移动，路径可能穿过 P1 中心附近，导致 P1 被 unwound。当前 transition 会先回到当前 peg 的目标侧外廊，再去下一个 peg 的 approach 点。

在 `endpoint-physics` 模式下，`--run-oracle` 保留 start endpoint 的 fixed-particle 约束，end endpoint 保持自由，并只在手爪拖动自由端时同步 end endpoint particles。旧 crash 路径来自“每帧全粒子 `set_particles_pos` 后立刻 `scene.step()`”，现在默认路径不再这样做。

如果场景里包含 Franka，oracle demo 会在 cable 自由端生成一个 `cable_free_end_handle`，手爪先张开靠近该 handle，再闭合抓住它，然后沿 `free_end -> P1:left -> P2:right -> C` 的子目标移动。`endpoint-physics` 不再每帧全粒子 `set_particles_pos`，这是此前 native segfault 的核心触发条件。

跑完 `endpoint-physics` oracle 后会打印 `cable_routing_verify`：

- `endpoint_route_ok`：自由端/手爪轨迹是否从目标侧绕过 peg。这回答“机械臂有没有按脚本绕柱走”。
- `rope_contact`：PBD rope 粒子最终是否贴近 peg 表面。这回答“绳子是否真的碰到了柱子”。
- `rope_wrap_ok`：在接触的基础上，rope 粒子是否出现在目标侧，并形成一定角度跨度。这回答“绳子物理上是否留下绕柱形态”。

如果 `endpoint_route_ok=True` 但 `rope_wrap_ok=False`，说明机械臂轨迹绕了，但 rope 被 PBD/摩擦/松弛滑掉了；这时优先调绕柱 waypoint、peg collision、rope friction 和 hold/settle，而不是退回全粒子 kinematic reshape。

如果 verbose log 里 `endpoint_drag` 的 `source.z` 明显低于目标 `target.z`，通常表示 robot PD/IK 还没有追上每个 waypoint，自由端 handle 被实际手爪位置拖低。这个状态很容易让 rope 接近 board 顶面或 peg 底部，进而触发 PBD native crash。优先提高 `--endpoint-drag-substeps`，必要时小幅提高 `--wrap-z-lift`；这仍然保留真实 `scene.step()`，只是让每个 waypoint 有更多物理步去收敛。

Cable Routing 覆盖了更宽的 `oblique` 相机，以便把 robot base、手爪和 routing board 一起拍进画面。正常 verbose log 应出现 `robot_present=True robot_follow=True oracle_mode=endpoint-physics`。

`--oracle-mode kinematic` 是旧的稳定展示模式：它会全粒子 reshape rope，并且录制时不调用 `scene.step()`。`--oracle-mode kinematic --oracle-physics-step --debug-print-oracle-steps` 只用于复现/诊断旧路径的 native PBD solver crash，正常录制不要加。

## 本次稳定性经验

这次 segmentation fault 的直接定位结论是：崩溃发生在 oracle 的第三段 `insert_at_C` 中，日志停在 `before_advance` 之后、`after_advance` 之前，也就是进入 Genesis native `scene.step()` / PBD solver 时崩溃。它不是 TetGen 建模、EGL warning、视频写入或 HUD overlay 的问题；这些日志都已经在崩溃前正常完成。

触发条件是旧 kinematic oracle 每一帧都对 PBD rope 做全粒子 `set_particles_pos`，然后立刻让 Genesis PBD solver 继续 `scene.step()`。这相当于一边把整根 rope 强行瞬移到脚本轨迹，一边让物理解算器按约束、碰撞和固定端继续求解，容易制造 native 层无法恢复的状态。自由端是否固定会加重约束冲突，但当前复现路径的核心问题是“全粒子重写 + PBD step”的组合。

不能把“去掉 `scene.step()`”当作修复。录制可以暂时不 crash，但 robot joint、attachment、collision、PBD rope 和 camera/render 同步都不会真正推进；结果只是 HUD 或手写粒子画面在变，机械臂和物理世界没有执行任务。以后所有需要证明 robot manipulation 的 demo 都必须保留真实 `scene.step()`，问题要通过减少非法粒子写入、改成端点 attach/drag、调整碰撞和约束来修。

## 当前落地文件

- `topogym/tasks/cable_routing.py`
  - `CableRoutingLayout`
  - `CableRoutingSignature`
  - `CableRoutingScene`
  - `CableRoutingSceneBuilder`
- `configs/task_configs/cable_routing.yaml`
- `prototypes/cable_routing_oracle_demo.py`

## 复用路径

当前 rope mesh 和 PBD 逻辑复用 `topogym.tasks.untangle` 里的能力：

- `_sample_polyline`
- `_make_elastic_tube_mesh`
- `_write_obj`
- `_endpoint_particle_indices`
- `RopeEndpointHandle`

第一版只固定 cable 的 start endpoint；end endpoint 在任务语义上保持自由。当前 `endpoint-physics` oracle 不重塑整根 cable，只用一个自由端 handle 把 end endpoint particles 稳定在手爪抓取点附近，再让 Genesis PBD 通过真实 `scene.step()` 演化其余 rope。

## 稳定性选择

为了先看清建模，fixture 默认是视觉件，`collision: false`。这样可以避免 PBD rope 和 peg/connector 初始重叠触发 native solver crash。等 oracle path 和视觉布局确认后，再逐步打开：

1. peg collision
2. connector insertion collision
3. robot grasp endpoint / connector handle

## 后续修复路线

最终标准不是“手爪轨迹绕过 peg”，而是 rope 物理上在两个 peg 外侧留下接触/包角，并由两个 peg 共同约束住 rope。现在要按下面顺序推进：

1. 自由端初始化：`initial` 只能从 S 到桌面上的 pickup/free-end 点，不连接 C。构建后第一步 `scene.step()` 前，先用 `EndpointAttachmentManager` 把 end endpoint particles 同步到 `cable_free_end_handle`，避免自由端在 settle 时像弓弦一样突然甩开。
2. 抓取稳定：手爪接近和闭合阶段仍保持 end endpoint 绑定到 free-end handle；手爪抓住 handle 后，再用 rigid attachment 让 handle 跟随手爪。每个 waypoint 后显式同步 endpoint，减少 handle 和 rope endpoint 的半步滞后。
3. peg 碰撞：正常 oracle 必须打开 P1/P2 collision。`--disable-peg-collision` 只能诊断轨迹，不能验证物理绕柱；没有碰撞时 rope 不可能被 peg 拉住。
4. 外侧路径：绕完一个 peg 后不要回切到两桩中间；transition 要从当前 peg 的外侧 corridor 离开，再去下一个 peg 的外侧 approach 点。若前一步已经做了 `front_pull_*`，该点本身就是 departure waypoint，不应再回到 side corridor。
5. 物理留存：如果 `endpoint_route_ok=True` 但 `rope_wrap_ok=False`，优先增大 `endpoint_side_clearance`、`wrap_overshoot_degrees`、`endpoint-drag-substeps`、`hold-steps`，并检查摩擦；如果仍然滑掉，说明光滑圆柱 peg 不足以稳定保形，需要给 peg 增加浅槽、挡圈或更高摩擦的 guide surface。

暂时不采用“卷尺式 coil”作为默认初始态：coil 能把绳长收纳在起点附近，但小半径多圈 tube mesh 很容易自交，TetGen/PBD 初始化风险比当前任务收益更高。等基础 routing 稳定后，可以再单独做 spool/coil fixture。

## Viewer 命令

查看初始错误 routing：

```bash
python -m prototypes.cable_routing_oracle_demo --viewer --keep-open --route-mode initial --verbose
```

查看目标 routing：

```bash
python -m prototypes.cable_routing_oracle_demo --viewer --keep-open --route-mode goal --verbose
```

如果 PBD rope 初始化太慢，可以先加 `--lite`：

```bash
python -m prototypes.cable_routing_oracle_demo --viewer --keep-open --route-mode goal --lite --verbose
```

录制带 Franka 视觉参与的 oracle demo：

```bash
python -m prototypes.cable_routing_oracle_demo --run-oracle --lite --settle-steps 8 --oracle-steps 90 --hold-steps 140 --endpoint-drag-substeps 12 --wrap-z-lift 0.040 --record-video runs/demo_cable_routing_robot_oracle.mp4 --record-fps 30 --record-every-n-steps 4 --record-camera oblique --record-res 960 960 --verbose
```

录制只含 routing board/cable 的 kinematic oracle demo：

```bash
python -m prototypes.cable_routing_oracle_demo --run-oracle --oracle-mode kinematic --no-robot --lite --settle-steps 8 --oracle-steps 90 --hold-steps 50 --record-video runs/demo_cable_routing_oracle.mp4 --record-fps 60 --record-camera oblique --record-res 960 960 --verbose
```

诊断 native PBD step 的崩溃位置，预期可能 segfault：

```bash
python -m prototypes.cable_routing_oracle_demo --run-oracle --oracle-mode kinematic --no-robot --lite --settle-steps 8 --oracle-steps 90 --hold-steps 50 --record-video runs/demo_cable_routing_oracle.mp4 --record-fps 60 --record-camera oblique --record-res 960 960 --verbose --oracle-physics-step --debug-print-oracle-steps
```

如果想在场景中看到 Franka，不要加 `--no-robot`；如果想保留 Franka 但不让它跟随 oracle 动作，可以加 `--no-robot-oracle-follow`。
