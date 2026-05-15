# D — Observation：类清单

> 对应 `modules/D_observation.md`。D 按 ObservationSpec 拼 dict，不知道下游 policy 怎么用。

---

## 1. `ObservationSpec`（数据类）

**字段**
- `cameras: list[CameraSpec]`（每个含 `name / res / fov / pos / lookat / up / render_modes`）—— Genesis 相机由 `pos`+`lookat`(+`up`) 定位，非 7 维 pose
- `proprio: list[Literal["joints","ee_pose","gripper","velocity"]]`
- `objects: list[str]`（按名字读 manifest 中的 props）
- `topology_state: bool`
- `dtypes: dict[str, dtype]`

**方法**
- `shape() -> ObservationShape`：构造期 D 暴露给 E
- `camera_specs() -> list[CameraSpec]`：构造期回传给 A
- `validate() -> None`

---

## 2. `ObservationShape`（数据类，跨模块契约）

**字段**：`dict[str, tuple[shape, dtype]]`。

**方法**
- `keys() -> list[str]`
- `shape_of(name) -> tuple`
- `dtype_of(name) -> dtype`

---

## 3. `Observer`

**功能**：按 spec 编排所有 fetcher，每步拼出 obs dict。

**输入（构造期）**：`ObservationSpec`, `SceneHandle`, `EntityManifest`, `TopologyStateCache`（从 B 取）。

**输入（每步）**：无（依赖构造期注入的句柄）。

**输出**：obs dict（按 spec 决定字段；形状对齐 `ObservationShape`）。

**方法**
- `__init__(spec, scene, manifest, topology_cache, preprocessor=None) -> None`
- `build_initial(env_ids: list[int] | None = None) -> dict`：reset 后的初帧 obs
- `step_obs() -> dict`：每步主入口
- `shape() -> ObservationShape`：透传 spec
- `_register_fetchers() -> None`：按 spec 实例化 fetcher 列表

---

## 4. `Fetcher`（抽象）

**子类**：`CameraFetcher` / `ProprioFetcher` / `ObjectStateFetcher` / `TopologyStateFetcher`。

**方法**
- `fetch(env_ids=None) -> dict[str, Tensor]`
- `keys() -> list[str]`：声明产出哪些字段
- `is_lazy() -> bool`：spec 中没要的 fetcher 可整体跳过

---

## 5. `CameraFetcher`

**输入**：camera handles（从 manifest 取）、render_modes（rgb/depth/seg/normal）。

**方法**
- `render() -> dict[str, Tensor]`：调 Genesis `cam.render(rgb=, depth=, segmentation=, normal=)`（返回 `(rgb, depth, segmentation, normal)` 元组，默认仅 rgb，其余需显式开）；批量多相机走 `scene.render_all_cameras(...)`
- `_should_render(camera_name) -> bool`：lazy 判断（粒度是「相机」整体跳过）

**纪律**：spec 没要的相机不渲染（渲染是开销大头）。

> ⚠️ Genesis 相机绑定到 `add_camera(env_idx=)`，光栅器一次 render 渲染该相机所辖的所有 env——**不能只渲染任意 env 子集**。lazy 粒度只能是「整台相机」，不能是「部分 env」；`render` 因此不再接受 `env_ids` 参数。

---

## 6. `ProprioFetcher`

**方法**
- `fetch` 内部：读 joint pos/vel、EE FK、夹爪开合
- `_compute_ee_pose(robot) -> Tensor[B, 7]`

---

## 7. `ObjectStateFetcher`

**方法**
- `fetch` 内部：按 spec 中 `objects` 列名从 manifest 取 props，读世界坐标
- 对 DLO 读顶点序列：`_read_dlo_vertices(name) -> Tensor[B, V, 3]`

---

## 8. `TopologyStateFetcher`

**方法**
- `fetch`：从 `TopologyStateCache.get()` 取，不重算
- `is_fresh() -> bool`：校验缓存有效（防止 step 顺序错乱）

---

## 9. `Preprocessor`（可选）

**功能**：resize / channel reorder / `uint8 → float / 255` 等 VLA-style 预处理。也可推到 E 内做。

**方法**
- `apply(obs_dict) -> obs_dict`
- `register_op(field_name, op_fn) -> None`

**纪律**：默认 RGB 保 `uint8`，预处理推迟到 E 内部减内存。
