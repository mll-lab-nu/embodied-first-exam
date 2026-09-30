# 刺球出笼

**三变体目标进度：1/3 正式完成。** medium 已验收；easy 当前已通过[物体完整路径复核](../../../runs/hedgehog_three_20260930/easy_object_audit_01/object_audit.json)，两种抓法已从默认 home 实际完成双指抓取和约 11.8 mm 抬升，尚无完整抓持出笼路径及全程验收。hard 当前默认初态的球核与笼壁碰撞网格相交，已保存[原初态与无碰撞候选初态对照](../../../runs/hedgehog_three_20260930/hard_initial_diagnostic_01/diagnostic.json)，尚未修改其默认初态或授予资格。本轮曾因旧 CPU 规则暂停，现已按最新“CPU 只监控、内存达到 90% 停止”规则恢复；[恢复点](../../../runs/hedgehog_three_20260930/progress.json)保存未完成项，未将 goal 标记完成。

## 当前纯物体解法

按用户 2026-09-30 最新要求，后续每个变体先汇报不带机械臂的动作分解、关键姿态和几何验证结果，再构思抓取与 IK。物体路线找到后即汇报，不等机械臂全程成功才展示。

easy / `simulator_v1`、默认参数、seed 0 的完整物体路线已通过独立审计。下面的坐标以笼中心为原点，单位为 mm，+X 指向宽度 60 mm 的侧窗；允许直接控制刺球的平移和转动，尚不约束机械臂或抓持。

1. 保持初始朝向，把球心从 `(0, 0, -29.25)` 上移到笼中心 `(0, 0, 0)`。
2. 在笼内多次倾斜和转向，同时向 +X 侧窗靠近，达到约 `(34, 0, -13.09)`。这段包含调整和小幅回退，不能用一次直线平移替代。
3. 先推进到 `(40, 0, -13.09)`，再边转边移到约 `(63, 0, -6.72)`，让球核穿过侧窗。
4. 在窗边继续上抬与转向，球心经过约 `(66.77, 0.72, 27.51)` 和 `(75.17, 4.07, 26.95)`，随后调整高度与朝向，让其余尖刺避开窗框。
5. 从约 `(75, 0.50, 11.44)` 保持朝向向外移动到 `(170, 0.50, 11.44)`，完全离笼；再经笼外 `(220, -283.44, 11.44)` 搬到目标区中心 `(0, -283.44, -41.56)`。

[六个关键姿态图](../../../runs/hedgehog_three_20260930/object_route_report_01/easy_gate_sequence.png)来自实际场景网格和保存的位姿，不是物理执行录像。完整路径有 20 个关键位姿；几何检查覆盖完整可视/碰撞表面、关键位姿之间的连续运动及最终全部尖刺进入目标区，连续间隙下界为 **0.100379 mm**。见[物体路径证据](../../../runs/hedgehog_three_20260930/easy_object_frozen_01/object_witness.json)及[独立复核](../../../runs/hedgehog_three_20260930/easy_object_audit_01/object_audit.json)。这些结果只确立纯物体几何通路，未确立完整机械臂执行。

hard / `fixed_v2` 当前默认初态存在球笼相交，因此尚无从该默认初态成立的纯物体证明。已有的[替代初态提案](../../../runs/hedgehog_three_20260930/hard_initial_proposal_01/proposal.json)采用球心 `(-6, 0, 55)`：先上抬，再边上升边调整朝向，通过顶部钥匙孔，继续升至 z=225 后在笼外搬到目标区。这条条件路线的连续间隙下界为 **1.025754 mm**；默认任务尚未修改，不能计作当前 hard 已通过。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

**2026-09-30：当前 medium 已完成有限实例可解证明。** 四腰窗 `waisted4_dark_wood_v1`、默认参数、seed 0 已通过物体通路、机械臂 IK、默认 home 开始的连续物理执行及独立逐 tick 审计；原生 `task_success=True`，56.5 s，完整刺球在固定目标区低速保持 2 s。完整证据及复现命令见[正式证明目录](../../../solvability_proof/hedgehog_in_cage/README.md)。

物体路径有 7 个关键位姿，初始抬升段连续间隙下界 0.199 mm，后续出笼和入区段下界 1.044 mm。把实测夹爪和腕部加入后重新规划，得到 1,273 个 IK 采样点；实际执行审计的球体运输间隙最小 1.027 mm，机械臂环境间隙最小 2.924 mm。几何证书检查完整可视/碰撞表面并采用刚体运动上界与 1 μm 数值误差预算；不等于连续动力学证明。

使用 Panda + Robotiq、真实双指接触触发的 `contact_weld_v1` 辅助抓持、CPU float64、25 ms tick / 40 子步，无 RGB/视频。纯摩擦抓持、其他 seed、easy/hard 和整个参数域尚未取得此次资格；旧 demos 仅作为解法参考。固定目标区、全尖刺包含、低速保持 2 s 的规则未放宽，允许保留抓持。此前未启用 terminal 的资格运行保留原始 `task_success=False`。

活动入口：[物体规划](../../../scripts/plan_hedgehog_object_oracle.py)、[机器人 oracle](../../../scripts/run_hedgehog_oracle.py)、[独立审计](../../../scripts/audit_hedgehog_oracle.py)。三个入口均冻结源码并保存资源记录，内存超过 90% 时停止本次进程；本次正式复跑峰值为 24.4%。

下文为历史版本记录，六椭圆窗、旧三原型、落桌释放规则和 09-27 搜索失败均不代表当前四腰窗的验收状态。

> **2026-09-27 更新：** medium 已改为深色实木、六个均匀纵向椭圆窗（58×224 mm）的笼体，复用原刺球；原 oblique_gate 描述属于旧版。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。


更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

Panda + Robotiq 将带刺球从木笼开口取出，放桌、解除辅助抓持并静置。基础原型包含 CLASSIC wood，当前生成器采用单斜窗、固定六刺侧孔和 GEN 顶部钥匙孔三个原型。

源码：[geometry.py](../../../topogym/tasks/hedgehog_in_cage/geometry.py) · [scene.py](../../../topogym/tasks/hedgehog_in_cage/scene.py) · [classic_families.py](../../../topogym/tasks/hedgehog_in_cage/classic_families.py) · [prepare_classic_prototypes.py](../../../topogym/tasks/hedgehog_in_cage/prepare_classic_prototypes.py) · [variants.py](../../../topogym/tasks/hedgehog_in_cage/variants.py) · [variant_validation.py](../../../topogym/tasks/hedgehog_in_cage/variant_validation.py) · [agent_adapter.py](../../../topogym/tasks/hedgehog_in_cage/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/hedgehog_in_cage.yaml)；场景入口：`python -m demos.environment_bootstrap.hedgehog_in_cage`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

当前三个有效基础变体各保留完整三视角，分别位于 `demos/hedgehog_in_cage/varaition_oblique_gate/`、`varaition_fixed_side_window/`、`varaition_gen_keyhole/`。2026-09-21 从原完整实测状态补录了单斜窗和固定侧孔，未增加动力学执行成功次数；GEN 原视频迁入对应目录。每个相机叶子目录一份 MP4，直链见 Demo 目录。

## 变体与下一步

v2 支持固定/参数模式、尺寸、位置、朝向、木质外观与保存/重载；随机后代仍是 physical_execution=not_run。侧孔与 CLASSIC 可以共享策略，不要求所有家族的 IK 本质不同。

## 当前证据

- [2026-09-16_classic_wood](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood)
- [2026-09-19_classic_replacements_v2](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_classic_replacements_v2)
- [2026-09-19_generator_replacements_review_v2](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_generator_replacements_review_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 2026-09-27 Scripted policy 首轮实施

新 medium 的反馈执行器与几何搜索已接入，但完整机器人路线尚未建立。六窗对照、8,192 个候选及 12,000 次 SE(3) 搜索扩展未在声明范围内找到完整出笼通路；这不是全局无解证明。当前目标仍要求全部尖刺进入固定区域并低速保持 2 s，正式终态资格未开启。见[实施与证据](../../../runs/test_results/hedgehog_claws_policy_20260927/README.md)及[开发计划实际进展](hedgehog_claws_scripted_policy_plan_20260927_zh.md#11-首轮实施已接入与未通过项)。
