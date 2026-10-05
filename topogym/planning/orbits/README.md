# Orbits oracle

移植用户提供的 2026-10-04 Orbits 源码，保留本项目 v15 环境规则。本次仅修改代码，未运行测试、搜索、审计、预览或仿真；来源中的机器人 pass、物体级进度和检查点不属于本项目的验证结果。

本地 easy／medium／hard 的任务参数保持原值：缩放 0.85、模板环半径 0.066 m、柱距 0.082 m、层距 0.068 m、最低环高 0.126 m；compact 绳长 0.80 m、木柄位置 0.41 m。`common.CORD_PROFILES` 仅提取这些现有数值供任务和规划器共用。变体的 `model_revision`、registry、FEM 材料、网格、永久连接、目标区选择及 terminal 均未改为来源版本。

| 模块 | 移植内容 |
| --- | --- |
| `invariant.py`、`topology.py` | 无限球模型自由群词、穿环记录；每个 pass 恰好消去一个 b，且必须匹配预测词 |
| `routes.py`、`bight_search.py`、`ribbon.py` | 绳弯候选、环孔竖直路线、绕行及路径变体 |
| `robot_oracle.py` | carry、helper 托举、双臂环孔交接、套球、整理、pull／unpoke 提取、分片搜索、轮次时间上限及检查点续跑 |
| `aloha_ik.py`、`ik_audit.py` | 连续下探／上升、双臂逐采样碰撞、丰富姿态、竖直撤离、原地等待和重定向 |
| `rope_sim.py`、`stretch.py`、`render.py` | 独立 MuJoCo 绳规划模型、拉伸诊断及工程快照 |
| `local_contract.py` | 读取本地 Task、桌面和机器人 footprint，通过共享 `choose_region` 得到实际目标区；检查完整木柄、绳厚度和本地静止速度阈值 |

规划工具使用保守的本地上限：机器人／夹具及绳模型穿透 1 mm；点抓持误差上限读取 `GraspAssistConfig`（当前 10 mm），单段拉伸读取 `SoftGraspTarget`（当前 1.3），额外保留总长 1.10 的搜索护栏。套球、初始落绳和提取不再使用来源的 6–20 mm 穿透、20 mm 抓持误差或 1.8–2.0 单段拉伸放宽；表面捏取偏移不超过实际绳半径。它们是规划预筛选，不修改 Harbor v15 的接触分级、0.25 s 持续时间判定、2 mm 连接阈值、关节步长、力矩上限或桌面保护。

默认模型始终读取本地 Task。不同的 `ORBITS_SCALE`、`ORBITS_FROM_TASK=0` 或绳长覆盖会被拒绝；检查点保存 `model.json`，恢复时核对模型和护栏身份。来源放大环上的检查点不能直接续跑。IK 审计同样检查记录的本地几何、修订和上限。

模型边界：MuJoCo 一维绳和虚拟点抓手不是 Genesis FEM/IPC 执行，木柄仍使用来源的近似碰撞形状及端点处理，不能核验 FEM 四面体体积和真实双指抓持。提取的几何／速度检查、IK 通过和 `standard_time_scale` 都不代表原生成功；所有模型与审计输出标记 `formal_qualification=False`。原生机器人执行和完整成功仍待实现。

可选依赖为 `orbits-oracle`（MuJoCo 3.14+、Matplotlib），不加入标准环境的物理依赖。入口示例，输出目录须不存在：

```bash
python scripts/plan_orbits_robot_oracle.py easy runs/oracle_dev/orbits_easy_01 \
  --plumb --plumb-first --max-candidates 300 --round-attempts 150 --round-seconds 1500
python scripts/audit_orbits_oracle.py easy runs/oracle_dev/orbits_easy_01 --fixed-arms
```

`--start <本地检查点目录>` 继续同模型搜索，`--shard/--nshard` 分片；`--object-level` 仅启用虚拟点抓手，跳过机器人 IK，仍保留绳模型护栏。保留来源经验：先探测可达深度，规划与审计共用路径／姿态／碰撞口径，交接间距只做排序，昂贵 IK 前做可达性预筛选，超时整理后再搜索，提取先释放木柄提供松弛。

`calibration_tools.adapters.orbits` 与 `scripts/preview_orbits_geometry.py` 保留来源 v8 放大环的独立候选预览；只在临时开发场景内生效，不修改安装的 Task。`CalibrationSession.drive_object_groups` 支持多组 FEM 顶点的有界外力，沿用本地真实 IPC、终止条件、取消和清力；它是明确记录的开发干预，不是正式动作接口或机器人完成。

附件的 14 个草稿脚本放在仓库外的 `/home/jianwen/orbits_solvability_work/imported_20261004/scratch_tools/`，没有运行。探针、复现和编排工具仅供后续研究，未附来源二进制检查点或视频。
