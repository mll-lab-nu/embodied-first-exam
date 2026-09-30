# 刺球出笼

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

下一轮开发要求：[medium 椭圆窗 scripted policy 与全流程验收](hedgehog_claws_scripted_policy_plan_20260927_zh.md)。包含 home 接近、真实抓取、抬升定向、完整出笼、当前目标区终态及机制反例；尚未新增完整成功记录。

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
