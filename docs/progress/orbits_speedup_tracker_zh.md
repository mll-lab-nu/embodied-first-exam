# Orbits very_easy／easier 加速工程目标与跟进（2026-10-06 建立）

本页是 Orbits 加速工作的唯一跟进表。每次有新运行结果，在"跟进日志"追加一行，并同步更新
"逐档状态"表；结论只写有证据目录支撑的内容。任务背景见 [Orbits 任务页](../develop/tasks/orbits_zh.md)，
交接说明见 [ORACLE_FIXES_2 第 3、6 节](../rcb/ORACLE_FIXES_2_FOR_JIANWEN.md)，
全项目加速记录见 [TOPOGYM_SPEEDUP_RECORD](../rcb/TOPOGYM_SPEEDUP_RECORD.md)。

## 场景与问题

Orbits 场景：桌上一个木底座立着柱子，柱上套着金属环（very_easy 单球头柱、easier 单环双柱、
easy / medium / hard 为两／三／四环），一根 0.8 m 软绳（FEM 有限元四面体网格）缠绕在环和柱上。
ALOHA 双臂只能靠夹爪摩擦抓绳（本任务没有辅助抓持），要把绳从整个器具上解下，放到目标区并静止：
全绳节点和木柄线速度 ≤ 1 mm/s、木柄角速度 ≤ 0.02 rad/s，连续 0.5 s。very_easy / easier 的绳和木柄
线速度上限按用户 10-06 决定放宽到 10 mm/s（待实施，见"终态判据"节）。

物理由 Genesis 驱动 libuipc 的 IPC（增量势接触）求解。当前每档的时间步设置相同：

- 控制周期 25 ms = IPC 帧长 `physics_dt_s` 2.5 ms × `control_decimation` 10；
- 每帧 Newton 迭代解到 `newton_tolerance` 1e-3，线性方程组容差 1e-5，碰撞宽相 `linear_bvh`；
- very_easy / easier 另设摩擦正则化速度 `contact_eps_velocity` 1 mm/s（物理身份
  `below_easy_v2_fem_soft50_friction1mm_v1`）；easy / medium / hard 仍用默认 10 mm/s。

（来源：`runs/test_results/orbits_v18_20261006_01/candidate/tasks/*/environment/instance.json` 的
`simulator` 段；`topogym/tasks/orbits/below_easy.py:38`。）

**为什么必须加速。** Harbor 规则：一次完整 oracle 执行最多占 agent 6 h 预算的 20 %，即 72 min
（4320 s）。lab 上测得 Orbits easy 每个控制步 2.50 s（v18，近静止的手臂小幅摆动，前 5 步中位数）。
4320 s ÷ 2.50 s ≈ 1730 个控制步 ≈ 43 s 仿真时间。也就是说，按现在的步时，整条解绳 oracle 必须在
约 43 s 仿真时间内做完；而接触多的阶段每步更慢，实际可用时长更短。现有已完成任务的 oracle
多在 50–300 s 仿真时间，所以不先降步时，Orbits 的 oracle 即使写出来也过不了时长规则。

## 工程目标

范围（2026-10-06 用户决定）：**只改 very_easy、easier 两档**。easy / medium / hard 的物理设置、
冻结初态、oracle 都不动，也不在本页做测量；交接材料原写"五档统一"，以本决定为准。
两档的摩擦正则化速度 `contact_eps_velocity` 回到默认 10 mm/s，与原三档一致；两档终态线速度上限
放宽到 10 mm/s（见下节）。

1. **统一物理设置**：两档采用同一套新的 IPC 时间步／求解器设置，摩擦正则化速度回到 10 mm/s；初态验收看绳穿环关系稳定（拓扑不变、绳头不滑脱），不看绳速；
   一次性改成新的物理身份，逐档重新生成冻结初态，通过与 10-05 相同的初态检查。
2. **测出加速收益**：同一主机、同一测量方法下，逐档给出修改前后的每控制步耗时和建场景耗时。
3. **测出对完成效果的影响**：有 oracle 的档位比较修改前后的任务完成、Harbor 评分和接触几何指标；
   无 oracle 的档位标"未验证"，待 oracle 可用后补测。
4. **交付**：本页的两档配置变更说明 + 加速结果表；同步任务页和 `docs/progress/current_zh.md`。

交接材料没有给出目标加速倍数或完成时限。本页把"可行"定义为：完整 oracle 执行按测得步时估算
不超过 72 min。若某档在新设置下仍超出，单独记录，由用户决定是否给出时长豁免（同 fiber hard、
buzz hard 的先例）。

## 候选物理设置

| 候选 | 设置 | 依据 | 风险 |
| --- | --- | --- | --- |
| **K2（建议先试）** | `physics_dt_s` 5 ms、`control_decimation` 5（控制周期仍 25 ms），`newton_semi_implicit_enable` + `newton_min_iterations` 3 | knot 同为 FEM 绳 + IPC，v18 已上线（`c83285343`）：步时 2.132 → 1.067 s（2.0×），完整 oracle 2.0–2.8× 提速；双重验证（最小非相邻中心线间距、桌面间隙、拉伸、无翻转四面体）在原设置包络内 | Orbits 有刚体木柄和环（ABD 仿射体），且只有摩擦抓持；knot 的 K1（1 次迭代）出现过夹爪下压扁绳，须逐档复验 |
| rope 设置（交接第 6 节建议） | 40 ms 单帧、`control_decimation` 1、Newton 3e-3 / PCG 3e-5，更粗更软的网格，机器人只用手指接触（rope `contact_relaxed_v16`） | rope 近静止 0.156 s/步，rope medium 端到端 33 min。交接粗估物理 4–10×（未实测），即 0.5–1 s/步 | 帧长是现在的 16 倍；rope 依赖辅助抓持，Orbits 只有摩擦抓持，绳缠在柱环之间，穿透风险高。K2 不够时再试 |

K2 按 knot 的比例估算 Orbits 步时约 1.25 s，72 min 可容约 3450 步（约 86 s 仿真时间）。
**这是推算值，未实测。** 交接第 6 节估计 very_easy 整条路线约 2500–3300 个控制步，所以 K2 的 2× 单独
不够，还要压缩 oracle 自身每步的检查开销（见"oracle 时长基线"节），或改用 rope 设置。

物理步时的测量（同一段动作在新旧设置下回放、比较每步耗时）不需要 oracle；
"加速后任务仍能完成"的验收需要 oracle 跑通。

### 摩擦正则化速度回到 10 mm/s（用户 10-06 提出）

IPC 摩擦在相对滑动速度低于 `contact_eps_velocity` 时按粘性处理，所以绳搭在柱、环或桌上时，
可能以低于该值的速度持续缓慢滑动。10 mm/s 高于成功判据的 1 mm/s，这正是 10-05 给两档改成
1 mm/s 的原因（同 knot 的做法）。已有对比（同一 seed、800 tick 沉降后观察 2 s）：

| 档位 | 10 mm/s（v1）终点最大绳速 | 1 mm/s（v2） | 2 s 最大节点位移 v1 / v2 |
| --- | --- | --- | --- |
| very_easy | 2.241 mm/s | 0.450 mm/s | 4.587 / 0.936 mm |
| easier | v1 末尾 0.5 s 未满足 ≤ 1 mm/s | 未取得（初始化中止） | — |

（来源：[Orbits 任务页 10-05 节](../develop/tasks/orbits_zh.md)、
`runs/test_results/orbits_friction_fix_20261005/historical_bootstrap_review.json`。）

慢速滑动影响两个时刻，验收口径分开：

- **初态（绳穿在环／柱上）**：用户 10-06 定的口径是**绳穿环关系稳定**，即拓扑不变、绳头不会因离环
  太近而滑脱；慢速滑动本身可以接受，绳速不作要求。检查：沉降后观察期内拓扑保持，并报告每个绳头到
  它所穿的环／柱开口的沿绳距离的最小值，确认没有逐渐缩向零。
- **终态（解下来放进目标区）**：用户 10-06 决定两档的绳和木柄线速度上限放宽到 10 mm/s（同
  rope_threading `merged-v16` 发布配置的做法；木柄角速度 0.02 rad/s 不变），连续 0.5 s 不变。
  交接第 6 节在初态上测得：ε = 10 mm/s 时静置的绳慢滑 2.0–2.5 mm/s（5 s 内约 10 mm），ε = 1 mm/s 时
  0.37–0.54 mm/s。10 mm/s 上限对 2–2.5 mm/s 的慢滑有约 4 倍余量。
  "与器具完全脱开"由目标区判据保证，与速度上限无关（见跟进日志 10-06 最后一行）。
- **原三档的潜在问题（不在本轮范围，只登记）**：easy / medium / hard 用 ε = 10 mm/s，终态上限仍是
  1 mm/s；按上面 2 mm/s 左右的慢滑，绳可能一直达不到 1 mm/s。两档放宽后，五档的终态速度上限不一致。

实施方式：与时间步改动合成一次物理身份修订（`topogym/tasks/orbits/below_easy.py` 去掉
`contact_eps_velocity` 覆盖、设置终态速度上限、更新 `model_revision`），只重做一次冻结初态；
目标描述文字、instruction 和终态回归测试随之更新。

## 当前 oracle 覆盖（2026-10-06）

| 档位 | oracle | 最近一次 Harbor 结果 | 失败位置 |
| --- | --- | --- | --- |
| very_easy | 原生候选 `topogym/planning/orbits/native_session.py` | privileged 0 分；standard 未运行（缺 privileged 成功轨迹） | 第 99 个动作（仿真 2.475 s），左手抓绳腿的接近阶段：`BridgeError: Action would be clipped by the public robot adapter` |
| easier | 同上 | privileged 0 分；standard 未运行 | 第 195 个动作（仿真 4.875 s），左手抓绳的第一次对准：`ValueError: No close contact pose above the support surface: left` |
| easy / medium / hard | **无**。仅有历史 MuJoCo 一维绳规划（虚拟点夹爪），不是 Genesis/IPC 机器人 oracle | 未打包进 Harbor（`run_harbor_oracle_grades.sh` 排除，`harbor_bridge/catalog.py` 无条目） | — |

两档的失败都是 oracle 自身的可达性／动作限幅问题，不是物理超时；回放确定性、实例精确重载都通过
（`deterministic=1`、`instance_exact=1`）。证据：`runs/test_results/orbits_v18_20261006_01/harbor_goal01/`。

**这两处已修**（交接第 6 节，`79c21d1f6`，10-06 17:53 经 `2f3233023` 合入 dev/jianwen；本地尚未复跑）：

- very_easy：IK 把左前臂滚转关节解在模型极限 −π，float32 舍入后超出公开动作范围约一个 ulp；
  现在 ≤ 1e-4 rad 的超出直接夹回，更大的仍报错。
- 两档：绳躺在桌面或底座上时，夹爪手指被支撑面挡住，停在绳中心上方 1.6–5 mm；对准环节把这段高度差
  记进偏置，下一次目标就落到支撑面以下，找不到姿态。现在求不出姿态时只保留水平方向修正。

**修好后在 lab 上停在的新位置（未修）**：

- very_easy：左手抓住绳腿后抬到等待位（局部 y 0.105 m、z 0.075 m），右手去接近另一条绳腿时，
  两臂间距 0.47 mm，低于 oracle 自己的 1 mm 碰撞检查。
- easier：左手抓绳后把新绳弯往上提（`fresh_bight_carry`），抓点误差从 14 mm 涨到 23 mm，
  绳被压扁 0.25 s、体积比 −0.075，episode 以 `connection_or_volume_invalid` 结束。过环路线要重做。

**对"修改前后比较完成效果"的影响**：目前两档都没有成功的基线执行，所以修改前后无法直接比较
"是否完成"。可比较的只有两类：

- 步时和建场景耗时（两档都能测）；
- 同一段动作序列下的物理几何指标。用上面两档已提交的 99 / 195 个动作作为固定动作序列，
  在新旧设置下各回放一次，比较抓持跟随、绳最小非相邻中心线间距、桌面间隙、拉伸和翻转四面体
  （knot K2 的同一套指标）。

任务完成率和 Harbor 评分的前后比较，只能在 oracle 修好之后补做。

## very_easy 右臂接近时两臂过近（交接第 6 节的新停点）

**场景**：左手已经夹住左侧绳腿，并抬到等待位（局部 y 0.105 m、z 约 0.08 m），夹爪竖直朝下；
右手要从 home 出发，移到右侧绳腿（局部 y −0.066 m）上方 6 cm 的接近点。两只夹爪的目标点 x 相同
（0.13 m），y 方向相距 17 cm。

**oracle 怎么检查**：对每一行下发的关节目标做 Genesis 正运动学，算左右臂所有碰撞网格之间的最近距离，
低于 1 mm 就拒绝这一行（`topogym/planning/knot_untying/kinematics.py` `KnotIK.check`）。lab 上这一行是 0.47 mm。
评分规则里没有"两臂不许接触"；只有接触力持续 0.5 s 不低于 20 N 且驱动接近上限才记强行施力事件。

**原因（MuJoCo 名义路线复算，不含绳的物理）**：右臂 6 个关节按每步 ≤ 0.039 rad 同时插值，路线中段
（41 步中的第 33–35 步）右夹爪座从左夹爪座旁边扫过，MuJoCo 碰撞几何下最多重叠 3.06 mm。之前的
运动学检查（`runs/test_results/orbits_v18_20261006_01/kinematic_contact_route.json`）只查路线端点，所以判通过。
Genesis 与 MuJoCo 的碰撞几何不同，所以 lab 得到 0.47 mm 而不是重叠；两者都说明中段扫得太近。

**是否构成问题**：是。下发值只差 0.47 mm，而实际关节在负载下会偏离下发值（oracle 的抓取偏置修正
上限达 25 mm），真碰上时右夹爪会撞到正夹着绳的左夹爪，摩擦抓持可能被撞松。

**oracle 内可改**（MuJoCo 名义路线上试过的顺序）：

| 右臂接近的走法 | 步数 | 两臂最近距离（MuJoCo） |
| --- | --- | --- |
| 现在：6 个关节同时插值 | 41 | −3.06 mm |
| 先转腰和腕，再展肩肘 | 75 | −3.06 mm |
| 先展肩肘，再转腰和腕 | 75 | 0.34 mm |
| **先把三个腕关节转到位，再动腰、肩、肘** | 74 | **19.4 mm** |

建议的改法：接近前按 `topogym/planning/oracle_path.py` 的 `joint_samples` 把整条关节路线细分，
逐点做同一个 `collision_check`；不通过时依次尝试分段顺序（先腕后其余等），都不行再报错。
复算脚本：会话临时目录 `inter_arm_gap.py`（待并入仓库前不作为证据）。

## oracle 时长基线（10-06 本机 Harbor 首轮，两档都没跑完）

两次都是 merged-v18 候选、本机 RTX 4090（共享）、旧物理设置（2.5 ms × 10、ε = 1 mm/s）。
oracle 没跑完，所以没有"完整一次"的时长，只能给每步速率。归档：
`runs/test_results/orbits_speedup_20261006/oracle_timing_baseline.json`。

| 档位 | 停在第几步（仿真时间） | 建场景 | oracle 实时执行 | 每步（实时，含 oracle 自身检查） | 评分回放 | 每步（回放，含一遍录像） | trial 总墙钟 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| very_easy | 99（2.475 s） | 136 s | 697.5 s | 7.05 s | 2 遍 × 179 步，1604.2 s | 4.48 s | 43.5 min |
| easier | 195（4.875 s） | 169 s | 822.3 s | 4.22 s | 2 遍 × 275 步，1710.6 s | 3.11 s | 48.6 min |

- 回放步数 = oracle 步数 + 80 步保持。实时与回放之差就是 oracle 自身的开销（IK、碰撞检查、
  候选姿态搜索）：very_easy 前 99 步全在搜抓取姿态，所以开销占比高。
- lab 上的对应数（交接第 6 节）：实时 7.8 s/步，回放（纯物理）3.7–5.2 s/步。
- 完整一次的推算（交接第 6 节，very_easy 约 2500–3300 步）：按本机速率，实时 4.9–6.5 h，每遍回放
  3.1–4.1 h。规则上限 72 min。

## 计划

1. **冻结基线**：记录两档当前 `instance.json` 物理段、实例哈希；本机按 TOPOGYM_SPEEDUP_RECORD 的
   方法（新容器、独占 GPU、5 步手臂摆动取中位数）测两档步时和建场景耗时；另测上述两段固定动作
   序列的回放墙钟时间和几何指标。原 Harbor 结果目录只读保留。
2. **K2 + 10 mm/s 逐档试验**：运行时覆盖 K2 并去掉 1 mm/s 覆盖，两档各重新沉降初态，跑 10-05 的七项初态检查 + 末尾 0.5 s 速度诊断；
   两段固定动作序列做新旧几何对比。为分开两项改动的影响，另跑一次"只改 10 mm/s、时间步不变"。任一档不通过，记录原因再决定调参或换候选。
3. **修 very_easy / easier oracle**：首轮两处失败已由 `79c21d1f6` 修复；接着处理 lab 上的新停点
   （very_easy 两臂间距、easier 过环路线），做到本地原生 `task_success`，再走 Harbor privileged / standard。
   同时压缩 oracle 每步的自身检查开销（实时与回放每步差 1–2.6 s）。
4. **固化**：把选定设置写入 `below_easy.py`（只影响两档），重做冻结初态、重建镜像，跑 v18 确定性回放。
5. **收口**：填满下面的逐档表，同步任务页与 `current_zh.md`。

## 逐档状态

"步时"均指每控制步（25 ms 仿真时间）的墙钟中位数，测法同 TOPOGYM_SPEEDUP_RECORD；写明主机。

| 档位 | 物理设置 | 基线步时 | 新设置步时 | 初态检查（新） | 几何对比 | 本地 oracle | Harbor priv / std | 72 min 估算 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| very_easy | 2.5 ms×10, eps 1 mm/s → 目标 K2, eps 10 mm/s | 回放 4.48 s（本机，含录像） | — | — | — | 首轮失败已修；lab 新停点：两臂间距 | 0 / 未运行 | 推算 4.9–6.5 h（实时） |
| easier | 2.5 ms×10, eps 1 mm/s → 目标 K2, eps 10 mm/s | 回放 3.11 s（本机，含录像） | — | — | — | 首轮失败已修；lab 新停点：过环时抓滑、绳被压扁 | 0 / 未运行 | — |

easy / medium / hard 不在范围内（不改、不测；参考值：lab v18 easy 2.50 s/步，无 oracle）。

## 跟进日志

| 日期 | 事项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 2026-10-06 | 建立本页；汇总交接材料与 v18 Harbor 首轮 | very_easy / easier privileged 均 0 分（oracle 早期报错），原三档无 oracle | `runs/test_results/orbits_v18_20261006_01/harbor_goal01/` |
| 2026-10-06 | 用户决定：原三档不动；两档摩擦正则化速度回到 10 mm/s | 范围缩为两档；10 mm/s 终态能否静止列为待验风险 | 本页"摩擦正则化速度"节 |
| 2026-10-06 | 用户定初态口径：允许慢速滑动，只要求绳穿环关系稳定、绳头不滑脱 | 初态检查改看拓扑与绳头到开口距离，不看绳速 | 同上 |
| 2026-10-06 | 讨论过"原地解开即成功"的判据改法，用户确认终态判据不变：绳圈和木柄整体进入目标区、与环和柱完全脱开，速度 ≤ 1 mm/s 持续 0.5 s | 判据不改；10 mm/s 下终态能否在桌上静止仍是待验风险 | `topogym/tasks/orbits/common.py:198` |
| 2026-10-06 | 核对目标区能否保证"已与器具脱开"；目标区高度是否要降 | 能保证：绳全部顶点与木柄在凸长方体目标区内，器具全在分界线另一侧（间隔 ≥ 30 mm），绳圈不可能仍套柱或穿环，与速度上限无关。两档目标区实测 0.40 × 0.40 m、高度桌面 −1 mm 至 +150 mm；用户决定高度不改 | `topogym/utils/geometry/regions.py:53`、`topogym/tasks/placement.py` `choose_region` |
| 2026-10-06 | 用户决定：两档终态线速度上限放宽到 10 mm/s | 待实施，与物理修订一起改 | 本页"终态"条 |
| 2026-10-06 | 读交接第 6 节；归档首轮时长 | 首轮两处失败已修并合入 `2f3233023`；lab 新停点见"当前 oracle 覆盖"；本机实时 7.05 / 4.22 s/步，回放 4.48 / 3.11 s/步 | `runs/test_results/orbits_speedup_20261006/oracle_timing_baseline.json` |
| 2026-10-06 | 查谁在写 Orbits oracle；分析 very_easy 两臂过近 | 另一会话的 below-easy 跟进页把 Orbits 标为"暂缓，先做加速"，无人在写；两臂过近是右臂关节同时插值时中段扫过左夹爪，改为先转腕再动其余关节在名义路线上拉开到 19.4 mm | 本页"very_easy 右臂接近"节 |
| 2026-10-06 | 用当前 HEAD 构建 v18 镜像 `topogym-below-easy:v18-20261006-orbits01`，跑 very_easy privileged | 进行中 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_01/` |
