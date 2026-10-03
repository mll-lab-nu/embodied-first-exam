# Rope Threading 简化任务开发控制器

入口：`scripts/oracle_runners/run_rope_threading_policy.py`。
`very_easy` 使用上方敞开的下半圆；`easier` 使用单个完整 R1，并检查双手交接。

控制器从统一 ALOHA home 开始，读取实际绳端位置，以普通 `JOINT_ABS` 指令连续接近、夹取、抬起。
双指接触经共享 `ipc_soft_band_v1` 确认后才能抓持。`ThreadingIK` 使用原生 IK/FK，检查关节限位、
桌面、双臂和场景支架；环的碰撞查询保留原三角网格，不把通孔凸包化。

`--part pickup` 只执行抓取和 40 mm 抬起；`--part solve` 继续执行搭绳或送绳／接绳候选路径。
`--speed-scale`、`--physics-dt`、`--solver-substeps` 都写入报告。更快的开发时序不等于默认物理资格。
`--no-rgb` 明确关闭视频；否则使用共享 SegmentRunner 的四路 Nyx 录制，从 home 起完整留证。

这是尚未完成完整机器人资格验收的开发策略。查阅
[任务页](../../../docs/develop/tasks/rope_threading_zh.md)和每次运行的 `run_report.json`，
不要把 `pickup_passed`、合成状态回归或 `policy_done` 当成原生任务成功。
