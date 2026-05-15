# C — Embodiment & Action Interface：类清单

> 对应 `modules/C_embodiment.md`。C 是适配层：把上游 policy 的输出统一规约到物理可执行的关节命令。

---

## 1. `Embodiment`

**功能**：把机器人加进 scene；配 controller；缓存 home pose；暴露 ActionSpace。

**输入（构造期）**
- `AssetRef`（URDF/MJCF）
- `ControllerConfig`
- `HomePose`
- `action_mode: Literal["joint", "ee_pose", "primitive"]`

**输出**：把 robot 加进 scene；对外暴露 `ActionSpace`。

**方法**
- `__init__(asset_ref, controller_config, home_pose, action_mode) -> None`
- `add_to_scene(scene_builder: SceneBuilder) -> None`：构造期被 A 调
- `action_space() -> ActionSpace`
- `apply_action(action: Tensor[B, dim]) -> Tensor[B] action_ok`
- `reset_to_home(env_ids: list[int] | None = None) -> None`
- `_robot_handle() -> EntityHandle`：通过 manifest 取 `"robot"`

---

## 2. `ActionSpace`（数据类，跨模块契约）

**字段**：`kind: Literal["joint","ee_pose","primitive"]`, `dtype`, `shape`, `low`, `high`, `dict_spec`（primitive 模式下用）

**方法**
- `sample(batch: int) -> Tensor`
- `validate(action) -> Tensor[B] bool`
- `denormalize(action) -> Tensor`
- `as_gym_space() -> gym.Space`：F 透传给 Gymnasium adapter

---

## 3. `ActionDecoder`（抽象）

**功能**：把 policy 输出译成 Genesis 调用。

**子类**：`JointActionDecoder` / `EEPoseActionDecoder` / `PrimitiveActionDecoder`。

**输入**：`action[B, dim]`, `robot: EntityHandle`, `scene: SceneHandle`。

**输出**：`action_ok[B]`；副作用是发命令到 Genesis。

**方法**
- `decode_and_apply(action, robot, scene) -> Tensor[B] bool`
- `action_space() -> ActionSpace`

---

## 4. `JointActionDecoder`

**输入**：`action[B, n_dof]`（归一化关节角/力矩增量）。

**方法**
- `decode_and_apply`：反归一化 → `robot.control_dofs_position(pos, dofs_idx_local, envs_idx)`（位置控制）或 `robot.control_dofs_force(force, dofs_idx_local, envs_idx)`（力/力矩控制）
- `_clip_to_limits(q) -> tuple[q_clipped, ok_mask]`

> ⚠️ Genesis 无 `set_dofs_position_target` / `control_dofs_torque`。真实 API：`control_dofs_position` / `control_dofs_velocity` / `control_dofs_force`；硬置位 `set_dofs_position`；增益 `set_dofs_kp` / `set_dofs_kv` / `set_dofs_force_range`。

---

## 5. `EEPoseActionDecoder`

**依赖**：`IKSolver`。

**输入**：`action[B, 7]`（6D 增量 + 夹爪开合）。

**方法**
- `decode_and_apply`：FK 当前 EE → 合成目标 → IK → `control_dofs_position` + 夹爪。整段轨迹也可改用 Genesis 自带 `robot.plan_path(qpos_goal=, num_waypoints=)`（OMPL）生成 waypoint 序列
- `_current_ee_pose(robot) -> Pose[B]`：`robot.get_link(name)` 后取 `get_pos / get_quat`
- `_compose_target(current_pose, delta) -> Pose[B]`
- `_apply_gripper(robot, open_close[B]) -> None`

---

## 6. `PrimitiveActionDecoder`

**依赖**：`PrimitiveLibrary`。

**输入**：`action = {primitive_id[B], params[B, ...]}`。

**方法**
- `decode_and_apply`：分发到 `Primitive.run`，内部启动子循环（多个物理 step）
- `_dispatch(primitive_id) -> Primitive`
- `_run_subloop(primitive, params, robot, scene, env_ids) -> done[B]`

**纪律**：子循环的"内 loop 步数"必须对 F 透明；F.step 内 Genesis 物理步数可以是 1 或 N，对外只算"一次决策"。

---

## 7. `IKSolver`

**功能**：IK 后端的统一包装。

> ⚠️ Genesis 的 IK **不是独立 solver**，而是实体方法 `robot.inverse_kinematics(link=, pos=, quat=)`（`pos` 支持 batch `[B, 3]`，用当前 qpos 作种子，无显式 `q_seed`，无工作空间边界 setter）。"genesis" 后端即薄包此方法；cuRobo / PyRoboKin 为可选外部后端。

**方法**
- `__init__(backend: Literal["genesis","curobo","pyrobokin"], robot: EntityHandle) -> None`：genesis 后端持有 robot 实体句柄，不是 URDF 路径
- `solve(target_pose: Pose[B], ee_link) -> tuple[Tensor[B, n_dof], Tensor[B] bool]`：genesis 后端 → `robot.inverse_kinematics(link=ee_link, pos=..., quat=...)`
- 运动规划：Genesis 另有 `robot.plan_path(qpos_goal=, num_waypoints=)`（OMPL），供 `Primitive` 子循环复用

---

## 8. `Primitive`（抽象）

**子类**：`PickPlace` / `Push` / 任务相关 primitive。

**输入**：`params: dict`, `robot`, `scene`, `env_ids`。

**输出**：`done[B]`（子循环结束标志）。

**方法**
- `params_space() -> gym.Space`
- `run(scene, robot, params, env_ids) -> Tensor[B] bool`：子循环主体
- `name -> str`

---

## 9. `PrimitiveLibrary`

**功能**：primitive 的注册表 + 统一 ActionSpace 拼装。

**方法**
- `register(name: str, primitive: Primitive) -> None`
- `get(primitive_id: int) -> Primitive`
- `space() -> ActionSpace`：拼成 `Dict({"primitive_id": Discrete(K), "params": Box(...)})`

---

## 10. `ControllerConfig`（数据类）

**字段**：`kp`, `kv`, `force_range`（力/力矩上下限）。

> 映射到 Genesis：`kp → set_dofs_kp`，`kv → set_dofs_kv`，`force_range → set_dofs_force_range`。`substeps` 是 sim 级配置（`gs.options.SimOptions`），不属于 controller，已从字段移除。
