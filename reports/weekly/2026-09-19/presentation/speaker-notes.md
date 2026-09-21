# TopoGym · 讲者备注与来源

## 01 · Complex spatial constraints.

研究动机：以 complex spatial constraint benchmark 为主线，考察几何、接触和动作次序共同约束下的可执行路径。11 个任务是当前候选池，尚未冻结为最终 benchmark。封面来自工程 demo，不表示受测 agent 已解决。材料沿用 2026-09-19 周报及用户本轮研究讨论。

## 02 · 从两个维度组织任务

这是正在整理的任务提议框架，不是互斥分类。Horseshoe Ring 包含刚性马蹄/环和可动链条，不能笼统视为全部刚性。严格刚体自身几何不变，因此 object–self / rigid 格中仅列待探索的关节化或多部件结构。难度还可能受净空、需要回退的次数、可见性、变形和操作长度影响；这些是候选轴，尚未证明单调难度。

## 03 · 候选任务 · 刚性构件为主

四阶段数值直接读取 reports/weekly/2026-09-19/report.json，与原 progress.svg 保持一致。绿色只表示周报明确限定的实例/协议范围内达到，不代表全族或正式 benchmark 已合格。Horseshoe Ring 包含可动链条。Claws 列表进度含 B0/C0 新物理证据，后面的主展示沿用前版选定的 A0，其资格限制单独标注。工程快照 18:27 CDT；具体更新以周报备注为准。

## 04 · 候选任务 · 可形变物体

四阶段状态与原周报一致。Fiber 三类是按线数划分的稀疏/标准/密集，不要求三类具有本质不同的 IK 策略。Knot v9 有成功解结轨迹，但 P3 网格收敛与通用双手交接未过。Rope 只展示抓取前段。Blanket v10 复杂麻花初态未达到展平成功标准。

## 05 · Cast Coil

Cast Coil — 基础装配。预抓取；双指接触后辅助抓持；装配、放置、松手与静置；基础版双步长证据。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / coil_base；runs/demo_metadata/cast_coil/2026-09-17_aloha_full/archive_manifest.json。

## 06 · Cast Coil · Wrist

Cast Coil — 基础装配。预抓取；双指接触后辅助抓持；装配、放置、松手与静置；基础版双步长证据。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / coil_base；runs/demo_metadata/cast_coil/2026-09-17_aloha_full/archive_manifest.json。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 07 · Cast Keyhole

Cast Keyhole — 基础拆解。预抓取、接触辅助；完整拆解后保持抓持；不含放桌松手。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / keyhole_base；runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/archive_manifest.json。

## 08 · Cast Keyhole · Wrist

Cast Keyhole — 基础拆解。预抓取、接触辅助；完整拆解后保持抓持；不含放桌松手。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / keyhole_base；runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/archive_manifest.json。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 09 · Horseshoe Ring

Horseshoe Ring — 重力修正基础版。预抓持、辅助抓持；交接、取环、自由落桌；基础版 2/1 ms 复验通过。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / horseshoe_base；docs/develop/tasks/horseshoe_ring_physical_ik_zh.md。

## 10 · Horseshoe Ring · Wrist

Horseshoe Ring — 重力修正基础版。预抓持、辅助抓持；交接、取环、自由落桌；基础版 2/1 ms 复验通过。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / horseshoe_base；docs/develop/tasks/horseshoe_ring_physical_ik_zh.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 11 · Hedgehog in Cage

Hedgehog in Cage — 当前家族 B：固定六刺侧孔。预抓取、接触辅助；取出、放桌、松手、撤离和静置。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / hedgehog_side；docs/develop/tasks/hedgehog_in_cage_zh.md。

## 12 · Hedgehog in Cage · Wrist

Hedgehog in Cage — 当前家族 B：固定六刺侧孔。预抓取、接触辅助；取出、放桌、松手、撤离和静置。 
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / hedgehog_side；docs/develop/tasks/hedgehog_in_cage_zh.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 13 · Lock Picking

Lock Picking — 150 mm 两回退基础版。成功物理状态重渲染；被动夹爪连杆按开合量重建；不是新的动力学执行。 被动夹爪连杆按开合量重建；本片不是一次新的动力学执行。新三族仍是 IK 预演，不能继承基础版结果。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / lock_base；runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/result.json。

## 14 · Lock Picking · Wrist

Lock Picking — 150 mm 两回退基础版。成功物理状态重渲染；被动夹爪连杆按开合量重建；不是新的动力学执行。 被动夹爪连杆按开合量重建；本片不是一次新的动力学执行。新三族仍是 IK 预演，不能继承基础版结果。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / lock_base；runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/result.json。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 15 · Interlocked Claws

Interlocked Claws — A0 原版。辅助抓持全过程；原非凸接触资格限制保留；与 B0/C0 的 MuJoCo 证据分开。 沿用此前主展示选定的 A0 基础变体。B0/C0 的 MuJoCo 动力学与双步长验证不能继承到 A0。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / claws_a；docs/develop/tasks/interlocked_claws_zh.md。

## 16 · Interlocked Claws · Wrist

Interlocked Claws — A0 原版。辅助抓持全过程；原非凸接触资格限制保留；与 B0/C0 的 MuJoCo 证据分开。 沿用此前主展示选定的 A0 基础变体。B0/C0 的 MuJoCo 动力学与双步长验证不能继承到 A0。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / claws_a；docs/develop/tasks/interlocked_claws_zh.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 17 · Buzz Wire 3D

Buzz Wire 3D — F3 四关 v3 最新主运行。同一次主物理运行成功；纯摩擦抓持；实测状态重渲染；小步长复验未完成，待归档。 主物理运行 106.92 s，三路视频 106.96 s。仅说明这一原型主运行成功，不代表全族资格已完成。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / buzz_f3；runs/environment-solvability/buzz_wire_3d/family_solvability_20260919/result.md。

## 18 · Buzz Wire 3D · Wrist

Buzz Wire 3D — F3 四关 v3 最新主运行。同一次主物理运行成功；纯摩擦抓持；实测状态重渲染；小步长复验未完成，待归档。 主物理运行 106.92 s，三路视频 106.96 s。仅说明这一原型主运行成功，不代表全族资格已完成。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / buzz_f3；runs/environment-solvability/buzz_wire_3d/family_solvability_20260919/result.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 19 · Fiber Bundling

Fiber Bundling — 8 芯 / R13.5 mm 基础版。实际接触后辅助抓持，只抓粗护套；末态仍夹持；两步长均完成，严格线形收敛未通过。 两档步长均完成穿环但末态仍夹持。只能抓粗护套，不能碰细线；严格全程线形收敛未通过。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / fiber_base；runs/demo_metadata/fiber_bundling/README.md。

## 20 · Fiber Bundling · Wrist

Fiber Bundling — 8 芯 / R13.5 mm 基础版。实际接触后辅助抓持，只抓粗护套；末态仍夹持；两步长均完成，严格线形收敛未通过。 两档步长均完成穿环但末态仍夹持。只能抓粗护套，不能碰细线；严格全程线形收敛未通过。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / fiber_base；runs/demo_metadata/fiber_bundling/README.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 21 · Knot Untying

Knot Untying — 三叶结 v9。连续解结、释放、静置；接触辅助；本轨迹通过，P3 网格收敛和通用双手交接未通过。 75 s 连续解结、释放和静置。本轨迹通过不等于新结型或通用算法完成验收。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / knot_base；runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/README.md。

## 22 · Knot Untying · Wrist

Knot Untying — 三叶结 v9。连续解结、释放、静置；接触辅助；本轨迹通过，P3 网格收敛和通用双手交接未通过。 75 s 连续解结、释放和静置。本轨迹通过不等于新结型或通用算法完成验收。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / knot_base；runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/README.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 23 · Rope Threading

Rope Threading — 最新完成的前段录像。仅抓取、抬升、主动释放和静置；不含三环全过程；完整试跑仍在进行。 视频 29.05 s，只含可播放前段，不含三环完成；不能作为完整任务成功见证。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / rope_prefix；docs/develop/tasks/rope_threading_zh.md。

## 24 · Rope Threading · Wrist

Rope Threading — 最新完成的前段录像。仅抓取、抬升、主动释放和静置；不含三环全过程；完整试跑仍在进行。 视频 29.05 s，只含可播放前段，不含三环完成；不能作为完整任务成功见证。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / rope_prefix；docs/develop/tasks/rope_threading_zh.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 25 · Blanket Flatten

Blanket Flatten — 选定麻花初态 v10：最新未完成。八次保护释放，末态覆盖率 45.4%；2 fps 实测状态重渲染；不是成功展平。 179.5 s，2 fps 实测状态重渲染，八次保护释放。v8 的 75.7% 仍不算成功；旧简单初态的成功不能替代当前复杂初态。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / blanket_latest；runs/environment_bootstrap/blanket_flatten/gathered_robot_study/result.md。

## 26 · Blanket Flatten · Wrist

Blanket Flatten — 选定麻花初态 v10：最新未完成。八次保护释放，末态覆盖率 45.4%；2 fps 实测状态重渲染；不是成功展平。 179.5 s，2 fps 实测状态重渲染，八次保护释放。v8 的 75.7% 仍不算成功；旧简单初态的成功不能替代当前复杂初态。
所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。
来源：demo_inventory.json / blanket_latest；runs/environment_bootstrap/blanket_flatten/gathered_robot_study/result.md。
本页单独展示腕部相机；与前一页主视角来自同一次执行。

## 27 · 先看已有 pilot，再定义正式评测

这是原 slides 第 15 页 token 用量图的 HTML/SVG 重排版。数值直接来自 token_audit.json。Coil 001 4,420,724；Coil 002 69,452,496；Horseshoe 2,819,223；Keyhole 12,487,795；Hedgehog 2,109,472；Lock Picking 3,821,375；Claws ≥23,376,797。结束轮次包含最终答复，进行中的 Claws 是下界。cached input、reasoning output 分别包含在 input、output，不重复加。现有 pilot 未实行实时硬预算，全部受测 adapter 的完整物理资格仍未完成，且部分 session 含旧上下文。不能称作严格 2M/3M 的成功率或 GPT-6 的能力上限；ready 不等于 succeeded。联网约定也不完全统一：非 Coil 禁联网，Coil 允许通用资料但结果称未联网研究。

## 28 · 3M tokens，能走到哪一档难度？

用户本轮提出检验 Astra 在 3M 下能完成什么难度。0.5/1/2/3M sweep 是建议设置，不是既有实验。L1–L3 是校准框架，不能在实测前宣称严格单调难度。当前 bridge v1 文档仍限制累计预算最多 2M，且当前 session pilot 无硬计量；3M 需要后续更新配置/预算上限、外部原生 usage 计量与隔离后另开新 run，本次仅制作 presentation，不修改执行器。离线指 solver 无互联网访问；模型服务请求与本机 bridge 通信单独定义。每次调用前预留 input/output 额度，累计重复上下文也计入；预算耗尽时保留终态。

## 29 · 两种输入条件，分别报告

Track A 不允许访问 simulator 内部，不代表没有环境交互：仍通过统一 action API 执行动作。Track B 提议额外开放物体 CAD/几何、真实位姿、接触等指定字段，但不是自动无限制访问；是否允许查询 simulator、额外 rollout、reset/restore 仍需另列条件并计量。两轨都不自动开放私有参考解和已有 demo。用宿主隔离和工具权限实现边界，不能仅靠提示词。当前 pilot 主要接近 A，但共享文件系统和旧上下文不满足正式隔离要求。

## 30 · 以 segment 为单位，闭环交互

建议目录结构：每个 segments/0001/ 包含 action.py 或 actions.json、trajectory.jsonl、states.jsonl、clips/<camera>.mp4、manifest.json。trajectory 保存实际执行的机器人轨迹，不用命令目标假装已执行。manifest 记录 request_id、起止时刻、步数、相机路径和可公开状态字段；index.json 给出可读目录，不暴露私有 evaluator 数据。模型工具若支持 clip 则按路径读取；否则由 harness 根据时间戳抽帧后作为图像输入，不能假定模型仅收到视频路径就能看见视频。原协议 v1 已有逐 segment PNG frames 与状态，MP4、索引整理和通用 clip 输入是本轮提案。动作不可回滚；每段反馈来自同一连续 episode。

## 31 · 固定场景，比较 success rate

回应 random bar 的笔记，区分随机策略基线和成功率误差棒。Random policy 的动作空间、控制步长、segment 上限与终止规则必须固定；随机动作基线尚未运行，本页不填造成功率。场景 seed 及生成器/资产/初态版本冻结后，所有 policy 使用同一组测试实例；policy RNG seed 与重复次数另行记录。建议使用 95% CI，具体 Wilson 或分层 bootstrap 在样本数确定后预注册。超预算和策略违规属于任务失败类型；基础设施错误不默认为模型失败，要按预先约定的无效 trial 重试规则处理，并单列数量，禁止事后挑选。RL 的训练成本另报，不能和 code agent 的 token 预算直接等同。

## 32 · 三类 policy，同一个 harness

三类 policy 是本轮研究规划，不是已完成的比较。Code agents 最接近现有 bridge 与 pilot。VLA 单独 baseline 与 VLA + code 的组合应分别报告。Pure RL 需要定义训练 split、训练交互成本、奖励和 test 泛化。所有 policy 对齐测试实例、动作空间、初态/抓持规则、成功条件与评测时交互步数；训练 compute、模型调用 token 和 wall time 保持各自可解释的资源报告。A/B 输入轨分别评测，不把有专有信息的 RL 结果直接混入 A 轨。

## 33 · VLA 提议动作，GPT 继续修订

用户提出 VLA roll out 一个 segment，将轨迹以及对应视频/仿真 clip 一起交给 GPT，让 GPT 在其基础上继续 interact/revise。这里默认 segment 已在当前环境执行，GPT 修订的是后续动作，不回滚已经执行的历史。若要让 VLA 在复制 simulator 中生成可编辑候选轨迹，需要独立的 privileged planning 条件和 rollout 预算，不能混到 A 轨。VLA + Code 的实现可行性尚未确认，需先测机器人动作空间、视频输入与轨迹对应关系。仅作为有待验证的 boosting 假设，不承诺提高成功率。

## 34 · 下一步：收敛任务与评测边界

任务保留标准是本轮讨论建议，不是已作出的删除决定。优先考虑约束机制有代表性、能按评测协议完整执行且成功/失败判据可靠的实例；物理数值故障不能当作困难任务。Rope 的完整三环、Blanket 复杂初态成功、Fiber/Knot 严格数值资格等仍需补齐。新加入目录的 Slotted Post Ring 只有静态初态演示且未在 11 任务周报基线中，本次不擅自加进主候选表。建议先做小批固定 seeds、干净 session、严格 offline、3M 硬预算的 Code agent 校准，再决定 task pruning 与 VLA/RL 扩展。

## 35 · 原始四阶段进度图

来源：reports/weekly/2026-09-19/progress.svg；配套数据 report.json。进度均为明确限定实例和协议范围内的状态，不折算为百分比。
