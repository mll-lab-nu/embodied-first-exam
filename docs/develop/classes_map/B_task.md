# B — Task：类清单

> 对应 `modules/B_task.md`。B 是纯逻辑层，不碰 Genesis API，只读 Scene 状态、产出 reward/done/info、产出初始配置。

---

## 0. 为什么 B 适合作为第一个实施模块

`B_task` 不是全框架最“底层”的模块，但它是**最适合第一个定型**的模块：

- **外部依赖最轻**：不直接 `import` Genesis、相机、IK、HF、rsl-rl。
- **耦合方向干净**：只消费 A 的只读场景契约，不反向依赖 C/D/E/F 的内部细节。
- **能反向约束其它模块**：A 的 reset setter schema、D 的 `topology_state` 字段、F 的 `info` 结构，都由 B 先定义更合理。
- **可先单测**：哪怕 A 还没落代码，B 也能先基于 mock scene state 跑 reward / success / sampler 测试。

因此，B 适合作为 `classes_map/` 里第一个进入“按图实现”的模块。

---

## 0.1 类依赖图（MVP 视角）

```text
TaskBase
├── TaskMeta
├── TopologyMetric
├── RewardComposer
│   └── RewardTerm[*]
├── SuccessCriterion
├── InitialConfigSampler
└── TopologyStateCache

SwapTask (首个 concrete task)
├── uses SwapMetric
├── uses SwapSampler
├── uses SparseSuccess / TopologyShaping / TimePenalty
└── uses SwapSuccessCriterion
```

实现顺序也应遵循这张图：先把叶子协议和数据类钉死，再写 `TaskBase` 聚合层，最后落第一个具体 task。

---

## 1. `TaskBase`

**功能**：一个具体任务的总装；构造期注册 reward/metric/sampler，每步产 reward/done/info，reset 时产初始配置。

**输入**
- 构造期：`TaskSpec`（含权重表、难度档、最大步数）
- 每步：`SceneHandle`, `EntityManifest`, `step_index`
- reset：`episode_seed`

**输出**
- 构造期：`TaskMeta`
- 每步：`reward[B]`, `terminated[B]`, `truncated[B]`, `info`（含 `topology_state`, `success`, `reward_terms`）
- reset：`list[dict]` 初始配置（N 份）

**方法**
- `__init__(task_spec: TaskSpec) -> None`
- `meta() -> TaskMeta`：注册元信息
- `step(scene, manifest, step_index) -> tuple[reward, terminated, truncated, info]`
- `sample_initial_configs(n: int, seed: int) -> list[dict]`
- `topology_state_now() -> TopologyState`：本帧缓存值，给 D 复用
- `_compute_topology(scene, manifest) -> TopologyState`：内部
- `_compose_info(state, reward_breakdown, success) -> dict`

**子类**：`KnotsTask / PipeTask / SwapTask / ChatNoirTask`（每个绑定一套 metric+reward+success+sampler）。

**实现纪律**
- `TaskBase` 负责**编排顺序**，不负责 task-specific 数学细节。
- `step(...)` 内部顺序固定为：`compute topology → cache → compute reward → judge success/termination → assemble info`。
- `topology_state_now()` 只读缓存，不触发重算。

---

## 2. `TopologyMetric`（抽象）

**功能**：Scene 状态 → 任务侧拓扑表达。

**子类**：`KnotsMetric`（绳交叉数）/ `PipeMetric`（tile 邻接图连通分量）/ `SwapMetric`（置换 Cayley 距离）/ `ChatNoirMetric`（猫到边界最短路）。

**输入（每步）**：`SceneHandle`, `EntityManifest`。

**输出**：`TopologyState[B]`（task-specific schema）。

**方法**
- `compute(scene, manifest) -> TopologyState[B]`
- `distance_to_goal(state) -> float[B]`：拓扑距离，供 `TopologyShaping` 用
- `schema() -> dict`：声明 state 字段结构（给 D / G3 用）

---

## 3. `RewardTerm`（抽象）

**子类**：`SparseSuccess` / `TopologyShaping` / `CollisionPenalty` / `TimePenalty` / `Subgoal`

**输入（每步）**：`TopologyState`, `SceneHandle`, `EntityManifest`, `step_index`。

**输出**：单项 `reward[B]`。

**方法**
- `value(state, scene, manifest, step_index) -> float[B]`
- 属性 `name: str`：拼入 `info["reward_terms"]`

---

## 4. `RewardComposer`

**功能**：按权重表把若干 `RewardTerm` 加起来。

**输入（每步）**：和 RewardTerm 一致。

**输出**：`reward_total[B]` + breakdown dict。

**方法**
- `__init__(terms_with_weights: dict[RewardTerm, float]) -> None`
- `compute(state, scene, manifest, step_index) -> tuple[float[B], dict[str, float[B]]]`
- `add_term(term, weight) -> None`
- `weights() -> dict[str, float]`

---

## 5. `SuccessCriterion`

**功能**：`topology_state → bool[B]`，每 task 一份。

**方法**
- `is_success(state) -> bool[B]`
- `is_unrecoverable(state) -> bool[B]`：纳入 `terminated`（区别于 `truncated`）

---

## 6. `InitialConfigSampler`（抽象）

**子类**：`KnotsSampler / PipeSampler / SwapSampler / ChatNoirSampler`。

**输入**：难度档参数 + `episode_seed`。

**输出**：`list[dict]`，N 份（每 env 一份），交给 A 的 `InitialConfigApplier`。

**方法**
- `sample(n: int, seed: int, difficulty: str) -> list[dict]`
- `difficulty_levels() -> list[str]`
- `_validate(config) -> bool`：保证可解（不允许采到不可解的初值）

---

## 7. `TopologyStateCache`

**功能**：一帧缓存；写一次读多次（D / `info` / G3）。归属 B，跨模块只读暴露。

**方法**
- `set(state: TopologyState) -> None`：B 每步开头写
- `get() -> TopologyState`：D / info 读
- `invalidate() -> None`：F 在 step 开始时清，防止跨帧污染
- `is_fresh() -> bool`

---

## 8. `TaskMeta`（数据类）

**字段**：`task_id`, `difficulty`, `max_episode_steps`, `reward_term_names`, `topology_schema`, `success_definition`。

**方法**
- `as_dict() -> dict`：给 G3 报告用

---

## 9. 首个 concrete task：`SwapTask`

如果现在开始真正实现，B 内第一条 concrete 路径建议只做 `SwapTask`，即纯刚体的置换类任务。

### 9.1 先做它的原因

- 不涉及 DLO / knot crossing，避免一上来就把几何拓扑难题和任务框架混在一起。
- `TopologyMetric` 可以先退化为**置换距离**或**目标错位数**，足够验证 B 的抽象。
- `InitialConfigSampler` 只需保证采样到**可解置换**，实现最简单。

### 9.2 最小类集

- `SwapMetric(TopologyMetric)`
- `SwapSampler(InitialConfigSampler)`
- `SwapSuccessCriterion(SuccessCriterion)`
- `SparseSuccess(RewardTerm)`
- `TopologyShaping(RewardTerm)`
- `TimePenalty(RewardTerm)`
- `SwapTask(TaskBase)`

### 9.3 最小 `topology_state` schema

```text
{
  "perm": IntTensor[B, N],
  "distance_to_goal": FloatTensor[B],
  "misplaced_count": IntTensor[B]
}
```

这个 schema 足以同时服务：

- B 自己做 reward / success
- D 选择是否把 `topology_state` 塞进 obs
- G3 做 success rate / difficulty 分桶统计

---

## 10. MVP 实施顺序

建议按下面顺序开工，而不是平铺所有类：

1. `TaskMeta`、`TopologyStateCache`
2. `TopologyMetric`、`RewardTerm`、`SuccessCriterion`、`InitialConfigSampler`
3. `RewardComposer`
4. `TaskBase`
5. `SwapMetric`、`SwapSampler`、`SwapSuccessCriterion`
6. `SparseSuccess`、`TopologyShaping`、`TimePenalty`
7. `SwapTask`

这样做的好处：

- 前 1-4 步就能把抽象边界固定住。
- 第 5-7 步只是在验证抽象，不会反过来污染基类。
- 后续 `KnotsTask / PipeTask / ChatNoirTask` 都可以视为往同一套插槽里换实现。
