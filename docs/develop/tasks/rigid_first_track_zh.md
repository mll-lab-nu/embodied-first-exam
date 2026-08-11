# 纯刚体任务轨道（工程计划）

> 日期：2026-08-05
> 上游：`../TopoGym_tasks.docx`
> 配套：[`task_environment_buildout_zh.md`](task_environment_buildout_zh.md)（17 个未实现任务的完整
> 清单与成本分档）、`../framework/task_taxonomy_zh.md`（四类定义与判定契约）
>
> 本文从 17 个未实现任务中筛出**不含任何可形变体**的 5 个，给出实施顺序、共享基建与逐任务的环境
> 需求。判据：场景内全部实体为 `gs.morphs.{Box,Cylinder,Sphere,Mesh,URDF}` + `gs.materials.Rigid`，
> 不出现 PBD 粒子或布料。

---

## 0. 结论摘要

- 纯刚体的未实现任务共 **5 个**：docx 2.3、3.4、4.1、4.3、4.4。
- 建议顺序：**2.3 → 4.1 → 4.4 → 4.3 → 3.4**。前四个之间存在基建复用关系，3.4 单独成本最高。
- 这条轨道做完，`connectivity/` 将**四个 docx 任务全部落地**（4.1–4.4），成为第一个完整的类别。
- 这条轨道**覆盖不到 `deformation/`**——该类别按定义即可形变体，无刚体版本。详见 §5。

---

## 1. 先做纯刚体的依据

### 1.1 仓库已有同方向的书面策略

`../data_pipeline/dataset_generation_prerequisites_zh.md:72`：

> **W3 录制器先在 swap 上做对，然后「补 split → 录」可以按刚体→PBD 的风险梯度逐个任务铺开**，
> 不必等所有任务都稳定。

同文 `:68-69` 把待录任务按风险排为：刚体（maze / onestroke / stacked_plate）→ untangle（中风险）
→ cable_routing / peeling（最高风险，放最后）。本文只是把同一梯度延伸到**新任务的实现顺序**。

### 1.2 风险差异的证据

| 观察 | 证据 |
|---|---|
| 稳定性 sweep 只覆盖含 PBD 的任务 | `bash_scripts/tests/stability_sweep.sh` 的 `ORDER` 为 untangle / untangle_continuous / cable_routing / stacked_plate / peeling；纯刚体的 swap 不在其中 |
| PBD 任务各自有独立的物理 debug 记录 | `../physics/cable_routing/`、`../physics/untangle/debug-log/`、`../physics/peeling/` 各成子目录 |
| 唯一被标为「完全就绪」的任务是刚体任务 | `../data_pipeline/dataset_generation_prerequisites_zh.md:45`（swap） |
| PBD 侧存在专门补写的物理 | `world/rope.py:276` `TabletopParticleFriction`，因 Genesis 的形变体-刚体摩擦随法向速度缩放，静止绳几乎无摩擦（`rope.py:281-290`） |

刚体路径已被 swap / onestroke / maze_wall_removal / stacked_plate 四个任务走通，没有遗留的求解器
问题。

### 1.3 与 `task_environment_buildout_zh.md` §5 推荐的关系

该文推荐第一步为 3.2 `swap_crossing_sign` + 2.5 `rope_unwind_post`，理由是二者可整体复用已跑通的
场景构建器，新增代码最少。两条路线的取舍：

| | 纯刚体轨道（本文） | 3.2 + 2.5（PBD 复用） |
|---|---|---|
| 物理风险 | 无 PBD 稳定性风险 | 复用已调稳的场景，风险低但非零 |
| 新增代码量 | 每个任务需新建场景资产 | 主要是配置与 verifier |
| 类别覆盖 | 完成 `connectivity/`（4/4） | 各推进 `entangle/` 与 `routing/` 一个 |
| 判定契约检验 | 覆盖 §4.4（C_free 连通性、约束图） | 覆盖 §4.3 的 over/under 符号——该字段目前只有 3.2 必须依赖 |

两者不冲突，可并行。本文不撤销该推荐，只补一条风险更低、但单任务代码量更大的路线。

---

## 2. 五个纯刚体任务

| docx | 建议模块 | 类别目录 | 一句话场景 | 成本 |
|---|---|---|---|---|
| 2.3 | `bar_through_hole.py` | `routing/` | 刚性横杆水平插入竖直面板上的孔 | 低 |
| 4.1 | `gate_cage_ball.py` | `connectivity/` | 在正确时机把挡板插入围栏开口，困住滚动小球 | 中 |
| 4.4 | `linkbar_merge_components.py` | `connectivity/` | 旋转铰接连接杆扣入插口，合并两个刚体组件 | 中 |
| 4.3 | `diverter_route_ball.py` | `connectivity/` | 旋转分流板改变小球从哪个出口离开 | 中 |
| 3.4 | `unlink_c_ring.py` | `entangle/` | C 形开口环从固定闭环中沿开口方向抽出 | 高 |

docx 对 2.3 与 3.4 都明确标注了「刚体」定位：2.3 是「把柔性线缆换成刚性横杆，验证 threading 能力
不限于柔体」，3.4 是「纯刚体的 embedding topology 任务，直接说明拓扑操作不限于柔性物体」。

---

## 3. 实施顺序与共享基建

```text
2.3 bar_through_hole
      └── 凸块组合开孔面板 ──────────────► 后续 2.2 cable_through_port（PBD 版）复用

4.1 gate_cage_ball
      ├── Sphere + 自由滚动物体 ─────┐
      └── shake test（物理层复核）    │
                                      ├──► 4.3 diverter_route_ball
4.4 linkbar_merge_components          │
      ├── 泛化的 URDF 铰链发射器 ─────┘
      └── 约束图 union-find verifier

3.4 unlink_c_ring     （无上游依赖，也不被复用；成本最高，放最后）
```

- **2.3 先做**：无新机构、无新求解器，且产出的「凸块组合开孔面板」被 2.2 直接复用。
- **4.1 与 4.4 可并行**：二者互不依赖，各自产出 4.3 需要的一半（小球 / 铰链）。
- **4.3 在两者之后**：它同时需要自由滚动的小球与枢轴铰链。
- **3.4 最后**：需要新的复合非凸几何与一个现有原语覆盖不到的六自由度抽出动作。

---

## 4. 逐任务环境需求

### 4.1 docx 2.3 —— `routing/bar_through_hole.py` ✅ 阶段 1 已落地（2026-08-05，08-12 改六棱柱）

| 项 | 内容 |
|---|---|
| 场景资产 | 竖直面板（**正六边形孔**）、**正六棱柱杆**、近端两个托座、远端托座、工业风六角法兰 |
| 开孔做法 | 8 块凸 `Box`：4 块框（立柱 + 下槛 + 上楣）围出六边形的外接矩形，再 4 块沿斜边旋转的倒角块削去四个角三角形。不做布尔开孔——与 `routing/cable_routing.py:810-818` 走线柱拆成柱身＋锥底＋顶盖的既有凸块组合解法同构 |
| 杆 | 程序化生成的正六棱柱网格（`hex_prism_mesh`，轴沿 local x），`gs.morphs.Mesh(convexify=True)`——棱柱本身是凸体，凸包即自身，所以 convexify 是**精确**而非近似。动态、`rho=2700`（铝的量级，P7）。对边距 0.018（此前是直径 0.024 的圆柱） |
| 承载方式 | **assisted attachment**：抓点在杆心后 75mm，指面只承受纯力矩，Franka 指增益 kp=100 承不住。用现成的 `primitives/attachment.py` 的 `AttachmentManager` 运动学承载，指面只需看起来夹住——与 cable_routing / untangle 抓刚体件的做法一致 |
| 托座 | **平顶开放块，无挡块**：六棱柱取平面朝下姿态，躺在一个面上不会滚，而挡块原本只为防圆轴侧滚而设。近端两个夹住杆心防倾覆，远端一个顶面与孔下沿齐平，使穿孔后变成两点支撑 |
| 复用 | `StandardTabletopSceneBuilder`、`AttachmentManager`、`physical_contact.py` 的摩擦配置与位姿读取 |
| 新增 | `primitives/axial_insert.py`（见下）、`verification/bar_through_hole_verifier.py` |
| 不变量 | `threading_count ∈ {0,1}`。判定 = 两端分居面板两侧 **且** 杆轴与中平面的交点落在**六边形孔内**（`hexagon_contains`：正六边形是三条条带的交集，法向在 30°/90°/150°） |
| 防捷径 | 从面板上方绕过去：起止 xy 与正常插入完全相同，只有搬运高度不同，杆落到面板顶上 → 交点在六边形外 → 判 0。**「两端分居两侧」单独不够**：横搭在面板顶上也满足该条件，孔内交点判据是承重的 |
| 风险 | 低。无 PBD、无关节 |

`threading_count` 取无符号 `{0,1}`：杆轴对称，端对端翻转是同一物理状态，state-based verifier
无法区分正反穿。§4.2 的方向敏感要求由 docx 2.4/2.5（绕/解绕）在任务对层面满足。

**六边形不是键控配合**：杆的外接圆半径 0.0104 小于孔的内切圆半径 0.016，任意滚转角都能通过。
六棱柱在这里的作用是工业观感 + 平面朝下不滚，不是增加对准约束。只判杆**轴**的穿越点，不判整个
截面：截面留在孔内由碰撞保证，而精确的截面判据（孔六边形对杆六边形作 Minkowski 腐蚀）在正确落座
位姿上恰好落在边界，会把真成功变成浮点掷硬币。

**原语缺口（已解决）**：docx 的动作是「夹持杆中段、一次水平平移插入」。`PickPlacePrimitive` 的
13 个阶段是顶抓序列，`translate` 发生在 `place` 之前而 `place` 是纯竖直下降，且释放后没有水平退出，
episode 会以张开的夹爪停在孔口。已新写 `primitives/axial_insert.py`
（`AxialInsertPrimitive`，15 阶段），不改 `PickPlacePrimitive`——它已被 swap / onestroke /
maze_wall_removal 三个任务共用，改动面过大。

### 4.2 docx 4.1 —— `connectivity/gate_cage_ball.py`

| 项 | 内容 |
|---|---|
| 场景资产 | 一侧开口的围栏（`Box` 组合）、小球、挡板、开口处的插板槽位 |
| 小球 | `gs.morphs.Sphere`。该 morph 存在于安装的 Genesis（`morphs.py:382`），但**仓库内尚无任何使用**，滚动阻尼与摩擦参数需要首次标定 |
| 复用 | `PickPlacePrimitive` 可完成「顶抓挡板 → 落入槽位」，与其 `place` 阶段的竖直下降语义一致 |
| 新增 | 首个「机器人全程不接触被判定物体」的任务；shake test（晃动平台后球是否仍在栏内） |
| 不变量 | 球的 `C_free` 连通性：与外界连通 → 有界连通分量。`to_info()` 须标 `"space": "c_free"`（§4.4 要求） |
| 防捷径 | 与时机深度耦合：球恰好位于开口处时插板会把球挡在外面——同一动作、不同时机，球落入 `C_free` 的不同连通分量。「看到开口就插」的脚本策略期望成功率被固定在约一半 |
| 随机化 | **必须**。`task_taxonomy_zh.md` §4.4 规定 C4 任务未在 `generation/layout_randomization.py` 注册随机化条目者不得进入 benchmark 产物；本任务随机化的是球的初始位置与速度（即插板时机） |
| 风险 | 中。Sphere 参数未标定；shake test 的判定阈值需实验确定 |

### 4.3 docx 4.4 —— `connectivity/linkbar_merge_components.py`

| 项 | 内容 |
|---|---|
| 场景资产 | 左右两组刚性杆件（组件 A、B）、一端铰接于 A 的连接杆、两个外观完全相同的插口（B 左端的 B1、A 立柱顶端的 A2），两插口都位于连接杆的旋转圆上 |
| 铰链 | 复用 `connectivity/stacked_plate.py:95` `_write_disk_urdf` 的程序化 URDF 写法。现有模板硬绑圆柱碰撞体与 Y 轴、参数为圆盘专用，需泛化为通用的单自由度铰链发射器 |
| 复用 | `primitives/connector_latch.py:18` `ConnectorLatch`——进入捕获区后把手柄吸附到固定位姿，正是「到位后由固定约束锁定」的语义；已被 cable_routing 与 untangle 使用 |
| 新增 | 约束图 union-find verifier |
| 不变量 | `component_count`（β₀）2→1。`to_info()` 须标 `"space": "constraint_graph"`——本任务的连通性定义在约束图上，与 4.1/4.3 的 `C_free` 不可混用 |
| 防捷径 | A2 与 B1 同款、同在旋转圆上、动作成本完全相同，唯一区别是接口的全局归属。接 A2 时新边两端本就同属 A，是 cycle 边而非合并边，判失败。物理层复核：提起 A，合并成功则 B 被整体带起 |
| 随机化 | **必须**。逐 episode 随机化两插口的角位置，使「转向最近或固定方向的插口」的策略被固定在随机水平 |
| 风险 | 中。铰链发射器泛化是确定性工作；union-find 判据无物理不确定性 |

### 4.4 docx 4.3 —— `connectivity/diverter_route_ball.py`

| 项 | 内容 |
|---|---|
| 场景资产 | 入口竖槽、分岔结构、左右两条出口通道、绕枢轴旋转的分流板、小球 |
| 依赖 | 小球来自 4.1；枢轴铰链来自 4.4 |
| 原语 | 旋转分流板。`primitives/rim_rotate.py:24-34` 的 `rim_point_world` 假定圆盘面在 XZ 平面、法向沿 Y，若分流板的枢轴取向不同则不可直接复用，需按实际取向决定复用或新写 |
| 不变量 | 球的 `C_free` 上入口区与左／右出口区的 S–T 连通关系。左路「通路不存在 → 存在」的同时右路「存在 → 不存在」 |
| 判定 | 功能性判定——球实际从指令一侧的出口离开。docx 明确「S–T 弹珠测试本身就是任务」，即该类允许物理复核作为主判据 |
| 防捷径 | 初始板向与目标指令逐 episode 随机组合，同一场景在指令「走左」与「走右」下正确旋转方向相反，「看到板就转固定方向」的脚本期望成功率被固定在一半。板旋转不到位（半开）时球卡在分岔口，构成可区分的中间失败态 |
| 随机化 | **必须**（同上，且指令方向本身也是随机轴） |
| 风险 | 中。小球在槽道内的滚动行为需调参；半开卡球的中间态需能稳定复现 |

### 4.5 docx 3.4 —— `entangle/unlink_c_ring.py`

| 项 | 内容 |
|---|---|
| 场景资产 | 支架、固定的闭合刚性圆环、C 形开口环 |
| 几何做法 | 两个环都是非凸体。按仓库既有解法拆为多段短圆柱沿圆周组合；C 环即少放几段留出开口 |
| 复用 | 仅 `StandardTabletopSceneBuilder` 与 `physical_contact.py` |
| 新增 | 复合环几何生成器；一个六自由度抽出原语——动作是「沿一条使开口始终对准闭环环身的空间轨迹一次抽出」，现有原语（顶抓放置、手柄拖拽、轮缘滚动）都不覆盖 |
| 不变量 | `linking_number` 1→0。判定为两环包围盒分离且无穿插；物理层复核为分离后 C 环可沿任意方向平移离开 |
| 防捷径 | 由物理本身保证：平拉、旋转等非 gateway 轨迹会直接被环身卡住，不存在侥幸通过的连续路径 |
| 风险 | 高。防捷径完全依赖碰撞精度——若复合近似太粗，开口尺寸失真会让本该卡住的轨迹通过，或让本该通过的轨迹卡住。分段数与碰撞裕度需实验确定 |

---

## 5. 这条轨道覆盖不到什么

| 类别目录 | 纯刚体轨道做完后 | 说明 |
|---|---|---|
| `connectivity/` | **4 / 4 完成** | 4.2 已实现，本轨道补齐 4.1、4.3、4.4 |
| `routing/` | 2 / 7 | 2.4 已实现 + 本轨道的 2.3。其余 5 个（2.1、2.2、2.5、2.6、2.7）都含绳或闭合环 |
| `entangle/` | 2 / 4 | 3.1 已实现 + 本轨道的 3.4。3.2、3.3 含绳或闭合带 |
| `deformation/` | **0 / 5，仍为空** | 该类别按定义即「可形变物体自身的形状、铺展与层叠关系」，不存在刚体版本 |

因此纯刚体轨道无法单独让四个类别都非空。若同时希望 `deformation/` 脱离空目录状态，最短路径是
docx 1.4 `hose_bend_u`——软管即开放弹性管，与现有 PBD 管线同构，不需要布料求解
（见 [`task_environment_buildout_zh.md`](task_environment_buildout_zh.md) §2.1）。它不属于本轨道
（含 PBD），但不依赖任何阻塞能力。

---

## 6. 第一步：2.3 `bar_through_hole` 的落地清单

最小文件集（依据 `../framework/module_boundaries_zh.md` §6，其中 planner / supervision / MDP 为
条件项）：

```text
topogym/tasks/routing/bar_through_hole.py            # Layout / Scene / SceneBuilder
topogym/verification/bar_through_hole_verifier.py    # PuzzleState + PuzzleEvaluator
configs/task_configs/bar_through_hole_topogym_tabletop_v1.yaml
topogym/primitives/<新原语>.py                        # 水平插入，见 §4.1 原语缺口
demos/routing/bar_through_hole_physical_insert_demo.py  # 要能录数据则必需
两处登记：topogym/core/taxonomy.py 的 CATEGORIES + topogym/tasks/__init__.py 的 re-export
一处登记：topogym/verification/__init__.py 的 re-export
四个 bash 注册表各一行：record_all_tasks.sh / collect_and_view.sh / stability_sweep.sh /
                        verify_dataset_recording.sh（均只接受 demo 模块路径）
```

登记完成后跑 `python topogym/core/taxonomy.py` 校验表与目录一致。

行数估算（按仓库内既有任务实测区间，不作为目标）：task 模块 269–504、verifier 48–237、
配置 106–157、demo 329–658。2.3 的几何比 `stacked_plate` 简单（无程序化 URDF、无扇形网格生成），
预期落在各区间下段。

---

## 7. 未决事项

1. ~~**水平插入原语的形态**~~ —— 已定：新写独立原语 `primitives/axial_insert.py`
   （`AxialInsertPrimitive`），15 阶段，`run()` 接 `insert_axis` 方向向量与 attach/release 回调。
   未为 3.4 的抽出动作预留免释放变体（按 CLAUDE.md §3，等 3.4 真要复用时再改）；届时若确认可合并，
   只需加一个「不释放、反向」的分支。
2. **4.1 的 Sphere 参数**：仓库内无先例，滚动阻尼、摩擦、恢复系数均需首次标定。建议在正式建任务
   前先用一个最小场景（平面 + 球）确认滚动行为可控。
3. **3.4 的碰撞精度**：复合环的分段数直接决定防捷径是否成立。建议在实现任务前先做一次独立验证：
   固定环 + C 环，脚本化地试若干条非 gateway 轨迹，确认全部被卡住。
4. 本轨道与 `task_environment_buildout_zh.md` §5 推荐的 3.2 + 2.5 是否并行推进。
