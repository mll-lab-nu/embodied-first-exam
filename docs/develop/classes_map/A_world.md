# A — World：类清单

> 对应 `modules/A_world.md`。A 在 build 期间一次性把场景搭出来，在每次 reset 时把物理状态落到 B 指定的初始配置。

---

## 1. `SceneBuilder`

**功能**：构造期一次性把场景搭出来，按 task 模板依次 `add_entity` 并 `scene.build(n_envs)`。

**输入（构造期）**
- `TaskSpec`（任务 ID + 难度档 + 全局 seed）
- `AssetRefs`（URDF/MJCF/mesh/纹理路径表）
- `SimConfig`（`n_envs / dt / substeps / backend`）—— 映射到 Genesis：`dt`、`substeps` 进 `gs.options.SimOptions`；`backend` 进 `gs.init(backend=...)`；Genesis 无单一 "solver" 概念，各材料用各自 options（`RigidOptions` 等）
- 来自 D 的 `CameraSpec` 列表（通过 `register_camera` 在 build 前注入）
- 来自 C 的 `Embodiment.add_to_scene` 回调

**输出**
- `SceneHandle`
- `EntityManifest`

**方法**
- `__init__(task_spec, asset_refs, sim_config) -> None`
- `register_camera(camera_spec) -> None`：build 前由 D 提交
- `register_embodiment(embodiment) -> None`：build 前由 C 提交
- `add_entity(morph, *, material=None, surface=None, name: str) -> EntityHandle`：内部 helper。对齐 Genesis 签名 `scene.add_entity(morph, material=None, surface=None, ..., name=None)`——首参是 `gs.morphs.*`，`name` 走 Genesis 原生 kwarg
- `build() -> tuple[SceneHandle, EntityManifest]`：执行 `gs.Scene(sim_options=...)` → 逐个 `add_entity` → `scene.build(n_envs=..., env_spacing=...)`，最后冻结 manifest（`gs.init` 不在此处，见纪律）
- `select_template(task_id) -> Callable`：把 task ID 映射到具体的 scene 模板函数

**纪律**
- build 后实体集合冻结；不允许 dynamic add/remove。
- `gs.init()` 是进程全局、只能调用一次——放进一次性 bootstrap，不要放进 `build()`；否则同进程内构建第二个 scene 会报错（`EvalMatrix.reconfigure_env` 换 task、G1 训练 + G3 中段评测同进程）。
- 即使单环境也用 `scene.build(n_envs>=1)`：`n_envs=0` 时 Genesis 张量不带 batch 维，与本 class map 处处假设的 `[B, ...]` 冲突。

---

## 2. `EntityManifest`

**功能**：字符串 ID → Genesis Entity 句柄；B/C/D 通过名字检索。

**输入（构造期）**：由 `SceneBuilder.add_entity` 写入。

**输出**：句柄查询结果。

**方法**
- `register(name: str, entity: EntityHandle) -> None`
- `get(name: str) -> EntityHandle`：缺失抛 KeyError
- `get_optional(name: str) -> EntityHandle | None`
- `robot() -> EntityHandle`：语义糖（约定 `"robot"` 必存在）
- `cameras() -> dict[str, CameraHandle]`
- `by_prefix(prefix: str) -> dict[str, EntityHandle]`：例 `"rope_"`
- `freeze() -> None`：build 后调用，禁止再注册
- `__contains__(name) / __iter__()`

---

## 3. `SceneHandle`

**功能**：`gs.Scene` 的薄包装，对外暴露元信息 + 受控的物理推进入口。

**输入（构造期）**：`gs.Scene`、`n_envs`、`device`、`dt`。

**输出**：作为句柄被 B/C/D/F 持有。

**方法**
- `step() -> None`：物理推进，对应 Genesis `scene.step()`。一次 step 内部已跑完 `SimOptions.substeps` 个子步——**没有 `n_substeps` 参数**；F 若要走多个物理子步，就多次调本方法
- `reset(state=None, env_ids=None) -> None`：包 Genesis `scene.reset(state, envs_idx)`
- `get_state() -> SimState`：包 Genesis `scene.get_state()`
- 属性：`n_envs / device / dt / gravity`
- `inner() -> gs.Scene`：受限暴露，仅供 A 内部子类使用

> 删除说明：Genesis 无 `zero_step`，也不支持 build 后 `to(device)`（device 在 `gs.init` 时固定）。

---

## 4. `InitialConfigApplier`

**功能**：reset 时把 N 份 initial config dict 翻译成对场景的 setter 调用。

**输入（每次 reset）**
- `initial_configs: list[dict]`（B 产出，N 份）
- `SceneHandle` + `EntityManifest`

**输出**：物理状态已落盘。

**方法**
- `__init__(scene: SceneHandle, manifest: EntityManifest) -> None`
- `apply(initial_configs: list[dict], env_ids: list[int] | None = None) -> None`：主入口；env_ids=None 时落全部
- `_apply_robot(env_ids, qpos) -> None`：`robot.set_dofs_position(qpos, dofs_idx_local, envs_idx=env_ids)`，必要时配 `zero_velocity`
- `_apply_rigid(env_ids, name, pose) -> None`：`entity.set_pos(...) / set_quat(...)`，按 `envs_idx` 切片
- `_apply_dlo(env_ids, name, vertices) -> None`：DLO 顶点位置。⚠️ **待核实**：PBD 实体 Genesis 仅文档化了 `get_particles_pos / fix_particles / find_closest_particle`；运行期写回任意 `[B, V, 3]` 顶点不是文档化能力，落地前须在目标 Genesis 版本上验证
- `_post_apply_sync() -> None`：setter 落值后做 state 同步。Genesis 无 `zero_step`——如需让 PD 控制器/可视化对齐，调一次 `scene.step()`，否则可为 no-op

**纪律**
- A 自己不掷骰子；所有"怎么摆"的随机性来自 B 提供的 config。
- Genesis 原生提供 `scene.get_state()` / `scene.reset(state, envs_idx)` / `save_checkpoint`。若某 task 的初值可退化为「若干已捕获 `SimState`」，优先直接走 `scene.reset(state, envs_idx)`，不必 setter 逐项落值；只有需要每集全新采样位姿时才用上面的 `_apply_*` setter 路径。

---

## 5. `SceneTemplateRegistry`（可选 / 如果只 4 个 task 可并入 SceneBuilder）

**功能**：按 task ID 注册不同的"地面 + 桌 + props + 相机"模板函数。

**方法**
- `register(task_id, template_fn) -> None`
- `get(task_id) -> Callable[[SceneBuilder], None]`
