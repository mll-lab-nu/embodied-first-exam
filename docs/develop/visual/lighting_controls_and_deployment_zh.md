# 光照参数组与部署步骤

> 日期：2026-08-15
> 性质：**参数定义与工程步骤文档，不含代码改动**。
> 来源：目标文档 [`../meta/render_config_and_env_delivery_goals_zh.md`](../meta/render_config_and_env_delivery_goals_zh.md) 的目标 A；
> 用户于 2026-08-15 定下两条架构决定（见 §1.2），并要求以旋钮加指标的形式取代固定预设。
> 相关：[`photorealism_workstream_zh.md`](photorealism_workstream_zh.md)（渲染现状与两条不可行发现）、
> [`physical_realism_guidelines_zh.md`](physical_realism_guidelines_zh.md)（metrics 的书写口径）、
> [`../framework/config_reference_zh.md`](../framework/config_reference_zh.md)（配置键总表，落地后需同步）。

---

## 1. 范围与已定决定

### 1.1 范围

本文覆盖 6 个在册环境（untangle_continuous、untangle、cable_routing、rope_winding、bar_through_hole、stacked_plate）共用的场景光照与渲染路径配置。不覆盖材质贴图资产、相机机位与相机内参。

### 1.2 两条架构决定

| # | 决定 | 含义 |
| --- | --- | --- |
| D1 | 光照参数只存在于 env 层，全部任务共用一套，切换动作发生在这一层 | task config 与 run config 不设光照键。现有实现已经满足该约束：`StandardTabletopSceneBuilder` 调用 `lighting.vis_options(self.env_cfg)`（`topogym/world/tabletop.py:188`），env 层以外的配置节点不进入该函数 |
| D2 | 渲染路径参数扩展现有的 `renderer:` 块，不另起新块 | 两份 env config 已有 `renderer.type` 与 `renderer.show_viewer`（`configs/env_configs/world_tabletop_v1.yaml:30-32`），目标 A1 本就要给该块接线。避免出现 `renderer:` 与 `render:` 两个近义键并存 |

由 D1 与 D2 得到的配置分工：`renderer:` 承载渲染路径（选哪个渲染器及其专属参数），`vis:` 承载光照（光源布置与强度）。两个块都在 env 层。

---

## 2. 现状核对（2026-08-15 读代码得到）

### 2.1 当前唯一的一套光照

数值硬编码在 `topogym/world/lighting.py:23-32`，两份 env config 的 `vis:` 覆盖块整体处于注释状态，因此 6 个环境、全部相机、sweep 与 demo 录制共用下表：

| 项 | 值 | 换算后的语义值 |
| --- | --- | --- |
| key 方向光 | dir `(-0.6,-0.5,-1.0)`、color `(1.0,0.98,0.95)`、intensity `4.0` | 方位角 40°、仰角 52° |
| fill 方向光 | dir `(0.6,0.4,-0.7)`、color `(0.90,0.93,1.0)`、intensity `1.5` | 方位角 214°、仰角 44°，与 key 相差 174° |
| ambient_light | `(0.35,0.35,0.38)` | — |
| background_color | `(0.55,0.58,0.62)` | 明度 0.58 |
| shadow | `true` | — |
| plane_reflection | `false` | — |
| key : fill | 4.0 : 1.5 | 对比比值 2.67 |

方向向量在 `gu.z_up_to_R` 内被归一化（`utils/geom.py:1583-1584`），因此改用方位角与仰角参数化可以逐像素复现当前画面。

### 2.2 三条渲染路径的光源模型互不相通

| 后端 | 光源来源 | 关键约束 | 本机可用性 |
| --- | --- | --- | --- |
| Rasterizer（当前默认） | `VisOptions.lights`，只支持 `DirectionalLight` 与 `PointLight`；`AmbientLight` 放进列表会抛异常（`vis/rasterizer_context.py:1193-1203`），环境光走 `ambient_light` 字段 | 每类光源上限 4 盏（`ext/pyrender/constants.py:4`）；`shadow` 为三类光源共用的全局开关（`ext/pyrender/renderer.py:710-714`）；`plane_reflection` 只作用于 `gs.morphs.Plane` 地面，不作用于桌面（`vis/rasterizer_context.py:478-480`） | 可用 |
| RayTracer | `SphereLight` 列表、`scene.add_mesh_light()` 发光网格、环境球 `env_surface` | 无方向光概念，方向光需映射为远置球面光源；`.hdr`/`.exr` 环境贴图只有该后端支持 | 不可用，`genesis/ext/LuisaRender` 不存在（`vis/raytracer.py:15-18`） |
| BatchRenderer | `scene.add_light()` 自有光源表，**不读 `VisOptions.lights`**（`vis/batch_renderer.py:270`、`engine/scene.py:589-628`） | 需 CUDA 后端；至少一台相机；全部非 debug 相机分辨率一致；`use_rasterizer=False`（缺省）时走 GPU 光线追踪（`gs_madrona/renderer_gs.py:86`） | 包已安装（linux-x86_64），导入与渲帧未验证 |

该表是参数组必须定义在语义层的直接原因：同一个「主光强度」在三个后端上是三种不同的调用。

---

## 3. 参数组定义

### 3.1 第一层：渲染路径 `env.renderer`

离散选择，决定真实度上限。

| 键 | 默认 | 取值 | 作用 | 生效后端 |
| --- | --- | --- | --- | --- |
| `type` | `rasterizer` | `rasterizer` / `raytracer` / `batch` | 映射到 `gs.Scene(renderer=)` | 全局 |
| `show_viewer` | `false` | bool | 现有键，行为不变 | 全局 |
| `batch_use_rt` | `true` | bool | Madrona 走光线追踪还是光栅化 | batch |
| `spp` | `256` | 16–1024 | 每像素采样数。噪点与耗时之间的主要旋钮，近似线性 | raytracer |
| `denoise` | `true` | bool | 去噪。开启后 spp 可降至 64 量级 | raytracer |
| `max_depth` | `8` | 4–32 | 光线弹射次数上限。Genesis 缺省 32，桌面场景 8 即可 | raytracer |
| `env_map` | `null` | `.hdr` / `.exr` 路径 | 环境球贴图，同时提供天空盒与全向环境光 | raytracer |
| `dof` | `null` | `{aperture, focus_dist}` | 景深。设值时相机 `model` 切为 `thinlens` | raytracer |

从 rasterizer 切到 raytracer 得到的能力：软阴影、间接光与环境光遮蔽、`materials.py` 中 9 个角色的 roughness/metallic 首次生效、HDRI 环境光、景深。代价为单帧耗时上升一至两个数量级，以及需要自行编译 LuisaRender。

### 3.2 第二层：光照旋钮 `env.vis`

连续调参，三个后端都需映射。**全部默认值等于 §2.1 现值**，不设任何键时画面零变化。

| 键 | 默认 | 含义 | 建议范围 |
| --- | --- | --- | --- |
| `exposure` | `1.0` | 全部光源强度的统一倍率，基准为 key=4.0 | 0.5–2.0 |
| `contrast` | `2.67` | key 与 fill 的强度比。1.0 为全平光 | 1.0–6.0 |
| `key_azimuth_deg` | `40` | 主光来向的水平角，+x 为 0°，向 +y 增大 | 0–360 |
| `key_elevation_deg` | `52` | 主光来向的仰角，90° 为正顶光 | 15–85 |
| `fill_offset_deg` | `174` | 补光方位相对主光的偏移，180° 为正对面 | 120–200 |
| `rim` | `0.0` | 轮廓光强度，取主光的比例。0 表示不建该光源 | 0–0.6 |
| `ambient` | `0.35` | 环境光水平，决定暗部下限 | 0.05–0.60 |
| `key_temp_k` | `null` | 主光色温（K）。设值后接管颜色，不设沿用现有 RGB | 3000–8000 |
| `fill_temp_k` | `null` | 补光色温（K） | 3000–8000 |
| `softness` | `0.0` | 光源角直径，控制半影宽度 | 0–1 |
| `shadow` | `true` | 阴影总开关 | — |
| `background` | `0.58` | 背景明度（灰阶标量） | 0–1 |

设计说明：

- 色温键默认为 `null`。色温到 RGB 的转换为近似公式，给定默认数值会让缺省画面产生微小漂移，与 §6 的基线不变约束冲突。设计为「不设即沿用现有 RGB」可以规避该风险。
- `rim` 默认为 0。第三盏光源对细绳轮廓有实际作用（绳直径为毫米量级，在浅灰桌面上属于低对比细长物体），但它改变画面，不能进入缺省档。
- `softness` 只有 raytracer 消费。rasterizer 使用 shadow map，无半影控制；batch 后端的光源模型同样没有对应项。这两种情况下设置该键需打印一条指明后端的 warning，不静默忽略。
- 不暴露 `plane_reflection`。它只作用于地面，桌子已遮住操作区，开启后仅使桌子周围地板变为镜面，并增加一遍渲染。该键在 `lighting.py` 内保持 `false`。
- 原有的 `key_dir` / `key_color` / `key_intensity` 等原始键保留，优先级高于语义旋钮，已有配置不受影响。

### 3.3 后端映射矩阵

| 旋钮 | rasterizer | raytracer | batch |
| --- | --- | --- | --- |
| key / fill / rim | `VisOptions.lights` 的 `DirectionalLight` | 沿该方向远置的 `SphereLight`，`radius` 由 `softness` 给定 | `scene.add_light(directional=True)` |
| `ambient` | `VisOptions.ambient_light` | 环境球均匀发光（`env_map` 为 null 时） | 无对应项 |
| `shadow` | `VisOptions.shadow` | 路径追踪固有，该键无效 | 每盏光的 `castshadow` |
| `softness` | 无对应项 | `SphereLight.radius` | 无对应项 |
| `background` | `VisOptions.background_color` | 环境球颜色 | 需确认 |

batch 列的两处缺口（无环境光、无软阴影）来自 Madrona 光源模型本身。切换到该后端时需打印被忽略的旋钮清单。

### 3.4 第三层：指标

全部指标可从单帧渲染结果算出，由 `scripts/lighting_probe.py` 输出一行数字。书写口径对齐 `physical_realism_guidelines_zh.md` §2。

| # | 指标 | 定义 | 建议区间 | 含义 |
| --- | --- | --- | --- | --- |
| L1 | mean_luminance | 归一化亮度均值 | 0.40–0.55 | 整体曝光 |
| L2 | clipped_high_ratio | 亮度 > 0.98 的像素占比 | < 1% | 高光处纹理丢失 |
| L3 | clipped_low_ratio | 亮度 < 0.02 的像素占比 | < 2% | 暗部细节进不了观测 |
| L4 | dynamic_range | p95 − p5 | 0.35–0.60 | 对比是否合适 |
| L5 | subject_bg_contrast | 分割 mask 内绳/物体像素与桌面像素的亮度中位数之差 | > 0.12 | 主体可辨识度，对应 B1.3 的人工核对前提 |
| L6 | shadow_coverage | `shadow` 开关两帧差分 > 0.03 的像素占比 | 5%–25% | 阴影过重或缺失 |
| L7 | frame_render_ms | 单帧渲染耗时 | 记录，不设阈值 | 与 sweep 的 `TIMEOUT_S=1200` 预算关联 |
| L8 | determinism_diff | 同 seed 两次渲染的像素差 | == 0 | 后续光照随机化的确定性前提 |

L5 可计算的依据：Genesis 支持 link 级分割渲染（`camera.render(segmentation=True)`，`VisOptions.segmentation_level`），能把绳的像素与桌面像素分开。该指标把「这套光照够不够」从目视判断变为一个数值。

---

## 4. 工程步骤

| 编号 | 内容 | 交付物 | 验收 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| S1 | 光照旋钮层：`lighting.py` 拆为「解析旋钮 → 语义光源中间表示 → 按后端发射」，`env.vis` 扩展为 §3.2 的键 | `topogym/world/lighting.py`、两份 env config 的 `vis:` 注释块改写 | 不设任何键时，6 个环境的同机位截图与改动前逐像素一致；设 `exposure` / `contrast` / `key_azimuth_deg` 后画面按预期变化 | 无 | 未开工 |
| S2 | 指标探针：新增 `scripts/lighting_probe.py`，走同一 Hydra 配置建场景、settle、逐相机渲一帧、打印 L1~L8 | 脚本 + 缺省档的基线数字（记入 §5） | 在 6 个环境上跑通并输出完整 8 项；L8 恒为 0 | S1 | 未开工 |
| S3 | 渲染路径接线：`renderer.type` 映射到 `gs.Scene(renderer=)`，扩展 §3.1 的键 | `topogym/world/tabletop.py` 一处改动 + env config 键说明 | 缺省行为不变；配置成缺依赖的渲染器时报出指明缺失依赖的错误，而非 import 栈 | 无（可与 S1 并行） | 未开工，对应目标 A1 |
| S4 | BatchRenderer 可用性判定 | 结论记录 + 一帧截图 + 光源重映射代码 | 导入成功且渲出与 rasterizer 构图一致的一帧；失败则记录报错 | S1、S3 | 未开工，对应目标 A3 |
| S5 | RayTracer 可用性判定 | 编译步骤与耗时记录，或失败原因 | 可编译时在一个环境渲出 512px 单帧并归档，同时接通 `softness` / `env_map` / `dof` / `spp` | S3 | 未开工，对应目标 A2 |
| S6 | 定档与记录：用探针在缺省档出一组基线数字，登记入本文 §5；后续任何光照改动对照该组数字 | 本文 §5 的填表 | 6 个环境各一行完整数字 | S2 | 未开工 |

S4 的前置条件需单独处理：BatchRenderer 要求全部非 debug 相机分辨率一致，而当前相机组存在两种分辨率（`base_camera` / `wrist` 为 256×256，`oblique` / `topdown` / `front` 为 512×512）。两条处理路径——统一分辨率，或把高分辨率的人看相机标为 `debug=true`（debug 相机始终走普通光栅化，不进批渲染，`vis/camera.py:63-67, 143-146`）。后者同时给出「观测相机走批渲染、录制相机走高分辨率光栅化」的分工，推荐采用。

建议顺序：S1 与 S3 并行 → S2 → S6 → S4 → S5。S5 成本最高且结论不确定，放在 S4 之后；若 S4 成立，已经拿到一条光线追踪通路，S5 的优先级相应下降。

### 4.1 验证命令

S1 落地后的缺省不变验证与旋钮验证（在 Linux 侧 venv 内执行）：

```bash
# 缺省档，逐环境出基线截图与指标
python -B -m scripts.lighting_probe env_configs@env=world_tabletop_fem_v1 2>&1 | tee runs/lighting_probe_default.log

# 单旋钮验证：主光转到正对面、整体提亮
python -B -m scripts.lighting_probe env.vis.key_azimuth_deg=220 env.vis.exposure=1.3 2>&1 | tee runs/lighting_probe_key220.log

# 录制档试拍（轮廓光 + 压暗背景），与缺省档同机位对比
python -B -m demos.routing.rope_winding_physical_handle_demo run.probe=true \
  env.vis.rim=0.4 env.vis.background=0.32 env.vis.ambient=0.22 \
  recording=hq recording.path=runs/videos/rope_winding_rim.mp4 recording.camera=[oblique,front] \
  2>&1 | tee runs/rope_winding_rim.log
```

---

## 5. 基线数字（S6 后填写）

| 环境 | 相机 | L1 | L2 | L3 | L4 | L5 | L6 | L7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| untangle_continuous | front | | | | | | | |
| untangle | front | | | | | | | |
| cable_routing | front | | | | | | | |
| rope_winding | front | | | | | | | |
| bar_through_hole | front | | | | | | | |
| stacked_plate | front | | | | | | | |

---

## 6. 与目标 A / B 的交叉约束

1. **缺省画面不变**。S1 与 S3 的缺省行为必须与本文日期之前一致，否则目标 B 的 sweep 与 metrics 基线随渲染改动漂移。判定方式为同机位截图逐像素比对。
2. **稳定性测量锁在缺省档**。`stability_sweep.sh` 一律不带 `env.vis.*` 与 `env.renderer.*` 覆盖，运行在 rasterizer、headless 下。
3. **录制产出可切换**。S4 或 S5 得出可用结论后，demo 视频可切到高真实度后端；稳定性测量仍留在缺省后端。
4. **渲染耗时计入预算**。FEM+IPC 已使带臂端到端墙钟为 PBD 的 1.50×（`../physics/rope_backend_migration_zh.md` §3.3）。渲染器升级叠加在该基数上，采用前需测一次带渲染的端到端墙钟，并据此复核 sweep 的单格超时。

---

## 7. 待确认项

| # | 项 | 影响 | 处理 |
| --- | --- | --- | --- |
| 1 | BatchRenderer 的 `background` 是否有对应项 | §3.3 映射矩阵最后一格 | 归入 S4，读 `gs_madrona` 接口确认 |
| 2 | 相机分辨率统一方案：统一为单一分辨率，或将人看相机标为 `debug=true` | 决定 S4 的改动范围 | 归入 S4，推荐后者 |
| 3 | 光照随机化是否纳入本阶段 | 决定是否需要在 `env.vis` 上加 seed 与范围键 | 不纳入。该项属目标 B 的 B2 范围，待布局随机化铺开后再立项；L8 指标先行，作为其确定性前提 |
| 4 | LuisaRender 在目标机器上的编译可行性与耗时 | 决定 S5 是否成立 | 归入 S5 |
