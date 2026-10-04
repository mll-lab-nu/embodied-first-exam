# 解绳结：一个松 Trefoil 的基础场景

> **2026-09-27 更新：** 正式 easy 为两次重叠单绳圈；medium 为原 easy 的 overhand_trefoil；hard 为原 medium 的 figure_eight。double_overhand 已移到实验附表。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。

## 冻结实例 oracle 交接与整合（2026-10-03）

已导入用户提供的 `knot_untying_oracle_artifacts.tar.gz`：原始运行、三档 IPC 存档及日志位于
`runs/test_results/knot_handoff_20261003/runs/knot_oracle/`，
[导入清单](../../../runs/test_results/knot_handoff_20261003/import_manifest.json) 记录压缩包与每个文件的 SHA-256。
代码归入 [planning/knot_untying](../../../topogym/planning/knot_untying/README.md)，
执行入口为 `scripts/oracle_runners/run_knot_oracle.py` 和 `run_knot_branching.py`。

| 档位 | 已收到的物理证据 | 本轮状态 |
|---|---|---|
| easy | `easy05` 原生成功，575 actions、5,744 ticks、14.360 s；已有正式实例新进程回放成功日志，exact=true | 原证据已核验导入；单次回放不证明重复确定性 |
| medium | `medium03` 原生成功，1,927 actions、19,268 ticks、48.170 s | 正式初态精确恢复；本轮首遍跑完全部动作但 `success=false, episode_end=null`，第二遍按用户要求取消，原因待查 |
| hard | `hard01` 部分执行 53.075 s，4→3→1，仍有紧卷；没有完整成功 | `hard06` 完成第一轮 30.0 s、4→1，后为原生规则优先迁移保留证据并停止；`hard07` 两个候选因接近跟踪滞后导致 IK 失败；`hard08` 修复抓姿选择和等待时序，沿用 v14 工具／精确新初态／0.2.13-dev，尚无完整成功 |

medium 首遍返回值见 [原生结果](../../../runs/test_results/knot_oracle_20261003/medium_first_replay_result.json)。
原命令请求两遍；第一遍完成后在第二遍初态恢复期间暂停，通过只读进程检查保存第一遍
`Session.replay` 的完整返回值，并由原生 session 日志交叉确认。随后停止进程给 hard 释放显存；
不能将进程的人工停止码当成首遍物理失败，也不能称本轮回放通过。末尾静置余量与轨迹偏差尚未区分。

此前交接回放与 hard06 使用已冻结工作区源码、`ghcr.io/luigivamper/rcb-topogym:0.2.6-cu128`、
Genesis 1.2.1／libuipc build `292c98c3`。日志与快照在
[本轮验证目录](../../../runs/test_results/knot_oracle_20261003/)。原交接使用镜像 0.2.3，
结果不自动移植给新环境；新进程回放单独记结果。当前源码已启用 `goal_complete=True`，
绳接触摩擦平滑为 1 mm/s；导入时旧 `tasks/` 存档与此不同，所以当时使用交接的重建实例。
现已合入 v14 新实例，后续入口不再默认选择交接存档，版本差异见下节。
oracle 搜索修改没有改变任务判据、绳径、有效体积要求或旧 benchmark 包。

执行保持实例时序：2.5 ms tick × 10、IPC 子步 1、纯摩擦抓持、默认 ALOHA home 起步。
easy 抬起 s=224 mm 的上股 25 mm、沿 −x 搬运 95 mm；medium 远端固定、删交叉再两端拉开。
夹爪命令是实际开口宽度，默认 **5 mm**；两端拉开的抓点离端头 **35 mm**。
旧运行中零开口曾压翻体单元，medium 离端头 15 mm 的一次尝试也失败；当前搜索不把这些经验当成参数禁令，保留失败证据并按原生规则及独立几何检查验收。
hard 的物体路线经验是完整拉 0.55 m，不能在第一次交叉减少时即停止。

本次补全了：实际 tick 计时、原生终止立即收尾、失败退出码、动作前缀存盘、完整决策回溯、
续跑前的实例／tick／绳形核对，以及正式 RGB 实例的新进程 replay 检查。
交叉已清零但原生稳定窗口未完成仍判未解开；分支搜索成功仍须重新回放。
复现和实例重建命令见 [oracle README](../../../topogym/planning/knot_untying/README.md)。
这批证据不扩展到其他 seed、网格／时间步收敛或逐子步机器人禁碰资格；本轮没有新录像。

## v14 / 0.2.12 对当前 hard 的影响（2026-10-03）

本地合并后的代码与 **hard05 实际执行快照**逐文件对比：Knot Task、基础 Task、
终态／稳定检查、Env、SimulatorConfig、IPC articulation 初始化及放宽后的分支搜索均相同。
因此这次更新没有给当前 oracle 新增固定终点或参考路径要求；主要变化在 `rcb_topogym.py` 的运行时规则。
[完整对比与实例哈希](../../../runs/test_results/knot_oracle_20261003/version_audit_v14/comparison.json)保存了核对范围。

| 变化 | 对 Knot hard 的影响 |
|---|---|
| R2 软体异常持续时间 | 原快照体积比 ≤0 当 tick 失败；v14 连续 0.25 s（100 ticks）才失败，短暂异常判不可评估、不能积累成功。原生 IPC invalid 仍立即失败。后续按用户“原生规则优先”要求，逐 tick 体积异常保留诊断，任务结论按原生 R2；独立实体穿透检查另行判定 |
| R3 手臂力矩上限 | 每臂六关节上限为 `[12.9, 80, 59, 12.9, 35, 17.5]` N·m，并与模型原上限取较小值；夹爪驱动力不变。可能改变接近、抓稳和抽绳时的跟随误差，需要新环境实测 |
| R4 桌面命令保护 | 按夹爪碰撞网格限制 arm target，最低允许桌面下 **15 mm**；会裁剪部分命令，但不是实际无穿桌检查 |
| R1 / R5 | R1 针对 rigid-task 接触判据，不直接用于 Knot FEM。R5 的每步 0.04 rad 限速及 0.5 rad IK 跳变拒绝位于 standard 服务；当前 privileged Session 的直接 JOINT_ABS oracle 不经过该服务 |
| cloth-contact 与 instability guard | 前者修复 PBD 刚体接触，后者检查 `particles` 速度；Knot 绳位于 FEM 状态，不能把这两项当作新增绳防穿模保障 |
| 新冻结实例 | 三档资产、模拟配置与 IPC 身份元数据相同，但 settled state 的数组与原生 dump 已重建；hard 初态 SHA 从 `90fc4a2f1ae464ba` 变为 `a4fbd7af273b0379`。hard 绳顶点最大位置差约 9.0 nm，数值虽小，仍属于不同冻结实例 |
| 步耗时文案 | hard 新文案为 unloaded 1.7 s / shared 3.3 s 每控制步；物理仍是 2.5 ms × 10、40 Hz。文案更新不使本机现有运行自动加速，按实际日志估时 |

`hard05` 已为控制器修复主动停止；`hard06` 当时使用 **0.2.6 + 冻结源码 + 旧 hard 初态**，后也保留证据并停止。
不会将其结果重标为 v14 成功。0.2.12 镜像拉取返回 registry `denied`；当前已用本机固定
0.2.13-dev 镜像运行 v14 工具和精确新初态，见下方 hard07 / hard08 记录。此组合正在真实执行，正式新进程回放仍待原生成功后进行。
后续新运行默认选择当前任务包实例，历史重放须显式给出旧实例并使用对应源码／镜像，避免新规则混用旧默认输入。
本次通过 25 项安全规则 CPU 测试和 18 项 Knot 回归；不代表新力矩／桌面保护下已完成真实抓绳。

## hard04 / hard05 的初次限制检查与放宽（历史）

本节保留 hard04 / hard05 时的限制检查和证据；当前 hard08 已进一步放宽，见下方“hard07 / hard08：原生规则优先、空间搜索与跟踪修复”，不沿用下表旧搜索预算。本节只核对 Knot 的 easy / medium / hard；初始检查依据 `hard04` 冻结源码，随后按用户要求放宽搜索并重启为 `hard05`。
**三档原生 Task 的固定 XY 终点限制为 0，参考路径匹配限制为 0。原搜索的 2 条操作末尾硬剪枝已放宽，新运行 `hard05` 使用该策略。**
源码哈希和 CPU 判据探针见 [检查记录](../../../runs/test_results/knot_oracle_20261003/constraint_audit/predicate_probes.json)。
检查中 48 个合成终态候选覆盖直绳／弯曲绳、平移／旋转和不同机器人远离位置，均通过候选判据；
6 个无效体积、运动、低于桌面、未释放或机器人过近的反例均未通过。
这些输入使用合成表面环和诊断字段，只证明判据行为，不构成真实 FEM 执行或无穿模证明。

| 层次 | 当时限制 | hard05 当时如何处理 |
|---|---|---|
| 原生终态 | 不指定绳端坐标、XY 目标区、机器人回 home 姿态或动作阶段顺序；要求无投影交叉／重叠、贴桌、松手、机器人离绳至少 5 mm，速度不超过 1 mm/s、漂移不超过 1 mm，稳定 0.5 s | 保留完成语义；弯曲但无重叠的绳也可以完成。不满足时通常继续等待，并非立即失败 |
| easy 路线 | 固定材料坐标 `s=.224 m`，抬 25 mm、沿 −x 搬运 95 mm；当前 carry 只有一个默认候选 | 这是求解器配方，不是评分规则；若该配方失效，可扩展抓点和搬运方向候选 |
| medium / hard 路线 | 按较短自由端选首个下穿交叉；竖直下夹，拉绳阶段保持抓取方向；主要只有删交叉／两端拉开两类动作 | 已允许同一节点交替尝试两类动作的参数候选，旧规则仅决定优先级；抓点和姿态仍沿用已有物理动作 |
| 原分支硬剪枝 1 | **一次完整操作后**交叉数不减少（`after >= before`）就回退 | 已改为默认允许连续 2 次未刷新本分支最低交叉数的操作；下一次若取得新低可继续。`4→5→4` 不刷新预算，可用 `--max-nonprogress-decisions` 调整上限 |
| 原分支硬剪枝 2 | 两端拉开后仍有材料跨度小于 **12 cm** 的交叉圈就回退 | 已改成 `tight_curl_after_spread` 诊断标记，不再据此回退，允许继续尝试恢复 |
| 搜索与等待预算 | 默认最多 8 层决策、30 次候选；交叉清零后最多再等 10 s | 预算耗尽只能说明本求解器尚未找到解，不能证明其他路径失败 |
| 新进程回放 | 精确核对**初始实例**，执行提交动作及 tick；不要求末态 SHA 与原运行一致，也不检查是否属于已知路线；动作结束后不自动追加静置 | 保留证据身份检查。需要更长静置时显式补动作、重新验证；medium 首遍未成功的原因仍未确定 |
| checkpoint 续跑 | 前缀回放后，绳形／关节必须与该 checkpoint 接近（0.2 mm／0.2 mrad） | 这是恢复控制器状态的前提，不是要求最终回到该位置；保留 |

本轮放宽只改搜索剪枝和动作类别候选，没有修改 Task、绳模型、碰撞参数或正在执行的
`hard04` 快照；不能通过放宽体积有效性、减小绳径或容许穿透来获取成功。
`branching.json` 记录策略版本 `bounded_nonmonotonic_v1`、每次操作的诊断标记和未进展计数。
计数由有效决策前缀重算，回溯和旧 checkpoint 续跑不会带入已丢弃分支的计数。
17 项 Knot CPU 回归通过，覆盖交叉数不变／增加后成功、小紧圈恢复、振荡预算、物理失败拒绝和完整回溯；
这些结果不代表放宽后的策略已经完成新的物理执行。原始判据检查记录保留修改前源码哈希。

用户要求重跑后，`hard04` 保留日志、源码和已有检查点，标为主动取消而非物理失败；
其第一个动作原语尚未结束，未完整写出这段执行的动作前缀。
`hard05` 从相同 hard 冻结初态重新开始，沿用 `hard04` 的物理／几何／资源源码，
只替换 `branching.py`、`cli.py` 和只读回放指标观察器 `replay_audit.py`。
[启动身份记录](../../../runs/test_results/knot_oracle_20261003/hard05_launcher/launch_plan.json)保留旧运行身份。
该轮曾由 `supervisor_v4` 接管，未因此重启物理执行，见[接管记录](../../../runs/test_results/knot_oracle_20261003/hard05_physics_replay_launcher_v2/adoption.json)。
发现下面的命令高度缺陷后主动停止，取消记录和全部旧证据保留；其待回放队列未执行。
[实时状态](../../../runs/test_results/knot_oracle_20261003/background_status.json)追踪当前 hard 轮次；hard06 的历史证据保留。

首个完整操作的[动作与检查点副本](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/decision_1/manifest.json)
已单独保留：1,192 actions、11,920 ticks、29.8 s，完整拉出 0.55 m 后释放撤手，交叉 4→1。
末次中心线采样 29.625 s 中，剩余局部圈对应约 27.0 cm 材料跨度，随后自动进入两端拉开；
这是实测部分流程与中心线诊断，不是完整成功或体网格无穿模证明。

第二轮已完成两端拉开与释放：43.62 s 的采样日志首次记录零交叉，49.2 s 时完整前缀为
1,968 actions／19,680 ticks，原生 `planar_clear=true`、`on_table=true`，非局部平面最小间距约 16.4 mm。
此时最大速度约 2.14 mm/s，高于 1 mm/s 阈值，`quiet=false`、稳定时间为 0。
[第二轮完整前缀](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/prefix_19680_6883325517a5/manifest.json)
已按动作数、tick 数和复制前后哈希核对保存；它仍不是完整成功或无穿模证明。
随后按原策略静置至 59.225 s，交叉持续为零，但未触发稳定成功，搜索回退到 29.8 s 并改试退绳。
[该分支的静置与拒绝记录](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/first_zero_crossing_settle_rejected.json)
保留完整日志；49.2 s 后没有完整详细指标落盘，因此不能断言最终仍只差速度。
后续静置阶段已加独立只读指标采样，保存实际阶段、分支、最后已提交 Task tick 和原生判据。
诊断会短暂停顿后恢复同一进程，不注入代码或写进程内存；首次有效读取发生在回退后，不用于解释上一分支。

随后替代的退绳候选在 40.305 s 被原生 `rope_volume_invalid` 拒绝，
[失败日志](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/second_candidate_volume_invalid.json)
已保存，失败动作没有纳入当前有效前缀。日志未保存失败 tick 的完整 FEM 数据，不能再细分为体积翻转或其他原生 IPC 无效。
搜索随后从 29.8 s 检查点尝试 50 mm 抓点，但在此候选完成前因下述命令缺陷主动停止，不能将人工停止解释为该候选的物理失败。

### hard06：修复低于桌面的命令并从初态重跑

对零交叉前缀全部 1,968 条动作，按原生 float32、限位裁剪和开口转换做独立 CPU FK 检查，
发现第一次释放目标最低约低于桌面 14.93 mm，第二次释放约 17.76 mm。
这是**命令几何**，不是实际物理穿透深度，见[诊断报告](../../../runs/test_results/knot_oracle_20261003/diagnostics/first_zero_command_kinematics/report.json)。
根因是水平移动每段从下沉的实测 TCP 重设高度，释放又减去最初的抬升量。
因此已[主动停止 hard05](../../../runs/test_results/knot_oracle_20261003/hard05/cancellation.json)，保留旧证据，不续跑其动作前缀。

控制器现保持计划的搬运高度，释放不低于绳在桌面上时的夹取高度；两臂路径长度不同时，短路径等待长路径完成。
每条提交命令按原生夹爪碰撞体的保守外包络检查桌面间隙，至少 0.5 mm；不满足则在推进前拒绝。
IK 只向上修正 Z 来满足这个规划余量，不放宽实际穿透、体积或成功判据。
每 8 控制步及终止时保存完整原生指标；被拒候选在回溯前保存完整动作前缀、终态指标和共享模块的最后一 tick 证据。
最后一 tick 记录不会标成全程碰撞证明。

18 项 oracle、5 项命令安全、10 项几何、11 项记录、6 项证据审计 CPU 测试通过。
真实模型 FK/IK 抽检 11 个旧危险姿态：全部原命令被拒，修正后包络间隙均至少 0.5 mm，
见[验证记录](../../../runs/test_results/knot_oracle_20261003/hard06_launcher/command_guard_native_fk_validation.json)。
这些是无物理积分的验证，不能证明修正后的实际抓取可行或无穿模。

`hard06` 在至少 10,000 MiB 空闲显存持续 30 s 后，于 23:25:34 UTC 启动；只在系统 RAM 达到 90% 时停止本轮工作，不停止其他任务。
其[冻结启动方案](../../../runs/test_results/knot_oracle_20261003/hard06_launcher/launch_plan.json)只覆盖 8 个控制／审计文件，
另 653 个运行文件与 hard05 相同；Task、物理、几何、时序和输入实例保持原字节。
从原始旧 hard 初态开始；原生成功后自动做两遍正式实例回放，首遍记录全 tick、四路共享录像并做独立碰撞审计。
当前尚无 hard 完整原生成功、正式回放或防穿模资格。

hard06 已实际完成首次闭合／夹紧并进入抬升，见[首次夹取记录](../../../runs/test_results/knot_oracle_20261003/hard06_milestones/first_pinch.json)。
已封存的[早期抬升采样](../../../runs/test_results/knot_oracle_20261003/hard06_milestones/first_lift_following.json)
中，左侧抓点绳中心升高约 20.4 mm，相对指垫接触点偏移仍不超过约 1.6 mm。
5.625 s／2,250 ticks 时已进入第一轮抽绳，尚无保护拒绝或原生失败。
这支持修复后仍能完成此次夹取和早期抬升，不代表完整抽绳、任务成功或防穿模资格。

hard06 第一轮退绳、释放和撤手已完整执行：30.0 s、1,200 actions、12,000 ticks，
拉出 0.55 m 后交叉 4→1，已进入第二轮两端拉开。动作前缀与决策 2 检查点的数组／tick 完全一致，
复制前后哈希核对通过，见[第一轮证据副本](../../../runs/test_results/knot_oracle_20261003/hard06_milestones/decision_1/manifest.json)。
此时原生最大速度约 0.877 mm/s，`quiet=true`，但 `planar_clear=false`、`on_table=false`，
仍未任务成功；命令保护未拒绝这一轮，也不能据此代替全程实际碰撞检查。

hard06 在第一轮释放／撤手阶段做了 30 s 非阻塞只读栈采样：594 个有效主线程样本中，
560 个（94.3%）位于镜像内 Genesis 的 `_ipc_world.advance()`，3 个（0.5%）位于 IK／FK／命令检查，
其余主要为状态读取和判据；另有 5 次采样读取错误。
这支持该窗口的主要耗时在原生 IPC 推进，不能细分 GPU 计算、同步等待或资源竞争，也不能外推为全程精确比例。
采样未注入代码或主动暂停 worker，见[原始栈与采样汇总](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard06_runtime_sampling/summary.json)。

后续检查发现 Genesis 原生 FK 会恢复 qpos 后重算实时 solver 的位姿字段，新版 tooling 的 `_ChainFK`
也明确规避了这个查询副作用。工作区已把命令几何检查改为只读 CPU 链式 FK，保留原生 IK；
1,968 个历史命令姿态加 100 个随机姿态与原生 FK 的最大位置差为 6.7×10⁻¹⁶ m、
最大角差为 1.1×10⁻¹⁵ rad，查询前后实测 solver 字段不变。
3 项链式 FK 合同检查、5 项命令安全及 18 项 oracle 回归通过，
见[真实模型对照记录](../../../runs/test_results/knot_oracle_20261003/diagnostics/static_command_fk_validation/report.json)。
此改动作为后续候选保存，**没有热替换 hard06 的冻结源码**；不能据 CPU 测试声称实际吞吐提升或物理资格通过。

另在 CPU 回归中复现了拒绝证据的目录冲突：子分支耗尽后，父分支用当前尝试总数命名，
会与最后一个子分支重名并中断搜索。工作区改为尝试开始时分配固定编号，父子失败前缀分别保存；
18 项 oracle 回归通过，包含真实临时目录写入和回退后继续找到解的检查，
见[冻结代码复现与候选验证](../../../runs/test_results/knot_oracle_20261003/supporting/rejected_evidence_id_candidate/validation.json)。
该修复尚未部署到 hard06；当前运行若触发此问题，会保留已有证据后再用修复快照恢复搜索，不将其报告为物理失败。

后续全 tick 记录还补了磁盘处理：原共享 writer 会每 tick 重存不变的单元连接表等大数组，
60 s 绳数据的两份副本估算就可能超过当前空闲磁盘。共享 `SegmentEvidence` 已增加默认关闭的
逐字段精确数组引用复用，Knot 回放启用；dtype、shape、C-order 字节均相同才复用，保留所有 tick 和字段，
仅缓存当前字段路径的上一值。原 decoder 直接读取，失败写入不会发布未提交数组引用。
5 项共享记录检查、11 项 Knot 记录检查和 6 项完整证据检查均通过，包括冻结回放快照中的复测。
[8-tick 编解码对照](../../../runs/test_results/knot_oracle_20261003/diagnostics/array_reuse_payload_validation/report.json)
使用实际绳拓扑和变化的测试位置／速度：解码字段逐字节相同，后续绳数据每 tick 从约 4.64 MB 降至 1.85 MB。
60 s 两份绳数据约 89 GB，未计刚体、录像及后续其他占用，仍不是容量保证。

[新的回放启动方案](../../../runs/test_results/knot_oracle_20261003/hard06_replay_array_reuse_launcher/launch_plan.json)
只在 hard06 快照上替换共享 writer 和 Knot 回放观察器，物理／任务源码不变，也未混入待验的 CPU FK 改动。
等待程序已绑定原 hard06 容器 ID；只有它退出且原生成功、完整动作文件存在后，才接管旧回放调度器。
目标目录为 `hard06_replay_array_reuse` 与 `hard06_collision_audit_array_reuse`，仍为两遍回放、首遍全 tick／四路录像及独立审计。
该 hard06 队列现已随迁移停止；hard07 使用新的独立调度器，实际完整回放资格仍待验证。

**防穿模仍有验收缺口。** `hard05` 原快照每 tick 检查 IPC 有效和体单元正体积，末态检查贴桌与机器人离开，
但这些不等价于全程网格无相交。`KnotIK.check()` 能检查机器人对桌面、同臂和双臂碰撞，
目前 `robot_oracle.py` 没有调用它；该函数本身也不包括形变绳的碰撞体。
抓点的中心线间隙、95% 材料跨度停止线和 5 mm 夹爪开口是预防措施，不能代替实际接触审计。
现有贴桌判据允许低于桌面至多 1 mm，这不是已经满足用户“无穿模”要求的证明，也不应继续放宽。
在扩展路线后的正式验收中，需要补充实际机器人／绳／桌面接触检查，并报告时间采样范围；
本轮 native success 或 replay success 均不能单独标成完整无穿模资格。

为补这部分证据，已接入可选的 `--physics-evidence` 回放观察器，复用共享数值证据 writer，
记录初态及每个物理 tick，不改变原生动作或时序。独立几何检查已覆盖体单元翻转和非相邻绳面自交，
现有 10 项几何检查、11 项记录合同检查与 6 项完整证据审计检查通过，均为 CPU 测试。
三角形算法与 FCL 的 600 组随机结果一致，新增 150 组实体凸体／四面体结果也一致；
覆盖物体完全包含、零间隙接触、瞬时翻转、记录缺失／篡改及 replay rewind 后分支编号不为 0 的情况。
hard 冻结初态的 40,769 顶点／174,085 四面体／47,376 表面三角形检查中，最小体积比约 0.9020，
未发现翻转或非相邻表面相交；这是**初态检查**，不能外推到执行全过程。
记录见 [初态几何诊断](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard05_initial_geometry_audit.json)。
带物理证据的回放与离线碰撞检查已接入成功后的队列，尚待实际物理运行验证。
两遍原生回放中首遍记录全部 tick，并通过共享 `RecordingSession` 保存同次执行的四路 Nyx 视频，
逐帧核对与数值证据的状态身份，结束后全量解码；第二遍只验证原生成功。证据保留 10 GiB 磁盘余量，
不足时明确失败，不截断后冒充完整。回放观察器采用独立快照，除 5 个审计入口／模块外，
656 个运行文件与 hard05 快照相同，见[启动方案](../../../runs/test_results/knot_oracle_20261003/hard05_physics_replay_launcher_v4/launch_plan.json)。
网格导出使用静态顶点和只读原生几何位姿，不调用会刷新 solver 顶点缓存的 `get_verts()`。
ALOHA 指尖另有 12 个球形碰撞体；球体采用按原生半径外扩至所有支撑平面都包住球体的多面体，
不能用内接三角网格凸包漏掉真实球面。BOX 使用解析角点，未知 primitive 拒绝认证。
独立检查使用实际机器人／桌面碰撞顶点的凸包外包络，逐个填充四面体检查分离，因此不会漏掉完全包含；
外包络重叠只表示不能认证，可能来自凹槽或接触，不据此声称确定穿透。刚体配对沿用原生启用列表，
检查所有记录时刻及原生刚体接触深度；不覆盖相邻绳面折叠、禁用刚体配对或 tick 之间的连续 CCD。

## hard07 / hard08：原生规则优先、空间搜索与跟踪修复

用户要求优先遵循 v14，并尽量减少 oracle 附加限制。hard06 第二轮两端抓取曾在
32.175 s 被额外 +0.5 mm 命令保护拒绝；退绳替代分支还出现过原生体积无效。
[停止记录](../../../runs/test_results/knot_oracle_20261003/hard06/cancellation_native_rules_migration.json)
保留最后指标、搜索状态、此前完整第一轮和各拒绝前缀，不将人工停止计为原生物理失败。

hard07 的[冻结方案](../../../runs/test_results/knot_oracle_20261003/hard07_native_launcher/launch_plan.json)
使用 v14 任务工具（SHA `062af946…`）、v14 hard 初态 `a4fbd7af273b0379`，以及本机
`0.2.13-dev-cu128` 镜像（ID `a54e0a324bc2…`）。官方 0.2.12 仍未安装；该组合不冒称官方镜像验证。
[真实预检](../../../runs/test_results/knot_oracle_20261003/hard07_preflight/report.json)
确认初态 exact、R2 100 ticks、R3 ALOHA 力矩上限和 R4 −15 mm 均已安装；一个控制步正常推进，
8 个竖直／偏转／倾斜抓姿均有 IK 解。这不是实际抓取或完整解结成功。
初态加 10 个物理 tick 的[几何审计](../../../runs/test_results/knot_oracle_20261003/hard07_preflight/contact_audit/audit.json)
完整，无穿透发现或 unresolved；最小体积比约 0.9020。因为任务未完成，qualified=false 正确保留。

hard07 的 `native_rules_spatial_search_v2`（hard08 继续沿用以下规则）：

- 有 v14 原生桌面保护时取消 oracle 的 +0.5 mm 门槛及自动向上修正；原生实际接受的目标成为后续 IK 种子。
- 默认关闭交叉数停滞剪枝，紧卷仍仅诊断；有限运行预算扩大为 16 层、128 次候选。
- 候选搜索两端、交换手臂、不同抓点和固定点、抓姿偏转／倾斜、不同拉动角度以及带抬升／侧移的路径。
- 抓点改为三维空间排序，拥挤点不再因二维投影余量不足直接失败；取消默认 95% 材料跨度停止线。
- IK 当前种子失败后尝试 home 和两个关节扰动种子；接受残差为 0.5 mm／0.01 rad，原生关节限位不变。
- 零交叉后等待未成功时继续撤手、重新落绳或拉开；完成仍只能由原生 task_success 决定。
- 抬升不再硬限 100 mm、拉开比例不再硬限 0.95、闭合宽度不再硬限绳径；输入必须有限且满足参数语义，机器人范围交原生裁剪。

接触审计也已调整。BOX 和原生凸网格用实际凸实体，球用解析半径；闭合凹网格在包络碰撞后
进一步检查实际表面和包含关系。边界接触不计为穿透，确认内部相交才记录 penetration；
未支持或缺失几何明确记录 unresolved，不能因此声称完整合格。几何比较分辨率为 1 nm。
绳自接触由非相邻表面及其相邻实体单元细分；仍不覆盖共享顶点面的自折叠、无表面接触的完整
自包含、禁用刚体配对或 tick 间连续 CCD。体积异常每 tick 保留，是否因持续时间失败由原生 R2 决定，
不另加“一个 tick 异常即任务失败”。原生刚体接触深度保留为诊断，不与精确实体相交混为同一测量。

hard07 的退绳和两端抓取候选都在接近结束的 1.0 s 遇到 IK 不可达，未触发额外桌面拒绝。
[实测状态与 CPU 重建](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard07_approach_ik/report.json)
表明左腕相对命令尚差约 1.56 rad；在这个实际位置强制最终朝向不可达，但预抓位本身可达。
另一夹爪朝向同样可达，并把 home 到预抓位的最大单关节转动从 3.14 rad 降为 1.77 rad。
该替代抓姿计算使用最后一份 0.825 s 中心线，不是未保存失败目标的精确重放，也不代表真实抓取通过。
hard07 已按[停止记录](../../../runs/test_results/knot_oracle_20261003/hard07/cancellation_approach_tracking.json)保留失败状态和动作。

hard08 使用[新的冻结源码](../../../runs/test_results/knot_oracle_20261003/hard08_native_launcher/launch_plan.json)，
策略 `native_rules_tracking_search_v3` 对两个可达夹爪朝向按实测关节转动排序，并在接近结束后
最多等待 4 s，待预抓位误差在 20 mm／0.1 rad 内再下降；超时仍尝试 IK，不额外判抓取失败。
接近时间和等待预算可配置，原生 R2／R3／R4、摩擦抓取和完成判据不变。
33 项相关 CPU 回归通过；旧版公共图像／初态预检不作为新控制器完整物理成功的证据。
实测接近后额外等待 0.05 s，右／左 TCP 距预抓位约 13.35／15.48 mm、姿态差约 0.083／0.091 rad，
通过下降转换条件，并已真实下降至 1.625 s／650 ticks、无回溯，见[首段下降证据](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/first_descent.json)；尚不代表抓取完成。该段 10 s [只读采样](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_runtime_sampling/summary.json)
的 199 个有效样本中 198 个在原生 IPC advance，采样不区分 GPU 计算、共享竞争或同步等待。
新的 hard08 证据／四路视频归档助手已完成语法检查和缺证据拒绝检查；尚未执行正式归档或发布。
随后已完成首次定位、闭合和夹紧，并进入退绳。3.02–4.42 s 的[实测抬升采样](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/first_lift_following.json)
显示左侧抓点上升 25.4 mm，采样接触偏差最大约 1.24 mm，右端仍固定；这支持早期抓取跟随有效。
这些是中心线和计划夹爪接触点的舍入采样，不构成全轨迹碰撞或完整解结证明。
第一轮退绳已经完整完成：29.125 s、1,165 actions／11,650 ticks，拉出 0.55 m 后释放两端并退开，投影交叉 4→1，无回溯、无原生 episode failure；第二轮两端拉开已开始。只读[前缀观察器](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/watcher_plan.json)已保存[完整第一轮动作前缀](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/prefix_11650_78299a35c0ad/manifest.json)。
[检查点核对](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/decision_1_validation.json)确认前缀 action／tick 数组与第二轮检查点逐项相同，文件哈希一致；命令保护归原生 Session，R4 为 −15 mm，额外 oracle 桌面余量为 null。此处证明一轮操作及其证据完整，不表示原生任务成功或全 tick 无穿透资格。
第二轮两端抓取已完成位置收敛，31.425 s 进入闭合，未出现旧的额外桌面保护拒绝，见[该阶段实测记录](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/second_grasp_convergence.json)。它使用新的初态／运行版本，不是 hard06 失败命令的对照重放；第二轮完整结果仍待验证。

当前调度器为 `/tmp/knot_hard08_supervisor.py`，状态见
[background_status.json](../../../runs/test_results/knot_oracle_20261003/background_status.json)。
原生成功后仍做两遍正式实例回放，首遍全 tick／共享四路录像及独立几何审计。
另已启动独立的只读 CPU 并行审计等待队列：9 项审计测试通过，同一 11 个真实状态的
逐 tick 结果、汇总和证据哈希与串行完全一致，1／4／8 进程耗时约 10.85／4.74／4.32 s。
[独立冻结方案及基准](../../../runs/test_results/knot_oracle_20261003/hard08_parallel_audit_launcher/launch_plan.json)
只改调度与 CLI；接触、穿透、体积和资格判据相同。队列绑定当前监督进程，在完整 capture 封存后启动 8 个 CPU 测量进程；原生运行和原串行调度不被替换。归档助手已支持 `--parallel` 显式选择及对应源码哈希核对，缺证据时仍拒绝发布；完整结果与最终归档仍待验证。
完整 hard 原生成功、正式回放和最终物理资格尚待验证。

## 三档物体路线与 IK 的历史记录（2026-09-30）

本节描述当时状态；机器人与终态开关的最新情况以上方 10 月 3 日记录为准。

按"只动绳的路线 → 机器人 IK → 任务 Env 内连续物理执行"的顺序补证据，**机器人物理执行尚未完成**。绳上位置一律用弧长 s（从 A 端起，直绳参考态的材料坐标）；"交叉"指俯视投影中两段不相邻绳的交点；"抓点"指离 s 不超过 6 mm 的那一段绳。

**动作及出处。** 三档只用两类动作：
- 删交叉（node deletion，[HULK](https://arxiv.org/abs/2011.04999)）：从较近的自由端往里找第一个"该端从下面穿过"的交叉，一只手按住、另一只手抓住该交叉之后 35 mm 处抬起并往外拉，每拉 50 mm 重新数交叉（HULK 每次动作后重新感知）。与 HULK 不同，按住的是另一端离端 15 mm 处（v9 demo 的远端固定）：按 HULK 原样按在交叉旁的上股时，两手之间只有约 291 mm 绳，拉开时绳被拉长、松手回弹（`hard_cl_v4/v5`），不采用。
- 两端拉开（Reidemeister move，HULK 与 [SGTM 2.0](https://arxiv.org/abs/2207.07813)）：只剩局部小圈（一个交叉的两次经过之间没有别的交叉）时，两手捏住两端往外拉，小圈翻转消失。
- easy 的两个交叉都是同一条腿压在上面（Reidemeister II 构型），一只手把上面那条腿抬起越过另一条即可。

| 档位 | 只动绳的路线（粗网格，IPC 摩擦平滑 1 mm/s） | 交叉数 | 机器人 IK（CPU，仅运动学） |
|---|---|---|---|
| easy | A 腿鼓包 s=224 mm 抬 25 mm、−x 平移 95 mm、放回 | 2→0，终态判据稳定通过 | 右臂可达，桌面最小间隙 2.1 mm |
| medium | 远端 B 固定；A 侧 s=249 mm 抬 15 mm 沿绳拉 300 mm；两端拉开到约 0.9 m | 3→2→0，稳定通过；绳总长最大 +1.8 % | 左臂按 B、右臂拉 A；两端拉开右 A 左 B；均可达 |
| hard | 远端 A 固定；B 侧 s=1135 mm 抬 30 mm 往外拉 0.55 m；两端拉开到约 1.15 m | 4→1→0，稳定通过；绳总长最大 +1.9 % | 右臂按 A、左臂拉 B；两端拉开右 A 左 B；均可达 |

只动绳的证据与失败轮次见 [README](../../../runs/test_results/knot_object_route_20260930/README.md)；IK 检查见 `runs/test_results/knot_ik_keyframes_20260930/`（`scripts/check_knot_keyframes.py`，竖直下夹、夹指垂直于绳，预抓位与撤离各高 80 mm，查桌面、同臂、两臂与关节限位，绳不作碰撞体）。机器人执行器为 `scripts/run_knot_robot_route.py`，选点规则与只动绳共用 `topogym/planning/knot_untying/route_rule.py`，抓取为纯摩擦（不开抓持辅助）。

**已知边界。** 只动绳的路线用的是 8 边粗网格（约 1.6k 顶点，正式约 3.2 万）并把接触摩擦平滑速度设为 1 mm/s；正式配置未设该参数（libuipc 默认 10 mm/s），此时弯绳以约 3 mm/s 持续蠕动，过不了"最大速度 ≤ 1 mm/s"。机器人执行沿用正式网格与正式接触参数，只把时序改为每物理步 25 ms、40 子步（IPC 积分步长仍为 0.625 ms），原因是正式时序下每模拟秒约 2700 s 墙钟。`KnotUntyingTask.goal_complete=False`，Env 不会报 `task_success`，Harbor 中 knot 的 trial 因而不会判成功；可解性证明直接核对终态判据（无投影交叉/重叠、贴桌、静止、已松手、机器人离开 ≥5 mm、稳定 0.5 s）。


Agent 接入见 [Knot Untying adapter](../../../legacy/cleanup_20260929/docs/develop/modules/knot_untying_agent_adapter_zh.md)：本地文件队列、双臂四图、CUDA FEM 接触辅助与可复制 prompt。该接口的验证状态独立于下述历史 demo。

变体设计见 [固定结型与家族内参数构造方案](knot_untying_family_space_zh.md)：三叶结、开放八字结、双重单结分别作为 easy / medium / hard 的目标代表，每个结型配独立的动作与 IK 路径。三档均要求持续支撑、余量控制和受限方向下的操作；难度须经实际执行及简单路线对照确认，当前 v9 也需补查这一操作要求。新增家族与参数范围目前为设计提案。固定实例可直接选择，参数采样另设入口。

实施与结果见 [物理稳定性验收与三视角全过程 demo 计划](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_physics_demo_plan_zh.md)。已完成 [完整机器人解结录像](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html)，实际连续模拟 75 s，保留五路同步视角。从双手张爪准备位开始，双指接触后使用显式辅助抓持；松手时解除全部约束。本次轨迹的局部物理检查通过，P3 网格收敛及通用双手交接验收仍未通过。详细记录见 [抓持与录像复测](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_recording_attempt_zh.md)。

完整 demo 的 MP4 已按视角独立归档至 `demos/knot_untying/varaition_<id>/<camera>/`；播放页、报告、轨迹和归档清单保存至 `runs/demo_metadata/knot_untying/<date>_<run_id>/`。

本阶段铺设一根绳上只打一次结的场景。采用开放绳的 overhand knot；将自由端从外侧无交叉地闭合后，得到 trefoil / 3₁。物理场景中保留两个自由端，可供后续抓取和退绳。结型参考：[MathWorld](https://mathworld.wolfram.com/TrefoilKnot.html)。

## 几何和配置

源码在 `topogym/tasks/knot_untying/`，Hydra 入口为 `configs/knot_untying_preview.yaml`，基线登记在 `configs/task_cards/knot_untying.yaml`。

| 参数 | 默认值 |
| --- | --- |
| 绳径 | 8 mm |
| 总长 | 约 1.074 m，由曲线和自由端共同决定 |
| 每端余长 | 180 mm，包含平滑转向段 |
| 结形平面尺度 a | 32 mm；参数卡圈径比定义为 2a / 绳径 = 8 |
| 高度幅值 h | 8 mm |
| 初态桌面净距 | 至少 1 mm |
| 网格轴向间距 / 圆周段数 | ≤2.5 mm / 12 |
| 自接触作用距离 | 0.8 mm |
| 材料 | E=100 kPa，ν=0.45，ρ=650 kg/m³，μ=0.3，沿用共享候选值 |
| 材料参考态 | 直绳，初始结形有弯曲预应力 |
| 时间步 / 子步 | 5 ms / 4 |
| 固定或跟随顶点 | 0 |

采用曲线 `x=a(sin t+2 sin 2t), y=a(cos t−2 cos 2t), z=h sin 3t`，截取 `[π+0.5, 3π−0.5]`，升高到桌面之上；两端用切向连续的曲线转向结外，再接直尾。镜像 x 可切换手性。

几何验收检查三个横截交叉、沿绳的交替上下顺序、Gauss 顺序 123123 和一致交叉符号，并确认外侧诊断闭合不添加交叉。因此不是仅凭“有三个投影交点”判断结型。初始管面最小间距使用线段到线段距离；排除沿绳距离小于 πr 的局部邻居，另查局部弯曲半径。

## 运行

Nyx 环境需要额外安装 FEM 接触库；本机补齐的是旧仿真环境已有的同版本：

```bash
uv pip install --python .venv-gs121-nyx/bin/python -r requirements/uv-topogym-fem-ipc.txt
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.knot_untying
.venv-gs121-nyx/bin/python -m unittest tests.check_knot_untying
```

默认输出 [trefoil_initial/index.html](../../../runs/environment_bootstrap/knot_untying/trefoil_initial/index.html)，包含 Nyx 实验室全景、俯视、近景静态图以及自由静置前后状态；不再生成相机环绕视频。`run.settle_steps=0` 仅建场与渲染，不会声明静置通过。

`inspection_report.json` 保存实际求解参数、体网格检查、模拟时长与初末状态；`settle_trace.json` 逐步记录位移与交叉数，`settle_states.npz` 保留实际顶点与中心线。直绳参考态若会翻转四面体，任务在构建前拒绝，不能静默改成结形参考态。

当前预览包含单台待命 Panda＋Robotiq 2F-85；机器人与绳接触已接入，未执行抓取。独立物理探针已加入长时接触检查和 ALOHA 双臂试跑，实际通过范围见上方验收页面。短时预览记录只检查这一初态的有限状态、体单元方向与投影交叉保留，不能代替连续碰撞的全程拓扑认证。

## 本机检查结果

2026-09-16 的默认运行完成 40 步、0.2 s 自由静置。实际体网格包含 6,516 个顶点、21,519 个四面体；直绳参考态和静置末态均无反转单元。三个交叉在每个采样步保留，末态 Gauss 顺序、上下交替和手性复查通过。

最大顶点位移约 37.27 mm，属于初始预弯曲绳的松弛，不能称为静止不动。末态按中心线及名义半径重建的管面净距约 0.48 mm，距桌面约 0.60 mm；这两个数是中心线诊断，不是形变后 FEM 表面的精确碰撞距离。实际报告保存该检查方法和范围。

几何、配置组合、参数卡和当前目录引用共 14 项测试通过；新增 Python 文件通过 Ruff 检查。Nyx 视频已检查为 45 帧、15 fps，只展示初始结形的相机环绕。
