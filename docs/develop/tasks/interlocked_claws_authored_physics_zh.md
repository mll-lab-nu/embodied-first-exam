# Claw B0 / C0 实体与物理验证

2026-09-19 C0 尺寸修订：当前展示基型改为[紧凑等尺寸双窗](interlocked_claws_balanced_gate_zh.md)。两窗外框均为 250 × 190 mm，整体最大尺寸 252 mm，已完成双步长完整物理执行；[近景视频](../../../demos/interlocked_claws/detail/2026-09-19_orthogonal_gate_balanced_physical_v2_detail.mp4)展示新版全过程。下文 C0 大框版是保留的历史验证记录，其不对称尺寸不再作为当前展示基准。B0 不变。

2026-09-19：B0、C0 均完成实体建模、双臂 IK、连续物理执行与半步长复验。两类的动作分别是连续旋拧推进、分段换轴穿窗，结构和动作均有明显差异。

这两套模型是此前概念的工程实现。可见网格由定向盒体做实体并集，碰撞使用同一组盒体，质量和惯量按并集计算。新运行使用 MuJoCo 3.13；原版 A0 的 Genesis 模型、录像和接触资格限制保持独立。所有视频从同次连续物理执行记录的完整状态重渲染，没有拼接不同执行或用运动学预演替代动力学。

[交付清单与视频入口](../../../runs/demo_metadata/interlocked_claws/2026-09-19_bc_physical_release_v1/README.md)汇总两个原型的五视角成片、独立证据副本和 19 项测试记录。

## B0 螺旋冠：已完成

- 六片双层翼片与三条螺旋肋配合，先同步旋转 100° / 上升 40 mm，再抬高、侧向分离。
- 两档物理步长 0.5 / 0.25 ms 均通过完整 ALOHA 执行；末态位置差小于 0.15 mm。
- 两个自由刚体、重力和碰撞全程保留；机械臂保留原有关节力矩上限，包含重力补偿后的总驱动力也通过上限检查。开始时已经抓住物体，使用显式理想焊接辅助，末段解除、张爪、退臂后落桌并独立静置。补充验收与视频运行的全部状态数组逐位相同，末一秒没有机器人接触支撑。
- 固定姿态直推、原地转动、反向旋拧、提前侧拉的物理对照均被阻挡；独立落桌稳定性检查通过。

视频：[全局](../../../demos/interlocked_claws/cam_high/2026-09-19_helical_crown_physical_v1_cam_high.mp4)、[正面](../../../demos/interlocked_claws/cam_low/2026-09-19_helical_crown_physical_v1_cam_low.mp4)、[近景](../../../demos/interlocked_claws/detail/2026-09-19_helical_crown_physical_v2_detail.mp4)、[左腕](../../../demos/interlocked_claws/cam_left_wrist/2026-09-19_helical_crown_physical_v1_cam_left_wrist.mp4)、[右腕](../../../demos/interlocked_claws/cam_right_wrist/2026-09-19_helical_crown_physical_v1_cam_right_wrist.mp4)。均来自同一次连续物理执行，37.05 秒、741 帧、20 fps。近景 v2 只调整相机取景，物理状态相同。

完整副本、可独立加载的场景资产、控制计划、两个步长的状态和报告、几何检查、视频哈希与解码结果：[`2026-09-19_helical_crown_physical_v1`](../../../runs/demo_metadata/interlocked_claws/2026-09-19_helical_crown_physical_v1/)。

## C0 正交双窗大框版：历史已完成版本

- 第一窗口内先绕 x 轴翻转 90°，穿过第一窗、在窗间侧移避让，再绕 z 轴转 90°，对准第二窗后退出；随后双臂分别搬运、放桌、松手、退臂和静置。
- 为使机器人前臂通过，实际第二窗使用更宽、更高且不对称的开口，并增加外部握柄。它保留了概念中的两次换轴机制，但尺寸和行程已不同于早期概念图及 `family_space_v1` 的提案值；最终基准以冻结实体和轨迹为准。
- 两档物理步长 0.25 / 0.125 ms 均完成全流程；最终位置最大差 0.455 mm、姿态最大差 0.00678 rad。两档运行的桌面接触穿透均小于 0.226 mm。
- 两次运行均在末一秒满足独立桌面静置、无机器人接触支撑，两个辅助焊接全部解除；重力补偿计入原有关节力矩上限。最大持物跟踪位置误差 2.87 mm，末态两件间距约 89.7 mm。
- 连续理想件间几何路径、独立重力落桌、正向受力路径和两条固定姿态错误动作对照均通过。有限负对照不证明全局唯一解，也不等于所有随机扰动通过。

视频：[全局](../../../demos/interlocked_claws/cam_high/2026-09-19_orthogonal_gate_physical_v2_cam_high.mp4)、[正面](../../../demos/interlocked_claws/cam_low/2026-09-19_orthogonal_gate_physical_v2_cam_low.mp4)、[近景](../../../demos/interlocked_claws/detail/2026-09-19_orthogonal_gate_physical_v2_detail.mp4)、[左腕](../../../demos/interlocked_claws/cam_left_wrist/2026-09-19_orthogonal_gate_physical_v2_cam_left_wrist.mp4)、[右腕](../../../demos/interlocked_claws/cam_right_wrist/2026-09-19_orthogonal_gate_physical_v2_cam_right_wrist.mp4)。均为 50.05 秒、1,001 帧、20 fps。

完整证据副本：[`2026-09-19_orthogonal_gate_physical_v1`](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_physical_v1/)。

早期候选在低刚度姿态伺服下曾被接触力带动转向，随后脱出。这是被动转向形成的另一条路径，不能称为穿透，也不能声称预设 90° 转向是唯一解。最终版本的错误动作对照明确采用姿态保持条件（角频率 300 rad/s、力矩上限 2 N·m）；正向台架使用 60 rad/s、0.7 N·m，报告分别记录。早期被动脱出结果不作为最终几何已测得的结论。

## 验证范围

| 项目 | B0 | C0 |
| --- | --- | --- |
| 两个连通、水密实体及正定惯量 | 通过 | 通过 |
| 理想件间路径连续几何检查 | 通过，采样最小间隙 10 mm | 通过，采样最小间隙 9 mm |
| 双臂 IK 及机器人碰撞采样检查 | 通过 | 通过 |
| 独立落桌、受力正向路径、错误动作阻挡 | 两档通过，4 条错误路径 | 两档通过，2 条错误路径 |
| 连续机器人动力学、解除抓持及静置 | 两档通过 | 两档通过 |
| 真实摩擦抓取、从桌面自主抓取 | 未验证 | 未验证 |

连续几何证书覆盖作者定义的理想件间路径；实际 IK 路径另做碰撞采样并逐物理步监测接触，不把二者混称为全机器人连续几何证明。19 项相关单元测试通过，包含几何变化不得重用旧 IK、松手后仍靠在夹爪上不能算独立静置等检查。

## 生成器与复用边界

本轮只验证固定基础结构及其控制计划，没有生成数据集或 H5，也没有把尺寸、位姿扰动自动认定为通过。旧 `claw_seed_v1` 是冻结版本，仍保留当时的模型可用性和拒绝行为；新实体不能通过修改旧清单而悄悄替换旧 seed 的含义。

固定结构、抓点、世界摆放、完整关节计划及哈希另存于 [`authored_compound_v1`](../../../assets/tasks/interlocked_claws/authored_compound_v1/README.md)。该版本提供可复跑的基础原型，尚未接入旧 seed API。后续三族随机生成器需发布新版本，对新几何重新求 IK 并逐实例验收；A0 的旧接触限制也仍需处理。

`family_models.py` 提供实体和相对路径，`family_physics.py` 做独立落桌、正向路径和错误动作台架检查，`family_robot.py` 做双臂 IK / 连续动力学，`family_render.py` 只重渲染实测状态，`family_archive.py` 核对双步长、视频和资产副本。运行器拒绝用已经变化的结构、质量惯量或抓持定义重用旧 IK。

从仓库根目录复跑冻结计划（输出必须使用新目录）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.interlocked_claws.family_robot \
  --execute assets/tasks/interlocked_claws/authored_compound_v1/helical_crown/plan.json \
  --dt .0005 --output runs/environment-solvability/interlocked_claws/NEW_B0_RUN

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.interlocked_claws.family_robot \
  --execute assets/tasks/interlocked_claws/authored_compound_v1/orthogonal_gate/plan.json \
  --dt .00025 --output runs/environment-solvability/interlocked_claws/NEW_C0_RUN
```
