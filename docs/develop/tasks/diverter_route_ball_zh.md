# docx 4.3 旋转分流板改变小球出口 —— 工程计划

> 日期：2026-08-17，2026-08-18 更新（三项决策定案；步骤 1 代码落地，取值与派生几何改为实际值）
> 上游：`../TopoGym_tasks.docx` §4.3
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置与依赖）、
> `../framework/task_taxonomy_zh.md` §4.4（C4 判定契约）
>
> 目标模块：`topogym/tasks/connectivity/diverter_route_ball.py`

---

## 0. 结论摘要

- 场景形态取**桌面水平 Y 形分岔 + 竖直枢轴分流板**，小球沿 4.1 已验证的匀速驱动进入，
  与 docx 的竖直落料槽存在几何差异，理由与代价见 §2。
- 依赖的两项基建各自的状态：小球与驱动器**已跑通**（4.1）；单自由度铰链**需要从
  `stacked_plate.py` 的圆盘专用 URDF 写法泛化**——4.3 是第二个使用者，抽取时机由
  `rigid_first_track_zh.md` §7.6 原定的 4.4 提前到本任务。
- 新增一条仓库此前没有的能力：**逐 episode 变化的语言指令**。`task_goal` 目前在每个 demo 中
  硬编码，4.3 要求它随实例变化（走左／走右），这是防捷径成立的前提。
- 本轮交付边界为「oracle 全流程跑通」，实施分 **4 个步骤**（§8）。随机化注册、20 种子基线、
  录像与两项重构不在本轮。
- §10 的三项待决事项已于 2026-08-18 全部定案，取值见该节。

---

## 1. 任务定义与依赖现状

### 1.1 docx 原文要点

| 项 | 内容 |
|---|---|
| 场景 | 入口槽接入分岔结构，下方左右各一条出口通道，分岔口装一块绕枢轴旋转的分流板 |
| 动作 | 一次旋转分流板；随后小球落入，沿打开的支路自行滚出 |
| 状态变化 | 球的 `C_free` 上入口区与左／右出口区的 S–T 连通关系翻转（一路通、另一路断） |
| 判定 | 功能性判定：球实际从指令一侧的出口离开（docx 明确「S–T 弹珠测试本身就是任务」） |
| 防捷径 | 初始板向与目标指令逐 episode 随机组合；「看到板就转固定方向」期望成功率固定在一半。板旋转不到位（半开）时球卡在分岔口，构成可区分的中间失败态 |
| 约束 | 机器人全程不接触球 |

### 1.2 可直接复用的部分

| 来源 | 内容 | 状态 |
|---|---|---|
| `connectivity/gate_cage_ball.py` | 布局类的 task-frame 换算、`_box` 构件、配置组织方式 | 2026-08-17 全流程通过 |
| `connectivity/_ball_drive.py` | 匀速驱动 + 出轨后恒减速滑行，包装 `scene.step`。2026-08-18 由 `_ball_shuttle.py` 改名，因为它现在同时装 4.1 的换向驱动与 4.3 的恒速航向驱动 | 同上 |
| `verification/gate_cage_ball_verifier.py` | xy 栅格化 + 障碍按球半径膨胀 + flood-fill | 同上 |
| `tests/ball_roll_spike.py` | 球的滚动/回弹实测（零回弹、平地零滚阻），本任务沿用其结论与写法 | 已完成 |
| `primitives/rim_rotate.py` | 接触驱动 revolute 关节的相位结构与判据（跟随误差、释放漂移） | `stacked_plate` 在用 |
| `tasks/connectivity/stacked_plate.py` `_write_disk_urdf` | 程序化 URDF 铰链 | 需泛化，见 §7 |

### 1.3 需要新建的部分

| 项 | 原因 |
|---|---|
| 通用单自由度铰链发射器 | 现有模板硬绑圆柱碰撞体、Y 轴、continuous 关节、单个碰撞体；4.3 需要 Box 碰撞体、Z 轴、带限位的 revolute、同一转动连杆上挂多个碰撞体（板 + 拨杆 + 手柄） |
| 竖直轴拨杆原语 | `rim_rotate.py:23-34` 的 `rim_point_world` 假定圆盘面在 XZ 平面、法向沿 Y，且接近/退出逻辑按「越过圆盘顶」写死。竖直轴 + 顶抓手柄的接近与退出是另一套几何 |
| 恒速航向驱动 | 4.1 的驱动器只写 y 分量并在受阻时换向。分岔场景要求方向由碰撞决定、驱动器只维持速率，且受阻时停止而非换向 |
| S–T 判据 | 4.1 的 flood-fill 问「是否触达场地边界」，4.3 问「是否触达指定出口区」。同一套栅格，两种查询 |
| 指令轴 | `task_goal` 目前每个 demo 一个常量字符串，需按 episode 取值 |

---

## 2. 场景形态选型

两种形态都能实现同一个不变量与同一套防捷径，差别在物理风险、复用量与几何保真度。

| 项 | A：竖直板面（贴 docx） | B：桌面水平 Y 形分岔（推荐） |
|---|---|---|
| 球的动力 | 重力，沿竖直槽下落 | 匀速驱动，沿桌面滚动（4.1 方案） |
| 旋转轴 | 水平 X 轴 | 竖直 Z 轴 |
| 球在动作阶段的处置 | 需要在旋转完成前保持球不动，即运行期写位姿或额外机构 | 平面上球自然静止，驱动器在退刀后启动，无需任何保持 |
| 球的面外约束 | 需要前挡边，可能遮挡 front 相机 | 不需要 |
| 步进穿透风险 | 落差 0.15 m 时球速约 1.7 m/s，dt=0.01 下单步位移 17 mm，接触求解压入量大 | 球速 0.12 m/s，单步 1.2 mm |
| 判据复用 | flood-fill 需改到竖直平面，且重力下的可达性与几何连通性不等价（几何上向上可达，物理上不可达） | 4.1 的 xy flood-fill 直接适用 |
| 驱动器复用 | 不复用 | 复用同一模块，新增一种模式 |
| 拨杆抓取 | 手腕需 90° 偏摆，拨杆须穿到板后侧避让通道 | 顶抓竖直手柄，与仓库既有抓取一致 |
| 与 docx 的几何差异 | 无 | 竖直落料槽改为水平进料道；分岔、分流板、两个出口、S–T 判据均保留 |

**推荐 B**。理由：docx 4.3 的考察内容（球的 `C_free` 上 S–T 连通关系由板的相位门控、指令方向随机化、
半开为中间失败态）与重力无关，而 A 引入的三类风险（面外约束、步进穿透、动作阶段保持球不动）
都是纯实现开销。4.1 已就同一个取舍留下实测依据与书面理由（`gate_cage_ball_topogym_tabletop_v1.yaml`
头部注释），4.3 采用同一方案可保持类别内一致。

**代价**：`connectivity/` 将有第二处与 docx 原文的几何差异（第一处是 4.2，见
`rigid_first_track_zh.md` §5.1）。区别在于 4.2 的差异导致 `C_free` 状态变化未被判定，而 B 完整保留
`C_free` 判定。落地后需在 `rigid_first_track_zh.md` §5.1 的差异表中补一行。

以下各节按 B 展开。

---

## 3. 机构与几何

### 3.1 结构

```text
                                   ┌── 左支路 ──► 左出口 (-y)
  进料道 ──────► 分岔口 ────────────┤
   (+x)          分流板枢轴          └── 右支路 ──► 右出口 (+y)
```

- 进料道沿 +x（远离机械臂、朝向 front 相机），两条支路自分岔口按 ±30° 分开。
  front 相机位于 (0.42, 0, 1.30) 朝 -x 看，其画面右方向为 +y，因此 +y 支路在画面中即右出口。
- 分流板铰接于分流鼻的上游尖点，指向上游。摆到 -30° 时封住左支路口，摆到 +30° 时封住右支路口，
  0° 时两侧都不封（半开态）。关节限位设在 ±30°，越程由限位吸收。
- 分流板与拨杆在同一转动连杆上：拨杆自枢轴向下游伸出，末端手柄竖起，手柄底面高于侧壁顶面，
  夹爪顶抓手柄并沿水平圆弧摆动，分流板由关节随动。机械臂全程不进入通道内部。

### 3.2 取值（步骤 1 已落地）

单位米，task 坐标系（z=0 为桌面）。**配置里只给下面这几个自变量，其余全部派生**，
改宽度或改角度时整套几何自洽：

| 配置项 | 值 | 备注 |
|---|---|---|
| `channel.inner_width` | 0.090 | 落座后的通行宽度等于它（板与支路内边界共线，通道等宽） |
| `channel.wall_thickness` / `wall_height` | 0.012 / 0.045 | 壁高远高于球心（0.030） |
| `channel.floor_top_z` / `plate.thickness` | 0.004 / 0.004 | 整体一块薄底板，见 §3.3 |
| `channel.entry_start_x` / `fork_origin_x` | -0.200 / -0.020 | 后者定整套派生几何的原点 |
| `branch.angle_deg` / `exit_station` | 30 / 0.200 | |
| `ball.radius` / `speed` / `release_x` | 0.026 / 0.120 / -0.170 | 半径的上下界见下 |
| `diverter.flap.thickness` / `wall_gap` / `ground_clearance` | 0.012 / 0.004 / 0.001 | |
| `diverter.lever.radius` / `knob_size` / `knob_height` | 0.055 / 0.018 / 0.050 | 拨杆向下游伸出 |

派生结果（`tests` 之外由 `DiverterRouteBallLayout` 计算，已离线核对）：

| 量 | 公式 | 值 |
|---|---|---|
| 分流鼻（枢轴）`nose_x` | `fork_origin_x + hw/sin a` | +0.070 |
| 进料壁与支路外壁交接 `junction_x` | `fork_origin_x + hw(cos a −1)/sin a` | −0.032 |
| 板长 | `hw/(sin a·cos a) − wall_gap` | 0.0999 |
| 出口中心 | `fork_origin + exit_station·d` | (0.153, ±0.100) |
| 落座角 | `∓a`（封左为 +30°） | ±30° |
| 底板 | 由最外侧构件反推 | x ∈ [−0.232, 0.173]，y ±0.169 |
| 释放到出口 | `(nose_x − release_x + exit_station − hw·cot a)/v` | 3.02 s |

**球半径的上下界**（两条都由几何反推，改通道宽度或角度需重算）：

| 界 | 条件 | 数值 |
|---|---|---|
| 下界 | 半开时板尖两侧的旁通间隙必须小于球径，否则球溜过去，中间失败态不成立 | 间隙 46.2 mm |
| 上界 | 落座后的通行宽度须显著大于球径 | 通道 90 mm |

取 52 mm：下界余 5.7 mm，上界每侧余 19 mm。

抓手柄时指垫在 z=0.098、手部在 0.201，与 4.1 的取板高度（0.188）同量级；手柄中心距 Franka
底座 0.688 m（4.1 的取板点是 0.645 m）。

### 3.3 底板做成一整块的原因

支路的地板在分岔口必然互相重叠，两块同高的顶面会 z-fighting。改为整体一块底板后，
侧壁站在板上，没有重叠也没有共面。板取 4 mm 厚：球从出口滚出去时只下一个 4 mm 的台阶，
而深色板面与浅色球的对比让各相机都能跟踪到球（桌面本身是浅灰）。

---

## 4. 球的驱动

新增一个驱动类 `HeadingDrive`，与 4.1 的 `BallShuttle` 并列，放在
`tasks/connectivity/_ball_drive.py`（原 `_ball_shuttle.py`，因同时承载两种驱动而改名）：

```
v = 实测水平速度
若 |v| < v_min : 停止驱动（判定为受阻）
否则           : v *= speed / |v| ，写回，并按滚动匹配自旋
```

三条设计约束：

1. **驱动器不选择支路。** 只维持速率，方向完全由碰撞求解结果决定。分流板对球的导向因此是物理
   结果而非脚本结果。
2. **受阻即停止，不换向。** 4.1 需要换向以表现「被困住的球持续往复」；4.3 需要停止以表现
   「半开时球卡在分岔口」这一中间失败态。
3. **出网络后沿用 4.1 的恒减速滑行**（`offtrack_decel`），使离开出口的球滚一段后静止，
   终态在画面中可读。

已知风险：紧贴侧壁的擦碰之后重新归一化速率，可能把球再次推向该侧壁。步骤 1 观测，必要时改为
仅在方向落在通道角度范围内时归一化。

---

## 5. 判定

模块：`topogym/verification/diverter_route_ball_verifier.py`

| 层 | 内容 |
|---|---|
| 不变量 | `invariant = "st_reachable"`，`invariant_value = {"left": 0/1, "right": 0/1}`，`space = "c_free"`，`subject = "ball"`，`gateway = "diverter_flap"` |
| 几何层 | 复用 4.1 的栅格：障碍矩形按球半径膨胀，自入口区 flood-fill，分别查询是否触达左／右出口区。分流板从场景实测位姿取矩形，其余构件由布局给出 |
| 物理层（主判据） | S–T 弹珠测试：退刀后启动驱动，步进至球离开出口区或超时，记录离开侧 |
| 成功 | 离开侧 == 指令侧，且几何层读数与之一致，且球未受阻 |

失败标签（保持互相可分，用于对触发相位做误差分析）：

| 标签 | 触发条件 |
|---|---|
| `wrong_exit` | 球从非指令侧离开 |
| `ball_stuck_at_fork` | 驱动因受阻停止且球位于分岔口区域 |
| `ball_never_left` | 超时且球仍在通道内 |
| `flap_not_seated` | 关节角未到达限位容差内（旋转不到位） |
| `rotate_check_failed` | 原语自身的跟随误差／释放漂移判据不过 |

注：半开态的实际表现（卡住，或偏向一侧通过）在步骤 1 观测后确定归入哪个标签；两种表现都判失败。

---

## 6. 指令轴与随机化

### 6.1 指令

`task_goal` 按 episode 取值，两条字符串（走左／走右）。这是仓库第一个指令随实例变化的任务：
`data/episode_dataset_writer.py:77` 已经把 `task_goal` 作为每 episode 参数，
`scripts/export_h5_lerobot.py:24` 将其导出为 prompt，因此管线侧不需要改动，只需 demo 按实例传值。

### 6.2 随机化轴

`task_taxonomy_zh.md` §4.4：C4 任务未在 `generation/layout_randomization.py` 注册随机化条目者
不得进入 benchmark 产物。本任务需要注册两个**离散**轴：分流板初始相位、指令方向。

现有 `layout_randomization.py` 的四种 directive 全部是连续扰动，且模块文档写明
「never change topology / the success criterion unchanged」，与离散指令轴冲突。解法：

- 新增 `_ChoiceJitter(path, choices)` directive；
- 指令侧写入 `cfg.task.command.side`（属于实例定义，而非运行模式）；
- 在模块文档中补一段说明：C4 类额外随机化离散实例轴，oracle 读回该轴后仍然可解，
  因此不违反「oracle 保持可解」这一原则。

该 directive 落地后同时解开 4.1 阶段 2 的随机化（`ball.release_y`，见
`configs/run_configs/gate_cage_ball_gate.yaml` 尾部说明）。

### 6.3 初始相位与指令的组合

三种取法，影响 IL 数据与评测两侧：

| 取法 | 每个实例是否需要旋转 | 是否强制读指令 | 备注 |
|---|---|---|---|
| 2×2 独立随机（docx 原文） | 一半需要 | 是 | 另一半的正确动作为不旋转，直接放球 |
| 指令恒取当前封闭侧 | 全部需要 | 否（看板即可推出答案） | 指令冗余，语言轴失效 |
| 初始恒为半开 | 全部需要 | 是 | 板的初始相位不携带答案信息，但失去 docx 描述的「一路通、另一路同时断」 |

**推荐 2×2 独立随机**（docx 原文）：不旋转的实例是合法评测实例，它把「总是旋转」这一策略钉在
一半；录制 IL 数据时通过配置项只取需要旋转的两种组合。

### 6.4 对照基线

与 4.1 的 `oracle` / `greedy` 同构，两条基线共用一个接口：

| 基线 | 行为 | 预期 |
|---|---|---|
| `oracle` | 读指令与当前板相位，转到对应限位 | 成功 |
| `fixed_direction` | 忽略指令，总是转向同一侧 | 期望成功率约一半 |

---

## 7. 文件集与登记点

依据 `../framework/module_boundaries_zh.md` §6 与 `rigid_first_track_zh.md` §6.1。

```text
新增（✅ = 步骤 1 已落地）
✅ topogym/tasks/connectivity/diverter_route_ball.py          Layout / Scene / SceneBuilder
   topogym/verification/diverter_route_ball_verifier.py       State + Evaluator
   topogym/planning/diverter_route_ball_planner.py            指令 -> 目标角与旋转方向；含 fixed_direction 基线
   topogym/primitives/pivot_lever.py                          竖直轴拨杆的接触驱动旋转
✅ configs/task_configs/diverter_route_ball_topogym_tabletop_v1.yaml
✅ configs/run_configs/diverter_route_ball.yaml               inspect 运行组
   configs/run_configs/diverter_route_ball_route.yaml         route 运行组（command / oracle_mode）
✅ configs/diverter_route_ball.yaml                           inspect 主配置
   configs/diverter_route_ball_route.yaml                     route 主配置
✅ demos/connectivity/diverter_route_ball_inspect_demo.py
   demos/connectivity/diverter_route_ball_physical_route_demo.py

修改
✅ topogym/tasks/_fixtures.py                                 + HingeShape / write_hinge_urdf /
                                                               add_hinge_mechanism / hinge_joint_dof
✅ topogym/tasks/connectivity/_ball_shuttle.py -> _ball_drive.py  + HeadingDrive
   topogym/generation/layout_randomization.py                 + _ChoiceJitter + 本任务条目（本轮之外）
   cli_commands.txt                                           + 一节命令

登记
✅ topogym/core/taxonomy.py  CATEGORIES["connectivity"]
✅ topogym/tasks/__init__.py 的 re-export
   topogym/verification/__init__.py、topogym/planning/__init__.py、
   topogym/primitives/__init__.py 的 re-export
```

不做独立的 `tests/diverter_ball_spike.py`：4.1 的 `gate_cage_ball_inspect_demo.py` 已经是
「建真场景 + 放球滚一遍 + 不含机械臂」的形态，独立 spike 会把通道几何复制一份且用完即弃。
`tests/ball_roll_spike.py` 那种独立 spike 测的是与几何无关的材料属性（回弹、滚阻），
那些值 4.1 已测过、直接沿用。

四个 bash 注册表（`record_all_tasks.sh` / `collect_and_view.sh` / `stability_sweep.sh` /
`verify_dataset_recording.sh`）在开始录数据时再登记。4.1 同样尚未登记，两者一并处理。

行数估算（按仓库既有任务区间）：task 模块 350–500、verifier 200–280、原语 150–220、
planner 80–120、配置 150–200、demo 300–380。

---

## 8. 实施步骤

本轮交付边界为「oracle 全流程跑通」，共 4 步。每步列出产出、验收判据与运行命令；
命令一律 `| tee runs/*.log`，实测值从日志取，逐步验收后再进下一步。

### 步骤 1：铰链发射器 + 场景 + inspect demo ✅ 代码已落地，待实机验收

产出见 §7 打勾项。要点：

- `_fixtures.py` 的 `write_hinge_urdf` / `add_hinge_mechanism`：转轴方向、关节类型
  （continuous 或带限位 revolute）、阻尼与摩擦、转动连杆上的**多个**碰撞体。
  模板取自 `stacked_plate.py` 的 `_write_disk_urdf`（硬绑圆柱碰撞体、Y 轴、continuous、
  单碰撞体，三项都不适用于分流板）。本步骤不迁移 `stacked_plate`。
- 分流板、连接柱、拨杆臂、手柄是同一个转动连杆上的四个碰撞体。
- inspect demo 三种模式：`static_only`（只建场景）、`sweep_joint`（写关节扫全程，
  运动学检查，不属于 episode）、球 rollout（`flap_phase=seal_left|seal_right|half|config`）。

**验收**

- `static_only` 下构建无互相穿透；
- 关节扫描：命令值故意越过限位 10°，两端 `reached` 都停在 ±30°（`worst_limit_error` < 1°），
  拨杆与侧壁无干涉；
- 封左 → 球从右出口离开；封右 → 球从左出口离开；三个球速取值下均成立
  （打印行的 `routed_correctly=True`）；
- 半开 → `jammed=True`，且 `jam_xy` 落在分岔口附近。几何上旁通间隙 46.2 mm 小于球径 52 mm，
  预期确定卡住；若实测出现「偏向一侧通过」，记录下来并据此定步骤 4 的失败标签；
- 记录 `exit_time`（预测 3.02 s），作为步骤 4 物理层复核的超时预算；
- `lane_max_abs_y` 应远小于 (90−52)/2 = 19 mm，否则球在进料道里跑偏；
- 已知风险：擦碰后速率归一化可能把球再次推向侧壁。此处观测，必要时改为仅在方向落在
  通道角度范围内时归一化。

```bash
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.static_only=true run.viewer=true run.keep_open=true 2>&1 | tee runs/div_static.log
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.sweep_joint=true run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_sweep.log
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.flap_phase=seal_left run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_roll_left.log
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.flap_phase=seal_right run.verbose=true 2>&1 | tee runs/div_roll_right.log
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.flap_phase=half run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_roll_half.log
python -B -m demos.connectivity.diverter_route_ball_inspect_demo -m run.flap_phase=seal_left task.ball.speed=0.08,0.12,0.18 2>&1 | tee runs/div_roll_speed.log
```

### 步骤 2：判据（几何层）

产出：`verification/diverter_route_ball_verifier.py`（State + Evaluator）、
`verification/__init__.py` re-export、inspect demo 的 `run.classify=true` 分支。

栅格化 + 障碍按球半径膨胀 + flood-fill **复制**自 `gate_cage_ball_verifier.py`
（4.1 问「是否触达场地边界」，4.3 问「是否触达指定出口区」，同一套栅格两种查询）。
本轮复制而不抽取共用助手，4.1 的已通过状态不受影响；抽取列入本轮之外。

**验收**

- 三个相位下几何读数与实际相位一致（封左 → `{"left":0,"right":1}`）；
- 几何读数与步骤 1 观测到的球实际去向一致——这一条是本步骤的意义所在：几何判据与物理结果对表；
- `python topogym/core/taxonomy.py` 通过。

```bash
python -B -m demos.connectivity.diverter_route_ball_inspect_demo -m run.classify=true run.flap_phase=seal_left,seal_right,half 2>&1 | tee runs/div_classify.log
python topogym/core/taxonomy.py
```

### 步骤 3：拨杆原语与 planner（不放球）

产出：`primitives/pivot_lever.py`、`planning/diverter_route_ball_planner.py`、
route demo 的 `run.stage=rotate_only` 路径与两个配置文件、两处 re-export。

原语的相位结构与三项判据（到位角误差、跟随误差、释放漂移）沿用 `rim_rotate.py`；
接近与退出几何按「顶抓竖直手柄 + 水平圆弧」重写——`rim_rotate.py` 的 `rim_point_world`
假定圆盘面在 XZ 平面、法向沿 Y，且接近逻辑按「越过圆盘顶」写死，不可直接复用。
关节限位吸收越程，因此沿圆弧多扫 5°。

**验收**：关节从任一端转到另一端，两个方向各一次；三项判据在阈值内；手柄未脱手；
退刀后机械臂不遮挡通道；planner 在四种「初始相位 × 指令」组合上给出预期决策（离线断言）。

**回退方案**：若顶抓在摆动中脱手，改为闭爪推动手柄（不抓取）。

```bash
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.stage=rotate_only run.command=left run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_rotate_left.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.stage=rotate_only run.command=right run.verbose=true 2>&1 | tee runs/div_rotate_right.log
```

### 步骤 4：完整 episode（oracle 跑通）

产出：route demo 完整流程（旋转或按指令跳过 → 退刀 → 启动驱动 → S–T 弹珠测试 → 判定）、
verifier 的物理层与失败标签、按实例取值的 `task_goal`。episode 结构照
`gate_cage_ball_physical_gate_demo.py`。

「不需要旋转」的实例作为一等路径处理：oracle 读出指令侧已连通即跳过旋转、直接放球；
该 episode 不含操作动作，`print_collision_il_contract` 的输出需如实反映。

本步骤收尾：订正 `rigid_first_track_zh.md` 的进度表与 §5.1 差异表（补 4.3 一行）；
本文件补实测值；`cli_commands.txt` 加一节。

**验收：四种组合的预期结局**（`fixed_direction` 定义为总是转到「封右」端）

| 初始封闭侧 | 指令 | oracle 动作 | oracle | fixed_direction 动作 | fixed |
|---|---|---|---|---|---|
| 左 | 右 | 不旋转 | 成功 | 旋转→封右 | 失败（`wrong_exit`）|
| 左 | 左 | 旋转→封右 | 成功 | 旋转→封右 | 成功 |
| 右 | 左 | 不旋转 | 成功 | 已在封右，不动 | 成功 |
| 右 | 右 | 旋转→封左 | 成功 | 已在封右，不动 | 失败（`wrong_exit`）|

oracle 四种组合全部成功；`fixed_direction` 恰好 2/4 失败且标签为 `wrong_exit`——这正是 docx
「期望成功率被钉在一半」的机制，在固定实例上逐项复核。任何一行与预期不符都先查因，不调几何
去凑结果：把几何调到某条基线必失败，等于把基线分数写进场景定义
（`gate_cage_ball_gate.yaml` 尾部已就同一问题留下说明）。

```bash
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo task.diverter.init_sealed_side=left run.command=right run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_o_lr.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo task.diverter.init_sealed_side=left  run.command=left  run.verbose=true 2>&1 | tee runs/div_o_ll.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo task.diverter.init_sealed_side=right run.command=left  run.verbose=true 2>&1 | tee runs/div_o_rl.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo task.diverter.init_sealed_side=right run.command=right run.verbose=true 2>&1 | tee runs/div_o_rr.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo -m run.oracle_mode=fixed_direction task.diverter.init_sealed_side=left,right run.command=left,right 2>&1 | tee runs/div_fixed_all.log
```

### 本轮之外

| 项 | 内容 |
|---|---|
| 随机化注册 | `layout_randomization.py` 新增 `_ChoiceJitter`，注册初始相位与指令两个离散轴（§6.2 的契约冲突与解法）。该 directive 同时解开 4.1 阶段 2 的 `ball.release_y` 随机化 |
| 基线实测 | 20 个种子上 oracle 与 `fixed_direction` 的成功率 |
| 录像 | 成功／失败两段 hq 录像 |
| 重构 | flood-fill 栅格助手抽取（需重跑 4.1 的 oracle/greedy）；`stacked_plate` 迁移到通用铰链发射器（需重跑其 rotate demo，且要给发射器补一个 mesh 视觉分支）——满足 `rigid_first_track_zh.md` §7.6 |
| bash 注册表 | 四个注册表在开始录数据集时登记；4.1 同样未登记，届时一并处理 |

---

## 9. 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 擦碰后速率归一化把球推向侧壁 | 球贴壁减速或停住 | 步骤 1 观测（看 `lane_max_abs_y`）；改为仅在方向落在通道角度范围内时归一化 |
| 半开态表现不稳定（有时卡住、有时通过） | 中间失败态不可复现 | 几何上旁通间隙 46.2 mm 小于球径 52 mm，预期确定卡住；若实测仍有通过，加大球径或缩短板长 |
| 分流板封位存在缝隙，球挤过 | 判据与物理不一致 | 板尖距外壁 3.5 mm，远小于球径；步骤 1 用最高球速验证 |
| 接触驱动的关节角不到限位 | 分流板半开 | 关节限位吸收越程，原语沿圆弧多扫 5°；关节摩擦按步骤 3 实测取值 |
| 手柄在摆动中脱手 | 旋转失败 | 沿用 `rim_rotate` 的跟随误差判据；必要时改为闭爪推动手柄（不抓取） |

---

## 10. 已定事项（2026-08-18）

| 项 | 结论 | 影响 |
|---|---|---|
| 场景形态 | §2 的 B 方案：桌面水平 Y 形分岔 | 步骤 1 按此落地；需在 `rigid_first_track_zh.md` §5.1 差异表补一行 |
| 初始相位与指令的组合 | docx 原文的 2×2 独立随机（§6.3） | 四种组合中两种的正确动作是不旋转，步骤 4 按一等路径处理；录 IL 数据时用配置项只取需要旋转的两种 |
| 交付边界 | 到 oracle 全流程跑通（步骤 1–4） | 随机化注册、20 种子基线、录像与两项重构列入「本轮之外」 |

仍未定、留到实测后决定的两项：

1. **抓取方式**（步骤 3）：顶抓手柄摆动，或闭爪推动手柄。按顶抓展开，推动作为回退方案。
2. **半开态的失败标签**（步骤 1 实测后）：`ball_stuck_at_fork` 与 `wrong_exit` 两者之一，
   取决于球是卡住还是偏向一侧通过。几何预测是卡住。
