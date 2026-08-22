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
- 第二轮补上抽出原语、verifier、自由平移探针与 physical demo，目标是一段判定为成功的
  完整 episode 录像（§8）。代码已落地、离线 gate 全过，**GPU 未跑**。
- 几何一侧的风险已消解。八条非 gateway 轨迹全部卡住，且**每一条都由两环的互锁本身卡住**
  （最深处 8.75–9.00mm），支架只是先碰到；gateway 轨迹全程净空为正、终态解链。
- 相对规划新增两项设计，理由见 §2.2 与 §2.3：支架取**立柱 + 水平悬臂**，C 环带**径向抓取凸台**。
- **gateway 只有一条**。反向转 90° 后向上抽会被闭合环的另一侧挡住，不存在镜像解。
- 求解器一侧已验证（2026-08-22，Genesis 1.2.1，CPU 后端）：600 步静置 `Lk` 恒为 −1，
  开口方位漂移 0.6°，每步 1ms。四项检查全部通过，明细见 §6.2。
- **一处结论修正**：维持互锁的是悬挂接触处的库仑摩擦，不是抓取凸台。此前
  「凸台不加环就自行脱落」的论断漏算了摩擦。缩短凸台的对照（§6.4）确证了这一点：
  预测静止方位挪 51°，实测挪 0.04°。凸台保留，但只作为抓取特征。
- **支架朝向 2026-08-22 由 `+x` 改到 `+y`**，立柱由 24mm 改细到 16mm，理由见 §2.2。
  连带发现写死的投影矩阵会随之失效，改为由布局导出，见 §1.2。

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

不写死的理由是实测出来的：整组场景随 `stand.yaw_deg` 转，此前写死的矩阵在 yaw=0 时正确，
改到 yaw=90 后正好沿着 C 环自身的平面看过去，出生读数变成 `Lk = -2`，由
`tests/check_c_ring_clearance.py` 当场拦下。导出式在 yaw = 0 / 30 / 45 / 90 / 135 / 180 / 270
七个取值上复核过，出生 `|Lk| = 1`、gateway 终态 `Lk = 0`。

---

## 2. 场景设计

坐标为 task 系：原点在桌面中心，`z=0` 是桌面，`+x` 远离机器人，`+y` 在机器人左侧
（`../../../configs/GEOMETRY_PARAMETERS_zh.md`）。

### 2.1 整体形态

`stand.yaw_deg = 90`：立柱在环的 `+y` 侧，即机器人的左手边。两个正交视角合起来说明全貌。

```text
沿 -y 看（oblique 一侧）              沿 -x 看（front 相机方向）

     ┌────────█  悬臂 / 立柱             ┌───────────█  悬臂 / 立柱
    ╭─┴─╮        （都在 +y，画面外）      ╭┴──────╮
   │  ○  │  闭合环（环面 xz）            │   ┃    ╰─ 开口（43°，朝 +y）
    ╰─╥─╯                              │   ┃     │  C 环（环面 yz）
      ║    C 环边对边，只见一条竖线        ╰───┬────╯   ┃ = 闭合环边对边
      ╨    凸台                             │ 凸台
 ══════════════════ 桌面              ══════╧═══════════ 桌面
   x=0.060                              -y ←  0  → +y
```

- 立柱竖直落在桌面上，在环心的 `+y` 侧 80mm 处。
- 悬臂水平，从立柱顶端伸向环心，方向由 `stand.yaw_deg` 给。
- 闭合环挂在悬臂末端，**环面与悬臂方向垂直**，悬臂接到环的最高点。
- C 环套在闭合环的下缘管身上，环面为 yz 面，开口朝 `+y`，凸台朝下。

立柱与悬臂是两个无关节的凸圆柱，直接 `scene.add_entity(gs.morphs.Cylinder(fixed=True))`，
不走 URDF：它们不动，彼此之间也不动，只有 C 环需要「多段几何、一个位姿」。

### 2.2 支架为什么取悬臂

规划阶段未定。若闭合环直接坐在立柱上，C 环的全部活动包络（悬挂、绕管轴转 90°、抽出、
落下）都紧贴立柱，任何一次卡住都要先排除「是不是撞到立柱了」。悬臂把闭合环牵出去
80mm，使立柱在整个任务里一次也不参与接触。

环面取垂直于悬臂而不是与悬臂共面：这样 C 环面就包含悬臂方向，C 环沿管轴平移是往侧向走，
彻底离开立柱所在的那条线。

**朝向取 `+y`（2026-08-22 由 `0` 改）**。最初把立柱放在桌子远端（`yaw_deg = 0`），录像
出来才发现 `front` 相机架在 `+x` 看回机器人，视线正好沿着悬臂的轴线过来，悬臂与立柱在画面里
叠在两环正前方，看不出夹爪在对什么动作。转到 `+y` 后 `front` 相机正对 C 环的环面（法向
`±x`），支架整根移出视线。

取 `+y` 而不取 `-y`：`oblique` 是默认录制机位，架在 `(1.00, -0.80)` 即 `-y` 侧；支架放 `+y`
落在两环背后，放 `-y` 会挡在前面。

对夹爪没有代价。悬臂只占 `y >= 0`，`-y` 侧那半圈从上方无遮挡；而 C 环实心的那半圈正在
`-y` 侧（开口在 `+y`），且管身在该处沿竖直方向——指尖朝下、水平合爪即可捏住。净空性质与
`yaw_deg = 0` 时相同，整组只是绕 `z` 转了 90°。

立柱同时由 24mm 直径改细到 16mm：它不承任何力，细一些画面里少挡东西。该值不进入任何判据
——`top_z` 按轴向端面加半径乘倾角算，竖直立柱的半径不抬高轮廓。底板随之由 1.6 倍放到
2.5 倍（40mm），否则 16mm 的杆配 26mm 的底板撑不住 139mm 的高度。

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

**结论**：凸台不维持互锁。保留它的理由只剩两条——它是夹爪的抓取特征（仓库在 untangle 与
cable_routing 里已经用刚性 handle 作为抓取件），以及接触一旦变滑时的裕度。长度因此改由
抓取需要决定，不再由质心计算决定；在抓取方案定下来之前保持 0.020。

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
| 闭合环 `major_radius` | 0.030 | 与环心高一起受 home 位净空约束 |
| 闭合环 `tube_radius` | 0.004 | 管细则开口不必开得大 |
| 闭合环 `center` | [0.060, 0, 0.109] | z 由 C 环静置高反推 |
| C 环 `major_radius` | 0.030 | |
| C 环 `tube_radius` | 0.005 | |
| C 环 `gap_deg` | 43.0 | 开口净宽 11.99mm |
| C 环 `gap_azimuth_deg` | 90.0 | 从环的正上方起算；0° 即管身所在处 |
| 凸台 `azimuth_deg / length / radius` | 180 / 0.020 / 0.005 | 与开口成 90° |
| 两处 `segment_deg` | 10.0 | 36 / 32 段，弦高 0.114mm |
| `stand.yaw_deg` | 90.0 | 立柱在 `+y`，让开 `front` 与 `oblique` 两个机位，见 §2.2 |
| `stand.arm_length` | 0.080 | > C 环外半径 + 净空 |
| `stand.post_radius` | 0.008 | 不承力，只影响观感；不进入任何判据 |
| `c_ring.spawn_drop` | 0.002 | 静置位是零间隙，出生时抬高再落下 |

导出量（由 `_c_ring_geometry.scene_geometry` 单点算出，配置里不重复写）：

| 量 | 值 | 定义 |
|---|---:|---|
| 孔间隙 `hang_offset` | 21.0mm | C 环挂上去时环心低于管心的距离 = C 孔半径 − 闭合环管半径 |
| 抽出行程 `extract_travel` | 18.0mm | 管身从贴住孔内缘到脱出外缘 = 2 ×（两管半径之和） |
| C 环静置环心高 | 0.058 | 管心高 − `hang_offset` |
| C 环下缘离桌面 | 23.0mm | |
| 凸台末端离桌面 | 8.0mm | |
| 场景最高点 | 0.145 | 悬臂顶。home 位指尖在 task z 0.1608，余量 15.8mm |

五条不等式互相咬合，改任何一条都要重跑 §6 的离线 gate：

1. 开口能过环身：`gap_clear_width > 2 × 闭合环管半径` —— 11.99 > 8.00mm
2. C 环套得进管身：`hang_offset > 0` —— 21.0mm
3. 抽出时不撞桌面：`静置环心高 − 抽出行程 − C 环外半径 > 余量` —— 5.0 > 4.0mm
4. 静置时凸台不触桌：`静置环心高 − (major_radius + 凸台长) > 余量` —— 8.0 > 4.0mm
5. reset 时不撞机械臂：`home 指尖高 − 场景最高点 > 0` —— 15.8mm

第 5 条与 `bar_through_hole` 的 `panel.top_z` 同一条余量：高于 home 指尖的结构会在
reset 的 `set_dofs_position` 瞬移里被扎进去，`stacked_plate` 当初由此出过求解器 NaN。
当前取值不需要任务专属的抬高 home 配置。

`UnlinkCRingLayout.validate()` 在 build 时复查这五条，不通过直接抛错——配置覆盖若把场景
改到不自洽，停在这里而不是几百步之后的求解器 NaN。

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
| gateway | gateway 轨迹全程净空为正且终态解链；八条非 gateway 轨迹全部卡住 |

「卡住」的阈值取 1mm 穿透。两链最深的弦近似误差是 0.114mm，非 gateway 轨迹实测穿透
8.75–9.00mm，1mm 把两者分得很开。

### 4.1 实测结果（2026-08-22）

```text
fit        开口余量 11.99 > 8.00mm；套入余量 21.0mm；抽出后离桌 5.0 > 4.0mm；
           凸台离桌 8.0 > 4.0mm；home 余量 15.8mm
fidelity   闭合环 36 段、C 环 32 段 + 1 凸台，两者弦高均 0.114mm；
           开口对 8mm 管身单边留 2.00mm，是弦高的 18 倍
reading    静置净空 -0.092mm（接触，量级即弦高）；出生净空 +1.895mm；
           视线 (-0.707, +0.707, 0)（两环法向的角平分线）；出生 Lk = +1.0
gateway    对准开口 → 下移 18mm → 沿管轴移开：环间 -0.15mm、支架 +17.00mm、终态 Lk = 0
```

`Lk` 的符号取决于投影基的手性，判据看的是 `|Lk|`。2026-08-22 把立柱转到 `+y` 之后视线随之
改变，符号由 −1 变为 +1，互锁本身没有变。

八条非 gateway 轨迹（括号内为仅计两环互锁时的最深穿透）：

方向按管轴而不按世界轴命名——整组随 `stand.yaw_deg` 转，管轴当前沿 `±x`。

| 轨迹 | 卡住位置 | 先碰到 | 互锁单独 |
|---|---:|---|---:|
| 反向转 90° 再抬起 | 71% | 支架 | −8.75mm |
| 不转直接下移 | 1% | 闭合环 | −8.79mm |
| 不转直接上移 | 41% | 支架 | −9.00mm |
| 沿管轴平移（正向） | 6% | 闭合环 | −8.99mm |
| 沿管轴平移（反向） | 6% | 闭合环 | −8.99mm |
| 横向平移（正向） | 6% | 闭合环 | −8.99mm |
| 横向平移（反向） | 6% | 闭合环 | −8.98mm |
| 提起后搬走 | 21% | 支架 | −9.00mm |

最后一列是关键：三条轨迹是支架先碰到，但**每一条都由两环的互锁本身卡住**，支架并非
任何一条的唯一阻挡。防捷径成立于互锁，不成立于摆件。

负对照：`--gap-deg 30` 时开口净宽降到 5.53mm，第 1 条不等式与 gateway 轨迹同时判失败，
退出码 1。

### 4.2 gateway 只有一条

反向转 90° 把开口转到管身下方后向上抽，在几何上也是一条闭合方案上的通路，但实测在 71%
处被挡住：C 环需要向上走完整个孔径再脱出，途中撞上闭合环的另一侧。因此本任务不存在
镜像解，成功轨迹的旋转方向是唯一的。

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
python tests/check_c_ring_clearance.py --gap-deg 30    # 负对照，退出码 1
python topogym/core/taxonomy.py                        # 分类表与目录一致
python tests/check_demo_configs.py                     # 19 个 demo，四项检查全部无命中
```

### 6.2 求解器（项目 venv，2026-08-22 已跑）

环境：Genesis 1.2.1，`.venv-gs121`，`env.genesis.backend` 默认取 cpu（AMD Ryzen 9 7950X）。

**这一组读数取自支架改动之前的布局**（`yaw_deg = 0`、立柱 24mm）。两环与桌面的相对关系在
改动中没有变——整组绕 `z` 刚性旋转，重力沿 `z` 不变，而支架自始至终不参与任何接触——所以
读数应当原样成立。§6.4 那一跑在新布局上取得同样的结论，这条推理已被证实。

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

### 6.3 待跑：观感确认与改动后重跑

第一次录像（`yaw_deg = 0`）暴露了两个问题：`front` 相机的视线沿着悬臂轴线过来，支架把两环
整个挡住；立柱也偏粗。§2.2 的改动针对这两点。下面这条既确认观感，也顺带在新布局上重跑
§6.2 的静置判据：

```bash
mkdir -p runs/videos/unlink_c_ring

python -m demos.entangle.unlink_c_ring_inspect_demo \
  recording=default 'recording.camera=[oblique,front,wrist]' \
  recording.path=runs/videos/unlink_c_ring/look.mp4 \
  2>&1 | tee runs/videos/unlink_c_ring/look.log
```

多机位要写列表 `[a,b,c]` 而不是逗号串：Hydra 把裸的 `recording.camera=oblique,topdown` 判为
歧义并直接报错（`topogym/utils/recording.py` 的 `_recording_camera_names` 两种都收，但请求
到不了那里）。录制器按 `<stem>_<相机名>.mp4` 拆开，产出三个文件：

三视角固定取 `oblique` / `front` / `wrist`（本项目的约定）：

| 文件 | 机位 | 看什么 |
|---|---|---|
| `look_oblique.mp4` | task (1.00, −0.80, 0.50) 斜俯视，默认录制机位 | 整体观感；支架在 `+y`，应落在两环背后 |
| `look_front.mp4` | task (0.42, 0, 0.38)，站在机械臂正前方面朝它俯视 | C 环环面正对镜头，开口与凸台朝向可辨；支架应完全不在画面中央 |
| `look_wrist.mp4` | 挂在 hand 连杆上，随夹爪走 | home 位下 C 环是否已在夹爪视野内——这关系到 §7 第 4 条的抓取点怎么定 |

本 demo 机械臂全程停在 home 位，`wrist` 因此是一张静止画面；它回答的不是运动过程，
而是"从 home 位看出去够不够得着"。

同时看日志末行的 `min_abs_Lk` 与 `min_opening_to_bar`，应与 §6.2 一致（1.00 / ~90°）。

用默认 600 步跑，片长约 20 秒；只想要短片就加 `run.hold_steps=200`（约 6.7 秒），
但静置判据仍以 600 步那次为准。录像不能与 `run.static_only=true` 同用——那一档一步不走，
录出来是空的。要更高分辨率把 `recording=default` 换成 `recording=hq`（1280×1280 + 抗锯齿），
`recording.path` 仍须单独给，否则会覆盖别的录像。视频路径的父目录由录制器自动建
（`save_to.parent.mkdir(parents=True)`），但 `tee` 的日志路径不会，所以那条 `mkdir -p`
是给日志用的。

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

原语还**自测跟踪误差**：`move_ee_to` 不报残差、不校验可达性（`cloth_corner_fold.py:213`），
而 90° 水平轴重定向在仓库里没有先例，所以每个 waypoint 记 `‖hand_pos − 指令‖` 与姿态夹角，
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
python -m demos.entangle.unlink_c_ring_physical_extract_demo run.build_only=true   2>&1 | tee runs/videos/unlink_c_ring/extract_buildonly.log

# 2. 无头跑完整 episode
python -m demos.entangle.unlink_c_ring_physical_extract_demo run.verbose=true   2>&1 | tee runs/videos/unlink_c_ring/extract.log

# 3. 防捷径对照，预期判失败
python -m demos.entangle.unlink_c_ring_physical_extract_demo run.verbose=true   run.oracle_mode=no_align 2>&1 | tee runs/videos/unlink_c_ring/extract_no_align.log

# 4. 成功 episode 三视角录像
python -m demos.entangle.unlink_c_ring_physical_extract_demo   recording=default 'recording.camera=[oblique,front,wrist]'   recording.path=runs/videos/unlink_c_ring/extract.mp4   2>&1 | tee runs/videos/unlink_c_ring/extract_record.log
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
5. **手腕 90° 重定向能否跟上**（新的主风险）。仓库里没有这个量级的先例，`move_ee_to`
   也不报残差，因此原语自测 `worst_pose_error` / `worst_tilt_rad`。GPU 未跑，
   判据与两条退路见 §9。
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
