# docx 4.3 旋转分流板改变小球出口 —— 工程计划

> 日期：2026-08-17
> 上游：`../TopoGym_tasks.docx` §4.3
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置与依赖）、
> `../framework/task_taxonomy_zh.md` §4.4（C4 判定契约）
>
> 目标模块：`topogym/tasks/connectivity/diverter_route_ball.py`

---

## 0. 结论摘要

- 场景形态推荐**桌面水平 Y 形分岔 + 竖直枢轴分流板**，小球沿 4.1 已验证的匀速驱动进入，
  与 docx 的竖直落料槽存在几何差异，理由与代价见 §2。
- 依赖的两项基建各自的状态：小球与驱动器**已跑通**（4.1）；单自由度铰链**需要从
  `stacked_plate.py` 的圆盘专用 URDF 写法泛化**——4.3 是第二个使用者，抽取时机由
  `rigid_first_track_zh.md` §7.6 原定的 4.4 提前到本任务。
- 新增一条仓库此前没有的能力：**逐 episode 变化的语言指令**。`task_goal` 目前在每个 demo 中
  硬编码，4.3 要求它随实例变化（走左／走右），这是防捷径成立的前提。
- 实施分 7 个阶段，阶段 0 为不含机械臂的物理 spike，阶段 6 为可跳过的重构。
- 三项待决事项见 §10，其中前两项影响阶段 1 之前的取值。

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
| `connectivity/_ball_shuttle.py` | 匀速驱动 + 出轨后恒减速滑行，包装 `scene.step` | 同上 |
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

### 3.2 第一版取值

单位米，task 坐标系（z=0 为桌面）。阶段 0 之后定稿。

| 项 | 值 | 备注 |
|---|---|---|
| `channel.inner_width` | 0.070 | 球径 50 mm，两侧各 10 mm |
| `channel.wall_thickness` / `wall_height` | 0.012 / 0.045 | 壁高高于球心（0.034） |
| `channel.floor_top_z` / `floor_thickness` | 0.009 / 0.009 | 与 4.1 同 |
| `entry.start_x` → `fork.apex_x` | -0.130 → 0.060 | 进料段长 0.190，用时 1.58 s |
| `branch.angle_deg` / `branch.length` | 30 / 0.170 | 出口中心 (0.207, ±0.085) |
| `ball.radius` / `speed` / `release_x` | 0.025 / 0.120 / -0.110 | 速度沿用 4.1 实测可用值 |
| `flap.length` / `thickness` / `height` | 0.085 / 0.010 / 0.045 | 长度须使封位时自由边与支路外壁重叠 ≥ 5 mm |
| `flap.limit_deg` | ±30 | revolute 限位 |
| `lever.radius` / 手柄尺寸 / 手柄顶 z | 0.055 / 0.016×0.016×0.030 / 0.105 | 手柄底面 0.075，高于壁顶 0.054 |

判定条件：全程 x 跨度 0.34、y 跨度 0.22，位于桌面与 Franka 工作区内；抓手柄时手部 z 约 0.193，
与 4.1 的取板高度（0.188）同量级。

---

## 4. 球的驱动

新增一种驱动模式，与 4.1 的换向驱动并列，放在 `tasks/connectivity/_ball_shuttle.py`：

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

已知风险：紧贴侧壁的擦碰之后重新归一化速率，可能把球再次推向该侧壁。阶段 0 观测，必要时改为
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

注：半开态的实际表现（卡住，或偏向一侧通过）在阶段 0 观测后确定归入哪个标签；两种表现都判失败。

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
新增
  topogym/tasks/connectivity/diverter_route_ball.py          Layout / Scene / SceneBuilder
  topogym/verification/diverter_route_ball_verifier.py       State + Evaluator
  topogym/planning/diverter_route_ball_planner.py            指令 -> 目标角与旋转方向；含 fixed_direction 基线
  topogym/primitives/pivot_lever.py                          竖直轴拨杆的接触驱动旋转
  configs/task_configs/diverter_route_ball_topogym_tabletop_v1.yaml
  configs/run_configs/diverter_route_ball.yaml               inspect 运行组
  configs/run_configs/diverter_route_ball_route.yaml         route 运行组（command / oracle_mode）
  configs/diverter_route_ball.yaml、configs/diverter_route_ball_route.yaml   两个 hydra 主配置
  demos/connectivity/diverter_route_ball_inspect_demo.py
  demos/connectivity/diverter_route_ball_physical_route_demo.py
  tests/diverter_ball_spike.py（+ 对应两个配置）

修改
  topogym/tasks/_fixtures.py                                 + 通用单自由度铰链发射器
  topogym/tasks/connectivity/_ball_shuttle.py                + 恒速航向驱动
  topogym/generation/layout_randomization.py                 + _ChoiceJitter + 本任务条目
  cli_commands.txt                                           + 一节命令

登记
  topogym/core/taxonomy.py  CATEGORIES["connectivity"]
  topogym/tasks/__init__.py、topogym/verification/__init__.py、
  topogym/planning/__init__.py、topogym/primitives/__init__.py 的 re-export
```

四个 bash 注册表（`record_all_tasks.sh` / `collect_and_view.sh` / `stability_sweep.sh` /
`verify_dataset_recording.sh`）在开始录数据时再登记。4.1 同样尚未登记，两者一并处理。

行数估算（按仓库既有任务区间）：task 模块 350–500、verifier 200–280、原语 150–220、
planner 80–120、配置 150–200、demo 300–380。

---

## 8. 分阶段实施

每阶段列出产出、验收判据与运行命令。命令一律 `| tee runs/*.log`，便于事后取实测值。

### 阶段 0：物理 spike（不含机械臂）

产出：`tests/diverter_ball_spike.py`。通道 + 分流板（`fixed=True`，按配置摆到三个相位之一）+
恒速航向驱动的球，无机械臂、无关节。

验收：

- 板封左时球从右出口离开、封右时从左出口离开，各 5 个速度取值全部成立；
- 半开相位下的表现稳定可复现（卡住或偏向一侧通过，二者之一），据此确定失败标签；
- 记录球自释放到离开出口的用时，作为物理层复核的超时预算；
- 无穿透、无沿壁弹跳。

```bash
python -B -m tests.diverter_ball_spike run.phase=seal_left run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_spike_left.log
python -B -m tests.diverter_ball_spike run.phase=seal_right run.verbose=true 2>&1 | tee runs/div_spike_right.log
python -B -m tests.diverter_ball_spike run.phase=half run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_spike_half.log
python -B -m tests.diverter_ball_spike -m task.ball.speed=0.08,0.12,0.18 2>&1 | tee runs/div_spike_speed.log
```

### 阶段 1：铰链发射器与场景

产出：`_fixtures.py` 的通用铰链发射器、`diverter_route_ball.py`、任务配置、inspect demo。

铰链发射器的参数面（由本任务的需求确定，不做超出需求的泛化）：转轴方向、关节类型
（continuous / 带限位 revolute）、阻尼与摩擦、转动连杆上的**多个**碰撞体（各自形状、尺寸、
局部位姿）、可选的视觉网格。

验收：

- `run.static_only=true` 下构建无互相穿透；
- inspect demo 用 `set_dofs_position` 扫过关节全程（此处为运动学检查，不属于 episode），
  两端到位、限位生效、拨杆与侧壁无干涉；
- 判据的几何层读数与板相位一致（封左 → `{"left":0,"right":1}`）。

```bash
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.static_only=true run.viewer=true run.keep_open=true 2>&1 | tee runs/div_static.log
python -B -m demos.connectivity.diverter_route_ball_inspect_demo run.sweep_joint=true run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_sweep.log
```

### 阶段 2：拨杆原语（不放球）

产出：`primitives/pivot_lever.py`。相位结构、跟随误差／释放漂移判据沿用 `rim_rotate.py`，
接近与退出几何按顶抓竖直手柄重写。

验收：关节从任一端转到另一端；到位角误差、跟随误差、释放漂移三项在阈值内；手柄未脱手；
退刀后机械臂不遮挡通道。

```bash
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.stage=rotate_only run.command=left run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_rotate_left.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.stage=rotate_only run.command=right run.verbose=true 2>&1 | tee runs/div_rotate_right.log
```

### 阶段 3：完整 episode

产出：完整 route demo（旋转 → 退刀 → 启动驱动 → S–T 弹珠测试 → 判定）、planner、verifier 接线。

验收：四种「初始相位 × 指令」组合全部得到预期结局；`fixed_direction` 基线在其中一半失败且
失败标签为 `wrong_exit`；打印行包含不变量读数、离开侧、用时、关节角误差。

```bash
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.command=left run.viewer=true run.keep_open=true run.verbose=true 2>&1 | tee runs/div_oracle_left.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.command=right run.verbose=true 2>&1 | tee runs/div_oracle_right.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.oracle_mode=fixed_direction run.command=left run.verbose=true 2>&1 | tee runs/div_fixed_left.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.oracle_mode=fixed_direction run.command=right run.verbose=true 2>&1 | tee runs/div_fixed_right.log
```

### 阶段 4：随机化与对照对

产出：`_ChoiceJitter`、随机化条目、planner 的单元测试（指令 → 目标角与旋转方向，纯算术，
不依赖 Genesis）、20 个种子的两条基线实测。

验收：20 个种子上 oracle 成功率与 `fixed_direction` 成功率分别落在预期区间并如实记录；
`python topogym/core/taxonomy.py` 通过。

```bash
python -B -m pytest tests/test_diverter_route_ball_planner.py -q 2>&1 | tee runs/div_unit.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo -m run.seed=0,1,2,3,4,5,6,7,8,9 run.randomize=true 2>&1 | tee runs/div_sweep_oracle.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo -m run.seed=0,1,2,3,4,5,6,7,8,9 run.randomize=true run.oracle_mode=fixed_direction 2>&1 | tee runs/div_sweep_fixed.log
python topogym/core/taxonomy.py
```

### 阶段 5：录像与文档

产出：成功／失败两段录像；`cli_commands.txt` 新增一节；
`rigid_first_track_zh.md` 的进度表、§5.1 差异表、§7 待决事项同步更新；本文件补实测值。

```bash
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo recording=hq recording.path=runs/videos/diverter_route_ball/success.mp4 recording.camera=[oblique,front,wrist] recording.res=[960,960] recording.every_n_steps=3 run.verbose=true 2>&1 | tee runs/div_success.log
python -B -m demos.connectivity.diverter_route_ball_physical_route_demo run.oracle_mode=fixed_direction recording=hq recording.path=runs/videos/diverter_route_ball/fail.mp4 recording.camera=[oblique,front,wrist] recording.res=[960,960] recording.every_n_steps=3 run.verbose=true 2>&1 | tee runs/div_fail.log
```

### 阶段 6：重构（可跳过）

两项抽取，各自带一次回归运行成本，因此排在功能完成之后：

| 抽取项 | 涉及 | 回归 |
|---|---|---|
| flood-fill 栅格助手 | 4.1 与 4.3 两个 verifier 共用 | 重跑 4.1 的 oracle / greedy 各一次 |
| `stacked_plate` 迁移到通用铰链发射器 | 满足 `rigid_first_track_zh.md` §7.6 | 重跑 `stacked_plate_physical_rotate_demo` 一次 |

阶段 1–5 期间两处保持复制，4.1 与 4.2 的已通过状态不受影响。

---

## 9. 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 擦碰后速率归一化把球推向侧壁 | 球贴壁减速或停住 | 阶段 0 观测；改为仅在方向落在通道角度范围内时归一化 |
| 半开态表现不稳定（有时卡住、有时通过） | 中间失败态不可复现 | 两种表现都判失败，标签按阶段 0 实测确定；必要时加宽分流鼻 |
| 分流板封位存在缝隙，球挤过 | 判据与物理不一致 | 板长按「与外壁重叠 ≥ 5 mm」取；阶段 0 用最高球速验证 |
| 接触驱动的关节角不到限位 | 分流板半开 | 关节限位吸收越程，原语沿圆弧多扫 5°；关节摩擦按阶段 2 实测取值 |
| 手柄在摆动中脱手 | 旋转失败 | 沿用 `rim_rotate` 的跟随误差判据；必要时改为闭爪推动手柄（不抓取） |

---

## 10. 待决事项

1. **场景形态**（阶段 0 之前）：采用 §2 的 B 方案（桌面水平分岔），还是按 docx 原文做竖直板面。
   本文按 B 展开。
2. **初始相位与指令的组合**（阶段 0 之前）：§6.3 三种取法，本文推荐 docx 原文的 2×2 独立随机。
3. **抓取方式**（阶段 2）：顶抓手柄摆动，或闭爪推动手柄。本文按顶抓展开，推动作为回退方案。
