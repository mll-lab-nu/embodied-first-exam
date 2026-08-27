# 任务四分类的工程约束（类别轴规矩）

> 日期：2026-08-04
> 上游：`docs/develop/TopoGym_tasks.docx`（四类能力定义与 20 个任务的场景／判定／防捷径设计）
> 配套：[`module_boundaries_zh.md`](module_boundaries_zh.md)（层轴规矩）
> 修订：初稿主张「类别用字段表示、不建目录」，同日改为「只在 `tasks/` 一层建类别目录」，
> 理由见 §1.1。已按新结论落地。

---

## 0. 本文解决的问题

`TopoGym_tasks.docx` 把任务按「机器人动作前必须理解的空间关系」分成四类，并对每个任务规定了状态
变化、成功判定与防捷径。本文写作时，仓库里没有任何位置记录这个分类：

- `topogym/tasks/`、`configs/task_configs/`、`demos/` 均按 task_id 平铺，无类别信息。
- 四个 bash 注册表（`stability_sweep.sh` / `verify_dataset_recording.sh` / `record_all_tasks.sh` /
  `collect_and_view.sh`）各自维护一份 task 列表，列表内容互不一致，也不含类别。
- H5 `setup` attrs 只写 `task_id`（`topogym/data/episode_dataset_writer.py:202`），下游无法按类别聚合。
- 各任务 verifier 的终态判据形式不统一：有整数交叉数（`untangle_continuous_verifier.py`）、
  有集合差（`peeling_verifier.py`）、有图连通（`maze_wall_removal_verifier.py`）、
  有位置阈值（`stacked_plate_verifier.py`），没有「同一类别的任务判据必须同形」的约束。

结果是：类别只存在于文档里，代码无法强制。本文规定类别在工程上的表示方式、每类必须满足的判定
契约、现有任务的归类结论，以及新增任务的准入条件。

第一条（`topogym/tasks/` 的目录布局）已于 2026-08-04 落地，见 §1.1 与 §7 阶段 A；其余三条待办。

---

## 1. 两条正交轴

仓库已有一条轴：**层**（`tasks` / `verification` / `supervision` / `envs` / `planning`），由
`module_boundaries_zh.md` 规定，回答「这段代码放哪个目录」。

本文引入第二条轴：**类**（C1–C4），回答「这个任务考什么能力、判定必须长什么样」。

两条轴正交，交叉方式如下：

| | 层轴 | 类轴 |
|---|---|---|
| 载体 | 全部五层的目录结构 | 仅 `tasks/` 一层的子目录 |
| 变更成本 | 移动文件 + 改 import | 移动一个文件 + 改一行 import |
| 由谁强制 | 目录约定 + import 方向 | 目录布局本身，`core/taxonomy.py` 校验 |

### 1.1 类别只在 `tasks/` 一层生效

`topogym/tasks/` 按类别分子目录，路径即分类：

```text
topogym/tasks/<category>/<task>.py
```

其余各层——`verification/` `planning/` `generation/` `supervision/` `envs/` `demos/`——
**保持平铺**，与类别无关。

本文初稿主张完全不建目录，理由是「4 类 × 5 层 = 20 个目录，每格只有 1–2 个文件」。该理由只在
「五层都分类」的前提下成立；只分 `tasks/` 一层时不适用。改用目录的依据：

1. **代价实测很小。** `tasks/` 的 import 图是深度 2、无横向边：`__init__.py` → 9 个任务模块 →
   `_visuals.py`，任务模块之间零互相引用。迁移共改 17 行 import
   （`tasks/__init__.py` 9 行 + `verification/` 7 行 + `envs/maze_wall_removal_mdp.py` 1 行）。
   `planning/` `generation/` `supervision/` 对 `topogym.tasks` 零引用，完全不受影响。
2. **路径即分类，不会脱节。** 字段方案需要维护一张表，表与实现可能不一致；目录方案里分类就是
   文件位置，无法写错。`topogym/core/taxonomy.py` 的镜像表仅供不便 import Genesis 的调用方查询，
   并由 `python topogym/core/taxonomy.py` 校验其与目录一致。
3. **归类调整仍然便宜。** `peeling` 等待定项改类别 = 移动一个文件 + 改一行 import。
   包级 re-export（`from topogym.tasks import XxxSceneBuilder`）使 12 个调用方零改动。

初稿理由中仍然成立的一条：类别不进入 task_id 命名（见 §6）。

---

## 2. 类别标识规范

四个类别使用固定的 slug，同时作为 `topogym/tasks/` 的子目录名。全仓库（目录名、Python 常量、
YAML 字段、H5 attrs、bash 变量、文档表头）统一使用同一组字符串，不使用中文名、不使用序号作为
程序标识：

| 序号 | slug（= 目录名） | 中文名 | 英文名 | docx 章节 |
|---|---|---|---|---|
| C1 | `deformation` | 形状与自身层叠 | Deformable Shape & Self-Arrangement | 1 |
| C2 | `routing` | 路径与围绕 | Routing & Winding | 2 |
| C3 | `entangle` | 缠绕与互锁 | Entanglement & Interlocking | 3 |
| C4 | `connectivity` | 连接与可达性 | Connectivity & Accessibility | 4 |

另需一个非类别目录：

| slug | 含义 |
|---|---|
| `legacy` | 先于四分类存在、尚未在能力轴上定位的任务。含义是「未定位」而非「已废弃」；逐任务的实际状态见 `topogym/tasks/legacy/README.md`。不计入 benchmark 的按类统计。 |

序号 C1–C4 只用于文档中引用 docx 章节，不进入代码。

---

## 3. 单一事实来源：目录布局

**仲裁方是 `topogym/tasks/<category>/` 的目录布局本身。** 一个任务的类别就是它所在的子包，
没有可以写错的第二处记录。

`topogym/core/taxonomy.py` 是这个布局的**镜像查询层**，存在的唯一理由是：`topogym/tasks/__init__.py`
会 import Genesis，而 bash 与工具链只需要类别字符串。它只依赖 `pathlib`。

```python
CATEGORIES: dict[str, tuple[str, ...]] = {
    "deformation": (),
    "routing": ("bar_through_hole", "cable_routing", "rope_unwinding", "rope_winding"),
    "entangle": ("untangle", "untangle_continuous"),
    "connectivity": ("stacked_plate",),
}
LEGACY: tuple[str, ...] = ("swap", "onestroke", "maze_wall_removal", "peeling", "peeling_physical")

def category_of(task_id: str) -> str: ...
def tasks_in(category: str) -> tuple[str, ...]: ...
```

**一致性校验**：

```bash
python topogym/core/taxonomy.py     # 表 vs 目录；不一致时打印差异并非零退出
```

按文件而非 `-m` 运行：这样跳过 `topogym/core/__init__.py`（它 import omegaconf），在项目 venv 之外
也能跑。校验覆盖三种脱节：类别目录内容与表不符、任务出现在错误的类别目录、任务模块遗留在
`tasks/` 根目录未分类。

尚未落地、留待判定契约工作（§7 阶段 B）的三处引用：

1. **配置**：`configs/task_configs/<task>_topogym_tabletop_v1.yaml` 的 `task:` 段增加
   `invariant:` 字段（`category:` 无需写入 YAML —— 路径已经表达）。
2. **数据集**：`episode_dataset_writer.py` 在 `setup.attrs` 中于 `task_id` 之后增写
   `category`、`invariant`、`invariant_initial`、`invariant_final`。第一项来自
   `category_of()`，其余来自 verifier（见 §4）。
3. **bash 注册表**：四个脚本的 `declare -A TASKS` 支持按类别选择，例如
   `bash bash_scripts/tests/stability_sweep.sh @routing`；类别取自 `category_of()`。

---

## 4. 每类的判定契约

这是「工程上严格遵守分类」的实质内容。docx 对每个任务都写了「成功判定与防捷径」；下面把它固化为
`topogym/verification/<task>_verifier.py` 必须满足的形式约束。

### 4.0 所有类别共同要求

每个 `XxxPuzzleState` 除现有的 `is_terminal` 与 `to_info()` 外，增加一个属性：

```python
@property
def invariant_value(self) -> int | tuple[int, ...] | dict[str, float]:
    """This task's category invariant reading. Type is fixed per category; see §4.1-4.4."""
```

`to_info()` 必须包含 `invariant`（名称）与 `invariant_value`（读数）两个键。这样任意一条 episode
的 H5 都能回答「该任务的不变量在动作前后是什么」，不需要读 verifier 源码。

每个任务还须在注册表中声明 **contrast pair**：一条终点位置几乎相同但不变量不变（或变错方向）的
轨迹。它须可由 `generation/<task>_generator.py` 生成，并在单元测试中断言被判为失败。docx 每个任务
的「防捷径」段落即该 contrast pair 的设计说明。缺少可执行 contrast pair 的任务不得进入 benchmark
产物。

### 4.1 C1 `deformation`

- 不变量类型：`dict[str, float]`，多指标联合。
- 必须同时包含至少一个**守恒或结构指标**（层数、材料铺展长度、累计转角、自接触区域面积）与至少
  一个**形态指标**（高度场方差、覆盖 IoU、局部曲率上界）。
- `is_terminal` 必须是这些指标的合取，禁止单一位置阈值。
- 该类**没有整数拓扑不变量**，`to_info()` 中须显式标注 `"topological": false`，避免下游把它与
  C2/C3 的整数读数混为一类统计。

### 4.2 C2 `routing`

- 不变量类型：`int` 或 `tuple[int, ...]`（多障碍时为 winding vector）。
- 允许的 `invariant` 值：`winding_number` / `linking_number` / `threading_count`。
- 必须显式声明**闭合方案**（canonical closure）与**参考轴／参考面**，并写入 `to_info()`；
  不同闭合方案下 winding 数值不同，未声明则读数无定义。
- 必须显式声明 **gateway**（docx 2.4：柱顶是改变 winding 的唯一通道）。gateway 须是布局中一个
  具名实体或具名位形区域，写入 `TaskTaxonomy.gateway`。
- 必须有物理层复核：释放测试（docx 2.1）、张力传递测试（docx 2.2）或拖拽约束测试（docx 2.7）。
  几何读数与物理复核都通过才置 `task_success`；只有几何读数通过时记为 `geometry_only`。
- 方向敏感：绕反方向的读数为负值，与目标严格区分（docx 2.4/2.5 构成方向 contrast pair）。

### 4.3 C3 `entangle`

- 不变量类型：带号交叉序列，`tuple[tuple[int, int, int], ...]`（over 链号, under 链号, 符号），
  或其计数摘要。
- 允许的 `invariant` 值：`crossing_number` / `signed_crossing_sequence` / `self_crossing_number`。
- 必须显式声明**投影方向**与**固定边界条件**（docx 3.1：悬挂端点固定，排除「绕过自由端点」的
  平凡解）。边界条件不固定时交叉数无定义。
- over/under 符号必须与交叉数一起记录。docx 3.2（交换上下关系）的终态交叉数仍为 1，只有符号翻转；
  仅记录交叉数的实现无法表达该任务。
- 必须有物理层复核：分拉测试（docx 3.1/3.3）或分离后自由平移测试（docx 3.4）。
- 现有 `untangle_continuous_verifier.py` 的 `GeoCrossing` 已记录 `over_strand` / `under_strand` /
  `z_gap`，符合本契约；`is_terminal` 额外要求 `min_separation` 阈值，属于该任务在契约之上的加严，
  须在 `to_info()` 中与不变量读数分列（现已分列）。

### 4.4 C4 `connectivity`

- 不变量类型：`int`（连通分量数 β₀）或 `bool`（S–T 可达）或二者的组合 `dict`。
- 允许的 `invariant` 值：`component_count` / `st_reachable` / `free_space_component_count`。
- 必须声明连通性定义在**哪个对象的位形空间**上。docx 4.1/4.2/4.3 的连通性定义在**被操作物体的
  C_free** 上（机器人全程不接触小球），4.4 定义在**约束图**上。二者不可混用，须写入
  `to_info()` 的 `"space"` 键，取值 `c_free` 或 `constraint_graph`。
- 必须有物理层复核：shake test（docx 4.1）、贯穿到底判定（4.2）、S–T 弹珠测试（4.3）、
  提起测试（4.4）。docx 4.3 明确「S–T 弹珠测试本身就是任务」，即该类允许物理复核作为主判据。
- **随机化是本类防捷径的必要条件**：docx 4.1/4.3/4.4 的防捷径均依赖逐 episode 随机化初始相位或
  指令方向，使脚本化策略的期望成功率被固定在随机水平。因此 C4 任务在
  `generation/layout_randomization.py` 中**必须**注册随机化条目，未注册的 C4 任务不得进入
  benchmark 产物。其余类别的随机化为可选。

---

## 5. 现有任务的归类结论

### 5.1 已归类（5 个）

只有判据形态与该类判定契约（§4）方向一致的任务进入类别目录。

| task_id | 类别目录 | 依据 | 缺口 |
|---|---|---|---|
| `rope_winding` | `routing/` | 绳绕柱 0 → 2 圈 + 放置，对应 docx 2.4 | 尚未跑过 GPU 验收（判据与 oracle 已有离线 gate：`tests/check_rope_winding_geometry.py`） |
| `rope_unwinding` | `routing/` | 从柱上解下 start_turns ∈ {1,2,3} 圈绳 + 放置，对应 docx 2.5；rope_winding 的镜像，共用 planner / 判据 / demo 主体 | 尚未跑过 GPU 验收（离线 gate：`tests/check_rope_unwinding_geometry.py`） |
| `cable_routing` | `routing/` | 线缆绕过多个障碍桩布线，接近 docx 2.2 变体（**不是 2.4** —— 2.4 的「绕了几圈」由 `rope_winding` 实现，2026-08-11 起） | 无 verifier 文件；判定散在 `supervision/cable_routing.py`；判据是「在桩的哪一侧」签名而非 winding number |
| `untangle` | `entangle/` | 离散版交叉任务，对应 docx 3.1 | 无 verifier 文件 |
| `untangle_continuous` | `entangle/` | 连续绳交叉消除，对应 docx 3.1 | 缺物理层分拉复核 |
| `stacked_plate` | `connectivity/` | 缺口相位门控杆的下落通道，对应 docx 4.2 | 判据为位置阈值，未表达 C_free 连通性 |

`deformation/` 目录已建但为空。四类中这一类**当前实现数为 0**。

### 5.2 未归类（5 个，在 `legacy/`）

逐任务的实际状态见 `topogym/tasks/legacy/README.md`。归类结论与待决事项：

| task_id | 倾向类别 | 未归类的原因 |
|---|---|---|
| `swap` | 无（不考察四类空间关系） | 滑块重排。框架成型前的产物；仍是数据管线与 π0.5 冒烟的默认载体（见 `../il_adaptation/pi05_smoke_zh.md`），在另一个任务达到同等就绪度前继续承担该角色。 |
| `onestroke` | `connectivity`（`discrete_graph`） | 判据为网格图上两色区域的连通性，定义在预设离散图而非连续 C_free 上，与 §4.4 契约不同形。 |
| `maze_wall_removal` | `connectivity`（`discrete_graph`） | 同上。 |
| `peeling` | `connectivity`（`occlusion_order`）或 `deformation` | 当前判据（`verification/peeling_verifier.py:37` 读 `layout.higher_overlapping_films()`）是覆盖关系门控的顺序可达性，属可达性；若改造为可形变薄膜（docx 1「局部堆叠 → 铺展」）则属 `deformation`。 |
| `peeling_physical` | 随 `peeling` | `peeling` 的 PBD 物理执行层，共用其 planner / generator。 |

三项待决事项：

1. **`peeling` 的归类。** 建议保持当前实现语义、归入 `connectivity` 的遮挡顺序变体，另立新任务
   承担 `deformation`；因为把它改造成可形变膜等于重写该任务，不是归类动作。
2. **`discrete_graph` 变体是否计入 benchmark。** 建议保留 `onestroke` / `maze_wall_removal`，
   若日后进入 `connectivity/`，在产物中与 C_free 任务分列统计，不合并计算成功率。
3. **`swap` 是否长期保留。** 建议保留至另一任务达到「完全就绪」（有 episode split、录制稳定、
   replay 自校验通过），届时把管线默认任务切过去。

### 5.3 尚未实现的任务

docx 共 20 个任务小节，已实现 4 个（2.4 → `rope_winding`、2.5 → `rope_unwinding`、3.1 → `untangle` +
`untangle_continuous`、4.2 → `stacked_plate`），**尚未实现 16 个**：1.1–1.5、2.1–2.3、2.6、2.7、3.2–3.4、4.1、4.3、4.4。
（`cable_routing` 是 2.2 的变体但不完全对应，暂不计入已实现小节；`bar_through_hole` 同理对 2.3。）

2.5「从柱子上解下一圈绳」于 2026-08-26 作为 `rope_winding` 的镜像落地（`rope_unwinding`）：柱、端子、插头、
winding number 判据全部复用，改的是 oracle 的起止圈数（`winding.start_turns` → 0）与出生路线（`helix_around`）。

按类别分布（括号内为该类已实现数）：

| 类别目录 | 未实现 | docx 小节 |
|---|---|---|
| `deformation/` | 5（已实现 0） | 1.1–1.5 |
| `routing/` | 5（已实现 2） | 2.1、2.2、2.3、2.6、2.7 |
| `entangle/` | 3（已实现 1） | 3.2、3.3、3.4 |
| `connectivity/` | 3（已实现 1） | 4.1、4.3、4.4 |

逐项的落地计划（目标模块名、场景资产、依赖的建模能力、成本分档、推荐顺序）见
[`../tasks/task_environment_buildout_zh.md`](../tasks/task_environment_buildout_zh.md)。
其结论：17 个中有 7 个不需要任何新建模能力；三个能力缺口——闭合弹性环、求解器驱动的布料、
板上真实开孔——门住其余 9 个。

---

## 6. 目录与命名准则

### 6.1 目录布局

```text
topogym/tasks/
├── __init__.py          # 平铺 re-export 全部任务的公开名
├── _visuals.py          # 跨任务共享，留在根目录
├── deformation/         # 空，预留
├── routing/
├── entangle/
├── connectivity/
└── legacy/              # 含 README.md 说明每个任务的实际状态
```

`module_boundaries_zh.md` §5 的依赖方向不变。类别目录只加在 `tasks/` 内部，不改变层间关系。

**~~`prototypes/` 保持平铺~~ —— 2026-08-10 推翻。** 原理由是「分类会改掉全部已文档化的
`python -m prototypes.X` 命令、四个 bash 注册表与 `cli_commands.txt`，且 demo 是用户入口而非
能力载体」。

改判的原因：那份代价确实付了（105 处引用、26 个文件），但 demo 平铺到 14 个文件之后，
「这个 demo 属于哪个任务、是不是主线」只能靠文件名猜。目录现在是 `demos/`，
分类与 `tasks/` 对齐：

```
demos/
├── routing/          # cable_routing, rope_winding, rope_unwinding, bar_through_hole
├── entangle/         # untangle, untangle_continuous
├── connectivity/     # stacked_plate
└── legacy/           # maze_wall_removal, onestroke, peeling, swap
```

`tasks/deformation/` 现在是空的，`demos/` 里不建对应目录。
非 demo 的两个文件移出：`fem_ipc_rope_spike.py` 进 `scripts/`（它自称诊断工具），
`record_physical_demos.py` 进 `demos/legacy/`（注册表里只有 legacy 三个任务）。
2026-08-11 修正：`scripts/` 只留产出工件的工具，检查与测量类移入新建的 `tests/`，
`fem_ipc_rope_spike.py` 随之进 `tests/`。`record_physical_demos.py` 已随 legacy demo 删除。

**新增类别目录时**同步在 `topogym/core/taxonomy.py` 的 `CATEGORIES` 登记，并跑
`python topogym/core/taxonomy.py` 确认表与目录一致。

### 6.2 import 约定

调用方走包级 re-export，不写类别段——这样任务改类别时调用方零改动：

```python
from topogym.tasks import StackedPlateSceneBuilder
```

只有需要具体 Scene/Layout 类型做标注的 verifier / env 走深层 import：

```python
from topogym.tasks.connectivity.stacked_plate import StackedPlateScene
```

### 6.3 命名准则

**task_id 不编码类别。** 命名仍为描述功能的 snake_case（如 `rope_through_hook`、
`ring_transfer`），不写成 `routing_rope_through_hook`。类别由所在目录表达。
理由：名称表达功能，类别是可变的元数据，归类调整时不应触发重命名。

**同一类别下的任务命名保持形式一致**，便于 grep：

| 类别 | 命名形式 | 示例 |
|---|---|---|
| `deformation` | `<物体>_<形变动作>` | `cloth_fold`、`hose_bend_u`、`tablecloth_spread` |
| `routing` | `<物体>_<关系>_<对象>` | `rope_through_hook`、`cable_through_port`、`ring_transfer` |
| `entangle` | `<关系动作>_<结构>` | `untangle_continuous`、`swap_crossing_sign`、`unlink_c_ring` |
| `connectivity` | `<门控动作>_<被影响对象>` | `stacked_plate`、`gate_close_cage_ball`、`diverter_route_ball` |

**contrast pair 任务成对命名。** docx 2.4/2.5 是加圈与解圈，3.1/3.2 是消除交叉与翻转符号。
成对任务共用词干，用后缀区分方向：`rope_wind_post` / `rope_unwind_post`。

**文档位置。**
- 任务设计说明（场景、动作、状态变化、判定、防捷径）：`docs/develop/tasks/<task>.md`，
  索引 `docs/develop/tasks/README.md` 按四类分组。
- 任务的物理调参与 debug 记录：沿用 `docs/develop/physics/`（大任务族已有子目录）。
- 二者不合并：前者是设计契约，随类别变化；后者是实现记录，随物理引擎变化。

**`TopoGym_tasks.docx` 转为 markdown。** 该文件是二进制，无法 grep、无法 diff、无法在 review 中
逐行讨论。建议将正文转入 `docs/develop/tasks/README.md`，图片存 `docs/develop/tasks/figures/`，
docx 保留为原始来源。

---

## 7. 落地动作清单

按依赖顺序排列，每步可独立提交。

### 阶段 A：建立类别轴（不改任何判定逻辑）—— 已完成 2026-08-04

1. ✅ `topogym/tasks/` 重组为 `deformation/` `routing/` `entangle/` `connectivity/` `legacy/`；
   `_visuals.py` 留在根；17 行 import 更新。
2. ✅ 新建 `topogym/core/taxonomy.py`：`CATEGORIES` / `LEGACY` / `category_of()` / `tasks_in()`
   + 目录一致性校验。
3. ✅ π0.5 管线通用化：`export_h5_lerobot.py`（`repo_id` 从 H5 的 `task_id` 派生）、
   `register_openpi_config.py`（按 config 名派生起止 marker，多任务 block 共存）、
   `pi05_smoke.sh`（任务名作位置参数，产物按任务分目录）。
4. ⬜ `episode_dataset_writer.py` 在 `setup.attrs` 增写 `category`。
5. ⬜ 四个 bash 注册表增加 `@<category>` 选择语法。

### 阶段 B：补齐判定契约

6. 新建 `topogym/verification/cable_routing_verifier.py`：把
   `supervision/cable_routing.py` 中 `endpoint_route_ok()` / `rope_wrap_metrics()` 的**判定部分**
   迁入，输出整数 winding signature；`supervision/` 只保留打印与运行期监控
   （`print_routing_verification` / `print_phase_routing_metrics`）。
   这一步同时修复对 `module_boundaries_zh.md` §1 的现存违反。
7. 各 `XxxPuzzleState` 增加 `invariant_value` 属性，`to_info()` 增加 `invariant` /
   `invariant_value` 键。
8. `stacked_plate_verifier.py` 的判据由位置阈值改为 C_free 通道存在性读数
   （两盘缺口相位是否同时对齐下落线），`to_info()` 增加 `"space": "c_free"`。
9. `untangle` 的定位确认：补 verifier 或退役。

### 阶段 C：补齐防捷径

10. C4 任务在 `generation/layout_randomization.py` 中补齐随机化条目。当前
    `_REGISTRY` 只覆盖 `untangle` / `cable_routing` / `stacked_plate` / `peeling` 四项，
    且 `stacked_plate` 只随机化初始角度，未随机化「哪一层需要转」这一指令方向。
11. 每个任务补一条 contrast pair 生成路径与对应单元测试。
12. `docs/develop/tasks/` 建立，docx 正文转入。

### 阶段 D：C1 类立项

13. C1 当前实现数为 0。从 docx 1.1–1.5 中选一个作为首个 C1 任务落地，
    同时确定可形变布料／软管在 Genesis 中的建模方案（现有 PBD 绳管方案是否可复用）。

---

## 8. 新增任务准入检查表

在 `module_boundaries_zh.md` §6 的 10 步之上，增加以下 6 项。任一项不满足的任务不得进入
benchmark 产物。

1. 任务模块放在 `topogym/tasks/<category>/` 下，并在 `topogym/core/taxonomy.py` 的 `CATEGORIES`
   登记；`python topogym/core/taxonomy.py` 通过。归类不确定时先放 `legacy/` 并在其 README 记状态，
   不要猜一个类别塞进去。
2. `invariant` 取值在该类别的允许集合内（§4.1–4.4），且 verifier 的 `invariant_value`
   返回类型与该类别规定一致。
3. verifier 的 `to_info()` 包含该类别要求的声明字段：C1 的 `topological: false`、
   C2 的闭合方案与参考轴、C3 的投影方向与边界条件、C4 的 `space`。
4. 存在物理层复核（C1 除外），且几何读数与物理复核分别记录。
5. 存在可执行的 contrast pair：终点位置相近、不变量不变或变错方向的轨迹可被生成，
   且单元测试断言其被判失败。
6. C4 任务已在 `generation/layout_randomization.py` 注册随机化条目。

---

## 9. 与现有文档的关系

| 文档 | 关系 |
|---|---|
| `module_boundaries_zh.md` | 层轴规矩。§4 文件命名已改为 `tasks/<category>/<task>.py`，§6 清单第 1 步已同步。本文 §4 判定契约是对其 §1「verification 层放什么」的按类细化，§8 是对其 §6 清单的扩展。 |
| `../modules/module_tasks.md` | `topogym/tasks` 的逐文件说明，已按新目录重写。 |
| `mdp_state_terminal_zh.md` | 终态语义约定。类别决定不变量形式，终态仍由 verifier 判、由 envs 封装，不变。 |
| `config_reference_zh.md` | 阶段 B 落地时需补充 `task.invariant` 字段的说明。 |
| `../data_pipeline/h5_data_format_zh.md` | 阶段 A 第 4 步落地时需补充 `setup` attrs 中新增的 `category` 等字段。 |
| `../data_pipeline/robomme_benchmark_deliverables_zh.md` | 按类聚合的产物统计以本文 §5 的归类为准，`legacy/` 下的任务与 `discrete_graph` 变体分列。 |
| `../il_adaptation/pi05_smoke_zh.md` | π0.5 冒烟链路已任务参数化，默认任务仍为 `swap`（见 §5.2）。 |
