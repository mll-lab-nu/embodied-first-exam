# Lock Picking 三变体可解性补充

[2026-09-30：完整机械臂流程与逐动作 IK](2026-09-30_robot_process/README.md)已补齐 easy、medium、hard 默认参数、seed 0 的实际机器人过程。三档均从默认 home 连续执行，包含空手接近、双指抓取、回退换槽、支撑换抓、END 插入、松手撤离和静置，并通过独立逐 tick 复核。

| 变体 | 回退数 | 完整仿真时间 | 执行中的笛卡尔 IK 查询 | 独立流程复核 |
| --- | ---: | ---: | ---: | --- |
| easy | 1 | 124.7 s | 972 | 通过 |
| medium | 2 | 159.2 s | 1,270 | 通过 |
| hard | 3 | 194.7 s | 1,571 | 通过 |

共 3,813 次 IK 查询与 Env 实际执行的关节目标逐条一致；4,789 个保存状态通过关节限位及声明范围内的 FCL 禁碰检查。两次抓取均通过闭爪与原生双指接触自动取得 `contact_weld_v1` 辅助抓持。hard 额外进给 3 mm 以抵消释放回滑，首次余量不足的失败记录也保留。

**资格边界：** 这是辅助抓持下的完整机器人流程证明。当前原 Task 的 `goal_complete=False`，释放后杆靠孔壁，严格正间隙检查仍不通过，三档 `task_success=False`。正式 benchmark 证明数仍为 **0**，不计入全局 `catalog.json`；不声明纯摩擦抓持、多 seed 或连续时间无碰撞。本批为 CPU float32、100 ms World tick／160 子步，显式无 RGB／新视频。

[上一批：物体路径与名义 IK](2026-09-30_object_ik/README.md)保留三档有限厚度孔槽、被动槽壁驱动、限位及 1／2／3 次最少回退证明，以及 5,466 点只读 IK 和历史视频参考。它与本次实际机器人流程分别记录，不能混为同一物理运行。

[实测轨迹图](2026-09-30_robot_process/measured_robot_process.png) · [本批汇总](2026-09-30_robot_process/summary.json) · [完整证据、边界与复现命令](2026-09-30_robot_process/README.md)
