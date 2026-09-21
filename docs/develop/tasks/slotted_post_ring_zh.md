# 第 12 项：长孔立柱解环

任务 ID：`slotted_post_ring`。来源是用户指定的 [Puzzle guy 视频](https://www.youtube.com/shorts/yZv8eUWIF-8)，约 50.65 秒。`video_reconstruction_v1` 保留基础几何、穿绳初态和共享 Nyx / `compact_lab` / ALOHA 双臂场景。**2026-09-21：28 mm 原版与 36 mm 候选版均通过 10 秒重力落稳及半步长复验；36 mm 候选版通过 147 秒连续外力驱动的完整解环检查，三视角录像已归档。完整机器人解环仍未通过。**

## 147 秒完整物理流程：36 mm 候选版，通过

**材料版本说明：本节及下列历史录像使用一维长度约束绳，不是 FEM。按用户要求，后续绳模型转向三维体积 FEM，当前接入及验证范围见 [FEM 绳说明](slotted_post_ring_fem_zh.md)。新材料不能继承旧模型的通过状态。**

`clearance36_full_physics_v1` 从重力落稳后的初态开始，连续完成移珠、端片侧穿柱槽、支撑绳尾并提环越柱顶、木环侧穿柱槽、再次过珠、搬离、放桌面及释放。最后 26 秒全部外力解除，待最后两秒速度达标后结束。无中途任务实体位姿写入、状态重置或不同运行拼接。

这是有力和力矩上限的外力驱动仿真，无机器人。槽宽显式采用独立的 36 mm 建模候选；原版 28 mm 及其历史结果保留。36 mm 不是视频实测尺寸，此结果不提升原版或机器人控制器资格。

| 逐积分步检查 | 最大实测值 | 门槛 |
| --- | ---: | ---: |
| 接触穿透 | 0.2326 mm | < 0.5 mm |
| 绳段相对长度误差 | 0.3592% | < 0.5% |
| 绳端连接误差 | 0.0950 mm | < 0.5 mm |
| 位置跟踪误差 | 2.6098 mm | < 5 mm |
| 最后两秒刚体线速度 | 1.3251 mm/s | < 2 mm/s |

原始验收和独立复核均通过，无引擎警告。最终木环独立落在桌面，环孔绳穿越数为零；整条绳与环的保守表面净距下界为 198.87 mm。完整操作采用 0.125 ms 步长，尚未做完整操作的半步长复验；半步长结论仅针对初态重力验证。

录像由本次实测物理状态重渲染，三路均为 960 × 720、20 fps、2940 帧、147 秒，已验证完整解码、同步与 SHA-256：

- [正面](../../../demos/slotted_post_ring/varaition_clearance36/front_oblique/2026-09-21_clearance36_full_physics_v1_front_oblique.mp4)
- [背面](../../../demos/slotted_post_ring/varaition_clearance36/rear_oblique/2026-09-21_clearance36_full_physics_v1_rear_oblique.mp4)
- [俯视](../../../demos/slotted_post_ring/varaition_clearance36/topdown/2026-09-21_clearance36_full_physics_v1_topdown.mp4)

[验收说明、原始报告及独立资产](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/README.md)保留状态、外力记录、完整动作表、运行开始时源码、可重载模型和实际相机配置。机器人局部执行和未通过的历史尝试另列于下文。

```bash
# 使用已归档的 36 mm 落稳初态与通过检查的动作表，输出到新目录。
.venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.fixture \
  --source runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_gravity_v1/main \
  --schedule runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/main/schedule.json \
  --output runs/environment_bootstrap/slotted_post_ring/my_full_fixture \
  --force-limit 4 --torque-limit .3
```

## 2026-09-21 物理验证

动态模型采用长度约束的一维 flex 绳，保留自碰撞、真实珠孔和柱孔碰撞、两枚可沿绳滑动的自由木珠，以及绳端到圆片外侧绳结位置的两个球铰式连接。基座、立柱固定，木环、珠子、圆片和绳节点均受重力与接触作用。珠子的滑动自由度是当前建模假设；端片碰撞体采用实心圆柱，连接点位于其外侧，视觉绳眼不参与端片碰撞。此模型不是有限元绳，也尚无实物材料标定。

`gravity_stability_v1` 两次独立运行均从同一初态开始，无外力夹持，初始化后不写物体位姿。门槛保持为：最大穿透 < 0.5 mm、绳端连接误差 < 0.5 mm、单绳段长度误差 < 0.5%；最后两秒节点速度 < 3 mm/s、刚体线速度 < 2 mm/s、角速度 < 0.03 rad/s、节点漂移 < 2 mm，且无引擎警告。

| 指标 | 主步长 0.125 ms | 半步长 0.0625 ms |
| --- | ---: | ---: |
| 模拟时间 | 10 s | 10 s |
| 最大接触穿透 | 0.0817 mm | 0.0809 mm |
| 最大绳端连接误差 | 0.00133 mm | 0.00091 mm |
| 最大单段长度误差 | 0.00723 mm | 0.00769 mm |
| 最后两秒节点最大速度 | 0.621 mm/s | 0.195 mm/s |
| 最后两秒节点最大漂移 | 0.0562 mm | 0.0556 mm |
| 结果 | 通过 | 通过 |

实测状态的 MuJoCo EGL 重渲染，三路均为 960 × 720、201 帧、20 fps、10.05 秒：

- [正面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_gravity_stability_v1_front_oblique.mp4)
- [背面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_gravity_stability_v1_rear_oblique.mp4)
- [俯视](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_gravity_stability_v1_topdown.mp4)

[独立物理证据与清单](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_gravity_stability_v1/archive_manifest.json)包含两次运行的状态、报告、可重载模型和代码快照；视频已完整解码并核对同步帧数与 SHA-256。这些视频仅证明重力落稳，不计作完整解环 demo。

解环路径采用有力矩上限的外力夹持验证，36 mm 候选版已通过上述全程检查。端片过孔后的直接提环会留下绳穿环孔，不能以“木环离开立柱”判成功。参考 [Cabalar 与 Santos 的 Fisherman’s Folly 形式化解法（Figure 4）](https://www.ime.usp.br/~logprob/articles/fishermansAIJ-15.pdf)，关键顺序是端片侧穿柱孔、木环越过柱顶、过珠、木环本身侧穿柱孔、再次过珠。`topology.py` 记录沿绳的有向穿孔序列并消去相邻反向穿越；这只辅助判断拓扑状态，不能代替接触、绳长和最终完全分离检查。早期局部外力夹持尝试存在接触/绳长超限。历史 `local_release_attempt_v1` 从中间检查点执行末段退出，接触与绳长检查通过，但位置跟踪误差 9.788 mm 超过 5 mm 门槛，原始总验收仍为 false。

### ALOHA 过珠局部执行

`partial_robot_bead_step_audit_v1` 归档了同一次 25 秒连续动力学执行：左臂扶环、右臂移珠绕柱并落入环内，依次松手、双臂退开，自然落稳 3 秒。初始使用预抓取；左爪与环为辅助 weld，右爪与珠为可转动 connect。它不是纯摩擦抓持，也未完成解环。任务实体初始化后无位姿写入；仅通过原驱动力限制下的 ALOHA 关节执行器驱动。

本次独立复验对每个积分步审计：最大接触穿透 0.3803 mm，未出现超过 0.5 mm 门槛的非抓持接触；最大绳段长度误差 0.1244%、绳端误差 0.0126 mm、辅助珠连接误差 0.00963 mm、末两秒刚体最大线速度 1.226 mm/s。两处辅助连接均已解除，实际限幅后的关节驱动力在模型上限内，无引擎警告，全部局部执行检查通过。原始执行器输出与限幅后关节力单独记录。早期 `partial_robot_bead_v2` 仅对绳长等指标作 20 Hz 采样审计，其录像和证据继续保留。

五路视频均为实测状态重渲染，960 × 720、501 帧、20 fps、25.05 秒：

- [高位](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_high/2026-09-21_partial_robot_bead_step_audit_v1_cam_high.mp4)
- [低位](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_low/2026-09-21_partial_robot_bead_step_audit_v1_cam_low.mp4)
- [左腕](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_left_wrist/2026-09-21_partial_robot_bead_step_audit_v1_cam_left_wrist.mp4)
- [右腕](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_right_wrist/2026-09-21_partial_robot_bead_step_audit_v1_cam_right_wrist.mp4)
- [近景](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_partial_robot_bead_step_audit_v1_front_oblique.mp4)

[物理报告及独立资产](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_partial_robot_bead_step_audit_v1/README.md)包含原始状态、控制、审计和可重载模型。已核对完整解码、同步帧数/时长与哈希。完整机器人 demo 状态仍为未通过。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.probe \
  --output runs/environment_bootstrap/slotted_post_ring/my_gravity_probe --seconds 10
.venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.probe \
  --output runs/environment_bootstrap/slotted_post_ring/my_half_step --dt .0000625 --seconds 10
MUJOCO_GL=egl .venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.render_physics \
  --run runs/environment_bootstrap/slotted_post_ring/my_gravity_probe
.venv-gs121-nyx/bin/python -m unittest tests.check_slotted_post_ring_physics
```

### 末段退出局部验证

`local_release_attempt_v1` 是从中间检查点开始的 20 秒外力夹持运行，不是完整初态到解环，也不是机器人执行。最大接触穿透 0.1647 mm、绳段长度误差 0.1153%、端部误差 0.0401 mm；末两秒刚体速度最大 0.530 mm/s。木环最终落在桌面，环孔无绳穿越，外力已释放。位置跟踪误差 9.788 mm 超过 5 mm，总验收保持未通过。

- [正面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_local_release_attempt_v1_front_oblique.mp4)
- [背面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_local_release_attempt_v1_rear_oblique.mp4)
- [俯视](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_local_release_attempt_v1_topdown.mp4)

[范围、起点来源及证据](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_local_release_attempt_v1/README.md)。三路 960 × 720、400 帧、20 fps，已验证解码、同步和哈希。

### 99 秒连续全路径失败记录

`full_route_attempt_v1` 从基础初态连续执行候选全路径，外力驱动、无机器人。木环最终仍在柱脚，最大接触穿透 0.6125 mm、绳段长度误差 4.466%，未通过验收。这个失败记录保留了从初态到释放的实际过程，不计为成功完整 demo。

- [正面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_full_route_attempt_v1_front_oblique.mp4)
- [背面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_full_route_attempt_v1_rear_oblique.mp4)
- [俯视](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_full_route_attempt_v1_topdown.mp4)

[失败指标及源码快照边界](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_full_route_attempt_v1/README.md)。三路均为 1980 帧、20 fps、99 秒。

### 36 mm 孔宽候选（独立于原版）

为检查木环与两股绳在柱孔处的夹绳问题，另建孔宽 36 mm 的物理候选，保留原版 28 mm。36 mm 给 20 mm 环厚加两股 7 mm 绳的并排通行留出 2 mm 余量，同时仍阻挡 39 mm 木珠；尺寸来自建模设计，并非视频测量值。两者的运行、视频和验证结果分别归档，不互相替代。扩大孔宽本身不能证明可解性。

候选版 10 秒主步长及半步长重力验证均通过，最大接触穿透 0.0712 / 0.0750 mm。147 秒外力驱动完整解环已通过；尚无完整机器人资格。

- [正面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_clearance36_gravity_v1_front_oblique.mp4)
- [背面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_clearance36_gravity_v1_rear_oblique.mp4)
- [俯视](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_clearance36_gravity_v1_topdown.mp4)

[独立报告、尺寸与步长对照](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_gravity_v1/README.md)。复现时在 `probe` 命令中显式指定 `--slot-width .036`；默认仍为 28 mm。



## 端片穿槽与双臂交接：局部机器人记录

两次连续执行均完成端片从柱后进入长槽、右爪交左爪拉出、交回右爪、放桌面和解除全部辅助连接，末段自然静置 5 秒。28 mm 版还包含前置移珠和一次接近受阻后的退避绕行；36 mm 版的前置移珠计划被静态预检拦下，未执行。均使用预抓取与接触后的 weld/ball 辅助抓持，实体初始化后无位姿写入。

| 版本 | 高位 | 低位 | 左腕 | 右腕 | 近景 |
| --- | --- | --- | --- | --- | --- |
| 28 mm / 106.05 秒 | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_high/2026-09-21_partial_robot_disc_handoff_v1_cam_high.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_low/2026-09-21_partial_robot_disc_handoff_v1_cam_low.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_left_wrist/2026-09-21_partial_robot_disc_handoff_v1_cam_left_wrist.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_right_wrist/2026-09-21_partial_robot_disc_handoff_v1_cam_right_wrist.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_partial_robot_disc_handoff_v1_front_oblique.mp4) |
| 36 mm / 83 秒 | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_high/2026-09-21_clearance36_partial_robot_disc_v1_cam_high.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_low/2026-09-21_clearance36_partial_robot_disc_v1_cam_low.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_left_wrist/2026-09-21_clearance36_partial_robot_disc_v1_cam_left_wrist.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/cam_right_wrist/2026-09-21_clearance36_partial_robot_disc_v1_cam_right_wrist.mp4) | [MP4](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_clearance36_partial_robot_disc_v1_front_oblique.mp4) |

局部逐步物理检查通过，环仍未解出，原始总验收保持 false。两次运行的左前臂退臂阶段分别有约 1.235 / 1.238 rad 的关节跟踪误差，因此控制器资格也未通过。源控制输出与实际限幅后驱动力分别保留；不能用执行器未限幅峰值代表实际关节力。

[28 mm 版范围与证据](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_partial_robot_disc_handoff_v1/README.md)；[36 mm 版范围与证据](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_partial_robot_disc_v1/README.md)。录像、轨迹、原始报告、局部复核、运行开始时源码、可重载模型和实际相机配置分别归档，未拼接不同运行。

后续控制器增加了 50 ms 规划采样间超过 0.5 rad 的 IK 关节突变拦截，以及仅供空手退臂的连续关节插值。独立 18 秒探针确认原突变路径在执行前被拒绝，分段退臂完成且局部物理检查通过；最大关节跟踪误差仍为 0.241 rad，因此没有提升完整控制器资格，也没有把探针片段拼入上述录像。该阈值是规划保护策略，不是硬件速度规格。

## 36 mm 候选版完整物理过程录像（第一轮，未全部通过）

`clearance36_full_attempt_v1` 保留了同一次 125 秒连续外力驱动运行：移珠、端片侧穿柱槽、支撑左绳尾并提环越柱顶、环侧穿柱槽、再次过珠、搬离、放桌面和释放。没有机器人或中途任务实体位姿写入；视频由本次实测状态重渲染。

环最终完全解出，环孔无绳穿越，最大接触穿透 0.1864 mm、绳段长度误差 0.3007%、绳端误差 0.0952 mm，无引擎警告。**总验收仍未通过**：木珠放置阶段跟踪误差 5.4069 mm 超过 5 mm；录像复核末两秒左木珠仍在端片上滑动，速度最大 3.8786 mm/s，超过 2 mm/s。不能计为正式完整机器人 demo。

- [正面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_clearance36_full_attempt_v1_front_oblique.mp4)
- [背面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_clearance36_full_attempt_v1_rear_oblique.mp4)
- [俯视](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_clearance36_full_attempt_v1_topdown.mp4)

[范围、原始报告、复核及独立资产](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_attempt_v1/README.md)。三路 960 × 720、20 fps、2500 帧、125 秒，已验证完整解码、同步与哈希。

## 视频中的结构与任务

木制底座上固定一根带竖直长孔的立柱，闭合木环起初套在柱脚。一根连续白绳穿过长孔，回程从柱子右侧绕回；绳的两端分别带有一颗木珠和一枚较大的木圆片。

目标是在不拆开木环、不切断绳、不拆卸端部挡件的条件下取出木环。视频 3–17 秒展示直接提环后仍被绳和端部圆片挡住；18–41 秒涉及重新安排绳套、圆片侧向过长孔；42–50 秒最终取下木环。此处记录可见动作，不把观察到的人类操作视作已验证的机器人轨迹。

建模保留三组关键关系：木环可越过柱截面；木珠可过环而不可过长孔；端片不能直接过环，却可侧着过长孔。立柱孔、木环、木珠轴孔及圆片绳眼均为真实网格孔洞。

尺寸按视频比例人工设定，绝对尺寸未从视频测量。基础版底座 260 × 190 × 22 mm，柱体 72 × 28 × 290 mm，长孔宽 28 mm、总高 204 mm；木环内径 102 mm、外径 142 mm；绳径 7 mm；木珠直径 39 mm；端片直径 110 mm、厚 11 mm。圆片与木珠采用能保留上述通行关系的机器人尺度。

## 2026-09-19 静态版本与验证边界

- 任务已登记为第 12 项，拥有独立参数卡、Hydra 配置、`Layout → SceneBuilder → Scene` 和运行入口。
- 几何生成器输出可重载的尺寸 JSON、连续绳中心线 NPY、封闭 OBJ、内嵌木纹的 GLB、几何报告和 SHA-256。视频分析与未决项见[来源记录](../../../assets/tasks/slotted_post_ring/video_reconstruction_v1/source.json)。
- 几何检查覆盖网格封闭、孔洞、一次穿槽及右侧回程、绳与木件/珠孔/圆片的初态间隙、非相邻绳段间隙及尺寸关系；它们是初态必要检查，不是可解性证明。
- ALOHA 双臂停在 home；所有任务实体固定、任务碰撞关闭；绳只是连续视觉网格，端部绳结是视觉连接标记。初态并非重力静置得到，录像只移动相机，`simulation_steps=0`。
- 尚无柔绳自接触求解、绳端与圆片约束、珠子滑动模型、机器人 IK/抓持/解环控制、成功判据或物理资格。珠子的滑动自由度及隐藏绳结构造不能从视频确定，后续接动力学前需要明确。

独立静态预览 MP4（`static_initial_v1`，不计为完整机器人 demo）：

- [实验室全景](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/overview/2026-09-19_static_initial_v1_overview.mp4)
- [斜前近景](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-19_static_initial_v1_front_oblique.mp4)
- [后侧穿绳视角](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-19_static_initial_v1_rear_oblique.mp4)

[检查报告与独立资产副本](../../../runs/demo_metadata/slotted_post_ring/2026-09-19_static_initial_v1/README.md)保存在配套目录，视频目录仅放 MP4，不生成 HTML。

## 复现

```bash
# 不加载物理后端：导出和校验几何。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.slotted_post_ring \
  run.build_scene=false run.render=false

# 默认 CUDA + Nyx，ALOHA 可见。三视角各 8 秒、15 fps，仅相机环绕。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.slotted_post_ring

# 任务几何、目录元数据和配置回归。
.venv-gs121-nyx/bin/python -m unittest tests.check_slotted_post_ring \
  tests.check_task_baseline_catalog tests.check_configs_compose
```

默认运行产物位于 `runs/environment_bootstrap/slotted_post_ring/static_initial_v1/`。
主配置是 [`configs/slotted_post_ring_preview.yaml`](../../../configs/slotted_post_ring_preview.yaml)，
参数卡是 [`configs/task_cards/slotted_post_ring.yaml`](../../../configs/task_cards/slotted_post_ring.yaml)。
几何参数可编辑，但绳尾排列是固定模板，改尺寸后必须重新通过初态检查；目前无随机实例生成器。

后续需完成全路径的半步长复验，并将已验证的外力解环路径转为双臂连续执行：补齐提环、木环过槽、再次过珠及最终释放，解决交接后的关节跟踪误差。当前端片交接、过珠局部录像及完整外力录像不替代完整机器人执行。
