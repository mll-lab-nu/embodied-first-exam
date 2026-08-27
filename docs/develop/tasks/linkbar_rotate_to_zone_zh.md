# docx 4.4 旋转连接杆转到同色区域 —— 工程记录

> 日期：2026-08-20 开工（首版：插口 + 小车），2026-08-27 改造（现版：颜色区域）
> 上游：`../TopoGym_tasks.docx` §4.4；2026-08-27 review 意见
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置）、
> `../framework/task_taxonomy_zh.md` §4.4（C4 判定契约）、
> [`variation_and_difficulty_plan_zh.md`](variation_and_difficulty_plan_zh.md) §3.8 / §6.8（随机化）
>
> 目标模块：`topogym/tasks/connectivity/linkbar_rotate_to_zone.py`

---

## 0. 结论摘要

- 场景：固定立柱上铰接一条连接梁，梁绕竖直轴转，梁端的销在水平圆上走。圆上分居初始角
  两侧各一块颜色区域（橙／蓝），销、销套环、手柄盖三处取其中一块的颜色。
- 判据：松手沉降后，销的关节角落在同色区域的角窗口内，且关节角速度低于阈值。单帧画面
  可辨：销在同色区里，或在异色区／区外。
- 2026-08-27 改造：删除小车、导轨、两个插口、weld 闩、行程测试、约束图 union-find。
  保留立柱、连接梁、`PivotLeverPrimitive` 及全部实测过的高度与夹持参数。
- 离线门已过：`tests/check_linkbar_planner.py`（oracle 4/4，`nearest_zone` 2/4）、
  `tests/check_linkbar_zone_geometry.py`（边界翻转、无重叠、六种非法布局被拒）、
  两个 demo 的 hydra 组合。GPU 门待跑（§7）。
- 时长：去掉行程测试（180 步）与部分停顿后，估计每 episode ≈ 560 步（原 ≈ 860）。

---

## 1. 任务定义

### 1.1 现行定义

| 项 | 内容 |
|---|---|
| 场景 | 桌面上一根固定立柱；连接梁铰接于立柱顶，绕 +z 转，无限位；梁端销半径 0.170 处；梁上手柄半径 0.100 处 |
| 目标 | 销停在与销同色的区域内 |
| 区域 | 两块，中心角分居初始角两侧（默认 +55° / −45°），角半宽 8°，径向宽 40 mm，纯视觉 |
| 动作 | 夹爪夹手柄转梁一次，松手，退刀 |
| 不变量 | `pin_zone ∈ {left, right, None}`，定义在梁的关节角上（`"space": "joint_angle"`） |
| 物理层 | `at_rest`：沉降 30 步后关节角速度 ≤ 0.05 rad/s |
| 指令 | 常量 `"Turn the bar so its pin rests on the zone that matches its colour."`；要读的信息（销的颜色）在场景里 |

### 1.2 与首版的差异及理由

首版（2026-08-20 ~ 08-22）：两块区域的位置上各有一个同款插口，一个装在固定件 A 上、一个
装在导轨小车 B 上；销扣进插口后 weld 锁死；判据为约束图连通分量 2→1，物理复核为推小车
不动（行程 0.0000 m 对 0.1002 m）。

review 意见（2026-08-27）：「原成功判据为小车保持静止，在视频中可辨识度低；改为将杆转动
至指定颜色区域，钉子颜色与目标区域颜色对应；任务时长应尽量短。」

改造决定：

| 项 | 首版 | 现版 | 理由 |
|---|---|---|---|
| 决策对象 | 两个同款插口，归属不同 | 两块同形区域，颜色不同 | 保留「二选一」结构；区分线索从「装在谁身上」改为「颜色」，画面可读 |
| 锁定机制 | weld 闩 | 无，靠关节摩擦 0.10 N·m 停住 | 少一个机制；摩擦值已在首版实测为「home 沉降 40 步不自转」 |
| 判据 | 约束图 + 行程测试 | 关节角窗口 + 静止 | 与画面一致；去掉 180 步的推小车段 |
| 契约字段 | `invariant=component_count`, `space=constraint_graph` | `invariant=pin_zone`, `space=joint_angle` | 已在 `task_taxonomy_zh.md` §4.4 登记为偏离 |
| 任务名 | `linkbar_merge_components` | `linkbar_rotate_to_zone` | 不再合并任何东西，名称随功能改 |

首版的记录（场景形态、高度链、行程测试两档读数、weld spike）保留在 git 历史
（提交 `a884929` 及之前的 `docs/develop/tasks/linkbar_merge_components_zh.md`）。

---

## 2. 场景形态

### 2.1 结构

| 实体 | 类型 | 碰撞 | 说明 |
|---|---|---|---|
| `pivot_column` | 固定圆柱 r 0.026 h 0.078 | 是 | 梁转在它上面 |
| `linkbar` | 单自由度铰链机构，7 个 `HingeShape` | 梁／转轴／轮毂／销／手柄座／手柄碰撞；销套环、手柄盖不碰撞 | 连续关节，`joint_friction 0.100` |
| `zone_left_00..06` / `zone_right_00..06` | 沿弧铺的 7 段直盒 | 否 | 每块角半宽 8°，径向 40 mm，厚 1 mm |
| `arc_tick_00..15` | 虚线 | 否 | 两区之间的圆弧 |

销、销套环、手柄盖三处同色。销是梁上最小的零件且在梁下方，套环与手柄盖把同一颜色放到
oblique / wrist 机位看得见的位置。

### 2.2 颜色

| 用途 | 值 |
|---|---|
| 区域 orange | `[0.88, 0.55, 0.10]` |
| 区域 blue | `[0.15, 0.45, 0.85]` |
| 梁 | `[0.42, 0.46, 0.52]` |
| 转轴／轮毂／手柄座 | `[0.55, 0.56, 0.58]` |
| 手柄 | `[0.12, 0.13, 0.15]` |
| 立柱 | `[0.50, 0.51, 0.53]` |
| 桌面 | 0.78–0.82 浅灰 |

橙与蓝对桌面浅灰、对梁的蓝灰都有明度或色相差。

### 2.3 区域的画法

`LinkbarRotateSceneBuilder._add_zones`：沿销的圆弧，从 `centre − half` 到 `centre + half`
均分 `segments` 段，每段一个 `gs.morphs.Box(fixed=True, collision=False)`，yaw 取该段中心角，
长度为该段的弦长 + 0.5 mm 搭接。7 段各 2.3°，弦弧偏差 < 0.1 mm。

两块区域出自同一个循环，除颜色外完全相同。

---

## 3. 机构与几何

高度（task 帧，桌面 z = 0）与首版一致，未动：

| 量 | 值 | 来源 |
|---|---|---|
| 立柱顶 | 0.078 | 轮毂底 0.093 下余 15 mm |
| 转轴底 | 0.080 | 立柱顶 + 0.002 轴承间隙（不能为 0，2026-08-20 实测卡死） |
| 梁 | 0.095–0.115 | |
| 销 | 0.052–0.095 | 销不碰任何东西；保留旧值以不动梁的质心与夹持实测 |
| 手柄 | 0.125–0.165 | 指腹在 0.150 |
| 手柄盖顶 | 0.171 | `approach_z 0.315` 对应指腹 0.212，余 41 mm |

枢轴 `x = +0.020`：共用 home 下手部落在轮毂正上方，手柄圆与指尖水平净空 43 mm
（首版 2026-08-20 实测结论，不改共用 home）。

派生量（`LinkbarRotateLayout`）：

| 量 | 公式 |
|---|---|
| `zone_center_xy(z)` | `pivot + arm_radius · (cos θ_z, sin θ_z)` |
| `in_zone(angle, z)` | `|wrap(angle − θ_z)| ≤ half_width` |
| `zone_at(angle)` | 第一个 `in_zone` 为真的区，否则 `None` |
| `target_zone()` | `cfg.zones.target` |
| `pin_color()` | `zone_color(target_zone())` |
| `nearest_zone(angle)` | 角差最小的区 |

`validate()` 拒绝：两区同侧；扫掠幅度出 [35°, 75°]；两区中心角距 < 2·half_width + 5°；
两区同色；`target` 不是 left/right。

---

## 4. 判定

### 4.1 读数

`LinkbarRotateEvaluator.classify(scene, rotate_ok)` → `LinkbarRotateState`：

| 字段 | 来源 |
|---|---|
| `pin_angle` | 关节角 |
| `pin_zone` | `layout.zone_at(pin_angle)` |
| `target_zone` | `layout.target_zone()` |
| `angular_speed` | 关节角速度 |
| `rotate_ok` | 原语自身的门（到位角、跟随误差、滞后、松手漂移、指位） |

`is_terminal = in_target and at_rest and rotate_ok`。

### 4.2 失败标签

| 标签 | 条件 |
|---|---|
| `rotate_check_failed` | 原语门未过 |
| `outside_zone` | `pin_zone is None` |
| `wrong_zone` | `pin_zone != target_zone` |
| `not_at_rest` | 角速度 > `max_angular_speed` |

### 4.3 时序

决策 → `PivotLeverPrimitive.run`（approach / descend / close / rotate / release / retreat）
→ 沉降 `success.settle_steps` 30 步 → `classify` → `final_hold_steps` 60 步。

---

## 5. 防捷径与随机化

三条随机化轴，均为 hydra 覆盖：

| 轴 | 叶子 | 说明 |
|---|---|---|
| 目标 | `task.zones.target` | left / right |
| 角位置 | `task.zones.left.angle_deg` / `task.zones.right.angle_deg` | 异侧，各在 [35°, 75°] |
| 颜色分配 | `task.zones.assignment.left` / `.right` | orange / blue 互换 |

对照规则（`run.oracle_mode`）：

| 模式 | 规则 | 期望成功率 |
|---|---|---|
| `oracle` | 转到 `target_zone()` | 1 |
| `nearest_zone` | 转到角差最小的区 | 0.5（target 与角位置独立抽样时） |

`tests/check_linkbar_planner.py` 四例交叉：oracle 4/4，`nearest_zone` 恰好 2/4。

`generation/layout_randomization.py` 尚未注册本任务；C4 任务未注册者不得进入 benchmark 产物。
分档方案见 `variation_and_difficulty_plan_zh.md` §3.8。

---

## 6. 文件集与登记点

| 文件 | 内容 |
|---|---|
| `topogym/tasks/connectivity/linkbar_rotate_to_zone.py` | `LinkbarRotateLayout` / `LinkbarRotateScene` / `LinkbarRotateSceneBuilder` |
| `topogym/verification/linkbar_rotate_to_zone_verifier.py` | `LinkbarRotateState` / `LinkbarRotateEvaluator` |
| `topogym/planning/linkbar_rotate_to_zone_planner.py` | `LinkbarOracleRule` / `NearestZoneRule` / `make_linkbar_rule` |
| `topogym/primitives/pivot_lever.py` | `PivotLeverPrimitive`（与 4.3 共用，未改） |
| `configs/task_configs/linkbar_rotate_to_zone_topogym_tabletop_v1.yaml` | 全部几何、区域、判据、时长 |
| `configs/linkbar_rotate_to_zone.yaml` / `_rotate.yaml` | 顶层组合 |
| `configs/run_configs/linkbar_rotate_to_zone.yaml` / `_rotate.yaml` | 运行档 |
| `demos/connectivity/linkbar_rotate_to_zone_inspect_demo.py` | sweep / seat / classify |
| `demos/connectivity/linkbar_rotate_to_zone_physical_demo.py` | 完整 episode |
| `tests/check_linkbar_planner.py` | 规划器离线门 |
| `tests/check_linkbar_zone_geometry.py` | 布局几何离线门 |

登记点：`topogym/core/taxonomy.py` `CATEGORIES["connectivity"]`；`topogym/tasks/__init__.py`、
`topogym/verification/__init__.py`、`topogym/planning/__init__.py` 的再导出。

已删除：`topogym/tasks/connectivity/_travel_probe.py`、`topogym/primitives/socket_weld.py`。
`tests/weld_constraint_spike.py` 保留为 weld API 的记录。

---

## 7. 步骤与验收状态

| 步骤 | 门 | 状态 |
|---|---|---|
| 离线：规划器 | `python tests/check_linkbar_planner.py` 退出 0 | 过（2026-08-27） |
| 离线：布局几何 | `python tests/check_linkbar_zone_geometry.py` 退出 0 | 过（2026-08-27，`.venv-gs110`） |
| 离线：配置组合 | 两个 demo `--cfg job` | 过（2026-08-27） |
| GPU：inspect sweep | `run.sweep_joint=true`，`reached_both=True` | 待跑 |
| GPU：inspect seat | `seat_phase=left/right/none`，`pin_zone` 分别为 left/right/None，`speed` < 0.05 | 待跑 |
| GPU：physical oracle | `task_success=True`，`angular_speed` 读数记入 §8 | 待跑 |
| GPU：physical nearest | 默认布局（target=left，left 更远）判 `wrong_zone` | 待跑 |
| GPU：physical offset | `run.target_offset_deg=12` 判 `outside_zone` | 待跑 |
| 录像 | oblique / front / wrist 三机位，`runs/videos/linkbar_rotate_to_zone/`，检查销色与区色可辨 | 待跑 |

命令：

```
python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.sweep_joint=true 2>&1 | tee runs/linkbar_zone_sweep.log
python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.seat_phase=left 2>&1 | tee runs/linkbar_zone_seat_left.log
python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo 2>&1 | tee runs/linkbar_zone_oracle.log
python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.oracle_mode=nearest_zone 2>&1 | tee runs/linkbar_zone_nearest.log
python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.target_offset_deg=12 2>&1 | tee runs/linkbar_zone_offset.log
```

---

## 8. 实测值

本节待 GPU 门填写。需要记录：

- 沉降 30 步后的 `angular_speed`（决定 `max_angular_speed 0.05` 是否合适）。
- 松手漂移 `release_drift`（首版实测门 5°；区域半宽 8°，到位容差 4°，二者之和须 < 8°）。
- 时长缩短后（`steps_per_phase 80`、`arc_settle 30`、`release_hold 30`）的 `max_lag` 与
  `follow_error`。若门触发，先回退这三项；`steps_arc 240` 不降。

首版实测（仍适用于保留的部分）：

| 项 | 值 |
|---|---|
| 关节摩擦 0.10 N·m | home 沉降 40 步梁不自转；0.05 时自转（2026-08-22） |
| 夹持 `grasp_qpos 0.001` | 能力 0.48 N·m，对扫掠阻力矩 0.125 N·m 余 3.8 倍 |
| 枢轴 x +0.020 | 手柄圆与指尖净空 43 mm |
| `approach_z 0.315` | 指腹对手柄盖余 41 mm |

---

## 9. 未决事项

- 随机化未注册到 `generation/layout_randomization.py`。
- `mdp.max_episode_steps` 无消费者（无 gym env）。
- `segments` 7 段为估计值；俯视机位若看出折线，加到 11。

## 10. 风险

- 静止判据依赖关节摩擦：若 GPU 上沉降 30 步后仍有 > 0.05 rad/s 的残余转动，先看
  `touching` 是否有接触，再调 `settle_steps`；不先调阈值。
- 连续关节无限位：`nearest_zone` 对照转错侧时销停在异色区，是期望画面；`validate` 的
  75° 上界保证手柄不出工作区。
- 时长缩短项未经 GPU 验证。
