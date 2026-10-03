# 当前开发进度（2026-09-21）

> 2026-10-03 Interlocked Claws：交接路线已接入并本地复验，easy / medium / hard 三档 seed 0 均原生成功且独立审计通过，分别为 18.55 / 31.275 / 208.225 s。hard 为两件表面内移 3 mm 的新版本，采用 8 N／0.5 mm 三角深度的显式滑动接触审计；原 hard 不继承资格。三档从任务预抓姿态开始，CPU、双手接触辅助抓持，无新录像；very_easy / easier 保持既有目标。见 [任务页](../develop/tasks/interlocked_claws_zh.md) 和 [完整证明](../../solvability_proof/interlocked_claws/README.md)。

> 2026-10-02 Fiber Bundling：新增 2 根相对的 `very_easy` 和 3 根三角排列的 `easier`，seed 0 均已从标准 home 连续完成穿环并通过独立审计，采用接触触发的护套辅助抓持。两档三路正式录像和四个任务包已生成；默认时序及双模式流程验收见 [Fiber 任务页](../develop/tasks/fiber_bundling_zh.md)。旧三档实例 ID 和资产字节回归不变，难度排序尚未做模型评测。

> 2026-10-02 新增两档变体的专项进度见[两个更简单变体的任务进度表](../tasks_simplifications/two_simpler_variants_progress_zh.md)：覆盖 10 个任务、20 个变体，排除其他成员负责的 Hedgehog、Slotted Post Ring、Horseshoe；按场景实现、机器人成功、录像和双模式验收分别维护。

> 2026-10-02 Lock Picking：双片 `very_easy`／`easier` 本地 oracle 均已从默认 home 实际完成，原生 Task success 分别为 35.6325／48.2575 s，独立逐 tick 审计通过。使用默认时序、CUDA、Nyx 与接触触发的辅助抓持；源码、三视角视频和验证边界见 [Lock Picking 任务页](../develop/tasks/lock_picking_zh.md)。Harbor 双模式完整正向评分未扩大。

> 2026-09-30 Hedgehog：当前四腰窗 medium、默认参数、seed 0 已通过物体通路、机械臂 IK、从默认 home 连续执行及独立审计，56.5 s 原生 Task success。使用接触触发辅助抓持、CPU，无新增视频；见[正式证明](../../solvability_proof/hedgehog_in_cage/README.md)。其他实例与纯摩擦资格未扩大。

> 2026-09-29 Slotted Post Ring：Easy / Medium / Hard 三档场景已接入（环内径 108 / 105 / 102 mm，均为 28 mm 槽），几何、资产复现与相关回归通过。当前 Genesis FEM/IPC 的 10 s 静置及半步长验收被 CUDA OOM / InvalidDevice 阻塞，未标通过；Easy/Medium 仅有失败尝试的短程 Nyx 诊断片段。详见[当前任务页](../develop/tasks/slotted_post_ring_zh.md)与[证据](../../runs/test_results/slotted_post_tiers_20260929_review/README.md)。

> 2026-09-29 Orbits 更新：Easy／Medium／Hard 两／三／四环场景入口已补齐，统一 0.85 比例及 0.8 m 绳长；完整资产、同 seed 重建和 Hard 41 个资产哈希回归通过。已补固定源码、逐 tick 静置指标与四路共享录制的验收入口；当前真实运行受共享 GPU 显存／原生 CUDA 初始化错误阻塞，三档均未取得物理稳定资格。见 [Orbits 当前状态](../develop/tasks/orbits_zh.md)。

> 2026-09-28 证明归档：已建立统一 [solvability_proof/](../../solvability_proof/README.md)，收录 Cast Keyhole 与 Cast Coil 各三档、共 6 个实际 Task success 且独立复核通过的实例。完整复制配置、冻结源码、逐 tick 状态/action 与必要前置证据，逐文件哈希核对通过；原运行保留。每个实例的时序、辅助抓持与有限参数范围见目录说明。

> 2026-09-28 Keyhole 更新：当前统一 Env 的 F1 / easy、F2 / medium、F3 / hard 均已从默认 home，经桌面拾取、两次实际换抓、解锁和固定目标区搬运，返回 `task_success=True`；独立逐 tick 复核全部通过，正式完成 3/3。采用显式 CPU 25 ms tick / 40 子步及双指接触触发的辅助抓持，无 RGB/视频。详见 [Keyhole 当前任务与证据](../develop/tasks/cast_keyhole_zh.md)，不继承下文历史实例的成功标签。

> 2026-09-23 后续状态：下文是重构前的 demo 与任务证据快照，其入口、运行队列及“已接通”结论不代表新核心。当前已整理 Genesis 单后端模块、历史状态 reset 和测试脚本，6 项 Task 已实现、7 项待迁移；测试按用户要求尚未运行，agent/API 延期。请先读[核心重构记录](../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_core_consolidation_20260923_zh.md)和[逐测试脚本说明](../develop/dev-logs/simulator_test_scripts_zh.md)。

按当前工作区（含尚未提交的实现）、任务专属文档、实际运行报告和 MP4 归档核对。任务范围以 [catalog.py](../../topogym/tasks/catalog.py) 的 `TASK_IDS` 为准：原十项任务，加上被子展平、长孔立柱解环、Orbits，共 **13 项**；不包含 legacy 的旧十三项任务。

结论：**13/13 已建立基础场景与任务卡；10/13 已有至少一个实例的完整机器人流程证据；7/13 已有接入共享 seed / EpisodeSpec 的任务级变体接口，其中只有 Keyhole、Horseshoe 已走通随机实例的完整物理验收入口。** 这三个数字分别衡量不同事情，不能相加或解读为全部环境已经完成物理验收。

这里的「基础场景已搭建」指资产、配置、机器人/场景入口已经存在，不等于整个物理参数域合格。「完整流程」采用项目现有实例范围，允许明确声明的预抓取和辅助抓持；成功物理状态的重渲染可以展示原执行，但不增加一次物理成功。静态展示、运动学预演、外力台架和局部动作另记。Agent 自主求解、模型服务及数据集导出不属于本次三项完成度统计。

| # | 任务 | 基础环境搭建 | 完整机器人 demo | 变体生成逻辑与剩余缺口 |
| --- | --- | --- | --- | --- |
| 1 | [双爪互锁 Interlocked Claws](../develop/tasks/interlocked_claws_zh.md) | **已搭建，资格分版本**。A0 独立接触资格仍有缺口；B0 同形双螺旋爪和 C0 固定原型通过双步长检查 | **有**。B0 新版 16.55 s，双臂分离停稳即结束；A0/C0 保留旧完整流程。每族各五视角，均声明辅助预抓持 | **部分接通**。`claw_seed_v1` 可采样、构建/恢复 A0；B/C 仍被旧接口拒绝。新版 B0/C0 尚未接入 seed 生成器，三族随机闭环未完成 |
| 2 | [绳穿环 Rope Threading](../develop/tasks/rope_threading_zh.md) | **五档已接入（10 月 2 日）**。统一 0° 布局、ALOHA 底座垫高 20.9 mm；Very-easy 下半圆搭绳，Easier 单环双手交接。两档评分与可回溯历史已实现；正常 IPC 预热参考错误已修复并通过短程推进，五档 Nyx 静态截图已保存 | **完整机器人解法待验收**。10 月 3 日整合原三档 Wang 接力 oracle，seed 0 物体路径及双臂 IK 分别以 452／466／500 个采样点通过；新两档保留 home 抓取与搭绳／穿环开发控制器。IK 与局部执行不计为物理成功 demo，证据见任务页 | **五档固定场景已有，任务级生成器未完成**。原绳尺寸、材料、FEM 网格与 home 保持；连续可解性、物理资格及难度排序仍待验 |
| 3 | [开锁 Lock Picking](../develop/tasks/lock_picking_zh.md) | **基础实例已跑通**。150 mm 盘距、三齿、两次必要回退的完整物理执行成功 | **有流程证据**。159.35 s 三视角来自成功物理状态重渲染；被动夹爪关节按开合量重建，不能计为一次新的完整物理执行 | **几何/IK 级已接通**。1/2/3 回退家族、固定 S/M/L、seed、确定性重试及保存/重载；256 个 seed 通过几何/IK。新实例的机器人场景碰撞、接触动力学及完整流程资格仍未运行 |
| 4 | [刺球出笼 Hedgehog in Cage](../develop/tasks/hedgehog_in_cage_zh.md) | **基础实例已跑通**。CLASSIC 及当前三个原型有对应场景与执行证据 | **有**。CLASSIC 以及单斜窗、固定六刺侧孔、GEN 顶部钥匙孔均有完整辅助抓持流程 | **几何/IK 级已接通**。v2 使用当前三原型，支持尺寸、位置、朝向、木质外观和保存/重载；随机后代仍为 `physical_execution=not_run`。侧孔与 CLASSIC 可共享策略，不把“三族 IK 必须本质不同”列为缺口 |
| 5 | [光纤收束 Fiber Bundling](../develop/tasks/fiber_bundling_zh.md) | **基础实例已跑通**。固定终端、被动细线、闭环、机器人只抓粗护套的操作链路存在 | **有**。4/8/16 芯、R=13.5 mm 三个密度代表各三视角，按变体/视角分目录；8 芯直接迁移，4/16 芯由各自完整物理状态补录 | **实例/几何级已接通**。稀疏/标准/密集，线数 4–16、R=12.8–15.0 mm，具名 seed、资产、保存/重载。300 个 seed 初态几何通过；随机实例仍需 IK、禁碰、受载稳定性、完整穿环及时间步对照。按已确认要求，密度家族无需不同 IK 机制 |
| 6 | [马蹄环 Horseshoe Ring](../develop/tasks/horseshoe_ring_zh.md) | **基础实例已跑通**。重力、自由链环、双臂交接、取环、释放落桌均有验证 | **有**。基础版 113.7 s 五视角并通过独立半步长复验；F1/F2/F3 已从原完整物理状态补齐五视角，129.7/125.8/119.7 s，新家族仍仅原 2 ms 执行资格 | **受限物理闭环已接通**。三个接近路线家族，围绕各自成功中心小范围采样；生成、重载、完整物理验收、拒绝重试均已实现。三族各有最终条件域随机实例通过，但新实例仅验收 2 ms，未做 1 ms 复验；非圆环等形状池未开放 |
| 7 | [解绳结 Knot Untying](../develop/tasks/knot_untying_zh.md) | **已搭建，完整物理资格未齐**。FEM/IPC、三种固定结型、抓持和换手控制存在；P3 网格收敛及通用双手交接仍未通过 | **有基础版，带验收缺口**。Trefoil v9 连续解结、释放、静置共 75 s，五视角。八字结、双重单结仍是未完成的局部尝试 | **局部参数化已实现**。三种固定模板，`appearance_seed` 可采样形状尺度、yaw、颜色；尺度和 yaw 会改变物理实例。未形成全部结型均能执行成功的统一 seed/验收闭环，目标难度档位尚未标定 |
| 8 | [Cast Coil](../develop/tasks/cast_coil_zh.md) | **基础原型已跑通**。双臂、实体碰撞、装配及释放静置已验证；不等同于官方八步解法复刻完成 | **有，三族视频已补齐**。基础版及三个固定家族各五视角，共 20 个视频；新增三族覆盖完整装配、释放与静置，按各自单次时间步验收，本次未完成成对半步长复验 | **几何/IK 级已接通**。三种固定机构、族内尺寸/位置/yaw、seed、实例重载与拒绝；48 个几何样本、12 个随机双臂规划通过。新代表 6 次物理试验仅 4 次通过严格归档门槛，不能标记三族随机物理资格完成 |
| 9 | [Cast Keyhole](../develop/tasks/cast_keyhole_zh.md) | **当前重建实例已跑通**。原型几何、双臂、接触及实际解锁有证据；不扩大为官方全部路线复现 | **有**。最终 F1/F2/F3 各一个代表、六路同步相机与一份拼屏，共 21 个 MP4，已按变体/视角归档；预抓取、接触辅助、分离后双臂持稳，不含释放。三家族视频从既有成功物理状态补录 | **受限物理闭环已接通**。v2 三机构 × 三外形，固定/参数模式、逐实例 seed、姿态重定向、几何/机器人检查、双步长执行与审计；三个随机实例共六次物理运行通过。每个新实例仍须独立验收，`export_ready=false` |
| 10 | [立体电流棒 Buzz Wire 3D](../develop/tasks/buzz_wire_3d_zh.md) | **三族 home 完整流程已验收**。70% 木质玩具版，实体支撑首尾，默认 home 连续接近、真实拾取与放回；4/2 ms 均通过 | **三族公共实验室最新版**。F1（09-22 起改为三拱，3 拱 2 谷）96.57 s、F2 136.63 s、F3 131.47 s，各三路 30 fps；共享 replay/archive，预穿环无预抓取 | **三套含 home 的完整 IK 已冻结**。F1 三拱版与 F2 均因 home 净空调整摆位后重新验收；参数派生须逐例完整复验，通用随机采样闭环尚未完成 |
| 11 | [被子展平 Blanket Flatten](../develop/tasks/blanket_flatten_zh.md) | **简单初态已跑通**。复杂麻花初态独立稳定性通过，双抓点外力版完成解扭、展开、铺放与 10 s 松手静置，末态覆盖率约 100% | **有简单版**。32.55 s 三视角；复杂版 54.38 s 外力流程通过，七次抓放后的外力整理达到 99.988%。此前 19.55 s ALOHA 录像为局部整理。现已从原始麻花落桌状态和默认 home 连续实测 36.865 s，公共 record 四视角记录抓取、抬升及部分解扭，后段材料拉伸超限，未到解折层；第二轮 34.655 s 实测已让全布离桌 76.8 mm，仍在解扭时拉伸超限。两轮均未到解折层、铺平及最终静置，完整机器人展平仍未完成 | **初态 seed 生成已实现**。折线/折角随机化、拒绝重试及多种固定折叠/卷转配置；复杂版目前只验证一个固定实例的理想抓持解法，尚无随机初态逐例完整机器人展平闭环 |
| 12 | [长孔立柱解环 Slotted Post Ring](../develop/tasks/slotted_post_ring_zh.md) | **已搭建，基础动力学已有验证**。柔绳、自由滑珠、保孔碰撞、端部连接和双步长重力落稳通过 | **机器人未完成；外力版完整**。36 mm 孔候选完成 147 s 连续外力解环；ALOHA 完成过珠、端片穿槽及交接等局部动作。完整外力流程也尚无半步长复验 | **未形成任务级生成器**。原型、36 mm 孔径候选等为人工配置版本，尚无 seed 抽样与可解实例筛选链路 |
| 13 | [Orbits 阶梯解绳](../develop/tasks/orbits_zh.md) | **三档场景已接入（9 月 29 日）**。Easy 两环、Medium 三环、Hard 四环；共用 0.85 尺度、0.8 m 绳及外置木柄。资产、同 seed 重建与 Hard 原资产回归通过；真实静稳验收受共享 GPU／CUDA 初始化阻塞 | **当前三档均无完整机器人解法资格**。历史 75% 器具、1.69788 m 长绳无臂 v2 已完成 93 动作／213 s，证据仍保留原实例含义，不能继承给紧凑绳三档 | **固定三档已有，任务级生成器未完成**。稳定性验收入口已补齐；实际停稳、连续可解路线、机器人可达及难度排序仍待验 |

变体逻辑按能力可以归成四组，避免仅凭 `variants.py` 文件是否存在来判断完成：

| 层级 | 任务 | 当前可承诺范围 |
| --- | --- | --- |
| 生成、保存/恢复、逐实例完整物理验收已连通：2 项 | Keyhole、Horseshoe | 受限家族与参数域；有限样本通过，Horseshoe 新随机实例尚缺半步长复验。均非全域成功保证 |
| 共享 seed/实例接口存在，物理闭环未齐：5 项 | Lock Picking、Hedgehog、Coil、Fiber、Claws | 前三项主要到几何/IK，Fiber 主要到初态几何；Claws 的新版 B/C 原型尚未接入。七项共享接口不是七项可直接发布的物理数据生成器 |
| 任务内局部采样或固定变体：3 项 | Knot、Blanket、Buzz Wire | Knot 有固定结型及局部 seed 参数，Blanket 有随机初态，Buzz Wire 有固定线路原型；三者尚无统一合格实例生成链路 |
| 尚无任务级 seed 生成器：3 项 | Rope Threading、Slotted Post Ring、Orbits | 参数化建模/配置已存在，优先补齐完整机器人执行，再冻结可用变体范围 |

建议按可验收交付安排接下来的工作：

1. **补完整任务流程**：Rope Threading 验证第二环实际绳端反馈换手；Slotted Post Ring 将外力解法转为连续双臂执行；Orbits 已完成指定视频无臂 v2；后续从这条路径重新安排双臂换抓、供绳及共同工作区放置。
2. **收口已有 demo 的关键缺口**：Knot 的网格收敛/换手资格和两个新结型；Blanket 将复杂麻花初态的双抓点外力解法转为机器人抓取和换手；Claws 原 A0 接触资格。Keyhole 的末端释放若作为新要求，应单独立项，当前实例定义止于分离持稳。
3. **补变体物理验收**：Lock/Hedgehog/Coil/Fiber 将现有冻结实例直接交给执行与验收，保留拒绝原因；Claws 发布包含新 B/C 的生成器版本；Horseshoe 补新随机实例的半步长复验。
4. **再扩大变体覆盖**：Buzz Wire 从已验收的 F1/F2/F3 固定 IK 派生，接通随机采样和逐例完整验收；Knot/Blanket 先冻结可成功的家族或初态范围，再统一 seed、完整配置、资产哈希、恢复接口和资格记录。


## 正在推进

- Blanket：Easy / Medium / Hard 的统一聚褶场景及 seed=0 冻结资源已补齐，构形目标 0° / 135° / 270°；三档标准 Env 零推进恢复、关节动作和精确回溯通过，46 项相关回归通过。按用户要求粒子静稳资格暂缓，机器人展平及难度排序待验；实际初态会在放桌后松弛。四视角预览和范围见[三档证据](../../runs/test_results/blanket_three_tiers_20260929_01/README.md)。

- **2026-09-30 Hedgehog：** 当前四腰窗 medium、默认参数、seed 0 已取得原生 Task success 与独立审计通过；从默认 home 执行 56.5 s，接触触发辅助抓持，CPU 无 RGB。见[正式证明](../../solvability_proof/hedgehog_in_cage/README.md)。其他 seed/参数、easy/hard、纯摩擦资格未扩大。
- 2026-09-27 历史批次，Hedgehog / Claws 新 medium：反馈执行器、几何搜索与 Claws 三档 2 s 摩擦持件诊断已实施；完整通路和抓持资格仍未通过，Task 终态未开启。失败记录、回归结果和 Nyx 诊断视频见[本轮证据](../../runs/test_results/hedgehog_claws_policy_20260927/README.md)。

- Rollout：RGB / simulator 工具模式、固定初态 reset、跨 episode 预算和 Bash workflow 已接通；独立模型服务未实现，付费模型成功响应及自主装配仍待验证。见[实用手册](../../legacy/cleanup_20260929/docs/develop/modules/agent_rollout_usage_zh.md)。
- Rope Threading：连续反馈执行已修正接绳/换手自碰，以[当前运行](../../runs/environment-solvability/rope_threading/current_recording.json)为准。
- Knot：倾斜抓取版本继续录制/排队，见[实时状态](../../runs/environment-stability/knot_untying/families_20260919/family_status.json)。
- Slotted Post Ring：体积 FEM 材料已接入，落稳及完整机器人操作待验收。

各任务的当前证据入口集中在[任务说明](../develop/tasks/README.md)；完整视频及验证范围集中在[Demo 目录](../../demos/README.md)。文档整理本身不增加成功或资格计数；新增物理结论以各任务独立运行与验收报告为准。
