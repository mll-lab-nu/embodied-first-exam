# PBD 绳索任务的机械臂物理交互

本文说明 knots/untangle 与 cable routing 如何从脚本 attachment 改成机械臂物理夹持。

## 目标

新的 physical demo 在动作执行期间遵守以下约束：

- 不使用 `AttachmentManager` 把把手绑定到机械臂。
- 搬运和插入期间不调用把手的 `set_pos`。
- 不逐帧调用 `set_particles_pos` 搬运绳端或重塑整根绳。
- 机械臂只控制关节和夹爪，刚性把手是否被拿起由碰撞、夹持力、摩擦和重力决定。
- PBD 绳索的其余粒子继续由 Genesis `scene.step()` 演化。

Cable 到达终点并通过插入检查后是一个例外：connector 自身的 snap-lock 会激活固定约束。此时对 pole 的位置保持属于终点机构状态，而不是机械臂抓取捷径。

相关文件：

- `topogym/primitives/pbd_handle_drag.py`
- `topogym/tasks/entangle/untangle.py`
- `topogym/tasks/routing/cable_routing.py`
- `demos/entangle/untangle_physical_handle_demo.py`
- `demos/routing/cable_routing_physical_handle_demo.py`

## 交互模型

直接用 Panda 指垫夹 PBD tube 容易受到软体接触、粒子分辨率和局部形变影响。当前版本在绳端加入一个真实的刚性 terminal handle：

1. handle 是 `fixed=false`、`collision=true` 的刚体圆柱。
2. 夹爪通过刚体碰撞接触 handle。
3. finger 与 handle 的物理摩擦系数默认均为 `2.0`。
4. 夹爪位置控制器持续尝试达到 `grasp_qpos`，被 handle 阻挡后产生法向夹持力。
5. Genesis 的 `fix_particles_to_link` 将一组端点 PBD particles 约束到 handle 的 rigid link。

handle 使用 `needs_coup=false`，避免嵌入 handle 内部的端点 particles 与同一个 handle 发生重复碰撞。PBD rope 与棋盘、其他 rope、routing peg 的物理求解仍然保留。

这和旧方案的关键区别是：机械臂到 handle 之间没有脚本 attachment，handle 的抬升和拖动必须由夹爪接触成功后才能发生。

运行 physical demo 时会额外打印两条 grep-friendly contract：

```text
untangle_physical_handle_demo il_contract mode=collision_based_contact ...
untangle_physical_handle_demo pbd_contract rope_model=pbd_elastic_tube endpoint_constraint=fix_particles_to_link ...
```

第一条说明机械臂只通过夹爪碰撞接触操作 rigid handle；第二条说明 rope 端点和 handle
之间使用 Genesis 原生 PBD-to-rigid-link 约束。demo 启动时还会校验
`attachment_mode=rigid_handles`、`fixed=false`、`collision=true`、
`exclude_pbd_collision=true`，不满足就直接报错。

## 九个动作阶段

`PBDHandleDragPrimitive` 把一次端点拖动拆成九个阶段：

```text
open
approach
descend
close
grasp_settle
lift_test
drag
release
retreat
```

其中 `lift_test` 会检查：

- handle 实际抬升量是否大于 `min_lift_delta`。
- handle 是否仍靠近机械臂实际指垫中心。

未通过时会张开夹爪并撤回，不继续拖绳。`drag` 使用连续 IK、ease-in/ease-out waypoint 和每段末尾的 physics settle，降低急停造成的滑落。

## Knots / Untangle

每根 rope 的两个 endpoint 都创建动态 handle，并分别通过 `fix_particles_to_link` 连接对应端点 particles。高层 topology planner 选择：

```text
rope index + start/end endpoint + target hole
```

physical primitive 随后完成：

```text
夹住选定 handle
抬离棋盘
搬运到目标 hole 上方
下降并释放
```

单动作 smoke：

```bash
python -m demos.entangle.untangle_physical_handle_demo run.viewer=true run.lite=true run.max_moves=1 run.verbose=true
```

完整规划：

```bash
python -m demos.entangle.untangle_physical_handle_demo run.viewer=true run.lite=true run.verbose=true
```

`untangle_physical_handle_demo` 默认使用 tabletop V1 的 common/env/task config。完整模式会持续执行到 topology terminal 或 `--max-moves` 上限。每个 move 都包含：

1. 高层 planner 选择需要移动的 rope endpoint。
2. 最多执行 `max_grasp_attempts` 次物理抓取。
3. 释放后等待 PBD 与刚体稳定。
4. 检查 handle 到目标 hole 的 XY 误差。
5. 只有物理落点通过，才提交对应的离散 topology action。

因此不会出现“夹爪已经滑脱，但高层状态仍假装动作成功”的情况。

viewer 默认在任务结束后驻留，按 `Ctrl+C` 退出；自动测试可加 `--close-on-finish`。

## Cable Routing

cable physical demo 现在默认使用 tabletop V1：

- `common_configs/topogym_tabletop_v1.yaml`
- `env_configs/topogym_tabletop_v1.yaml`
- `task_configs/cable_routing_topogym_tabletop_v1.yaml`

与 untangle 相同，机械臂不直接 attach 到 cable，也不逐帧 `set_particles_pos` 搬运整根 cable。运行时会强制检查 free-end handle：

```text
attachment_mode=rigid_handle
fixed=false
collision=true
exclude_pbd_collision=true
```

如果这些条件不满足，`cable_routing_physical_handle_demo` 会在开始动作前直接报错。日志中的 `il_contract` 表示机械臂只通过夹爪碰撞操作 rigid handle；`pbd_contract` 表示 cable free-end particles 通过 Genesis `fix_particles_to_link` 连接到该 handle。终点 `ConnectorLatch` 只表示插座捕获后的环境锁扣，不参与前面的运输和绕柱动作。

cable 的 start endpoint 继续固定在 `S`，free end 使用一个动态 handle。机械臂物理夹住该 handle 后，沿 P1、P2 和 C 的 waypoint 序列连续拖动。

先验证一次夹持和短距离拖动：

```bash
python -m demos.routing.cable_routing_physical_handle_demo run.viewer=true run.lite=true run.max_waypoints=1 run.verbose=true
```

运行完整走线：

```bash
python -m demos.routing.cable_routing_physical_handle_demo run.viewer=true run.lite=true run.verbose=true
```

完整模式只抓取一次 free-end handle，并在保持夹爪闭合的情况下连续执行全部 waypoint。每一段结束都会检查 handle 与实际指垫中心的跟随误差；超过 `max_segment_follow_error` 会立即释放、撤回并终止，不会继续用已经滑脱的夹爪走剩余轨迹。

在 P1、P2 和 C 的关键 waypoint 会输出 `cable_routing_phase_verify`，完整释放并稳定后再输出最终 `cable_routing_verify`。

### Connector socket 与 latch

旧的 C 只是一个 `collision=false` 的实心视觉方块，pole 放到附近后没有任何结构可以抵抗重力或绳索回拉。physical demo 现在将 C 替换为：

- 一个低矮的四壁开口 socket。
- 28 mm 的内部开口，用于容纳直径 20 mm 的 pole。
- 6 mm 高的导向壁，位于夹爪主要抓取区域下方。
- 一个条件触发的 `ConnectorLatch`。

最后一个 waypoint 会把 pole 从上方向下插入 socket。`ConnectorLatch` 在每个仿真步结束后自动检查：

```text
XY error <= latch_capture_tolerance_xy
Z error  <= latch_capture_tolerance_z
tilt     <= latch_capture_max_tilt_deg
```

只有三个条件同时满足，latch 才会变为 `active`，把 pole 对齐并固定到 connector 中。这个状态只会从未锁定变为已锁定，不会因为下一个仿真步的瞬时误差重新打开。之后夹爪张开、撤离，PBD endpoint 仍连接在 pole 上，因此 cable 终点随 pole 一起保持在 C。

这相当于真实 connector 的 snap-fit/click-lock：插入动作必须通过机械臂物理完成，但锁扣闭合是环境机构的离散状态变化。只有 C 创建这个 attachment；P1、P2 和夹爪运输阶段都不会触发。它不会在远处吸附 pole，也不会帮助前面的绕线动作。

verbose 日志会输出：

```text
cable_routing_physical_handle_demo connector_latch engaged=True ...
```

最终成功要求同时满足 `latch_engaged=True`、endpoint 位置检查和 PBD 绕柱检查。

完整运行结束后同时检查：

- `physical_success`：handle 是否通过真实夹持完成抬升和到达终点。
- `endpoint_route_ok`：handle 轨迹是否从要求的一侧绕过 peg。
- `rope_wrap_ok`：最终 PBD particles 是否与 peg 接触，并保留目标侧的包角。
- `routing_success`：所有目标 peg 是否同时通过轨迹与 PBD 形态检查。

`--max-waypoints` 是夹持 smoke，不代表完成整条 route，因此结果中的 `full_route=false`、`success=false` 是预期的；应查看 `physical_success`。

## 参数位置

通用物理参数分别放在：

- `configs/task_configs/untangle.yaml` 的 `physical_handle`
- `configs/task_configs/cable_routing.yaml` 的 `physical_handle`

优先调节顺序：

1. `grasp_qpos`：保证指垫确实压住 handle，而不是在其外侧闭合。
2. `z_offset`：保证 handle 底部落在棋盘表面，指垫中心对准 handle 中部。
3. `close_hold_steps`：给夹持接触足够的收敛时间。
4. `move_steps` 和 `motion_settle_steps`：降低搬运加速度和控制滞后。
5. `finger_friction` 与 `handle_friction`：只用于改善已经建立的接触，不能补偿抓取位置错误。
6. cable 的 `wrap_z_lift` 与 routing waypoints：调节绳索绕 peg 时的高度和外侧路径。
7. `fixtures.C.socket.inner_size`：过小会撞 pole/夹爪，过大会失去导向意义。
8. `latch_capture_tolerance_xy/z`：决定 connector 卡扣允许多大的插入误差。
9. `latch_capture_max_tilt_deg`：防止横倒的 pole 在靠近终点时被错误吸附。

## 当前边界

`fix_particles_to_link` 是 Genesis solver 内部的 PBD-to-rigid-link 约束，不是 Python 逐帧搬运。但 Genesis 1.1.0 当前实现主要按 rigid link 位姿更新 attached particles，绳索张力对 handle 的反作用并不是完整的双向力耦合。因此：

- 夹爪是否真正夹住 handle 是物理结果。
- handle 是否拖动绳端由原生 solver 约束保证。
- rope 的形变、碰撞、绕柱和滑动由 PBD 求解。
- 当前还不能把“绳子反向拉动机械臂/handle 的力反馈”视为完整建模。

Connector latch 在未激活时通过兼容不同 Genesis 版本的 `scene.step` hook 持续检测插入；激活后则在每个仿真步前后保持 pole 的固定 pose。它是显式建模的终点锁扣，而不是纯粹依赖 socket 摩擦的被动卡紧。若以后需要研究插头拔出力、卡扣弹性或失败脱落，应将该离散 latch 换成带可断裂 joint/spring 的双向动力学模型。

另外，Untangle 的 topology terminal 目前仍由高层离散状态在物理动作成功后更新，并非从 PBD 粒子几何重新识别 crossing/knot。Cable 已使用最终 PBD particle 指标验证绕柱形态。这两项是后续从 demo 走向模仿学习数据生产时需要继续补齐的验证层。
