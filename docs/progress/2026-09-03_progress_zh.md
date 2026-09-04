# 2026-09-03 进度归档：gate_cage_ball 变体部署（第 3 步）+ 取板原语修正 + band_untwist 变体部署（第 4 步）+ unlink_c_ring 变体部署（第 8 步）

> 范围：变体计划（`../develop/tasks/variation_axes_plain_zh.md` §6.2）第 3 步、gate 角点暴露的原语修正、第 4 步、第 8 步（含 GPU 与两处判据 / 原语修正）。
> 详细记录：`../develop/tasks/gate_cage_ball_zh.md`（新建）、`band_untwist_zh.md` §7（新增）、`unlink_c_ring_zh.md` §11（新增）；本文只汇总。第 4 步见 §7，第 8 步见 §8。
> 第 3 步（gate，含取板原语修正与角点门）已于本日 15:30 提交（38209a2）；第 4、8 步的改动未提交，见文末清单。

---

## 0. 一句话

一天落地了变体计划的三步。**第 3 步 gate_cage_ball**（§1–§4）：`timing:` 段 + 三个耦合叶子反解派生，GPU oracle 修 `pinched` 判据后 **10/10**；顺带加了全任务通用的**角点门**，gate 首跑 54/64 暴露取板原语丢姿态插值，修后 64/64。
**第 4 步 band_untwist**（§7）：镜像开关做防捷径离散轴，`end_gap` 派生，256 角点全过；GPU oracle seed 0–9 **10/10**，wrong_end 3/3，角点子集 5/6（c130 落点规则问题，待定）。
**第 8 步 unlink_c_ring 提前做**（§8）：`checks()` 加可达与手净空两行，抓取方位角派生，32 角点全过、拒绝率 0。GPU：08-24 的 `passed_through` 基线失败复现后定性为判据口径（gateway −2.6 mm 对 no_align −9 mm 两群分开），判定器改判 `success.max_pass_through_depth` 5 mm；首跑 seed 0–9 oracle 7/10、角点 oracle 16/32，失败全在原语的对准门，机制是摆动段 9 mm 的稳态落后；给摆动段加闭环修正后 oracle **10/10**、角点 **32/32**，no_align 10/10 判失败。第 8 步六项齐全。

## 1. 会话里定下的决定

| 决定 | 内容 |
|---|---|
| 校验函数拿不到 env / run 段 | task yaml 加 `timing:`（`sim_dt` 0.01、`safety_margin` 0.15 从 run 配置搬来、`ready_margin` 0.10 新）；demo 断言 `timing.sim_dt == env.sim.dt`，并断言 Layout 的 `t_ready()` / `insert_duration()` 与 `GatedInsertPrimitive` 同名公式相等 |
| 包络 | `speed` [0.08, 0.16]、`center_x` [0.055, 0.095]、`rack.center_y` ±0.03 独立抽；`flat_end_y`（判据 A）、`release_y`（判据 B）、`rack.center_x`（不与导柱重叠）由归一化量派生。原表 `release_y` 下界 −0.46 越过轨底起点，弃用 |
| 不约束的量 | `hover_wait = entry_delay − t_ready` 的正负只报告：它是三条触发规则拉开差距的机制 |
| 第三条对照规则 | `FixedDelayRule`（`run.trigger=fixed_delay`，`run.fixed_delay_s` 3.6）：不感知球的策略的上限 |
| 角点门 | 随机 sweep 抽不到包络边界，可解性判据恰在那里最紧。加边界值测试：从 yaml `variation:` 块构造全部顶点（uniform 两端点 × choice 全部值；spaced_pair 用手写命名对），离线过派生 / 校验 / `checks()`，再逐格送进物理。只走 demo 的固定布局路径（`run.randomize_layout=false` + `task.*` 覆盖），不碰 `randomize_task_cfg`，seed→变体映射不变 |

## 2. 做了什么

- Layout：`t_ready` / `insert_duration` / `window_margin` / `last_commit` / `ready_margin` / `hover_wait`；三个 `*_bounds` / `*_from_frac`；`rack_channel_gap`、`hover_reach`；`checks()` 五行、`validate()`；模块级 `derive_task_cfg` / `validate_task_cfg`；builder 建场景前 `validate()`。
- yaml：`timing:`、`reach:`；`channel.flat_end_y_min/max/flat_end_frac`、`ball.spawn_entry_margin/spawn_door_margin/release_frac`、`gate_rack.x_min/channel_gap/x_frac`；头注两条判据改指向 `checks()`；末尾 `variation:` 块。
- 规则：`FixedDelayRule`、`make_trigger_rule`；三条规则的 `decide` 多一个 `elapsed_s`。
- demo：两个 demo 接 `randomize_task_cfg` + `variant` 行；physical demo 加 `checks` 行、dt 与时序断言、`safety_margin` 改读 task、死键 `task.feed_ramp.rise` 文案改掉、`EpisodeKey.variant_id`；inspect demo 加 `final_hold_steps`。
- run 配置：三个变体键；gate 配置删 `safety_margin`、加 `fixed_delay_s`、尾注改写。
- 离线门：`check_variant_rng.py` gate 段；`tests/check_gate_cage_ball_geometry.py`。
- sweep：`bash_scripts/tests/gate_cage_ball_variation_sweep.sh`（visual / oracle / greedy / fixed）。
- 角点门（三任务通用）：`tests/check_variant_corners.py`（`TASKS` 表登记 yaml / physical config / Layout / 命名对；linkbar 尚无 `checks()`，用 `_linkbar_checks` 把 `validate()` 的四条不等式改写成余量并加 `sweep_deg`；每个角点经 Hydra compose 复现读数，`--manifest` 输出 TSV）；
  `bash_scripts/tests/variant_corners_sweep.sh <task> [oracle visual 对照…]`（先跑离线门产清单，再每格一跑；`CORNERS="c002 c016"` 选格、`DRY_RUN=1` 只打印命令；产出 `runs/<task>_corners/<时间戳>/{corners.tsv,summary.csv,*.log}`）。用法与读法见 `tests/README.md`、白话文档 §4.3。
- 文档：`gate_cage_ball_zh.md` 新建；计划文档 §2.5 / §3.6 / §5；白话文档 §4 / §6.2；README 索引。

## 3. 实测

| 门 | 结果 |
|---|---|
| `check_variant_rng.py`（六段） | 全 PASS。gate 首抽拒绝率 0.000；球先到 462 / 臂先到 538 |
| `check_gate_cage_ball_geometry.py` | PASS：seed 0–199 checks 全过；16 个包络角点 slack 0.00–5.45 s；时序公式与原语一致；三条规则四个合成状态判定正确 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| `check_variant_corners.py`（离线） | 三任务全 PASS：linkbar 20、gate 64、diverter 256 个角点全部可行、无拒绝，Hydra compose 读数一致 |
| GPU sweep seed 0–9 首跑 | visual 10/10；oracle 6/10，四格 `ball_pinched_in_doorway`；greedy 4/10；fixed 6/10 |
| seed 5 复盘 | 闸板整个坐到轨底（`gate_bottom_z` 0.009）、球在门内 47 mm 自由往复——任务其实成功；`pinched` 只问「球心在门口 ±51 mm 内」，短封闭区里判定时刻球常在门口附近 |
| 判据修正后重跑三组（`*_judgefix/`） | oracle **10/10**（悬停 0–2.34 s 与 `hover_wait` 一致）；greedy 8/10（只在臂提前 ≥ 0.96 s 时失败，其余「从下降中的闸板底下钻进去」）；fixed_delay 6/10 |
| GPU 角点 sweep，oracle 组（`runs/*_corners/20260902_205605/`，判据修正之后跑） | linkbar **20/20**；diverter **256/256**（`knob_reach` 0.625–0.690）；gate **54/64**，每格 8–13 s。gate 失败格见 §4 |
| gate 取板原语修正后重跑（`runs/gate_cage_ball_corners/20260903_145828_slerpfix/`、`runs/gate_cage_ball_variation/20260903_145828_slerpfix/`） | 角点 oracle **64/64**，64 格 `finger_qpos` 0.0062–0.0069、`plate_yaw` 0.22–0.35°（修前那一角 −0.0010 / 2.19°）；时序最紧的 c002 / c034 也过；seed 0–9 oracle 10/10、greedy 8/10、fixed 6/10，逐格与判据修正后那轮相同 |
| `check_gate_cage_ball_geometry.py`（六行 + `approach_z=0.220` 必拒）、`check_variant_rng.py`、`check_variant_corners.py --task gate_cage_ball`、`check_configs_compose.py`、`check_demo_configs.py` | 全 PASS；64 角点 `approach_clearance` 恒 0.032 |

## 4. 遗留 / 观察

- **判据修正**（`topogym/verification/gate_cage_ball_verifier.py`）：`pinched` 改为「闸板挡着 且 板被顶住没坐到位（板底高于 `gate.seated_bottom_z` 5 mm 以上）且 球体在板的 y 跨度内」，
  即只有板压在球上才算夹住。旧定义在默认实例上没暴露只是窗口相位凑巧。与 diverter 的 `max_lag` 同一类：变体把判据里的隐含假设晒了出来。
- greedy 8/10 偏高，原因是下板 1.0 s 慢于臂的提前量；不按它的分数回调包络。若要让它更接近随机，动的是 `motion.insert_steps`（原语参数），另议。
- **gate 角点 10/64 失败，未处理**。全部落在 `gate_rack.center_y=−0.03` 且 `gate_rack.x_frac=0`（该组合 16 格，失败 10）：
  - 8 格 `grasp_check_failed`（c016/018/020/022/048/050/052/054）：都在 `channel.center_x=0.095`，与球速和两个派生 frac 无关；`phases=8/15`，死在取板后的 `lift_test`。形式上判负的是 **`plate_yaw` 2.19° > `max_plate_yaw_deg` 2.0**；同格 `finger_qpos` −0.0010（正常格被板挡在 0.0063–0.0075），按原语文档的定义是「夹了个空」，只因 `min_finger_qpos` 为 null 不判；`lift_delta` 0.106 是 assisted attachment 带起来的。
    **根因（09-03 逐步追踪 + 对照实验，GPU 复现）**：板在 approach 阶段就被手指扫走，descend / close 还没开始。approach 是从 home 位（指开合轴沿 x）30 步移到停放架上方 `approach_z` 0.240，同时姿态要转到 `default_ee_quat`（指开合轴沿 y），腕转 90°。`GatedInsertPrimitive._move` 收了 `start_quat` 却没用：每一步给 IK 的姿态目标都是最终姿态，而 `PivotLeverPrimitive._move` / `AxialInsertPrimitive._move_linear` 都用 `_quat_slerp` 把姿态在 30 步里插值——从 axial_insert 派生时把 slerp 丢了。后果：IK 每步面对 90° 的姿态误差，给出的中间关节角让手下沉到指令下方 63–70 mm、倾 17–18°（只转腕不平移也是 70 mm；放慢到 120 步仍 70 mm，说明是解序列本身而不是动态滞后）。`approach_z` 只给指尖 12 mm 静态净空（指尖 ≈ 0.117，板顶 0.105），指尖从板顶边缘扫过：第 12 步起两根（耦合的）手指被顶着合拢到 −0.001，板被推向 −x 14 mm、偏摆 2.1°；随后合爪、attachment 把已偏的板挂上手，`lift_test` 读到 2.19°。对照：同一移动加 slerp，下沉 1.5 mm、倾 1.6°。另有一项独立的水平滞后（165 mm 平移在 0.3 s 内，终点落后 40 mm，不转腕也一样），settle 30 步即归零，不是撞板原因。c000 同一机制但推得更远（板离手 69 mm），偏摆只 1.76°，判「过」，全程手指空夹、靠 attachment 拎着插进了槽——是现门漏掉的假成功；停放架在 `center_y=−0.03`、`x_frac=0` 的 16 格里指位全部 ≤ 0.0018，都是这种。停放架在 `center_y=+0.03` 时同样的扫掠从板旁边过、不碰，指位保持 0.040。可达性不是问题：底座到停放架 0.451 m，`lift_test` 时手到位 ±4 mm。
    **已处置（oracle 侧，包络不动）：** ① `gated_insert._move` 补 `_quat_slerp`（逐字同 axial_insert，用上原本收了没用的 `start_quat`）；② `min_finger_qpos` null → 0.004；③ `checks()` 第六行 `approach_clearance = approach_z − HAND_TO_PAD_Z − 停放架上板顶 ≥ 0.030`（现值 0.032，不随任何轴变）；④ 几何测试加 `approach_z=0.220` 必被 `validate()` 拒。**用户定：不加 settle**（会把 `t_ready` 2.40 → 2.70 s、改变 `release_y` 派生上界，v=0.16 且封闭区最短的格会被挤空），**`approach_z` 不动**。重跑结果见 §3 末两行：64/64。
  - 2 格时序：c002 `pinched`、c034 `ball_outside`，都是 `center_x=0.055, flat_end_frac=0, release_frac=1`（球放得最近），`slack` 只有 +0.10 s、`window_margin` ≈ 0。这是包络里时序最紧的顶点，和随机 sweep 里 oracle 10/10 不矛盾——随机抽不到它。**原语修正后这 2 格也过了**（板不再带 1.76° 偏摆进 3 mm 槽；只是观察，`ready_margin` 未动）。旋钮是 `timing.ready_margin`（`release_y` 上界由判据 B 取等给出）：0.10 → 0.30 时 c002 的上界 −0.144 → −0.160；但 v=0.16、`flat_end_frac=0` 的格在 0.10 时区间只剩 0.024 m，0.30 就空了（拒绝）。抬 `ready_margin` 要么同时抬 `safety_margin`（判据 A，`flat_end` 下界随之变长），要么接受高速端拒绝率上升；改后重跑拒绝率门。
  - 两类都按 09-02 原则处理：修 oracle 执行参数或收窄该轴，不加重试。

- `motion.*_z` 仍是手写绝对高度（§2.5 约定 1）；本步的轴不动 z，欠账留着。
- `TopoGym_变体参数轴表.xlsx` 的 gate 行需手动同步。

## 5. 当前进度与下一步

变体计划 §6.2 的落地状态（截至本日晚）：

| 步 | 任务 | 离线六项 | GPU | 备注 |
|---|---|---|---|---|
| 0 | 通用层 | 完成 | — | `VariantRng`、yaml `variation:` 块、`derived` kind、拒绝率门 2%、角点门（本日新增，五任务通用） |
| 1 | linkbar_rotate_to_zone | 完成 | oracle 10/10，角点 20/20 | 09-02 改 `init_frac` 派生后 seed→变体映射变了，09-01 的十格未重跑复核 |
| 2 | diverter_route_ball | 完成 | oracle 10/10，角点 256/256 | `max_lag` 超 6° 门是既有问题 |
| 3 | gate_cage_ball | 完成 | oracle 10/10，greedy 8/10，fixed_delay 6/10，角点 64/64 | 本日 §1–§4 |
| 4 | band_untwist | 完成 | oracle 10/10，wrong_end 3/3，角点子集 **5/6** | 本日 §7；c130 落点规则待定 |
| 8 | unlink_c_ring | 完成 | oracle **10/10**，no_align 10/10，角点 **32/32**，visual 10/10 + 32/32 | 本日 §8；判据 `passed_through` 与摆动段闭环修正两处改动 |
| 5 | swap_crossing_sign | 未开始 | — | 场景与 untangle_continuous 同源、FEM 绳，等 GPU 空闲能连带回归时做 |
| 6–7、9–12 | 其余 | 未开始 | — | 按 §6.2 表顺序 |

§4.3 的 50 seed 全包络 sweep 与 §4.4 划档尚未开始，等 13 个任务的变体逻辑都立住再做。

本日三步共同的规律：每个任务的变体 sweep 都把执行链或判据里的一个隐含假设晒了出来（gate 的 `pinched` 定义与取板原语丢姿态插值、band 的 c130 落点规则、unlink 的 `passed_through` 口径与摆动段稳态落后），处置都是改判据定义或原语，包络只在离线阶段按 `checks()` 的行收窄过一次（unlink 的 `gap_azimuth` ±15 → ±10）。

**下一步，按顺序：**

1. **band_untwist c130 的处置**：角点 c130（开口叶最大 + 镜像）抓起成功但落下压出第二个交叉，是 planner `place_beside` 落点规则的问题。二选一：改落点规则，或收窄 `open_lobe_radius` / `heading_deg`。见 `band_untwist_zh.md` §7.4。**09-04 已处置**：落点只量到另一插头、不看那股的弧，零余量的是「开口叶 0.065 且绳头间距下限」64 格（c002 孪生过是运气）；改 `place_beside` 沿圆外摆到离留桌那股整条折线 ≥ 35 mm，`checks()` 加落点两行，见 §7.5。
2. **linkbar 十格复核**：09-02 改 `init_frac` 派生后映射已变，`linkbar_variation_sweep.sh` seed 0–9 重跑一遍，刚体，几分钟。
3. **第 5 步 swap_crossing_sign**：`braid.py` 交叉位置改为接收采样值并裁剪窗口、接入 `verify_braid_spec`、planner 抬升守卫；改动落在与 untangle_continuous 共用的场景构造上，两个任务要一起回归，FEM 绳一格分钟级。
4. 之后按 §6.2 表顺序：rope_winding / rope_unwinding（先做绳长反解与 closure 路线）、cloth 两项、ring_transfer（先把三个搬运高度改为按柱顶推导）、cloth_fold、bar_through_hole。

**未提交**：第 3 步（gate）已随 38209a2 提交；第 4 步（band）与第 8 步（unlink）的改动仍在工作区（29 个文件），文件清单见 §6。建议按步分两次提交。

## 7. band_untwist 变体部署（第 4 步，同日下午）

详细记录 `band_untwist_zh.md` §7。按前三步的六项清单部署：

| 决定 | 内容 |
|---|---|
| 防捷径离散轴 | `figure_eight.over_end ∈ {0,1}`：几何模块把局部 b 分量取反并把点序反转，两绳头位置不变、上下股互换；`layout.over_end` 读 cfg；planner / judge 不改（本来就读实测值） |
| 连续轴 | `heading_deg` ±30、`center_x` [−0.01, 0.05]、`center_y` ±0.03、`half_angle_deg` [30, 60]、`closed_lobe_radius` [0.032, 0.055]、`open_lobe_radius` [0.040, 0.065]；`center: [x, y]` 拆成两个标量键（随机化器不支持列表元素） |
| 派生 | `end_frac` → `end_gap ∈ [min_clearance 0.070, 0.95 × 2·open_lobe_radius]`；`min_clearance` 从代码默认值显式写进 yaml |
| `checks()` 六行 | 绳头间距、开口比、转角半径（3D 外接圆含鼓包，`lift_ramp` 被截短时由它判）、足迹（margin 0.040 ≥ `place_clearance`，落点由此在工作区内）、抬升高度 ≤ 0.40（与 planner 公式同构）、管底净空。纯函数在 `_figure_eight_geometry.py`（离线门保持 Genesis-free），钩子在 `band_untwist.py` |
| 插值 | task yaml 有 26 处 `${prefabs…}`，校验只拿得到未解析配置：`figure_eight.tube_radius` 是 `rope.radius` 的字面量副本、`workspace:` 段是 `manipulation_space.workspace` 的副本，builder 与离线门各断言一处相等。`check_variant_corners.py` 的叶子遍历改为不解析插值 |
| 不做 | 难度划档；`BandUntwistLayout.seed` 保留为 run seed |

离线：`check_band_untwist_geometry.py`（镜像格实测 1、256 角点六行全过且恰一个交叉、两个负例拒）、`check_variant_rng.py` band 段（`over_end` 479/521，最大预测抬升 0.298，拒绝率 0）、`check_variant_corners.py --task band_untwist` 256 角点 compose 一致、配置组合与 demo 配置全 PASS。
角点最紧余量：转角半径 +3.1 mm（半角 60°、闭合叶 0.032：`lift_ramp` 被截到 14.8 mm）、足迹 +9.7 mm、抬升 0.309 / 0.40。区间未收窄。

GPU（4090，FEM 绳，oracle / wrong_end 一格 ≈ 5 min，visual 25 s；`runs/band_untwist_variation/20260903_155802_*/`）：
oracle seed 0–9 **10/10**（沉降后 `gt_match` 全 True，1→0，绳头落桌，无 blow-up），`over_end=1` 的 6 格 planner 全抓端 1——镜像轴生效；
wrong_end seed 0–2 3/3 判 `wrong_end`；visual 十格可分。预测抬升与实测差 −24 / +26 mm（半角大的格实测偏高），不是上界，最大预测 0.309 距 0.40 还有 91 mm；docstring 已改口。
角点子集 c002/c130（抬升最高）、c008/c136（转角最紧）、c036/c164（足迹最贴边）oracle：**5/6**，c130（抬升最高那一角的镜像，抓端 1）抓起成功但落下压出第二个交叉 1→2；
孪生 c002 抓端 0 成功。是 planner `place_beside` 落点规则在这一角的问题，不是抓取或抬升；处置（改落点规则 vs 收窄 `open_lobe_radius` / `heading_deg`）待定，见 `band_untwist_zh.md` §7.4。

## 8. unlink_c_ring 变体部署（第 8 步，同日傍晚至夜间）

详细记录 `unlink_c_ring_zh.md` §11。选它而不按表走第 5 步的理由：它已有 `SceneGeometry.checks()`，纯刚体 GPU 一格秒级；swap_crossing_sign 的场景与 untangle_continuous 同源、FEM 绳，要等 GPU 空闲且能连带回归。

| 决定 | 内容 |
|---|---|
| 防捷径离散轴 | 无。开口不对准管身就卡住，物理保证（`variation_axes_plain_zh.md` §3 已定） |
| 连续轴 | `stand.hang_yaw_deg` 180 ± 15、`fixed_ring.center_x/center_y` ± 0.020、`c_ring.gap_deg` [21.5, 28]、`c_ring.gap_azimuth_deg` **315 ± 10**（计划 ±15）；`center: [x, y, z]` 拆成三个标量键 |
| 派生 | `primitive.grasp_azimuth_deg = gap_azimuth_deg + primitive.grasp_offset_deg`（112.5）mod 360，`derive_task_cfg` 覆盖；固定布局仍用 yaml 的 67.5 |
| `checks()` 七行 | 原五行 + 「抓取点可达」（`reach:` 段照 gate_cage_ball，`hang_yaw 0` 的 0.738 m 被排除）+ 「手在闭合环之外」（yaml 注释的 45 mm 规则写成判据：R·sin(grasp_az) − 0.045 > 0）。两行都在纯 numpy 的 `SceneGeometry`，`UnlinkCRingLayout.checks()` 转发 |
| 包络收窄 | 手净空行在 gap_az 302.4° 以下失败，±15 约 8% 拒绝超 2% 门；收到 ±10 后角点最紧 +1.39 mm，拒绝率 0 |
| 不做 | 离线阶段不碰判定器与原语，GPU 复现基线后再按 §11.4 的规则定（结果是两处都改了，见下）；`align_rotation()` 等死代码、§3 参数表的过期值不动 |

离线：`check_c_ring_clearance.py`（加第五段：32 角点七行全过、出生 Lk=±1、gateway 不卡、八条非 gateway 全卡；负例 gap_az 295 / hang_yaw 0 拒）、`check_gateway_slide_path.py` 不变、`check_variant_rng.py` unlink 段（1000 seed 拒绝率 0，最小手净空 1.41 mm、最小单边净空 1.26 mm）、`check_variant_corners.py --task unlink_c_ring` 32/32 compose 一致、demo 配置与 Hydra 组合全 PASS、CPU build_only 冒烟打出 checks / variant 行、角点 sweep DRY_RUN 32 格命令正确。
角点最紧余量：手净空 +1.39 mm（gap_az 305）、开口过杆 +2.52 mm（gap 21.5）、抽出离桌 +2.0 mm；其余 ≥ 26.8 mm。

GPU（4090，纯刚体，一格 8–18 s，同日晚）：
基线复现与 08-24 逐阶段一致（gateway 抬升段 −2.63 mm、no_align 抽出段 −8.97 mm），判定规则能核的三条都指向判据口径，判定器 `passed_through` 改判新叶子 `success.max_pass_through_depth` 0.005，`jam_depth` 1 mm 留给离线扫描与探针；改后 seed 0 gateway success=True、no_align 仍判失败。
seed 0–9：visual 10/10，oracle **7/10**（seed 5/6/8 `align_failed`，3.14/4.31/3.14° 对门 3.0°），no_align 10/10 判失败（−8.84 … −9.00 mm）。角点：visual 32/32，oracle **16/32**——`gap_azimuth_deg=305` 的 16 格全败（残差 3.7–5.8°），325 的 16 格全过（0.4–1.9°）。
机制：两段直线摆动按抓取后位姿算一次不再修正，每段 5.5–6 mm 稳态落后，叠成 9 mm（基线就有）；固定方向的位置偏差在开口方位角离它越远时垂直分量越大，角残差随出生开口角单调上升，3.0° 的门在基线只剩 0.35° 余量。物理上 3–4° 能出来（中止后的探针把「仍互锁」的环推出去了）。
处置（用户选闭环修正，不改门、不收包络）：`gateway_extract.py` 两段走完后重测环心，把差值加到命令点再走一段，最多 2 次（`primitive.align_correct_passes` / `align_correct_tol` 两个新键）。seed 0：一次修正 5.4 mm → 0.1 mm，残差 2.65° → 0.28°；305 角 0.33°。重跑 oracle 十格 **10/10**（残差 0.2–0.3°）、32 角点 **32/32**（0.2–0.4°，修前 0.4–5.8°），面间距 −2.2 … −3.5 mm 全在 5 mm 门内（`runs/*_correct/`）。

## 6. 文件清单

```
topogym/tasks/connectivity/gate_cage_ball.py（含 checks 第六行 approach_clearance、plate_top_on_rack）
topogym/primitives/gated_insert.py（_move 姿态插值 _quat_slerp）
topogym/planning/gate_cage_ball_planner.py, topogym/planning/__init__.py
topogym/verification/gate_cage_ball_verifier.py（pinched 定义）
configs/task_configs/gate_cage_ball_topogym_tabletop_v1.yaml
configs/run_configs/gate_cage_ball.yaml, gate_cage_ball_gate.yaml
demos/connectivity/gate_cage_ball_physical_gate_demo.py, gate_cage_ball_inspect_demo.py
tests/check_variant_rng.py, tests/check_gate_cage_ball_geometry.py（新）, tests/check_variant_corners.py（新，三任务角点门）, tests/README.md
bash_scripts/tests/gate_cage_ball_variation_sweep.sh（新）, bash_scripts/tests/variant_corners_sweep.sh（新）
docs/develop/tasks/gate_cage_ball_zh.md（新）, README.md, variation_and_difficulty_plan_zh.md, variation_axes_plain_zh.md
docs/progress/2026-09-03_progress_zh.md（本文）

第 4 步（band_untwist）：
topogym/tasks/entangle/_figure_eight_geometry.py（over_end 镜像、end_gap_bounds/from_frac、chord_turn_radii、open_half_arc、predicted_lift、figure_eight_checks）
topogym/tasks/entangle/band_untwist.py（over_end 读 cfg、center_x/y、checks/validate、derive_task_cfg/validate_task_cfg、build 前 validate + tube_radius 断言）
configs/task_configs/band_untwist_topogym_tabletop_v1.yaml（center 拆键、over_end/end_frac/end_gap_max_ratio/tube_radius、min_clearance、workspace 段、variation 块）
configs/run_configs/band_untwist.yaml, band_untwist_inspect.yaml（变体三键；inspect 加 static_only/final_hold_steps）
demos/entangle/band_untwist_physical_pinch_demo.py, band_untwist_inspect_demo.py（randomize_task_cfg、variant/checks 行；inspect 录像 + static_only）
tests/check_band_untwist_geometry.py（新键、镜像、256 角点、负例）, tests/check_variant_rng.py（band 段）, tests/check_variant_corners.py（TASKS 登记、_leaves 不解析插值）, tests/README.md
bash_scripts/tests/band_untwist_variation_sweep.sh（新）, variant_corners_sweep.sh（band 分支）
docs/develop/tasks/band_untwist_zh.md §7, variation_and_difficulty_plan_zh.md §3.12, variation_axes_plain_zh.md §3/§6.2, configs/GEOMETRY_PARAMETERS_zh.md

第 8 步（unlink_c_ring，离线 + GPU 后两处修正）：
topogym/tasks/entangle/_c_ring_geometry.py（HAND_HALF_WIDTH、SceneGeometry 三个新字段与 grasp_point/grasp_reach/hand_clearance、checks 第六七行、center_x/y/z + primitive/reach 读取）
topogym/tasks/entangle/unlink_c_ring.py（Layout.checks 转发、derive_task_cfg/validate_task_cfg）
configs/task_configs/unlink_c_ring_topogym_tabletop_v1.yaml（center 拆键、grasp_offset_deg、reach 段、variation 块、头部不等式清单 5→7）
configs/run_configs/unlink_c_ring.yaml, unlink_c_ring_extract.yaml（变体三键；inspect 加 final_hold_steps；extract 头部过期测试名改 check_gateway_slide_path）
demos/entangle/unlink_c_ring_physical_extract_demo.py, unlink_c_ring_inspect_demo.py（randomize_task_cfg、checks/variant 行；inspect static_only 走 final_hold_steps 步供录像）
tests/check_c_ring_clearance.py（第五段 variation envelope：32 角点 + 两个负例）, tests/check_variant_rng.py（unlink 段）, tests/check_variant_corners.py（TASKS 登记）, tests/README.md
bash_scripts/tests/unlink_c_ring_variation_sweep.sh（新）, variant_corners_sweep.sh（unlink 分支；failure_reason/failure_label 都能解析）
topogym/verification/unlink_c_ring_verifier.py（passed_through 改判 max_pass_through_depth）
topogym/primitives/gateway_extract.py（摆动段闭环修正 align_correct_passes / align_correct_tol；demo 与 yaml 接线）
docs/develop/tasks/unlink_c_ring_zh.md §5/§10/§11, variation_and_difficulty_plan_zh.md §3.5/§6 表, variation_axes_plain_zh.md §6.2, configs/GEOMETRY_PARAMETERS_zh.md
```
