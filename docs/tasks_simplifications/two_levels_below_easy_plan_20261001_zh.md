# 三个任务新增 very_easy / easier 变体

日期：2026-10-01。本文供任务开发成员参考，说明大概目标和代码边界，具体场景由实现者设计。

本轮 pipeline 修复对实例冻结、动作计时、判据版本及验收的具体影响，见[场景调整与低难度变体开发注意事项](post_fix_scene_variant_guidelines_zh.md)。

## 1. 要做什么

先从 **Hedgehog、Horseshoe、Slotted Post Ring** 开始，每个任务新增两个比当前 easy 更简单的变体，保留原 easy / medium / hard。

| 变体 | 大概目标 |
| --- | --- |
| `very_easy` | 主要考察机械臂找合适角度接近、抓住目标物、取出并搬运的能力，尽量减少抓取后的解谜操作。 |
| `easier` | 在上述基础上增加少量约束，让机械臂抓住物体后需要调整角度或方向，再完成取出和搬运；整体仍比当前 easy 简单。 |

预期难度关系为 **very_easy < easier < easy**，实际效果需要完成场景后验证。

**具体怎么布置由实现者决定。** 可以根据任务特点调整几何、尺寸、障碍数量和初始摆放，不限定某种结构、旋转角度或动作顺序。Horseshoe 和 Slotted Post Ring 只需围绕上述两档能力目标设计，不预先指定场景方案。

入口统一命名为 `<task_id>_very_easy` 和 `<task_id>_easier`，其中 task_id 为 `hedgehog_in_cage`、`horseshoe_ring`、`slotted_post_ring`。

## 2. 只举一个 Hedgehog 例子

- **very_easy：**把笼子做得更敞开，或让柱子更稀疏，使机械臂能够找好接近角度、伸入夹爪、抓住刺球并直接拿出来，再搬到目标区。
- **easier：**增加一点出口约束。例如刺球直接往外拉时，两根长刺会被柱子挡住；机械臂需要在抓住后转一下刺球，调整方向再取出。

这个例子只说明两档的能力区别，不要求照搬。柱子怎么排、刺多长、出口多大，都可以由实现者结合夹爪和实际可达性决定。需要给“抓住后的夹爪和物体一起通过”留出空间。

## 3. 代码和素材放在哪里

注意区分：**`topogym/tasks/` 是任务源码，根目录 `tasks/` 是生成后的 Harbor 任务包。** 新变体先在源码和素材层实现，再通过公共工具生成任务包。

| 范围 | 可能需要的改动 |
| --- | --- |
| `topogym/tasks/<task_id>/` | 新增 `<task_id>_very_easy.py`、`<task_id>_easier.py`；按需修改同任务 `common.py` 或增加任务内辅助模块，处理场景、初态、抓持和目标适配。 |
| `topogym/assets/geometry/` | 按需修改对应任务的几何生成器，或新增该任务的简化构造模块。 |
| `topogym/assets/resources/variations/<task_id>/` | 放新变体需要随安装包提供的模板、姿态、网格等素材；同步更新 `topogym/assets/resources/catalog.json` 的资源登记和哈希。 |
| `topogym/config/variation_records.py` | 登记六个新入口，保留原入口和 `base` 的含义。 |
| `configs/`、`topogym/tasks/goal_description.py` | 如配置或公开任务说明受场景变化影响，作相应更新。 |
| `topogym/planning/<task_id>/`、`scripts/oracle_runners/`、`ci_checks/` | 如需参考策略、执行入口或回归检查，放在这些现有目录中，复用公共执行和录制能力。 |
| `scripts/topogym_mk_task.py`、`scripts/topogym_mk_limited.py` | 使用现有生成器制作 privileged / standard 两种模式的任务包，正式交付时登记到 `tasks/dataset.toml`。 |
| `runs/test_results/` | 保存本次构建和验证产物；实现说明可补充到本目录及各任务现有文档。 |

几个需要保留的工程边界：

- 正式运行所需素材放在包内资源目录，不能只放根目录 `assets/tasks/` 或依赖历史 `runs/`；活动代码不导入 `legacy/`。
- 新变体有独立参数、资源和版本身份，不覆盖旧 easy 的素材或借用旧实例的成功记录。新增文件不受历史“每任务只保留三个难度入口”的收敛安排限制。
- 修改同任务共用代码时，保留旧变体的行为。若简化场景需要不同的几何校验或目标适配，限定在新变体内，并让公开说明与实际判据一致。
- 当前 `seeded` 和批量评测按 easy / medium / hard 三档采样。新变体可先作为独立具名入口接入；若要自动跑五档，再协调修改 `topogym/config/registry.py`、`scripts/sample_difficulty_instances.py`、`scripts/difficulty_eval.py` 及相关结果处理，保留旧 seed 的含义。

素材打包仍需检查 `pyproject.toml`、`.dockerignore` 和镜像实际内容；现有包内 variations 目录已有打包规则，通常无需另建资源通路。更多背景见[变体部署记录](../develop/tasks/variation_deployment_implementation_20260925_zh.md)和[仓库规则](../../AGENTS.md)。

## 4. 与 pipeline debugging 的关系及交付目标

**场景建模可以独立推进，但不能保证 pipeline 调试对运行和评分完全没有影响。** 任务专属几何和素材由变体开发成员负责；共享 simulator、World、`topogym/tasks/base.py`、公共判据、Harbor 模板及打包工具可能同时在修复中。需要动到这些公共文件时，与 pipeline 成员协调，避免互相覆盖。

继续使用统一 Env、控制、录制和评分流程。新变体完成后，用包含新代码和素材的运行版本重新生成任务包并验证；旧包和旧镜像不会自动获得新变体。相关工作见[pipeline 修复计划](../rcb/run_trials_post_merge_repair_plan_zh.md)。

交付时，提供六个可选择的变体、每个场景的简短说明，以及能看出接近、抓取、必要调整和搬运过程的运行证据。重点确认场景可达、能完成任务，两档确实体现上述能力区别；区分“已建好场景”和“已完成真实机器人验证”。不需要提前锁死所有尺寸和操作步骤。
