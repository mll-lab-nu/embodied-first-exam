# 阶段目标：渲染真实性配置 与 逐环境交付

> 日期：2026-08-12
> 性质：**目标与验收定义文档，不含代码改动**。
> 来源：用户给出的两条阶段目标——(1) 让环境支持 ray tracing 等提升真实性的渲染配置；
> (2) 逐个环境部署并产出 demo，每个环境交付「稳定的物理模拟」与「稳定的变式与配置体系」。
> 相关：[`../visual/photorealism_workstream_zh.md`](../visual/photorealism_workstream_zh.md)（渲染现状与两条不可行发现）、
> [`../visual/physical_realism_guidelines_zh.md`](../visual/physical_realism_guidelines_zh.md)（物理真实性准则与 metrics）、
> [`../data_pipeline/stable_il_generation_system_devlog_zh.md`](../data_pipeline/stable_il_generation_system_devlog_zh.md)（环境生成系统分层）、
> [`../physics/rope_backend_migration_zh.md`](../physics/rope_backend_migration_zh.md)（FEM+IPC 迁移进度与遗留项）。

---

## 1. 范围

本阶段的「环境」指仓库中有可运行 demo 的 6 个任务环境：

| 环境 | 类别 | demo | 绳/柔体 | env preset |
| --- | --- | --- | --- | --- |
| untangle_continuous | entangle | `untangle_continuous_physical_pinch_demo`（主力）等 3 个 | FEM+IPC（`rope.model=fem_ipc_tube`） | `world_tabletop_fem_v1` |
| untangle（离散） | entangle | `untangle_physical_handle_demo` | FEM+IPC | `world_tabletop_fem_v1` |
| cable_routing | routing | `cable_routing_physical_handle_demo` | FEM+IPC | `world_tabletop_fem_v1` |
| rope_winding | routing | `rope_winding_physical_handle_demo` | FEM+IPC | `world_tabletop_fem_v1` |
| bar_through_hole | routing | `bar_through_hole_physical_insert_demo` | 无（纯刚体） | `world_tabletop_v1` |
| stacked_plate | connectivity | `stacked_plate_physical_rotate_demo`、`stacked_plate_inspect_demo` | 无（纯刚体） | `world_tabletop_v1` |

`topogym/tasks/legacy/` 的 swap / onestroke / maze_wall_removal / peeling 场景代码保留，
demo 已于 2026-08-10 删除，不在本阶段范围内；若要纳入需先恢复 demo 入口，属另立项。

---

## 2. 目标 A：环境的渲染真实性配置

### 2.1 现状核对（2026-08-12 读代码与已装包得到）

| 项 | 现状 | 证据 |
| --- | --- | --- |
| `renderer` 配置键 | 两份 env config 都有 `renderer.type: rasterizer`，但没有任何代码消费该键：`StandardTabletopSceneBuilder.create()` 构造 `gs.Scene` 时只传 `sim_options` / `viewer_options` / `vis_options` / `show_viewer` 与 `scene_kwargs`（后者只含 `rigid_options`、`pbd_options`、调用方传入的 `scene_options`） | `configs/env_configs/world_tabletop_v1.yaml:30`、`configs/env_configs/world_tabletop_fem_v1.yaml:43`、`topogym/world/tabletop.py:163-191` |
| RayTracer 可用性 | Genesis 的 RayTracer 无条件 `import LuisaRenderPy`，路径为 `<genesis>/ext/LuisaRender/build/bin`；当前安装（Genesis 1.2.1，`.venv-gs110`）的 `genesis/ext/` 下只有 `isaacgym`、`pyrender`、`urdfpy`、`VolumeSampling`、`_trimesh_patch.py`，无 LuisaRender | `.venv-gs110/lib/python3.11/site-packages/genesis/vis/raytracer.py:14-18` |
| BatchRenderer 可用性 | Genesis 的 BatchRenderer 依赖 `gs_madrona`；`gs_madrona 0.0.7.post2` 已安装在同一 venv。**导入是否成功未验证**（该 venv 为 Linux 侧环境，本机 Windows shell 无法执行） | `genesis/vis/batch_renderer.py:15-21`、site-packages 内 `gs_madrona-0.0.7.post2.dist-info` |
| 光栅化下有效的观感手段 | `VisOptions` 的 lights / ambient_light / background_color / shadow / plane_reflection，以及 diffuse `ImageTexture`；surface 的 roughness / metallic / normal / emissive 仅光追消费，在光栅化下无视觉效果 | `photorealism_workstream_zh.md` §2、§5 |
| 已落地的共用模块 | `topogym/world/materials.py`（9 个语义角色的材质入口）、`topogym/world/lighting.py`（key/fill 方向光 + ambient + 背景 + 阴影，可用 `env.vis` 覆盖），所有 task 经 builder 自动继承 | `topogym/world/lighting.py`、`configs/env_configs/world_tabletop_v1.yaml` 的注释版 `vis:` 块 |

读表结论：「enable ray tracing」在当前安装下不能通过改配置达成，因为缺两件东西——一是配置键到
`gs.Scene(renderer=...)` 的接线，二是 LuisaRender 扩展本身。因此目标 A 拆成先接线、再逐条判定可用性。

### 2.2 子目标

| 编号 | 内容 | 交付物 | 验收 | 状态 |
| --- | --- | --- | --- | --- |
| A1 | renderer 配置接线：`env.renderer.type` 映射到 `gs.Scene(renderer=...)`，缺省仍为 rasterizer | `topogym/world/tabletop.py` 一处改动 + 两份 env config 的键说明 | 缺省运行与改动前画面一致；配置成不可用的渲染器时给出指明缺失依赖的报错，而非 import 栈 | 未开工 |
| A2 | RayTracer 可用性判定：评估在目标机器上编译 LuisaRender 的成本，或确认放弃 | 一份结论记录（编译步骤与耗时，或失败原因） | 可编译：在一个环境中渲出 512px 单帧并归档；不可编译：记录原因并转 A3/A4 | 未开工 |
| A3 | BatchRenderer 可用性判定：验证 `gs_madrona` 导入与单相机渲一帧 | 结论记录 + 一帧截图 | 导入成功且渲出与 rasterizer 构图一致的一帧；失败则记录报错 | 未开工 |
| A4 | 光栅化路径的观感上限：diffuse 贴图（桌面/桌框）与光影参数在 `env.vis` 覆盖块上的调档 | 贴图资产 + 一组 `vis` 预设 | 同机位截图与当前默认并排对比，由用户判定是否采用 | 未开工 |

依赖关系：A1 独立且是其余三项的前置（没有接线，任何渲染器都进不去场景）。A2 成本最高、结论不确定；
A3 成本低，先做可以在 A2 之前给出「是否已有比 rasterizer 更真实的通路」的答案。A4 与 A2/A3 的结论无关，
任何时候都可做，收益上限受光栅化能力限制。

建议顺序：A1 → A3 → A4 → A2。

### 2.3 目标 A 的验收口径

1. 6 个环境都能用一行配置覆盖切换渲染器，且缺省行为与本阶段开始前一致。
2. 光追与 BatchRenderer 各有一条明确结论（可用并附样张 / 不可用并附原因），不留「未验证」。
3. 若两条高真实度通路都不可用，本目标降级为 A4 的光栅化观感提升，并在本文更新结论。

### 2.4 需要一并考虑的成本

FEM+IPC 已是四个绳任务的默认后端，带臂端到端墙钟为 PBD 的 1.50×，单步成本约 3.7×
（`rope_backend_migration_zh.md` §3.3）。渲染器升级会叠加在这个基数上，直接影响录制时长与
sweep 的单格超时设置（当前 `TIMEOUT_S=1200`）。若 A2/A3 通路可用，需在采用前测一次带渲染的端到端墙钟。

---

## 3. 目标 B：逐环境部署与产出 demo

### 3.1 两件交付物的可验收定义

**交付物 1：稳定的物理模拟**

| # | 条件 | 测量方式 |
| --- | --- | --- |
| B1.1 | 该环境在 seed × 难度矩阵上无 CRASH-segv、CRASH-phys、TIMEOUT | `bash_scripts/tests/stability_sweep.sh <task>` 的分类矩阵 |
| B1.2 | 物理真实性 metrics M1~M6 全部满足阈值 | `physical_realism_guidelines_zh.md` §2 |
| B1.3 | 无未记档的可见穿模（准则 P2） | 评测相机 512px 下人工核对 + 已有豁免清单 |
| B1.4 | demo 退出码 0 并打印顶层 `success=`，失败时给出结构化 EpisodeResult | demo 日志 |

**交付物 2：稳定的变式与配置体系**

| # | 条件 | 测量方式 |
| --- | --- | --- |
| B2.1 | 该 task_id 在 `topogym/generation/layout_randomization.py` 的 `_REGISTRY` 中有条目，且抖动只作用于 oracle 会读回的字段 | 代码 + 单元检查 |
| B2.2 | demo 支持 `run.randomize_layout` 与 `run.difficulty`，并在日志中打印本次取值 | demo 日志 |
| B2.3 | easy / default / hard 三档的抖动幅度经 sweep 验证在安全包络内 | `RANDOMIZE=1 DIFFICULTIES="easy default hard" stability_sweep.sh <task>` |
| B2.4 | `configs/episode_splits/<task>.yaml` 已登记，`episode_index.py` 路由表有对应行 | 配置 + 代码 |
| B2.5 | 同一 seed 重复运行得到同一布局与同一 plan | 两次运行的 resolved config 与 plan 摘要比对 |

`_REGISTRY` 的既有约束沿用，不在本阶段放宽：只做有界扰动、不改拓扑与物体数量、不动 robot home 与 env 配置。
cable_routing 的抖动要求 `routing.smooth_route=true`，硬写的 `endpoint_oracle_waypoints` 路径不得开随机化。

### 3.2 逐环境现状与净差距

图例：✅ 已具备 · ⚠️ 具备但有注意点 · ⬜ 缺

| 环境 | 物理后端 | B2.1 randomize 注册 | B2.2 demo 接线 | B1.1 在 sweep 表内 | B2.4 split | 净差距 |
| --- | --- | --- | --- | --- | --- | --- |
| untangle_continuous | FEM+IPC | ⬜ | ⬜ | ✅ | ⬜ | 注册 + 接线 + split |
| untangle（离散） | FEM+IPC | ✅ `holes.spacing` | ✅ | ✅ | ⬜ | split；FEM 下的抖动包络未重扫 |
| cable_routing | FEM+IPC | ⚠️ P1/P2 位置，要求 smooth_route=true | ✅ | ✅ | ⬜ | split；FEM 下的抖动包络未重扫 |
| rope_winding | FEM+IPC | ⬜ | ⬜ | ⬜ | ⬜ | 注册 + 接线 + 加入 sweep 表 + split |
| bar_through_hole | 纯刚体 | ⬜ | ⬜ | ⬜ | ⬜ | 注册 + 接线 + 加入 sweep 表 + split |
| stacked_plate | 纯刚体 | ✅ `disks.init_angle_deg` | ✅ | ✅ | ⬜ | split |

补充事实：

- `_REGISTRY` 现有 4 条（untangle、cable_routing、stacked_plate、peeling），其中 peeling 对应的 demo 已删除。
- `stability_sweep.sh` 的 `TASKS` 表覆盖 4 个任务（untangle、untangle_continuous、cable_routing、stacked_plate），
  rope_winding 与 bar_through_hole 未登记。
- `configs/episode_splits/` 目前只登记了 swap（该任务的 demo 已删除），即 6 个在册环境的 split 全缺。
- 现有的抖动幅度是保守初值，注释里写明安全包络需用 sweep 实测确定；FEM+IPC 成为默认后端之后，
  这些幅度尚未在新后端上重扫过。

### 3.3 建议顺序

按「已有基础 → 补齐差距」的梯度铺开，每个环境走完再进下一个：

```
stacked_plate    ← 纯刚体、三项已具备，只差 split；用来把 split 与 sweep 口径跑通
untangle（离散）  ← 三项已具备，FEM 下重扫抖动包络
cable_routing    ← 同上，注意 smooth_route 前置
untangle_continuous ← 补注册 + 接线
rope_winding     ← 补注册 + 接线 + 进 sweep 表
bar_through_hole ← 同上（纯刚体，风险最低，放最后是因为差距最全）
```

### 3.4 目标 B 的验收口径

6 个环境各自的 B1.1~B1.4 与 B2.1~B2.5 全部满足，并留下一份跨环境汇总表（每个环境一行：
sweep 矩阵结果、metrics 结论、难度档包络、split 路径）。任何一项不满足时记录未满足的具体条款，
不以「基本可用」结论收尾。

---

## 4. 两条目标线的关系

目标 A 与目标 B 相互独立，可并行推进，但有两处交叉：

1. 渲染器切换必须落在 env 层且缺省不变，否则目标 B 的 sweep 与 metrics 基线会随渲染改动漂移。
   建议目标 B 的 sweep 一律在缺省渲染器（rasterizer、headless）下跑。
2. 若 A2/A3 得出可用结论，录制类产出（demo 视频）可切到高真实度渲染器；稳定性测量仍留在缺省渲染器。

---

## 5. 待确认项

| # | 项 | 影响 | 处理 |
| --- | --- | --- | --- |
| 1 | `gs_madrona` 能否在目标机器上导入并渲一帧 | 决定 A3 是否成立 | 归入 A3，需在 Linux 侧 venv 内执行 |
| 2 | 编译 LuisaRender 的可行性与耗时 | 决定 A2 是否成立 | 归入 A2 |
| 3 | FEM+IPC 下现有抖动幅度是否仍在安全包络内 | 决定 B2.3 是否需要调参 | 归入各环境的 sweep |
| 4 | 遗留项：cable_routing 的 P1:left `endpoint_route_ok` 两后端同败、绳材质 E/nu 联合标定、`substeps=1` 吞吐优化 | 影响 cable_routing 的 B1 判定 | 见 `rope_backend_migration_zh.md` §5「遗留立案」，未排期 |
| 5 | 成功判定未统一：untangle 与 cable_routing 的判定在 demo/supervision 层，不是 `*PuzzleEvaluator` 类 | 影响跨环境汇总表的口径一致性 | 本阶段不强制收敛，汇总表中标注来源 |

---

## 6. 不在本阶段范围

- legacy 四个任务（swap / onestroke / maze_wall_removal / peeling）的 demo 恢复与交付。
- IL 数据集正式录制（属 `robomme_pipeline_roadmap_zh.md` 的 W3/W4）。
- RL / MDP 环境。
- 拓扑或成功判定语义的改动；本阶段只测量既有判定，不重定义。
