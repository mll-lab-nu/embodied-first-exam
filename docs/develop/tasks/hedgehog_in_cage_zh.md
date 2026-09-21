# 刺球出笼

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
