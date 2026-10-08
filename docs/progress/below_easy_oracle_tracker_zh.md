# very_easy / easier oracle 开发与检验：工程目标与进度

> 建立：2026-10-06。最后核对：2026-10-06 20:50 CDT（`dev/jianwen`，HEAD `d86ea023a`，已合并 `rcb/dev/jianwen` 至
> `da47d3a49`：v19 发布、布料静止速度改读法、rope 两档环境统一、slotted easier 结论）。
> 每次推进后更新第 3 节状态表、第 7 节评分记录和第 9 节变更记录。只登记有证据目录支撑的结论；lab 的结果注明 lab 路径。

同一计划的另两部分各有跟进页，本页不重复：

- 第二部分「物理设置调整」中的 Orbits 五档加速：[orbits_speedup_tracker_zh.md](orbits_speedup_tracker_zh.md)
- 第三部分「proof 与 session 选择」（该页 F2）及 helper 升级：[helper_upgrade_test_fixes_tracker_zh.md](helper_upgrade_test_fixes_tracker_zh.md)

交接原文：[ORACLE_FIXES_FOR_JIANWEN.md 第 11 节](../rcb/ORACLE_FIXES_FOR_JIANWEN.md#11-v18-below-easy-oracle-sweep-buzz-fixed-rope-and-knot-easier-analysed-topospeed-2026-10-06)
（rope、knot）；[ORACLE_FIXES_2_FOR_JIANWEN.md](../rcb/ORACLE_FIXES_2_FOR_JIANWEN.md) 第 6 节（orbits、blanket、knot）。

## 1. 名词与规则

- **very_easy / easier**：各家族在原 easy 之下新增的两档简化场景，难度须满足 very_easy < easier < easy。
- **oracle**：私有参考解程序。在 Harbor 冻结的 Session 中只提交机器人动作；本地原生成功不等于评分通过。
- **privileged 模式**：oracle 与模拟器在同一容器，可读特权状态（如绳、布的材料点位置）。交付物是一条动作轨迹；
  verifier 在两个新进程中各回放一遍判分。
- **standard 模式**：模拟器在 oracle 打不开的 sidecar 中，只能发动作、收图像和本体感觉，不能 reset。oracle 的参考
  动作行经 standard service 下发，一个控制步内每个臂关节最多变化 0.04 rad，有行被裁剪或拒绝即失败；verifier 另做
  独立回放。
- **正式评分 / grade / solved**：Harbor verifier 写出的 `results.json` 中的 grade 与 `reward.json` 中的 success，1 为解出。
  每个任务的每一档、每个模式各一个。
- **控制步 / 行**：一个控制步是 25 ms 仿真时间（rope 两档若改用原三档配置变为 40 ms，见 D2）；轨迹的一行是一个控制步的动作。
- **72 min 规则**：一次完整 oracle 执行（含建场景）不超过 agent 6 h 预算的 20 %。超出须用户书面豁免；先例为
  fiber hard 185 min、buzz hard 74–87 min。

## 2. 工程目标

收口须同时满足：

1. **五个明确交接的任务**——rope_threading very_easy / easier、orbits very_easy / easier、blanket_flatten easier——
   逐个做到：
   1. oracle 在冻结实例上原生 Task success；
   2. privileged 正式评分 grade=1；
   3. standard 正式评分 grade=1；
   4. 单次执行 ≤ 72 min，或有用户豁免；
   5. 第 7 节登记两个模式各一行：代码版本、镜像、物理配置、执行模式、结果、失败原因，以及回放或视频路径。
2. **knot_untying easier（条件接手）**：拿到 lab 对 `7571e4194` 版 oracle 的正式评分。双模式通过则登记收口；
   任一失败则按第 4.4 节定位修复，再满足 1.1–1.5。
3. **执行语义**：受第三部分「proof 与 session 选择」影响的 Harbor oracle，先在第 5 节 D4 写明采用的执行语义，
   再按选定流程验证。
4. **汇总**：第 3 节把六项的最终状态分成「通过」「仍失败」「等待评分」三类（暂缓的项另注）。

起点（10-06 交接截图）：五个任务的 privileged 与 standard 均未通过；knot easier 没有最终结果。

## 3. 状态总表

| # | 任务 / 档 | privileged | standard | 停在哪里（最近一次） | 卡在哪里 | 状态 |
| - | - | - | - | - | - | - |
| R1 | rope very_easy | **1**（本机 v19，第 770 行严格达成，两次回放一致） | **1** | 新路线（10-06 晚，用户思路）：在环心下方 3.5 cm 平移，让绳尾沿环的法线穿过半圆平面，再下放；按实测绳-环间隙闭环下压 | — | **通过**（代码未提交；10-07 用最终代码重评仍为 1，770 行动作与终态 hash 和首次逐位相同） |
| R2 | rope easier | **1**（本机 v19，第 1119 行严格达成，两次回放一致） | **1** | 新接力路线（10-07，用户思路）：右手在离端头 10 cm 处抓，停在环面入口侧 3.5 cm，只让绳尾穿过；左手送绳前先到出口侧等待，再从侧面（夹爪竖直）按实测位置抓离端头 2.5 cm 处；右手松开后退 | — | **通过**（代码未提交） |
| O1 | orbits very_easy | 0（lab 两次，`7571e4194`；本机停在第 99 行） | 未运行 | lab 修掉前两处后（`79c21d1f6`，已合并），停在右臂接近：oracle 自己的双臂间隙检查 0.47 mm < 1 mm | Orbits 加速 | **暂缓**：先做加速（用户 10-06） |
| O2 | orbits easier | 0（lab；本机停在第 195 行） | 未运行 | lab 修复后，`fresh_bight_carry` 抓持误差 14→23 mm，绳被压扁 0.25 s，Session 终止 | Orbits 加速 | **暂缓**：先做加速（用户 10-06） |
| B1 | blanket easier | **1**（本机 v19，22:52，严格达成于第 2336 行，两次回放成功） | 进行中（22:53 起，回放 privileged 轨迹） | 远侧半张对折；三段路线（翻回翻角 → 两手翻页抓边缘 → 抓卷边内侧拉到离展平 3 mm）；现场运行覆盖率 0.9999、最高 4 mm | standard 结果 | **privileged 通过** |
| K1 | knot easier | lab 报告已跑通（用户 10-06 转述）；本机 v18 冻结快照 `source03`：grade 1、solved 1 | 同左 | — | lab 的评分版本与证据路径待补 | **通过**（lab 证据待补） |

本机正在运行的评分作业（不归本页所有，结果出来后登记）：`runs/test_results/harbor_below_easy_v18_20261006_ik01/`，
镜像 `topogym-below-easy:v18-20261006-ik01`，10 个家族的两档双模式，队列中有 knot 与 orbits。它的源码快照是
`7571e4194` 加当时的工作区改动，**不含** lab 的 orbits 两处修复，所以其中 orbits 的结果只反映修复前的代码。它是 v18
标签：其中 rope、blanket 共 8 项（原因 D1 而搁置）不应再在 ik01 中跑——rope 两档已换新配置，blanket 要用 v19。
这一点需要告知该作业的负责会话。20:35 CDT：buzz very_easy 双模式 1；buzz easier privileged 的容器处于暂停状态
（不是资源守护进程暂停的，原因未知），作业没有推进。

## 4. 各任务现状与下一步

### 4.1 rope_threading very_easy / easier（R1、R2）

场景：ALOHA 双臂，桌上一根 IPC 有限元软绳。very_easy 只有一个下半圆环 R1（上半圈移除），要把绳搭进半圆下方的
中央弧段；easier 是一个完整的 R1（净孔径 138 mm），绳要沿材料方向恰好穿过一次，并由入口侧的送绳手交给出口侧的
接绳手（两手有同时抓持的阶段）。两档都要求整绳最大速度 ≤ 1 mm/s、持续 0.5 s（[任务页「成功条件」](../develop/tasks/rope_threading_zh.md)）。

失败机理（lab v18，`7f0b002cc`，交接第 11 节）：

- **够不到**：两档相同的 `raise_to_ring` 让抓绳的右手保持夹爪朝下，直线抬到环心上方 10 cm（世界 z 1.35 m）；
  腕关节升到 2.185 rad（范围 [-1.8675, 2.234]），约 56 min 后报 "IK exhausted 4 seeds"。lab 的 IK 探测：夹爪朝下时，
  右臂够不到环心上方 9 cm 及以上的任何目标；6 cm、3 cm 对多数夹爪切向可达；easier 的各送绳位都可达；左臂一个都
  够不到。本机 v18 同一失败的最后一个候选残差为 1.27072 mm / 0.0181975 rad，超过 `KnotIK.solve` 写死的
  0.5 mm / 0.01 rad（[门槛审查](../rcb/oracle_tolerance_review_zh.md)）。
- **绳子掉落（very_easy）**：从抬升起点的检查点改为关节空间一步移到环心 + [0.025, 0, 0.06] m，再按原 24 步下放：
  越过了抬升，但下放到半圆上时报 "right lost the physical rope grasp"。
- **送绳被挡（easier）**：一步移到入口送绳位环心 + [0.15, 0, 0.025] m，越过抬升和 `align_ring_entrance`；
  `feed_through_ring` 报 "Action would be clipped by the public robot adapter"，即送绳需要公开动作范围之外的关节目标。
- **速度**：两档在 v18 上约 2.6 s/控制步，一次执行 1.5–2 h，超 72 min；rope easy 用原三档配置为 0.73 s/控制步。

已做（本机，未上 GPU）：`99c3d27b0` 让两档在穿环搬运前依次尝试 10 / 6 / 3 cm 中间高度、0 / ±10° yaw、先抬升或
直接关节过渡，最多 18 条候选；每条整段检查关节范围、自碰撞、桌面、双臂及环/支架间隙，公开动作范围也纳入预检。
207 项 CPU 回归通过，没有完整物理运行（[实施记录](../rcb/oracle_tolerance_review_zh.md#两档实施结果)）。

**环境配置已统一（`da47d3a49`，10-06，基于 v19）**：`release_profile.environment_inputs` 接受 rope 两档，整套使用
原三档的 `contact_relaxed_v16`，只有原三档的环布局不带入（两档的环与托架不变）。带入项包括：每控制步 1 × 40 ms、
网格 4,939 顶点、Newton / PCG 3e-3 / 3e-5、只有手指碰绳、绳 E 5e6、静止形状取出生形状、`ipc_soft_band_v1`
（接触 6 mm、强度 1000、拉伸比 2.0），以及终态速度上限 10 mm/s 与 1 mm 圆环孔口余量。lab 实测：每控制步
3.14–3.41 s → 0.146 s；出生静置 5 s 后绳速 4.5 μm/s；`ThreadingPolicy` 原样执行时拾起、抬升通过，仍在
`raise_to_ring` 停止（IK 4 个种子无解，第 589 行，4.7 min，此前约 56 min）。配置统一只降低了每次尝试的成本，
没有修好 oracle。lab 这次跑的源码基于 `89cc32674`，**不含** `99c3d27b0`（18 条候选），所以它复现的是旧的单一路径；
18 条候选至今没有任何物理运行（10-06 21:15 核对：本机、mll-4090-3、上游 `b16d2b3a2` 都没有 rope 运行或新提交）。

下一步：

1. 用 v19 的 rope 两档与 `99c3d27b0` 的通用 IK（`topogym/planning/oracle_ik.py`，含 10 / 6 / 3 cm 中间高度等 18 条候选）
   跑一次，看 1.3 mm 残差的抬升能否找到经过检查的路径（用户已交给另一会话执行，结果到后登记）。
2. 抬升通过后逐一确认后两处：very_easy 下放不丢绳（辅助抓持已换成强度 1000、拉伸比 2.0，需重新观察）、easier 送绳行
   在公开动作范围内。控制步已从 25 ms 变为 40 ms，按步数计的动作段与限速要一并检查。
3. 整次执行时长按 0.146 s/控制步估算，预计远低于 72 min（实测后确认，D5 对 rope 可能不再需要）。
4. privileged → standard 正式评分（v19），登记第 7 节。

**very_easy 新路线（10-06 晚，按用户思路）**：绳尾沿环的法线方向（x 方向）穿过半圆平面时，半圆两个上端点不挡路，
不必举到环心以上。改动在 `ThreadingPolicy.plan_ring_transfer` 的 very_easy 分支：

1. `carry_beside_cradle`：一步关节移动，把捏点（离绳端 6.5 或 8.5 cm）带到环面外侧 10 cm、环心下方 3.5 cm（离桌面约 29.7 cm）；
   绳尾末端仍在环面外 1.5 cm 以上。候选：高度 −3.5 / −4.5 / −2.5 cm × yaw 0 / ±10° × 夹爪倾斜 0 / ±15°，共 27 条，每条整段做
   关节范围、公开动作范围、自碰撞、桌面、环与支架间隙检查。
2. `slide_tail_through_cradle`：水平平移到环面外侧 2.5 cm，绳尾穿过环面约 4–6 cm。
3. `lower_onto_cradle`：12 步下放到环心下方 6.6 cm（绳静止靠在内侧时绳心在 6.5 cm），判定 draped 即停。
4. `press_onto_rim`（新增闭环）：若仍未 draped，读 Task 实测的最小绳-环间隙，每步下压（间隙 − 0.3 mm），
   限 0.5–3 mm，最多 12 步。原因：第一次本机运行下放到 −6.6 cm 后间隙仍为 2.9 mm（> 1 mm 门槛），未判 draped。

本机原生（v19 环境配置，与 Harbor 同一 Session 入口 `below_easy.run_feedback_policy`，出生状态 hash
`a84196f03addb097` 与冻结实例相同）：第 1 次 994 行结束、未 draped（间隙 2.9 mm）；加闭环后第 2 次第 770 行（30.8 s）
Task success，下压两步 2.3 / 0.8 mm，终态支撑点间隙 0.68 mm、最大绳速 4.8 mm/s，整次 317 s。
证据：`runs/test_results/rope_below_easy_v19_20261006/native_very_easy_0{1,2}/`。CPU 测试
`ci_checks/test-below-easy-ik-candidates.py` 20 项通过（候选数改为 27，新增"very_easy 路线全程低于环心、终点在 −6.6 cm"）。

**easier 新接力路线（10-07，按用户思路）**：判据只认离绳端 12 cm 以内的抓持，辅助抓持的材料半径是 18 mm，
所以送绳手最远只能抓在离端头 10 cm 处。手停在环面入口侧，只让绳尾沿环的法线穿过环；接绳手在出口侧接住同一段绳尾。

1. 右手在离端头 10 cm 处竖直向下抓（`plan_pickup` 对 easier 用 10 / 9.5 cm），抬起。
2. `carry_to_ring_entrance`：一步关节移动，把捏点带到环面入口侧 13 cm、环心下方 1 cm。
3. 左手张开，`plan_receive` 按"绳尾沿 −x 伸直"预测接绳点（离端头 1.5–3 cm、距环面至少 4 cm），选侧面抓取姿态：
   相对竖直捏取绕 z 转 180° 并绕绳轴转 ±90°（夹爪竖直）。左手先关节移动到离环再远 4 cm 处（`left_clear_of_ring`），
   再直线到接绳点沿抓取方向后退 5 cm 处等待（`left_stage`）。**必须在送绳之前做**：第 4 次运行在送绳之后才移动左手，
   关节空间路径扫过绳尾，把它推开了 4.4 cm。
4. `feed_tail_through_ring`：右手直线移到环面入口侧 3.5 cm（IK 探测：右手 ≥ 3.5 cm 可达，更近会碰环），绳尾穿过约 6.5 cm。
5. 左手按实测绳尾重选接绳点（仍需在环面出口侧 3.5 cm 以外），只修正位置、沿用规划好的朝向（第 2 次运行重算朝向后
   IK 差 29 mm），直线靠近，捏住。
6. 两手同时抓持 0.05 s 后右手张开，沿 +x 退 6 cm 再抬 4 cm；左手再沿 −x 拉 6 cm。

IK 探测（`runs/test_results/rope_below_easy_v19_20261006/easier_ik_probe_0{1,2_left}/`）：左手夹爪朝下时在出口侧
3–5 cm 几乎都够不到；绕 z 转 180° 并绕绳轴转 ±90° 后，在 4–5 cm 可达。

本机原生 7 次（`native_easier_01`–`07`）：前 6 次依次停在左手没捏到绳（绳尾被推开）、重算朝向够不到、手指离环 0.07 mm、
左手没捏到绳（同一推开）、等待位后退 10 cm 够不到、关节移动擦环（0.2–0.5 mm）；第 7 次第 1120 行（44.8 s）Task success：
交接 right → left、端点 end、穿越 R1−，接绳点实测偏移约 1 cm，对准误差 3 mm，右手后退阶段即判定成功，整次 681 s。

### 4.2 orbits very_easy / easier（O1、O2）——暂缓

**用户 10-06 决定：Orbits 先做加速（见加速页），本节暂缓。** 以下是暂缓时的状态，恢复时从这里接着做。

场景：木底座上的立柱缠着一根 0.8 m 有限元软绳。very_easy 是单个球头柱（无环），easier 是单环双柱。ALOHA 只能靠
夹爪摩擦抓绳（无辅助抓持），要把绳从器具上解下、放进目标区并静止（[任务页](../develop/tasks/orbits_zh.md)、
[加速页「场景与问题」](orbits_speedup_tracker_zh.md)）。

失败经过（lab，`7571e4194` 的 `topogym/planning/orbits/native_session.py`，交接第 6 节）：

- 前两处已修并已合并（`79c21d1f6`）：very_easy 第 99 行，IK 把左前臂滚转关节放在模型限位 -π 上，比公开动作范围
  多一个 float32 步，报 "Action would be clipped"；very_easy 第 238 行与 easier 第 195 行，首次对准时绳躺在桌面或
  底座上，指垫停在支撑面之上，偏置更新把目标压到支撑面以下，报 "No close contact pose above the support surface"。
- 修复后 very_easy：右臂接近时，oracle 自己的双臂间隙检查报 0.47 mm < 1 mm（此时左手停在 y 0.105、z 0.075 m 的
  让位点）。更宽或更高让位点的试跑因太慢被 lab 中止，没有结论。
- 修复后 easier：`fresh_bight_carry` 搬运新绳弯时抓持误差从 14 mm 增到 23 mm，绳被压扁 0.25 s（体积比 -0.075），
  Session 以 `connection_or_volume_invalid` 终止。穿环路线需要重做。
- 速度：lab 每控制步 7.8 s，其中纯物理 3.7–5.2 s，其余是 oracle 的逐行检查。very_easy 路线约 2500–3300 行，一次执行
  5–7 h、每遍回放 3–4 h。

恢复后的下一步：在加速后的物理设置与新冻结初态上复现两个停止点；very_easy 调整左手让位点或两臂接近顺序，
满足 1 mm 双臂间隙；easier 重做 `fresh_bight_carry` 与穿环段；缩减逐行检查开销；原生成功后双模式正式评分。

### 4.3 blanket_flatten easier（B1）

场景：60 × 48 cm 方格布（PBD 粒子，12 mm 网格、8 mm 粒径）。easier 先沿 60 cm 方向对折成约 30 × 48 cm 的双层，
再把自由边的右前角连同两层翻折（折角两边各 22 cm）。目标是展平：覆盖率 ≥ 0.95 且布面静止。两档声明
`pbd_local_patch_v1` 局部辅助抓持，拉伸比上限 1.3（`topogym/tasks/release_profile.py:44-46`；[任务页](../develop/tasks/blanket_flatten_zh.md)）。

现有路线（`topogym/planning/blanket_flatten/below_easy_routes.py` 的 `EASIER`）分三段：左手在材料坐标
UV (-0.17, 0.06) 的双层区抓起，`lift_half` 抬 7 cm、`turn_half` 移到 (-0.21, 0.21, 0.15) m、`lay_half` 放到
(-0.305, 0.21, 0.04) m，打开对折；然后右手按 very_easy 的方式展开右前角；最后右手抓 UV (0.282, 0.222) 拉开远边。

失败（lab，`7571e4194`，第 633 行，交接第 6 节）：`lay_half` 中报 "assisted grasp lost"，拉伸比 1.3014 > 1.3。
拉伸比是布料网格边的当前长度 ÷ 静止长度的最大值（`topogym/world/physics/grasp_soft.py:250`），超过 1.3 时辅助
抓持释放。lab 把 `lay_half` 终点 x 改为 -0.29 / -0.28，仍然释放（1.3020 / 1.3009），所以峰值不在终点，而在下放
过程中。lab 在自己的 GPU 上重新准备的初态（覆盖率 0.4112、最高点 30.5 mm）与本机一致。

本机：`easier_initial_01` 只有场景构形资格，最大局部速度 0.284 m/s，静稳未通过（机器人停在 home 时布位移 2.7 mm，
very_easy 为 0.02 mm），终态静止判定可能碰到与 very_easy 在 lab 上相同的抖动粒子；easier 的正式评分尚未执行。
本机此前两次尝试（[验证汇总](../../runs/test_results/blanket_below_easy_20261005/validation_summary.json)）：

- `easier_oracle_01` 抓四层角：`lift_corner` 中未被抓的下层拉伸比到 1.403 > 1.3，辅助抓持释放。
- `easier_oracle_02` 改抓双层区：接近时 IK 残差 0.93 mm，被通用 IK 的 0.1 mm 精度门槛拒绝（门槛审查第 1 条所说的
  过严门槛；`99c3d27b0` 已为两档改为候选预算加路径检查，blanket 上尚未实测）。
- 现路线（左手 UV (-0.17, 0.06)）本机未在 v18 上跑过，lab 的结果即上面的 `lay_half` 失抓。

**场景诊断（10-06，[证据](../../runs/test_results/blanket_easier_scene_diag_20261006/README.md)）**——lab 称最新阻塞点是场景问题，
本机复核如下：

- 结构：两层一起翻角，角上自下而上是下层主体、上层主体、上层翻角、下层翻角——下层的角翻到最上面，把上层的角夹在中间。
  层序与设计一致、没有穿插，但四层被压到 7.94 mm（粒径 8 mm），7367 对跨层粒子处在接触距离内；very_easy 只有两层，7.995 mm。
- 初态没有静止：冻结后每个 tick 有 564 个粒子位移速度超过 30 mm/s（最大 0.20 m/s），集中在最上层翻角，几乎全是竖直方向的
  "弹起—回落"；准备阶段静止检查未过，只按"场景构形"验收，松手 0.6 s 就冻结。very_easy 同样指标最大 1.5 mm/s、通过静止检查。
- 后果：拉伸保护看全布最大边（任一边超过 1.3 就松开所有辅助抓持，也不能新建抓持）。用 lab 评分的同一份代码在本机初态上跑：
  打开对折峰值 1.2751（通过），松手后上层翻角折线处无人拉也保持 1.24–1.27（被下层翻角压住），第二段翻角时 1.30004 失败；
  lab 在它自己 GPU 上重新准备的初态上，第一段就到 1.3014 失败。两处都只差千分之几，失败位置随初态而变。
- 对照：`topogym/tasks/release_profile.py:44-46` 给 very_easy / easier / easy 的拉伸保护是 1.3，medium / hard 是 1.5。

v19 的影响（`42c6ee4cd`）：布料粒子速度改为每个 2.5 ms tick 的位移 ÷ tick 时长，门槛不变（live 0.03 m/s、回放
0.08 m/s）。每个 tick 的布料位置与改前逐位相同，所以 `lay_half` 的拉伸问题不变；但 oracle 的"等布安静"与最终
落稳改用新读数，等待结束的时刻可能变，之后的轨迹会随之不同，所以诊断与评分都在 v19 镜像上做。
`cloth_preparation.py` 仍用旧读法，easier 初态"静稳未通过"（0.284 m/s）可能也是旧读法下的抖动粒子读数，
可用新读法复测出生后的静置速度。

下一步（10-07 更新；场景已按 D7 改为只翻上层的角、对折不居中，新初态已安装）：

1. 逆折叠路线的原生运行（mll-4090-1，`oracle_05_inplace`，进行中）：右手把上层翻角翻回 → 左手把上层绕折痕翻回原位 →
   最多三次残留折角整理；看终态覆盖率 ≥ 0.95 与布面静止，记录各段最大拉伸比（门槛 1.5）。
2. 未展平时按残留形状调整抓点或放下位置，一次只改一项并复测。
3. 原生成功后构建 v19 的 blanket 候选，privileged → standard 正式评分。

### 4.4 knot_untying easier（K1，条件接手）

场景：桌上一个宽绳圈，圈口两处交叠、上下关系交替（麻花状），两条自由端；目标是投影交叉数降到 0、绳落桌且静止
（[任务页](../develop/tasks/knot_untying_zh.md)）。

现有两份结果对应不同代码，不能互相替代：

- **本机，已通过**：v18 镜像 `topogym-below-easy:v18-20261005-01`，冻结私有快照 `source03`，两个模式都是 grade=1、
  solved=1（[评分汇总](../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/grading_summary.json)，10-06 12:47）。
  - privileged：1066 行、26.645 s 仿真；两遍新进程回放都在第 1066 行达到严格目标，末态哈希同为 `d80d36edb8f23cd8`；
    没有额外保持步、未用容差，review 与 forcing 为 0。
  - standard：live 成功、独立回放成功、live 与回放一致；断点续传 0 次，没有额外保持步、未用容差。
- **lab，进行中**：评分对象是 `7571e4194` 提供的 knot oracle，即交接所说的"新执行器"；lab 评分目录
  `obe/tree_g/runs/test_results/harbor_grade_obe_knot_untying_very_easy_easier`。它与 `source03` 的文件差别在
  `robot_oracle.py`、`harbor_bridge/actions.py`、`harbor_bridge/callbacks.py`、`planning/solvability.py`。
  `robot_oracle.py` 新增的逐行限速、拉绳保护、释放前悬停门在两档运行中被 `BelowEasyRunner` 关闭
  （`topogym/planning/knot_untying/below_easy_runner.py:30-43`），两档实际生效的控制逻辑差别只有 `4a92ecc1c` 的
  偏置饱和即停：第一次两端抓取时，`converge()` 学到的 TCP 偏置到 40 mm 上限就停止，不在绳旁闭爪。

跨机器稳健性（10-06 评估，未做实验）：

- 同一套两档控制逻辑，lab 在 `7f0b002cc` 上、用 lab GPU 重新构建的实例失败于第一次两端抓取：左臂腰关节落后
  命令 0.10–0.16 rad，左 TCP 一直差 17 mm，偏置涨到 40 mm 上限；本机实例通过。very_easy 两边都通过，且都是 848 行。
  所以 easier 对机器或初态的差别敏感；失败是手臂物理上没跟上（原因未查明），不是阈值过严。
- 本机通过那一局的各项实测与门槛（`end_grasp_attempts.json`、`report.json`）：

  | 检查 | 门槛 | 实测 | 失败后 |
  | - | - | - | - |
  | 第一次两端抓取 `converge()` | 4 s 内 TCP 误差 ≤ 2 mm；偏置 ≤ 40 mm | 1.62 mm；偏置 ≤ 4 mm | 超时仍闭爪；偏置饱和即停（无重试） |
  | 第二次抓取的空中接近 | 4 s 内 ≤ 20 mm / 0.1 rad | 5.7 / 10.1 mm，0.012 / 0.030 rad | 放开后换抓点重试，共 3 次 |
  | 第二次抓取闭爪前对准 | ≤ 2 mm / 0.1 rad | 1.68 / 1.52 mm，0.005 / 0.008 rad | 同上 |
  | 第二次抓取抬升跟随 | 夹点抬 ≥ 4 mm，绳点与夹点距离 ≤ 8 mm | 8.9 mm，1.15 mm | 同上 |
  | 单步关节变化 | standard 上限 0.04 rad | 0.0379 rad | 按构造限在上限的 95 % |
  | 终态静止 | 整绳 ≤ 1 mm/s 持续 0.5 s | 窗口最差 0.903 mm/s | live 只会多等，不会判失败 |

- 唯一偏薄的是第二次抓取闭爪前的 2 mm 对准（余量 0.3–0.5 mm），但它防止闭在 8 mm 绳旁，且有 3 次换点重试；
  历史上的失败都远在门槛外（v16 第二轮 5.9–14.1 mm，lab 17 mm），放宽门槛救不回这些情况。
- 同一台机器上，v18 的确定性 IPC 让两遍回放逐位一致，回放噪声不是风险；但在 A 机录下的动作行拿到 B 机开环回放，
  没有成功保证。
- 建议：不放宽门槛；给第一次两端抓取加与第二次相同的放开、重测、换点重试；查清 lab 腰关节失跟的原因；
  用数据代替判断——在冻结实例上以不同的空等步数起跑若干次（模拟不同的数值历史），并争取在 lab GPU 上跑一次，
  记录上表各项的余量与通过率。

跨机器与扰动实验（10-06，已按用户要求停止；证据 `runs/test_results/knot_easier_xmachine_20261006/`）：

- 机器：本机 mll-4090-2 与 mll-4090-3，均为 RTX 4090（驱动 570 / 580）；mll-4090-3 有他人作业（GPU 占 8.9 GB、
  利用率 80–86 %，CPU 负载约 28/32），一次只跑一局。两边同一 v18 镜像（ID `b747db38…`）、同一任务包（`source03`）。
- 运行：R1 在 mll-4090-3 原样执行 oracle 入口，与本机已通过的运行逐个动作对比；L1 在本机用实验脚本、不加扰动，
  应与原运行逐位一致（证明脚本本身不改变结果）；L2 / L3（本机）与 R2 / R3（mll-4090-3）在起跑前空等 3 / 40 /
  1 / 12 个控制步，模拟初态的细小差别。所有扰动运行逐步记录要求的关节目标、Session 接受的目标与实测关节角。
- 用 `source03` 而非当前代码的原因：两档控制逻辑与当前代码只差偏置饱和即停（仅在手臂已失跟时触发）和 IK 备用候选
  （仅在精确解失败时启用），用来检验路径是否僵化是等价的。
- 结果（10-06 20:35）：
  - L1（本机，实验脚本、不加扰动）：1066 行动作与原通过运行逐位一致，26.645 s 成功，各检查数值相同——实验脚本不改变结果，
    本机新进程完全复现。
  - R1（mll-4090-3，原样入口）：跑到 25.4 s（第 1017 行）时 libuipc 显存分配失败退出（对方机器 GPU 与他人作业共用，
    属资源问题）；已执行的 1017 行动作与本机逐位一致，128 条进度记录（绳高、绳与夹爪接触点偏移、阶段、交叉数）
    完全相同。闭环 oracle 的动作取决于实测绳状态，逐位一致说明两台机器算出的物理完全相同。
  - 结论：同型号 GPU（sm89）、同镜像时，换机器不产生数值差异；lab 的失败来自它的 GPU 架构不同和/或它重建的初态。
    检验路径是否僵化要靠人为扰动（L2/L3/R2/R3）。
  - L2（本机，空等 3 步）跑到 20.8 s、R2（mll-4090-3，空等 1 步）跑到 8.0 s 时按用户要求停止：两局都通过了 lab 卡住的
    第一次两端抓取（收敛前 TCP 误差约 3–5 mm，与不扰动时同量级）；L2 还通过了第二次抓取，闭爪前对准 1.706 / 1.544 mm
    （不扰动时 1.678 / 1.518 mm，门槛 2 mm），抬升跟随 8.93 mm。小扰动下各检查余量基本不变，没有复现失跟。
  - 10-06 20:55 用户决定停止本组实验（lab 报告 knot 两档 oracle 均已跑通）：L3、R3 取消；lab 失跟的根因未查明，
    若以后在其他 GPU 型号上再现，用本组脚本（`xrun.py` 逐步关节记录）复查。mll-4090-3 上保留 v18 镜像与
    `~/topogym_xmachine/`，可复用或删除。
  - 正常跟踪基线（L1 逐步关节记录）：每次 `converge` 结束时各关节与接受目标相差约 0.01 rad（段内最大约 0.02 rad），
    腰关节从不是最大者；lab 的 0.10–0.16 rad 腰关节落后约为正常值的 10 倍，属于异常卡滞，不是普通跟踪滞后。

下一步：

1. lab 结果到达且双模式为 1：第 7 节登记，K1 收口。
2. 任一失败：先在同一冻结实例上对比 `source03` 与新代码。已知线索（交接第 11 节，同档在 `7f0b002cc` 上失败）：
   从 `grasp_ends:descend` 起，左臂腰关节落后命令 0.10–0.16 rad、腕滚转落后 0.14–0.16 rad，其余关节在 0.03 rad 内；
   交接列出的待查原因包括限速器或 Session 守卫改写了腰关节目标。按上述四个文件逐项替换回 `source03` 定位。
3. 本机 ik01 作业也会评 knot 两档（新共享 IK 下），结果一并登记。

## 5. 待决定事项

### D1 rope 与 blanket 两档的辅助抓持范围——已决定

- **决定（2026-10-06，用户）：rope 与 blanket 两档都可以使用辅助抓持。**
- 背景：本机 ik01 评分作业曾因此搁置 rope、blanket（`runs/test_results/harbor_below_easy_v18_20261006_ik01.supervision/state.json`）。
  rope 两档入口要求实例声明以绳为目标的 `ipc_soft_band_v1`（`topogym/planning/harbor_bridge/below_easy.py`）；
  blanket 两档声明 `pbd_local_patch_v1`（`topogym/tasks/release_profile.py:44-46`）。
- rope 的参数随 D2 定为原三档值（`ipc_soft_band_v1`，接触 6 mm、强度 1000、拉伸比 2.0），即保留辅助抓持。
- 本机 ik01 作业里因此搁置的 rope、blanket 共 8 项不应再在 ik01 中跑：rope 的实例是旧配置，blanket 要换 v19。

### D2 rope 两档改用原三档配置时带入哪些项——已决定

- **决定（2026-10-06，用户；`da47d3a49` 实现）：整套带入原三档的 `contact_relaxed_v16`，只排除原三档的环布局。**
  实现位置：`topogym/tasks/release_profile.py` 的 `environment_inputs`，`scripts/topogym_merge_candidate.py` 的两档分支。

| 项 | 两档原值 | 现值（同原三档） | 性质 |
| - | - | - | - |
| 每控制步物理推进 | 2.5 ms × 10（控制步 25 ms） | 40 ms × 1（控制步 40 ms） | 时间步 |
| IPC Newton / PCG 容差 | 1e-3 / 1e-5 | 3e-3 / 3e-5，`linear_bvh` | 求解器 |
| 绳网格 | 默认，33,070 顶点 | 5.5 mm 间距、12 边，4,939 顶点 | 绳模型 |
| 绳杨氏模量 E | 5e4 Pa（`topogym/assets/materials.py:39`） | 5e6 Pa（硬 100 倍） | 绳模型 |
| 绳的静止形状 | 直绳 | 出生时的形状 | 绳模型 |
| 与绳碰撞的机器人连杆 | 全部连杆 | 只有手指 | 接触 |
| 辅助抓持：接触距离 / 强度 / 拉伸比 | 1 mm / 100 / 1.3 | 6 mm / 1000 / 2.0 | 辅助抓持 |
| 辅助抓持：抓点半径（空间 / 材料） | 12 / 14 mm | 14 / 18 mm | 辅助抓持 |
| 辅助抓持：最大平移误差 / 穿透 | 10 / 2 mm | 25 / 6 mm | 辅助抓持 |
| 终态速度上限 | 1 mm/s | 10 mm/s | 成功判据 |
| 孔口接触余量 / 孔口检查形状 | 0 / 圆柱 | 1 mm / 圆环 | easier 穿环判据 |
| R2、R3 环的偏转、偏移、安装侧 | 两档没有这两个环 | 不带入 | 几何 |

- 含义：两档的成功判据中，静止速度上限放宽 10 倍、easier 穿环判据允许 1 mm 绳-环接触，与原三档一致。
- 代价：两档初态已在新物理下重新沉降、镜像重建，物理身份改变，此前两档的评分不能沿用（两档此前也没有通过的评分）。

### D3 orbits 物理设置

由[加速页](orbits_speedup_tracker_zh.md)负责。**用户 10-06 决定先做加速，O1、O2 暂缓**；加速后的物理设置与新冻结
初态落定后，再按第 4.2 节恢复。

### D4 proof 与 session 选择（第三部分）

由 helper 页 F2 负责。按源码检索，本页四个家族的两档入口——`blanket_flatten/public_session.py`、
`knot_untying/public_session.py` 与 `below_easy_runner.py`、`orbits/native_session.py`、`below_easy.py` 中 rope 的
`SessionPolicyRunner` 分支——都不经过 `run_stages` / `QualificationWorkflow`。两档中经过它的只有 fiber_bundling
（`below_easy.py:67`），而 `harbor_bridge/callbacks.py:36` 已固定为 `mode="session"`。因此 F2 的结论预计不改变本页
任务的执行路径；F2 决定后复核一次再登记。

- 执行语义：_（待 F2 决定后填）_

### D5 72 min 豁免

rope 两档在新配置下 0.146 s/控制步（lab，`da47d3a49`），整次执行预计远低于 72 min，实测确认后可能不再需要豁免；orbits very_easy 现约 5–7 h，随加速页重测。仍超出的由用户决定是否豁免。

### D6 正式评分的基线版本

- **v19 已发布为当前候选（`89cc32674`，10-06）**：`merged-v19`，tooling 19，镜像 0.2.17-dev；v18 的 tooling 哈希写入
  `ci_checks/topogym_tooling_versions.json` 冻结。起因是 `42c6ee4cd` 改了公开源码（`topogym/world/genesis_world.py`）
  和布料静止判据，v18 与 v19 的结果不能放在同一标签下。profile 名会进 blanket 实例的 state hash，所以 v19 的 blanket
  实例 hash 全变（物理状态相同）。v19 要重建镜像才生效，本机尚未构建。
- 对本页任务：blanket 两档、rope 两档的正式评分都在 v19 上做（rope 两档的新配置也基于 v19）。knot 的 IPC/FEM 速度
  读法未改，物理不变，但标签不同。
- 待定：v18 上已有的评分（knot easier 本机双模式 1、其他家族）是在 v19 下重评，还是像 v17→v18 那样逐位核对回放后沿用。
  helper 页的 H 项（helper 目标版本）是同一问题。
- 决定（部分，2026-10-07，用户）：lab 推送过来的改动及其附带的验证视为已完整测试，不在本机重评。据此 blanket very_easy按 lab 用 `42c6ee4cd` 回放已评分轨迹、第 637 行严格通过的结果记为 v19 通过。本机自己在 v18 上得到的结果（如 knot easier 本机双模式 1）是否在 v19 重评仍待定。

### D7 blanket easier 的场景怎么改

诊断见 4.3 节。可选方向（可组合）：

| 方向 | 做法 | 代价 / 风险 |
| - | - | - |
| A. 只翻上层的角 | `blanket_corner_folds.py` 的 easier 只翻 T 的角，角上三层、不再有"夹住"的结构 | 新场景、新初态、镜像重建；难度顺序 very_easy < easier < easy 要重新核对 |
| B. 初态必须静止 | 准备阶段改用 `released_stable` 验收（不再用"场景构形"），必要时加大层间距或延长静置 | 四层叠放在 PBD 中可能始终不静止；成功后初态跨机器才可复现 |
| C. 拉伸保护与 medium / hard 一致 | easier 的 `max_strain_ratio` 1.3 → 1.5 | 改的是环境规则（实例身份变）；只给余量，不解决不静止 |
| D. oracle 先翻角再打开对折 | 路线改顺序，避免把上层从下层翻角下拖出 | 不改场景；但第二段翻角本身也到了 1.30004，余量仍薄 |

建议 A，必要时加 B：它去掉了"夹住"的结构，两段动作都不再需要把一层布从另一层下面拖出来。
- **决定（2026-10-06，用户）：A，easier 改为只翻上层的角。** 实施：
  - `topogym/assets/geometry/blanket_corner_folds.py`：`CornerFoldProfile.upper_corner_only`，easier 为 True，对折后只翻上层自由角，
    下层平放，任一点上方最多三层；very_easy 的折叠目标与参数逐位不变（已核对）。
  - `topogym/tasks/blanket_flatten/corner_folds.py`：只有 easier 的参数带 `upper_corner_only`，因此旧两层初态的身份对不上、被拒绝。
  - oracle 路线（`below_easy_routes.py` 的 `EASIER`）：先翻回上层的角（目标点按 easier 几何计算），再打开对折，再把下层远、近
    两角拉回原位；旧路线第二段照搬 very_easy 的翻角目标点，会往外多拉约 9 cm，这也是本机那次 1.30004 的直接原因之一。
  - 新初态在 v18 准备镜像中按"松手后必须静止"验收准备，证据目录 `/data/jianwen/topogym/blanket_easier_upper_corner_20261006/`。
  - 结果（10-06 22:40）：按"松手后必须静止"验收未通过（8 s 内静止检查不合格，其余检查都过）。原因不是布没放平：上层翻角
    平躺在下面一层上，层间 6.8 mm，与 very_easy 静止的翻角（6.78 mm）相同；跳动恰好出现在三层平叠、完全接触的区域
    （翻角中部 3–10 cm 处约 80 % 的粒子在跳，靠折线、被稍微撑起的 3 cm 只有 11 %），最下层与所有两层区为 0，松手后 3 s
    内不衰减。即按现在的布料设置（粒径 8 mm、每 2.5 ms 4 个子步），三层平叠本身不能静止，多加展平步骤无效。
    另按"场景构形"验收准备了一份（`easier_initial_02`），用于测试新路线。
  - 与家族标准对齐（10-06 22:45）：blanket 已安装的冻结初态都按"场景构形"验收——easy / medium / hard 静止检查都没过
    （冻结时最大速度 178 / 155 / 594 mm/s，松手后 0.6 s 冻结），very_easy 恰好静止。新 easier 同样按"场景构形"验收：
    覆盖率 0.503、最高 25.4 mm、最大拉伸 1.025、无层间穿插，冻结时逐 tick 最大 175 mm/s（全在上层翻角）。
    已撤掉两份旧 easier 初态（资源文件与 `catalog.json` 条目，两套运行环境各一份），安装新初态于
    `corner_folds_archive_v1/cuda_sm89_mp128_87407517a32a/easier/seed_0`；`test-blanket-below-easy` 7/7、
    `test-harbor-below-easy` 6/6 通过。
  - 新路线原生测试（10-06 23:05，`/data/jianwen/topogym/blanket_easier_upper_corner_20261006/oracle_01`）：第一段抬上层翻角约 6 mm
    时拉伸比 1.3012，抓持释放。超线的边在中间层（上层布本体，材料坐标 (−111, −36) mm），位置就在抓点正下方约 1.3 cm：翻角与
    中间层贴合（层间 6.8 mm、粒径 8 mm），手指插不进两层之间，把未绑定的中间层一起带起。旧路线抓四层角时"未抓持的下层拉到
    1.40"是同一现象；very_easy 翻角下只有一层且贴桌，抬起峰值 1.244。
  - 门槛对齐诊断（10-07 02:38，只在实验副本里把 easier 门槛改为 1.5，`oracle_02_guard15`）：四段全程没有因拉伸松手。各段峰值：
    抬翻角 1.289、放翻角 1.3145、放半边 1.3292，其余 ≤ 1.27，全程最高 1.329——按 1.3 会有两段失败，按 1.5 余量 ≥ 0.17。
    同一初态、同一路线的两次运行在同一 tick 建立抓持、同一条边受力，但数值差 2–3 %（1.3012 对 1.289），即 1.3 附近的通过与否
    取决于运行间的细小差异。路线本身未展平：最终覆盖率 0.628（要求 ≥ 0.95），上层的角仍折着、对折没有真正打开——第二段把
    抓点只放到折痕外 2 cm（沿用旧路线"之后再把下层拉回原位"的设计），实际上层没有翻开；收尾的 `fold_layout` 识别出上层折角
    （513 个粒子）但没有执行。本次运行耗时约 3.5 h（共用 GPU 利用率 99 %）。

## 6. 检验流程

每个任务按顺序：

1. 本地原生：冻结实例上 oracle 原生 Task success（入口见各家族 README）。
2. 构建候选：`scripts/topogym_merge_candidate.py --families <家族> --tiers very_easy easier`，再用
   `scripts/topogym_candidate_pipeline.py` 执行 `--phase build` 与 `--phase preflight`（含初态 exact 恢复）。
3. 正式评分：`scripts/oracle_runners/test_harbor_oracles.py --candidate --families <家族> --tiers very_easy easier
   --modes privileged standard --execute`；完整命令见[门槛审查文档的 GPU 代码块](../rcb/oracle_tolerance_review_zh.md#两档实施结果)。
4. 登记第 7 节；失败的保留 `bridge_report.json`、日志和录像。

资源：本机一块 RTX 4090（24 GB），与 ik01 等作业共用；IPC 任务一次只跑一个 Env（knot 约 9 GB）；blanket 启动前须
连续三次确认 ≥ 8 GiB 空闲显存；系统内存到 90% 时守护进程会暂停作业。

## 7. 正式评分记录

| 日期 | 地点 | 任务 / 档 | 模式 | 代码 | 镜像 / 物理 | grade | 停在哪里 | 证据 |
| - | - | - | - | - | - | - | - | - |
| 10-06 | lab | rope very_easy、easier | privileged | `7f0b002cc` | `labv18be`（v18）；Task 默认物理 | 0 / 0 | `raise_to_ring` IK 无解（约 56 min） | lab `align_be/sweep/` |
| 10-06 | 本机 | rope very_easy | privileged | v18 两档候选 | `merged-v18` | 0 | `raise_to_ring`，残差 1.27072 mm / 0.0181975 rad | [bridge_report.json](../../runs/test_results/harbor_below_easy_v18_20261005_01/trials/rope_threading/very_easy/attempt-20261006T124633-257137/jobs/001-oracle/topogym-rope-threading-very-easy__hEu49eY/artifacts/app/output/bridge_report.json) |
| 10-06 | 本机 | rope very_easy | privileged / standard | 工作区（`d86ea023a` + very_easy 新路线，未提交；快照在 `runs/test_results/rope_below_easy_v19_20261006/harbor_very_easy_01/candidate/source_snapshot/`） | `topogym-below-easy:v19-20261006-rope01`；v19 `contact_relaxed_v16` | 1 / 1 | — （770 行，30.8 s；oracle 执行约 8 min 含建场景 218 s） | [summary.tsv](../../runs/test_results/rope_below_easy_v19_20261006/harbor_very_easy_01/summary.tsv) |
| 10-07 | 本机 | rope very_easy、easier | privileged / standard | 工作区（`d86ea023a` + 两档新路线，未提交；快照在 `runs/test_results/rope_below_easy_v19_20261006/harbor_both_02/candidate/source_snapshot/`） | `topogym-below-easy:v19-20261007-rope02`；v19 `contact_relaxed_v16` | very_easy 1 / 1，easier 1 / 1 | — （easier 1119 行、44.8 s；oracle 执行 7.9 min 含建场景 146 s） | [summary.tsv](../../runs/test_results/rope_below_easy_v19_20261006/harbor_both_02/summary.tsv) |
| 10-06 | lab | orbits very_easy | privileged ×2 | `7571e4194` | `obejw/rcb-topogym:0.2.16-dev-cu128`；2.5 ms × 10，eps 1 mm/s | 0 / 0 | 第 99 行、第 238 行 | lab `obe/tree_g/runs/test_results/harbor_grade_obe_*` |
| 10-06 | lab | orbits easier | privileged | `7571e4194` | 同上 | 0 | 第 195 行 | 同上 |
| 10-06 | 本机 | orbits very_easy、easier | privileged | v18 两档候选 | `topogym-local/orbits-v18:below-easy-20261006-01` | 0 / 0 | 第 99 行（4.475 s）/ 第 195 行（6.875 s） | `runs/test_results/orbits_v18_20261006_01/harbor_goal01/` |
| 10-06 | lab | blanket easier | privileged | `7571e4194` | `obejw/...`；lab 重新准备的初态 | 0 | 第 633 行 `lay_half`，拉伸比 1.3014 | lab `obe/tree_g/runs/test_results/harbor_grade_obe_*` |
| 10-06 | lab | knot easier | privileged | `7f0b002cc` | `labv18be` | 0 | `grasp_ends:converge`：左 TCP 差 17 mm，偏置到 40 mm 上限 | lab `align_be/sweep/` |
| 10-06 | 本机 | knot easier | privileged / standard | 冻结快照 `source03` | `topogym-below-easy:v18-20261005-01`；v18 K2 | 1 / 1 | — | [grading_summary.json](../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/grading_summary.json) |
| 10-06 | lab | knot easier | privileged / standard | `7571e4194`（待确认） | 待补 | 通过（用户转述 lab 消息） | — | lab `harbor_grade_obe_knot_untying_very_easy_easier`（待确认） |
| 10-07 | 本机 | blanket easier | privileged | 工作区（`d86ea023a` + 远侧对折场景、三段路线、接触同步，未提交；快照在 `runs/test_results/blanket_easier_harbor_v19_20261007_02/candidate/source_snapshot`） | `topogym-below-easy:v19-20261007-blanket02`；merged-v19 | **1** | — | [grade_both](../../runs/test_results/blanket_easier_harbor_v19_20261007_02/grade_both/)：success 1、strict_goal_row 2336、replay_tolerance_needed 0、replays 2、physics_steps 23356 |

## 8. 相关但不在本页范围

- blanket very_easy：本机 v18 privileged 已 1（严格门槛），standard 因共享显存低于本任务 2 GiB 保护线中断，待重试；
  lab privileged 只在回放容差内为 1、standard 0。lab 的初态是在它自己的 GPU 上重新准备的，折角旁皱褶处一个粒子被
  自碰撞投影在两点间来回推，速度读数恒为 33 mm/s；本机初态没有这个问题，属于换机器导致的失败。已由 `42c6ee4cd`
  （v19）修正：速度改读每个 tick 的位移，lab 用新代码回放 5 条已评分的 blanket 轨迹，very_easy 在第 637 行严格通过，
  easy、medium 成功行不变，hard 晚一个 tick。按用户 10-07 的原则（lab 推送的改动及验证视为已完整测试，见 D6），very_easy 记为
  v19 通过，本机不再重评；v18 上待重试的 standard 也不再做。
- slotted_post_ring：very_easy 在 lab 双模式 1（已随 `2f3233023` 合并）。easier 的"第 2 颗珠固定在绳圈上"方案在 lab
  跑 3 次都失败（珠 2 之后那段绳弯一直压在环上），未提交；新提案 P2（缩短绳圈）未构建。用户 10-06 决定 slotted 只交付
  very_easy，easier 交给 William 和 Jianwen（`5da3e98b4`）。是否纳入本页跟踪待用户说明。
  10-07：easier 有了开发 oracle（`below_easy_oracle.EasierPolicy`，原场景不改）：右手捏住环（选直上越柱顶可达的捏法）抬
  6 mm；左手绕立柱 −x 侧捏起珠 2，越过环的后段放进立柱背面与环之间的空隙后松手、退开；环向 +y 移 5 mm 后直上越柱顶，
  搭在环上的其余绳在提环时向内滑落，再按 very_easy 放入目标区。经 `public_session` 从出生态连续一次原生成功：874 行，
  仿真 21.8 s，限速器 2 行分摊、0 行截断；mll-4090-3 共享 GPU 上墙钟 62 min。证据
  `runs/test_results/slotted_easier_oracle_dev_20261007_01/`（开发 Session，非 Harbor 冻结实例）。
  10-07 Harbor 正式评分（mll-4090-1；源码 = HEAD `d86ea023a`（v19）+ 本次 slotted 改动的干净 worktree
  `/home/jianwen/topogym_slotted_easier`；候选镜像 `topogym-below-easy:v19-20261007-slotted-easier01`，实例 state_sha
  `70d1536b9b8d3003`）：privileged 1（回放 2 次一致、第 874 行严格达成、review 0、forcing 0，验证 2 h 42 min）、standard 1
  （live 与回放一致）。证据 `runs/test_results/slotted_easier_harbor_v19_20261007_01/`。代码尚未提交。
  10-07 晚：按队友的刚体链指导，very_easy / easier 的绳改为 16.5 mm 胶囊链（只换绳，槽宽与位置不变，绳长沿用原走向，
  `contact_weld_v1` 焊链节和环、不焊珠子；CPU float64）。oracle 随之调整：捏环角度扩到整圈并预检直上越柱顶可达、
  捏珠 2 深度 11 mm 夹紧目标 0.020、easier 放下环后松手。本机 Harbor 评分（候选镜像
  `topogym-below-easy:v19-20261007-slotted-chain01`）：very_easy privileged 1 / standard 1（431 行），easier privileged 1 /
  standard 1（872 行），均回放一致、review 0、forcing 0。证据 `runs/test_results/slotted_chain_harbor_v19_20261007_01/`。
- orbits、slotted 原三档：没有 oracle，属任务级决定。
- 其余 8 个家族的两档：在 ik01 作业中按新共享 IK 重评。

## 9. 变更记录

- 2026-10-06 18:00：建立本页。核对交接第 11 节、`rcb/dev/jianwen` 上的第 6 节、本机 knot v18 评分、ik01 作业状态与
  `99c3d27b0` 的两档改动。
- 2026-10-06 19:15：用户决定 D1（两档都可用辅助抓持）、orbits 暂缓先做加速；rope 环境配置由他人修正，补等待期间的
  可做与需等项；D2 改为逐项对照表；D6 记录 v19 在本机不存在的检索结果；K1 补两个模式的 solved=1 明细；
  合并 `2f3233023` 已完成。
- 2026-10-06 晚：更正 4.4——此前写的 `robot_oracle.py` 四项新增中，三项在两档运行中被 `BelowEasyRunner` 关闭，
  实际生效的只有偏置饱和即停；补 knot easier 跨机器稳健性评估（各检查门槛、实测余量、失败后的处理）。
- 2026-10-06 19:45：用户要求在 mll-2（即本机 mll-4090-2）与 mll-3（mll-4090-3）上做对比实验；knot easier 六局排队开跑
  （4.4 节）；blanket 补本机两次 easier 尝试的失败细节，very_easy 的 lab 失败记为换机器导致。
- 2026-10-06 20:50：合并上游 4 个提交（`42c6ee4cd` 布料静止速度改读每 tick 位移、`89cc32674` 发布 v19、`da47d3a49` rope
  两档整套用原三档环境、`5da3e98b4` slotted easier 结论）。D2 记为已决定（整套带入，含终态 10 mm/s 与 1 mm 孔口余量）；
  D6 改为 v19 已发布、待定 v18 评分是否沿用；rope 行更新为新配置下仍停在 `raise_to_ring`；blanket 两档改在 v19 上评；
  knot 跨机器实验不受影响（只改布料粒子读数），继续在 v18 上做。
- 2026-10-06 20:55：用户转述 lab 消息——knot 两档 oracle 均已跑通，K1 记为通过（lab 评分版本与证据路径待补）；
  按用户要求停止 knot 跨机器 / 扰动实验（L2、R2 中途停止，L3、R3 取消），已得结果写入 4.4 节。
- 2026-10-06 21:15：核对 rope 两档。lab 在 v19 上的 4.7 min 运行不含 `99c3d27b0`，18 条候选尚无物理运行；
  本机、mll-4090-3 与上游（`b16d2b3a2`）都没有 rope 在跑或新提交，4.1 节第 1 步实际未开始。本机没有 v19 镜像。
- 2026-10-06 21:40：blanket easier 场景诊断（lab 称阻塞点为场景问题）：四层压紧、初态未静止、两段都卡在 1.3 拉伸线，
  新增 D7（场景怎么改），B1 改记为场景问题；证据 `runs/test_results/blanket_easier_scene_diag_20261006/`。
- 2026-10-06 22:10：D7 定为 A（只翻上层的角）；场景几何、参数身份、oracle 路线已改，任务页已记；新初态准备中。
- 2026-10-06 22:25：rope very_easy 按用户思路改为环心下方平移穿过 + 闭环下压；本机原生第 770 行 success；
  v19 候选 `topogym-below-easy:v19-20261006-rope01` 正式评分 privileged / standard 均 grade 1、solve 1（22:58）；R1 收口，代码待提交。
- 2026-10-06 22:40：新 easier 按"松手后必须静止"准备失败；诊断为三层平叠本身跳动（不是没放平），记入 D7；另按"场景构形"准备测试用初态。
- 2026-10-06 22:50：用户同意与家族标准（"场景构形"验收）对齐；新 easier 初态已安装，CI 两项通过，新路线原生测试开跑。
- 2026-10-06 23:05：新路线第一段抬翻角时把下面贴着的中间层一起带起，拉伸 1.3012 失败；记入 D7，待定下一步。
- 2026-10-07 01:30：rope easier 按用户的接力思路重写，本机原生第 7 次 success；very_easy 与 easier 一起在 `topogym-below-easy:v19-20261007-rope02` 上
  正式评分（`runs/test_results/rope_below_easy_v19_20261006/harbor_both_02/`）。very_easy 跨机器（mll-4090-3）复跑在排队等显存，第 1 次启动时显存不足退出。
- 2026-10-07 02:45：门槛 1.5 诊断——拉伸问题消失（全程最高 1.329），但路线未展平（覆盖率 0.628），第二段打开对折的设计需重做。
- 2026-10-07 03:45：rope 两档在 `v19-20261007-rope02` 上正式评分全部 grade 1、solve 1（very_easy 重评、easier 首次），R2 收口，代码待提交。
  very_easy 两次评分的 770 行动作逐位相同、终态 hash 同为 `cee772c30aff335e`。mll-4090-3 跨机器复跑仍在等显存（该机另有他人 Isaac Lab
  作业约 7 GB、devserver 约 11.9 GB，空闲约 4.8 GB；R1、R2 启动即显存不足退出，R3 改为连续 10 次采样 ≥ 10 GiB 才启动）。
- 2026-10-07 08:30：用户同意：easier 拉伸门槛正式对齐 1.5（`topogym/tasks/release_profile.py` 与 `EASIER` 路线声明，`test-harbor-below-easy`、
  `test-blanket-oracle`、`test-blanket-below-easy`、`test-v15-release-selection` 通过）；路线可改、可多次微调，机器自选。
  `robot_oracle.py` 的残留折角整理改为可由路线声明 `fold_layout.max_stages`（默认 1，行为与阶段名不变）。路线新顺序：翻回上层的角
  → 夹折痕把整叠布右移 15 cm（左臂底座在 (−0.469, −0.019)〔12:05 更正：这是机器人自身坐标系的数，机器人整体在世界坐标中沿 x 偏移 −0.136，左臂底座实际在 x ≈ −0.605〕，整片翻到左侧会压到底座）→ 把上层绕新折痕翻回原位；方案 V1（折痕
  中点拖一次）在本机、V1b（折痕前后各拖一次）在 mll-4090-3 并行试验，脚本 `runs/test_results/blanket_easier_scene_diag_20261006/diag_variant.py`。
- 2026-10-07 10:00：V1 结果——第一段（翻回上层的角）、第二段（夹折痕拖布）都执行完，但拖折痕没有平移整叠布：折痕右移 10 cm，
  两层自由边只动约 2 cm，布在折痕一侧挤起（覆盖面积约 0.53 → 0.45，最高 33 mm）；布只能拉不能推，另一侧被桌面摩擦留住。第三段
  抓点设在上层自由边附近，拖布后离左臂底座水平约 0.65 m，规划阶段找不到朝下可达的路径。V1b（同为拖折痕）已停。另核对：左臂底座
  碰撞网格的包围盒覆盖 x ∈ [−0.666, −0.367]，但 very_easy 平铺布在原位置（左缘 −0.436）全部贴桌，说明原平铺位置可用，再往左未验证。
  新方案 V2（本机）：初态下上层翻角让出的下层近角是露在外面的，先拉它把整叠布右移 15 cm（上层压在下层上并在折痕处相连，会跟着走），
  再翻回上层的角、把上层绕折痕翻回原位（这两段改用相对抓点的位移），再把下层远角拉到原位，最后最多三次残留折角整理；V2b（mll-4090-3）
  把第一步拆成两次各 7.5 cm。
- 2026-10-07 10:35：用户提议按折叠的逆过程展平、避免平移。实施：初始化改为对折不居中（`recenter_half_fold=false`，整叠布在原右半张位置
  x ∈ [−0.131, 0.164]），逆过程打开后布正好回到原平铺位置；路线改为两段逆折叠（上层翻角 → 上层翻面，均按相对抓点位移）+ 最多三次
  残留折角整理（`robot_oracle.py` 新增 `fold_layout.max_stages`，默认 1、其他档位不变）。平移方案的实验（V3、V3b、V2b）已停。新初态在
  mll-4090-1 上按"场景构形"准备中。
- 2026-10-07 10:50：跨机器复跑（mll-4090-3，同一镜像、同一 privileged 包、同一 oracle 入口 `solve.sh`）：very_easy（R3，rope01）770 行、
  easier（E2，rope02）1119 行动作与本机正式评分逐位相同，终态 hash 分别为 `cee772c30aff335e`、`c1a10b4df78cfa49`，与本机一致。
  证据 `runs/test_results/rope_very_easy_xmachine_20261006/remote/R3_bridge/`、`runs/test_results/rope_easier_xmachine_20261007/remote/E2_bridge/`。
- 2026-10-07 11:10：对折不居中的初态准备完成。前两次原地对折（10 s；放慢到 16 s）都被准备程序的材料保护（任一网格边超过原长
  1.15 倍即停止）停下，拉伸 1.15336 / 1.15028。原因：准备时机器人停在 home 不动、碰撞开着；左半张像翻书一样绕折痕
  x = −0.136 翻过竖直往右倒时，靠机器人一侧的上部扫过右手两根手指（离桌约 31 cm），一小块布被挡住拉紧。放慢不改变路径，
  所以无效；原居中做法翻书时折痕同时左移 15 cm，翻落的布从手指左侧约 9 cm 处经过。改为：先居中对折（与原 easier 相同）→
  两层布在空中右移 15 cm（`half_fold_return`，离桌 10–12 cm，比手指低 15 cm 以上）→ 在最终位置原地翻上层的角
  （`topogym/tasks/blanket_flatten/corner_preparation.py`）。第三次（mll-4090-1，`easier_inplace_03`）按"场景构形"验收通过：
  翻角全程没有触发保护，翻完时最大拉伸 1.013；冻结初态覆盖率 0.503、最高 25.4 mm、最大拉伸 1.025，三层上下次序无颠倒，各层
  平面位置与目标形状的均方根误差 0.9 / 4.2 / 3.0 mm（下层 / 上层主体 / 上层翻角），最大 6.5 mm；冻结时最大粒子速度 0.183 m/s
  （居中版本 0.364 m/s）。对照的第四次（mll-4090-3，三层折完再整体右移 15 cm）也通过（最大速度 0.162 m/s），不安装。已撤掉
  居中版本初态，安装第三次于 `corner_folds_archive_v1/cuda_sm89_mp128_87407517a32a/easier/seed_0`；`test-blanket-below-easy`
  7/7、`test-blanket-oracle` 6/6、`test-harbor-below-easy` 6/6、`test-v15-release-selection` 12/12。逆折叠路线的原生运行已在
  mll-4090-1 开始（`oracle_05_inplace`，源码快照 `oracle_source_05_inplace`）。证据目录
  `/data/jianwen/topogym/blanket_easier_upper_corner_20261006/`（`easier_inplace_03`、`easier_inplace_03_analysis.json`）。
- 2026-10-07 12:05：逆折叠路线第一次原生运行（mll-4090-1，`oracle_05_inplace`，11:09–11:43）。第一段（右手把上层翻角翻回）
  执行完，全布最大拉伸 1.324（门槛 1.5），翻角区域与"只对折"目标的均方根偏差从 124 mm 降到 18 mm，但角尖约 6 cm 的三角
  仍折着（62 个粒子偏差 > 3 cm）：抓点离角尖 25 mm、在抓持局部范围（半径 18 mm）之外，放下又短了 4 cm。第二段开始前的
  可达性检查失败（`No top-down IK along stage 1 for left`）。CPU 上逐点复查（`probe_reach.py --cpu`，证据
  `runs/test_results/blanket_easier_scene_diag_20261006/reach_02.json`）：第二段抓点 (0.029, 0.213) 上方 10 cm、贴布、抬起三个点
  左手两种朝向都够不到（位置差 10–21 cm）。原因：机器人整体在世界坐标中沿 x 偏移 −0.136（两肩约在 x = −0.605 与 +0.333），
  两臂以布的中心线、也就是对折的折痕 x = −0.136 为镜像；夹爪朝下时，桌面高度两手都只能越过折痕 9–11 cm
  （y ≤ 0.1：左手到 −0.025、右手到 −0.25；y = 0.2：−0.05 / −0.225），抬到 27 cm 时只剩 0–4 cm。不居中的对折把整叠布
  放在右手一侧，上层要翻到左手一侧，单臂做不完。路线改为（`below_easy_routes.py` 的 `EASIER`）：① 右手抓离角尖 14 mm 处
  （角尖在抓持范围内）翻回上层翻角，放到目标前 1 cm；② 右手抓上层自由边中点 (0.144, 0.15)，越过折痕放到 (−0.195, 0.15)，
  上层在自身上折返；③ 左手抓同一材料点，拉到展平位置 (−0.416, 0.15) 前 1 cm，折返滚回折痕；之后最多三次残留折角整理。
  CPU 预检（`probe_route_ik.py`，抓点用预测位置）：三段都至少有一种朝向通过，关节余量 ≥ 0.31 rad。原生运行已在 mll-4090-3
  开始（`oracle_06_handoff`，物理步上限放到 64000 以观察整条路线实际用量；mll-4090-1 的显存被另一会话的 slotted 评分占用）。
- 2026-10-07 12:35：用户决定 easier 改为远侧半张对折（D7 第三次调整；用户先问能否只折一条：左边一条宽 ≤ 18 cm 时左手单手可完成翻页，但初始覆盖率升到 0.70–0.75、翻角直角边只能 10–13 cm、仍是单手单点翻页，所以选转 90°）。交接路线的运行（`oracle_06_handoff`）按用户要求停在第一段翻角之后（exit 137）。实施：`blanket_corner_folds.py` 用 `far_half_fold` 取代今天加的 `recenter_half_fold`（左右对折恢复为提交版本的居中写法，very_easy 与居中左右对折的目标都与提交版本逐位相同）；easier 翻角直角边 22 → 18 cm（叠好的布 60 × 24 cm，翻角弯折须离对边 ≥ π × 层间距）；准备流程先在空中把布往远处挪 15 cm（`fold_away`），折完挪回（`fold_return`）；路线改为右手翻回翻角、两手各在自己一侧抓上层自由边（材料坐标 u = ±0.11、v = 0.22）一起越过折痕放回。CPU 可达性预检（`probe_route_ik.py`）：第一段右手朝向 0°余量 ≥ 0.65 rad，第二段左手 180°、右手 0° 余量 ≥ 0.59 rad。`test-blanket-below-easy` 7/7、`test-blanket-oracle` 6/6；新初态（`easier_farfold_01`）在 mll-4090-3 上准备中。
- 2026-10-07 12:43：远侧半张对折的初态准备通过（mll-4090-3，`easier_farfold_01`，按"场景构形"验收）：全程没有触发 1.15 的材料保护，各阶段最大拉伸 ≤ 1.020；冻结初态覆盖率 0.498、最高 26.1 mm、最大拉伸 1.026，三层上下次序无颠倒，各层平面位置与目标形状的均方根误差0.9 / 3.7 / 5.0 mm（下层 / 上层主体 / 上层翻角），最大 7.2 mm，不相邻粒子最近 7.97 mm；冻结时最大粒子速度 0.080 m/s（前两版 0.183 / 0.364 m/s）。已撤掉不居中左右对折的初态，安装于 `corner_folds_archive_v1/cuda_sm89_mp128_87407517a32a/easier/seed_0`（arrays sha256 `0391e0a1…`）；`test-blanket-below-easy` 7/7、`test-blanket-oracle` 6/6、`test-harbor-below-easy` 6/6、`test-v15-release-selection` 12/12。原生运行已在 mll-4090-3 开始（`oracle_08_farfold`，源码快照 `oracle_source_08_farfold`，物理步上限 64000）。证据 `runs/test_results/blanket_easier_scene_diag_20261006/easier_farfold_01_analysis.json`。
- 2026-10-07 13:20：远侧对折的第一次原生运行（mll-4090-3，`oracle_08_farfold`，12:42–13:08）停在第一段 `lay_corner`：全布最大拉伸 1.5007 > 1.5，辅助抓持松开。超线的边在上层，材料坐标 (276, 216)–(270, 216) mm，离抓点中心 20–24 mm，刚在抓持范围（18 mm）外、朝翻角折线一侧；放下过程中从 1.24 单调升到 1.50。失败时刻的布形（trail 第 5290 步）：被抓的那块布保持抓起时的朝向（夹爪始终竖直朝下、只平移），翻过 180° 后它相对周围的布是翻着的，从它往折线去的材料先往外走约 1.5 cm 再折回，多耗掉约 3 cm，手离折线的直线距离 9.2 cm 时就到头了；按几何算整个翻角并未拉直。`routes.py` 的 hard 路线注释记录过同一现象（翻页带到镜像位置时抓点处 1.48），做法是低弧线、落短、离桌 3 cm松手、再用新的抓点摊开。路线改为三段：① 右手翻回翻角，过折线时 9 cm 高，落在折线外 7 cm（镜像位置 11 cm）；② 两手翻回上层，过折痕时 12 cm 高，落在 y = 0.30（折痕外 15 cm，镜像位置 22 cm）；③ 两手抓上层远边 u = ±0.2、v = 0.21（离第二段翻着的两块 9 cm），往外拉到展平位置前 1 cm（y = 0.35）。CPU 可达性预检：三段都至少有一种朝向通过，关节余量 ≥ 0.68 rad。新的原生运行已在 mll-4090-3 开始（`oracle_09_farfold`）。
- 2026-10-07 14:15：三段路线第一次原生运行（mll-4090-3，`oracle_09_farfold`，13:14–14:01）。第一段（右手翻回翻角，低弧线、落短 4 cm）完成，全布最大拉伸 1.443，松手后翻角完全平复（第二段开始时全布最高 12.7 mm，即只剩两层）。第二段建立抓持时失败（`Assist did not admit both hands`）：两手指令高度相同（工具中心点离桌 32.6 mm），下压结束时左手实际高 3.1 mm、右手低 2.2 mm，且两手指尖都比 oracle 估计的伸出量多 3–4 mm，结果左手指尖停在布面上方 1.4 mm、右手指尖插进两层布 4.9 mm；右手下方的下层布（材料坐标 (132, −222) mm）被压到 1.5007，右手刚被接纳就以"material_strain" 判为丢失。抓持规则要求丢失的手先张开再合上才能重新接纳，而 oracle 的接触反馈仍每 0.25 s 把它再压低 1 mm，9 步共压 9 mm，上层被挤到 2.43 后粒子穿透、数值发散（拉伸读数 40587，第 10272 步）；左手因全布拉伸超限一直不能被接纳。修改：`robot_oracle.py` 的下压高度改读路线的 `fingertip_gap_m`（缺省仍为 1.5 mm，其他档位不变），easier 设 8 mm，由接触反馈逐毫米下压到被接纳。`test-blanket-oracle`、`test-blanket-below-easy`、`test-harbor-below-easy` 通过。另记：接触反馈不处理"丢失"的手、会继续下压，只在失败路径上出现，暂未改。重跑：本机与 mll-4090-3 同一快照（`oracle_source_10_farfold`）同时运行，兼作跨机器一致性对照。
- 2026-10-07 15:25：指尖停高 8 mm 后的两次运行（本机与 mll-4090-3，`oracle_10_farfold`，同一快照）都在第二段建立抓持时失败，接触记录逐步一致（同一步、距离差 ≤ 0.2 mm），说明换机器结果可复现。经过：右手在接触第 5 步、指面离粒子中心 5.6–5.9 mm（约隔 2 mm）时被接纳；之后它的指令已固定，但手臂仍在追赶前面逐毫米下压的指令并有约 2 mm 稳态误差，1 s 内手指又下沉 2.1 mm，把抓住的上层布压低 1.8 mm，正下方下层布的边从 1.03 升到 1.46 后超限，右手判为丢失；接触反馈随后又把它压低 9 mm，最终数值发散（拉伸读数 42359）。左手起点离粒子中心 14.9 mm，降到 6.2 mm 时被全布超限挡住。very_easy 只有一只手、接纳后立即抬起，所以没遇到。查辅助抓持接纳条件（`grasp_soft.py`）：两指面各自离抓持区内某粒子中心 ≤ 6 mm（`contact_distance_m` 默认值），粒子陷入手指 ≤ 2 mm，区域在最上层、全布拉伸不超限、候选唯一并持续 0.03 s；不要求手指碰到布。very_easy 通过的 v18 Harbor 评分里，手指在离粒子中心 6.6 mm 之后的下一步被接纳，全程未压布。修改：`Contact` 增加 `hold_admitted`（路线 `hold_admitted_height`，easier 打开，缺省关闭）：已接纳的手按接纳时实测的工具中心点高度每 0.25 s 补偿下沉；有手被判为丢失时结束接触阶段（规则要求先张开才能重新接纳），不再继续下压。三项测试通过；本机与 mll-4090-3 同一快照重跑（`oracle_11_farfold`）。
- 2026-10-07 17:45：`oracle_11_farfold`（本机，15:22–17:30；mll-4090-3 同一快照，停在第三段建立抓持时被我停掉）。第一段完成（峰值本机 1.438、mll-4090-3 1.471）；第二段两手都被接纳并完成翻页（右手在接触第 5 步被接纳，按实测高度保持后仍随手臂漂移：手指 1 s 内又沉 2.2 mm、整手朝底座漂 8.6 mm，关节跟踪误差持续增大，例如手腕俯仰 41 → 55 mrad；左手第 12 步后才被接纳，期间全布拉伸升到 1.452）。第二段松手后：两抓点之间（u −0.11 至 0.11）铺开，远边距展平约 3 cm；两侧外段（u = ±0.2、±0.3）从 v ≈ 0.12 起折回压在上层自身上（两层、约 12 mm 高）。第三段抓点（u = ±0.2、v = 0.21）正落在折回的布上，往外拉相当于再翻一次页，左抓点边缘到 1.5005 失败。修改（`oracle_source_12_farfold`）：① `Contact`（`hold_admitted`）让两手同时被接纳：未接纳的手按实测指面距离每步最多降 3 mm，降到 8.5 mm 内等待另一只，都到后一起每步降 1 mm；已接纳的手按接纳时实测的工具中心点三个方向补偿漂移（模拟数据单测通过）；② 翻页抓点外移到 u = ±0.22（离角 8 cm），落点 y = 0.30 → 0.32；③ 拉平抓点改到两翻页抓点之间正面朝上处（u = ±0.15、v = 0.20），抬 5 cm 拉到 y = 0.34；④ 翻角落点再短 0.5 cm（0.1275 → 0.125）。CPU 可达性预检通过（余量 ≥ 0.69 rad），三项测试通过；本机与 mll-4090-3 同时重跑。
- 2026-10-07 19:35：`oracle_12_farfold`（本机，17:34–19:17）。两手同时被接纳生效：两手指面距离同步从 14.4/14.5 降到 6.2/6.3 mm 后同一步被接纳，接触期间全布最大拉伸 1.009（上一轮 1.452）；全程最大拉伸 1.384（第一段放翻角）、翻页 ≤ 1.224；mll-4090-3 同一快照到第二段结束最大 1.262。第二段松手后布已满足原生运行的任务目标（原生配置覆盖率门槛 0.90）：第三段下降途中（仿真 41.2 s、第 16,466 步）任务以 "Goal stable" 成功终止，覆盖率 0.912、最高 11.4 mm、最大速度 0.0003 m/s、最大拉伸 1.008。oracle 随后在接触阶段报 "Assist did not admit both hands"——阶段循环只在每段开始检查终止，段内终止后被跳过的接触阶段读成未接纳。修改：`robot_oracle.py` 接触阶段后若任务已终止则正常收尾（只影响任务已终止的情形）。正式评分（release profile）要求覆盖率 0.95，0.912 不够，第三段仍须拉平。`diag_native.py` 增加 `--coverage`（重置后把任务的覆盖率门槛设为给定值，初态身份不变，与评分方只改目标的做法一致）。按 0.95 在本机重跑（`oracle_13_farfold`）；mll-4090-3 的 `oracle_12` 继续跑完作跨机器对照。
- 2026-10-07 20:35：`oracle_12` 终态分析（本机，第 16,466 步）：两个折都已打开，全布最高 11.4 mm，没有内部褶皱；上半张整体向折痕错位约 1.5 cm；未覆盖的 8.3 %（按 4 mm 网格、6 mm 内无布计）全部在远边 y > 0.33 的一条带上，横贯整个宽度——远边最外约 2.5 cm 沿整条边往回折、压在布面上（材料坐标 v = 0.24 的边落在 y = 0.311、高 11.4 mm；折线在 v ≈ 0.215–0.22，正是第二段两手抓点那一行）。成因：被抓的那小块布翻过去后方向是反的，抓点外侧的 2 cm 跟着它反着落下，整条边连成卷边。mll-4090-3 的 `oracle_12` 同样在第二段后按 0.90 判成功（第 16,251 步，覆盖率 0.911）。卷边只有约 2.5 cm 宽，比被抓那块布翻转后多耗的约 3.6 cm 还窄，不能靠再翻一次打开；改为第二段直接抓在边缘（材料坐标 v = 0.234，离边 6 mm），落点 y = 0.33，余下的约 5 cm 由第三段沿垂直折痕的方向往外拉平。CPU 可达性预检通过（余量 ≥ 0.69 rad）。并行：本机 `oracle_13`（现路线，门槛 0.95）继续；mll-4090-3 的 `oracle_13` 副本停掉，换成新版 `oracle_14`（`oracle_source_14_farfold`，门槛 0.95）。另：用户问 blanket very_easy 的"待重评"——本机 v18 privileged 1、standard 因共享显存中断；v19 改了布料静止判定（`42c6ee4cd`），需在 v19 重做两模式评分（D6）。
- 2026-10-07 20:50：用户定原则：lab 推送过来的改动及其附带验证视为已完整测试，不在本机重评（D6 部分决定）。blanket very_easy 据 lab 的 v19 回放（第 637 行严格通过）记为通过，取消"v19 重评"。来源核对：very_easy 场景与路线由本方 10-05/10-06 提交（LUIGIVAMPER）；lab 评分发现粒子 7458 的 PBD 二周期抖动（读数 33 mm/s），给出两个选项，用户选"改用每 tick 位移算速度"，lab 实现为 `42c6ee4cd`（QinengWang-Aiden，10-06）并回放验证，10-06 晚经 `d86ea023a` 合并进本地。
- 2026-10-07 21:45：用户要求今晚 23:00 前尽量完成 blanket easier 的开发与 Harbor 评分，门槛不降（0.95）。单步耗时实测（本机 `oracle_12`，按各阶段起止步数与逐步写盘时间）：夹爪张开的阶段 95–135 ms/物理步，夹爪合上（找抓点、抓持中）540–600 ms/物理步，全程平均 360 ms（16,466 步 98.9 min）；一个物理步 2.5 ms 仿真时间，控制步 = 10 物理步。整条路线约 2.3 h。`oracle_14`（第二段抓边缘）第二段后卷边由 2.5 cm 收窄到约 1.5 cm，但仍沿整条边（被抓那块布本身翻过去后仍是反的）；第三段抓点 v = 0.20 落在卷边下，已停。新第三段：抓 v = 0.17（卷边内侧 2 cm），拉到展平前 3 mm（`oracle_15`，mll-4090-3）或 8 mm（`oracle_15b`，本机）。为赶时间，不等原生结果，直接用 3 mm 版路线启动 v19 正式评分：`bash bash_scripts/run_harbor_oracle_grades.sh --output runs/test_results/blanket_easier_harbor_v19_20261007_01 --families blanket_flatten --tiers easier --image topogym-below-easy:v19-20261007-blanket01 --gpu 0`（21:39 起，先 privileged 后 standard）。另：mll-4090-3 根分区被写满（3.6 TB，本组实验约 290 GB），已删旧运行的逐步状态文件，腾出 99 GB；该机无 /data 写权限，输出仍在 home，跑完即清。
- 2026-10-07 21:55：第一次启动正式评分（`blanket_easier_harbor_v19_20261007_01`）在构建实例时失败：`Frozen initial-state scene/configuration identity differs`。原因：发布配置把覆盖率目标从 0.90 改为 0.95，而冻结初态的身份记录了 0.90；`topogym_merge_candidate.py` 只对用 `initial_state_path` 显式给出的初态做"只改目标"的重新标记（`rekey_goal_parameters`），按资源名读取的初态被跳过；`bash_scripts/run_harbor_oracle_grades.sh` 不传 `--blanket-initial-state`。改为先手动生成候选：`.venv-gs121-nyx/bin/python scripts/topogym_merge_candidate.py --output runs/test_results/blanket_easier_harbor_v19_20261007_02/candidate --families blanket_flatten --tiers easier --gpu 0 --image topogym-below-easy:v19-20261007-blanket02 --blanket-initial-state easier=<已安装的 easier manifest>`（重新标记：覆盖率 0.90 → 0.95，arrays 逐字节不变），写入同格式 `queue.json` 后用包装脚本 `--resume` 构建与评分；21:51 开始评分（先 privileged 后 standard）。
- 2026-10-07 22:05：用户决定以 Harbor 正式评分作为唯一通过标准、优先并加快评分。已停原生 `oracle_15`（mll-4090-3）与 `oracle_15b`（本机），本机只跑评分。曾尝试把 privileged 与 standard 拆成两个进程并行，standard 立即报 `blocked_dependency`：standard 的 oracle 是回放同一实例 privileged 得分 1 的轨迹（`topogym/planning/harbor_bridge/suite.py`，recipe `privileged_output` → `public_trajectory`），两模式只能先后执行。现用一个进程顺序跑两模式：`test_harbor_oracles.py --output runs/test_results/blanket_easier_harbor_v19_20261007_02/grade_both --tasks-root .../candidate/tasks --candidate --families blanket_flatten --tiers easier --modes privileged standard --no-nop --execute`（21:59 起）。
- 2026-10-07 22:55：blanket easier v19 正式评分 privileged 通过（`grade_both`，21:59 起）：现场运行 22:02–22:18，第三段后折角诊断 0 个折着的粒子、任务以 Goal stable 成功（覆盖率 0.9999、最高 4.0 mm、五项判定全过）；评分器两次回放 1920 s，严格达成于第 2336 行，未用回放容差，deterministic 1、instance_exact 1。Harbor 路径单步约 30 ms/物理步（原生诊断约 360 ms，多出的主要是逐步状态写盘与拉伸日志）。standard（回放该轨迹）22:53 起。
