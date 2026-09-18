# G3 — Eval：类清单

> 对应 `modules/G3_eval.md`。结构和 G2 几乎一样，区别是末端消费者从 Recorder 换成 Scorer。

---

## 1. `Evaluator`

**功能**：主入口；构造 EvalMatrix + Scorer + Reporter，启动 `BatchedRolloutDriver`。

**输入（启动期）**：`Runtime` 实例（policy 为 frozen E），`EvalConfig`, `MetricSpec`。

**输出**：episode JSONL + summary.json + 可选 GIF + 可选 plots。

**方法**
- `__init__(runtime: Runtime, eval_config: EvalConfig, metric_spec: MetricSpec) -> None`
- `run() -> Path`：返回 summary.json 路径
- `_build_scorer() -> Scorer`
- `_build_reporter() -> Reporter`
- `_build_driver() -> BatchedRolloutDriver`
- `_install_callbacks(driver, scorer, gif_saver) -> None`

---

## 2. `Scorer`

**功能**：持有 Metric 集合；episode 结束时 `update_episode`。

**方法**
- `__init__(metrics: list[Metric]) -> None`
- `update_episode(task: str, difficulty: str, info: dict) -> None`
- `aggregate() -> dict`：按 task × difficulty 分组返回所有 metric 值
- `episodes_per_combination() -> dict[tuple[str,str], int]`

---

## 3. `Metric`（抽象）

**子类**：`SuccessRateMetric` / `AvgStepsOnSuccessMetric` / `AvgTopologyDistanceMetric` / `IllegalActionRateMetric` / `FailureModeBreakdownMetric`。

**输入（每 episode）**：`task`, `difficulty`, `info`。

**输出**：metric 值（聚合时）。

**方法**
- `update(task, difficulty, info) -> None`
- `value(task=None, difficulty=None) -> float | dict`
- `confidence_interval(...) -> tuple[float, float] | None`
- `reset() -> None`
- 属性 `name: str`

---

## 4. `MetricSpec`（数据类）

**字段**：`metrics: list[str]`（要算哪些）、`confidence_level: float`、`bootstrap_samples: int`。

**方法**
- `instantiate() -> list[Metric]`：按 name 实例化

---

## 5. `Reporter`

**功能**：把 Scorer 聚合结果写盘。

**方法**
- `__init__(output_dir: Path) -> None`
- `write_jsonl(episodes: list[dict]) -> Path`：每 episode 一行
- `write_summary(aggregate: dict) -> Path`：按 task×difficulty×policy 汇总
- `write_plots(scorer: Scorer) -> list[Path]`（可选）
- `write_tensorboard(scorer: Scorer, logger: TrainLogger) -> None`：G1 中段评测复用

---

## 6. `GifSaver`

**功能**：rollout GIF（最难/最快/典型失败各几条）。

**方法**
- `__init__(output_dir: Path, max_per_category: int = 3) -> None`
- `add_frame(env_id: int, rgb: Tensor) -> None`
- `eligible(info: dict) -> Literal["hardest","fastest","typical_fail",None]`
- `save(env_id: int, info: dict, category: str) -> Path`
- `reset(env_id: int) -> None`

---

## 7. `EvalMatrix`

**功能**：`task × difficulty × policy` 组合迭代器。

**方法**
- `__init__(tasks: list[str], difficulties: list[str], policies: list[Policy] | None = None) -> None`
- `iter_combinations() -> Iterable[tuple[str, str, Policy | None]]`
- `reconfigure_env(runtime: Runtime, task: str, difficulty: str) -> None`：让 F 切到指定 task/difficulty（必要时换 TaskBase 子类实例）

---

## 8. `EvaluatorCallback`（`Callback` 子类）

**功能**：把 `Scorer` + `GifSaver` 钩到 `BatchedRolloutDriver` 上。

**方法**
- `__init__(scorer, gif_saver, current_task, current_difficulty) -> None`
- `on_step(timestep)`：若 `gif_saver` 开启，对 active env `add_frame(rgb)`
- `on_episode_end(env_id, summary)`：调 `scorer.update_episode` + `gif_saver.save`（若 eligible）
- `set_combination(task, difficulty) -> None`：每个组合切换时 EvalMatrix 调

---

## 9. `EvalConfig`（数据类）

**字段**：`tasks`, `difficulties`, `episodes_per_combination`, `deterministic: bool`, `save_gif: bool`, `output_dir`, `n_envs`。

**方法**
- `validate() -> None`
- `eval_matrix() -> EvalMatrix`
