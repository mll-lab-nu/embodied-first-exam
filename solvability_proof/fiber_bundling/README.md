# Fiber Bundling 可解性证明

**easy / medium / hard 的 seed 0 已通过独立审计，三档 3/3。** 从默认 Panda + Robotiq home 连续执行 190.075／344.000／639.125 s，分别核对 7,604／13,761／25,566 个状态；零回溯、完整穿环、0.5 s 稳定，护套接触辅助抓持。

[完整证明、审计结果与复核命令](2026-10-03/README.md) · [机器汇总](2026-10-03/summary.json) · [归档验证](2026-10-03/archive_validation.json)。

本次补审计已有运行，未增加物理执行或录像。easy 原执行为 v3，原实例身份保留，同一轨迹另通过当前 v4；medium／hard 原执行已是 v4。三档均通过原环境资产重建、原 Task 重算、当前 v4 复核及封存 world／动作交叉核对。

资格仅覆盖原冻结 seed 0、CPU64、25 ms／40 子步及 `contact_weld_v1`；不扩展为其他 seed、默认 400 Hz、纯摩擦或 Harbor 正向评分。very_easy／easier 的既有独立成果见[任务页](../../docs/develop/tasks/fiber_bundling_zh.md)，不并入本批三个原变体。
