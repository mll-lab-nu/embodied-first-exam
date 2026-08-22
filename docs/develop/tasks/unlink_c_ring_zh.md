# docx 3.4 C 形环从固定圆环中解开 —— 基础场景建设

> 日期：2026-08-22（同日补入 GPU 实测结果与由此产生的一处结论修正）
> 上游：`../TopoGym_tasks.docx` §3.4
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置，
> §4.5 为落地后的形态表、§7 第 3 条为碰撞精度前置验证的结论）、
> `../framework/task_taxonomy_zh.md` §4.3（C3 entangle 判定契约）
>
> 目标模块：`topogym/tasks/entangle/unlink_c_ring.py`

---

## 0. 结论摘要

- 本轮交付边界为**场景与几何验证**：场景可载入、可静置、可观察，且
  `rigid_first_track_zh.md` §7.3 要求的碰撞精度前置验证已完成。
  verifier、六自由度抽出原语、physical demo 不在本轮。
- 几何一侧的风险已消解。八条非 gateway 轨迹全部卡住，且**每一条都由两环的互锁本身卡住**
  （最深处 8.75–9.00mm），支架只是先碰到；gateway 轨迹全程净空为正、终态解链。
- 相对规划新增两项设计，理由见 §2.2 与 §2.3：支架取**立柱 + 水平悬臂**，C 环带**径向抓取凸台**。
- **gateway 只有一条**。反向转 90° 后向上抽会被闭合环的另一侧挡住，不存在镜像解。
- 求解器一侧已验证（2026-08-22，Genesis 1.2.1，CPU 后端）：600 步静置 `Lk` 恒为 −1，
  开口方位漂移 0.6°，每步 1ms。四项检查全部通过，明细见 §6.2。
- **一处结论修正**：维持互锁的是悬挂接触处的库仑摩擦，不是抓取凸台。此前
  「凸台不加环就自行脱落」的论断漏算了摩擦，见 §2.3。凸台保留，但理由改了。

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

**结论**：凸台不是维持互锁的原因。保留它的理由改为两条——它是夹爪的抓取特征（仓库在
untangle 与 cable_routing 里已经用刚性 handle 作为抓取件），以及接触一旦变滑时的裕度。
是否缩短它是可选项，见 §7 第 1 条。

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
读数应当原样成立；确认用的重跑列在 §6.3。

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

### 6.4 待跑：凸台对照

判定凸台是否承担稳定作用（§7 第 1 条）。只改凸台长度，其余不动；五条不等式在该取值下
仍然成立（凸台离桌面由 8.0mm 放宽到 22.0mm）。

```bash
python -m demos.entangle.unlink_c_ring_inspect_demo run.verbose=true \
  task.c_ring.tab.length=0.006 \
  2>&1 | tee runs/videos/unlink_c_ring/hold_tab6.log
```

判读末行的 `min_opening_to_bar`：

| 读数 | 结论 |
|---:|---|
| 仍在 ~90° | 摩擦是唯一机理，凸台不承担稳定作用；它可以纯按抓取需要定尺寸，整组几何还能压低 |
| 落到 ~39° 附近 | 重力矩在起作用，凸台长度是有效旋钮，保持 0.020 |

39° 是按 `_link_xml` 的包围盒质心模型算出的预测值。同一模型在凸台 20mm 时预测 79°，
而实测是 90.2°，两者不符正是「摩擦压过重力矩」的证据；缩到 6mm 后预测值挪了 51°，
远大于测量噪声（600 步里开口方位的总起伏 0.6°），因此一次运行就能分开两种解释。

---

## 7. 未决事项

1. **凸台留多长，或是否保留**。§2.3 的实测说明它现在不承担稳定作用。对照命令与判读见
   §6.4。若确认摩擦是唯一机理，凸台可按抓取需要单独定尺寸，整组几何也能压低（第 3、4 条
   不等式都会松出来）。在抓取方案定下来之前不动它。
2. **摩擦裕度的边界**。`add_rigid_assembly` 的 `contact_friction` 目前取默认值 1.0，
   未作为配置暴露。若后续把它调低或让随机化改变 C 环质量，§2.3 的 15 倍裕度要重算，
   届时凸台的作用才会显现。
3. **抽出原语的形态**。轨迹已量出，待写规格：是给 `AxialInsertPrimitive` 加一个
   「不释放、反向」的分支，还是新写 `primitives/gateway_extract.py`。
   按 `../CLAUDE.md` §3，等真要复用时再决定。
4. **抓取点**。C 环靠近机器人的那半圈从上方无遮挡，凸台朝下且末端离桌面 8mm。
   夹爪是捏管身还是捏凸台，要在 viewer 里看过手部姿态之后再定。
5. **随机化**。`task_taxonomy_zh.md` §4.4 只对 C4 类强制要求注册随机化条目，本任务属 C3，
   非强制。可随机的轴有 `stand.yaw_deg`、`c_ring.gap_azimuth_deg`、环心 xy。
   `gap_azimuth_deg` 的范围受第 1、2 条约束：摩擦既然会把开口钉在出生方位，随机化就直接
   决定了每个 episode 的初始方位，范围要避开开口半角 21.5° 以内。
