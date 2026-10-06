# 第 12 项：长孔立柱解环

> **2026-10-04 代码迁移：** 已迁入外部 12 阶段 oracle、IK/FK、拓扑探针及诊断入口，并将执行改为本地 v15 Session。按用户要求不运行测试或仿真，不修改现有几何、材料、网格、接触、规则或模型修订。外部直立端盘抓取与本地平放初态不兼容，完整入口明确拒绝，首阶段仅供未验证的开发使用。外部检查点续跑成功不授予本地资格。迁入内容、差异、经验和命令见 [oracle 说明](../../../topogym/planning/slotted_post_ring/README.md)。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

> **2026-09-29 更新：** Easy / Medium / Hard 已有独立可构建场景，当前物理途径为 Genesis FEM/IPC。几何与相关回归通过；长时稳定性因 CUDA 显存不足及原生 IPC `cudaErrorInvalidDevice` 阻塞，未通过。见[本轮证据与复跑说明](../../../runs/test_results/slotted_post_tiers_20260929_review/README.md)。下文 2026-09-21 的 MuJoCo 一维绳与 FEM 试验是历史版本，不能授予当前场景资格。

## 当前三档场景与稳定性验收

| 档位 | 家族 | 环内径 | 环外径 | 柱截面径向净空 | 端盘阻挡直径余量 |
|---|---|---:|---:|---:|---:|
| Easy | `large_ring` | 108 mm | 148 mm | 15.374 mm | 2 mm |
| Medium | `middle_ring` | 105 mm | 145 mm | 13.874 mm | 5 mm |
| Hard（兼容 `base`） | `original_scale` | 102 mm | 142 mm | 12.374 mm | 8 mm |

三档共享 28 mm 槽、20 mm 环管直径、110 mm 端盘、7 mm 绳径，以及一次穿槽、右柱外侧返回的连续绳路。端盘限制了可扩大的环径范围，因此这是小幅净空分级，不是已标定的操作难度；较大环也减小了侧立穿槽的高度余量。36 mm 槽仍是独立实验入口，未用于替代 Easy 或 Medium。

两端永久连接到端盘，绳结止挡属于同一 FEM 绳体；珠、盘、环均为自由刚体，只有底座和立柱固定。场景中心为 `[-0.02, 0.04] m`，机器人从 ALOHA home 开始，未启用辅助抓持。材料沿用共享 `stable_neohookean`，E=50 kPa、ν=0.30、ρ=650 kg/m³，`v13_material_mesh` 细网格与 0.2 mm IPC 接触距离；未改动公共材料来强行落稳。

静态检查覆盖封闭网格、真实孔洞、绳—实体与自碰净空、过柱截面与端盘限位关系，以及同 seed 重新生成资产的字节复现。过柱截面关系仅说明绳路允许时裸环可越柱顶；不代表绳与机器人同时存在时的完整解脱路径。

[`validate_slotted_post_scenes.py`](../../../legacy/research_tools_20260929/scripts/validate_slotted_post_scenes.py) 冻结源码后，为三档各执行一次主步长 2.5 ms 和半步长 1.25 ms，均为 4 个求解子步、25 ms 控制周期、seed=0、10 s 连续 home hold。通过现有 `Env`、`SceneEvidence` 与公共 `RecordingSession` 保存四路 Nyx / compact_lab 实际录像、配置、资产、逐 tick 指标和状态样本。

每个 Env 物理 tick 检查有限状态、IPC 有效性、FEM 最小体积比 ≥0.2、两端连接误差 ≤0.5 mm、刚体接触穿透 ≤1 mm、全体任务几何处于桌面范围且无超过 0.1 mm 的桌面穿透。末两秒要求 FEM 最大 / RMS 速度 ≤5 / 1 mm/s，动态刚体线速度 ≤2 mm/s、角速度 ≤0.03 rad/s，所有绳顶点及动态刚体网格顶点漂移 ≤2 mm。两次运行都通过后，比较对应末态顶点，最大差异须 ≤2 mm。IPC 有效性与现有接触诊断不等于独立表面 CCD 证书；采样覆盖物理 tick，不宣称覆盖每个原生求解子步。

```bash
.venv-gs121-nyx/bin/python scripts/validate_slotted_post_scenes.py \
  --output runs/test_results/slotted_post_tiers_NEW --seconds 10
```

当前 `goal_complete=False` 保持不变。场景、静置稳定性、机器人可达/抓持、完整解环、随机参数资格分别记录。

本轮主步长 Easy 审计到 0.1675 s、Medium 到 0.085 s，Easy 半步长到 0.0225 s；均因 CUDA OOM 退出。已提交 tick 内的连接、体积与桌面支撑检查通过，但未进入末两秒落稳窗口。Hard 的本轮短程复验及无 RGB 重试还出现 IPC 原生 `cudaErrorInvalidDevice`，未得到有效物理序列。未修改材料、放宽门槛或清除其他会话 GPU 作业；全部原日志和源码快照保留。Easy/Medium 已录片段仅为失败尝试的场景诊断，四视角链接与配置见本轮证据页。


任务 ID：`slotted_post_ring`。来源是用户指定的 [Puzzle guy 视频](https://www.youtube.com/shorts/yZv8eUWIF-8)，约 50.65 秒。`video_reconstruction_v1` 保留基础几何、穿绳初态和共享 Nyx / `compact_lab` / ALOHA 双臂场景。**2026-09-21：28 mm 原版与 36 mm 候选版均通过 10 秒重力落稳及半步长复验；36 mm 候选版通过 147 秒连续外力驱动的完整解环检查，三视角录像已归档。完整机器人解环仍未通过。**

## 147 秒完整物理流程：36 mm 候选版，通过

**材料版本说明：本节及下列历史录像使用一维长度约束绳，不是 FEM。按用户要求，后续绳模型转向三维体积 FEM，当前接入及验证范围见 [FEM 绳说明](../../../legacy/cleanup_20260929/docs/develop/tasks/slotted_post_ring_fem_zh.md)。新材料不能继承旧模型的通过状态。**

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
MUJOCO_GL=egl .venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.recording_adapter \
  --run runs/environment_bootstrap/slotted_post_ring/my_gravity_probe \
  --output runs/environment_bootstrap/slotted_post_ring/my_gravity_probe/recording --diagnostic
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

## 2026-10-03 below-easy 设定：very_easy / easier

依据 [两档计划](../../tasks_simplifications/two_levels_below_easy_plan_20261001_zh.md)。说明页与图片见 [below_easy_variants_zh.html](../../tasks_simplifications/below_easy_variants_zh.html)。

部件尺寸沿用 easy（环内径 108 mm、长孔 28 mm、端盘直径 110 mm），环开局仍套在立柱根部。环只会被“从环上方跨过”的那段绳困住，因为端盘穿不过环。难度旋钮是绳的走向 `cord_route`：

| 入口 | 别名 | 绳的走向 | 物体层面检查 |
| --- | --- | --- | --- |
| `slotted_post_ring_easy` | `easy` | 穿长孔一次，两侧都从环上方跨过（现有） | 两侧都在环上方 |
| `slotted_post_ring_very_easy` | `very_easy` | `under_ring`：同样穿孔一次、绕右立柱回来，但两侧都从环下方穿出，环压在绳上 | 两侧都在环下方；环沿立柱直接提起 289 mm 越过柱顶，有认证路径（余量 0.2 mm） |
| `slotted_post_ring_easier` | `easier` | `loop_over_ring`：穿长孔两次（定式第一步之后的走向），两个端盘都在近侧、绳在环下方；另一侧带珠 2 的绳圈从环上方跨过 | 近侧在环下方，另一侧绳圈两次跨过环上方且位于两次穿孔之间；直接提环会碰到绳；环推向一侧时与立柱的最大空隙 66 mm，珠 2 直径 39 mm |

绳变长：very_easy 0.92 m、easier 1.24 m（easy 0.79 m）。环抬高到压在绳上（中心高 43.5 mm，easy 为 33 mm）。

代码：[below_easy.py](../../../topogym/tasks/slotted_post_ring/below_easy.py)（两种走向的 layout 子类与 `ring_band_runs`）、[slotted_post_ring_very_easy.py](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_very_easy.py)、[slotted_post_ring_easier.py](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_easier.py)；`common.py` 新增 `make_layout()` 钩子；几何模块把珠的位置和走向检查改为 layout 的方法 `bead_controls()`、`route_checks()`，现有三档的网格、绳和几何报告逐字节不变。检查：[below_easy_witness.py](../../../topogym/planning/slotted_post_ring/below_easy_witness.py)、[test-slotted-below-easy.py](../../../ci_checks/test-slotted-below-easy.py)。

```bash
python -m topogym.planning.slotted_post_ring.below_easy_witness --variant easier --output runs/below_easy/slotted_easier
# GPU FEM 落稳需要 IPC 后端，在 TopoGym 镜像里运行，加 --settle-seconds 2
```

GPU 落稳（TopoGym 镜像 0.2.3-cu128，挂载本分支代码，CUDA，2.5 ms、4 子步，机器人保持 home）：very_easy 落稳 2 s 后，处在环所在高度范围内的绳顶点没有一个在环上方（下方 1414 个），IPC 状态有效，任务未结束；环移动 15.9 mm、倾斜 4°（开局时悬在两股绳上，落稳时一侧落到底座上），绳最大下垂 37 mm。easier 尚未完成：在共享 GPU 上一次显存溢出、一次进程段错误，原因未确定。

边界：物体层面检查把绳当作冻结的折线，不含机器人、IK 与动力学；easier 的“把绳圈连同珠 2 穿下去”没有路径证明，只检查了尺寸关系。

2026-10-06：v18 实例已构建（落稳、精确恢复、无穿透）；very_easy 有机器人 oracle（右臂指尖捏环、直上越柱顶、放入目标区），Harbor 两种模式均评分 1。easier 在现场景下无 oracle：珠 2 沿绳滑动、带不动绳圈，E 50 kPa 的绳一捏即出现反转四面体；把珠 2 固定在绳圈上的方案（a）在实验室三次运行仍失败（珠 2 之后的绳弯一直压在环上），未提交；用户决定 slotted 只交付 very_easy，easier 交给 William / Jianwen。结果、缩短绳圈的 P2 提案与补丁位置详见 [oracle 说明](../../rcb/ORACLE_FIXES_2_FOR_JIANWEN.md) 第 5 节。
