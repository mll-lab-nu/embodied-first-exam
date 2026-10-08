# very_easy / easier oracle 部署总览

> 快照：2026-10-07 20:25 CDT（上一版 20:10、16:30）。本页只汇总现状，细节与变更记录在各任务的跟进页：
> rope、blanket、knot、slotted 见 [below_easy_oracle_tracker_zh.md](below_easy_oracle_tracker_zh.md)（下称"两档页"），
> orbits 见 [orbits_speedup_tracker_zh.md](orbits_speedup_tracker_zh.md)（下称"加速页"）。
> 表中数字从各评分目录与运行目录（本机、mll-4090-1、mll-4090-3）直接读取。

## 怎么读这张表

- **原生成功**：oracle 在 Harbor 冻结实例（或开发 Session，另注）上从出生状态连续跑完，Task 判 success。
- **privileged / standard**：Harbor 两种正式评分模式（定义见两档页第 1 节）；格中的 1 / 0 是 verifier 写出的
  `reward.json` success。"—"表示还没跑。
- **执行时长**：一次完整 oracle 执行（含建场景）的墙钟；规则上限 72 min。
- **状态**：通过 = 两个模式都为 1；进行中 = 有人在改并有运行在跑；未开始 = 没有人在做。

## 总表

| 任务 / 档 | 原生成功 | privileged | standard | 执行时长 | 现在停在哪里 | 状态 |
| - | - | - | - | - | - | - |
| rope very_easy | 是：第 770 行（30.8 s 仿真） | **1** | **1** | 约 8 min | 已完成；跨机器（mll-4090-3）复跑 770 行动作与终态 hash 逐位相同 | **通过**（代码未提交） |
| rope easier | 是：第 1119 行（44.8 s 仿真） | **1** | **1** | 7.9 min | 已完成；跨机器复跑逐位相同；噪声敏感性实验 22 / 22 成功（见下） | **通过**（代码未提交） |
| orbits very_easy | 是：3020 行（75.5 s 仿真） | 1（第 18 次） | 1（第 18 次） | oracle 约 7 min（0.14 s/控制步） | 第 18 次（镜像 `v18-20261007-orbits18`，刚体链、100 MPa）两个模式都为 1，但那时链的其余参数还不是队友标准。用户 20:00 前后定：两档用 100 MPa 硬绳 + 队友标准链（model_revision `below_easy_v8_stiff_team_chain_v1`）；按这个最终配置的第 19 次评分 20:12 起在跑 | **重评中** |
| orbits easier | 否 | 0 | — | 未跑完 | 场景再次改为柱距 165 mm、环内径 220 mm、绳长 1.25 m；MuJoCo 标准动作参考运行在 100 MPa 下能走通。尚无新的机械臂运行 | **进行中** |
| blanket very_easy | 是：637 行 | **1**（lab v19） | **1**（lab v19） | oracle 6.4 min | lab 在 v19（`89cc32674`，镜像 `rcb-topogym:0.2.17-dev-cu128`）上重评，两遍回放与 standard 终态 hash 同为 `51c8d213bf1b7bc8`，无容差（`docs/rcb/benchmarks/topogym.md` "v19 re-grades"，上游 `b16d2b3a2`）。此前本页写"未开始"是漏看了这个提交 | **通过** |
| blanket easier | 是，但只在原生门槛 0.90 下：覆盖率 0.912，本机与 mll-4090-3 两局一致 | 0（lab，旧场景） | — | 单局约 1.7 h | `oracle_12` 两段翻折后布已覆盖 0.912，正式评分要 0.95；第三段（两手拉平远边）按 0.95 重跑，本机与 mll-4090-3 各一局 `oracle_13`（19:20 起），两边都在第二段（翻上层）进行中 | **进行中** |
| knot very_easy | 是（848 行，本机与 lab） | **1**（lab） | **1**（lab） | — | lab 表：merged-v18 候选、镜像 0.2.16-dev，lab 目录 `obe tree_g`（`docs/rcb/ORACLE_FIXES_FOR_JIANWEN.md` "Update, 2026-10-06 21:45"，上游 `57b61ef2b`） | **通过**（v18） |
| knot easier | 是（1066 行，26.6 s 仿真） | **1**（本机 v18；lab 同为 1） | **1**（本机 v18；lab 同为 1） | — | lab 证据同上一行 | **通过**（v18） |
| slotted very_easy | 是 | 1（lab） | 1（lab） | — | 已随 `2f3233023` 合并；lab 评分在 merged-v18 候选上 | **通过**（v18） |
| slotted easier | 是：874 行（21.8 s 仿真） | **1** | **1** | 开发 Session 中 62 min（共用 GPU） | mll-4090-1，v19 候选 `v19-20261007-slotted-easier01`；privileged 两遍回放一致，standard live 与回放一致 | **通过**（代码未提交） |

按状态数：两个模式都为 1 的 7 项（rope 两档、knot 两档、slotted 两档、blanket very_easy）；按最终配置重评中 1（orbits very_easy）；
oracle 还没跑通 2（orbits easier、blanket easier）。能否直接拿去跑正式评测见下一节。

## 哪些可以拿去跑正式评测（20:25）

"可以"指：oracle 两个模式都为 1，评分所用的代码已提交、且就是正式评测要用的那份代码（v19 之后的同一个候选）。
按这个标准，**现在没有一项完全满足**，差别在后两条：

| 任务 / 档 | oracle 两个模式 | 评分所用代码 | 还差什么 |
| - | - | - | - |
| blanket very_easy | 1 / 1 | lab 的 v19（`89cc32674`），**不含** `99c3d27b0`（共享 IK 与路径检查，改了 `robot_oracle.py` 与 `harbor_bridge/actions.py`），也不含之后 easier 对 `robot_oracle.py` 的未提交改动 | 用当前代码重评一次 |
| knot 两档、slotted very_easy | 1 / 1 | lab：merged-v18 候选（knot `7571e4194`），本机 knot：冻结快照 `source03`；都**不含** `99c3d27b0`（两家族的 `kinematics.py` 改用共享 `OracleIKSolver`） | 用当前代码重评一次（本机 ik01 作业本应评 knot，但停在 not_run）；D6 随之不再需要 |
| rope 两档 | 1 / 1，换机器逐位一致，噪声 22 / 22 | 工作区快照（v19 + 未提交改动） | 提交代码，用提交后的代码建候选重评一次 |
| slotted easier | 1 / 1 | 独立 worktree（v19 + 未提交改动） | 同上 |
| orbits very_easy | 第 18 次 1 / 1，最终配置第 19 次在跑 | 工作区（未提交） | 第 19 次两个模式为 1，再提交、进候选 |
| orbits easier、blanket easier | 未跑通 | — | oracle 本身 |

评分走的路线（20:45 核对）：以上所有通过都经 `scripts/oracle_runners/test_harbor_oracles.py --candidate … --no-nop --execute`，
即原生 `harbor run -p <任务目录> -a oracle`：任务目录的 `environment/`、`tests/` 与候选逐字节相同（打包时按哈希核对，
只加 runtime_binding），verifier 是任务自带的 `tests/`，privileged 两遍新进程回放、standard 经 sidecar。与真实使用的差别：
① 都加了 `--no-nop`，没有跑"什么都不做得 0"的对照（`docs/rcb/README.md` 的验收要求有这一项）；② standard 的 oracle
是把 privileged 轨迹经 standard 服务回放（按单步 0.04 rad 换算时序），证明这条轨迹走公开接口可执行、可复现，不是只看图像的
闭环策略；③ 评的是候选目录，不是 `topogym_candidate_pipeline.py --phase all` 激活后的 `tasks/`（launcher 只跑 build 阶段，
初态精确恢复由 verifier 的 `instance_exact` 检查）。

另一点：工作区里还有别的会话对共享文件的未提交改动（`harbor_templates/topogym/common/rcb_topogym.py`、
`topogym/tasks/goal_description.py` 等），上面各次评分各自用的是当时的快照。最终候选把这些改动合在一起后，
至少要跑一次 preflight（初态 exact 恢复）；公开源码哈希一变，镜像也要重建（lab 对 `da47d3a49` 的说明同此）。

## 16:30 以来的变化

1. **slotted easier**：standard 也为 1，两个模式都通过。
2. **orbits very_easy**：第 18 次 Harbor 评分两个模式都为 1。做法：给刚体链加抗弯刚度（100 MPa），两手抓住后只竖直抬
   6 cm，再一起竖直升到实测所需高度、从固定件正上方越过放下；硬绳圈靠自身刚度保持张开，不碰球头脱出。
   之后用户要求对齐队友的刚体链标准（节长、阻尼、木柄为根等已对齐），刚度也改成队友的 50 kPa——这时 MuJoCo 两点提起
   复算卡在球上（中点连接拉开 24 mm），即第 18 次的解法在当前代码上不成立。
3. **orbits easier**：环孔太窄，夹爪伸不进环与球头柱之间（第 3 次实际碰到了环）。用户定了新尺寸（柱距 165 mm、
   绳长 1.25 m），MuJoCo 参考运行显示只有硬绳（100 MPa）能走通。
4. **blanket easier**：第 12 次改成两手同步下压、同一步被接纳后，接触期间最大拉伸从 1.452 降到 1.009；两段翻折后布
   就已静止且覆盖 0.912（本机与 mll-4090-3 一致），原生配置的 0.90 门槛判成功。正式门槛 0.95，所以第三段拉平还要做，
   `oracle_13` 在两台机器上跑。另修了一处 oracle 误报：任务在段中途已成功终止时，后续接触段不再报"两手未被接纳"。
5. **rope 噪声敏感性**：easier 已完成 22 局（关节目标噪声 1e-7–1e-4 rad、求解器容差 ×0.97–1.03，闭环与回放），
   全部成功，回放的成功行全是 1119。very_easy（mll-4090-3）完成 4 局全部成功，其余未跑完。

## rope 噪声敏感性实验

目的：模拟换 GPU 型号后的数值差别，看 rope 两档 oracle 是否还能成功。两种扰动：每控制步给每个臂关节目标加
均值 0、标准差 S 的高斯噪声（S = 1e-7、1e-6、1e-5、1e-4 rad），或把 IPC Newton 与线性求解器容差乘以
0.97–1.03。closed = oracle 闭环重跑；open = 回放已评分的动作行。

| 档 | 已完成 | 成功 | 未完成 |
| - | - | - | - |
| easier（本机） | closed 13 局、open 9 局 | 22 / 22 | — |
| very_easy（mll-4090-3） | closed 3 局、open 1 局（无噪声、容差 ×0.97 / ×0.99） | 4 / 4 | 容差 ×1.01 及各档关节噪声 |

证据：`runs/test_results/oracle_noise_20261007/`（`runs/`、`remote_mll3/`、`queue.log`）。

## 收口前还要定的事

1. ~~orbits 绳刚度~~：已定（用户，10-07 晚）——两档用 100 MPa 硬绳 + 队友标准链，改动只限这两档。
2. **D6 评分基线版本**（两档页第 5 节）：knot 两档、slotted very_easy 的通过结果在 merged-v18 候选上；
   是在 v19 下重评，还是逐位核对回放后沿用。（blanket very_easy 已在 v19 上重评通过。）
3. **代码提交**：rope 两档、slotted easier、orbits、blanket 的改动都还在工作区（或独立 worktree）未提交。
4. ~~knot 的 lab 证据~~：已在上游 `57b61ef2b` 的表中（lab 目录 `obe tree_g`，merged-v18 候选）。
