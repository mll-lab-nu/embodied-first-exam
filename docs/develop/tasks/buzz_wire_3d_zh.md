# 3D Buzz Wire：紧凑单臂场景

2026-09-21 变体交付沿用已设计的固定构型，统一按 70% 缩放及当前玩具版材质处理；新版 F2 的完整 demo 已完成。现有基础布局 / F2 / F3 的尺寸与外观改版均已落地，后续补齐各固定实例的执行验证；本轮不以通用随机生成器或参数随机化为完成条件。F1 双拱仍需按已有设计落实场景。详见[当前变体范围](buzz_wire_3d_family_space_zh.md)。

2026-09-20 **F2 紧凑玩具版已完成全流程验收**：`F2_compact_toy_s70_v2` 保持原预览的尺寸、摆位及抓持点，连续通过三连回折 → 错层八字 → 竖直 W，末端松手、撤臂并稳定静置。13549 点连续 IK 检查与 4 ms / 2 ms 两轮真实摩擦抓持执行通过；受控通行均为零触线，两轮最大位置差 0.115 mm。三路来自同一次主运行的实测状态重渲染，各 **103.04 秒、2576 帧、25 fps**：[全景](../../../demos/buzz_wire_3d/agentview/2026-09-20_F2_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F2_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/wrist/2026-09-20_F2_compact_toy_s70_v2_full_wrist.mp4)。从预穿环 / 预抓取开始，不包含桌面拾取及初始穿环。

[物理验收及归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-20_F2_compact_toy_s70_v2_full/README.md) · [可复用 IK 种子与复现](../../../assets/tasks/buzz_wire_3d/F2_compact_toy_s70_v2/README.md)。资格仅覆盖此 F2 实例与控制策略；基础布局及 F3 的 70% `toy-v2` 实例仍未完成机器人全流程验收。

2026-09-20 按第二张实物照片更新为 `*_compact_toy_s70_v2`：浅木底座改为削角、两层收边；使用连续木纹和小方木线脚，移除拼接色带及深色球形支座。轨道改为铜色金属丝，套环为银色金属并保留木柄；场景不含电路板、电池或接线摆设。迷宫尺寸和关卡结构保持上一版 70% 紧凑布局。新版[配置](../../../configs/buzz_wire_3d_compact_toy.yaml)、[三视角和验证](../../../runs/demo_metadata/buzz_wire_3d/2026-09-20_photo_toy_s70_v2_scene_preview/README.md)；斜前预览：[基础](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_baseline_compact_toy_s70_v2_scene_preview_front_oblique.mp4) · [F2](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F2_compact_toy_s70_v2_scene_preview_front_oblique.mp4) · [F3](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F3_compact_toy_s70_v2_scene_preview_front_oblique.mp4)。三个完整工具几何检查与 29 项回归测试通过；这些视频为静态外观预览；其中 F2 的后续完整执行见上方新归档，其余实例尚未验收。

以下为同日第一版尺寸收缩记录；目前外观以 `toy-v2` 为准，`wood-v1` 配置和视频保留。

2026-09-20 新场景采用 **70% 等比例迷宫 + 双色木质支撑 + 银色金属丝 + 木柄铜环**。基础布局与 F2 底座为 **520.1 × 368.9 × 17.5 mm**，F3 为 **520.1 × 385 × 17.5 mm**，占地减少 51%，线路缩短 30%，保留各自关卡数和顺序。圆环、连接杆及握柄同步缩小，机械臂保持原尺寸；新增木质端柱有实体碰撞。基础布局不等同于提案中的 F1 双拱。

新版[配置](../../../configs/buzz_wire_3d_compact_wood.yaml)和[启动入口](../../../demos/environment_bootstrap/buzz_wire_3d_compact_wood.py)已落地。三个布局的完整工具几何检查通过，28 项回归测试通过，基础场景完成 100 步加载 / 自由落体检查。**这些是场景改版验证，尚未完成新版连续 IK 与完整摩擦抓持物理执行**；沿用原姿态的机器人采样检查存在局部碰撞，不能继承旧版通关资格。详情及三视角：[新版报告](../../../runs/demo_metadata/buzz_wire_3d/2026-09-20_compact_wood_s70_scene_preview/README.md)。外观预览：[基础](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_baseline_compact_wood_s70_v1_scene_preview_front_oblique.mp4) · [F2](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F2_compact_wood_s70_v1_scene_preview_front_oblique.mp4) · [F3](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F3_compact_wood_s70_v1_scene_preview_front_oblique.mp4)。机械臂停在旁边作为尺度参照，视频不含任务动作。

已验证的历史机器人版为 `spatial_maze_robot_v3 / compact_single_arm_v1`，使用一台标准安装位的 **Panda + Robotiq 2F-85**。其底座为 **743 × 527 × 25 mm**，导线最高点距台面约 **266 mm**；原照片台架为 1180 × 820 × 45 mm、最高约 580 mm。下文物理证据及已固定的 agent episode 仍对应历史版本。

2026-09-19 新增[基础实例 coding agent adapter](../modules/buzz_wire_agent_adapter_zh.md)：复用公共 Panda 执行模块，以真实摩擦抓持和固定腕相机提供本地任务包；已通过 101 步短程协议验证，完整自主通行尚未验证。该入口只加载静态初态，不使用下方参考 demo 的路径控制器。

2026-09-19 新增[三个动作家族与原型内微调设计](buzz_wire_3d_family_space_zh.md)：高低双拱，以及串联 3–4 个不同构型关卡的错层八字和换平面家族。F3 v3 已通过密集 IK 与 4 / 2 ms 双步长完整单臂物理验收，三视角已归档到 `demos/`；该历史尺寸 F2 的后半程当时仍在搜索；新版 70% F2 的成功执行见本文开头。历史视频与状态见 [可解性与完整动作报告](../../../runs/environment-solvability/buzz_wire_3d/family_solvability_20260919/result.md)，[首轮验收报告](../../../runs/environment-solvability/buzz_wire_3d/family_physics_20260919/result.md)保留。触碰检查视频明确标为无机器人台架检查，不替代下方已验证的基型单臂 demo。

[单臂三路同步播放](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_compact_single_arm_v1/index.html) · [物理稳定性](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_compact_single_arm_v1/stability_report.json) · [时间步对照](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_compact_single_arm_v1/stability_plot.png) · [视频检查](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_compact_single_arm_v1/archive_validation.json)

## 单臂版的结构与动作

保留照片中的左侧长水平回折与右侧盘旋。中部调整为有前后位移的倾斜下探 / 上升折返，右侧为一整圈螺旋，给真实夹爪和腕部留出空间。机器人、关节限位及安装位未缩放或放宽。

- 导线直径 4.2 mm，总长约 2.536 m；扣除两端各 18 cm 的支撑段，参考可玩段约 2.176 m。
- 环中心线直径 44 mm，环丝直径 3.6 mm，净内径 40.4 mm。短连接杆为 22.8 mm；蓝色平面握柄为 43.6 × 14 × 10 mm，整件质量约 31.0 g。
- 圆环可相对导线切线倾斜。完整参考路线仍以实体几何检查环、杆、握柄、防脱球和底座，连续净空下界约 1.927 mm，穿环数保持 1。不能只检查圆环中心是否在线上。
- 1601 个机器人规划样本全部使用原始物理关节限位；机器人到固定玩具最小采样净空约 13.55 mm，非手指部件到环杆约 2.34 mm，机器人到金属部分约 6.52 mm。这是密集采样规划检查，动态执行另行逐步检查接触。

完整流程从**预穿环、预抓取位置**开始：夹爪闭合并确认两侧接触，保持 3 秒；单臂带环走过所有回折和螺旋；在最后下转弯之后的直立段松手，圆环沿末端立柱靠重力滑到橙色限位球；机械臂退开，等待圆环静置。机械臂释放点为参考进度 0.988，剩余路线仅含最终直立支撑段，规划器会检查这个条件。本版不包含从桌面拾取手柄或初次穿环。

抓持采用接触摩擦，无焊接约束。环杆没有重力补偿、外力驱动或运行中位姿覆写；机械臂采用有限力矩关节伺服及常规重力补偿，并以 50 Hz 使用仿真中实测的夹爪 / 圆环位姿更新抓持变换，补偿握柄在转腕时的偏转。它是基于仿真状态反馈的控制演示，未实现视觉估计或通用学习策略。执行记录包含真实的夹爪被动关节，录像没有重建被动关节或用理想路线代替物理状态。

## 单臂物理稳定性与录像

| 检查 | 主运行 | 时间步减半复验 |
| --- | --- | --- |
| 完整动作与终点静置 | 通过 | 通过 |
| 受控通行触线次数 | 0 | 0 |
| 最大圆环位置偏差 | 3.591 mm | 3.628 mm |
| 环杆最大记录穿透（含抓持及释放） | 0.149 mm | 0.149 mm |
| 机器人与固定玩具 / 自身最大记录穿透 | 0.000 / 0.000 mm | 0.000 / 0.000 mm |
| 通行全程双侧夹爪接触 | 20493 / 20493 步 | 40984 / 40984 步 |

按相同路线进度比较，最大位置差 **0.053 mm**、最大姿态差 **0.039°**。两次均完成松手、退开和终点静置。三路视频各 **91.84 秒、2296 帧、25 fps、960 × 720**。


主运行使用 Genesis 1.2.1 CPU / 64 位精度、4 ms 控制步、16 子步、0.5 ms 接触时间常数；独立复验为 2 ms / 16 子步。平面握柄避免圆柱握柄在夹爪内转动；启用 Genesis 的 `noslip_iterations=100 / noslip_tolerance=1e-12` 接触求解后处理，抑制软约束摩擦产生的持续数值滑移。该选项属于仿真器的实验性摩擦收敛功能，仍受接触摩擦约束，没有增加物体连接约束。2F-85 每个驱动关节使用 Kp=50、Kv=5、力矩上限 2.5 N·m。所有配置和源码随实际运行归档。

释放后另外检查脱离机器人接触的圆环机械能，允许的额外增长上限为 1 mJ，以区分重力引起的正常转动与能量异常增长。

穿透值在每个外层物理步后采样，不代表所有积分子步的严格上界。零触线结论针对受控通行；末端释放后允许圆环与立柱 / 限位球接触。此次验收仅覆盖当前尺寸、初态与控制策略，不使整个任务参数族自动成为已验证；导线保持刚性，不模拟铜线弹性、电路或真实硬件。

三路 `agentview / front_oblique / wrist` 来自同一次连续执行，原速、无叠字。腕部视角位置随手腕移动，镜头朝向实测圆环中心。由记录的物理状态重渲染时没有新增仿真步进，并核对全部机器人关节、环杆位姿及碰撞 / 惯量资产一致。视频按视角放在根目录 [`demos/buzz_wire_3d/`](../../../demos/buzz_wire_3d/)，证据和播放页在 `runs/demo_metadata/buzz_wire_3d/`。旧无机器人台架视频保留，文件名前缀区分版本。

### 单臂版复现

使用新目录名；入口拒绝覆盖已有结果。依赖见 `requirements/uv-topogym-buzz-wire.txt`。

```bash
export OPENBLAS_NUM_THREADS=1
export PYTHONPATH=.

.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_plan \
  --seed-plan assets/tasks/buzz_wire_3d/compact_single_arm_v1/robot_seed.json \
  --output runs/environment_bootstrap/buzz_wire_3d/robot_recheck/plan

.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_runtime \
  --plan runs/environment_bootstrap/buzz_wire_3d/robot_recheck/plan \
  --output runs/environment_stability/buzz_wire_3d/robot_recheck/nominal

.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_runtime \
  --plan runs/environment_bootstrap/buzz_wire_3d/robot_recheck/plan --dt 0.002 \
  --output runs/environment_stability/buzz_wire_3d/robot_recheck/refined

.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_verify \
  --nominal runs/environment_stability/buzz_wire_3d/robot_recheck/nominal \
  --refined runs/environment_stability/buzz_wire_3d/robot_recheck/refined \
  --output runs/environment_stability/buzz_wire_3d/robot_recheck/stability_report.json

PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_render \
  --source runs/environment_stability/buzz_wire_3d/robot_recheck/nominal \
  --output runs/environment_stability/buzz_wire_3d/robot_recheck/render

.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_archive \
  --source runs/environment_stability/buzz_wire_3d/robot_recheck/render \
  --suite runs/environment_stability/buzz_wire_3d/robot_recheck/stability_report.json \
  --run-id 2026-09-18_compact_single_arm_recheck
```

若纯渲染阶段中断，可对同一 `robot_render` 命令追加 `--resume`：先核对物理记录、机器人资产、相机配置及已有画面，再续渲缺失的同步帧，不重新执行物理动作。完整输出仍禁止覆盖。

配置为 [`buzz_wire_3d_robot.yaml`](../../../configs/buzz_wire_3d_robot.yaml)，复现种子说明见 [compact_single_arm_v1](../../../assets/tasks/buzz_wire_3d/compact_single_arm_v1/README.md)。`robot_plan / robot_runtime / robot_verify / robot_render / robot_archive` 分别负责规划、实际执行、步长对照、三路实测回放和归档；正式归档要求独立完整物理执行与复验均通过。`contact_weld` 仅为明确标注的辅助抓持调试选项，正式验收拒绝它。

## 历史：照片尺寸无机器人台架

以下记录只描述旧 `spatial_maze_v2`，其物理结论和视频仍保留；其中“未验证机器人”指旧尺寸台架，不是上面的紧凑单臂版。


2026-09-18 根据用户提供的实物照片，默认布局更新为 `spatial_maze_v2`：左侧横向长回折、中部竖向回折、右侧盘旋再下行。它取代最初只有两个大起伏的空间路线，保留旧布局与平面接触台架作为对照。

[打开可旋转、可播放的场景预览](../../../runs/environment_bootstrap/buzz_wire_3d/spatial_maze_v2/index.html) · [三视图](../../../runs/environment_bootstrap/buzz_wire_3d/spatial_maze_v2/scene_views.png) · [实际检查报告](../../../runs/environment_bootstrap/buzz_wire_3d/spatial_maze_v2/report.json) · [GLB 场景模型](../../../runs/environment_bootstrap/buzz_wire_3d/spatial_maze_v2/scene.glb)

![按参考图重建的回折与盘旋布局](../../../runs/environment_bootstrap/buzz_wire_3d/spatial_maze_v2/scene_overview.png)

## 结构与玩法

布局直接参考本轮用户提供的照片。连续铜色导线由左端升起，在高处完成三次水平 U 形回折，然后转入中部的两次低位 U 形回折及一次高位回折，最后进入右侧约 1.35 圈的收缩盘旋并从内侧落到底座。盘旋还带有约 35 mm 的高度变化；不同路线段分处水平、竖直与缓升曲面。尺寸为自行设计，并非实物测绘；照片中的电池、标牌和蜂鸣电路未建模。

- 长方体底座为 **1180 × 820 × 45 mm**，空间路径固定于两端。
- 桌面实例中心为 `[-0.035, 0] m`，绕竖直轴旋转 90°，把长边横向布置在桌面上并避开机器人安装底座；独立预览使用玩具自身坐标。
- 导线半径 **3.5 mm**，总长约 **6.129 m**；扣除两端支撑附近各 100 mm，可玩段约 **5.929 m**。
- 导线相对底座底面的包围范围约为 x `[-490, 481]`、y `[-280, 260]`、z `[55, 580]` mm。最小采样曲率半径约 **35.4 mm**，最优拟合平面的均方根偏离约 **102.5 mm**，确实为空间曲线。
- 闭合环中心线半径 **26 mm**，环丝半径 **3 mm**；净内半径 **23 mm**。连接杆长 **38 mm**，蓝色握柄长 **70 mm**、半径 **9 mm**；整件作为一个六自由度动态刚体，环孔保持真实开放。
- 两端绿色 / 橙色防脱球半径 **33 mm**，大于环内孔。没有中途支柱、岔线或可供绕过线路的开放端。
- 初态已穿环，位于绿色端上方。终点位于橙色端上方；无需也不允许把环从端头取走。参考姿态让环面跟随局部切线变化：手柄在水平回折段主要朝上，转入竖直回折后主要朝前；盘旋末端逐渐绕导线切线转动 90°，给相邻导线留出空间。

这是基础可行实例。初态预穿环，没有机器人抓持或收纳托架；直接自由步进时环会受重力下落，并由绿色防脱端支撑。全程动力学台架用有限力和力矩保持初态、驱动通行，终点撤去驱动力。机器人抓取和初态交接仍需单独实现。

## 已验证的范围

生成器同时输出 URDF 碰撞体、参考位姿、尺寸报告及文件 SHA-256。导线和环杆用分段胶囊的实体并集构造，各段接缝有球体覆盖，不将闭环整体凸包化。惯量使用胶囊分量质量求和，包含连接处少量重叠的质量近似，报告明确记录。

完整路线含 **2966 个参考姿态**。位置采用分段线性插值、姿态采用最短弧 SLERP。几何检查覆盖环、细杆、粗握柄对整条导线、防脱球及底座的距离：

1. 对所有胶囊中心线构造最大间距 1.5 mm 的采样覆盖；最近点距离减去半径及两侧覆盖误差，得到每个姿态的保守实体净空。
2. 对每段插值，使用平移距离的一半与刚体旋转位移界，扣除姿态采样之间的最大运动量。
3. 当前全程连续净空下界约 **12.959 mm**。这个界对应实际导出的胶囊并集及上述插值轨迹；不会因为只看若干离散截图而漏掉两帧之间的碰撞。
4. 把导线沿底座内部闭合后，所有参考位姿的环绕数为 1；结合无碰撞连续路径，环始终保持穿在线上。
5. 故意侧移 24 mm、把环面转错 90° 均被净空检查拒绝；压低路径导致撞底座、把深度压近平面也被拒绝。去掉盘旋末端的手柄转动也无法通过，防止只验证环孔而漏掉握柄扫到邻线。

初期 Genesis CPU 加载检查固定底座 / 导线、自由环杆、碰撞体数量与短时有限状态。现在已另行完成新空间路线的完整有限力动力学通行、主动触线及重力释放检查；这些报告与初期几何检查分开保存。**仍未验证机器人全程抓持、蜂鸣电路或自动任务计分。** 旧平面台架的证据没有用于替代新空间路线的动力学检查。

几何阶段运行 12 项空间 / 旧平面几何回归，增加盘旋末端转柄反例及旧布局复现检查，并执行 Ruff、Buzz Wire 参数卡与 CPU 场景加载。新线路包含导线 2303 个、环杆 198 个碰撞形状；加载状态见实际报告。上面的总览、三视图、HTML 与 GLB 属于早期独立几何预览；本轮全程动作录像另由 Genesis 相机渲染，明确标注为无机器人的环杆动力学台架。

上轮附带运行的全任务参数卡检查发现原有 `fiber_bundling` 卡使用 `geometry_candidate`，而目录校验器只接受 `candidate`；此问题与本任务无关，本次未改动该卡。

## 动力学验证与三视角完整动作

[三路同步播放](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_spatial_maze_fixture_v1/index.html) · [物理报告](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_spatial_maze_fixture_v1/stability_report.json) · [测量曲线](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_spatial_maze_fixture_v1/stability_plot.png) · [视频检查](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_spatial_maze_fixture_v1/archive_validation.json)

本轮保留的是**无机械臂的环杆动力学台架**：初态已经穿在线上，六自由度刚体由有限外力 / 力矩驱动，走完约 5.929 m 的路线，再撤去驱动力，自由落到橙色防脱端并静置。执行中不覆写物体位姿；机器人抓取与全程可达性尚未验证。

| 检查 | 结果 |
| --- | --- |
| 初态自由下落 5 秒 | 保持穿环并稳定；最大记录穿透 0.180 mm |
| 主动侧推触线、退回中心 7 秒 | 检出约 4.97 N 接触反力；最大记录穿透 0.008 mm；退回后无触线 |
| 60 秒完整通行 | 零触线；最大位置误差 0.825 mm；最大姿态误差 3.44° |
| 终点撤力并自由静置 4 秒 | 保持穿环并稳定；含释放阶段的最大记录穿透 0.260 mm |
| 控制周期与积分步长减半 | 独立全程再次通过；受控阶段最大位置差 0.318 mm，最大姿态差 0.540° |

使用 Genesis 1.2.1、CPU、64 位精度。主运行控制周期 4 ms、16 个子步（积分步长 0.25 ms），接触时间常数 1 ms；复核使用 2 ms / 16 子步（0.125 ms）。限幅为每轴 8 N、0.25 N·m。按质量惯量缩放姿态 PD；将世界力矩转换为 Genesis 自由关节要求的局部力矩。默认场景已同步这套接触参数。

接触力、穿透和穿环拓扑在每个外层物理步后检查，保存位姿为 50 Hz；没有记录每个积分子步，表中穿透值是外层检查记录的最大值。主运行共 16500 步、复核 33000 步，均无运行中位姿覆写。导线和底座固定且为刚体，未验证铜线弹性、电路或真实硬件。

三路 `overview / front_oblique / topdown` 均为 **66.04 秒、25 fps、1651 帧、960 × 720**，包含 1 秒起点保持、60 秒通行、1 秒终点保持、4 秒释放；末帧额外显示一个视频帧周期。三路从同一次成功物理运行的实测姿态渲染，渲染阶段不再步进物理；位置重建误差为 0。修正了 URDF 重复材质名导致蓝色握柄、绿色 / 橙色端头显示为铜色的问题，碰撞几何、质量、惯量和关节保持一致。视频无叠字、状态栏或画中画。

MP4 按视角位于仓库根目录 [`demos/buzz_wire_3d/`](../../../demos/buzz_wire_3d/)，下分 `overview/`、`front_oblique/`、`topdown/`，旧版每路保留一份独立视频，共享目录内以文件名前缀区分新单臂版；原 `runs/demos/buzz_wire_3d/` 副本保留备份。播放页、原始状态、配置、资产、运行时源码、测试证据和 SHA-256 清单仍在 `runs/demo_metadata/buzz_wire_3d/`，播放及核心证据不依赖原运行目录。它不计入完整机器人 demo 数量。

已尝试标准 Panda/Robotiq 安装位的固定轴向抓姿，以及若干抬高安装位、侧向抓姿、悬挂候选；这些局部 IK 搜索没有找到覆盖所有采样点的单一方案，详见归档的 `exploratory/robot_reach_check.json`。这不是机械臂不可达的严格证明，也不是完整连续碰撞检查。交付场景没有应用这些探索性安装改动。

初版自由下落的穿透超限、姿态控制坐标错误导致的触线、GPU 显存不足尝试都保留为非验收记录；没有用它们充当成功证据。本轮几何及控制/证据回归合计 **17 项通过**，另通过 Ruff 和本任务参数卡校验。

### 动力学与录像复现

下面的运行目录应使用新名称；已有目录不会覆盖。

```bash
# 三项实际动力学检查，依次执行；每项保存状态、报告、配置和资产。
for case in gravity contact traverse; do
  .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.physics \
    --backend cpu --case "$case" \
    --output "runs/environment_stability/buzz_wire_3d/recheck_new/$case"
done

# 减半控制周期和积分步长，完整独立复核。
.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.physics \
  --backend cpu --case traverse --dt 0.002 \
  --output runs/environment_stability/buzz_wire_3d/recheck_new/refined

.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.verify_physics \
  --gravity runs/environment_stability/buzz_wire_3d/recheck_new/gravity \
  --contact runs/environment_stability/buzz_wire_3d/recheck_new/contact \
  --nominal runs/environment_stability/buzz_wire_3d/recheck_new/traverse \
  --refined runs/environment_stability/buzz_wire_3d/recheck_new/refined \
  --output runs/environment_stability/buzz_wire_3d/recheck_new/stability_report.json

# 从成功执行的实测状态渲染同步三视角，需可用 EGL 上下文。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.render \
  --source runs/environment_stability/buzz_wire_3d/recheck_new/traverse \
  --output runs/environment_stability/buzz_wire_3d/recheck_new/render

# 完整解码验证后，复制视频和证据并更新统一目录。
.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.archive \
  --source runs/environment_stability/buzz_wire_3d/recheck_new/render \
  --suite runs/environment_stability/buzz_wire_3d/recheck_new/stability_report.json \
  --run-id 2026-09-18_spatial_maze_fixture_recheck_new
```

## 几何与场景加载复现

当前环境已有依赖；新环境可安装 `requirements/uv-topogym-buzz-wire.txt`，渲染 Nyx 另按共享环境安装说明准备。

```bash
# 不需要 GPU：生成资产、连续净空报告、独立 HTML、三视图及 GLB。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.buzz_wire_3d

# CPU 实际场景加载及两个物理时间步；不渲染，不执行参考路线。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.buzz_wire_3d \
  run.build_scene=true env.genesis.backend=cpu \
  env.renderer.type=rasterizer env.presentation.background=checker

# 有可用 GPU 时，使用项目默认 Nyx / compact_lab 拍实际初态三视角。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.buzz_wire_3d \
  run.build_scene=true run.render=true

# 回归空间通行、反例、URDF 一致性及旧平面几何。
.venv-gs121-nyx/bin/python -m unittest \
  tests.check_buzz_wire_3d tests.check_rigid_bootstrap_geometry -v
```

默认配置为 [`buzz_wire_3d_preview.yaml`](../../../configs/buzz_wire_3d_preview.yaml)。入口默认不加入机器人；`run.include_robot=true` 可布置共享机器人，但未验证机器人沿这条空间路径的运动。几何参数可通过 Hydra 覆盖，每次都会重新检查；不能把独立参数范围直接视为已验证可玩空间。

代码职责：[`templates.py`](../../../topogym/tasks/buzz_wire_3d/templates.py) 定义照片布局的各段回折与盘旋；[`geometry.py`](../../../topogym/tasks/buzz_wire_3d/geometry.py) 构造曲线、环杆、资产与参考姿态；[`verification.py`](../../../topogym/tasks/buzz_wire_3d/verification.py) 检查完整连续通路；[`scene.py`](../../../topogym/tasks/buzz_wire_3d/scene.py) 接入共享桌面；[`preview.py`](../../../topogym/tasks/buzz_wire_3d/preview.py) 输出审阅材料并可选加载仿真。

后续机器人阶段需要补足：机器人抓握与初态交接、完整连续 IK 与手臂 / 夹爪碰撞检查、机器人驱动的空间全程跟踪。任务集成还需接入触线计分、按路径顺序的终点 evaluator。当前有限力台架的成功不等同于完成这些工作。

## 旧布局对照

第一版较简单的空间起伏仍可查看 [spatial_slalom_v1 预览](../../../runs/environment_bootstrap/buzz_wire_3d/spatial_slalom_v1/index.html)。历史输出没有覆盖，原有 1.869 m 路线也有复现回归。需要重建其几何时：

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.buzz_wire_3d \
  task.variant=spatial_slalom_v1 'task.geometry.base_size_m=[0.84,0.64,0.05]' \
  run.output=runs/environment_bootstrap/buzz_wire_3d/slalom_recheck
```
