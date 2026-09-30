# 马蹄环

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

更新：2026-09-30。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 当前默认三档的 oracle 与证明工作

当前 easy / medium / hard 分别是 `waist_mild` / `u_mild` / `waist_ellipse`，revision 为 `coupled_shapes_settled_v2`，从桌面物理静置姿态出生。下文 9 月 18–21 日的 F1/F2/F3 视频属于旧的接近方向家族，不能授予当前三档成功资格。

目前按物体路径、机器人 IK、连续物理执行的顺序补充证据，**尚未取得当前版本的完整机器人可解性证明**：

| 检查 | 实际结果与范围 |
| --- | --- |
| 当前资产的物体路径 | easy / medium / hard 的 3393 / 3385 / 3364 段参考运动全部通过自适应连续表面间隙检查，下界分别为 0.050317 / 0.050259 / 0.050100 mm。起点是模板装配姿态，包含初态实体占据检查；尚不覆盖桌面静置初态前缀、实验室障碍和自由链环动力学。 |
| easy 翻转与折合 IK | 已找到保持物体相对路线的双臂联合 IK；784 个加密样本通过本体、双臂、桌面和拼图几何检查。仍是运动学候选。 |
| easy 水平折合与关节余量 | 两手抓外弧、以 18 mm 单指开度接近，避免初始目标环进入夹爪。翻转后将马蹄放平，再允许至多 0.07 rad 倾角，为腕部俯仰留出 0.10 rad 余量；909 个密集原生 IK / 碰撞样本通过，冻结源码重现轨迹最大关节差约 2.6e−15 rad。其他关节的余量不同，见计划中的逐关节数组。 |
| easy 反向路线 | 对参考运动作 y 反射并交换上下链名称后，3393 段物体运动重新通过连续间隙检查；另一组抓点通过 784 个加密 IK 样本。物理执行尚未通过。 |
| easy home → 接近 → 抓取 → 抬升 | 一次连续 900 tick 的实际执行通过独立复核：双指接触触发 `contact_weld_v1`，两件抬高 18 cm，链环连接保持、没有抓持丢失，最大任务接触穿透 0.270 mm。不是完整解题成功。 |
| easy 完整物理折合 | `support_cone_01` 从默认 home 连续抓取、抬升、翻转并走完 3630 帧折合候选，115.925 s 进入 `folded_settle`。完整 7038 tick 独立复核通过历史连续性、双指抓取、链环连接、无抓持丢失，最大任务接触穿透 0.284 mm。交接前再次微调因右腕限位而超时，整段任务尚未完成。 |
| easy 支撑交接与抓环 | `extract_cone_02` 从 home 连续完成折合、释放上件、由下件接触支撑、左手撤离与重新抓环。5499 tick 独立复核通过，逐 tick 检查的 19 对跨物体闭环连接数全部保持，最大任务接触穿透 0.298 mm，无机器人自碰、碰桌或抓持丢失。两手分别只绑定目标环、下件；上件仍是自由物体。 |
| easy 接触取环前缀 | `staged_solve_02` 从 home 连续完成 14 个取环短段，圆环上提时自由上件随接触移动。11984 tick 的接触、抓持和全部闭环连接审计通过，最大任务接触穿透仍为 0.298 mm；尚未完全分离。下一段入口因约 0.04 µrad 的观测关节限位残差被严格规划检查拒绝。后续只读规划种子允许投影不超过 1 µrad 的数值残差，原始观测和物理状态不改写；审计另报告实际关节残差峰值并拒绝超过该界限的运行。 |
| easy 完整取环候选 | `joint_withdrawal_probe_02` 从真实抓环记录构造 106 个位姿的关节空间候选，867 个加密原生 IK / 碰撞检查通过；对当前上件环眼和链环加入连接数筛选。仍允许圆环推动自由部件，因此必须通过完整动力学验证。 |
| 当前衔接缺口 | 圆环在支撑交接后贴住上下马蹄。把上件固定的取出搜索尚未通过；正在检查包含局部接触脱离、允许环推动自由上件和链条的取出候选。取出、固定区域放置与完整成功尚待真实连续执行。原生成功判据继续保持未资格化。 |

物体证据：[easy](../../../runs/test_results/horseshoe_oracle_20260930/object_easy_frozen/object_certificate.json) · [medium](../../../runs/test_results/horseshoe_oracle_20260930/object_medium_frozen/object_certificate.json) · [hard](../../../runs/test_results/horseshoe_oracle_20260930/object_hard_frozen/object_certificate.json)。
机器人证据：[加密 IK](../../../runs/test_results/horseshoe_oracle_20260930/fold_refined_01/dense_ik.json) · [抬升独立复核](../../../runs/test_results/horseshoe_oracle_20260930/pickup_04/independent_audit.json) · [首轮折合中断说明](../../../runs/test_results/horseshoe_oracle_20260930/fold_01/interruption.json)。

正式 CLI 重现结果：[正向规划](../../../runs/test_results/horseshoe_oracle_20260930/oracle_plan_frozen/oracle_plan.json) · [反向物体证书](../../../runs/test_results/horseshoe_oracle_20260930/mirrored_geometry/object_certificate.json) · [反向规划](../../../runs/test_results/horseshoe_oracle_20260930/mirrored_ik/oracle_plan.json)。延长跟踪窗口的 `fold_02` 与小角度重新悬挂的 `fold_03` 均因跟踪超时结束，没有触发资源上限；不能记作通过。重新悬挂、支撑交接接口目前仍属实验诊断。

当前候选：[带关节余量的冻结规划](../../../runs/test_results/horseshoe_oracle_20260930/reserved_oracle_frozen/oracle_plan.json) · [首次完整物理折合记录](../../../runs/test_results/horseshoe_oracle_20260930/support_cone_01/run_report.json) · [独立复核](../../../runs/test_results/horseshoe_oracle_20260930/support_cone_01/independent_audit.json)。该方案只约束双臂持有的马蹄，链与目标环始终服从真实动力学。支撑交接只释放左手并让上件依靠接触落在下件上，不给右手添加第二个焊接约束。在线抓环与取环规划在 `manipulation.py` / `ring_route.py`；取环的初始 3 mm 接触脱离邻域与离散碰撞采样不是连续正间隙证明，须由物理运行单独验收。

实际抓环的证据：[执行报告](../../../runs/test_results/horseshoe_oracle_20260930/extract_cone_02/run_report.json) · [独立复核](../../../runs/test_results/horseshoe_oracle_20260930/extract_cone_02/independent_audit.json)。抓环规划围绕线材切线旋转夹爪方向，以避开支撑手。`ring_route.py` 的接触规划模式将已经释放的上件与两个链环列为可受圆环推动的自由物体；它不改变碰撞、重力、焊接或原生失败判据，也不将该候选写成无碰撞证明。`placement.py` 提供固定区域的后续候选，尚未物理验收。`--withdrawal-mode staged` 每次最多执行 12 mm 已检查的引导段，再按真实被动部件姿态重规划；每段仍检查双臂、桌面和持有的下件，不改变 Genesis 的接触约束。首次 54 样本检查通过仅属于短段运动学候选。

接触前缀的[独立审计](../../../runs/test_results/horseshoe_oracle_20260930/staged_solve_02/independent_audit.json)与[实际物体姿态示意](../../../runs/test_results/horseshoe_oracle_20260930/staged_solve_02/geometry_snapshots/contact_progress.png)已保存，示意图不属于相机 RGB 或完整成功视频。`--withdrawal-mode joint-staged` 将[完整关节空间候选](../../../runs/test_results/horseshoe_oracle_20260930/joint_withdrawal_probe_02/free_ring_transport_plan.json)用作短段引导；放置端另有 2074 样本的绕行候选，均等待实际执行。`joint_staged_solve_01` 在折合中触发 CPU 99.4% 的资源停止，内存当时为 21.4%；[中断记录](../../../runs/test_results/horseshoe_oracle_20260930/joint_staged_solve_01/interruption.json)明确保留未完成状态，不拼接续跑。

`joint_staged_solve_02` 在 16290 tick / 407.25 s 被旧版 CPU 资源守护中断（CPU 99.7%，内存 24.5%），未完成取环；保留[中断说明](../../../runs/test_results/horseshoe_oracle_20260930/joint_staged_solve_02/interruption.json)。实测右手持有的下件随接触载荷偏移约 2 cm，导致随下件更新的引导路径反复移动。当前候选在取环中同时反馈保持右手支撑物，并在短段末反馈停稳；新的 `joint_staged_solve_03` 从 home 执行验证。另有[反向右手抓持的 909 点 IK 检查](../../../runs/test_results/horseshoe_oracle_20260930/opposite_right_grasp_probe_01/audit.json)通过，右腕旋转关节最小余量约 1.36 rad，尚未物理验证。

实现位于 [`topogym/planning/horseshoe_ring/`](../../../topogym/planning/horseshoe_ring/)；当前入口为 [`scripts/run_horseshoe_policy.py`](../../../scripts/run_horseshoe_policy.py)。`--part geometry --reference .../body_poses.json` 复核物体路径；`--part plan --reference .../body_poses.json` 搜索完整折合所需抓点和联合 IK；`--part pickup` / `--part fold` 执行诊断。运行会冻结源码和输入，每秒记录资源用量；按最新资源规则，仅内存达到 90% 时停止本次工作进程，CPU 只监控记录。无 RGB 的 CPU 运行使用 25 ms World tick / 40 子步、JOINT_ABS，IK 只读查询后输出普通关节动作。局部通过不计入 `solvability_proof/`。

`--part plan --retarget-plan .../horizontal_oracle_frozen/fold_plan.json --grasps .../grasp_selection.json --reference .../body_poses.json` 复现上述余量规划；`--part support` / `--part grasp_ring` / `--part extract` 分别追加支撑交接、抓环和取环阶段，均须传入 `--grasps`、`--reference`、`--fold-plan`、`--support-plan`。这些阶段仍按诊断结果报告，尚无固定目标区的完整成功记录。

### 证明结构与验收边界

物体路径证书枚举五个刚体的全部十对组合。每段使用质心线性插值与最短四元数 SLERP；设物体包围半径为 \(r_i\)，单段任一点的位移上界为 \(L_i=\|\Delta p_i\|+r_i\Delta\theta_i\)。在参数子区间宽度 \(h\) 上，中点距离 \(d\) 给出整段表面间隙的数值下界 \(d-\varepsilon-(L_i+L_j)h/2\)。程序递归细分，直到每个子区间都超过 50 µm，或者明确失败。当前距离误差预算 \(\varepsilon\) 为 1 µm；这属于固定网格、指定插值与误差预算下的数值证书，不是浮点区间算术证明。初始实体互不占据另由资产报告检查，不能仅凭表面距离排除完全包含。

机器人阶段另行验证：默认 home 出生、普通控制动作、真实双指接触后生效的单目标辅助抓持、连续 World tick 历史，以及被动部件的接触响应。独立审计逐 tick 重算全部 19 对跨物体闭环连接数，并检查任务物体、机器人自碰和桌面的接触穿透。有限采样 IK 与上述物体证书均不能替代这段动力学证据。

最终还必须实际达到固定目标区：圆环的全部可见与碰撞几何在区内、剩余组件位于分隔面系统侧，并满足速度和持续时间要求。当前尚无这一记录，因此不启用原生成功资格，也不写入正式可解性证明目录。将来须先取得独立审计合格的完整原始目标记录，再绑定几何与目标区身份，最后重新从 home 执行一次原生成功流程；不会追溯修改旧失败运行的标签。

## 任务与实现

双马蹄通过独立链环连接，ALOHA 在重力下翻转、折合、交接、抓环、取出并释放到桌面。使用预抓持及接触确认后的辅助抓持。

源码：[geometry.py](../../../topogym/tasks/horseshoe_ring/geometry.py) · [scene.py](../../../topogym/tasks/horseshoe_ring/scene.py) · [physical_demo.py](../../../topogym/tasks/horseshoe_ring/physical_demo.py) · [gravity_demo.py](../../../topogym/tasks/horseshoe_ring/gravity_demo.py) · [variant_generator.py](../../../topogym/tasks/horseshoe_ring/variant_generator.py) · [variant_pipeline.py](../../../topogym/tasks/horseshoe_ring/variant_pipeline.py) · [agent_adapter.py](../../../topogym/tasks/horseshoe_ring/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/horseshoe_ring.yaml)；场景入口：`python -m demos.environment_bootstrap.horseshoe_ring`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 历史 demo 状态与边界

基础版五视角 113.7 秒；同代码 2 ms / 1 ms 独立完整执行通过。F1 上方接近、F2 外侧接近、F3 后方接近均已补齐完整五视角，分别 129.7 / 125.8 / 119.7 秒；它们来自原成功物理状态重渲染，仅保留原 2 ms 验收范围。

## 变体与下一步

三个接近路线家族，围绕已成功中心做小范围条件采样。variant_generator 产生实例，variant_pipeline 做生成、重载、完整物理验收及拒绝重试。三族各有条件域随机实例通过 2 ms，新随机实例仍缺 1 ms 复验；非圆环形状池尚未开放。

## 当前证据

正式目录：`demos/horseshoe_ring/varaition_baseline/<camera>/`、`varaition_f1/<camera>/`、`varaition_f2/<camera>/`、`varaition_f3/<camera>/`，共 20 份独立 MP4。[全部视角与证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-21_variation_restore_v1/README.md)。F1/F2/F3 低位相机统一移到桌面上方，改善遮挡及落桌画面的可见性；五路使用同一次执行的相同帧与时间戳。


- [2026-09-18_gravity_replanned_v1](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1)
- [2026-09-18_timestep_validation_v1](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_timestep_validation_v1)
- [2026-09-19_variant_generator_v2](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
# 仅产生一个候选实例描述，不运行机器人，不生成数据集或视频。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.variant_generator \
  --seed 42 --family F2 --output runs/variant_checks/horseshoe_seed42.json
```
