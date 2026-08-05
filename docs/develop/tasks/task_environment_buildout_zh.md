# 任务环境落地清单与第一步选择（dev-log）

> 日期：2026-08-05
> 上游：`../TopoGym_tasks.docx`（20 个任务的场景／动作／判定／防捷径设计）
> 配套：`../framework/task_taxonomy_zh.md` §5.3（已实现 3 个、未实现 17 个的按类分布）
>
> 本文回答两个问题：每个类别子目录下要实现哪些 docx 任务、各自需要什么环境；以及第一步做哪几个
> 成本最低。逐任务的成本判断基于 2026-08-05 对现有建模能力的一次盘点（§1），结论随能力变化。

---

## 0. 结论摘要

- 17 个未实现任务中，**7 个不需要任何新的物理建模能力**，其中 2 个可直接复用现有场景与原语。
- **3 个新能力**门住其余任务：闭合弹性环（3 个任务）、求解器驱动的布料（4 个任务）、板上真实开孔
  （2 个任务，可用凸块组合绕开）。
- 推荐第一步：**`swap_crossing_sign`（docx 3.2）与 `rope_unwind_post`（docx 2.5）**。两者各自复用
  一个已跑通的场景构建器与运动原语，主要新增工作是配置与 verifier，且分别落在 `entangle/` 与
  `routing/` 两个类别下。
- `deformation/` 目录当前为空。docx 1.4（软管弯成 U 形）**不需要布料**——软管即开放弹性管，与现有
  PBD 绳管线同构。它是让 `deformation/` 脱离空目录状态的最短路径，无需先解决布料求解。

---

## 1. 现有建模能力盘点

### 1.1 已具备

| 能力 | 实现位置 | 说明 |
|---|---|---|
| 刚体基元 | Genesis `gs.morphs.{Plane,Box,Cylinder,Sphere,Mesh,URDF,MJCF}` | `Sphere` 存在于安装的 Genesis（`morphs.py:382`）但仓库内尚无使用 |
| PBD 弹性管（开放两端） | `world/rope.py:165` `make_elastic_tube_mesh` + `:414` `elastic_material` + `:431` `tube_morph` | 沿任意开放三维中心线扫掠，parallel-transport 帧 |
| 中心线生成 | `world/rope.py:71` `sample_polyline`、`:93` `catmull_rom_centerline` | 任意折线／样条，非周期 |
| 回转体网格 | `world/rope.py:455` `revolve_profile` | 由 `(z, r)` 剖面绕轴回转，两端封盖 |
| 粒子锚定 | Genesis 实体方法 `fix_particles` / `fix_particles_to_link` | 用例见 `tasks/entangle/untangle.py:272`、`tasks/routing/cable_routing.py:370` |
| 铰链关节 | `tasks/connectivity/stacked_plate.py:95` `_write_disk_urdf` | 程序化写 URDF，`type="continuous"`、轴 Y、单自由度 |
| 桌面基座与相机 | `world/tabletop.py:109` `StandardTabletopSceneBuilder` | 地面／桌／装饰框／机器人／相机一次建好 |
| PBD 粒子-平面摩擦 | `world/rope.py:276` `TabletopParticleFriction` | 补 Genesis 静止绳几乎无摩擦的问题 |
| 刚体顶抓放置 | `primitives/pick_place.py:42` `PickPlacePrimitive` | 13 阶段（`:51-65`），含抓取／提升／放置容差校验 |
| 经刚体手柄拖拽 PBD | `primitives/pbd_handle_drag.py:73` `PBDHandleDragPrimitive` | 多段航点拖拽 + 跟随误差中止 |
| 插入即锁定 | `primitives/connector_latch.py:18` `ConnectorLatch` | 进入捕获区后把手柄吸附到固定位姿 |
| 运动学焊接 | `primitives/attachment.py` `RigidAttachment` / `ParticleAttachment` | 把实体或粒子组绑到运动父体 |

### 1.2 尚不具备

| 缺口 | 证据 | 门住的任务 |
|---|---|---|
| **闭合弹性环** | `make_elastic_tube_mesh` 三处开放假设：侧面四边形只连 `i→i+1`（`rope.py:231`）、两端无条件加圆盘封盖（`rope.py:239-247`）、端点用单侧差分且接缝无扭转闭合（`rope.py:190-202`）。`catmull_rom_centerline` 用反射而非环绕外推（`rope.py:115`）。仓库内 `torus` / `periodic` / 闭合曲线零命中 | 2.6、2.7、3.3 |
| **求解器驱动的布料** | `gs.materials.PBD.Cloth` 实体确实创建（`tasks/legacy/peeling_physical.py:669`），但 `PeelingKinematicSheetDriver`（`:401`）用解析式逐帧写 `set_particles_pos`（`:351-358`），布面由脚本驱动。`configs/` 下无任何 `cloth` 配置块，该路径当前不可运行 | 1.1、1.2、1.3、1.5 |
| **板上真实开孔** | `untangle` 的「孔」是 1mm 高、`collision: false` 的贴片圆盘（`tasks/entangle/untangle.py:340-346`，配置 `untangle_topogym_tabletop_v1.yaml:25-28`），板体是无孔实心 Box（`:319-323`）。`stacked_plate` 的缺口只进 URDF `<visual>`（`stacked_plate.py:143`），`<collision>` 是完整圆柱（`:137`） | 2.2、2.3 |
| **重力下自行运动、机器人不接触的物体** | 仓库内无此类任务。`stacked_plate` 的杆是 `fixed=True` 且 `collision: false` 的装饰轴（`stacked_plate.py:377-396`），不下落 | 4.1、4.3 |
| **钩状／悬挑几何** | `revolve_profile` 只能作回转体，钩不是回转体。但 `make_elastic_tube_mesh` 是通用扫掠器，沿 L／J 形中心线扫掠即可得钩的网格 | 2.1 |

**非凸碰撞体的既有解法**：仓库一贯用「多个凸块组合」而非单个非凸体。`cable_routing.py:810-818`
的走线柱即拆成柱身 + 锥形底座 + 顶盖三个实体，其 docstring 记录了理由（合成单体后凸包会撑大绕线
半径）。板上开孔可沿用此法：矩形孔 = 四条 Box 围成的框，无需真正的布尔开孔。

---

## 2. 逐任务环境需求

成本档定义：**低** = 不需要新建模能力，且可复用某个已有场景构建器；**中** = 不需要新建模能力，
但场景资产需新建；**高** = 需要新建模能力但无求解器风险；**阻塞** = 依赖 §1.2 的缺口。

### 2.1 `deformation/` —— 5 个任务，docx 1.1–1.5

| docx | 建议模块 | 场景资产 | 建模能力 | 成本档 |
|---|---|---|---|---|
| 1.4 软管弯成 U 形 | `hose_bend_u.py` | 顶部导轨、两个向下接口 P1/P2、软管 | **PBD 弹性管（已有）**；接口可复用 `rope_flush_port` / `rope_fixed_terminal` 剖面；抓取端复用 `rope_endpoint_connector` | 中 |
| 1.1 对折／折角 | `cloth_fold.py` | 方形软布、工作面 | 求解器驱动布料 | 阻塞 |
| 1.2 展开单个褶皱 | `cloth_unfold_pleat.py` | 布带 + 预置褶皱初态 | 同上，且需要「三层重叠」的初态构造 | 阻塞 |
| 1.3 展开自身卷曲的布带 | `strap_unroll.py` | 布带 + 多层筒卷初态 | 同上，且需要自接触稳定 | 阻塞 |
| 1.5 铺展桌布并形成目标垂坠 | `tablecloth_spread.py` | 桌布、桌沿 | 同上，且需要布料跨桌沿垂坠 | 阻塞 |

**1.4 的关键性**：docx 把它归入类别 1，其状态变化是「近似直线 → U 形垂坠」，属可形变体整体构型
变化。但它的物理载体是软管，即开放弹性管，与 `cable_routing` / `untangle_continuous` 用的
PBD 管线同构。因此 `deformation/` 的第一个实现不必等布料求解就绪。新增工作集中在 verifier：
沿管曲率符号单一性、kink 检测（局部曲率超阈值）、最低点位于两端之间——三者都是对中心线折线的
几何计算，而 `strand_centerline` 一类的采样接口已存在。

### 2.2 `routing/` —— 6 个未实现，docx 2.1–2.3、2.5–2.7（2.4 已实现为 `cable_routing`）

| docx | 建议模块 | 场景资产 | 建模能力 | 成本档 |
|---|---|---|---|---|
| 2.5 从柱上解下一圈绳（1→0） | `rope_unwind_post.py` | 与 2.4 完全相同：立柱 + 锚点 + 绳 | **全部已有**。复用 `CableRoutingSceneBuilder` 的柱与锚，初态改为预绕一圈的螺旋中心线（`sample_polyline` 接受任意三维折线），动作复用 `PBDHandleDragPrimitive` | 低 |
| 2.3 横杆穿过孔（刚体） | `bar_through_hole.py` | 竖直面板（四条 Box 围成矩形孔）、刚性横杆（Cylinder） | 全部为刚体基元；动作复用 `PickPlacePrimitive` | 中 |
| 2.2 线缆穿过护线孔 | `cable_through_port.py` | 同上面板 + PBD 线缆 + 左侧锚点 | 面板同 2.3；线缆复用现有 PBD 管线 | 中 |
| 2.1 绳端穿过挂钩 | `rope_through_hook.py` | 顶梁、J 形挂钩、配重（购物袋）、绳 | 挂钩用 `make_elastic_tube_mesh` 沿 J 形中心线扫掠得网格，碰撞用多段凸块组合 | 中 |
| 2.6 绳圈从柱 A 转移到柱 B | `ring_transfer_post.py` | 两根立柱 + 闭合弹性圈 | 闭合弹性环 | 阻塞 |
| 2.7 闭合环同时围住两柱 | `ring_enclose_two_posts.py` | 同上 | 闭合弹性环 | 阻塞 |

**2.5 与 2.4 的配对关系**：docx 2.4/2.5 构成方向敏感的 contrast pair（加圈／解圈，几乎镜像的
轨迹）。按 `task_taxonomy_zh.md` §6.3 的成对命名准则，二者应共用词干
（`rope_wind_post` / `rope_unwind_post`）。现有实现名为 `cable_routing`，与该准则不一致；
**不重命名 `cable_routing`**（会波及 4 个 bash 注册表、episode split、随机化注册表与全部文档），
在本文与两个任务的配置注释中记录配对关系即可。

### 2.3 `entangle/` —— 3 个未实现，docx 3.2–3.4（3.1 已实现为 `untangle` + `untangle_continuous`）

| docx | 建议模块 | 场景资产 | 建模能力 | 成本档 |
|---|---|---|---|---|
| 3.2 交换两根线的上下关系 | `swap_crossing_sign.py` | 与 3.1 完全相同：两根线缆、悬挂端固定、一处交叉 | **全部已有**。`untangle_continuous` 的冻结配置正是 `n_strands: 2` / `braid.length: 1`，即恰好一处交叉（配置 `:47`、`:55`，注释记录 seed 0–3 上 `crossing_count` 均为 1） | 低 |
| 3.4 C 形环从固定圆环中解开 | `unlink_c_ring.py` | 支架、固定闭合刚性圆环、C 形开口环 | 刚体互锁。圆环／C 环用多段短圆柱沿圆周组合（沿用 §1.2 的凸块组合解法），无新求解器 | 高 |
| 3.3 8 字绳圈改成 O 形 | `band_untwist.py` | 壁面挂销 + 闭合弹性带 | 闭合弹性环 | 阻塞 |

**3.2 是全表成本最低的任务**。场景、原语、配置结构全部与 `untangle_continuous` 相同，差别只在
目标与判据：终态交叉数仍为 1，翻转的是 over/under 符号。而
`verification/untangle_continuous_verifier.py:28` 的 `GeoCrossing` **已经记录**
`over_strand` / `under_strand` / `z_gap`，即符号信息已在状态里，新 verifier 只需在同一状态上换一个
终态谓词。docx 亦指出该任务对纯几何模仿策略是天然对抗样本：初末端几何位置几乎相同，只有轨迹
同伦类不同，仅学「终点构型」的策略在此获得零监督信号。

### 2.4 `connectivity/` —— 3 个未实现，docx 4.1、4.3、4.4（4.2 已实现为 `stacked_plate`）

| docx | 建议模块 | 场景资产 | 建模能力 | 成本档 |
|---|---|---|---|---|
| 4.1 关闭挡板困住移动小球 | `gate_cage_ball.py` | 带开口的围栏（Box 组合）、滚动小球（Sphere）、挡板（Box） | 全部为刚体基元。需要仓库首个 `gs.morphs.Sphere` 与首个「机器人不接触、自行运动」的物体；挡板插入复用 `PickPlacePrimitive` | 中 |
| 4.4 旋转连接杆合并两个组件 | `linkbar_merge_components.py` | 两组刚性杆件、铰接连接杆、两个同款插口 | 铰链复用 `_write_disk_urdf` 的 URDF 写法（需泛化几何与轴）；插接锁定复用 `ConnectorLatch`；判据为约束图 union-find | 高 |
| 4.3 旋转分流板改变小球出口 | `diverter_route_ball.py` | 入口竖槽、分岔结构、左右出口、枢轴分流板、小球 | 同 4.1 的小球 + 同 4.4 的铰链 | 高 |

**4.1 与 4.3 引入的共同新要素**：机器人全程不接触被判定物体，拓扑操作施加在另一个物体的自由
空间上。这是与现有全部任务本质不同的一点，也是 `task_taxonomy_zh.md` §4.4 要求 C4 任务必须注册
随机化条目的原因——docx 4.1 的防捷径依赖插板时机随机化，4.3 依赖初始板向与指令方向逐 episode
随机组合，使「看到开口就插」「看到板就转固定方向」的脚本策略期望成功率被固定在随机水平。

---

## 3. 三个阻塞能力

| 能力 | 门住 | 工作内容 | 风险 |
|---|---|---|---|
| 闭合弹性环 | 2.6、2.7、3.3 | 为 `make_elastic_tube_mesh` 加周期模式：接缝处补 `(N-1)→0` 侧面带、跳过两端封盖、端点改中心差分、接缝作扭转闭合修正；`catmull_rom_centerline` 加环绕外推 | 中。PBD 侧不是障碍——`tube_morph` 用 `force_retet=True` 对任意水密闭合网格作四面体化（`rope.py:442`），环面在原理上可直接作为 `PBD.Elastic` 载入。风险集中在接缝处的扭转失配与自接触稳定性 |
| 求解器驱动的布料 | 1.1、1.2、1.3、1.5 | 让 `PBD.Cloth` 真正由求解器推进：`PeelingKinematicSheetDriver` 目前逐帧覆写粒子位置；需要一条不经该 driver 的路径，并补 `configs/task_configs/` 下的 cloth 配置块（当前不存在） | 高。布料自接触、层叠与抓取稳定性均未在本仓库验证过；`peeling_physical` 走脚本驱动本身即是回避该问题的结果 |
| 板上真实开孔 | 2.2、2.3 | 用四条 Box 围成矩形孔（凸块组合），不做布尔开孔 | 低。与 `cable_routing.py:810-818` 走线柱的既有解法同构 |

第三项已在 §2 中按「中」档计入 2.2／2.3，不单独立项。

---

## 4. 成本分档汇总

| 档 | 任务 | 类别 |
|---|---|---|
| 低（复用现有场景 + 原语） | 3.2 `swap_crossing_sign`、2.5 `rope_unwind_post` | entangle、routing |
| 中（新场景资产，无新建模能力） | 1.4 `hose_bend_u`、2.3 `bar_through_hole`、2.2 `cable_through_port`、2.1 `rope_through_hook`、4.1 `gate_cage_ball` | deformation、routing ×3、connectivity |
| 高（新几何或新机构，无新求解器） | 3.4 `unlink_c_ring`、4.4 `linkbar_merge_components`、4.3 `diverter_route_ball` | entangle、connectivity ×2 |
| 阻塞 | 2.6、2.7、3.3（闭合环）；1.1、1.2、1.3、1.5（布料） | routing ×2、entangle、deformation ×4 |

不需要新建模能力的任务共 7 个（低 2 + 中 5），覆盖全部四个类别。

---

## 5. 推荐的第一步

**做 3.2 `swap_crossing_sign` 与 2.5 `rope_unwind_post` 两个。**

选择理由：

1. 两者是唯二可以直接复用一个已跑通场景构建器的任务，主要新增工作是配置与 verifier，不新建场景
   资产、不新增原语。
2. 两者分别落在 `entangle/` 与 `routing/`，一次验证两个类别目录下「新增任务」这条路径是否顺畅。
3. 两者都是 docx 明确设计的 contrast pair 的另一半（3.2 对 3.1，2.5 对 2.4），能直接检验
   `task_taxonomy_zh.md` §4 的判定契约是否可执行——尤其是 §4.3 要求的 over/under 符号记录，
   3.2 是唯一必须依赖该字段才能表达的任务。
4. 两者都不触及 §3 的三个阻塞能力，因此第一步的结论不会被建模风险污染。

**其后的第二批**建议为 1.4 `hose_bend_u` 与 2.3 `bar_through_hole`：前者让 `deformation/`
不再为空且不需要布料，后者建立「凸块组合开孔」这一被 2.2 复用的资产做法，且是纯刚体、无 PBD
稳定性风险。

> 若优先级改为「先把物理风险压到最低」，另有一条纯刚体路线：5 个不含任何可形变体的任务
> （2.3、4.1、4.4、4.3、3.4），做完可让 `connectivity/` 的四个 docx 任务全部落地。
> 见 [`rigid_first_track_zh.md`](rigid_first_track_zh.md)。两条路线不冲突，可并行。

### 5.1 第一步的文件清单

单个「场景 + 判定，无 oracle、无 RL」的任务最小文件集为 4 项（依据
`../framework/module_boundaries_zh.md` §6，其中第 5/6/7 项标注为条件项）：

```text
topogym/tasks/<category>/<task>.py              # Layout / Scene / SceneBuilder
topogym/verification/<task>_verifier.py         # PuzzleState + PuzzleEvaluator
configs/task_configs/<task>_topogym_tabletop_v1.yaml
两处登记：topogym/core/taxonomy.py 的 CATEGORIES + topogym/tasks/__init__.py 的 re-export
```

要能录数据还需 `prototypes/<task>_physical_<机构>_demo.py` 与四个 bash 注册表各一行
（`record_all_tasks.sh` / `collect_and_view.sh` / `stability_sweep.sh` / `verify_dataset_recording.sh`
只接受 demo 模块路径，跳过 demo 等于跳过全部四项）。

对这两个任务的具体预期：

| | `swap_crossing_sign` | `rope_unwind_post` |
|---|---|---|
| 场景构建器 | 可先直接复用 `UntangleContinuousSceneBuilder`，仅新增配置；若后续发散再拆出独立模块 | 复用 `CableRoutingSceneBuilder` 的柱与锚，新增预绕螺旋初态的中心线构造 |
| verifier | 新增。在 `GeoCrossing` 已有的 `over_strand` / `under_strand` 上换终态谓词：交叉数仍为 1 且符号相对初态翻转 | 新增。winding number 由 1 变 0，需先声明闭合方案与参考轴（§4.2 要求） |
| 原语 | `PBDHandleDragPrimitive`，无改动 | `PBDHandleDragPrimitive`，无改动 |
| 主要风险 | 「翻转符号」要求末端回到原位附近，对拖拽轨迹的精度要求高于 3.1 的「移开」 | 预绕初态需静置稳定；螺旋中心线的 PBD 初始化此前未验证过 |
| 待定 | 是否独立成模块，取决于配置发散程度 | 与 `cable_routing` 的命名配对（见 §2.2） |

### 5.2 单任务成本基线

按仓库内既有任务的实测行数（用于估算，不作为目标）：

| 文件 | 区间 | 备注 |
|---|---|---|
| `tasks/<category>/<task>.py` | 269–816 | 下界 `legacy/swap.py`，上界 `entangle/untangle_continuous.py`；其中约 35 行是每个任务都逐字重复的坐标系转换块 |
| `verification/<task>_verifier.py` | 48–237 | 下界 `stacked_plate_verifier.py`（仅委托给 layout），上界 `untangle_continuous_verifier.py`（含约 105 行交叉检测几何） |
| `configs/task_configs/<task>_*.yaml` | 106–419 | 上界的 419 行中仅约 115 行为实际配置，其余为 PBD 调参记录 |
| `prototypes/<task>_*_demo.py` | 329–658 | 其中约 150 行为各 demo 间重复的 CLI/bootstrap |
| `generation/<task>_generator.py` | 121–125 | 约 82% 为逐字重复的样板（前 36 行在 7 个 generator 中完全相同） |

`untangle_continuous` 作为最近一个完整落地的任务，含两个 demo 的总量为 2692 行。

---

## 6. 未决事项

1. `swap_crossing_sign` 是否独立成模块，还是作为 `untangle_continuous` 的一个目标变体。前者符合
   「一个任务一个文件」的现有约定，后者省掉约 800 行重复的场景构建代码。倾向前者，但需先看配置
   实际发散多少。
2. 闭合弹性环与布料两项能力的先后。闭合环门住 3 个任务且风险为中，布料门住 4 个任务且风险为高；
   按「解锁数 ÷ 风险」应先做闭合环。
3. docx 正文尚未转为 markdown。该文件为二进制，无法 grep、无法 diff、无法在 review 中逐行讨论，
   而本文与 `task_taxonomy_zh.md` 均把它作为设计契约引用。
