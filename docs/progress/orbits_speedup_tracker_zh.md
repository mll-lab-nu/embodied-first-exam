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
- very_easy / easier 另设摩擦正则化速度 `contact_eps_velocity` 1 mm/s（物理身份 10-07 起为
  `below_easy_v3_thin_base_friction1mm_v1`，此前 `below_easy_v2_fem_soft50_friction1mm_v1`）；easy / medium / hard 仍用默认 10 mm/s。
- 10-07 起 very_easy / easier 的木底座厚 2 mm（原 20.4 mm），长宽、柱、球头高度不变（见跟进日志 10-07）。

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

## 两档解法的拓扑（无限球模型，`topogym/planning/orbits/invariant.py`）

模型：去掉球头，球头柱 P0 向上无限延伸；环 k 由柱 Pk 托着，各柱向下穿过桌面。绳圈只有在越过球头
（穿过 P0 的向上延伸）时类别才变，每越过一次增减一个球字母 `b`。

| 绳圈 | 字（循环约化） | 球字母数 |
| --- | --- | --- |
| very_easy 初始绳形 | `b'` | 1 |
| easier 初始绳形 | `b' m1 b m1'` | 2 |
| easier：只绕托环支柱 P1、在环下方的小圈 | `m1 b' m1' b`（初始字的反向） | 2 |
| easier：绕球头柱的小圈（环下 50 mm 或环上 100 mm） | `b` | 1 |
| easier：绕整个环和两柱的大圈（环下 50 mm 或环上 100 mm） | `b` | 1 |

easier 布局：P0（带球）x = −0.0476 m，穿在环孔内；环心 x = −0.0289 m、中线半径 76.5 mm、管半径 6.8 mm，
由 P1（x = +0.0476 m）在外缘托住；环面高 85 mm，环顶到球底竖直缝 17.85 mm；球头柱轴线到环内缘最近 51 mm。

结论：

- easier 初态等价于"绳圈套在托环支柱 P1 上，被环挡住"，至少要越过球头两次。
- 用户 10-06 的思路成立：第一次从环与球头柱之间的缝把绳弯穿上去、越过球头套到柱上，类别变为 `b`；
  `b` 与"包住整个环的大圈"同类，绳圈可扩张到环外，再整体越过球头取下（第二次）。
- 现有 easier oracle（`peel_ring`）第一次过球头与此相同，第二次是把绳从环孔内沿球头柱往上提；用户的
  外绕路线避免把绳再从窄缝穿回。外绕需要绳圈够长：包住环的圈半径约 0.10 m，周长约 0.63 m；easier
  绳长 0.665 m（另有木柄）。"加长绳圈／缩小木环"是场景改动，须用户批准并重新冻结实例。
- very_easy 现有 oracle 已是"双手各抓绳圈一侧、一起抬过球头"的路线，只是两手依次抓取。

## oracle 时长基线（10-06 本机 Harbor 首轮，两档都没跑完）

两次都是 merged-v18 候选、本机 RTX 4090（共享）、旧物理设置（2.5 ms × 10、ε = 1 mm/s）。
oracle 没跑完，所以没有"完整一次"的时长，只能给每步速率。归档：
`runs/test_results/orbits_speedup_20261006/oracle_timing_baseline.json`。

| 档位 | 停在第几步（仿真时间） | 建场景 | oracle 实时执行 | 每步（实时，含 oracle 自身检查） | 评分回放 | 每步（回放，含一遍录像） | trial 总墙钟 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| very_easy | 99（2.475 s） | 136 s | 697.5 s | 7.05 s | 2 遍 × 179 步，1604.2 s | 4.48 s | 43.5 min |
| easier | 195（4.875 s） | 169 s | 822.3 s | 4.22 s | 2 遍 × 275 步，1710.6 s | 3.11 s | 48.6 min |
| very_easy（HEAD `2f3233023` 镜像，含 lab 两处修复） | 429（10.725 s），右臂接近两臂间距 0.444 mm | 141 s | 2408.7 s | 5.61 s | 2 遍 × 509 步，3580.5 s | 3.52 s | 105.1 min |

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
| 2026-10-06 | 修 very_easy 右臂接近：接近前预演每一行并做碰撞检查，不通过时依次试分段顺序（先腕等） | `topogym/planning/orbits/native_session.py` `reach_checked`；新增回归测试，`test-orbits-native-oracle.py` 9 项、`test-harbor-below-easy.py` 6 项、`test-below-easy-ik-candidates.py` 19 项通过；尚未实跑 | 本页"very_easy 右臂接近"节 |
| 2026-10-06 | 本机 HEAD 镜像复现 very_easy 停点 | 第 429 行（仿真 10.73 s）右臂接近被拒，inter_arm 0.444 mm；左手抓取、试提、抬到等待位均通过 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_01/` |
| 2026-10-06 | 用拓扑不变量检验用户的 easier 思路 | 成立（见"两档解法的拓扑"节） | 同上 |
| 2026-10-06 | very_easy HEAD 镜像 Harbor 评分结束 | privileged 0 分（第 429 行停在右臂接近），standard 因缺 privileged 成功轨迹未跑；确定性 1；实时 5.61 s/步、回放 3.52 s/步 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_01/`、`oracle_timing_baseline.json` |
| 2026-10-06 | 方案 B（加宽绕柱绳弯、双手柱后撑开、往前越过球头）可达性检查 | 解开阶段各点可达；解开后从器具上方搬到目标区需提到 0.53 m，不可达（误差 23–33 mm、41°）；提出 B2（器具转 180° 让木柄朝目标区）待用户定 | 会话临时目录 `reach_b.py` |
| 2026-10-06 | 用户改动作：一只手抓一边拉开停住，另一只手再抓另一边拉开，两手都抓住后做反向套圈 | 发现原等待位（离柱 0.13 m、±0.105 m）已把绕柱的 0.35 m 绳拉直（余量约 −0.01 m）；改为离柱 0.06 m、±0.12 m（余量约 +0.055 m，两手相距 0.24 m），只改 very_easy，场景不变；名义可达性全部通过（搬运处夹爪倾斜 30°） | `native_session.py` `grasp_legs`；会话临时目录 `spread.py`、`reach_b.py` |
| 2026-10-06 | 用新动作跑 very_easy Harbor 评分（镜像 `topogym-below-easy:v18-20261006-orbits02`，物理设置未改） | 左手拉开途中滑脱（仿真 7.0→10.8 s，夹爪与抓取点偏差 0.5→42 mm，`Grasp slipped during standoff: left`）。原因：只算了绕柱侧余量，漏了木柄侧；新等待位到木柄孔 0.27 m > 抓取点到木柄的 0.225 m 绳，绳被从指间抽走。0.80 m 绳圈在两手相距 24 cm 时全绳最短需求已超过 0.80 m。同期另一会话的 rope 评分共用 GPU，本次实时约 19 s/步 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_02/` |
| 2026-10-06 | 提出：绳长 0.80→0.95 m，抓取点离两端 0.30 m，先竖直提 4–5 cm 再拉到离柱 0.08 m、±0.12 m | 用户否决加长：绳不要改太长；抓点不合适时可先抓、提离桌面、再沿绳滑到合适位置。停掉第 2 次的评分回放 | — |
| 2026-10-06 | 改为"先提后拉开"，绳长不变（0.80 m） | 抓点离两端 0.18 m（初态 x 0.171 m、±0.061 m，相距 12.3 cm，可直接抓，不需滑动）；每只手抓住后提到离桌 0.10 m、±0.09 m（离木柄孔 0.164 m < 0.18 m，不拖桌面）；两手都抓住后一起到离柱 0.12 m、±0.12 m、高 0.20 m（木柄离桌挂起，绕柱 0.44 m 段余量约 7 cm）；提过球头 0.395 m、搬运 0.41 m；名义可达性全部通过 | 会话临时目录 `plan_c.py`、`reach_b.py`；`native_session.py` `grasp_legs`、`run` |
| 2026-10-06 | 用新动作跑 very_easy Harbor 评分（镜像 `topogym-below-easy:v18-20261006-orbits03`，物理设置未改） | 左手试提失败（`Physical grasp did not follow: left`，仿真 6.83 s）：试提期间全绳最高点一直 0.024 m，没夹住。原因：离两端 0.18 m 处（x 0.171 m）正是绳从底座边缘（x 0.153 m）垂向桌面的斜坡，±12 mm 内高 8–23 mm，手指不能低于底座顶面，停在绳上方。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_03/` |
| 2026-10-06 | 抓点改到离两端 0.15 m（x 0.195 m 桌面上，绳高 3.4–7.6 mm，两点相距 10.4 cm），等待位改为离桌 0.08 m、±0.07 m（离木柄孔约 0.14 m < 0.15 m）；提过球头与搬运高度 0.425 m；名义可达性全部通过 | 第 4 次：左手抓取、试提、提到等待位均通过；右臂接近通过逐行碰撞预演（第 1 次的两臂过近已解决）；右手在桌面 0.15 m 处试提失败（`Physical grasp did not follow: right`，仿真 18.7 s，偏差 2.6→11 mm，绳没上来）。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_04/` |
| 2026-10-07 | 抓持观察（第 4 次 trace） | 绳躺在支撑面上时，手指不能低于支撑面、只夹到绳上半部：左手提起时先在指间滑约 5 mm 才带动绳；之后静止抓持仍以约 0.2 mm/s 蠕动（ε = 1 mm/s 下）。各次抓取：底座上 0.225 m 2/2 成功，桌面 0.15 m 1/2，底座边缘斜坡 0/1。**ε 改回 10 mm/s 预计会让摩擦抓持滑得更快，此前"两档 ε 回 10 mm/s"的决定需要重新评估** | 同上 |
| 2026-10-07 | 第 5 次：左手 0.15 m（桌面）、右手 0.225 m（底座）；拉开点改为离柱 0.10 m、±0.12 m（绕柱 0.425 m 段余量约 7.5 cm）；拉开时的滑脱检查改为相对拉开前的增量 ≤ 8 mm；提过球头 0.39 m、搬运 0.456 m，名义可达 | 左手 0.15 m 抓取、试提通过；右手在底座 0.225 m 处找不到候选姿态（`No collision-free pinch and pregrasp for right at material 0.225`）：IK 候选的关节路径预演中右夹爪座擦到停在 x 0.195 m、+0.07 m、0.08 m 的左夹爪座（重叠 0.05 mm），精确解未收敛。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_05/`（`ik_candidates.json`） |
| 2026-10-07 | 第 6 次：very_easy 改为右手先抓（底座 0.225 m），提到离桌 0.12 m、−0.07 m 等待（离木柄孔 0.21 m < 0.225 m）；左手再抓桌面 0.15 m | 右手（底座 0.225 m）抓取、试提、提到 0.12 m 等待均通过；左手接近四种关节顺序都不通过（`No collision-free joint ordering in approach`）。MuJoCo 复算：竖直夹爪的夹爪座在指尖上方约 10 cm，两手指尖分在窄绳圈两侧时，两夹爪座都挤在绳圈正上方，终点间距只有 5–24 mm、路径中重叠。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_06/`；会话临时目录 `left_sweep.py` |
| 2026-10-07 | 第 7 次：先抓的手到等待位后，以指尖为轴往自己一侧倾斜 45°（MuJoCo 名义路径最近间距 6.6 → 58 mm，左手再倾 15° 时 93 mm）；`grasp_one` 改为按"偏好朝向、倾角从小到大"逐个预演整条接近路径，取第一个畅通的（原来只查端点、取倾角最小）。新增回归测试 1 项，`test-orbits-native-oracle.py` 10 项通过，回退到 HEAD 时两项新测试失败 | 首次两手都抓住并提起：右手抓取、试提、等待、外倾 45° 均通过（偏差 2–3.5 mm），左手按路径选姿态后接近、抓取、试提、等待均通过。一起拉开（往 x 0.10 m、±0.12 m、0.20 m）时，木柄被两段绳在桌面上拖了约 13 cm（绳最远端 x 0.293→0.165 m），卡在底座边缘（x 0.153 m）；27.0 s 左手偏差 0.2 s 内 5.7→122 mm，绳整个脱出（`Grasp slipped while opening the loop: left`，仿真 29.4 s）。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_07/` |
| 2026-10-07 | 用户决定：very_easy 与 easier 都改成薄底座（第 7 次木柄被拖到 20.4 mm 底座边缘卡住） | `below_easy.py` 底座厚 2 mm（缩放前 `.002/.85`），修订号改为 `below_easy_v3_thin_base_friction1mm_v1`，`variation_records.py` 两条同步；新增尺寸断言先失败后通过；`test-orbits-below-easy.py` 14 项、`test-orbits-native-oracle.py` 10 项、`test-harbor-below-easy.py` 6 项、`test-terminal-defaults.py` 7 项通过。初态里底座边缘的绳斜坡消失（离端 0.18 m 处高 3.6–5.4 mm，原 8–23 mm） | `topogym/tasks/orbits/below_easy.py`、`topogym/config/variation_records.py`、`ci_checks/test-orbits-below-easy.py` |
| 2026-10-07 | 第 8 次：薄底座 + 第 7 次的全部动作（右手先抓、外倾 45°、按路径选姿态、先提后拉开） | 新初态（哈希 `5892ec66be0807fa`）。右手抓取（偏差 0.28 mm）、试提、提到等待位通过；外倾 45° 时右前臂滚转停在 +π 限位（3.142 rad），IK 换到另一组解，前臂滚转从 3.14 一路走到 1.3 以下、腕关节翻转，夹爪在空中甩动把绳带到 0.2 m 高再甩脱（13.0–13.6 s，偏差 1.2→245 mm，`Grasp slipped while leaning out: right`）。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_08/` |
| 2026-10-07 | 第 9 次：抓取候选优先选前臂滚转和腕部旋转离限位 ≥ 0.8 rad 的（两指对称，换手指朝向通常就有余量）；`move()` 中相邻插值点 IK 解任一关节相差 > 0.5 rad 即报错、不下发。新增 2 项回归测试，撤掉这两处时都失败，恢复后 `test-orbits-native-oracle.py` 12 项、`test-harbor-below-easy.py` 6 项、`test-orbits-below-easy.py` 14 项通过 | 右手抓取、试提、等待、外倾 45° 均通过（第 8 次的限位问题消失）；左手接近、对准、夹紧通过，在桌面离终点 0.15 m 处试提失败（`Physical grasp did not follow: left`，仿真 20.9 s，偏差 2.2→7.6 mm，绳没上来）。该点绳正往木柄孔爬升（±12 mm 内高 3.4–7.8 mm）。桌面平躺绳的夹取累计 3 成 2 败。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_09/` |
| 2026-10-07 | 第 10 次：左手改抓离终点 0.18 m（薄底座后平，3.6–5.4 mm；等待位离木柄孔约 0.16 m < 0.18 m；绕柱 0.395 m 段拉开余量约 4.5 cm）；试提没带起绳时（新异常类型 `GraspNotFollowing`）张开、上抬 6 cm、清零对准偏置后重抓一次。新增 1 项回归测试（先失败后通过），`test-orbits-native-oracle.py` 13 项、`test-harbor-below-easy.py` 6 项通过 | 右手全部通过；左手第一次试提没带起绳，重抓机制触发后第二次成功（两手都抓住）。左手提往等待位途中 episode 结束（仿真 32.03 s）：`connection_or_volume_invalid`，绳被压扁 0.25 s（体积单元翻转，最小体积比 −0.094）。推测：左手改抓 0.18 m 后绕柱段只剩 0.395 m，右手停在 0.12 m、左手提到 0.08 m 时三段直线距离约 0.415 m，绕柱段被拉紧；压扁位置未确认（评分回放约需 2.5–3 h，GPU 与他人实验共用，按用户决定停掉、未拿到录像） | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_10/` |
| 2026-10-07 | 第 11 次（用户思路）：拉开时两手移到柱子两侧（离柱 0 m、±0.12 m、离桌 0.08 m），绳圈以柱为中心张开，绕柱段需约 0.30 m（绳 0.395 m，余量约 9 cm），木柄被两手拖向器具约 15 cm（底座已薄）；两手抓住后都只停在抓取点上方 6 cm。名义可达性通过（`runs/test_results/orbits_speedup_20261006/tools/reach_check.py`），`test-orbits-native-oracle.py` 13 项通过 | 右手抓取、等待、外倾，左手接近（右手停 6 cm 未挡路）、一次夹住、提到等待位均通过（第 10 次的压绳未再出现）。两手在离桌 8 cm 水平移向柱两侧时，木柄与绳贴桌被拖，绳持续从指间抽出：左手偏差 1.2→45 mm、右手 8→19 mm（`Grasp slipped while opening the loop: right`，仿真 28.0 s）。对比第 7 次：边移边升到 20 cm，木柄被拖 13 cm 时两手只滑约 0.5 mm。已停掉评分回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_11/` |
| 2026-10-07 | 滑脱归因（用户问：动作还是材料） | Orbits 的绳与 knot 同材料（`rope_fem_parameters`：E 5e4 Pa、μ 0.3），都是纯摩擦抓持；但 Orbits 绳半径 1.87 mm（直径 3.7 mm）、夹紧开口 2.8 mm（挤压 0.9 mm，约 25%），knot 绳半径 4 mm、开口 5 mm（挤压 3 mm，约 37%），knot 的 oracle 已评满分。rope_threading 原三档用 E 5e6 Pa（硬 100 倍）加 `ipc_soft_band_v1` 辅助抓持；below-easy 的 rope、blanket 已按 D1 允许辅助抓持。Orbits 原三档无机器人 oracle，同材料同直径，预计同样问题。结论：夹持能力主要受细软绳 + 纯摩擦限制，动作决定是否超出（只在要拖动负载时滑） | `topogym/assets/materials.py:36-40`、`topogym/planning/knot_untying/cli.py:25`、`docs/progress/below_easy_oracle_tracker_zh.md` D1/D2 |
| 2026-10-07 | 用户与团队讨论决定：Orbits 的绳由 FEM+IPC 改为刚体链（参考 fiber_bundling），放弃 FEM+IPC；本页范围只换 very_easy / easier，原三档由另一位同事同样改成刚体链 | 待写方案确认后实施；共用文件（`topogym/tasks/orbits/common.py`、`topogym/assets/geometry/orbits.py`）只做向后兼容的小改动，主体放两档专用文件，避免与同事冲突 | — |
| 2026-10-07 | 用户确认：纯摩擦抓持先试；粗细在"好抓"与"像绳"之间取平衡；Harbor 模板只加按物理模型的分支 | — | — |
| 2026-10-07 | 刚体链第 1 步（物理验证）。实现：`topogym/assets/geometry/orbits_chain.py`（新）把现有初始绳形截去穿入木柄孔的两端、按等弧长切节，写出"木柄（自由根刚体）+ 胶囊链节（球关节）+ `<connect>` 把末节尖端连到第二个木柄孔"的单个 MJCF；链节与木柄互不碰撞，与器具、桌面、机器人及彼此碰撞。`below_easy.py` 改为刚体链声明（`physics_model = rigid_articulated`，修订号 `below_easy_v4_rigid_chain_v1`），判据为全部链节覆盖点与木柄在目标区内、链节与木柄线速度 ≤ 10 mm/s、木柄角速度 ≤ 0.02 rad/s、末节与第二孔残差 ≤ 2 mm（超出判 `connection_invalid`）。CPU 双精度、4 子步静置探针：15 mm 链节（52 节）0.51 s/步、抖动 7 mm/s；关自碰撞 0.48 s；2 子步 0.27 s；**20 mm 链节（39 节）0.26–0.28 s/步、闭合残差 ≤ 0.23 mm**；关节阻尼 2e-5 时 easier 第二节振荡到 31 mm/s 且增长，**1e-4** 两档 2.5–2.8 s 内降到 3 mm/s 以下（木柄下垂段像摆一样晃，最终停住）。定为直径 6 mm、20 mm 链节、阻尼 1e-4、保留自碰撞与 4 子步。外观接近连续绳；MJCF 里的金黄色未在渲染中生效（待处理，仅外观） | `runs/test_results/orbits_speedup_20261006/chain_probe_*`；工具 `runs/test_results/orbits_speedup_20261006/tools/chain_env_probe.py`、`chain_mujoco_check.py` |
| 2026-10-07 | 刚体链接入：Harbor 模板 `simulator_config()` 中，族配置带 IPC 参数而任务类不是 `fem_ipc` 时改用 CPU 双精度、`use_contact_island False`、默认 4 子步、建实例前沉降 1200 步（3 s），去掉 IPC 参数（easy 等原三档配置不变，已核对）；`scripts/topogym_merge_candidate.py` 同样按任务类物理模型决定是否导出 IPC 状态；oracle 改为从链节位姿读绳形、按链弧长定位、夹爪合拢到直径减 1.5 mm（4.5 mm）；任务说明对刚体链两档改为 10 mm/s 与"末节连在第二孔 2 mm 内"；目标区高度由 0.15 m 变为 0.17 m（目标件只剩一个实体 `cord`，`choose_region` 默认高度规则所致）。测试：`test-orbits-below-easy.py` 14 项（按刚体链改写）、`test-orbits-native-oracle.py` 13 项、`test-harbor-below-easy.py` 6 项、`test-terminal-defaults.py` 7 项通过；`test-task-goal-descriptions.py` 6 项 interlocked_claws 失败，HEAD 版本同样失败（原有） | `harbor_templates/topogym/common/rcb_topogym.py`、`scripts/topogym_merge_candidate.py`、`topogym/planning/orbits/native_session.py`、`topogym/tasks/goal_description.py`、`topogym/config/variation_records.py`、`ci_checks/test-orbits-below-easy.py` |
| 2026-10-07 | 第 12 次：刚体链 very_easy 首次 Harbor 评分（动作同第 11 次） | 刚体链上纯摩擦抓取：右手、左手抓取、试提、等待、外倾全部一次通过；oracle 实时 0.44 s/步（IPC 时 5.6 s/步，约快 13 倍），1099 行约 8 分钟。拉开（离桌 8 cm 水平移向柱两侧）时左手偏差 2.3→18 mm、右手 5.3→11.5 mm（有限元绳为 1.2→45 mm），判滑脱；右手静持也有约 0.4 mm/s 蠕动。已停回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_12/` |
| 2026-10-07 | 第 13 次：夹爪合拢改为直径减 3 mm（3.0 mm）；拉开同时升到 16 cm | 拉开时左手偏差 2.4→13.1 mm（+10.7 mm，仍超 8 mm），右手 4.8→6.4 后降到 0.8–1.5 mm（说明该"偏差"含链节绕夹持点转动，不全是滑动）；安全统计只有强行施力（0 次、最大压力 0）与桌面保护，无夹持深度复查项。已停回放 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_13/` |
| 2026-10-07 | 第 14 次：拉开滑脱判定线 8→20 mm（刚体链节绕夹持点转动也计入偏差），看后续提过球头、搬运、放置能否走通 | 首次越过"拉开"（左手偏差增至约 13 mm、未超 20 mm）。往高处提越过球头时（`lift_over_ball`，仿真 32–33 s）右手偏差 1.9→10 mm，随后 0.2 s 内两手偏差跳到 16–34 cm，刚体求解接触力出现非有限值，Env 判仿真故障。推断：绳弯贴柱上滑到球下时须张开约 5 cm 才能绕过球的最宽处，两手仍按 ±0.12 m 上提、未让出长度，绳被拉死卡在球下 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_14/` |
| 2026-10-07 | 第 15 次：very_easy 往上提时两手同时从 ±0.12 m 收到 ±0.05 m（约让出 7 cm 绳长） | 收手过程中偏差稳定（右 2.5–5 mm、左 15–18.5 mm），34.0 s 左手突然脱手（18.5 mm→32 cm），链节最快 1.48 m/s，闭合残差 2.2 mm > 2 mm，任务判 `connection_invalid` 失败。判断：贴柱上滑的绳弯在球下需张开，收手让出的长度不够，绳在高张力下卡住后弹开 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_15/` |
| 2026-10-07 | easier 第 1 次 | 右手预抓位（绳弯最深点正上方 20 cm）有可行姿态，但从 home 过去的关节路径四种顺序都碰撞（`No collision-free approach for right`）；报错未写碰撞对象。改：报错附直接路径首个碰撞检查结果；右手不行换左手；预抓高度 25 cm。已停回放 | `runs/test_results/orbits_speedup_20261006/harbor_easier_01/` |
| 2026-10-07 | easier 第 2 次（带诊断与换手） | 右手直接路径右手指扫到球头（诊断已输出）；换左手：从环孔上方 25 cm 竖直下降 10 s 到底后，首次对准偏差超 25 mm（`Excessive contact tracking bias: left`）。原因未定（被环挡住或手指把链推开），下次保留回放录像判断 | `runs/test_results/orbits_speedup_20261006/harbor_easier_02/` |
| 2026-10-07 | very_easy 第 16 次：不再贴柱上提。两手由柱两侧退到柱后 6 cm、撑开到 ±0.15 m（柱后那股绳悬空离柱），升到 0.30 m（下垂约 11 cm，最低点高过球顶 4 cm），再前移到柱前 6 cm 带过球顶；名义可达性通过 | 退到柱后正常（右 2–4.5 mm）；在柱后升高时右手偏差 4.5→14.6 mm，34.3 s 脱手，链节 2.4 m/s，闭合残差 2.2 mm，判 `connection_invalid`。推测木柄被两段绳拖到柱前卡住、张力骤增 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_16/` |
| 2026-10-07 | 用户问能否撑成 O 形无接触套出；解释两点悬持的软绳必落在过两手的竖直面内，需第三支点或抗弯刚度。用户提出加刚度（像充电线），要求扫描绳长 + 刚度 | Genesis 球关节弹簧把关节拉回初态姿态（`forward_dynamics.py` 中 刚度 ×（qpos − qpos0）），可用 | — |
| 2026-10-07 | MuJoCo 两点提起扫描（两焊接夹持点在 oracle 原抓取点，竖直 35 cm 后水平 20 cm；首轮脚本焊接未生效，结果作废，修正后重扫） | 不加刚度的所有组合都卡在柱上（夹持点被拉开 20–25 cm、仍套柱）。有刚度时保持张开、无接触脱出：绳弯 35 mm 时 0.80 m + 0.03 N·m/rad 余 7.0 mm；**0.90 m + 0.1 N·m/rad 余 9.0 mm（最大）**；1.00 m + 0.3 N·m/rad 余 7.3 mm；绳弯 30 mm 时余量更小。绳越长所需刚度越大 | 工具 `runs/test_results/orbits_speedup_20261006/tools/stiff_lift_mujoco.py`；`stiff_lift_04/` |
| 2026-10-07 | 用户要求用辅助抓持避免滑脱。`contact_weld_v1` 支持多目标：`common.py` 新增 `recommended_grasp_assist()`，刚体链两档把每节链（中点、半径半节长加 5 mm）声明为可焊目标（very_easy 39 个、easier 52 个），原三档返回空；Harbor 模板 orbits 族 `grasp_assist="recommended"`（easy 实测仍为 none）；oracle 允许 `contact_weld_v1`。`below_easy.py` 新增 `chain_roots()` 供声明与推荐共用。`test-orbits-below-easy.py` 14、`test-orbits-native-oracle.py` 13、`test-harbor-below-easy.py` 6 项通过 | `topogym/tasks/orbits/common.py`、`harbor_templates/topogym/common/rcb_topogym.py`、`topogym/planning/orbits/native_session.py` |
| 2026-10-07 | very_easy 第 17 次（辅助抓持 + 退到柱后翻过球顶）、easier 第 3 次（辅助抓持 + 穿环孔下抓）；刚体链回放快，今后不停回放，用录像诊断 | 进行中 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_17/`、`harbor_easier_03/` |
| 2026-10-07 | 待用户定：刚体链闭合残差 > 2 mm 现为瞬时判失败（原有限元绳的连接残差有 0.25 s 持续窗口）；被拉紧后突然松开时残差可能瞬间冲过 2 mm 又恢复 | — | `topogym/tasks/orbits/below_easy.py` `evaluate_goal_region` |
| 2026-10-07 | 用户定：easier 按标准解法（从环与球头柱之间把绳弯穿上去），同意调整尺寸。同一判据（只算环、柱、球，不算指尖所贴的底座）下，原尺寸竖直伸入的最小间隙为 −6.2 / −6.4 / −0.1 mm（全部碰撞）；整个环孔扫描无可行位置。放大到柱距 125 mm、环内径 200 mm 为 +4.5–7.6 mm；**定为柱距 135 mm、环内径 220 mm（外径约 234 mm）、绕支柱绳弯半径 70 mm、底座 360 × 260 mm、木柄 0.42 m、绳长 1.05 m**：绳弯最深点离环内缘 63 mm、离球面 45 mm，名义间隙 10.3 mm；支柱侧环内缘到球面 108 mm（原 68 mm）；初始拓扑仍为 2 个球字母；绳圈宽 0.244 m。实现：`orbits_easier.py` 覆盖几何、`common.py` 绳形表新增 `easier_wide_ring_v1`（只新增键）；尺寸测试先失败后通过。刚体链探针：52 节、0.37 s/步、闭合残差 0.07 mm、3 s 后 2.7 mm/s | 工具 `runs/test_results/orbits_speedup_20261006/tools/easier_resize*.py`；`chain_probe_easier_resized_01/` |
| 2026-10-07 | easier 第 1 次：标准解法 1a——右手从环孔正上方 20 cm 竖直下降，夹绳弯最深处（环孔内最靠近球头柱的链点），竖直提到球顶上方 6 cm；开发阶段在此停止 | 进行中（镜像 `topogym-below-easy:v18-20261007-easier01`） | `runs/test_results/orbits_speedup_20261006/harbor_easier_01/` |
| 2026-10-07 | easier 并行开发（用户同意）。复核用户思路第 1 步"从环与球头柱的缝里把绳弯穿上去"：刚体链初态绕支柱 P1 的绳弯只有第 19 节伸到环孔下方，离环内缘 14 mm、离球头柱 74 mm；MuJoCo 名义检查左右手、7 种倾角、12 种朝向共 152 个可解姿态，竖直穿过环孔下降途中全部碰到环或柱（最好也嵌入 6.3 mm）。提出 A：在环外抓两点提起绳弯、从上方套过球头放低落到球头柱上（拓扑 2→1，第 2 步不变）；B：加大环孔或绳弯后按原思路。待用户定 | 工具 `runs/test_results/orbits_speedup_20261006/tools/easier_geometry.py`、`easier_reach.py` |
| 2026-10-07 | very_easy 第 17 次（辅助抓持 + 退到柱后、升高、前移翻过球顶）结果 | 两手抓取、拉开、退到柱后都正常（闭合残差约 0.5 mm）。柱后升高到 34.4–34.68 s，绳最低点到底座上 108 mm（球底 110 mm）时，闭合残差 0.5→0.6→1.04→2.05 mm，判 `connection_invalid`。机理：两只手提软绳圈时绳圈垂进两手所在的竖直面，木柄那股被拉向柱后、压在柱前侧，顺柱上滑后顶到球底卡住（第 16 次同一机理）。2 mm 上限不是原因：卡住后残差持续增大，放宽只会推迟判失败 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_17/`（`native_trace.json`） |
| 2026-10-07 | easier 第 3 次（辅助抓持）+ 本机复现 | 右手同第 2 次没有无碰撞路径；左手下降后再报 `Excessive contact tracking bias: left`。本机复现：碰撞模型里指令姿态离桌 2.7 mm、判无碰撞，实际夹爪停在离底座 62 mm、y 向被推开 17 mm，即夹爪或手腕实际碰到了环；名义间隙 10.3 mm 被跟踪误差吃掉。待办：再放大环或改用倾斜伸入 | `harbor_easier_03/`；`local_easier_01.log`；工具 `tools/easier_align_debug.py` |
| 2026-10-07 | 用户确认采用抗弯刚度（扫描本就为此而做，我误列为待决定）。落地：每个球关节刚度 0.1 N·m/rad（两档同一种绳）；very_easy 绳弯半径 23.8→35 mm、绳长 0.80→0.90 m（新绳形 `below_easy_stiff_loop_v1`，旧 `below_easy_external_handle_v1` 已无引用并删除）；model_revision `below_easy_v5_stiff_chain_v1`。Genesis 静放 3 s：44 节、各节最大速度 0.03 mm/s、闭合残差 0.08 mm、0.29 s/步。oracle very_easy：抓后只竖直抬 6 cm，删除手腕外倾与拉开绳圈；脱出改为两手竖直升到 0.36 m 再朝木柄方向平移 0.20 m（与扫描同一动作）。`test-orbits-below-easy.py` 14（新增刚度断言）、`test-orbits-native-oracle.py` 13 项通过 | `topogym/tasks/orbits/below_easy.py`、`topogym/assets/geometry/orbits_chain.py`、`topogym/planning/orbits/native_session.py`；`chain_probe_very_easy_stiff_01/`；本机运行 `local_very_easy_stiff_01/` |
| 2026-10-07 | very_easy 硬绳 oracle 本机调试（`tools/local_oracle.py`，开发 Session，不经 Harbor）。第 1 次：右手试提 12 mm 后绳只升 4.4 mm，判 `GraspNotFollowing`；对照（同几何、刚度 0）升 8.3 mm，两者绳与夹爪都只差约 1 mm，即机械臂位置控制在加载后滞后（静止时差 3.7 / 7.6 mm），没有打滑 → 试提门槛 6→3 mm（另一条"绳离夹爪 ≤ 8 mm"不变）。第 2 次：竖直升到 0.36 m 时 IK 不可达 → MuJoCo 扫描：手升到 0.20–0.30 m、平移 0.06–0.20 m 都脱开（余 8.6–9.0 mm），定为 0.25 m + 0.10 m。第 4 次：抬起与平移成功、拓扑判定已脱开；侧移时共享 IK 扫掠检查把未夹的链节当固定障碍（左手指贴着 `link_25`）拒绝所有运动 → orbits oracle 内把绳从该检查中去掉（与有限元时期一致；固定件、桌面、另一臂仍检查）。第 5 次：侧移不可达 → 名义 IK：竖直夹爪过不了固定件中线（缺 13–43 mm），倾斜手腕可以 → 放置改为：降到 0.16 m、侧移与沿固定件搬运用倾斜手腕、目标上方转回竖直再放下（每个抓点落到其初始位置加上"让初始绳圈居中于目标区域"的平移）。**第 6 次：任务原生成功（`episode_end: success`，仿真 83.7 s，3349 控制步）** | `runs/test_results/orbits_speedup_20261006/local_very_easy_stiff_0{1..6}.log`；工具 `local_lift_debug.py`、`stiff_lift_height.py`、`stiff_lift_carry.py`、`reach_beside*.py` |
| 2026-10-07 | 用户给出队友的 Orbits 刚体链标准，要求对齐。已对齐：节长 16.5 mm（队友 23.1 mm 是 linear_scale 1.19 下的值）、直径 3.74 mm（即布局原有绳径）、球关节阻尼 2e-4、armature 1e-6、质量只按每节圆柱段算、摩擦 0.3 / condim 3、木柄密度 700；结构改为木柄为根、两绳眼各长一支、中点 connect（每节坐标仍是绕圈顺序起点，中点后各节的球关节放在胶囊远端，oracle 与判据按名字读绳不变）；辅助抓持区域改为节中点 8 mm 球；1 个子步（模板不再弹出该族的 `solver_substeps: 1`）+ CG 求解器（任务物理选项写 `"CG"`，`genesis_world.py` 转为 Genesis 枚举）；model_revision `below_easy_v6_team_chain_v1`；目标描述改为"两半在中点相接、偏差 ≤ 2 mm"。very_easy 53 节、easier 63 节 | `topogym/assets/geometry/orbits_chain.py`、`topogym/tasks/orbits/below_easy.py`、`common.py`、`harbor_templates/topogym/common/rcb_topogym.py`、`topogym/world/genesis_world.py`、`topogym/tasks/goal_description.py` |
| 2026-10-07 | **唯一不对齐项：抗弯刚度。** 队友用 50 kPa。新链 MuJoCo 两点提起（0.25 m + 0.10 m）：0.05 / 3 / 10 MPa 都卡在球上、中点连接被拉开 24 mm；30 MPa 余 1.0 mm；50 / 100 / 170 MPa 余 7.6 / 8.8 / 8.2 mm，中点连接 ≤ 0.1 mm → 定 **100 MPa（k ≈ 0.058 N·m/rad）**，待用户确认。顺带发现：MuJoCo 里中点两节（非父子）端球重叠会互推 3.6 mm，需要 `<exclude>`；但 Genesis 遇到 `<exclude>` 会用 z3 重写整个实体的 contype/conaffinity，把部分链节解成 0 并载入失败（`KeyError: 'vmesh'`），故 MJCF 不写 exclude（Genesis 自动关掉建模时接触的零件对），只在 MuJoCo 工具里加 | 工具 `tools/team_chain_modulus.py`；`team_chain_modulus_0{4,5,6}/` |
| 2026-10-07 | 新链 Genesis 静放 3 s（1 子步 + CG，本机无队友 CPU 补丁）：53 节、**0.139 s/控制步**（旧链 4 子步 0.29 s）、中点连接 0.001 mm、各节最大速度 0.003 mm/s。测试：`test-orbits-below-easy.py` 14、`test-orbits-native-oracle.py` 14、`test-harbor-below-easy.py` 6 项通过；`test-task-goal-descriptions.py` 仅 HEAD 上已有的 6 项 interlocked_claws 失败 | `chain_probe_very_easy_team_01/`；新链本机 oracle 第 7 次进行中 `local_very_easy_team_07.log` |
| 2026-10-07 | 新链（队友标准 + 100 MPa）very_easy 本机第 7–13 次。第 7 次：默认夹宽"直径 − 3 mm"= 0.74 mm 低于 1 mm 防全闭下限 → 取 max(直径 − 3 mm, 1 mm)。第 8、10 次：抓取、竖直抬起、平移都成功，28.4 s 拓扑判定已脱开；侧移时两只手腕各自朝自身伸出方向倾斜 45°，两手刚性夹着的硬绳圈被拧住，左手焊接以 `relative_pose_error` 松开（oracle 进度新增每只手的辅助抓持状态与松开原因）。两手共用绕 y 轴（两手连线）的倾角不会拧绳，但名义 IK 下左手缺 31–112 mm → 放弃侧移，改为夹爪竖直从固定件正上方越过（`place_over`）。第 11 次：脱开处直接升向 0.32 m 时左臂到可达边缘、抖动扯断焊接 → 升高量按实测最低点（链或木柄比球顶高 2 cm）。第 12 次：实测要 0.295 m（木柄垂得最低，手在 0.25 m 时链最低点已在球顶上 1.6 cm）→ 先在 0.25 m 回退 5 cm（绳弯端过球上方，链最低点需高于球顶 1 cm），再升，高度上限 0.30 m。**第 13 次：整条路线走完（越过、放下、松手、静置 20 s），连接与静止都满足，但绳弯一端出界 15 mm**：按初始形状开环放下偏了约 2.4 cm，区域每边只余 7.5 mm → 松手前加闭环对中（实测链 + 木柄的中心对准区域中心）。第 14 次进行中 | `runs/test_results/orbits_speedup_20261006/local_very_easy_team_{07..14}.log`；工具 `reach_common_tilt.py`、`reach_over.py` |
| 2026-10-07 | **very_easy Harbor 第 18 次（新链 + 100 MPa + 新 oracle）通过**：`success 1`、`final_reward 1.0`、`deterministic 1`（两遍回放一致）、3020 控制步、仿真 75.5 s；oracle 实耗约 415 s（约 0.14 s/控制步，有限元 IPC 时期 3.5–5.6 s/步）；verifier 回放 608 s；无 forcing、无失稳 | `runs/test_results/orbits_speedup_20261006/harbor_very_easy_18/`，镜像 `topogym-below-easy:v18-20261007-orbits18` |
| 2026-10-07 | 用户要求在 MuJoCo 里做 easier 标准动作参考运行，给出支持标准动作的环与柱参数。工具 `tools/easier_standard_mujoco.py`：焊接点驱动链节（不模拟机械臂），队友标准链 + 100 MPa；步骤：① 焊绳弯最深节竖直提过环孔到球顶上 4 cm；② 移过球头柱、放低到球与环之间、松开（期望 1 个球字母）；③ 焊绳圈两侧（25% / 75% 处）撑开到环外缘外 5 cm、先抬过环面再抬过球顶、朝木柄方向移开 0.45 m（期望 0 个）。结果：现有尺寸 + 1.05 m 绳拓扑能走通但抬过环时被挂、中点连接拉开 7.3 mm；抓点 15% / 35% 更差；绳长是关键（1.15 m 刚好 2.05 mm，1.25 m 0.72 mm）；环与柱距同加 3 cm 反而更难绕过（1.25 / 1.35 m 绳 11–14 mm）；只加柱距 +2/+3 cm、1.25 m 绳在移开时被球扫到（11.7 mm）→ 移开高度从球顶上 6 cm 改 10 cm 后，**现有 / 柱距 +2 / 柱距 +3 cm 三种都干净脱开，中点连接 ≤ 0.72 mm**，环与柱距同加 3 cm + 1.35 m 仍失败（3.25 mm） | `easier_standard_*/`（每步示意图 + `report.json`） |
| 2026-10-07 | 机械臂伸入环孔的名义间隙（`tools/easier_ring_margin.py`、`easier_spacing_margin.py`、`easier_spacing_only_margin.py`）：只加环半径 10→17 mm 封顶；只加柱距 +2/+3/+4 cm 为 18.9/19.6/19.6 mm 封顶；两者同加 3 cm 为 28.8 mm（但第 ③ 步绕不过去）。空隙模型：球面到环靠支柱一侧内缘的距离 ≈ 柱距 − 球半径 − 环管半径，夹爪约占 88 mm。第 ③ 步各手位（撑开、抬过环、0.25 m 过球、移开到 +0.45 m）在柱距 +3 cm 下名义可达，需倾斜手腕 30–45°（`tools/easier_step3_reach.py`）。**建议配置：柱距 135→165 mm，环不变（内径 220 mm），绳长 1.05→1.25 m（75 节），底座不变**；伸入间隙 19.6 mm（现 10.0 mm；目标 25 mm 未标定），待用户定 | — |
| 2026-10-07 | 用户定：easier 采用柱距 165 mm、环不变、绳长 1.25 m（绳形 `easier_ring_hole_v2`，旧 `easier_wide_ring_v1` 删除）；绳刚度用队友的 50 kPa。已改：`orbits_easier.py`、`common.py`、`below_easy.py`（`YOUNG_MODULUS_PA = 5e4`，model_revision `below_easy_v7_team_chain_50kpa_v1`）、`variation_records.py`、尺寸测试（14 项通过）。easier 75 节，绳圈加木柄跨 0.44 × 0.42 m，大于目标区域 0.40 m 边长，放置时须转约 45° | — |
| 2026-10-07 | 50 kPa 下的验证：easier MuJoCo 标准动作参考运行，①② 正常（2→1 个球字母，中点连接 ≤ 0.5 mm），③ 移开时软绳圈垂在两手竖直面内、挂住球头柱与环，中点连接拉开 19.2 mm；刚度扫描：3 / 10 / 30 MPa 移开时 19.6 / 11.6 / 11.2 mm，均失败；100 MPa（此前同几何）0.51 mm 成功。very_easy：50 kPa 下 MuJoCo 两点提起卡在球上（24 mm，见上），即 Harbor 第 18 次通过的解法在 50 kPa 下不成立。待用户定：两档用约 100 MPa 的硬绳（与队友只差刚度一项），或保留 50 kPa 另找软绳解法（very_easy 软绳此前第 14–17 次全失败，可行性未知） | `easier_standard_final_50kpa/`、`easier_standard_final_E{3e6,1e7,3e7}/` |
| 2026-10-07 | 用户定：两档改回硬绳，且改动只限这两档。`YOUNG_MODULUS_PA = 1e8`（只在 `OrbitsBelowEasyTask`，仅 very_easy / easier 使用），model_revision `below_easy_v8_stiff_team_chain_v1`。顺带收紧三处原本按 `physics_model == "rigid_articulated"` 判断、同事把 easy–hard 换成刚体链后会被波及的代码：`recommended_grasp_assist` 只认 `OrbitsBelowEasyTask`（否则会对没有 `chain_roots()` 的任务报错）；目标描述的"两半中点相接 ≤ 2 mm"只加给 very_easy / easier；Harbor 模板的"离开 IPC → CPU float64、1200 ticks 静置"分支只对这两档生效。模板实测：very_easy / easier 为 cpu、1 子步、辅助抓持 53 / 75 个目标，easy 仍为 cuda、无辅助抓持。测试：below-easy 14、native-oracle 14、harbor-below-easy 6 项通过；goal-descriptions 仅 HEAD 已有的 6 项 interlocked_claws 失败。very_easy Harbor 第 19 次（最终代码复核）进行中 | `harbor_very_easy_19/` |
| 2026-10-08 | **very_easy Harbor 第 19 次（最终代码：100 MPa 限两档、model_revision v8、模板分支按档限定）通过**：`success 1`、`final_reward 1.0`、`deterministic 1`、3020 控制步（与第 18 次相同）、回放 559 s。接着开始 easier oracle（新几何 + MuJoCo 参考动作） | `harbor_very_easy_19/`，镜像 `topogym-below-easy:v18-20261007-orbits19` |
