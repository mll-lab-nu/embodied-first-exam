# 公共自动抓持辅助：刚体、FEM IPC 与 PBD

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

2026-09-26。对应 [assist 工程计划 §9](../tasks/assist_integration_engineering_plan_20260925_zh.md#9-blanket-初始化之外可以独立推进的-assist2026-09-26-复核)。

2026-09-27：按 [柔体开发计划](soft_grasp_assist_engineering_plan_20260927_zh.md)接入 `ipc_soft_band_v1` 和 `pbd_local_patch_v1`。两者复用当前 Env、自动 manager、SegmentRunner 和 recording；实际资格与剩余限制见计划的实施记录，不继承历史任务成功标签。

独立双手机制及标准 Panda 完整抓放已通过：[FEM 绳报告／视频](../../../runs/test_results/soft_grasp_20260927_fem_robot_02_rgb/README.md)、[PBD 布报告／视频](../../../runs/test_results/soft_grasp_20260927_pbd_robot_09_rgb/README.md)。均从默认 home 运行普通 scripted policy，完成两段 rollout 与回溯，保留 Nyx 三视角。机器人描述未因本轮柔体开发而修改。

FEM 绳现使用共享的 `v13_material_mesh` 默认配方（50 kPa、24 边表皮及细四面体网格），覆盖四类 FEM 绳任务和独立抓放夹具。历史额外阻尼未迁入；`--fem-rope-profile baseline` 仅在独立夹具显式选择旧粗硬试件。迁移范围与验证结果见[默认绳替换记录](../../../runs/test_results/fem_rope_default_20260927/README.md)。本次新共享网格已录到完整抓取／抬升，但完整释放与持握回溯因并行 GPU 显存争用尚未验收；上方既有通过记录不能直接算作新默认试件通过。

## 已实现的工程

首版 `contact_weld_v1` 已接入标准 simulator。管理方在创建环境时固定辅助模型和可抓区域；策略只提交原有夹爪／手臂 action。普通 agent 和 oracle 使用同一套自动取得、保持和释放机制。默认 `none`，没有给 13 个任务批量启用辅助，也没有将历史成功记录转记为当前任务成功。

| 文件 | 已实现内容 |
|---|---|
| [utils/grasp.py](../../../topogym/utils/grasp.py) | 不可变 `GraspTarget / GraspAssistConfig`；原生夹爪坐标归一化；同一接触快照、同一目标 link 的双指筛选；实测相对位姿与误差；空间∩材料邻域选片 |
| [world/physics/grasp_manager.py](../../../topogym/world/physics/grasp_manager.py) | 逐手闭合／张开意图、连续采样准入、候选歧义拒绝、独占 link 归属、取得／保持／释放／失效、事件和 capture/restore |
| [world/physics/grasp_rigid.py](../../../topogym/world/physics/grasp_rigid.py) | Genesis 实际 weld 创建与核查、完整 equality 行迁移删除、取得接触证据、实际指位与相对位姿健康检查 |
| [robot/description.py](../../../topogym/robot/description.py) 及两种机器人 description | 显式两指 link 和原生开／合坐标；ALOHA 是米，Robotiq 是 rad，未复制旧半开度常数 |
| [world/genesis_world.py](../../../topogym/world/genesis_world.py)、[world/state.py](../../../topogym/world/state.py) | 唯一物理生命周期前后钩子、状态导出、原生缓冲与 manager 同步恢复、错误后的 fault 边界 |
| [simulator/config.py](../../../topogym/simulator/config.py)、[simulator/env.py](../../../topogym/simulator/env.py) | 管理方配置、预留动态约束容量、静态公开 action 合同、episode 身份与逐 tick 日志复用 |
| [physics/pbd_initial_state.py](../../../topogym/world/physics/pbd_initial_state.py) | 初态 archive 必须在运行时 manager 配置前导入／导出，防止只保存引擎约束而遗漏抓持逻辑状态 |

代码回收来源固定为 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6` 的 Fiber 接触筛选、Blanket 空间／材料交集、Lock／Coil 的准入过程、共用约束核查。新代码没有从 `legacy/` 或 `runs/` 导入执行实现。

## 配置和策略如何使用

管理方配置示例采用测试专用 `cube_transfer`，须先按 [测试夹具](../../../tests/fixtures/cube_transfer.py) 注册；它不是第 14 个正式任务：

```python
from topogym.simulator import SimulatorConfig
from topogym.utils.grasp import GraspAssistConfig, GraspTarget

config = SimulatorConfig(
    task_id="cube_transfer",
    robot_id="panda_robotiq",
    grasp_assist=GraspAssistConfig(
        model="contact_weld_v1",
        targets=(GraspTarget("cube", "box_baselink", radius_m=0.04),),
    ),
)
```

正式任务需要声明实体名称、可动 link、该 link 坐标系内的球形可抓区域，并实测其机器人可接近性。区域由管理方配置，策略不能在 action 中指定对象 ID、创建约束、改变辅助参数或跳过准入。固定器具、机器人本体和 IPC-only 对象明确拒绝；IPC 场景不支持此后端。

策略仍然写普通 action，例如 Robotiq 已接近目标后：

```python
interaction.step({"arm": {"gripper_position_rad": 0.8}})
interaction.step({})   # 保持已提交目标，继续物理过程
interaction.step({"arm": {"gripper_position_rad": 0.0}})
```

关闭夹爪本身不保证取得。还必须在同一个最终刚体 substep 的接触快照里，两指接触同一个允许的 link，接触点处于声明区域，穿透与 TCP 距离在阈值内，并连续采样满足准入时间。零接触力不自动等于无接触，负 penetration 的分离候选不算接触；不能拿之前左指的一帧与之后右指的一帧拼出取得证据。

2026-09-30：Horseshoe、Claws、Hedgehog、Cast Keyhole 和 Cast Coil 的共享刚体失败规则允许手指与被抓可动零件之间最多 **2 mm** 穿透，与辅助抓取默认准入上限共用常量。纯物理抓取以同一快照中同一只手的两根声明 finger link 接触同一可动任务 link 为依据；已有 `registered` / `holding` 辅助约束时，也允许该手与其已绑定零件的单侧接触。单指触碰、不同手各碰一侧、两指碰不同零件、固定零件均不获得此放宽。其他任务接触，包括零件之间、零件与桌面／手臂／夹爪外壳，仍为 **1 mm**。严格超过对应上限才失败；这不是无限穿透豁免，也不修改物理求解器或夹爪力度。

判定每 tick 重新读取接触与抓持状态，不累计历史接触；失效或释放后的辅助绑定不再提供放宽。五类任务的终止规则版本及实例身份已更新，旧 checkpoint 不能作为新规则实例恢复。`ci_checks/test-rigid-grasp-contact.py` 检查两种机器人的指部识别、1/2 mm 边界、纯物理／辅助抓取、失效与回溯；这是合成接触回归，不代表截图中实际夹持或完整任务已通过。

`action_spec["grasp_assist"]` 公开静态模型／参数；实际候选、owner、接触、约束和失效原因留在管理方或特权 `get("world")` 的 `grasp` 以及逐 tick state sink 中。这里没有新建录像或日志执行循环，SegmentRunner 使用现有证据模块记录。

## 时序、状态和物理模型

1. Env 先完整验证动作并提交机器人目标。非法 action 不改变 manager 或约束。
2. World 推进前读取持续目标；张开意图先移除本手约束。目标省略和 `{}` 不等于释放。开合方向按机器人显式描述解释；小于归一化 deadband 的变化累计到超过阈值后才改变意图。
3. 原有 `scene.step()` 只调用一次。推进后读取最终刚体 substep 接触，更新准入／健康，创建并查询实际约束。
4. 本 tick 新建约束标记 `registered`，事件记录下一 tick 的生效时间；之后才记 `holding`。Task update、原生缓冲、manager 与逐 tick 日志沿原有路径保存。

在刚体模型中，两手各持一个 link；同一个 link 同时被两手申请时两者都拒绝，避免遍历顺序决定归属。同 link 交接仍未开放。柔体模型改为材料区域归属，见下节。

保持阶段检查约束实际存在、取得时相对位姿的误差，以及实际手指相对取得时异常张开。不要求每 tick 有正接触力，因为 weld 可能承担载荷。失效后解除并锁住重新取得，必须先重新张开再闭合。该模型是**理想六自由度保持**，没有经过验证的握力／抗扭上限，`reaction_force` 返回不可用的 `None`，没有伪造力值。

没有 `set_pos / set_quat / set_particles_pos` 吸附，也不替策略执行 IK。物体与环境的碰撞保留。Genesis 1.2.1 非末尾删除适配复制全部五项 equality 数据，而不是仅复制 `eq_type`；静态行不删，其他手的约束不撤销重建。适配受版本、字段集合和单环境布局检查保护，未修改已安装 Genesis 或全局 patch。

读取、渲染、开始／结束 segment 不推进 manager；跨 segment 持握继续。rewind 先恢复原生缓冲，再恢复候选、计时、意图、归属、相对位姿、指位和事件并核对真实约束，不重新选点或重新捕获姿态。reset 在新场景清空辅助；初始化准备期间不自动焊接。

## 柔体模型与材料声明

```python
from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget

assist = GraspAssistConfig(
    model="ipc_soft_band_v1",  # PBD 布选择 pbd_local_patch_v1
    targets=(SoftGraspTarget("soft"),),
    stable_time_s=0.03,
)
```

`SoftGraspTarget` 由管理方固定实体和可选 `material_min_m/material_max_m`：FEM 绳是一维弧长，PBD 布是二维、以米计的材料 UV。空 bounds 允许整实体，但永久 stitch／出生时固定粒子不允许成为临时抓点。`spatial_radius_m` 与 `material_radius_m` 取交集，`contact_distance_m` 是双指表面邻近阈值，`max_strain_ratio` 是材料边长保护阈值。`strength` 仅供 IPC SoftPositionConstraint 使用，PBD 是原生运动学附着。

选片尺寸需要匹配真实夹口。独立 PBD 夹具使用 `SoftGraspTarget("soft", spatial_radius_m=0.006, material_radius_m=0.009)`；14 mm 半径在此小夹口中会把夹爪外侧布面也约束住，实测继续闭合时触发拉伸保护。此处调整材料选区，没有放宽应变、穿透或跟随阈值。

FEM 实体继续声明已有 `volume_path`，不更改体网格生成器。PBD 布需要 `EntitySpec.material_map_path` 指向 NPZ，包含 authored 出生世界坐标 `vertices (N,3)`、三角形 `faces (F,3)`、材料米制 `uv (N,2)`。build 后以重心坐标映射真实物理粒子，验证到表面的距离与重合层歧义；不能从已变形 XYZ 猜 UV。可参考 [独立材料夹具](../../../tests/fixtures/soft_grasp.py)。

准入读取现有机器人描述指定的两根 finger link 的真实碰撞三角面，检查同一时刻的双侧邻近、指内穿透、局部材料连续性和区域歧义。证据明确标为 `ipc_bilateral_finger_surface_proximity` 或 `pbd_bilateral_finger_surface_proximity`，不表示测得夹持力。两手可持同一实体的不同索引区；重叠区同时申请拒绝，已有 owner 优先保留。取得时保存当前材料形状相对实际 hand link 的局部偏移，跟随实测手姿态。

双侧证据属于同一局部材料片，允许两指靠近该片的不同顶点；不要求一个顶点同时贴近两指。材料已超过应变阈值时拒绝取得，避免将已损坏形状注册后再立即释放。

运行时实现分为共享的 [grasp_soft.py](../../../topogym/world/physics/grasp_soft.py)、[grasp_ipc.py](../../../topogym/world/physics/grasp_ipc.py)、[grasp_pbd.py](../../../topogym/world/physics/grasp_pbd.py) 和只读 [grasp_geometry.py](../../../topogym/robot/grasp_geometry.py)。IPC 在建场前预留约束，在原生 animator 中合并所有活动带；PBD 使用 `fix_particles_to_link/release_particle`。manager 的意图、失效锁存、事件和唯一物理时钟保持一致；rewind 恢复原生数组和所有选区、owner、offset 后再核查，不重新抓取。

PBD 适配固定于 Genesis 1.2.1：原生 `LegacyCoupler` 的附着速度混用了 root COM 与 link COM 参考点；场景内仅对本后端拥有的粒子补上 `omega × i_pos`。该钩子在原生 coupling 后执行，不新增物理步、不设置粒子位置、不修改已安装引擎；状态仍由现有 World checkpoint 保存。引擎原有附着速度晚一个子步的时序限制仍存在。

PBD `free=False` 粒子不再响应内部材料约束，但该版本原生刚体碰撞仍会移动它们；因此不能视为有碰撞响应的柔顺夹持。当前实现提供每个 World tick 的凸刚体穿透检查、跟随误差和材料拉伸保护，触发后释放并锁存失效；这不等于连续碰撞检测或物理受阻保持。遮挡检查采用重力向上的局部层判定，任意姿态复杂叠层尚需专项资格。两模型都没有标定握力输出，`reaction_force=None`；默认仍为 `none`。

独立运行命令：

```bash
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cpu --case pbd-mechanism --output runs/test_results/pbd_mechanism
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-mechanism --output runs/test_results/fem_mechanism
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case pbd-robot --output runs/test_results/pbd_robot
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-robot --output runs/test_results/fem_robot
```

GPU case 应串行运行。mechanism 是显式机械夹具、无 RGB；robot 默认使用标准 Panda/Robotiq、默认 home、普通 EE action、Nyx 三路录像和两段 `run_policy`。`--robot aloha` 可选择 ALOHA，`--no-rgb` 明确关闭录像用于物理诊断；是否通过分别查看该次报告。测试不加入正式任务 registry。输出包括独立源码快照、引擎哈希、报告、逐 tick 物理状态与失败原因；新运行还保留生成资产与其哈希。

## 验收入口与剩余工作

[test_grasp_assist.py](../../../legacy/research_tools_20260929/scripts/test_grasp_assist.py) 在独立源码副本中执行，记录源码哈希、引擎身份、pytest 日志、失败与逐 tick 数据：

```bash
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py \
  --device cpu --output runs/test_results/grasp_mechanism_cpu
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py \
  --device cuda --output runs/test_results/grasp_mechanism_cuda
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py \
  --device cuda --case robot-cube --output runs/test_results/grasp_robot_cube
```

mechanism 使用明确标注的双夹爪／方块测试场景、正常重力和无 RGB 的物理路径，测试独立释放、阻挡、rewind、非法动作和后端部分失败。robot-cube 复用现成的标准方块策略，使用实际 Panda／Robotiq、Nyx + compact_lab、两段执行与公共录像。两者均不是 13 个拓扑任务的完整 solve。

当前首批任务接入仍需 Task 负责方提供／验收抓持区域和接近动作；没有自动删除各任务的 assist 资格缺口。柔体独立夹具与正式任务资格分别报告。

当前合同／单元回归为 **185 passed**；CUDA 机械夹具的 11 类检查通过，详见[验收报告](../../../runs/test_results/grasp_assist_20260926_04_cuda/README.md)。CPU 较早版本和 CUDA 当前核心的源码身份分别保存，不混为一次测试。

实际 Panda／Robotiq 的两段方块抓放也已通过，见[机器人验收报告](../../../runs/test_results/grasp_assist_robot_20260926_02/README.md)和[抓取抬起视频](../../../runs/test_results/grasp_assist_robot_20260926_02/evidence/trail/segment_1.mp4)、[搬运释放视频](../../../runs/test_results/grasp_assist_robot_20260926_02/evidence/trail/segment_2.mp4)。514 个物理 tick 保存了 515 份状态，段间抓持延续、边界三路 RGB 相同，帧索引与视频哈希核查通过。方块抬高 94.904 mm、空中搬运 201.083 mm、最终平面误差 0.177 mm，张爪撤手后放稳；这只证明共享抓放链路通过，正式任务的可解性仍需单独验收。

World/state 源码变化会使旧 Blanket 冻结初态的严格源码身份失效。当前 Blanket 默认仍是 `authored`；试验用冻结资源需在新源码下重新导出和资格复验，不能放宽哈希校验继续复用旧资格。
