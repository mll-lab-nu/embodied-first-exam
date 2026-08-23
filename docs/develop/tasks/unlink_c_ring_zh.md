# docx 3.4 C 形环从固定圆环中解开 —— 基础场景建设

> 日期：2026-08-22（同日三轮：场景落地 → GPU 实测与结论修正 → 抽出原语／verifier／physical demo）
> 上游：`../TopoGym_tasks.docx` §3.4
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置，
> §4.5 为落地后的形态表、§7 第 3 条为碰撞精度前置验证的结论）、
> `../framework/task_taxonomy_zh.md` §4.3（C3 entangle 判定契约）
>
> 目标模块：`topogym/tasks/entangle/unlink_c_ring.py`

---

## 0. 结论摘要

- 第一轮交付**场景与几何验证**：场景可载入、可静置、可观察，且
  `rigid_first_track_zh.md` §7.3 要求的碰撞精度前置验证已完成（§1–§7）。
- 第二轮补上抽出原语、verifier、自由平移探针与 physical demo（§8）。
- **第三轮把支架从「竖立环 + 悬臂」改成「立柱 + 平放环」**（§2.2）：viewer 里机械臂被
  悬臂卡住，而离线 gate 没抓到——它量的是 C 环的净空，不是手的。平放之后头顶无结构，
  并且抽出的转轴变成水平指向机器人，滚转成了 joint 7 的自转，原来的主风险消失。
  代价是 gateway 由一条变两条（§4.2）。离线 gate 全过，**GPU 未跑**。
- 几何一侧的风险已消解。七条非 gateway 轨迹全部卡住，且**每一条都由两环的互锁本身卡住**
  （最深处 8.60–8.97mm）；两条 gateway 全程净空为正、终态解链。
- 支架取**立柱 + 平放闭合环**（§2.2）。C 环的径向凸台已默认关闭（§2.3）。
- **gateway 有两条**（§4.2），互为镜像；两条都要求先把开口对准管身，防捷径不受影响。
- 求解器一侧已验证（2026-08-22，Genesis 1.2.1，CPU 后端）：600 步静置 `Lk` 恒为 −1，
  开口方位漂移 0.6°，每步 1ms。四项检查全部通过，明细见 §6.2。
- **一处结论修正**：维持互锁的是悬挂接触处的库仑摩擦，不是抓取凸台。此前
  「凸台不加环就自行脱落」的论断漏算了摩擦。缩短凸台的对照（§6.4）确证了这一点：
  预测静止方位挪 51°，实测挪 0.04°。凸台第三轮起默认关闭。
- 写死的投影矩阵在改支架朝向时会失效（读成 `Lk = -2`），已改为由布局导出，见 §1.2。

---

## 1. 任务定义

### 1.1 docx 原文要点

| 项 | 内容 |
|---|---|
| 场景 | 支架上固定一个闭合圆环，C 形开口环与其互锁 |
| 闸门关系 | 由 C 环的开口定义：闭合环身必须从开口通过，其余方向都是刚体碰撞死路 |
| 动作 | 夹持 C 环，沿一条使开口始终对准闭环环身的空间轨迹一次抽出 |
| 状态变化 | linked → unlinked |
| 判定 | 几何层判两环包围盒分离且无穿插；物理层验证分离后 C 环可沿任意方向平移离开 |
| 防捷径 | 由物理本身保证：平拉、旋转等非 gateway 轨迹会被环身卡住 |
| 定位 | 纯刚体的 embedding topology 任务，说明拓扑操作不限于柔性物体 |

### 1.2 判定口径

`task_taxonomy_zh.md` §4.3 对 C3 类允许的 `invariant` 取值为 `crossing_number` /
`signed_crossing_sequence` / `self_crossing_number`，其中不含 `linking_number`；而
`rigid_first_track_zh.md` §4.5 原本把本任务的不变量写作 `linking_number`。两处不一致。

本任务取的口径：主读数用 `signed_crossing_sequence`，并显式声明
**「C 环开口用一条直弦补合」**这一 canonical closure（闭合方案）；`linking_number` 作为
派生读数一并写入 `to_info()`，其值为带号交叉和的一半。不修改契约文档。

取这一口径的原因：C 环是开曲线，linking number 在补合之前没有定义；而补上的那条弦
恰好就是闭合环身要穿过的那一段，因此「读数发生变化」与「环身通过了开口」是同一件事。

投影方向按契约要求显式声明，但**不写死在配置里，而是由布局导出**
（`_c_ring_geometry.bisector_projection`）：两个环的法向互相垂直（C 环挂在闭合环的切向管段
上），取其角平分线为视线，两个环都成 45°，谁也不是边对边。导出的视线向量由 gate 与 demo
在运行时打印，也写入 `to_info()`，「显式声明」由此满足。

不写死的理由是实测出来的：整组场景随 `stand.hang_yaw_deg` 转，此前写死的矩阵在一个朝向上
正确，换个朝向就正好沿着 C 环自身的平面看过去，出生读数变成 `Lk = -2`，由
`tests/check_c_ring_clearance.py` 当场拦下。导出式在多个朝向上复核过，出生 `|Lk| = 1`、
gateway 终态 `Lk = 0`。

---

## 2. 场景设计

坐标为 task 系：原点在桌面中心，`z=0` 是桌面，`+x` 远离机器人，`+y` 在机器人左侧
（`../../../configs/GEOMETRY_PARAMETERS_zh.md`）。

### 2.1 整体形态

立柱竖在桌面上，**闭合环平放在立柱顶端**、在立柱正上方的环缘固定；C 环挂在正对面的环缘，
与立柱相距一个环直径。**没有悬臂**。`stand.hang_yaw_deg = 270`：C 环挂在环的 `-y` 缘，
立柱立在 `+y` 缘。

```text
沿 -y 看（oblique 一侧）                    俯视

        ╭──────────────╮  闭合环（平放）          ╭───────╮
        │              █  立柱                  │   ●   │  ● = 立柱（+y 缘）
        ╰─╥────────────╯                        │       │
          ║  C 环（环面 yz，边对边）              ╰───╥───╯
          ╨                                          ╨  C 环挂在 -y 缘
 ════════════════════════ 桌面                  -y ←    → +y
```

- 闭合环平放，法向朝上，因此它只比自己的平面高出一个**管半径**——竖立时要高出一整个
  major_radius。这是本形态给 home 位让出 36mm 净空的主要原因。
- C 环挂在环缘的管身上，环面与该处管身垂直，即 **yz 面**，法向 `±x`。
- 立柱、闭合环都是固定件；只有 C 环需要「多段几何、一个位姿」。

### 2.2 为什么改成平放的环（2026-08-22 第三轮）

原形态是「竖立圆环 + 水平悬臂」。它在 viewer 里暴露的问题是**机械臂被立柱与悬臂卡住**。

原因是我漏了一项检查：离线 gate 核的是 **C 环**包络与悬臂的净空，没核**手**的。抓取点在
悬臂正下方，手降下去必然撞上。gate 通过而场景不可用，是因为它量的对象不对。

平放的环把头顶结构整个去掉：立柱在环的另一侧，C 环上方只有它挂着的那段管身。

**附带的收益：转轴变水平。** 环平放之后，C 环的法向（抽出要绕的转轴）变成水平且指向
机器人。这开出一个选项——夹爪若从侧面正对环面进去，工具轴与转轴重合，滚转就是 joint 7 的
自转。**这个选项试过之后放弃了**：viewer 里手横着伸出去很别扭（2026-08-22）。改回竖直接近，
理由与代价见 §2.5。

**代价：gateway 由一条变成两条。** 竖立时闭合环的远侧挡住了向上的退路，所以只有「开口朝上、
向下抽」一条解；平放之后头顶无遮挡，「开口朝下、向上抽」同样成立。两条都要求把开口对准
管身，防捷径（不对准就卡住）不受影响——离线 gate 已把第二条重新归类为 gateway 而不是捷径，
并各自验过。任务的解不再唯一，这一点写在这里备查。

### 2.3 抓取凸台

规划阶段未列。`tasks/_fixtures.py` 的 `_link_xml` 把一个刚体的质心放在其**碰撞件包围盒的
中心**，惯量按同尺寸实心长方体给。

不带凸台时，C 环的包围盒中心只被开口**横向**拉偏 1.62mm，竖直方向不偏；而管身正在环心的
正上方。于是这个刚体的静止姿态是「把那 1.62mm 转到正下方」，也就是开口正对管身——离出生
姿态 90°，且到那个姿态时环已经掉下去了。凸台（径向短圆柱，与开口成 90°）把包围盒向下拉
8.30mm，静止姿态因此改到离出生姿态 11°。

**实测修正（2026-08-22）**：两个静止姿态都没被走到。600 步静置里开口方位只从 90.00° 变到
90.23°，最大偏离 0.6°。原因是悬挂接触处的库仑摩擦：

| 量 | 值 | 来由 |
|---|---:|---|
| 阻碍环绕自身法向转动的摩擦力矩 | 12.3 mNm | `mu * W * r`，默认接触摩擦 1.0、C 环自重 0.49N、孔半径 25mm |
| 包围盒质心偏心产生的重力矩 | 0.79 mNm | `W × 1.62mm`（带不带凸台都是这个值——凸台只改竖直方向） |

相差 15 倍，因此 C 环停在出生姿态不动。环套在固定横杆上绕自身法向转动时，接触点在环的
内表面上滑动而横杆不动，这是滑动摩擦而不是滚动，此前的判断漏掉了这一项。

**对照已跑（§6.4）**：把凸台缩到 6mm——预测静止方位由 79° 移到 39°——开口方位实测仍是
89.99°，一动没动。摩擦是唯一机理这一点由此确证，凸台对稳定性的贡献为零。

**结论（第三轮定案）**：凸台**默认关闭**。它不维持互锁（上面已证），而平放形态下夹爪
从侧面直接捏管身，它也不是抓取特征了——反而正好挡在选定的抓取方位（环底 180°）上。

备用方案按用户建议保留在纸面上：若侧向捏管身抓不稳，就在 C 环上加一根**沿环法向**的横杆
（不是这里的径向凸台）。那种朝向下，转轴、工具轴、横杆轴三者重合，是最省手腕的一种。
届时新写，不复用 `tab` 字段。

### 2.5 接近姿态取竖直，滚转 45°

三种姿态都试算过：

| 方案 | 手腕行程 | 观感 | 结论 |
|---|---|---|---|
| 工具轴对齐环法向（水平伸手） | 0（纯 joint 7 自转） | 别扭 | 放弃 |
| 竖直接近，滚转 = 开口方位角 | 45° | 自然 | **取这个** |
| 竖直接近，开口方位角 90° | 90° | 自然但行程大 | 不必要 |

关键在于**滚转角等于开口方位角**：把开口从 315° 转到 0° 只要 45°。手起于指尖朝下、
止于偏 45°，两头都在舒服的范围。代价是滚转不再落在单关节上，但 45° 比原来的 90° 好办得多，
且原语自测跟踪误差，跟不上会直接报。

**C 环放大到 55mm 是这个决定逼出来的。** 竖直下来的手必须穿过闭合环所在的平面，而只有
`y < 0` 那一侧在环的 footprint 之外——`|y|` 的上限就是 C 环半径。手半宽约 45mm：

| C 环半径 | 抓取点 y | 手的 +y 边缘 | home 余量 |
|---:|---:|---:|---:|
| 40mm | −37.0mm | **+8.0mm**（切进环里） | 56.8mm |
| **55mm** | **−50.8mm** | **−5.8mm** | **26.8mm** |
| 60mm | −55.4mm | −10.4mm | 16.8mm |

取 55mm。45mm 的手半宽是估算，−5.8mm 这个余量要靠 GPU 跑确认。

**「抓不住」不是风险。** C 环由 `AttachmentManager` 配 `parent_quat_fn` 刚性焊在手系里
承载——就是 cloth folding 那套「假装抓住 + assist 牵引」，指面从不承载。指头唯一要做的是
不撞上、看起来像夹住。因此剩下的风险纯粹是碰撞，上表就是为它定的。

### 2.4 复合环的构造

两个环都是非凸体。`gs.morphs.Mesh(convexify=True)` 会把环的孔填实，因此按仓库既有解法
拆为多段短圆柱沿圆周组合（同 `routing/bar_through_hole.py` 用 8 块凸 Box 围出六边形孔）。
移动的 C 环必须是一个刚体、一个位姿，用 `_fixtures.write_body_urdf` /
`add_rigid_assembly`：一个 link、多个 `<collision>`，`convexify=False`、
`recompute_inertia=False`。闭合环用同一函数、`fixed=True`。

`_fixtures.py` 未作修改：整环的朝向烘进每段的 `rpy`，整体不用 `yaw_deg`。

两处取舍：

- **弦而非切线**。每段圆柱的轴取两个落在真实圆周上的点之间的弦，因此近似只会把材料
  往内移，孔略紧、外廓略小，**不会把开口撑宽**——而开口宽度正是防捷径唯一依赖的尺寸。
- **按弧角配段数**。配置给 `segment_deg` 而不是段数。固定段数时弦近似的矢高
  `R(1-cos(seg/2))` 随半径增长，固定弧角时它与半径成正比，两个环的保真度一致。

---

## 3. 尺寸与不等式

配置：`configs/task_configs/unlink_c_ring_topogym_tabletop_v1.yaml`。单位米。

| 参数 | 取值 | 来由 |
|---|---:|---|
| 闭合环 `major_radius` | 0.055 | 同时决定立柱离 C 环多远（相距 2×R = 110mm） |
| 闭合环 `tube_radius` | 0.004 | |
| 闭合环 `center` | [0.060, 0.055, 0.130] | 平放。xy 使 C 环落在 y=0（机器人正中线）；z = C 环静置中心 + 孔间隙 |
| C 环 `major_radius` | 0.055 | 由竖直下手的净空定，见 §2.5 |
| C 环 `tube_radius` | 0.005 | |
| C 环 `gap_deg` | 23.0 | 开口净宽 11.93mm |
| C 环 `gap_azimuth_deg` | 315.0 | 它同时是手腕的滚转角（45°），见 §2.5 |
| `stand.hang_yaw_deg` | 270.0 | C 环挂 `-y` 缘、立柱立 `+y` 缘 |
| `stand.post_radius` | 0.008 | 不承力，也不进入 `top_z`（竖直圆柱顶面是平的） |
| `primitive.grasp_azimuth_deg` | 67.5 | 起止两处 y 都是 −50.8mm，是竖直下手净空最好的一段 |
| `c_ring.tab.enabled` | false | 已证明不承担稳定作用，且正挡在抓取方位上，见 §2.3 |

导出量（由 `_c_ring_geometry.scene_geometry` 单点算出）：

| 量 | 值 | 定义 |
|---|---:|---|
| 孔间隙 `hang_offset` | 46.0mm | C 孔半径 − 闭合环管半径 |
| 抽出行程 `extract_travel` | 18.0mm | 2 ×（两管半径之和） |
| C 环静置环心 | (0.060, 0, 0.084) | |
| 场景最高点 | 0.134 | 闭合环平面 + 管半径。home 位指尖 0.1608，余量 26.8mm |

五条不等式，改任何一条都要重跑离线 gate：

1. 开口能过环身：`gap_clear_width > 2 × 闭合环管半径` —— 11.93 > 8.00mm
2. C 环套得进管身：`hang_offset > 0` —— 46.0mm
3. 抽出时不撞桌面：`静置环心高 − 抽出行程 − C 环外半径 > 余量` —— 6.0 > 4.0mm
4. 立柱不碰 C 环：`两者水平距离 − C 环外半径 − 立柱半径 > clearance` —— 42.0 > 8.0mm
5. reset 时不撞机械臂：`home 指尖高 − 场景最高点 > 0` —— 26.8mm

第 5 条与 `bar_through_hole` 的 `panel.top_z` 同一条余量。平放的环让这一条从竖立形态的
15.8mm 松到 26.8mm。

`UnlinkCRingLayout.validate()` 在 build 时复查这五条，不通过直接抛错。

**这五条量的是 C 环与场景，量不到手。** 第三轮改形态就是因为这个：gate 全过而 viewer 里
机械臂被卡住（§2.2）。手的净空目前靠形态本身保证（头顶无结构、侧向进出），没有对应的
自动判据——这是已知缺口，记在 §10。

---

## 4. 碰撞精度验证（§7.3 的前置验证）

`tests/check_c_ring_clearance.py`，纯 numpy + PyYAML，不需要 GPU。

两个环都是圆柱链，所以「是否接触」就是两组线段之间的最小距离减去各自半径。这个量对
**实际载入的碰撞体**是精确的，而不是对理想圆环——正是分段近似是否够用这个问题需要的口径。

判据分四组：

| 组 | 内容 |
|---|---|
| fit | §3 的五条不等式及其余量 |
| fidelity | 两链的段数与弦高，以及弦高与开口单边余量的比值 |
| reading | 静置与出生位姿的净空，出生时弦闭合后的 `Lk` |
| gateways | 两条 gateway 轨迹全程净空为正且终态解链；七条非 gateway 轨迹全部卡住 |

「卡住」的阈值取 1mm 穿透。两链最深的弦近似误差是 0.171mm，非 gateway 轨迹实测穿透
8.60–8.97mm，1mm 把两者分得很开。

### 4.1 实测结果（2026-08-22，平放形态 + 竖直接近）

```text
fit        开口余量 11.93 > 8.00mm；套入余量 46.0mm；抽出后离桌 6.0 > 4.0mm；
           立柱离 C 环 42.0 > 8.0mm；home 余量 26.8mm
fidelity   两链各 36 / 34 段，弦高均 0.209mm；
           开口对 8mm 管身单边留 1.97mm，是弦高的 9 倍
reading    静置净空 -0.196mm（接触，量级即弦高）；出生净空 +1.804mm；
           视线 (+0.707, 0, +0.707)（两环法向的角平分线）；出生 Lk = +1.0
gateway A  开口朝上、下移 18mm、径向移开：环间 -0.21mm、立柱 +42.00mm、终态 Lk = 0
gateway B  开口朝下、上抽 120mm：        环间 -0.21mm、立柱 +42.00mm、终态 Lk = 0
```

七条非 gateway 轨迹（括号内为仅计两环互锁时的最深穿透）：

| 轨迹 | 卡住位置 | 先碰到 | 互锁单独 |
|---|---:|---|---:|
| 不转直接下移 | 1% | 闭合环 | −8.94mm |
| 不转直接上移 | 93% | 闭合环 | −8.20mm |
| 沿管轴平移（正向） | 29% | 闭合环 | −8.93mm |
| 沿管轴平移（反向） | 29% | 闭合环 | −8.93mm |
| 横向平移（正向） | 9% | 闭合环 | −8.95mm |
| 横向平移（反向） | 9% | 闭合环 | −8.95mm |
| 提起后搬走 | 47% | 闭合环 | −8.91mm |

**每一条都由闭合环本身卡住**，立柱一次也不是先碰到的那个。防捷径成立于互锁。

负对照：`--gap-deg 20` 时开口净宽不足，gate 退出码 1。

### 4.2 gateway 有两条

平放的闭合环头顶无遮挡，因此「开口朝上、向下抽」与「开口朝下、向上抽」都成立，
互为镜像。原形态（竖立环）只有一条，因为环的远侧挡住了向上的退路。
两条都要求先把开口对准管身，所以防捷径（不对准即卡住）不受影响。

**但两条的代价差一个数量级**，oracle 取第一条：

| | 手腕滚转 | 平移行程 |
|---|---:|---:|
| A 开口朝上、下移 | 45° | 18mm |
| B 开口朝下、上抽 | 135° | 120mm |

下移只需把管身从孔的近缘挪到 C 环外廓之外——两个管半径的两倍；上抽要先把管身横穿整个
孔径，行程是孔半径加 C 环外半径。加上开口从 315° 转到 180° 比转到 0° 远 90°，
第二条几乎不构成有吸引力的替代解。

gate 里那条镜像探针因此只做「转 + 直上」，不带搬离段：抽完时 C 环正骑在闭合环的平面上，
从那里横移会把它拖过环缘。

---

## 5. 文件与登记

**新增**

| 路径 | 内容 |
|---|---|
| `topogym/tasks/entangle/_c_ring_geometry.py` | 环几何与全部导出量。纯 numpy，不 import Genesis，离线 gate 按路径加载它 |
| `topogym/tasks/entangle/unlink_c_ring.py` | `UnlinkCRingLayout` / `Scene` / `SceneBuilder` |
| `tests/check_c_ring_clearance.py` | §4 的离线 gate |
| `configs/task_configs/unlink_c_ring_topogym_tabletop_v1.yaml` | 布局（task 系） |
| `configs/unlink_c_ring.yaml` | inspect demo 主配置，env 取 `world_tabletop_v1` |
| `configs/run_configs/unlink_c_ring.yaml` | `static_only` / `settle_steps` / `hold_steps` / `hold_sample_every` |
| `demos/entangle/unlink_c_ring_inspect_demo.py` | stage-0 demo |

**登记**：`topogym/core/taxonomy.py` 的 `CATEGORIES["entangle"]`、`topogym/tasks/__init__.py`
的 re-export、`demos/README.md`、`tests/README.md`、
`configs/GEOMETRY_PARAMETERS_zh.md` 的任务布局入口、
[`rigid_first_track_zh.md`](rigid_first_track_zh.md) 的进度表与 §4.5、§7 第 3 条。

**与规划相比少写的一个文件**：原计划另立 `tests/c_ring_spike.py` 与两份 spike 配置。
`closed_band_spike` 之所以独立成文件，是因为 docx 3.3 的任务场景尚不存在、spike 场景与
任务场景不是同一个；本任务的 spike 场景就是任务场景本身，因此四档测试（build / settle /
hold / bench）并入 inspect demo，不另建一套同构的 harness。

**本轮未做**：`verification/unlink_c_ring_verifier.py`、六自由度抽出原语、physical demo、
四个 bash 注册表（它们只接受 demo 模块路径，且只登记 physical demo）、
`generation/` 的 contrast pair。按 `../framework/task_taxonomy_zh.md` §4.0，本任务目前
不具备 benchmark 产物资格，任务模块的 docstring 已按 `bar_through_hole.py` 的写法注明分期。

抽出原语的形态刻意留到场景定下来之后再定：`rigid_first_track_zh.md` §7 第 1 条已注明
`AxialInsertPrimitive` 未预留「不释放、反向」的变体。现在轨迹已由 §4 量出来（对准开口 →
下移 18mm → 沿管轴移开），可以据此写规格。

---

## 6. 验证

### 6.1 离线（只需 numpy 与 PyYAML，任何解释器）

```bash
python tests/check_c_ring_clearance.py                 # 退出码 0，见 §4.1
python tests/check_c_ring_clearance.py --gap-deg 20    # 负对照，退出码 1
python topogym/core/taxonomy.py                        # 分类表与目录一致
python tests/check_gateway_extract_quat.py             # 抽出原语的旋转合成
python tests/check_demo_configs.py                     # 20 个 demo，四项检查全部无命中
```

### 6.2 求解器（项目 venv，2026-08-22 已跑）

环境：Genesis 1.2.1，`.venv-gs121`，`env.genesis.backend` 默认取 cpu（AMD Ryzen 9 7950X）。

**这一组读数取自第一版布局**（竖立环 + 悬臂）。第三轮把闭合环改平放、C 环放大到 40mm、
凸台关闭之后，这些数字**不再直接适用**：静置的接触点、C 环质量分布、悬挂高度都变了。
结论（摩擦压过重力矩、静置不自解）预期仍成立——机理与朝向无关——但要在新形态上重跑才算数。
重跑命令见 §6.3。

| 命令 | 结果 |
|---|---|
| `python tests/check_configs_compose.py --task unlink_c_ring_topogym_tabletop_v1` | 任务配置 298 键、主配置 `unlink_c_ring` 302 键，全部通过；26 份主配置无失败 |
| `python -m demos.entangle.unlink_c_ring_inspect_demo run.static_only=true run.verbose=true` | 23 个实体载入，两份 URDF 生成正常，无初始互嵌告警。出生 `Lk = -1.0`、开口方位 90.00°、`top_z = 0.1450`、home 余量 15.8mm |
| `python -m demos.entangle.unlink_c_ring_inspect_demo run.verbose=true` | 沉降后 `Lk = -1.0`、开口方位 90.36°、位移 1.02mm、倾角 0.03°。600 步静置：`min_abs_Lk = 1.00`、开口方位始终在 90.03–90.61° 之间、位移在 0.5–1.8mm 之间往复、倾角 ≤ 0.03°、`slipped_at = None` |
| `python -m demos.entangle.unlink_c_ring_inspect_demo run.bench_steps=200` | 每步 1ms、约 1115 步/秒；钩子开销落在噪声里（−2%）。约 1150 个接触对未构成瓶颈，`segment_deg` 不必放宽 |

两条读法：

- **静置不自解成立**。600 步内互锁读数没有变过，开口方位的总变化 0.6°，远小于开口半角
  21.5°。位移的往复是 C 环在孔内的小幅晃动，不是单向漂移。
- **但维持互锁的不是凸台**，见 §2.3。开口方位停在出生值而不是走到凸台给出的静止姿态
  （偏离 11°），说明摩擦先于重力矩起作用。

各次运行都出现的两条 Genesis 告警与本任务无关：`Neutral robot position (qpos0) exceeds
joint limits` 与 `Filtered out geometry pairs causing self-collision ...` 的几何对列表与
`runs/lmc_look7.log`（linkbar）逐字相同，是 Panda 自身几何的既有告警。

### 6.3 待跑：新形态的观感与静置重跑

第三轮改了形态（§2.2），§6.2 与 §6.4 的读数都取自旧布局，需要在新场景上重跑。
这一条同时给出三视角录像：

```bash
mkdir -p runs/videos/unlink_c_ring

python -m demos.entangle.unlink_c_ring_inspect_demo run.verbose=true \
  recording=default 'recording.camera=[oblique,front,wrist]' \
  recording.path=runs/videos/unlink_c_ring/look.mp4 \
  2>&1 | tee runs/videos/unlink_c_ring/look.log
```

判据：

| 读数 / 画面 | 期望 |
|---|---|
| `min_abs_Lk` | 600 步恒为 1.00，`slipped_at=None` |
| `min_opening_to_bar` | 远大于开口半角 16°（凸台已关闭，靠摩擦钉住） |
| `look_front.mp4` | C 环环面正对镜头，立柱偏在一侧，**画面中央没有任何遮挡物** |
| `look_oblique.mp4` | 平放的闭合环与垂挂的 C 环互锁关系可辨 |
| `look_wrist.mp4` | home 位下 C 环是否已在夹爪视野内 |

### 6.4 凸台对照（2026-08-22 已跑）

判定凸台是否承担稳定作用。只改凸台长度，其余不动；五条不等式在该取值下仍然成立
（凸台离桌面由 8.0mm 放宽到 22.0mm）。

```bash
python -m demos.entangle.unlink_c_ring_inspect_demo run.verbose=true \
  task.c_ring.tab.length=0.006 \
  2>&1 | tee runs/videos/unlink_c_ring/hold_tab6.log
```

两种解释各自的预言（预测值按 `_link_xml` 的包围盒质心模型算）与实测：

| 凸台长度 | 预测静止方位 | 实测 `min_opening_to_bar` |
|---:|---:|---:|
| 0.020 | 79.0° | 90.03° |
| 0.006 | 38.7° | 89.99° |

预测值挪了 51°，实测挪了 0.04°，远小于测量噪声（600 步里开口方位的总起伏 0.6°）。
**摩擦是唯一机理，凸台对稳定性零贡献**，见 §2.3。

这一跑同时是新布局（`yaw_deg = 90`、细立柱）下的确认，补上了 §6.2 那组读数的可迁移性：
`stand_yaw=90`、`projection_viewer=(-0.707, +0.707, 0)`、出生与静置 `Lk = +1.0`、
600 步 `min_abs_Lk = 1.00`、`slipped_at = None`、位移 ≤ 2.2mm、倾角 ≤ 0.03°。
且它是在**更弱**的凸台下取得的，因此对默认配置是偏保守的证据。

---

## 8. 第二轮：抽出、判定与 demo（2026-08-22）

### 8.1 新原语 `primitives/gateway_extract.py`

`rigid_first_track_zh.md` §7 第 1 条把「改 `AxialInsertPrimitive` 还是新写」留作未决。
结论是**新写，且不是工作量问题，是表达不了**：`AxialInsertPrimitive.align_axis` 用
`_rotation_between(part_axis_now, insert_axis)` 算修正量，而本任务的旋转是**绕零件自身法向**
滚转——法向在滚转中不动，该式恒等于零；它的 `_axis_tilt` 对准门同理恒为 0。

三条设计要点：

| 项 | 做法与理由 |
|---|---|
| 转手腕而不转握持 | attachment 用 `parent_quat_fn=controller.hand_quat` 刚性焊在手系里，旋转由手腕做。`ramp_to` 能到同样的终态，但那是「零件转了而手臂没动」，动作流里没有东西解释这次转动（`axial_insert.py:321`），演示是废的 |
| 偏移量跟着手转 | `axial_insert` 手部姿态全程不变，实测偏移在世界系里是常量；本任务手要转 90°，偏移存在**手部局部系**里，每步用当前指令姿态转回世界系：`hand = part − R(q) @ offset_in_hand` |
| 按零件插值而不是按手插值 | 对准段是绕环心的纯滚转，手若走直线、姿态单独 slerp，零件中途会甩出去。gateway 全程只有 0.15mm 净空，这个差别就是过与不过 |

对准门改判 `opening_to_bar_deg`（开口方向与「环心指向管身」方向的夹角），由 verifier 提供、
以回调传入，原语因此不 import `verification/`。

**抓取点取环身方位角 67.5°，姿态取竖直**（`ee_quat_for_yaw` 在默认的指尖朝下姿态上加一个
绕竖直轴的偏航）。选点的依据见 §2.5：起止两处的 `y` 都是 −50.8mm，是竖直下手时离闭合环
最远的一段。数值复核：手腕滚转 45.0°，手心由 (0.060, −0.051, 0.208) 走到
(0.060, −0.214, 0.118)，离底座 0.665–0.676m，起点手的 `+y` 边缘在 −5.8mm——整只手在
闭合环的 footprint（`y ∈ [0, 0.110]`）之外。

原语还**自测跟踪误差**：`move_ee_to` 不报残差、不校验可达性（`cloth_link_attach_drag.py:219`）。
第三轮改形态之后这条已不是主风险（滚转落在 joint 7 上），但读数保留——每个 waypoint 记 `‖hand_pos − 指令‖` 与姿态夹角，
把 `worst_pose_error` / `worst_tilt_rad` 放进 Result。这是判断手腕到底跟没跟上的唯一读数。

### 8.2 判定：端点读数不够

**这一轮最重要的发现。** C 环由 assisted attachment 承载，每步写位姿，因此错误轨迹在物理上
**穿模而不是卡住**。而穿模之后把 C 环搬开 90mm，它读起来就是 unlinked——因为它确实
unlinked。**正解与捷径的终态完全相同**，端点读数分不开。

因此判定加入**路径证据**：demo 每步采样两条链的表面净空，把全程最小值 `min_gap_seen` 交给
verifier；穿透超过 `jam_depth` 即 `passed_through`，直接判失败。这与
`swap_crossing_sign` 的 `separated_seen` 是同一形状的论证——路径证据，不是终点谓词。
采样开销实测 0.28ms/步，整段 episode 约 0.4 秒。

### 8.3 `verification/unlink_c_ring_verifier.py`

- `invariant = "signed_crossing_sequence"`，取契约 §4.3 的字面形式 `(over 曲线号, under 曲线号,
  符号)`。这**不是** `swap_crossing_sign_verifier.signed_crossings` 的约定——那里把第三位用来
  表示谁在上，因为它那一个交叉的几何符号从不变；本任务两个交叉共用一个几何符号、
  区别在于哪个环在上，两件事必须分开携带。为此给
  `world/closed_band.py` 的 `Crossing` 加了 `over_curve` 字段，并公开了
  `crossings_between`（`linking_number` 本来就在内部算它，算完丢掉）。
- 判据看 `|Lk|`：符号随投影基手性变，改支架朝向时已由 −1 变成 +1。
- `is_terminal` = 解链 ∧ 表面净空达标 ∧ **未穿模** ∧ 自由平移探针各方向全过 ∧ 释放后稳定。
- 另有两个只报警不判失败的读数，取自 linkbar 的先例：`judge_disagrees`（读数说解链但环推不动
  ——判官错了，不是这次运行错了）与 `probe_uninformative`（还连着却推得动——推力压过了互锁）。
- inspect demo 原本自带的 `live_frame` / `reading` 已搬进 verifier，两个 demo 共用一份。

### 8.4 自由平移探针 `tasks/entangle/_c_ring_travel_probe.py`

契约对 C3 强制要求「分离后可沿任意方向平移离开」。照
`tasks/connectivity/_travel_probe.py`：**施力而不是写位姿**，力按自重的倍数给，同时报
`travel` 与 `peak_travel`，`on_step` 回调把推力喂给 HUD。方向集取离线 gate 里那六个平移方向
——解链前实测全部卡住，解链后应当全部自由，是同一组方向上的前后对照。六次推之间把位姿写回
起点，否则第四次环已经在桌外；这一步在 episode 的操作结束之后，不属于演示。

### 8.5 释放后判「停下来」，不判「没动」

抽出后的 C 环是一个**立在桌面上的环**，松手必然倒平——环心掉约 31mm、横移约 35mm。
那是把环放下应有的样子，拿它判失败是在判场景而不是判运行。所以量的是最后一段窗口内的位移
（`release_settle_window`），要求它停下来且读数未变；一直不停（滚出板外）才判不稳。

### 8.6 防捷径对照

`run.oracle_mode=no_align`：同样的抓取、同样的下移、同样的搬离，唯一区别是开口从未对准管身。
预期**执行顺利但判失败**，失败原因是 `passed_through`。

### 8.7 文件与登记

新增 `primitives/gateway_extract.py`、`verification/unlink_c_ring_verifier.py`、
`tasks/entangle/_c_ring_travel_probe.py`、`demos/entangle/unlink_c_ring_physical_extract_demo.py`、
`configs/unlink_c_ring_extract.yaml`、`configs/run_configs/unlink_c_ring_extract.yaml`、
`tests/check_gateway_extract_quat.py`；task 配置增补 `oracle` / `primitive` / `physical` /
`travel_test` / `success` 五块。

登记：`primitives/__init__.py`、`verification/__init__.py`、
`record_all_tasks.sh` 与 `stability_sweep.sh`（`TASKS` 与 `ORDER` 都改）。
另两个 bash 注册表要 `run.record_dataset`，本轮不接，不登记。

`tests/check_gateway_extract_quat.py` 是新增的离线 gate：原语用四元数合成旋转、
`_c_ring_geometry.apply_phases` 用矩阵合成同一个旋转，两套写法各有一处可能写反符号，
而写反的后果是把环转进闭合环里——在 assisted carry 下是穿模不是卡住，下游看不出来。
gate 因此断言「转完开口确实落到管身方向上」，并比对两套写法在数值上一致
（实测 3.3e-16），五个 `stand.yaw_deg` 取值全过。

### 8.8 本轮验证状态

离线全过：

```text
tests/check_gateway_extract_quat.py   5 个 yaw 全过；两套旋转写法一致到 3.3e-16
tests/check_c_ring_clearance.py       退出码 0（负对照 --gap-deg 30 退出码 1）
tests/check_demo_configs.py           20 个 demo，四项检查全部无命中
tests/check_closed_band_mesh.py       退出码 0（Crossing 加字段后回归）
topogym/core/taxonomy.py              退出码 0
bash -n 两个注册表                     语法通过，无 CRLF
```

**GPU 未跑**，命令见 §9。

---

## 9. 第二轮待跑

```bash
mkdir -p runs/videos/unlink_c_ring

# 1. 只验管线，不跑物理
python -m demos.entangle.unlink_c_ring_physical_extract_demo run.build_only=true \
  2>&1 | tee runs/videos/unlink_c_ring/extract_buildonly.log

# 2. 无头跑完整 episode
python -m demos.entangle.unlink_c_ring_physical_extract_demo run.verbose=true \
  2>&1 | tee runs/videos/unlink_c_ring/extract.log

# 3. 防捷径对照，预期判失败
python -m demos.entangle.unlink_c_ring_physical_extract_demo run.verbose=true \
  run.oracle_mode=no_align 2>&1 | tee runs/videos/unlink_c_ring/extract_no_align.log

# 4. 成功 episode 三视角录像
python -m demos.entangle.unlink_c_ring_physical_extract_demo \
  recording=default 'recording.camera=[oblique,front,wrist]' \
  recording.path=runs/videos/unlink_c_ring/extract.mp4 \
  2>&1 | tee runs/videos/unlink_c_ring/extract_record.log
```

通过标准：

| 步骤 | 期望 |
|---|---|
| 1 | 场景与原语构造完成即退出，无异常 |
| 2 | ` success=True`；`Lk` 由 ±1 变 0；`passed_through=False`；六个方向 `travel_free=True`；`release_stable=True` |
| 3 | ` success=False`，`failure_reason` 为 `c_ring_passed_through_the_closed_ring` |
| 4 | 三段视频里看得清「转 90° 对准开口 → 下移脱出 → 移开」，HUD 上 `Lk` 在脱出那一刻由 ±1 跳到 0 |

**主风险读数**：第 2 步的 `wrist_tilt`。若明显大于零，说明 IK 没跟上 90° 重定向，
demo 会直接打 warn 并给出退路。两条退路按顺序试，每次只改一个量：

1. `task.primitive.grasp_ee_quat` 预偏 −45°，手腕行程对半分（起 −45°、终 +45°），
   转完后手心还更高；
2. `task.c_ring.gap_azimuth_deg` 由 90 改到 45~60，需要的滚转同步减小。这条**现在才安全**
   ——§6.4 已证明摩擦把开口钉在出生方位，离管身 45° 仍远大于开口半角 21.5°。改完要重跑
   两条离线 gate。

第 4 步的录像同时覆盖 §6.3 那条尚未跑的 inspect 观感确认。

---

## 10. 未决事项

1. ~~**凸台是否承担稳定作用**~~ —— 已答：不承担，见 §6.4。凸台长度因此完全由抓取需要决定，
   与质心无关；确定抓取点之后可以顺带重估，整组几何也能压低（第 3、4 条不等式都会松出来）。
2. **摩擦裕度的边界**。`add_rigid_assembly` 的 `contact_friction` 目前取默认值 1.0，
   未作为配置暴露。若后续把它调低或让随机化改变 C 环质量，§2.3 的 15 倍裕度要重算，
   届时凸台的作用才会显现。
3. ~~**抽出原语的形态**~~ —— 已答：新写 `primitives/gateway_extract.py`，理由见 §8.1
   （`AxialInsertPrimitive` 的对准式在绕自身法向滚转时恒等于零，改不出来）。
4. ~~**抓取点**~~ —— 已答：环身方位角 135°，见 §8.1 与 task 配置的 `primitive` 块。
   约束不是「哪里好抓」而是「转完之后手在哪」。
5. ~~**手腕 90° 重定向能否跟上**~~ —— 第三轮改平放形态后不再是风险：转轴与工具轴重合，
   滚转落在 joint 7 上（§2.2）。跟踪误差读数保留，作为兜底。
5b. **手的净空没有自动判据**。五条布局不等式量的是 C 环，量不到手——第三轮改形态正是
   因为 gate 全过而 viewer 里机械臂被卡住。目前靠形态本身保证（头顶无结构、侧向进出），
   要真正补上得把夹爪包络也纳入 gate，本轮未做。
6. **`min_finger_qpos` 阈值未定**。首轮留 `null`：assisted carry 下它是唯一能区分
   「夹到环」与「合于空处」的读数，但阈值要先量出实际值再回填。与 `bar_through_hole`
   §7 第 5 条同一件待办。
7. **随机化**。`task_taxonomy_zh.md` §4.4 只对 C4 类强制要求注册随机化条目，本任务属 C3，
   非强制。可随机的轴有 `stand.yaw_deg`、`c_ring.gap_azimuth_deg`、环心 xy。
   `gap_azimuth_deg` 的范围受两头夹：摩擦既然会把开口钉在出生方位，随机化就直接决定了
   每个 episode 的初始方位，下限要避开开口半角 21.5°，上限受第 5 条的手腕行程约束。
8. **benchmark 产物资格**。仍缺 `generation/unlink_c_ring_generator.py`：本轮的
   `oracle_mode=no_align` 是对照**动作**，不是对照**数据集**。按 `task_taxonomy_zh.md`
   §4.0，缺可执行 contrast pair 生成器的任务不得进入 benchmark 产物。
