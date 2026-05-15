# 跨模块契约类（_shared_contracts）

> 这些类**不归任何一个模块独占**——它们是模块间的接口契约。建议放到一个独立的 `topogym.core` / `topogym.contracts` 子包里，避免反向依赖循环。
>
> 每个条目标注：**所在模块（定义在哪）** / **消费者（谁依赖它）** / **入口方法**。

---

## 0. Genesis 坐标 / 单位 / 数据约定

> 凡产出或消费位姿、张量的模块（B 采样初值、C 动作解码、D 读物体状态）必须遵守 Genesis 约定，否则跨模块对接会**静默错位**。来源：Genesis 官方 conventions 文档。

- **坐标系**：右手系、**z-up**；+Z 向上，重力沿 −Z（默认 9.81 m/s²）。
- **四元数**：`(w, x, y, z)` 标量优先（Hamilton 约定）。凡 `ee_pose` / `Pose[B]` 的 7 维布局固定为 `pos(3) + quat(4, wxyz)`。
- **morph 朝向**：`gs.morphs.*` 的 `euler` 为 x-y-z 度、`quat` 为 wxyz。
- **资产导入**：glTF 固定按 y-up 解释并自动转 z-up（不支持 z-up 的 glTF）；STL/OBJ 用 `file_meshes_are_zup`（默认 True）显式声明。
- **batch 维**：`scene.build(n_envs=0)` 时 Genesis 张量**不带 batch 维**；本 class map 处处假设 `[B, ...]`，因此即使单环境也必须 `build(n_envs>=1)`。
- **`gs.init`**：进程全局、仅能调用一次；放进一次性 bootstrap，不要塞进 per-scene 的 `SceneBuilder.build()`。

---

## 1. `EntityManifest`

- **所在**：A
- **消费者**：B（读物体世界坐标）/ C（取 robot 句柄）/ D（取相机/物体句柄）
- **入口方法**：`get(name) / robot() / cameras() / by_prefix(...)`
- **契约纪律**：build 后冻结；不允许动态加减实体。下游只能读不能写。

详见：`A_world.md#2-entitymanifest`

---

## 2. `TopologyStateCache`

- **所在**：B
- **消费者**：D（拼 obs 字段 `topo_state`）/ F（透传进 `info["topology_state"]`）/ G3（按拓扑距离打分）
- **入口方法**：`set(state) / get() / invalidate() / is_fresh()`
- **契约纪律**：B 在每步开头算完写入；F 在 step 开始时 `invalidate`；D / `info` 只读不改。

详见：`B_task.md#7-topologystatecache`

---

## 3. `ActionSpace`

- **所在**：C（由 `Embodiment.action_space()` 暴露）
- **消费者**：E（构造期需要知道输出形状）/ F（透传给 Gym/rsl-rl adapter）/ G2 G3（dataset schema / metric 推断）
- **入口方法**：`sample(batch) / validate(action) / denormalize(action) / as_gym_space()`
- **契约纪律**：`kind ∈ {"joint", "ee_pose", "primitive"}`；primitive 模式下用 `dict_spec`。

详见：`C_embodiment.md#2-actionspace`

---

## 4. `ObservationSpec` / `ObservationShape`

- **所在**：D
- **消费者**：E（构造期自配输入头）/ F（透传给外部 adapter）/ A（构造期回传 `CameraSpec` 给 SceneBuilder）
- **入口方法**：`shape() / camera_specs() / keys() / shape_of(name)`
- **契约纪律**：`ObservationShape` 必须和 E 的输入期望对齐；A 在 build 前必须先拿到 `camera_specs()`。

详见：`D_observation.md#1-observationspec`, `D_observation.md#2-observationshape`

---

## 5. `Policy`（抽象基类）

- **所在**：E
- **消费者**：F（每步调 `act`）/ G1（反向修改 TorchPolicy 子类）/ G2 G3（持有 frozen policy）
- **入口方法**：`act(obs, info) / reset / save / load / train_mode / eval_mode`
- **契约纪律**：所有子类对外接口完全一致；内部状态（RNN hidden / action chunk / 对话历史）只通过 `reset` 清。

详见：`E_policy.md#1-policy抽象跨模块契约`

---

## 6. `TimeStep` / `EpisodeSummary`

- **所在**：F
- **消费者**：G1（rsl-rl 接口面透传）/ G2（落盘字段抽取来源）/ G3（metric 聚合输入）
- **入口方法**：`TimeStep.done() / slice(env_ids)`；`EpisodeSummary.as_dict()`
- **契约纪律**：`info` 必带 `success / topology_state / reward_terms / task_id / difficulty`。

详见：`F_runtime.md#6-timestep数据类跨模块契约`, `F_runtime.md#7-episodesummary数据类跨模块契约`

---

## 7. `Callback`

- **所在**：F（接口定义在 F）
- **消费者**：G1（`MidTrainEvalCallback`）/ G2（`DataCollectorCallback`）/ G3（`EvaluatorCallback`）
- **入口方法**：`on_step / on_episode_end / on_iter_end / on_train_end / on_eval_end`
- **契约纪律**：钩子调用顺序由 `Runtime` / `BatchedRolloutDriver` 保证；callback 自身不修改 timestep。

详见：`F_runtime.md#9-callback抽象跨模块契约`

---

## 8. `BatchedRolloutDriver`（跨 G2/G3 复用）

- **所在**：建议放在 `topogym.core.driver`（不放在 G2 或 G3）
- **消费者**：G2（`DataCollector.run`）/ G3（`Evaluator.run`）；将来扩展（如纯可视化 rollout）也可复用
- **入口方法**：
  - `__init__(runtime: Runtime, target_episodes: int, callbacks: list[Callback]) -> None`
  - `run() -> dict stats`：主循环：`obs = reset → while completed < target: while any active: action = policy.act; step = runtime.step; for active env: callback.on_step; if done: callback.on_episode_end`
  - `register_callback(cb: Callback) -> None`
  - `stop() -> None`：手动中断
- **内部组件**：
  - `_ActiveMask`：per-env active 状态
  - `_EpisodeCounter`：达到 target 后停
  - `_PerEnvBuffer`（可选）：通用 per-env 临时缓冲（G2 用 `EpisodeBuffer`，G3 用 GIF 帧）
- **契约纪律**：driver 不知道下游是 G2 还是 G3，所有差异通过 callback 注入。

---

## 9. 共享 Config 协议（可选）

建议在 `topogym.core.config` 提供：

- `BaseConfig`：所有 `*Config` 数据类的基类，提供 `validate / to_dict / from_yaml`
- `RegistryFactory`：按 task / policy / backend 名注册类型 → 实例化（统一 Hydra/OmegaConf 入口）

避免 G1/G2/G3 各自实现一套 Hydra 入口产生分歧。
