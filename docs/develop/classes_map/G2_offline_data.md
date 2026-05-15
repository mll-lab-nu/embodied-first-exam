# G2 — Offline Data Generation：类清单

> 对应 `modules/G2_offline_data.md`。G2 自己写循环（rsl-rl 不参与），核心是 Recorder + StorageBackend。

---

## 1. `DataCollector`

**功能**：主入口；配置 Recorder，启动 `BatchedRolloutDriver`。

**输入（启动期）**：`F` 实例（policy 为 frozen E），`DataConfig`, `TrajectorySchema`。

**输出**：数据集文件 + index + DatasetCard + 生成日志。

**方法**
- `__init__(runtime: Runtime, data_config: DataConfig, schema: TrajectorySchema) -> None`
- `run() -> Path`：返回输出目录路径
- `_build_recorder() -> Recorder`
- `_build_driver() -> BatchedRolloutDriver`：见 `_shared_contracts.md`
- `_install_callbacks(driver, recorder) -> None`

---

## 2. `Recorder`

**功能**：主聚合接口；持有 schema + storage backend；接 `commit_episode`。

**输入**：`TrajectorySchema`, `StorageBackend`。

**方法**
- `__init__(schema: TrajectorySchema, backend: StorageBackend) -> None`
- `record_frame(timestep: TimeStep, env_id: int) -> Frame`：按 schema 抽字段
- `commit_episode(buffer: list[Frame], metadata: dict) -> None`
- `finalize() -> None`：写 index + close backend
- `episodes_committed -> int`

---

## 3. `StorageBackend`（抽象）

**子类**：`Hdf5Backend` / `ZarrBackend` / `LeRobotBackend` / `RldsBackend`。

**方法**
- `open(output_dir: Path) -> None`
- `write_episode(episode_id: str, frames: list[Frame], metadata: dict) -> None`
- `write_index(episode_meta_list: list[dict]) -> None`
- `close() -> None`
- `supports_streaming() -> bool`

---

## 4. `TrajectorySchema`（数据类）

**字段**：`fields: list[FieldSpec]`，每个 `FieldSpec` 含 `name / dtype / codec / source`（`source` 指明从 timestep 的哪个键拿）。

**方法**
- `select_fields(timestep: TimeStep, env_id: int) -> Frame`
- `validate() -> None`：保证字段不冲突 / codec 合法
- `summary() -> dict`：dump 到 DatasetCard 用

---

## 5. `EpisodeBuffer`

**功能**：per-env frame 累积，episode 结束统一 commit。

**方法**
- `__init__() -> None`
- `append(env_id: int, frame: Frame) -> None`
- `flush(env_id: int) -> list[Frame]`
- `reset(env_id: int) -> None`
- `length(env_id: int) -> int`

---

## 6. `EpisodeFilter`（可选）

**功能**：丢弃失败/超时 episode；按 success/fail 平衡。

**方法**
- `accept(metadata: dict) -> bool`
- `should_balance(metadata) -> bool`
- 属性 `accepted / rejected: int`

---

## 7. `DatasetCardWriter`

**功能**：渲染 README/DatasetCard。

**输入**：模板、字段 schema、生成命令、总数与成功率。

**方法**
- `write(template: str, fields: list[FieldSpec], stats: dict, output_path: Path) -> None`
- `_render_field_table(fields) -> str`
- `_render_split_info(stats) -> str`

---

## 8. `DataCollectorCallback`（`Callback` 子类）

**功能**：把 `Recorder` 钩到 `BatchedRolloutDriver` 的 `on_step / on_episode_end` 上。

**方法**
- `__init__(recorder: Recorder, buffer: EpisodeBuffer, filter: EpisodeFilter | None) -> None`
- `on_step(timestep)`：对每个 active env 调 `buffer.append(recorder.record_frame(...))`
- `on_episode_end(env_id, summary)`：调 `filter.accept` → `recorder.commit_episode` → `buffer.reset(env_id)`

---

## 9. `DataConfig`（数据类）

**字段**：`target_episodes`, `max_episode_steps`, `output_dir`, `format: Literal["hdf5","zarr","lerobot","rlds"]`, `filter_failures: bool`。

**方法**
- `validate() -> None`
