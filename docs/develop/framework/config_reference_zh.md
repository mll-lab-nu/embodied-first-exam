# TopoGym 配置参数速查表

本文按“环境、机器人操纵、Swap 任务、MDP/RL、运行命令”几层整理当前配置。
目的是让我们后续调物理、控制和训练时，能快速知道每个参数控制什么。

## 通用操作空间

来源：`configs/common_configs/manipulation_space.yaml`

这份配置作为 `cfg.common` 加载。环境、机器人控制和任务 YAML 通过
`${common.*}` 引用它，避免每个任务分别维护棋盘、机器人安装位和 home pose。

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `manipulation_space.base.pos` | `[0.60, 0.00, 0.751]` | 通用底板中心。 |
| `manipulation_space.base.size` | `[0.70, 0.80, 0.002]` | 通用底板尺寸；与 task board 共用 XY footprint，Swap 当前直接使用这一层。 |
| `manipulation_space.board.pos` | `[0.60, 0.00, 0.7555]` | 各任务棋盘的统一中心。 |
| `manipulation_space.board.size` | `[0.70, 0.80, 0.007]` | 各任务棋盘的统一尺寸。 |
| `manipulation_space.workspace.x` | `[0.35, 0.75]` | 当前保守末端 x 边界；扩大前需通过 demo 和 IK sweep 验证。 |
| `manipulation_space.workspace.y` | `[-0.20, 0.20]` | 当前保守末端 y 边界；扩大前需通过 demo 和 IK sweep 验证。 |
| `manipulation_space.workspace.z` | `[0.78, 1.10]` | 候选末端 z 边界。 |
| `manipulation_space.grid.spacing` | `0.10` | basic env demo 的尺度网格间距。 |
| `robot_setup.mount.pos` | `[0.15, 0.00, 0.75]` | Franka 通用安装位置；MJCF 安装面与桌面顶面齐平。 |
| `robot_setup.home.qpos` | `[0.0, -0.65, ..., 0.04, 0.04]` | Franka 通用初始关节状态。 |
| `robot_setup.home.settle_steps` | `100` | reset 到 home 后的稳定步数。 |

交互式尺寸调试入口：

```bash
python -m prototypes.basic_env_demo --viewer --keep-open --verbose
python -m prototypes.basic_env_demo --viewer --keep-open --no-robot \
  --board-size 0.70 0.80 --workspace-x 0.32 0.86 --workspace-y -0.30 0.30
```

第二条命令只做本次运行覆盖，不修改 YAML，适合我们逐轮比较尺寸。

通用棋盘与正式子任务的静态对接入口：

```bash
python -m prototypes.common_task_demo --task swap --viewer --keep-open --verbose
python -m prototypes.common_task_demo --task onestroke --viewer --keep-open --verbose
python -m prototypes.common_task_demo --task maze_wall_removal --viewer --keep-open --seed 11 --verbose
python -m prototypes.common_task_demo --task cable_routing --route-mode initial --lite --viewer --keep-open --verbose
python -m prototypes.common_task_demo --task peeling --viewer --keep-open --verbose
python -m prototypes.common_task_demo --task stacked_plate --viewer --keep-open --verbose
python -m prototypes.common_task_demo --task untangle --lite --viewer --keep-open --verbose
```

这些命令直接调用各任务正式 `SceneBuilder`，把 Franka reset 到通用 home
pose，但不会执行抓取、拖动或 oracle。它们用于检查任务布局是否正确落在
`0.70m x 0.80m` 通用棋盘上。

## 一句话关系

当前低层 MDP 的一个 RL action 会执行多次 Genesis 物理步：

```text
仿真时长 = iterations * num_steps_per_env * steps_per_action * sim.dt
```

例如当前 smoke 命令：

```text
1 * 8 * 20 * 0.01 = 1.6 秒仿真时间
```

## 环境与世界配置

来源：`configs/env_configs/common_room.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `genesis.backend` | `cpu` | Genesis 使用的计算后端，可选 CPU/GPU/CUDA 路径。 |
| `genesis.precision` | `"32"` | 仿真数值精度，32 位更快。 |
| `genesis.logging_level` | `warning` | Genesis 日志等级。 |
| `sim.n_envs` | `0` | Genesis 构建时的环境数量参数；当前原型走单场景 smoke。 |
| `sim.dt` | `0.01` | 每次 `scene.step()` 推进的仿真时间，单位秒。 |
| `sim.substeps` | `4` | 每个物理步内部细分次数，主要影响接触稳定性。 |
| `sim.gravity` | `[0, 0, -9.81]` | 世界重力。 |
| `renderer.type` | `rasterizer` | 渲染器类型。 |
| `renderer.show_viewer` | `false` | 配置默认不打开 viewer；脚本里由 `--viewer` 决定。 |
| `viewer.camera_pos` | `[2.1, -1.3, 1.5]` | 交互 viewer 的相机位置。 |
| `viewer.camera_lookat` | `[0.55, 0.0, 0.85]` | 交互 viewer 的观察中心。 |
| `viewer.camera_fov` | `45` | 交互 viewer 视场角。 |
| `viewer.max_fps` | `60` | viewer 最大刷新帧率，不改变仿真步长。 |
| `world.plane.enabled` | `true` | 是否添加地面。 |
| `world.table.pos` | `[0.50, 0.0, 0.375]` | 桌子中心位置。 |
| `world.table.size` | `[1.30, 1.00, 0.75]` | 桌子尺寸；扩大后的桌面完整承托 Franka 底座和任务棋盘。 |
| `world.table.color` | `[0.78, 0.80, 0.82]` | 桌子颜色。 |
| `world.stage.pos` | `${common.manipulation_space.base.pos}` | 桌面通用底板中心。 |
| `world.stage.size` | `${common.manipulation_space.base.size}` | 桌面通用底板尺寸。 |
| `world.stage.color` | `[0.92, 0.92, 0.94]` | 桌面任务区域颜色。 |
| `robot_mount.pos` | `${common.robot_setup.mount.pos}` | Franka 基座安装位置。 |
| `robot_mount.euler` | `${common.robot_setup.mount.euler}` | Franka 基座安装朝向。 |

## 录制相机配置

来源：`configs/env_configs/common_room.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `cameras.oblique.res` | `[512, 512]` | 斜视录制相机分辨率。 |
| `cameras.oblique.pos` | `[1.35, -0.95, 1.35]` | 斜视录制相机位置。 |
| `cameras.oblique.lookat` | `[0.55, 0.0, 0.78]` | 斜视录制相机观察中心。 |
| `cameras.oblique.up` | `[0, 0, 1]` | 斜视录制相机上方向。 |
| `cameras.oblique.fov` | `50` | 斜视录制相机视场角。 |
| `cameras.topdown.res` | `[512, 512]` | 俯视录制相机分辨率。 |
| `cameras.topdown.pos` | `[0.55, 0.0, 1.65]` | 俯视录制相机位置。 |
| `cameras.topdown.lookat` | `[0.55, 0.0, 0.75]` | 俯视录制相机观察中心。 |
| `cameras.topdown.up` | `[0, 0, 1]` | 俯视录制相机上方向。 |
| `cameras.topdown.fov` | `45` | 俯视录制相机视场角。 |

## 机器人资产与关节配置

来源：`configs/robot_control_configs/franka_panda_position_ik.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `robot.name` | `franka_panda` | 机器人名称。 |
| `robot.asset` | `xml/franka_emika_panda/panda.xml` | Genesis/MJCF 机器人资产路径。 |
| `robot.joint_names` | 7 个 arm 关节 + 2 个 finger 关节 | 控制器要控制的关节列表。 |
| `robot.arm_joint_count` | `7` | 机械臂关节数量。 |
| `robot.gripper_joint_count` | `2` | 夹爪关节数量。 |
| `robot.ee_link` | `hand` | IK 使用的末端 link。 |
| `home.qpos` | `[0.0, -0.65, ..., 0.04, 0.04]` | reset 后的 home 关节位置。 |
| `home.settle_steps` | `100` | reset 到 home 后额外等待的物理步数。 |

## 机器人控制参数

来源：`configs/robot_control_configs/franka_panda_position_ik.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `controller.type` | `position` | 当前使用关节位置控制。 |
| `controller.kp` | `[4500, ..., 100, 100]` | 每个受控关节的位置控制刚度。 |
| `controller.kv` | `[450, ..., 10, 10]` | 每个受控关节的速度阻尼。 |
| `controller.force_lower` | `[-87, ..., -100, -100]` | 每个关节控制力下限。 |
| `controller.force_upper` | `[87, ..., 100, 100]` | 每个关节控制力上限。 |
| `ik.enabled` | `true` | 是否使用 IK 控制末端位姿。 |
| `ik.default_ee_quat` | `[0, 1, 0, 0]` | 默认末端姿态。 |
| `gripper.open_qpos` | `0.04` | 夹爪张开目标关节位置。 |
| `gripper.closed_qpos` | `0.00` | 夹爪闭合目标关节位置。 |
| `control_loop.steps_per_action` | `20` | 一个 RL action 执行多少个 Genesis 物理步。 |
| `control_loop.interpolation` | `linear` | 预留的插值策略字段。 |
| `control_loop.use_plan_path` | `false` | 是否使用多 waypoint 规划路径；当前控制器尚未启用。 |
| `control_loop.plan_waypoints` | `80` | 预留的规划 waypoint 数量。 |

## 低层动作域配置

来源：`configs/robot_control_configs/franka_panda_position_ik.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `action_protocol.mode` | `ee_delta` | 动作语义是末端增量控制。 |
| `action_protocol.dims` | `[dx, dy, dz, dyaw, gripper]` | 规划中的动作维度；当前 MDP 使用 `[dx, dy, dz, gripper]` 四维。 |
| `action_protocol.max_delta_xyz` | `0.03` | 单个 RL action 的最大末端位移，单位米。 |
| `action_protocol.max_delta_yaw` | `0.20` | 预留的 yaw 最大增量，当前低层 MDP 尚未使用。 |
| `workspace.x` | `${common.manipulation_space.workspace.x}` | 末端目标 x 范围。 |
| `workspace.y` | `${common.manipulation_space.workspace.y}` | 末端目标 y 范围。 |
| `workspace.z` | `${common.manipulation_space.workspace.z}` | 末端目标 z 范围。 |

## Swap 布局与物体配置

来源：`configs/task_configs/swap.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `task.id` | `swap` | 任务 ID。 |
| `task.difficulty` | `smoke` | 当前任务难度标签。 |
| `task.success_tolerance_xy` | `0.045` | 判断目标方块到目标 slot 的 XY 成功半径。 |
| `slot_size` | `[0.056, 0.056, 0.006]` | slot 尺寸。 |
| `slot_color` | `[0.90, 0.92, 0.93]` | slot 颜色。 |
| `slots[0].pos` | `[0.55, -0.184, 0.755]` | slot 0 中心位置。 |
| `slots[1].pos` | `[0.55, -0.092, 0.755]` | slot 1 中心位置。 |
| `slots[2].pos` | `[0.55, 0.000, 0.755]` | slot 2 中心位置。 |
| `slots[3].pos` | `[0.55, 0.092, 0.755]` | 目标空位 slot 3 中心位置。 |
| `slots[4].pos` | `[0.55, 0.184, 0.755]` | slot 4 中心位置。 |
| `blocks.*.initial_slot` | `0, 1, 2, 4` | 每个方块初始所在 slot，slot 3 留空。 |
| `blocks.*.size` | `[0.038, 0.038, 0.038]` | 方块尺寸。 |
| `blocks.*.color` | 各色 RGB | 方块颜色。 |

## Swap Oracle 参数

来源：`configs/task_configs/swap.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `oracle.block_to_move` | `block_green` | scripted oracle 要移动的方块。 |
| `oracle.source_slot` | `4` | scripted oracle 的起始 slot。 |
| `oracle.target_slot` | `3` | scripted oracle 的目标空 slot。 |
| `primitive.approach_z` | `0.98` | 抓取前悬停高度，指的是 `hand` link 目标 z。 |
| `primitive.grasp_z` | `0.878` | 下探抓取高度，指的是 `hand` link 目标 z。 |
| `primitive.lift_z` | `1.05` | 抬起搬运高度，指的是 `hand` link 目标 z。 |
| `primitive.place_z` | `0.878` | 放置高度，指的是 `hand` link 目标 z。 |
| `primitive.steps_per_phase` | `80` | oracle 每个移动阶段执行多少个物理步。 |
| `primitive.gripper_steps` | `30` | oracle 开合夹爪时执行多少个物理步。 |

物理抓取 demo 另外使用 `physical` 小节：

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `physical.finger_friction` | `2.0` | 两个 Franka finger link 的刚体摩擦系数。 |
| `physical.block_friction` | `0.8` | Swap 方块的刚体摩擦系数。 |
| `physical.noslip_iterations` | `5` | 接触求解后的 no-slip 迭代数，用于抑制夹持滑移。 |
| `physical.close_hold_steps` | `30` | 夹爪闭合后保持接触、建立夹持力的步数。 |
| `physical.lift_check_delta` | `0.05` | 正式搬运前的试抬高度。 |
| `physical.min_lift_delta` | `0.025` | 方块至少随夹爪升高这么多才认定抓取成功。 |
| `physical.max_grasp_xy_error` | `0.025` | 试抬后方块相对抓取中心允许的最大 XY 偏差。 |

## Swap 低层 MDP 参数

来源：`configs/task_configs/swap.yaml` 与 `topogym/envs/swap_mdp.py`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `mdp.max_episode_steps` | `150` | 一个 episode 最多允许多少个 RL action。 |
| `mdp.lift_height` | `0.07` | 方块高于初始中心多少米后算 lifted。 |
| `mdp.reward.reach` | `1.0` | 靠近目标方块的奖励权重。 |
| `mdp.reward.place` | `2.0` | 目标方块靠近目标 slot 的奖励权重。 |
| `mdp.reward.lift` | `1.0` | 方块被抬起的奖励权重。 |
| `mdp.reward.success` | `10.0` | 成功完成任务的奖励权重。 |
| `mdp.reward.action` | `0.01` | 动作幅度惩罚权重。 |
| `mdp.reward.step` | `0.01` | 时间步惩罚权重。 |
| `SwapMdpEnv.num_actions` | `4` | 当前动作为 `[dx, dy, dz, gripper]`。 |
| `SwapMdpEnv.num_obs` | `25` | 当前观测维度。 |

当前 25 维观测由以下部分拼接：

| 观测项 | 维度 | 说明 |
|---|---:|---|
| `hand` | `3` | Franka `hand` link 的世界坐标。 |
| `gripper` | `1` | 当前夹爪开合比例。 |
| `block_positions` | `12` | 4 个方块各自的世界坐标。 |
| `target_block_pos - hand` | `3` | 红块相对末端的位置。 |
| `target_center - target_block_pos` | `3` | 目标 slot 相对红块的位置。 |
| `target_center[:2] - hand[:2]` | `2` | 目标 slot 相对末端的 XY 偏移。 |
| `is_lifted` | `1` | 红块是否已经被抬起。 |

## OneStroke 场景参数

来源：`configs/task_configs/onestroke.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `task.id` | `onestroke` | 任务 ID。 |
| `task.difficulty` | `smoke` | 当前任务难度标签。 |
| `board.pos` | `${common.manipulation_space.board.pos}` | OneStroke 使用通用棋盘中心。 |
| `board.size` | `${common.manipulation_space.board.size}` | OneStroke 使用通用棋盘尺寸。 |
| `grid.rows / grid.cols` | `3 / 3` | cell 网格行列数。 |
| `grid.top_left_cell_pos` | `[0.42, 0.075, 0.766]` | 左上角 cell 中心位置。 |
| `grid.cell_size` | `[0.058, 0.058, 0.014]` | 每个 cell 的尺寸。 |
| `grid.cell_gap` | `0.036` | 相邻 cell 之间的缝隙宽度；给 14 mm 厚 wall block 留出约 11 mm 单侧余量。 |
| `grid.colors` | 3x3 RGB 表 | 每个 cell 的颜色。 |
| `wall_block.size` | `[0.058, 0.014, 0.022]` | 可抓取 wall block 的尺寸，默认长轴沿 x。 |
| `wall_block.count` | `5` | supply tray 中的 wall block 数量。 |
| `supply.pos` | `[0.695, -0.005, 0.762]` | supply tray 中心位置。 |
| `supply.size` | `[0.085, 0.335, 0.006]` | supply tray 尺寸。 |
| `supply.block_start_pos` | `[0.695, 0.120, 0.776]` | 第一个 wall block 的初始中心位置。 |
| `supply.block_spacing` | `0.060` | supply tray 中相邻 wall block 的间距。 |
| `edge_slots.width` | `0.016` | cell 间目标承托面的短边宽度；窄于 gap，避免承托体挤进相邻色块区域。 |
| `edge_slots.height` | `0.004` | cell 间目标缝隙标记高度。 |
| `edge_slots.z` | `0.771` | 目标承托面中心高度；其顶面与 cell 顶面 `z=0.773` 齐平。 |
| `edge_slots.collision` | `true` | 是否创建 gap 内的隐形承托碰撞体；physical demo 可用 `--no-edge-support` 临时关闭。 |
| `edge_slots.visualization` | `false` | 是否显示 gap 内承托体；默认不显示，避免视觉泄露结构。 |
| `edge_slots.targets` | `5` 条 | Oracle 参考解使用的逻辑 edge 列表；不生成可见预置墙。 |
| `oracle.supply_pick_z` | `0.91` | 预留：取 wall block 时的 hand 高度。 |
| `oracle.carry_z` | `1.05` | 预留：搬运 wall block 的安全高度。 |
| `oracle.insert_z` | `0.84` | 预留：插入 cell 缝隙时的 hand 高度。 |

当前 OneStroke smoke 场景对应“从 supply tray 取一块 wall block，再插入 cell 间目标缝隙”的范本。
`edge_slots.targets` 记录 oracle 参考解中每条 wall 连接的两个相邻 cell。
Builder 不会据此显示或单独强化这些边；它会为网格的全部合法 cell 边界
创建相同的不可见碰撞承托面，以防 wall block 落入缝隙，同时避免通过
视觉或物理结构泄露答案。

OneStroke physical demo 还使用：

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `physical.motion_steps` | `90` | 每段机械臂运动的线性 IK waypoint 数。 |
| `physical.gripper_steps` | `35` | 夹爪开合物理步数。 |
| `physical.finger_friction` | `2.0` | Franka 两个 finger link 的刚体摩擦。 |
| `physical.wall_friction` | `1.0` | 墙块刚体摩擦。 |
| `physical.grasp_yaw_offset` | `pi/2` | 让夹爪跨墙块长轴两端闭合，而不是夹 14 mm 薄边。 |
| `physical.motion_settle_steps` | `20` | 每段位姿运动后保持控制，减少到位速度。 |
| `physical.place_hold_steps` | `35` | wall 接触承托面后保持夹持，再张开夹爪。 |
| `physical.place_tolerance_xy` | `0.008 m` | 墙块中心到目标 edge 的最大 XY 误差；仍小于真实 gap 单侧余量。 |
| `physical.place_tolerance_z` | `0.006 m` | 墙块中心到目标支撑高度的最大误差。 |
| `physical.place_tolerance_yaw` | `0.25 rad` | 墙块落位后的方向误差。 |
| `physical.place_tolerance_tilt` | `0.18 rad` | 墙块局部 z 轴允许的最大倾角；翻滚 wall 不再判为成功。 |
| `physical.target_xy_bias` | `[0.000, 0.000]` | 默认把物理释放目标放在两个相邻 cell center 的中点；如观察到系统性漂移，可用 CLI `--target-xy-bias X Y` 临时补偿。 |
| `physical.release_clearance` | `0.000 m` | 不再在 slot 上方悬空释放。 |
| `physical.placement_preload` | `0.001 m` | 张开前向承托面施加 1 mm 轻微预压，减少弹跳且避免过度下压。 |

## Maze Wall Removal 物理参数

来源：`configs/task_configs/maze_wall_removal.yaml`

Maze 使用与 OneStroke 相同的长轴端夹和 `lift_test`。区别是墙块从迷宫边缘垂直拔出后
放入 discard 区，不需要重新插入窄槽。

Maze 当前默认 `edge_slots.visualization=false` 且 `edge_slots.collision=false`，因此不会生成 cell
之间的浅灰凹槽，也不会留下隐藏承托体。移除后的墙块放入棋盘右侧的逻辑 discard 长条区；
该区域默认 `discard.visible=false`，所以 viewer/视频里不会显示额外托盘。

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `grid.cell_size` | `[0.070, 0.070, 0.014]` | Maze cell 尺寸；比早期版本更大，降低相邻 wall 对夹爪下探的干扰。 |
| `grid.cell_gap` | `0.040 m` | 相邻 cell 间距；配合 16 mm wall 厚度，单侧约有 12 mm 余量。 |
| `wall_block.size` | `[0.056, 0.016, 0.026]` | wall block 尺寸；长轴保持 56 mm 以复用当前长轴端夹，厚度降到 16 mm。 |
| `discard.visible` | `false` | 不显示拿走后放墙块的区域；只保留逻辑判断区域。 |
| `discard.size` | `[0.700, 0.120, 0.006]` | 棋盘右侧逻辑长条区，x 方向与通用棋盘等长。 |
| `physical.motion_steps` | `240` | 每段拔出和搬运运动的 waypoint 数；使用 ease-in/ease-out 插值。 |
| `physical.motion_settle_steps` | `30` | 每段运动结束后的跟踪稳定步数。 |
| `physical.gripper_steps` | `50` | 夹爪开合物理步数。 |
| `physical.grasp_qpos` | `0.0240 m` | 每根 finger 的闭合目标；考虑指垫偏置后，目标内侧间隙约 51 mm。 |
| `physical.finger_friction` | `2.0` | 指爪刚体摩擦。 |
| `physical.wall_friction` | `1.0` | 迷宫墙块刚体摩擦。 |
| `physical.grasp_yaw_offset` | `pi/2` | 跨墙块长轴两端抓取。 |
| `physical.noslip_iterations` | `8` | 降低拔墙和搬运过程中的滑移。 |
| `physical.min_lift_delta` | `0.020 m` | 试抬后墙块至少上升的距离。 |
| `physical.lift_hold_steps` | `50` | 试抬后保持夹持，用于发现延迟滑落。 |
| `physical.max_lift_drift` | `0.006 m` | 保持阶段允许的最大墙块漂移。 |

## Untangle 场景参数

来源：`configs/task_configs/untangle.yaml`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `task.id` | `untangle` | 任务 ID。 |
| `task.difficulty` | `smoke` | 当前任务难度标签。 |
| `board.pos` | `${common.manipulation_space.board.pos}` | Untangle 使用通用棋盘中心。 |
| `board.size` | `${common.manipulation_space.board.size}` | Untangle 使用通用棋盘尺寸。 |
| `holes.rows / holes.cols` | `4 / 4` | holes 网格行列数。 |
| `holes.top_left_pos` | `[0.42, 0.070, 0.760]` | 左上角 hole 薄圆盘中心位置。 |
| `holes.spacing` | `[0.065, 0.060]` | 相邻 holes 的 x/y 间距。 |
| `holes.source` | `[0, 1]` | 当前要移动的源 rope endpoint 所在 hole。 |
| `holes.target` | `[3, 0]` | 目标插入 hole。 |
| `peg.enabled` | `false` | 当前场景不生成高 peg，只保留 holes、anchor pins 和 ropes。 |
| `peg.pegs` | `0` 个 | 当前场景中没有 peg 实体。 |
| `rope.model` | `pbd_elastic_tube` | rope 使用 Genesis PBD.Elastic 体网格近似。 |
| `rope.anchor_endpoints` | `true` | build 后把每条 rope 两端粒子固定在孔位。 |
| `rope.anchor_radius` | `0.008` | 选择端点附近 PBD particles 作为固定粒子的半径。 |
| `rope.radius` | `0.004` | 生成 tube mesh 的圆管半径。 |
| `rope.z` | `0.766` | rope 基准中心高度，接近 board 表面和低矮 anchor pins。 |
| `rope.layer_height` | `0.006` | 每个 crossing layer 的高度差；当前主要用 `z_offset` 给交叉处很小的初始间隔。 |
| `rope.particle_size` | `0.004` | PBD solver 的粒子尺度。 |
| `rope.mesh.segment_length` | `0.009` | 生成 rope mesh 时每段最大采样长度。 |
| `rope.mesh.radial_segments` | `8` | tube mesh 每个截面的圆周采样点数。 |
| `rope.mesh.maxvolume` | `0.000000025` | TetGen 单个四面体最大体积，越小体网格越细、越慢。 |
| `rope.mesh.output_dir` | `.cache/topogym/meshes/untangle` | 自动生成 OBJ rope mesh 的缓存目录。 |
| `rope.pbd.*_iterations` | `10 / 6 / 6` | PBD stretch/bending/volume solver 迭代次数。 |
| `rope.elastic.*` | 多项 | PBD elastic 密度、摩擦、stretch/bending/volume 柔顺度参数。 |
| `rope.anchor_pins.enabled` | `true` | 默认在每条 rope 的 start/end 端点生成低矮固定桩，robot demo 抓这个实体而不是直接夹 rope。 |
| `rope.anchor_pins.placement` | `endpoints` | 在每条 rope 的 start/end 端点生成固定桩。 |
| `rope.anchor_pins.fixed / collision` | `true / false` | 固定桩作为可视化抓取实体存在；当前关闭碰撞，避免 pin 与 PBD rope 初始重叠导致 native crash。 |
| `rope.strands` | `3` 条 | 红、绿、蓝三条 rope 的折线路径。 |
| `oracle.source_hole` | `[0, 1]` | 预留：oracle 要移动的源 rope endpoint。 |
| `oracle.target_hole` | `[3, 0]` | 预留：oracle 要插入的目标洞。 |
| `oracle.above_z / pull_z` | `1.05 / 1.05` | 预留：移动和抬起 rope endpoint 的安全高度。 |
| `oracle.grasp_z / insert_z` | `0.875 / 0.875` | 预留：抓取和放置 rope endpoint 的 hand 高度。 |

当前 Untangle smoke 场景搭出 hole board、holes、三条 rope 和每条 rope 两端的低矮固定桩。
rope 现在是自动生成的闭合 tube surface mesh，交给 Genesis PBD.Elastic tetrahedralize 成 3D deformable body，并会把两端附近的 PBD particles 固定在孔位。rope point 可以写成 `[row, col]`，也可以写成 `{hole: [row, col], z_offset: 0.006}` 给交叉处一个很小的初始物理间隔；robot demo 会让机械臂抓固定桩，搬运中用 attachment 辅助固定桩跟随手爪，并让 rope endpoint 跟随固定桩。

## rsl-rl PPO Smoke 参数

来源：当前正式 demo 入口见 `cli_commands.txt`

| 参数 | 当前值 | 作用 |
|---|---:|---|
| `--iterations` | `1` | PPO 采样和更新循环次数。 |
| `--num-steps-per-env` | `8` | 每次 iteration 每个 env 采多少个 RL step。 |
| `--device` | `cpu` | rsl-rl 网络运行设备。 |
| `--log-dir` | `runs/rsl_rl_swap_smoke` | 日志和 diff 保存目录。 |
| `train_cfg.save_interval` | `100` | checkpoint 保存间隔。 |
| `train_cfg.logger` | `tensorboard` | 日志后端。 |
| `obs_groups.actor` | `["policy"]` | actor 使用的观测组。 |
| `obs_groups.critic` | `["policy"]` | critic 使用的观测组。 |
| `actor.class_name` | `MLPModel` | actor 网络类型。 |
| `actor.hidden_dims` | `[128, 128]` | actor MLP 隐藏层大小。 |
| `actor.obs_normalization` | `true` | 是否对 actor 观测做经验归一化。 |
| `actor.distribution_cfg.class_name` | `GaussianDistribution` | 连续动作分布。 |
| `actor.distribution_cfg.init_std` | `1.0` | 初始动作探索噪声标准差。 |
| `critic.class_name` | `MLPModel` | critic 网络类型。 |
| `critic.hidden_dims` | `[128, 128]` | critic MLP 隐藏层大小。 |
| `critic.obs_normalization` | `true` | 是否对 critic 观测做经验归一化。 |
| `algorithm.class_name` | `PPO` | 使用 PPO 算法。 |
| `algorithm.learning_rate` | `1e-4` | 学习率。 |
| `algorithm.num_learning_epochs` | `1` | 每批 rollout 做几轮学习。 |
| `algorithm.num_mini_batches` | `1` | 每批 rollout 切成几个 mini-batch。 |
| `algorithm.clip_param` | `0.2` | PPO ratio clipping 范围。 |
| `algorithm.gamma` | `0.98` | 回报折扣系数。 |
| `algorithm.lam` | `0.95` | GAE 优势估计参数。 |
| `algorithm.value_loss_coef` | `1.0` | value loss 权重。 |
| `algorithm.entropy_coef` | `0.01` | 熵奖励权重，鼓励探索。 |
| `algorithm.max_grad_norm` | `1.0` | 梯度裁剪阈值。 |
| `algorithm.desired_kl` | `0.01` | 期望 KL，用于学习率调度或监控。 |

## 运行脚本参数

来源：当前正式 demo 入口见 `cli_commands.txt`

| 参数 | 默认值 | 作用 |
|---|---:|---|
| `--common-config` | `configs/common_configs/manipulation_space.yaml` | 通用棋盘、候选工作区、机器人安装位和 home pose 配置。 |
| `--env-config` | `configs/env_configs/common_room.yaml` | 环境配置文件。 |
| `--robot-config` | `configs/robot_control_configs/franka_panda_position_ik.yaml` | 机器人控制配置文件。 |
| `--task-config` | `configs/task_configs/swap.yaml` | 任务配置文件。 |
| `--backend` | `None` | 临时覆盖 Genesis backend。 |
| `--viewer` | `false` | 是否打开 Genesis viewer。 |
| `--keep-open` | `false` | 脚本结束后是否继续 step，让 viewer 保持打开。 |
| `--record-video` | `None` | 是否保存 mp4 视频。 |
| `--record-fps` | `100` | 视频保存帧率；越低越慢动作。 |
| `--record-camera` | `oblique` | 使用哪个配置相机录制。 |
| `--record-every-n-steps` | `1` | 每 N 个 `scene.step()` 保存一帧。Genesis 会在结束编码前把帧保留在内存中；长流程建议设为 `4` 或更大。 |
| `swap_empty_slot_demo --move-steps` | `80` | Swap 正式 demo 每段搬运动作的插值步数。 |
| `swap_empty_slot_demo --gripper-steps` | `30` | Swap 正式 demo 张开/闭合夹爪时执行多少步。 |
| `swap_empty_slot_demo --grasp-qpos` | `半个方块宽度` | Swap 正式 demo 的可视化夹爪闭合宽度；默认不会完全闭死。 |
| `swap_empty_slot_demo --grasp-offset` | `[0.0, 0.0, -0.1029]` | 方块中心相对 hand target 的偏移，随 yaw 一起旋转；用于微调方块在夹爪里的位置。 |
| `swap_empty_slot_demo --carry-yaw` | `0.0` | Swap 正式 demo 搬运时的手爪 yaw；默认不主动侧旋转。 |
| `swap_physical_grasp_demo --motion-steps` | `80` | 每段机械臂直线运动拆成多少个 IK waypoint。 |
| `swap_physical_grasp_demo --grasp-qpos` | `0.0` | 物理夹持的每指目标位置；默认完全闭合，由方块接触阻止手指继续运动并建立夹持力。 |
| `swap_physical_grasp_demo --finger-friction` | `2.0` | 两个 finger link 的刚体摩擦系数。 |
| `swap_physical_grasp_demo --block-friction` | `0.8` | 所有 Swap 方块的刚体摩擦系数。 |
| `swap_physical_grasp_demo --noslip-iterations` | `5` | 接触 no-slip 求解迭代数。 |
| `onestroke_physical_wall_demo --max-walls` | `None` | 默认执行完整分隔墙计划；设为 `1` 可先验证单墙抓放。 |
| `onestroke_physical_wall_demo --motion-steps` | `90` | 每个墙块动作阶段的 IK waypoint 数。 |
| `onestroke_physical_wall_demo --no-edge-support` | `False` | 临时移除 OneStroke gap 内隐形承托 floor，让 wall block 靠重力落到 board 顶面。 |
| `maze_wall_removal_physical_demo --max-walls` | `None` | 默认执行完整最优拆墙计划；设为 `1` 可做单墙 smoke。 |
| `maze_wall_removal_physical_demo --seed` | `11` | 随机迷宫实例种子。 |
| `untangle_physical_handle_demo --max-moves` | `8` | 连续执行 endpoint move，直到 topology terminal 或达到上限；设为 `1` 是单动作 smoke。 |
| `untangle_physical_handle_demo --max-grasp-attempts` | 配置值 `2` | 单个 topology move 允许的物理抓取尝试次数。 |
| `untangle physical_handle.placement_tolerance_xy` | `0.030` | handle 释放并稳定后到目标 hole 的最大 XY 误差；通过后才提交高层 topology action。 |
| `cable_routing_physical_handle_demo --max-waypoints` | `None` | 默认保持一次连续物理夹持并执行完整 P1 -> P2 -> C 路径；设为 `1` 是抓取 smoke。 |
| `cable physical_handle.max_segment_follow_error` | `0.040` | 每个 waypoint 后 handle 到实际指垫中心的最大允许误差，超过即判定途中滑脱。 |
| `cable physical_handle.route_settle_steps` | `80` | 完整释放后、最终 PBD 绕柱验证前的稳定步数。 |
| `cable fixtures.C.socket.inner_size` | `[0.028, 0.028]` | physical demo 的终点 socket 内部开口；pole 直径为 20 mm。 |
| `cable fixtures.C.socket.wall_height` | `0.006` | 终点 socket 导向壁高度，保持在夹爪抓取中心下方。 |
| `cable physical_handle.connector_tolerance_xy` | `0.012` | latch 后 free-end handle 到 connector 目标的最大 XY 误差。 |
| `cable physical_handle.latch_capture_tolerance_xy` | `0.010` | 插入时允许触发 connector snap-lock 的最大 XY 误差。 |
| `cable physical_handle.latch_capture_tolerance_z` | `0.012` | 插入时允许触发 connector snap-lock 的最大高度误差。 |
| `cable physical_handle.latch_capture_max_tilt_deg` | `20.0` | 允许触发卡扣的最大 pole 倾角，避免横倒物体被吸附。 |
| `cable physical_handle.segment_steps` | 分段配置 | 覆盖 physical demo 的分段搬运速度；P2 外侧三段使用更多插值步，降低连续绕线时的横向滑脱，不影响 oracle demo。 |
| `cable physical_handle.latch_auto_capture` | `true` | 每个仿真步自动检查 pole 是否进入 C socket 的捕获体积。 |
| `untangle_rope_drag_demo --mode` | `robot` | 默认让 Franka 接近端点小桩、闭合夹爪，再用 endpoint attachment 搬运 rope 端点；`manual` 保留旧的直接拖动模式。 |
| `untangle_rope_drag_demo --lite` | `off/on` | 使用更粗的 rope 网格和更少 PBD 迭代，适合 viewer 诊断和稳定录制正式 demo。 |
| `untangle_rope_drag_demo --move-steps` | `60` | Untangle 正式录制中接近、下降、撤回等机械臂动作的插值步数；viewer 诊断可用 `50`。 |
| `untangle_rope_drag_demo --gripper-steps` | `20` | Untangle 正式录制中张开/闭合夹爪时执行多少步；viewer 诊断可用 `16`。 |
| `untangle_rope_drag_demo --grasp-qpos` | `pin 半径 + 0.001` | 夹住端点小固定桩时的可视化夹爪闭合宽度。 |
| `untangle_rope_drag_demo --endpoint-lift` | `0.05` | 拖动 rope endpoint 前先把端点和固定桩抬高约 5cm，让红绳跨过绿绳而不是贴着绿绳拖。 |
| `untangle_rope_drag_demo --drag-steps` | `280` | Untangle 正式 demo 中拖动 endpoint 的总步数；viewer 诊断可用 `240`。 |
| `untangle_rope_drag_demo --arc-height` | `0.0` | endpoint 平移过程中的额外弧线高度；默认只使用 `endpoint-lift`。 |

旧的 oracle/展示 demo 搬运阶段可能使用 `AttachmentManager` 表示“已抓住”状态。名称中带
`physical` 的刚体和 PBD-handle demo 不使用该机制：夹爪到物体之间依靠碰撞、摩擦和 PD
夹持力，PBD 绳端则通过 Genesis `fix_particles_to_link` 连接动态 rigid handle。Cable
完整路线的 connector latch 会持续监测 C 的插座捕获体积，并只在 pole 实际插入后激活；该
attachment 仅属于终点 C，不参与运输阶段，也不会在 P1/P2 附近吸附 pole。

## 常用换算

### RL 动作数到仿真时间

```text
仿真秒数 = RL step 数 * steps_per_action * sim.dt
```

当前配置下：

```text
1 个 RL step = 20 * 0.01 = 0.2 秒
150 个 RL step = 30 秒
```

### PPO smoke 视频长度

```text
视频内容时长 = iterations * num_steps_per_env * steps_per_action * sim.dt
```

如果命令是：

```bash
python -m prototypes.swap_empty_slot_demo --record-video runs/demo_swap_empty_slot.mp4 --record-fps 60
```

则视频内容约为：

```text
1 * 150 * 20 * 0.01 = 30 秒
```

### Viewer 与录制的区别

| 功能 | 是否改变仿真 | 是否改变视频长度 |
|---|---|---|
| `--viewer` | 否 | 否 |
| `--keep-open` | 训练后继续空跑 | 不录训练后的空跑，除非录制上下文也包住它 |
| `--record-video` | 否 | 保存被录制的 `scene.step()` |
| `--record-fps` | 否 | 改变播放速度，不改变仿真数据 |

## 调参建议

| 目标 | 优先调的参数 |
|---|---|
| 视频太短 | 增大 `--num-steps-per-env` 或 `--iterations`。 |
| 视频太快 | 降低 `--record-fps`。 |
| 机械臂动作太大 | 降低 `action_protocol.max_delta_xyz`。 |
| 每个 action 执行得太久 | 降低 `control_loop.steps_per_action`。 |
| 接触不稳定 | 优先看 `sim.substeps`、夹爪 force/kp/kv、方块尺寸和摩擦。 |
| 随机探索太剧烈 | 降低 `actor.distribution_cfg.init_std` 或 `algorithm.entropy_coef`。 |
| episode 太短 | 增大 `mdp.max_episode_steps`。 |
| 想训练更久 | 增大 `--iterations` 和 `--num-steps-per-env`。 |
