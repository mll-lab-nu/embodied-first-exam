# G1 — Online RL Training：类清单

> 对应 `modules/G1_online_rl.md`。G1 不重写训练循环；只配置 + 启动 + 监听 rsl-rl。

---

## 1. `RlTrainer`

**功能**：主入口；config 合并、建 env、建 policy、launch。

**输入（启动期）**：`TrainConfig`, `AlgorithmConfig`, `OutputDir`，可选 `--resume <path>`。

**输出**：周期性 checkpoint + 训练日志。

**方法**
- `__init__(train_cfg: TrainConfig, algo_cfg: AlgorithmConfig, output_dir: Path) -> None`
- `build() -> tuple[Runtime, Policy]`：组装 A+B+C+D+E + F
- `run() -> None`：主入口；调 `algorithm.learn(num_iters)`
- `resume(checkpoint_path: Path) -> None`：续训
- `_register_callbacks() -> None`：例如 `MidTrainEvalCallback`

---

## 2. `Algorithm`（抽象协议）

**功能**：算法侧抽象；目前 MVP 走 rsl-rl，预留 RLinf / TorchRL / 自研。

**方法**
- `init(env, policy, config) -> None`
- `learn(num_iters: int) -> None`
- `save(path) -> None`
- `load(path) -> None`
- 属性 `iter_count: int`

---

## 3. `RslRlAlgorithm`

**功能**：包 rsl-rl `OnPolicyRunner` 的具体实现。

**输入**：`F.as_rsl_rl_env()` adapter, `TorchPolicy`, `AlgorithmConfig`。

**方法**
- `_build_runner(env, policy, log_dir) -> OnPolicyRunner`：把 E 网络注入 rsl-rl 的 actor-critic
- `learn(num_iters)`：调 `runner.learn(num_learning_iterations=num_iters, init_at_random_ep_len=True)`
- `_inject_policy_weights(policy, runner) -> None`：双向同步 E 内 nn.Module ↔ rsl-rl actor-critic
- `save(path) / load(path)`：透传给 runner

---

## 4. `CheckpointManager`

**功能**：save/load 网络 + optimizer + iter counter。

**方法**
- `save(iter: int, network_state, optimizer_state, extra: dict | None = None) -> Path`
- `load(path: Path) -> dict`：返回 `{iter, network_state, optimizer_state, extra}`
- `latest() -> Path | None`：扫输出目录返回最新 checkpoint
- `prune(keep_n: int) -> None`：保留最近 N 个

---

## 5. `TrainLogger`（抽象） + 子类

**子类**：`TensorBoardLogger` / `WandbLogger` / `StdoutLogger` / `CompositeLogger`（聚合多个）。

**方法**
- `log_scalar(name: str, value: float, step: int) -> None`
- `log_dict(d: dict, step: int) -> None`
- `log_histogram(name, values, step) -> None`（可选）
- `log_video(name, frames, step) -> None`（可选；用于评测中段）
- `close() -> None`

---

## 6. `TrainConfig` / `AlgorithmConfig`（数据类）

**`TrainConfig` 字段**：`num_iters`, `rollout_length`, `save_interval`, `log_interval`, `mid_eval_interval`, `resume_from`。

**`AlgorithmConfig` 字段**：`algorithm: Literal["ppo","sac",...]`, `lr`, `clip_param`, `gamma`, `lam`, `batch_size`, `entropy_coef`, `value_coef`。

**方法**
- `validate() -> None`
- `to_dict() -> dict`：dump 给 reproducibility 用

---

## 7. `MidTrainEvalCallback`（`Callback` 子类）

**功能**：训练中段周期性调 G3 评测。

**输入**：`Evaluator` 实例 + 评测间隔。

**方法**
- `__init__(evaluator: Evaluator, interval: int) -> None`
- `on_iter_end(iter_idx)`：若 `iter_idx % interval == 0`，调 `evaluator.run()`；评测结果 log 到 `TrainLogger`

---

## 8. `SmokeTest`（可选）

**功能**：验证 F 的 rsl-rl 接口面在最新 rsl-rl-lib 上能跑通（dummy task + 10 iter PPO），针对 Issue #757 的护栏。

**方法**
- `run() -> bool`：返回是否通过
