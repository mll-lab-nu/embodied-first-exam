# 刚体任务的机械臂物理交互实现

> **2026-08-10 起本文引用的 `demos/legacy/` 已删除**（swap / onestroke /
> maze_wall_removal / peeling 的 demo 与录制批处理 `record_physical_demos`），
> 因此下面涉及这些 demo 的命令与文件路径不再有效。删除原因见
> [`docs/develop/framework/demo_cli_and_config_zh.md`](../framework/demo_cli_and_config_zh.md)。
> 这些任务的场景代码 `topogym/tasks/legacy/` 与任务配置保留（RL 环境壳仍在用），
> 本文其余内容按当时记录原样保留。

本文说明 Swap、OneStroke 和 Maze Wall Removal 如何通过真实刚体接触完成抓取，
而不是用 `AttachmentManager` 将物体绑定到机械臂。

## 1. 共同原则

三个 physical demo 只控制 Franka 的机械臂关节和夹爪关节：

- 不在动作执行期间调用物体的 `set_pos` 或 `set_quat`。
- 不创建 `AttachmentManager`。
- 物体是否移动，由 Genesis 的碰撞、夹爪 PD 力、摩擦和重力决定。
- Maze builder 在创建随机实例时仍会设置初始墙体位姿；这是 episode reset，
  不是机械臂动作的一部分。

共享实现位于：

- `topogym/primitives/pick_place.py`
- `topogym/primitives/physical_contact.py`
- `topogym/robot/franka.py`

## 2. 每次抓放的 12 个阶段

`PickPlacePrimitive` 将一次操作拆为：

```text
open
approach
descend
close
grasp_settle
lift_test
lift_clear
translate
place
release
release_settle
retreat
```

机械臂运动不是一次跳到目标 IK，而是把每段路径拆成多个线性 waypoint。
夹爪闭合后，位置控制器仍尝试到达闭合目标，因此在手指被物体阻挡时持续产生法向夹持力。
指垫与物体之间的摩擦力负责抵抗重力。

`lift_test` 是关键反馈阶段。夹爪先试抬约 5 cm，只有物体满足以下条件才继续：

- 物体高度至少增加 `min_lift_delta`。
- 物体 XY 没有明显离开夹爪中心。

失败时 primitive 会执行 `recovery_open` 和 `recovery_retreat`，不会继续横向搬运。

## 3. 物理接触参数

三个任务默认使用：

```yaml
finger_friction: 2.0
object/wall_friction: 0.8 ~ 1.0
noslip_iterations: 5
```

`finger_friction` 和物体摩擦通过 Genesis rigid entity/link 的 `set_friction`
设置。场景中的 `Plastic.roughness` 只影响渲染外观，不代表物理摩擦。

`noslip_iterations` 用于降低稳定夹持后的接触滑移。夹爪的夹持力来自
`franka_panda_position_ik.yaml` 中的 finger PD 增益和 force range。

## 4. Swap

Swap 方块接近正方体，采用常规两侧夹取：

```text
方块中心对准
两指闭合
试抬
水平搬运
放入空 slot
```

运行：

```bash
python -m demos.legacy.swap_physical_grasp_demo --viewer --keep-open --verbose
```

## 5. OneStroke

OneStroke 墙块尺寸为 `58 x 14 x 22 mm`，目标 gap 当前为 `36 mm`。
这给 14 mm 厚的 wall block 留出约 `11 mm` 单侧余量，比早期 26 mm gap 更容易在
viewer 中看清墙块是否落在两个色块之间。

如果夹爪跨墙块的 14 mm 薄边闭合，两根手指会处在相邻 cell 的两侧，
下降插入时容易先与 cell 碰撞。因此 physical demo 使用长轴端夹：

```text
墙块长轴 yaw = wall_yaw
夹爪闭合轴 yaw = wall_yaw + pi/2
```

手指夹住墙块 58 mm 长轴的两个端面，手指主要留在墙块两端。

搬运阶段通过 quaternion slerp 将夹爪从供料区方向旋转到目标 edge 方向。
早期实现让墙块在 slot 上方张开，再靠重力落入较窄 gap；这会给 14 mm 厚的
墙块留下翻滚和斜插空间。现在 edge slot 顶面与两个 cell 顶面齐平，形成跨 gap
的固定承托面。夹爪将墙块轻压到承托面，保持若干 physics steps 后再张开。
逻辑目标仍由 `edge_pose_for_cells()` 计算为两个相邻 cell center 连线的中点；
`physical.target_xy_bias` 默认是 `[0, 0]`，所以物理释放目标也正好落在这个几何中点。
如果某个 Genesis/runtime 仍然出现稳定方向的释放漂移，再用 CLI `--target-xy-bias X Y`
做单次补偿。
如需测试纯重力插入，可以运行 `onestroke_physical_wall_demo --no-edge-support`，
此时不会创建 gap 内的隐形承托体，wall 的目标高度也改为 board 顶面加半个 wall 高度。
最终同时检查：

- 墙块 XY 是否靠近目标 edge。
- 墙块中心是否接近目标支撑高度，避免下陷。
- 墙块 yaw 是否与目标 edge 一致；由于长方体具有 180 度对称性，按 `pi` 周期计算误差。
- 墙块局部 z 轴倾角是否小于阈值，翻滚或侧倒不会再被判为成功。
- `OneStrokePuzzleEvaluator` 是否判定颜色区域已经分离。

运行单墙 smoke 和完整任务：

```bash
python -m demos.legacy.onestroke_physical_wall_demo --max-walls 1 --viewer --keep-open --verbose
python -m demos.legacy.onestroke_physical_wall_demo --viewer --keep-open --verbose
python -m demos.legacy.onestroke_physical_wall_demo --max-walls 1 --no-edge-support --viewer --keep-open --verbose
python -m demos.legacy.onestroke_physical_wall_demo --no-edge-support --viewer --keep-open --verbose
```

默认完整命令会执行完整 separator plan；若只想达到 terminal 即停，可加
`--stop-on-terminal`。调试视觉轨迹时也可加 `--continue-on-failure`，但这类运行
只用于观察，失败 move 会让最终 `il_ready=False`。

## 6. Maze Wall Removal

Maze 墙块同样采用长轴端夹。每个 oracle move 执行：

```text
对准目标墙
夹住长轴两端
试抬
垂直拔出迷宫
移动到 discard 区
释放
```

Maze 不需要把墙重新插入窄槽，因此搬运时保持抓取姿态即可。每移除一堵墙后，
`MazeWallRemovalPuzzleEvaluator` 会重新计算 A、B 间仍需移除的最少墙数。
达到 `current_min_wall_count == 0` 才算任务完成。

当前 maze 几何为 `70 mm` cell、`40 mm` gap、`56 x 16 x 26 mm` wall block。
这不是单纯放大视觉尺寸：它给 wall 两端留下约 `7 mm` 端部余量，并给 16 mm 厚 wall
在 40 mm gap 中留下约 `12 mm` 单侧余量，减少夹爪下探时碰到相邻 wall blocks。
移除后的 wall block 会放到棋盘右侧的逻辑 discard 长条区；该区域默认不可见，但 evaluator
仍用它的 XY 范围判断墙块是否已经离开 maze。

这里的物理版本必须运行 `maze_wall_removal_physical_demo`，不要用
`maze_wall_removal_demo --solve-oracle` 生成 IL/物理交互视频。physical demo 的执行阶段
只通过 Franka gripper、刚体碰撞和摩擦移动 wall block；不使用 attachment，也不在动作执行期间
调用 wall 的 `set_pos` / `set_quat`。`MazeWallRemovalSceneBuilder.apply_instance()` 中的
`set_pos` / `set_quat` 仅用于场景构建时把 seed 对应的初始迷宫摆好，不属于策略动作。

Maze physical demo 还针对细长墙块做了以下稳定性处理：

- approach 阶段从机械臂当前 hand quaternion 到目标抓取 quaternion 做最短路径 slerp。
- 每个 Cartesian waypoint 显式使用当前 qpos 作为 IK 初值，只解 7 个手臂关节，并关闭随机重采样，避免 IK 分支跳变造成腕部绕转。
- 默认 `grasp_qpos=0.0240`。考虑 Panda 指垫内侧相对 joint 的几何偏置后，对应约 51 mm 的目标间隙，对 56 mm 长轴建立持续法向夹持力。
- 运动使用 ease-in/ease-out 插值，并将默认 `motion_steps` 提高到 240，减小起停惯性。
- 每段运动末尾额外保持 30 个 physics steps，降低控制跟踪滞后造成的抓取中心偏差。
- 试抬后保持 50 个 physics steps；若墙块漂移超过 6 mm，则立即判定抓取失败，不继续横向搬运。

运行：

```bash
python -m demos.legacy.maze_wall_removal_physical_demo --seed 11 --max-walls 1 --viewer --keep-open --verbose
python -m demos.legacy.maze_wall_removal_physical_demo --seed 11 --viewer --keep-open --verbose
```

启动时会依次输出 `building_scene`、`scene_ready`、`robot_home_ready` 和
`[pick_place start]`。如果 viewer 中看起来没有运动，可根据最后一条日志判断是场景构建、
home reset，还是首段 IK 尚未开始。

命令带有 `--viewer` 时，成功或失败后的机械臂都会回到 home，随后 viewer 默认无限驻留。
日志会输出 `viewer_hold`；此时机械臂不再运动是预期行为，按 `Ctrl+C` 退出。
自动化 smoke 若需要任务结束后立即退出，可额外传入 `--close-on-finish`。

## 7. 调参顺序

若真实运行出现失败，建议按以下顺序排查：

1. 查看 verbose 输出中的 `after_descend`，确认指垫高度对准物体。
2. 查看 `lift_check_failed`，区分没有夹住和夹住后滑落。
3. 增加 `close_hold_steps`，让夹持力充分建立。
4. 降低运动速度，即增加 `motion_steps`。
5. 小幅提高 finger friction 或 wall friction。
6. 最后才调整 grasp yaw、抓取高度或任务几何。

摩擦系数只能改善已有接触，不能补偿错误的抓取位置或夹爪与 cell 的几何碰撞。
