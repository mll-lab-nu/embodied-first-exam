# physics — 物理模拟与交互

刚体 / PBD 机械臂物理交互实现与仿真稳定性。大任务族（cable_routing / untangle / peeling）各有子目录。

## 通用 / 单篇

| 文件 | 说明 |
| --- | --- |
| `rigid_physical_interaction_zh.md` | 刚体任务（swap / onestroke / maze）真实接触抓取，替代 AttachmentManager |
| `pbd_physical_handle_interaction_zh.md` | PBD 绳索任务从脚本 attachment 改成机械臂物理夹持 |
| `pbd_tabletop_friction_zh.md` | 绳↔桌面摩擦为什么在 Genesis 里失效（速度式 vs 位置式），以及只改速度的库仑摩擦补丁 |
| `rope_backend_migration_zh.md` | 绳索求解器从 PBD 迁到 FEM + IPC：回滚锚点、判据表、各阶段进度 |
| `stacked_plate_physical_interaction_zh.md` | stacked_plate 夹爪-盘缘刚体接触旋转 |
| `maze_wall_removal_zh.md` | maze wall removal（连通性恢复）任务语义与开发记录 |

## 子目录

| 子目录 | 内容 |
| --- | --- |
| [`cable_routing/`](cable_routing/) | MVP 记录、迁移 devlog、全要素建模、路线规划协作、轨迹生成 review（5 篇） |
| [`untangle/`](untangle/) | 重构计划（插头连接器 + 双态 weld）、连接器飞出 debug、PBD segfault debug、连续版方案（4 篇）+ [`debug-log/`](untangle/debug-log/)：连续版抓取时的 PBD 求解发散（已解决）、两根绳互相穿模（未解决），正文与各轮原始 trace |
| [`peeling/`](peeling/) | 单膜物理交互、segfault debug、sticky-tip / kinematic sheet 公约（3 篇） |
