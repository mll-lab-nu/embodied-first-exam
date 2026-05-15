# F — Runtime：类清单

> 对应 `modules/F_runtime.md`。F 编排 D→E→C→physics→B→auto-reset，并暴露两套外部 adapter。

---

## 1. `Runtime`

**功能**：核心 orchestrator；持有 env（A+B+C+D 组装好的句柄）与 policy（E），实现 step/reset 主循环。

**输入（构造期）**
- `scene: SceneHandle`
- `manifest: EntityManifest`
- `task: TaskBase`
- `embodiment: Embodiment`
- `observer: Observer`
- `policy: Policy`
- `RunConfig`（`n_envs / max_episode_steps / auto_reset / deterministic`）

**输出（构造期）**：自身实例，可 attach adapter。
**输出（每步）**：`TimeStep`。

**方法**
- `__init__(scene, manifest, task, embodiment, observer, policy, run_config) -> None`
- `step(action: Tensor | None = None) -> TimeStep`：action=None 时内部调 policy.act
- `reset(env_ids: list[int] | None = None) -> dict obs`
- `as_gym_vec_env() -> GymVecAdapter`
- `as_rsl_rl_env() -> RslRlAdapter`
- `register_callback(callback: Callback) -> None`
- 属性：`n_envs / num_obs / num_actions / action_space / observation_space`

---

## 2. `GymVecAdapter`

**功能**：Gymnasium `VectorEnv` 接口面。

**方法**
- `step(action) -> tuple[obs, reward, terminated, truncated, info]`
- `reset() -> tuple[obs, info]`
- `action_space / observation_space / num_envs`：属性
- 内部 delegate 到 `Runtime`

---

## 3. `RslRlAdapter`

**功能**：rsl-rl `GenesisEnv` 接口面。

**方法**
- `step(action) -> tuple[obs, reward, done, info]`
- `reset() -> obs`
- `get_observations() -> obs`
- 属性：`num_envs / num_obs / num_actions`
- 内部 delegate 到 `Runtime`

> ⚠️ rsl-rl 接口跨版本漂移（见 G1 `SmokeTest` / Issue #757）：新版 `get_observations()` 返回 `(obs, extras)`、`step` 返回 `(obs, rewards, dones, extras)`。落地前先把目标 rsl-rl 版本钉死，再定本 adapter 的精确签名。

---

## 4. `AutoResetManager`

**功能**：处理 done env 的就地重置 + emit `EpisodeSummary`。

**输入**：`done_mask[B]`, 当前 info, env handles。

**输出**：被替换为初帧的 obs 切片 + 一批 `EpisodeSummary`。

**方法**
- `__init__(task, applier, embodiment, observer, episode_stats) -> None`
- `handle_done(done_mask, current_info) -> tuple[obs_slice_dict, list[EpisodeSummary]]`
- `_reset_envs(env_ids) -> dict obs_slice`：调用 B→A→C→D 重置流程（A 侧最终落到 `set_dofs_position/set_pos(..., envs_idx=env_ids)`，或 `scene.reset(state, envs_idx=env_ids)`）
- `_emit_summaries(env_ids) -> list[EpisodeSummary]`

---

## 5. `EpisodeStats`

**功能**：per-env counter；步数 / 累计 return / 上次 reset 时间。

**方法**
- `__init__(n_envs) -> None`
- `accumulate(reward: Tensor[B]) -> None`
- `tick_step() -> None`
- `on_reset(env_ids) -> None`
- `summary(env_id: int) -> EpisodeSummary`
- 属性：`step_count[B] / return_acc[B]`

---

## 6. `TimeStep`（数据类，跨模块契约）

**字段**：`obs: dict`, `action: Tensor`, `reward: Tensor[B]`, `terminated: Tensor[B] bool`, `truncated: Tensor[B] bool`, `info: dict`。

**方法**
- `done() -> Tensor[B]`：`terminated | truncated`
- `slice(env_ids) -> TimeStep`：取子集（G2/G3 用）

---

## 7. `EpisodeSummary`（数据类，跨模块契约）

**字段**：`env_id`, `return_total`, `length`, `success`, `termination_reason`, `final_topology_state`。

**方法**
- `as_dict() -> dict`

---

## 8. `CheckpointHook`

**功能**：保存/加载 RNG state + per-env step counter（G1 长跑续训）。

**方法**
- `save(path) -> None`：dump RNG + EpisodeStats
- `load(path) -> None`
- `_capture_rng() -> dict`
- `_restore_rng(state) -> None`

---

## 9. `Callback`（抽象，跨模块契约）

**功能**：G1/G2/G3 通用的钩子协议；F 在主循环里 fire。

**方法**
- `on_step(timestep: TimeStep) -> None`
- `on_episode_end(env_id: int, summary: EpisodeSummary) -> None`
- `on_iter_end(iter_idx: int) -> None`（G1 用）
- `on_train_end() -> None`
- `on_eval_end() -> None`

---

## 10. `RunConfig`（数据类）

**字段**：`n_envs`, `max_episode_steps`, `auto_reset: bool`, `deterministic: bool`, `step_action_source: Literal["external","internal_policy"]`。
