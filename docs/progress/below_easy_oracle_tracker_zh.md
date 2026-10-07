# very_easy / easier oracle 开发与检验：工程目标与进度

> 建立：2026-10-06。最后核对：2026-10-06 19:15 CDT（`dev/jianwen`，HEAD `2f3233023`，已合并 `rcb/dev/jianwen`：lab 的
> orbits 两处修复与 slotted very_easy oracle）。
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
| R1 | rope very_easy | 0（lab `7f0b002cc`；本机同样失败） | 未运行（缺 privileged 轨迹） | `raise_to_ring`：抬到环心上方 10 cm 的 IK 无解（够不到）；改到 6 cm 后，下放到半圆上时右手丢绳 | 环境配置修正（他人进行中）、D2 中不在其清单的项、D5 | **仍失败**；运动学部分可先做 |
| R2 | rope easier | 0（lab `7f0b002cc`） | 未运行 | 同 R1 的抬升；改走入口送绳位后，`feed_through_ring` 需要超出公开动作范围的关节目标（送绳被挡） | 同 R1 | **仍失败**；运动学部分可先做 |
| O1 | orbits very_easy | 0（lab 两次，`7571e4194`；本机停在第 99 行） | 未运行 | lab 修掉前两处后（`79c21d1f6`，已合并），停在右臂接近：oracle 自己的双臂间隙检查 0.47 mm < 1 mm | Orbits 加速 | **暂缓**：先做加速（用户 10-06） |
| O2 | orbits easier | 0（lab；本机停在第 195 行） | 未运行 | lab 修复后，`fresh_bight_carry` 抓持误差 14→23 mm，绳被压扁 0.25 s，Session 终止 | Orbits 加速 | **暂缓**：先做加速（用户 10-06） |
| B1 | blanket easier | 0（lab `7571e4194`，第 633 行） | 未运行 | `lay_half`：布料边拉伸比 1.3014 > 1.3，辅助抓持释放 | D6（评分基线版本） | **仍失败**；D1 已定，可以开始 |
| K1 | knot easier | lab 评 `7571e4194` 版：进行中；本机 v18 冻结快照 `source03`：grade 1、solved 1 | 本机 `source03`：grade 1、solved 1 | lab 结果未到 | — | **等待评分** |

本机正在运行的评分作业（不归本页所有，结果出来后登记）：`runs/test_results/harbor_below_easy_v18_20261006_ik01/`，
镜像 `topogym-below-easy:v18-20261006-ik01`，10 个家族的两档双模式，队列中有 knot 与 orbits。它的源码快照是
`7571e4194` 加当时的工作区改动，**不含** lab 的 orbits 两处修复，所以其中 orbits 的结果只反映修复前的代码。它把
rope、blanket 搁置在 D1 上；D1 现已决定（两档可用辅助抓持），但 rope 仍应等环境配置修正落地后再评（否则评的是
即将被替换的配置），blanket easier 的路线问题未修，评了也是 0。这两点需要告知该作业的负责会话。
19:15 CDT：buzz very_easy 双模式 1，buzz easier privileged 仍在运行。

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

**环境配置修正（他人进行中，10-06）**：两档实例实际用的是 `scripts/topogym_merge_candidate.py` 为两档推荐的配置，
原三档用 `topogym/tasks/release_profile.py` 的 `contact_relaxed_v16`。修正方给出的差异：辅助抓持接触距离 1 vs 6 mm、
辅助强度 100 vs 1000、最大拉伸比 1.3 vs 2.0、每控制步物理推进 10 × 2.5 ms vs 1 × 40 ms、网格顶点 33,070 vs 4,939。
完整差异（含不在该清单中的项）见 D2。

等待修正期间：

- **现在可做（与绳物理无关）**：抬升目标与 easier 送绳位能否到达、整段是否在公开动作范围内，只取决于机械臂模型、
  环的位置和公开动作范围；可在 CPU 上用当前冻结实例的几何，对 `99c3d27b0` 的 18 条候选做离线 IK 与路径检查。
  新初态重新沉降后抓点会略移，结论届时在新实例上复核一次。另可检查 oracle 中按步数计的动作段和限速，
  为控制步 25 → 40 ms 做准备（只能等新配置落地后验证）。
- **必须等修完**：very_easy 下放时丢绳，恰由辅助抓持的强度、拉伸比、接触距离决定，配置一改结果可能完全不同；
  rope 的任何物理运行、正式评分和测速，换配置后实例与物理身份都会变，旧结果不能沿用。
- **需要协调**：确认修正方是否也改 `topogym/planning/rope_threading/policy.py` 或 `harbor_bridge/below_easy.py` 的
  rope 分支；若会，本页先不动这些文件。

下一步：

1. 与修正方确认 D2 表中不在其清单的项。
2. 修正落地后：在新实例上跑原生 oracle，逐一确认三处——抬升可达、very_easy 下放不丢绳、easier 送绳行在公开动作范围内。
3. 测每控制步耗时，估算整次执行时长；超 72 min 交 D5。
4. privileged → standard 正式评分，登记第 7 节。

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

下一步（D1 已定，可以开始；与 rope 的配置修正无关）：

1. 在冻结初态上记录 `lay_half` 全程每步的最大拉伸比及其所在的边（被抓的上层还是未抓的下层），确定峰值时刻。
2. 按定位结果在以下方向中选择：放慢或降低下放；把抓点移向折边；两手同时展开对折。一次只改一项并复测。
3. 原生成功后 privileged → standard 正式评分；评分基线版本按 D6。

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

跨机器与扰动实验（10-06 起，进行中；证据 `runs/test_results/knot_easier_xmachine_20261006/`）：

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
- rope 用哪一组辅助抓持参数（两档推荐值还是原三档值）属于 D2。

### D2 rope 两档改用原三档配置时带入哪些项

"带入"指生成 rope 两档候选实例的那一步（`scripts/topogym_merge_candidate.py` 的 `candidate_inputs()`）：把原三档
`contact_relaxed_v16`（`topogym/tasks/release_profile.py:24-38`）中的哪些项写进两档实例的 `task_parameters` 与
`simulator_overrides`。现在这一步对 rope 两档只写入推荐的辅助抓持（`topogym/tasks/rope_threading/simplified.py:11-16`），
其余全用 Task 默认值（`topogym/tasks/rope_threading/common.py:46-48`）。修正由他人进行；其清单列了 5 项，下表其余
各项需与修正方确认。

| 项 | 两档现在 | 原三档 v16 | 性质 | 建议 |
| - | - | - | - | - |
| 每控制步物理推进 | 2.5 ms × 10（控制步 25 ms） | 40 ms × 1（控制步 40 ms） | 时间步 | 带入 |
| IPC Newton / PCG 容差 | 1e-3 / 1e-5 | 3e-3 / 3e-5，`linear_bvh` | 求解器 | 带入 |
| 绳网格 | 默认，33,070 顶点 | 5.5 mm 间距、12 边，4,939 顶点 | 绳模型 | 带入 |
| 绳杨氏模量 E | 5e4 Pa（`topogym/assets/materials.py:39`） | 5e6 Pa（硬 100 倍） | 绳模型 | 带入 |
| 绳的静止形状 | 直绳 | 出生时的形状 | 绳模型 | 带入 |
| 与绳碰撞的机器人连杆 | 全部连杆 | 只有手指 | 接触 | 带入 |
| 辅助抓持：接触距离 / 强度 / 拉伸比 | 1 mm / 100 / 1.3 | 6 mm / 1000 / 2.0 | 辅助抓持 | 带入 |
| 辅助抓持：抓点半径（空间 / 材料） | 12 / 14 mm | 14 / 18 mm | 辅助抓持 | 带入 |
| 辅助抓持：最大平移误差 / 穿透 | 10 / 2 mm | 25 / 6 mm | 辅助抓持 | 带入 |
| 辅助抓持：要求抓点外露 | 是 | 否 | 辅助抓持 | 带入 |
| 终态速度上限 | 1 mm/s | 10 mm/s | **成功判据** | 不带入（见下） |
| 孔口接触余量 / 孔口检查形状 | 0 / 圆柱 | 1 mm / 圆环 | **easier 穿环判据** | 不带入（见下） |
| R2、R3 环的偏转、偏移、安装侧 | 两档没有这两个环 | 有 | 几何 | 不适用 |

- 不带入判据项的理由：它们决定"什么算解出"，不是物理设置；项目约定不能用改判据来弥补控制器问题
  （[门槛审查「建议的统一接受逻辑」第 5 条](../rcb/oracle_tolerance_review_zh.md)）。
- 风险：原三档在 v16 物理下把速度上限设为 10 mm/s，[rope oracle README](../../topogym/planning/rope_threading/README.md)
  只写了"显式采用"，没写原因。换物理后须先测两档出生静置和终态的绳速能否低于 1 mm/s；若测得做不到，是否放宽
  由用户决定（属判据改动）。孔口两项同理：只在 easier 的穿环判据因 1 mm 以内的绳-环接触误判时，才单独提出。
- 代价：两档初态须在新物理下重新沉降，镜像重建，难度顺序与初态检查重做；物理身份改变，此前两档的评分不能沿用。
- 决定：_（待与修正方确认，含日期）_

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

rope 两档现约 1.5–2 h，orbits very_easy 现约 5–7 h。rope 在配置修正后重测；orbits 随加速页重测。仍超出的由用户决定是否豁免。

### D6 正式评分的基线版本

交接称 blanket 的"已静止"判定在 v19 修正（针对 very_easy 中一个粒子在相距 20.65 μm 的两点间来回跳、速度读数恒为
33 mm/s 的问题）。10-06 19:00 检索：v19 在本机**任何地方都不存在**——所有本地分支与已 fetch 的远端分支、提交说明、
已提交文件、未提交改动、另一个 worktree、helper 发布副本、`runs/test_results` 目录名、本地 Docker 镜像均无；
最新为 `merged-v18`（`topogym/tasks/release_profile.py` 的 `PROFILE`）。本环境连不上 GitHub（ssh 公钥被拒），最近一次
fetch 之后远端若有新推送则看不到。v19 对 oracle 的影响无法从代码确认，需要向构建 v19 的人要变更清单。

- 已知的唯一一项若是 blanket 静止判定，它改变 blanket 五档的成功判定时刻，blanket 在 v18 上的评分都要在 v19 重评；
  其他家族是否受影响取决于 v19 是否改动它们的运行时（v17→v18 时是逐项核对"逐位相同"后才沿用旧评分的）。
- 决定：六项正式评分统一在 v18 还是 v19 上做 _（待填）_；helper 页的 H 项（helper 目标版本）是同一问题。

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
| 10-06 | lab | orbits very_easy | privileged ×2 | `7571e4194` | `obejw/rcb-topogym:0.2.16-dev-cu128`；2.5 ms × 10，eps 1 mm/s | 0 / 0 | 第 99 行、第 238 行 | lab `obe/tree_g/runs/test_results/harbor_grade_obe_*` |
| 10-06 | lab | orbits easier | privileged | `7571e4194` | 同上 | 0 | 第 195 行 | 同上 |
| 10-06 | 本机 | orbits very_easy、easier | privileged | v18 两档候选 | `topogym-local/orbits-v18:below-easy-20261006-01` | 0 / 0 | 第 99 行（4.475 s）/ 第 195 行（6.875 s） | `runs/test_results/orbits_v18_20261006_01/harbor_goal01/` |
| 10-06 | lab | blanket easier | privileged | `7571e4194` | `obejw/...`；lab 重新准备的初态 | 0 | 第 633 行 `lay_half`，拉伸比 1.3014 | lab `obe/tree_g/runs/test_results/harbor_grade_obe_*` |
| 10-06 | lab | knot easier | privileged | `7f0b002cc` | `labv18be` | 0 | `grasp_ends:converge`：左 TCP 差 17 mm，偏置到 40 mm 上限 | lab `align_be/sweep/` |
| 10-06 | 本机 | knot easier | privileged / standard | 冻结快照 `source03` | `topogym-below-easy:v18-20261005-01`；v18 K2 | 1 / 1 | — | [grading_summary.json](../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/grading_summary.json) |
| 10-06 | lab | knot easier | privileged / standard | `7571e4194` | `obejw/...` | 进行中 | | lab `harbor_grade_obe_knot_untying_very_easy_easier` |

## 8. 相关但不在本页范围

- blanket very_easy：本机 v18 privileged 已 1（严格门槛），standard 因共享显存低于本任务 2 GiB 保护线中断，待重试；
  lab privileged 只在回放容差内为 1、standard 0。lab 的初态是在它自己的 GPU 上重新准备的，折角旁皱褶处一个粒子被
  自碰撞投影在两点间来回推，速度读数恒为 33 mm/s；本机初态没有这个问题，属于换机器导致的失败。修法二选一：
  v19 的"已静止"判定（见 D6），或在 oracle 中给 very_easy 加与 easier 相同的整理段（`fold_layout`），先整平皱褶再等静止。
- slotted_post_ring：very_easy 在 lab 双模式 1（已随 `2f3233023` 合并）；easier 用户已决定改场景（第 2 颗珠固定在
  绳圈上），lab 另行交付。
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
