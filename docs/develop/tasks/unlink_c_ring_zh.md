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
| `bash_scripts/tests/unlink_c_ring_variation_sweep.sh` | 变体 sweep：visual / oracle / no_align 三组（§11，2026-09-03） |
| `tests/check_variant_rng.py` unlink 段、`tests/check_variant_corners.py` `TASKS` 登记 | 变体离线门：1000 seed 拒绝率、32 角点（§11.3） |
| `bash_scripts/tests/variant_corners_sweep.sh` unlink 分支 | 角点送进物理 |

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
linkbar 首版的 `tasks/connectivity/_travel_probe.py`（2026-08-27 随小车删除）：**施力而不是写位姿**，力按自重的倍数给，同时报
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
7. ~~**随机化**~~ —— 已做：见 §11（2026-09-03）。五条连续轴 + 抓取方位角派生，`gap_azimuth_deg`
   取 315 ± 10，收窄的原因是新加的手净空行，不是这里原先担心的开口半角或手腕行程。
8. **benchmark 产物资格**。仍缺 `generation/unlink_c_ring_generator.py`：本轮的
   `oracle_mode=no_align` 是对照**动作**，不是对照**数据集**。按 `task_taxonomy_zh.md`
   §4.0，缺可执行 contrast pair 生成器的任务不得进入 benchmark 产物。

---

## 9. 第三轮：轨迹从「转出来」改成「滑出来」（2026-08-23）

第二轮的 demo 能跑满 14 个相位、对准做到 0.96°、指面真夹住（`finger_qpos=0.0052`），
但 `passed_through` 始终不过：`min_gap_seen = -9.00mm`，恰好是互锁本身的重叠深度。

### 9.1 定位

给每一行阶段日志加上当前的最小间隙之后，位置一目了然：

| 阶段 | `min_gap` |
|---|---|
| regrasp / hover / descend | −0.0001 m |
| grasp | −0.0018 m |
| **turn** | **−0.0090 m** |
| extract / clear / place | −0.0090 m（不再变化） |

是转动那一段把环压穿的。同时新加的 `part_drift` 给出量级：转动期间环心偏离预定位置
**54.9mm**。

### 9.2 机制：134mm 的杠杆

夹爪原点在指面后方 `HAND_TO_PAD_Z = 103mm`，因此从手原点到环心的 `offset_in_hand`
是 **134mm**，不是环半径 55mm。手腕每 1° 姿态误差就是 2.3mm 的环心位移。而管身只在
环缘内侧 9mm（`R_c − hang = 55 − 46`）。

要把环心位移压进 9mm，腕部姿态需准到 `asin(9/134) = 3.85°`。实测控制器在**静止悬停**
时姿态误差就是 **14.28°**，差 3.7 倍。

用 `align_steps` 160 → 1600 的十倍对照排除了「跟踪滞后」这个解释：滞后 12.16° → 12.58°，
`min_gap` −9.00mm → −8.65mm，基本不动。误差不随速度变化，是这个位形下的稳态精度，
放慢消不掉。

### 9.3 改法：让环平移而不是自转

管身穿过 C 环平面于一点。保持环的朝向不变、把环心绕该点沿一段弧移动，管身相对于环
同样从「正上方」走到「缺口处」——相对运动与自转完全相同，拓扑内容相同。手腕全程不转，
那个恒定的 14.28° 在抓取测 `offset_in_hand` 时就被吸收，不再放大成环心位移。

精度要求由此从「腕部 3.85°」换成「手部位置约 1mm」，后者与实测静置精度 2.4mm 同量级。

| 量 | 值 |
|---|---|
| 环心行程 | 36.1mm（8 段弦，每段 4.51mm） |
| 抽出方向 | 沿缺口方向的反向，`(+0.707, 0, +0.707)`，不再是 −z |
| 弧的分段 | 1 段弦向内切 3.35mm、2 段 0.845mm、4 段 0.212mm、**8 段 0.053mm** |

**弧不能用直线弦代替**：单段弦的向内偏差 3.35mm 超过整个余量。`apply_phases` 没有
弧原语也不需要——弧就是这么多段短平移。

`slide_waypoints` 与 `extract_direction`（`_c_ring_geometry.py`）是这段几何的唯一出处，
离线 gate 与运行时原语都从它取，不会漂开。

### 9.4 变体可解性

离线扫过 18 组（R_c ∈ {45,55,65}mm × R_f ∈ {55,70}mm × gap ∈ {23,30,40}°）：
只有「缺口塞不下管身」的两组不可解（R_c=45 且 gap=23，单边余量 −0.03mm），而那条
约束与轨迹无关，本来就是 §3 的 `opening clears the bar`。**平移方案没有引入新的
可解性限制。**

### 9.5 gateway 从两条变成一条

自转有两条镜像解（开口转朝上后下移、转朝下后上抬），因为转动同时改变了开口在世界系里
的朝向。平移下环不转，开口的世界方向固定，**能让管身落在缺口上的环心只有唯一一点**，
于是只有一条 gateway。

剩下的唯一替代是「沿弧的另一侧绕过去」，终点相同、路径不同。实测它在 19% 处被**立柱**
挡住（1.01mm 深），而互锁本身只有 −0.20mm——也就是说这个方向的唯一性由支架保证，
不是由互锁保证。这一条现在由 `check_c_ring_clearance.py` 单独一节打印出来，不再隐含。

### 9.6 两条更正

本轮推翻了自己先前的两个判断，记在这里免得再犯：

1. **「平移余量 1.79mm、比自转的 0.15mm 宽 12 倍」不成立。** 1.79mm 是从**出生位**
   （比静置位高 `spawn_drop` = 2mm）量出的假象。C 环静置时就挂在管身上、接触间隙为零
   （`hang = R_c − r_c − r_f` 的定义即相切），gate 里的 −0.20mm 是分段圆柱链的离散
   底噪，任何从静置位出发的轨迹都带这个数。平移方案的理由**只有** §9.2 的误差放大
   一条，但这条是硬的。
2. **「手腕做不到 45° 转动」的最初依据（`tilt=43deg`）不可用。** 那是在
   `hang_yaw_deg=270` 下取的，而那个配置需要 ±90° 腕部偏航、手在转动开始前就已有
   28.6° 误差。真正的障碍是 134mm 杠杆，不是转角本身。

### 9.7 顺带落地的执行链修正

这一轮之前逐个清掉的缺陷，都有实测支撑，一并记录：

| 改动 | 症状 | 实测依据 |
|---|---|---|
| `stand.hang_yaw_deg` 270 → 180 | 抓不住、环被撞歪 | 270 需 ±90° 偏航，手姿态误差 28.6°，指面偏出 `0.1029×sin(28.6°)=49mm` |
| 悬停后按实测环姿重算抓取位姿 | 抓取点过期 | `regrasp moved` 47.6mm → 0.4mm |
| 等到环真正停下再读姿态 | 读到还在动的零件 | 环绕竖直轴转动无恢复力矩，40 步不够；改成测到停为止，实测 25 步 |
| 接近改三段轴对齐（升→平移→落） | 斜线插值斜穿场景 | 悬停点本身离 O 环 90mm，是路径形状的问题 |
| 合拢前先焊住 | 合拢拨动环 | `disturbed` −30° → 0.08° |
| 探针越阈值即停推 | 推力把环加速到 3.6m 后穿模误报 free | `probe_uninformative` 消失 |
| `opening_to_bar_deg` 改在环平面内测 | 沿管轴的无害滑动被算成偏差 | 环在目标姿态（残差 0.07°）却报 10.1° |

### 9.8 负对照的正确参数

`check_c_ring_clearance.py` 的负对照是 **`--gap-deg 18`**（单边余量 −0.40mm，
`opening clears the bar` 判失败）。此前 docstring 里写的 30 是错的——缺口越宽越容易过。
20°（+0.55mm）与 30°（+5.24mm）都通过。

### 9.9 第四轮：弧线换两段直线（2026-08-23 深夜）

§9.3 的弧线方案落地后仍差最后 2mm 不过，逐段读数（`slide0..15`）指认根因：环挂在
管身上时**贴着管身**滑，走廊宽度为零，手在该位形下的 6mm 稳态位置误差没有任何余量
吸收。为此叠出的四层机制——弧拆弦、抬升拆段、每段静置 100 步、指令积分补偿——都是
在给零走廊买单，最好也只做到 −1.2mm。

正确做法是人手摘钥匙圈的做法：**先提、再摆、后抽**。环内腔半径 50mm、悬挂半径
46mm，竖直上提 d 之后，管身处在内腔中间，之后的一整段直线平移离管壁约 d。
`slide_waypoints` 重写为两段直线（上提 20mm → 直线摆到缺口内侧），实测对准段全程
净空 **19.8mm**，6mm 误差直接被吞掉；弦、段、长静置、积分补偿全部删除。
抽出段的 ±2mm 由缺口宽度决定，是任务本体，不是轨迹问题。

连带的结构变化：gateway 又收敛回**一条**（「沿弧另一侧绕」随弧一起消失）；
`check_gateway_slide_path.py` 的断言从「弦够不够细」改为「摆动段净空是否兑现了
上提量」（四个 `hang_yaw` 下均为 19.80mm）。

教训一条：走廊为零的路径不能靠控制精度去凑，要换一条有走廊的路径。前一版在
「贴壁滑」上连修四层是方向性错误，此轮由用户指出。

---

## 11. 变体轴与派生（2026-09-03，变体计划 §6.2 第 8 步）

按 linkbar / diverter / gate / band 的六项清单部署：yaml `variation:` 块、`checks()` 与派生钩子、demo 接线 + variant 行 + run 配置键、`check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测。
没有防捷径离散轴：开口不对准管身就卡住，由物理本身保证（`variation_axes_plain_zh.md` §3）。

### 11.1 轴

| 类 | 叶子 | 抽法 | 说明 |
|---|---|---|---|
| B | `stand.hang_yaw_deg` | uniform [165, 195] | 整组场景绕竖轴转。270 实测手腕位姿误差 28.6°（§9.7），不进包络 |
| B | `fixed_ring.center_x` / `center_y` | uniform [0.040, 0.080] / [0.035, 0.075] | 装置在桌上的位置。原 `center: [x, y, z]` 拆成三个标量键（随机化器不支持列表元素），z 不动 |
| B（难度候选） | `c_ring.gap_deg` | uniform [21.5, 28] | 开口张角。单边净空 R·sin(gap/2) − r_c − r_f = 1.26 / 1.97 / 4.31 mm（21.5 / 23 / 28） |
| B | `c_ring.gap_azimuth_deg` | uniform [305, 325] | 开口方位角。**±10 而非计划的 ±15**：抓取点 = 方位角 + 112.5°，手净空行（下表第 7 行）在 302.4° 以下失败，±15 约 8% 首抽被拒，超 2% 门 |
| B→C | `primitive.grasp_azimuth_deg` | derived = `gap_azimuth_deg + primitive.grasp_offset_deg`（112.5）mod 360 | `derive_task_cfg` 覆盖；固定布局仍用 yaml 的 67.5。抓取点跟着开口走，手指始终远离开口端帽；不到 90°（那里管身竖直，手腕偏航的推导退化） |
| D | 全部 z、两环半径、`tab.*`、`slide_lift`、`carry`、摩擦、`reach.*` | 不动 | |

### 11.2 `checks()` 七行

原五行不动，新加两行把 §10 第 5b 条「手的净空没有自动判据」和计划表的「补可达行」补上。两行都在 `SceneGeometry.checks()`（纯 numpy，两个离线门按路径导入），`UnlinkCRingLayout.checks()` 只是转发。

| 行 | 读数 | 门 | 默认布局 | 32 角点最紧 |
|---|---|---|---|---|
| opening clears the bar | 开口净宽 | > 2 r_f | 11.93 / 8.00 mm | +2.52 mm（gap 21.5） |
| C fits over the bar | 孔半径 − r_f | > 0 | 46.0 mm | +46.0 |
| ring clears the table after extraction | 静置中心高 − 抽出行程 − 外半径 | > 4 mm | 6.0 / 4.0 | +2.0 |
| post clears the C ring | 立柱面到 C 环最外点 | > `stand.clearance` 8 mm | 42.0 / 8.0 | +34.0 |
| stand clears the home pose | home 指尖 z − 场景顶 | > 0 | 26.8 mm | +26.8 |
| hand reaches the grasp point（新） | `reach.max_grasp_dist` − 抓取点到底座距离 | > 0 | 0.700 − 0.527 | +138.7 mm（yaw 165/195 + 远角） |
| hand clears the ring at the grasp point（新） | R_c·sin(grasp_az) − `HAND_HALF_WIDTH` 0.045 | > 0 | 50.8 − 45 = +5.8 mm | **+1.39 mm**（gap_az 305 → grasp 57.5°） |

`reach:` 段照 gate_cage_ball（`base_xy: [-0.570, 0.0]`、`max_grasp_dist: 0.700`）；`hang_yaw_deg 0` 的抓取点在 0.738 m，被这一行排除。
手净空规则来自 yaml `c_ring.major_radius` 的注释（手半宽 45 mm，量到环缘管中心线），以前只是文字。

### 11.3 离线实测（2026-09-03）

| 门 | 结果 |
|---|---|
| `tests/check_c_ring_clearance.py`（加第五段「variation envelope」） | 32 角点：七行全过、出生 Lk=±1、gateway 不卡且终态 Lk=0、八条非 gateway 全卡；负例：`gap_azimuth_deg=295` 手净空 −4.45 mm 拒、`hang_yaw_deg=0` 可达 0.738 m 拒；`--gap-deg 18` 仍 exit 1 |
| `tests/check_gateway_slide_path.py` | 不变，四个 `hang_yaw` 摆动段净空 19.80 mm |
| `tests/check_variant_rng.py` unlink 段 | 叶子顺序、seed 3 确定性、1000 seed 每轴在区间内、派生抓取角逐 seed 等于规则值、七行全过；最小手净空 1.41 mm、最小单边净空 1.26 mm；首抽拒绝率 **0.000** |
| `tests/check_variant_corners.py --task unlink_c_ring` | 32 角点 32 可行，Hydra compose 读数一致 |
| `tests/check_demo_configs.py`、`tests/check_configs_compose.py` | 全过 |
| CPU 冒烟 | `unlink_c_ring_inspect_demo env.genesis.backend=cpu run.build_only=true run.randomize_layout=true run.seed=3` 打出 checks 与 variant 行 |

### 11.4 GPU 实测（待跑）

**先复现基线。** 最近一次物理记录（`runs/videos/unlink_c_ring/fast_001128.log`，2026-08-24，§9.9 之后代码未动）`success=False`：
Lk +1→0、分离 14 cm、探针五向全通、释放稳定都对，唯一失败项是 `passed_through`——两环最小面间距 −2.63 mm，超 `topology.jam_depth` 1 mm。
按阶段（`[gateway_extract <phase>] min_gap=` 是累计最小值）：悬停 / 下降 −0.1 mm（手腕倾角 20.4°）→ 抓取 −0.5 mm → **抬升段 slide0 −2.6 mm**（倾角回到 0.7°）→ 之后沿用。
抬升时手腕把 20° 转回来，环被夹在指垫上跟着转，环心离抓点 55 mm，环内侧顶部在这一瞬间压到杆上——更像真实接触挤压，不像穿模。

判定规则（`run.randomize_layout=false run.seed=0 run.verbose=true recording=default`，gateway 与 no_align 各一次）：

- **判据口径问题**（照 gate_cage_ball `pinched` 的先例改判据），须同时满足：Lk 恰在 `extract` 阶段翻转一次且当时 `align_deg ≤ max_align_deg`；`extract` / `clear` 的 `part=` 位置与 `c_rest_frame.center − (extract_travel + slide_lift)·extract_direction` 再 `+ carry·hang_direction` 差几毫米以内；同布局 `no_align` 的最小间距在 −8 到 −9 mm 量级而 gateway 远小于它；穿透量是刚体接触的几毫米而非 9 mm 互锁。处置：新叶子 `success.max_pass_through_depth`（如 0.005）供判定器的 `passed_through` 读，`topology.jam_depth` 1 mm 留给离线 `sweep()` 与探针。两组数据记回本节。
- **轨迹 / 抓取问题**（不改判据）：Lk 在 `extract` 之前翻转或翻转时未对准；终点落在闭合环那一侧；gateway 最小间距逼近 no_align 的深度；或在 `descend` / `close` 就跌破且 `disturbed` > 10 mm（指垫压在管身上，修抓取）。

**基线复现（2026-09-03 晚，4090，`runs/unlink_c_ring_variation/baseline_*/`）**：gateway 与 no_align 的读数和 08-24 逐阶段一致。

| | gateway | no_align |
|---|---|---|
| 最小面间距首次跌破 −1 mm 的阶段 | 抬升段 slide0，−2.63 mm（手腕倾角 20.4° → 0.7°） | 抽出段 extract，−8.97 mm |
| 对准时开口到管身 | 2.65°（≤ `max_align_deg` 3.0） | 44.5°（从未对准） |
| extract / clear 后的环心 | 与「抬 20 → 摆 20 → 出 38 → 径向搬 90」的预期路径差 ≤ 2 mm | — |
| 其余判据 | Lk +1→0、分离、探针五向全通、释放稳定 | 同左 |
| 判词（`jam_depth` 1 mm） | success=False，`passed_through` | success=False，`passed_through` |

判定规则四条里能核的三条全部指向判据口径：终点在正确一侧、gateway 的 −2.6 mm 与 no_align 的 −9.0 mm 两群分得开、2.6 mm 是刚体接触受力时的穿透量级而非 9 mm 互锁（Lk 逐阶段没有日志，只有终值 0 与对准角可核）。
处置：判定器的 `passed_through` 改判新叶子 `success.max_pass_through_depth`（0.005，落在两群之间）；`topology.jam_depth` 1 mm 只留给离线 `sweep()` 与自由平移探针。改后 seed 0 重跑：gateway **success=True**（min_gap_seen 仍 −2.63 mm，`passed_through=False`），no_align 见下表。

之后：`bash_scripts/tests/unlink_c_ring_variation_sweep.sh visual oracle no_align`（seed 0–9）、`variant_corners_sweep.sh unlink_c_ring oracle visual`（32 格全跑）。纯刚体，一格秒级到 1–2 min。

**实测（2026-09-03 晚，4090，一格 8–18 s；`runs/unlink_c_ring_variation/20260903_202933/`、`runs/unlink_c_ring_corners/20260903_203647/`）**

| 组 | 结果 |
|---|---|
| 基线 seed 0 gateway / no_align（新判据） | gateway **success=True**；no_align success=False（−8.97 mm，`passed_through`），防捷径对照仍成立 |
| visual seed 0–9 | 10/10 有帧；开口朝向、装置角度、位置逐 seed 可分 |
| oracle seed 0–9 | **7/10**。三格失败全是原语的对准门 `align_failed`：seed 5 / 6 / 8 摆动后开口到管身 3.14 / 4.31 / 3.14°，门 `max_align_deg` 3.0。通过格全程最小面间距 −2.16 … −3.47 mm，都在 5 mm 门内 |
| no_align seed 0–9 | 10/10 判失败（`passed_through`，−8.84 … −9.00 mm）；与 gateway 的 −2 … −3.5 mm 两群分开 |
| 角点 32 格 visual | 32/32 有帧 |
| 角点 32 格 oracle | **16/32**：`gap_azimuth_deg=305` 的 16 格全部 `align_failed`（残差 3.7–5.8°），325 的 16 格全过（残差 0.4–1.9°）；与装置角度、位置、开口张角无关 |

**对准失败的机制。** 每格结果行里 `turn_pose_err`（环偏离两段直线终点的距离）都是 8.4–10 mm，基线 seed 0 也是 9.1 mm（demo 的 `[warn] strayed 9.x mm` 本来就在）。来源见 `gateway_extract.py` 的注释：两段直线在对准阶段开始时按抓取后的实测位姿算一次，之后不修正；每段走完环相对目标有 5.5–6 mm 的稳态落后，多沉降不缩。这个位置偏差的方向基本固定，摆动后「开口到管身」的角残差 = 偏差的垂直分量 / 环心到管身距离（约 45 mm）：开口方位角离偏差方向越远垂直分量越大，所以残差随出生时的开口角单调上升——34° 时 0.4–1.9°，45°（基线）2.65°，55° 时 3.7–5.8°。门 3.0° 在基线只有 0.35° 余量，包络一动就越界。
物理上 3–4° 过得去：seed 5 / 8 中止后跑探针，环在仍读作互锁的姿态下被 1.3 倍自重推出去了（demo 报 `[warn] the ring travelled freely while still reading linked`）。

**处置（用户选定：闭环修正摆动段，不改门、不收包络）。** `gateway_extract.py` 在两段直线走完后重测环心，把「目标 − 实测」加到命令点上再走一段（手臂是稳态落后，重发同一目标还会落后同样的量，所以要把命令点推过目标），最多 `primitive.align_correct_passes`（2）次，差值小于 `primitive.align_correct_tol`（2 mm）就停。日志多一行 `[gateway_extract correct0] miss_before=… behind=…`。
seed 0 固定布局：一次修正 5.4 mm → 0.1 mm，对准残差 2.65° → **0.28°**；305 那一角 5.5 mm → 0.2 mm，残差 **0.33°**，success=True。
修正后重跑（`runs/unlink_c_ring_variation/20260903_223337_correct/`、`runs/unlink_c_ring_corners/20260903_223715_correct/`）：oracle seed 0–9 **10/10**，残差 0.2–0.3°；角点 oracle **32/32**，残差 0.2–0.4°（修前 0.4–5.8°）；全程最小面间距 −2.16 … −3.47 mm，全在 5 mm 门内。no_align 与 visual 不受修正影响，沿用上表。
至此第 8 步六项齐全：oracle 覆盖包络内部与全部顶点，防捷径对照 10/10 判失败，两群面间距分得开。
