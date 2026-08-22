# docx 4.4 旋转连接杆合并两个组件 —— 工程记录

> 日期：2026-08-20 开工，2026-08-22 更新（场景形态定案，判据全过，执行层待复核）
> 上游：`../TopoGym_tasks.docx` §4.4
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置）、
> `../framework/task_taxonomy_zh.md` §4.4（C4 判定契约）
>
> 目标模块：`topogym/tasks/connectivity/linkbar_merge_components.py`

---

## 0. 结论摘要

- 场景取**桌面水平面 + 转臂工位 + 直轨小车**：连接梁绕竖直轴转，梁端的销插进两个同款插口
  之一；插进小车那个，两段合并。与 docx 图的竖直平面有几何差异，判定的不变量完整保留。
- 判据两层已全部跑通：约束图 `component_count` 三个相位读数正确，行程测试读出
  **0.0000 m 对 0.1002 m**。防捷径的四组合在离线与在线各验一次，oracle 4/4、
  `nearest_socket` 恰好 2/4。
- 仍未过的只有执行层：机械臂扫掠时指腹在手柄上打滑，梁差 5.03° 到不了位
  （`rotate_check_failed`）。原因已定位（§8.5），修改已落地，**待复核**。
- 对类别契约有一处偏离：物理复核由「提起测试」改为「行程测试」，理由见 §4.2。

---

## 1. 任务定义

### 1.1 docx 原文要点

| 项 | 内容 |
|---|---|
| 场景 | 左右两组刚性杆件分离；连接杆一端铰接于 A，只能绕枢轴旋转；B 的左端有插口 B1，A 自身立柱顶端有外观完全相同的插口 A2，两插口都位于连接杆的旋转圆上 |
| 动作 | 一次旋转：把连接杆自由端扣入某个插口，到位后由固定约束锁定 |
| 状态变化 | 接入 B1：β₀ 由 2 变 1；接入 A2：只在 A 内部新增一条 cycle 边，仍是两个组件 |
| 判定 | T̂ 直接读 latch 约束图，union-find 判组件数 |
| 物理复核 | 提起 A：合并成功则 B 被整体带起 |
| 防捷径 | A2 与 B1 同款、同在旋转圆上、动作成本完全相同，唯一区别是接口的全局归属；逐 episode 随机化两插口的角位置 |

### 1.2 与 docx 的三处差异

| 项 | docx | 本实现 | 理由 |
|---|---|---|---|
| 旋转平面 | 竖直平面 | 桌面水平面（铰链轴 +z） | 复用 4.3 已验证的 `PivotLeverPrimitive`（顶抓手柄 + 水平圆弧）；梁无重力下垂，插口角位置随机化只是改一个角度。4.1 与 4.3 已就同一取舍留下先例 |
| 组件 B 的形态 | 一组刚性杆件 | 直轨上的一节车厢 | 见 §2.2 |
| 物理复核 | 提起 A，看 B 是否被带起 | 推小车沿轨走，看是否被拉住 | 见 §4.2。**这是对 `task_taxonomy_zh.md` §4.4 的偏离，需在该文补一行** |

---

## 2. 场景形态

### 2.1 结构

```text
          A2 插口（支座顶起）
             ▣
              \      销的旋转圆 R=0.170
   ●━━━━━━━━━━━━▶ ▣═╤═════╤═  →  行程 0.100
  枢轴  连接梁      B1  车厢  直轨
  立柱                 ○   ○
```

- **组件 A（固定，三件 + 插口）**：枢轴立柱、一条通往 A2 的伸出臂底板、把 A2 顶到耦合
  高度的支座。伸出臂的方向随 `a2_angle_deg` 派生，因此 A2 在画面里始终结构上连着 A。
- **连接梁（一个铰链机构）**：梁体、转轴、轮毂、梁端垂下的销、供顶抓的手柄。关节为
  **continuous，不设限位**——圆上有两个插口，限位只能描述其中一个。
- **组件 B（可动，一个移动关节机构 + 视觉导轨）**：车厢台面、车厢体、四个轮子、车头的
  B1 插口，全部在同一个 URDF link 上。两条直轨与末端挡块是纯视觉件。

### 2.2 组件 B 为什么是导轨小车

初版把 B 做成自由刚体，靠摩擦与两块定位块待在原位。实测 2026-08-20：销蹭到插口就把它
推走 12.8 mm，再一次 14.5 mm——远超插口 4 mm 的单边间隙，而闩当时按标称座位判定，等于
在测一个已经不在那儿的座位。

改成移动关节上的小车之后，B 只有一个平动自由度：推不歪、转不动、蹭不走（改造后实测
`b_drift = 0.00 mm`）。同时判据变成**有界读数**：合并了车走不动，没合并就跑到行程末端，
是一个固定距离，而不是一个大小取决于推力设定的位移。

**导轨方向必须是径向。** 落座时连接梁正好沿导轨方向，梁以纯拉压受力，锁得最死；切向
导轨与销的圆相切，车能滑而梁角只有二阶变化，锁是软的。导轨方向由卡座角派生，因此这条
自动满足。

### 2.3 插口为什么是浅口袋

中间做过一版弧形分段槽（103 mm 长，底板与颚板按弧长切成三段）。原因是直槽导不了摆臂上
的销：170 mm 的弧在 55 mm 弦上偏离 12.9 mm，是间隙的三倍，实测把销卡死在离 A2 座位
22.44° 处、接触力 13.45 N。

浅口袋把这个问题消掉了：24 mm 的入口只偏 1.69 mm，对 4 mm 间隙余 2.31 mm，直的就够，
整套弧形分段代码不需要。咬合仍然是真的——销被两片颚板径向卡住，而销只能在圆上走，所以
推小车时径向力无处可去，**行程测试靠机械本身就成立**，weld 因此退回它该有的角色（docx
「到位后由固定约束锁定」），而不是唯一的受力路径。

### 2.4 耦合高度为什么定在台面

插口原来底面在 0.004，看起来是坐在地上的；而小车底盘由轮子架在 0.032。两个互相矛盾的
支承故事挂在同一个物体上，调颜色和调宽度都读不成一件东西。

整条链因此抬到**车厢台面的高度**：B1 自车头平伸出去、底下是空的（像车钩），A2 靠伸出臂
上的支座顶到同一高度。两个插口仍然在完全相同的高度上——它们必须如此，因为销只有一个;
而**托着它们的东西一个有轮、一个固定**，归属线索比同高时更强。

---

## 3. 机构与几何

### 3.1 高度链

单位米，task 坐标系（z=0 为桌面）。整条链由 `socket.floor_z` 定住，改它则全体跟着动。

| 层 | 区间 | 约束 |
|---|---|---|
| 轨 | 0.0000–0.0120 | 纯视觉 |
| 轮 | 0.0120–0.0320 | 半径 0.010，骑在轨顶；纯视觉 |
| 台面 | 0.0320–0.0440 | 底面 = 轮顶 |
| **插口** | **0.0440–0.0840** | 底面 = 台面顶 |
| 销 | 0.0520–0.0950 | 底面高出插口底面 8 mm；与颚板重叠 32 mm |
| 梁 | 0.0950–0.1150 | 底面高出颚板顶 11 mm，梁从任何插口上方扫过 |
| 手柄 | 0.1250–0.1750 | 抓取点 0.1500 |

`demos` 的 `heights` 行把这一列打出来，是判断「配置有没有同步到运行机器」最快的依据——
本轮因同步滞后误判过两次。

### 3.2 自变量与派生量

配置里只给自变量，其余由 `LinkbarMergeLayout` 派生：

```text
socket_center(θ)      = pivot + arm_radius · (cos θ, sin θ)
socket_yaw(θ)         = θ − 90°·sign(θ − init)          插口口部朝销来的方向
socket_half_width     = pin.radius + pin_clearance + jamb_thickness
outrigger 长度        = arm_radius − socket_half_width + neighbour_overlap
车厢起点              = socket_half_width − neighbour_overlap
capture_tolerance_deg = rad2deg(capture_tolerance_xy / arm_radius)
```

现值（`arm_radius=0.170`，`init=0°`，`b1=+55°`，`a2=−45°`）：B1 座位 (0.1175, 0.1393)、
A2 座位 (0.1402, −0.1202)、捕获窗 15 mm ≈ **5.06°**、手柄到 Franka 底座 0.690 m。

### 3.3 枢轴位置是被实测逼出来的

停在共用 home 位姿的手部实测在 (+0.043, −0.000, +0.267)。枢轴原为 −0.020 时，手部相对
枢轴的半径 0.063 而手柄圆是 0.100，张开的夹爪正好横跨手柄圆：四段扫掠里有三段顶在机械臂
上，接触力约 20 N，梁停在 +8.34° 再也过不去。挪到 +0.020 后手部半径 0.023，落在轮毂正
上方，手柄圆与指尖的水平净空从 26 mm 增到 43 mm。

不改共用 home（RoboMME 锚点）。若将来仍需让开，按 `stacked_plate` 的先例配任务专属的
抬高 home。

---

## 4. 判定

模块：`topogym/verification/linkbar_merge_components_verifier.py`

### 4.1 约束图层

节点是三段刚体，边是把它们连在一起的东西：

```text
component_a ──[铰链]── linkbar      恒有
linkbar ──[闩]── component_b        合并边：component_count 2 → 1
linkbar ──[闩]── component_a        环边：  component_count 2 → 2
```

闩边从求解器读回（`get_weld_constraints`），再用并查集数分量。**判据不看插口的名字**：
扣错失败是因为那条边在图上确实没合并任何东西。

**导轨不是图上的边。** 它把小车连到桌面，而桌面不是这三段刚体之一——与 A 自己的螺栓同
一性质。图数的是**组件之间**的约束，行程测试量的是**B 相对 A 还有没有自由度**，两者从
两端回答同一个问题，所以分开记录。

`to_info()` 带 C4 契约要求的字段：`invariant=component_count`、`invariant_signed=False`、
`space=constraint_graph`、`subject=linkbar`、`gateway=socket_latch`。

### 4.2 物理层：行程测试

沿导轨方向推小车（力 = `force_scale × 车质量 × g`，逐步重复施加），读移动关节的位置。

契约（`task_taxonomy_zh.md` §4.4）给 4.4 规定的是**提起测试**。改为行程测试有两条理由：
封闭导轨会让提起测试失去判别力（没合并时小车也被导轨压着抬不起来）；而小车只有一个自由
度，读数直接就是那个关节的位置，有界且无需标定。**这一处偏离需要在 `task_taxonomy_zh.md`
§4.4 与 `rigid_first_track_zh.md` §5.1 各补一行。**

### 4.3 两道自检

| 字段 | 含义 |
|---|---|
| `judge_disagrees` | 图说合并了但小车照样跑掉 → **判据错了，不是这次运行错了**，查焊接集与 link 映射，不要动场景 |
| `probe_uninformative` | 没合并、小车也没跑 → 推力太小，探针没有判别力，加大力而不是下结论 |

### 4.4 失败标签

| 标签 | 触发 |
|---|---|
| `rotate_check_failed` | 原语自身的判据不过（到位角、跟随误差、`max_lag`、释放漂移、指位） |
| `no_latch` | 销没进任何插口 |
| `latched_wrong_socket` | 扣进 A2，图上是环边 |
| `travel_test_failed` | 图说合并了但小车走了 |

**成功 = 三层都过**：约束图为 1、小车被拉住、原语判据通过。

---

## 5. 防捷径与随机化

逐 episode 随机化两个插口的角位置，使「哪个更近」与「哪个属于 B」相互独立：

| 插口角 | oracle | `nearest_socket`（捷径） |
|---|---|---|
| b1=+55, a2=−45 | 合并 | 扣 A2，失败 |
| b1=+35, a2=−60 | 合并 | 恰好扣对 |
| b1=−55, a2=+45 | 合并 | 扣 A2，失败 |
| b1=−35, a2=+60 | 合并 | 恰好扣对 |

离线（`tests/check_linkbar_planner.py`）与在真实物理上各验一次，都是 oracle 4/4、捷径 2/4。
「总是转同一个方向」同理，因为 B1 出现在初始角两侧的概率各半。

`LinkbarMergeLayout.validate` 拒绝不合法的角位置组合（两插口必须分居初始角两侧，各自的
扫掠幅度落在 `[min_sweep_deg, max_sweep_deg]`），不合法时报错而不是静默生成不可解实例。

**随机化尚未在 `generation/layout_randomization.py` 正式注册**，目前以配置项提供
（`task.sockets.*_angle_deg`）。C4 任务未注册者不得进入 benchmark 产物。

---

## 6. 文件集与登记点

```text
新增
  topogym/tasks/connectivity/linkbar_merge_components.py     Layout / Scene / SceneBuilder
  topogym/tasks/connectivity/_travel_probe.py                行程探针
  topogym/verification/linkbar_merge_components_verifier.py  State + Evaluator（union-find）
  topogym/planning/linkbar_merge_components_planner.py       oracle + nearest_socket
  topogym/primitives/socket_weld.py                          捕获窗 → add_weld_constraint
  tests/weld_constraint_spike.py                             weld 约束可用性 spike
  tests/check_linkbar_planner.py                             捷径基线的离线断言
  configs/task_configs/linkbar_merge_components_topogym_tabletop_v1.yaml
  configs/{,run_configs/}linkbar_merge_components{,_merge}.yaml
  demos/connectivity/linkbar_merge_components_{inspect,physical_merge}_demo.py

修改
  topogym/tasks/_fixtures.py   + sliding/joint_limit（移动关节）、yaw_deg、
                                 write_body_urdf / add_rigid_assembly、_link_xml 抽取

登记（已完成）
  topogym/core/taxonomy.py 的 CATEGORIES["connectivity"]
  topogym/{tasks,verification,planning,primitives}/__init__.py 的 re-export

登记（未完成）
  generation/layout_randomization.py、generation/<task>_generator.py
  四个 bash 注册表、cli_commands.txt 的一节
  task_taxonomy_zh.md §4.4 与 rigid_first_track_zh.md §5.1 的偏离记录
```

---

## 7. 步骤与验收状态

| 步骤 | 内容 | 状态 |
|---|---|---|
| 0 | weld 约束 spike | **过**（§8.1） |
| 1 | 素材、场景、inspect demo | **过**（§8.2–8.3） |
| 2 | 约束图判据 | **过**（§8.4） |
| 3 | planner + 原语接线 | planner 过；原语执行未过（§8.5） |
| 4 | 完整 episode | 任务逻辑四组合全对；`rotate_ok` 未过 |

---

## 8. 实测值

### 8.1 weld 约束（`tests/weld_constraint_spike.py`）

Genesis 1.2.1 的 `rigid_solver.add_weld_constraint` 仓库内首次使用，三项全过：读数可从
`get_weld_constraints` 读回；焊到固定 link 后 5.886 N 的拉力下位移 0.0001 m（删除约束后
同样的力抬起 0.3973 m）；两个可动体互焊后只拉其中一个，间距变化 0.47 mm。

判据用**间距**而不是高度差：力作用点偏离合体质心，自由飞行的合体会明显翻滚（120 mm 跨距
上高差 95 mm，即 53°），拿高度差当判据会把正常刚体运动判成 weld 失效。

### 8.2 三处几何错误与修法

| 现象 | 原因 | 修法 |
|---|---|---|
| 伺服扫掠最多欠转 22°，B 被推 9 mm | 转轴与固定立柱同轴、在立柱整个高度上互相穿透 | 转轴改为自立柱顶面上方 2 mm 起 |
| 四段扫掠三段 `touching=robot:20.32N`，停在 +8.34° | 停在 home 的夹爪横跨手柄圆 | 枢轴 x 由 −0.020 改到 +0.020（§3.3） |
| 销卡死在离 A2 座位 22.44° 处（13.45 N）；B 被推 14.5 mm | 直槽导不了弧上的销，偏差 12.9 mm 对 4 mm 间隙 | 先改弧形分段，后改浅口袋（§2.3） |

三项修完后：`worst_error_deg=0.00`、四段 `touching=none`、`b_drift_mm=0.00`、
`reached_both=True`。

### 8.3 行程测试的两档

| 相位 | travel | reached_stop | component_count |
|---|---|---|---|
| `none` | 0.1002 m | True | 2 |
| `a2` | 0.1002 m | True | 2 |
| `b1` | **0.0000 m** | False | **1** |

阈值 `max_travel=0.005`、`min_free_travel=0.080` 落在两档之间，任何位置都不改变结论。

### 8.4 三个相位的判据读数

`none` → `component_count=2, latch_edges=[], failure_label=no_latch`；
`a2` → `2, [['component_a','linkbar']], latched_wrong_socket`；
`b1` → `1, [['component_b','linkbar']], None, terminal=True`。
三档的 `judge_disagrees` 与 `probe_uninformative` 均为 False。

### 8.5 执行层：指腹打滑（待复核）

完整 episode 的读数：`target_error=5.05°`、`max_lag=5.03°`、`follow_error=0.0096`、
`release_drift=0.01°`、`finger_qpos=0.0107`。分相位日志：

```
after_grasp_settle  flap=+0.21deg      合爪后梁基本在起始角，不是抓取偏置
after_arc_settle    flap=+49.97deg     目标 55°，差 5.03°
after_arc_settle    hand=(+0.075,+0.082,...)
```

手到位了（命令点 (0.0774, 0.0819)，实测差 2.4 mm），而梁停在 49.97°——那个角度下手柄
应在 (0.0843, 0.0766)，**手与手柄相距 10.8 mm，接近一个手柄半径**。指腹从手柄上滑掉了。

量化：指位停在 0.0107、指令 0.006，过行程 4.7 mm × 指刚度 100 = 每指 0.47 N，折算到手柄
半径 0.100 上是 0.23 N·m；扫掠阻力矩（关节阻尼 0.05 × 峰值角速度 + 摩擦 0.03）约 0.11
N·m——**只有 2.1 倍余量**，销进口袋时再加一点接触就滑。

已落地的修改：`grasp_qpos` 0.006 → 0.001（过行程 10.0 mm，每指 1.00 N）、梁的关节阻尼
0.050 → 0.020、摩擦 0.030 → 0.015。余量由 2.1 倍变为 **17.4 倍**。**尚未在实跑中复核。**

### 8.6 小车的驻车阻力

移动关节摩擦原为 0.2 N。插口的颚板是径向的，法向正好是小车能走的方向，所以销滑进口袋时
蹭一下产生的就是纯径向力，0.2 N 拦不住，录像里可见整台车被推走。销上能传的力受夹爪力矩
上限约束约 1.4 N，摩擦提到 **4.0 N** 挡得住；行程测试推 13.24 N 减去 4.0 N 还剩 9.24 N，
自由小车仍然到底。

---

## 9. 未决事项

1. **§8.5 的复核**：`max_lag` 应降到 1° 以内、`target_error` 落入 4° 容差、`rotate_ok=True`。
   这是本轮唯一未过的判据。
2. **连杆在沉降阶段自行偏转**：曾观测到梁在机械臂回 home 期间离开初始角。已加
   `settle_check` 行（报角度与接触对象），读数未取。裙板删除后可能已消失。
3. 随机化在 `generation/layout_randomization.py` 的正式注册（C4 硬要求）。
4. 两处契约偏离的记录（§4.2）。
5. 20 种子上 oracle 与 `nearest_socket` 的成功率实测。
6. H5 录制、四个 bash 注册表、`cli_commands.txt` 一节。
7. `world_tabletop_v1` 的 `genesis.logging_level` 未被 demo 传给 `gs.init`，配置项写了没接线。

---

## 10. 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 提高夹持力后手柄被挤出或求解器不稳 | 扫掠失败 | `closed_qpos` 为 0.00，0.001 仍留有余量；复核时看 `finger_qpos` 是否仍停在 0.0107 |
| 降低梁的关节阻力后梁更易自行偏转 | 抓空 | 与未决事项 2 是同一件事，一起复核 |
| 抬高耦合后手柄进入停住指腹的高度带 | home 处干涉 | 水平净空 43 mm；若 `settle_check` 打出 `touching=robot` 即为此 |
| 捕获窗 15 mm 与原语容差 4° 接近 | 擦边扣上 | 容差比窗严一档是有意的，原语先失败；不得为让 run 变绿而放宽 |
