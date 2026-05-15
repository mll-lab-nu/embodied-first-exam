# E — Policy：类清单

> 对应 `modules/E_policy.md`。E 是统一插槽：所有 policy 类型实现同一接口。

---

## 1. `Policy`（抽象，跨模块契约）

**功能**：所有 policy 子类的统一接口；F/G1/G2/G3 都依赖此接口。

**输入（构造期）**：`ObservationShape`, `ActionSpace`。

**输入（每步）**：`obs: dict`, 可选 `info`。

**输出（每步）**：`action[B]`, 可选 `log_prob[B] / value[B] / entropy[B]` / debug aux。

**方法**
- `act(obs, info=None) -> tuple[action, aux: dict]`
- `reset(env_ids: list[int] | None = None) -> None`
- `save(path) -> None`
- `load(path) -> None`
- `train_mode() / eval_mode() -> None`
- 属性 `is_trainable: bool`, `mode: Literal["train","eval"]`
- 属性 `action_space / observation_shape`

---

## 2. `RandomPolicy`

**功能**：baseline / smoke test。

**方法**
- `act`：`action = action_space.sample(batch)`；aux 为空

---

## 3. `ScriptedPolicy`

**功能**：人写规则；每个 task 一份 `rule_fn`。

**输入**：rule_fn 注册表 + 当前 task ID。

**方法**
- `register_rule(task_id: str, rule_fn: Callable[[obs, info], action]) -> None`
- `act`：dispatch by `info["task_id"]`，调对应 rule_fn
- `set_task(task_id) -> None`

---

## 4. `OraclePolicy`

**功能**：基于完整符号 state 用搜索/规划算法找最优下一步。主要供 G2 教师用。

**输入**：planner（BFS / A* / SAT solver）配置。

**方法**
- `set_planner(planner: Planner) -> None`
- `act`：从 `info["topology_state"]` 取符号 state → planner.solve → 翻译成 action
- `_translate_plan_to_action(plan_step) -> action`

---

## 5. `TorchPolicy`

**功能**：被 RL/IL 训出来的网络；G1 反向更新它。

**输入（构造期）**：`nn.Module` 或网络定义 + 权重路径。

**输出（每步）**：`action`、`log_prob`、`value`、`entropy`。

**方法**
- `__init__(obs_shape, action_space, network_def | network_module, weights_path=None) -> None`
- `act(obs) -> tuple[action, dict(log_prob, value, entropy)]`
- `forward(obs) -> distribution`：内部网络前向，返回分布对象
- `train_mode() / eval_mode() -> None`
- `state_dict() / load_state_dict(state) -> None`
- `parameters() -> Iterable[Parameter]`：给 optimizer 用

---

## 6. `ImageEncoder` / `ProprioEncoder` / `FusionHead` / `ActionHead`

**功能**：`TorchPolicy` 的子组件，都是 `nn.Module`。

- **`ImageEncoder`**：CNN / ViT → embedding
  - `forward(rgb) -> feat`
- **`ProprioEncoder`**：MLP
  - `forward(proprio_dict) -> feat`
- **`FusionHead`**：拼接 / cross-attn → 共享 feat
  - `forward(image_feat, proprio_feat) -> feat`
- **`ActionHead`**（抽象）+ 子类 `GaussianHead` / `CategoricalHead` / `DiffusionHead`
  - `forward(feat) -> distribution`
  - `sample(distribution) -> action`
  - `log_prob(distribution, action) -> Tensor[B]`

---

## 7. `OpenVLAPolicy`

**功能**：包预训练 VLA 模型（HuggingFace）。

**输入（构造期）**：HF checkpoint 路径、prompt template、action chunk K。

**方法**
- `_load_model() -> None`：`AutoModelForVision2Seq.from_pretrained(...)`
- `_build_prompt(task_id) -> str`
- `_preprocess_image(rgb) -> Tensor`：resize 224×224 + normalize
- `act(obs)`：取相机图 → 拼 prompt → `model.predict_action` → 反归一化 → 经 `ActionChunker` 缓存
- 内置 `ActionChunker` 实例

---

## 8. `VLMPolicy`

**功能**：GPT-4V / Claude / Gemini，HTTP-based。

**依赖**：`VLMClient`。

**方法**
- `_build_messages(obs, task_desc) -> list[dict]`：base64 编码图 + 系统提示
- `act(obs)`：调 client → 解析 JSON → 转 ActionSpace 形式
- `_parse_response(json_str) -> action`
- 失败重试逻辑下沉到 `VLMClient`

---

## 9. `VLMClient`

**功能**：HTTP 通信层；重试 / 限流 / key pool。

**方法**
- `__init__(endpoint, api_keys: list[str], system_prompt) -> None`
- `request(messages: list[dict]) -> dict`
- `_rotate_key() -> str`
- `_backoff(retry_idx) -> None`
- `health_check() -> bool`

---

## 10. `HierarchicalPolicy`

**功能**：planner（VLM/大模型）每 K 步出 subgoal；executor（小网络/脚本）执行。

**输入**：`planner_policy: Policy`, `executor_policy: Policy`, `planner_period_k: int`。

**方法**
- `act(obs)`：若到周期则调 planner 更新 `current_subgoal`；否则调 executor
- `reset`：清空 `current_subgoal`
- `_subgoal_buffer`（per-env）：保存当前 subgoal

---

## 11. `ActionChunker`（组件/mixin）

**功能**：缓存 K 步动作，下 K-1 步直接出 cache。OpenVLA 和 Hierarchical 都用。

**方法**
- `push(env_id: int, chunk: list[action]) -> None`
- `pop(env_id: int) -> action | None`
- `is_empty(env_id: int) -> bool`
- `reset(env_ids: list[int] | None = None) -> None`
- 属性 `chunk_size: int`
