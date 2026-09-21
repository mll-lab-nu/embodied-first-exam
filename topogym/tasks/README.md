# 当前任务实现

`catalog.py` 登记 13 项任务，任务卡位于 `configs/task_cards/`。
每个任务的几何、场景、执行、规划和判定归入对应子包；共享机器人、物理和数据能力放在公共模块。
当前包不导入 `legacy/`，包入口保持轻量，物理后端按需加载。

- [任务定义、实现入口与变体接口](../../docs/develop/tasks/README.md)
- [当前完成度与验收缺口](../../docs/progress/current_zh.md)
- [当前多视角 MP4](../../demos/README.md)
- [项目架构](../../docs/develop/framework/architecture_zh.md)

运行入口为 `demos/environment_bootstrap/`；任务初始化、几何通过、完整执行和物理资格是不同层级，不能用任务卡存在或 preview 成功替代物理验收。
