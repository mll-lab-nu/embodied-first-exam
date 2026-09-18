# Cast Keyhole 基础环境

本阶段选用 **Hanayama Huzzle Cast Keyhole 标准版**（HZ 4-11 / 515061），
设计者 Vesa Timonen，官方难度 4 / 6。目标是建立可复现的几何、双刚体场景及基础检查入口。

## 当前实例已找到完整解（2026-09-17）

`perpendicular_lower_bore_v1` 的原始网格、板厚、槽宽均保持不变。新路径
`assets/tasks/cast_keyhole/diagram_reference_v1/baseline_solution.json` 从场景实际初态出发，28 段全部通过连续 SAT 验证，
间隙下界至少 0.15 mm，最终分离下界 55.5 mm。初始位姿由两件实际网格的刚体变换还原，
不是沿用历史 `route_candidates.json` 的另一种顶部初态。

动作顺序是：下部孔道转动、绕顶部转向右侧、对齐并穿过右齿、横移避开下齿、完全退出。
参考官方图解的转向与对槽原则；当前工程初态不对应商品出厂初态，未声称逐图复现官方 16 步。

完整路径的 64 位动力学台架在 1 / 0.5 ms 两种时间步均通过，分别执行 16,128 / 32,256 步，
未覆写运行中的零件位姿；最大位置跟踪误差为 0.00239 / 0.00120 mm，未出现接触穿透。
台架固定金件、以有界力和力矩驱动银件，不能代替机器人抓持验收。
证据：[`current_instance/`](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/certificate.json)。

ALOHA 双臂通过 12 关节耦合 IK，共 270 帧、22.5 秒；两臂分别抓金件左脚、银件顶部。
共同世界朝向可调整，零件相对位姿始终跟随已验证的路径。另检查 971 个关节插值点，
最大检查关节间隔 0.003 rad；实际 FK 相对位置误差最大约 10.5 nm，采样间隙最小约 0.304 mm。
这些数值是仿真运动学精度，不是实体机器人的精度保证。
预演从抬高后的预抓取姿态开始，保留当前零件相对初态；不包含从桌面拾取。

双臂受力执行也已通过：`robot_execution.py` 连续运行 23.917 秒 / 23,917 个物理步，
只在复位时设置关节和零件姿态，运行中使用有界关节控制。两侧夹爪都在第 1 个物理步确认双指同刻接触，
随后分别增加辅助焊接抓持约束；末态保持辅助约束，不宣称纯摩擦抓取或已经放回桌面。
物理执行最大接触穿透 0.1054 mm，实际零件间采样最小间隙 0.2814 mm，最终分离下界 55.4484 mm。
独立凸体检查覆盖 2,391 个实际状态（10 ms 间隔），机器人自身、谜题、桌面均通过；
最后 0.5 秒的零件原点速度最大约 `4.03e-7 m/s`，角速度约 `8.56e-7 rad/s`。
证据：[物理执行](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/robot_physics/report.json)、
[独立实际轨迹审查](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/robot_physics/audit.json)。

记录采用 ALOHA 四路同步相机，另外保留细节、斜视和四视拼图。物理版逐帧取自同一次执行的保存状态，
不重新插值零件姿态，每帧包含原物理步号；录像从第 10 步预抓取保持阶段开始，到第 23,910 步分离静止结束。
完整控制运行仍保留第 1 步的双指接触证据。源码 `physical_recording.py` 与 `archive_demo.py` 分别核对实际状态来源和视频同步。

- [完整物理执行播放页](../../../runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/index.html)
- [完整 IK 预演播放页](../../../runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_ik/index.html)

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.robot_execution \
  --motion runs/environment_bootstrap/cast_keyhole/aloha_current_instance/robot_motion.json \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/robot_physics
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.physical_audit \
  --folder runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/robot_physics
```

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.instance_solution \
  --solution assets/tasks/cast_keyhole/diagram_reference_v1/baseline_solution.json \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/certificate.json
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.robot_motion \
  --solution assets/tasks/cast_keyhole/diagram_reference_v1/baseline_solution.json \
  --certificate runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance/certificate.json \
  --output runs/environment_bootstrap/cast_keyhole/aloha_current_instance/robot_motion.json
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.aloha_demo \
  --output runs/environment_bootstrap/cast_keyhole/aloha_current_instance
```

## 选择依据与谜题结构

[厂家产品说明](https://hanayama-toys.com/product/cast-keyhole/)描述了两块平板组成的三维槽道迷宫。
[厂家拆件照片](https://hanayama-toys.com/wp-content/uploads/2018/06/Keyhole-2-800x800.jpg)可以直接核对：

- 金件是一端开口的叉形板，内侧有错列齿；金件槽道与外界连通。
- 银件有一个封闭的阶梯通孔；底部外凹口与通孔之间仍有实体横梁。
- 两件可处于不同平面，通过槽壁限制相对平移和转动。

[Hanayama 拆解图](https://www.logicagiochi.com/pub/media/wysiwyg/pdf/473743-Cast-Keyhole-Japan.pdf)
由经销商托管，共两页、16 个示意步骤，最后两件完全分开；包含滑动、90° 与 180° 翻转。
[Puzzle Master 的公开解法](https://www.youtube.com/watch?v=Du0JUir_9tA)是补充的人类演示来源。
因此所选**商业实物版本**有公开的人类解法依据。
这些资料未提供槽宽、板厚、倒角或连续毫米位姿，不能直接证明照片重建模型同样可解。

## 当前模型

模板位于 `assets/tasks/cast_keyhole/diagram_reference_v1/`。工程单件包络为 26 × 69 × 3 mm，
默认放大 3 倍；尺寸与 6600 kg/m³ 密度均为假设。保留圆弧回头、错列齿、阶梯孔与银件底部横梁，
未使用闭槽替代形状；槽角暂为锐角，真实倒角与加工公差待实测。

金 / 银视觉网格各自连通、封闭，Euler 数分别为 2 / 0；前者为开口叉实体，后者保留一个贯通孔。
水平切片得到 62 / 67 个不重叠凸棱柱，视觉与碰撞从同一实体导出。
质量、质心和惯量使用实体积分；缩放质量按三次方、惯量按五次方变化。
每件是独立单 link、6 自由度刚体，两件之间没有关节、焊接或约束抓持。

初态 `perpendicular_lower_bore_v1` 将金件穿入银件下部孔道，模板内金件绕 z 转 90°、沿 z 移动 −47 mm。
这是**工程候选初态**，不是原厂出盒位姿，也未确认对应官方解法中的哪一步。
选择它便于检查孔内穿插接触；3 倍实例的初始最小表面间隙为 3.9 mm。
整体摆放使长轴沿桌面，两件各倾斜 45°，底面距桌面 0.5 mm。
机器人复用共享 Panda + Robotiq 2F-85，仅作静止尺度参照。

## 运行与产物

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.cast_keyhole
```

默认采用 Genesis 1.2.1、CUDA、Nyx 和共享 `compact_lab`。输出位于
[`runs/environment_bootstrap/cast_keyhole/assembly_initial/`](../../../runs/environment_bootstrap/cast_keyhole/assembly_initial/index.html)：
装配正反面、实验室全景、单件正面检查、6 秒 / 120 帧相机绕行视频、静置后图像、
配置快照、URDF / 网格、几何检查、场景报告和文件哈希。

视频只移动相机，不步进物理。单件图显式重置到独立展示位姿，随后恢复全部自由度并清零速度，
再执行静置；展示重置不计作拆解。用 `run.record_video=false` 跳过视频，
用 `run.settle_seconds=0` 只检查初态。
无 GPU 时可显式选择 CPU 光栅路径（本轮未实际运行该路径）：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.cast_keyhole \
  env.genesis.backend=cpu env.renderer.type=rasterizer run.record_video=false
```

## 验证及加载修正

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_cast_keyhole \
  tests.check_configs_compose tests.check_task_baseline_catalog tests.check_project_layout
.venv-gs121-nyx/bin/python -m scripts.build_bootstrap_review
```

15 项检查覆盖金叉开口、银件封闭通孔及底部横梁、分块碰撞空槽、初始间隙、错误重叠拒绝、
体积 / 质心 / 惯量与缩放、URDF 导出及任务配置契约。

第一次 GPU 试跑出现弹跳，记录保留在 `initial_probe/`。
本机 Genesis `utils/mesh.py` 的 `_postprocess_collision_geoms_impl` 在 `convexify=False`
时会合并同组网格。这里拼接的是带内部接面的多个闭合凸块，不是一个已消除内部面的完整凹体。
修正为对**每个已经为凸的棱柱**启用 `convexify=True`，使原有分块保持独立；
并在加载后校验凸块数、各块包络和体积，阻止整件凸包或合并网格改变槽口。
此修正局限于本任务，不更改 Genesis 安装或其他任务。

修正后的 `convex_probe/` 完成 0.5 秒、500 步自由重力静置，最大接触穿透约 0.097 mm，
末 0.1 秒最大线速度约 0.061 mm/s、角速度约 0.0011 rad/s。
期间最大位移约 16.95 mm、转角约 27.55°，零件重新落稳，**初始摆姿没有保持**。
静置期间没有写入位姿或施加驱动力；这只覆盖短时接触与落稳，不能证明不能穿模、正式互锁或完整拆解。
最终默认产物以 [场景报告](../../../runs/environment_bootstrap/cast_keyhole/assembly_initial/inspection_report.json) 为准。

任务卡保持 `physics.qualification: unqualified`，并分别记录
`human_reference_solution_documented=true` 与 `extraction_route_verified=false`。
下述接触台架与部分路径检查扩展了短时静置的证据，但完整官方解法与机器人抓持仍未通过验收。

## 接触台架与时间步复核

`physics_probe.py` 每组并行建立 11 个隔离场景，运行 5 秒：

- 3 个自由重力静置：基准摆放、改变 yaw、抬高 2 mm 落下。
- 2 个允许移动：金件沿 x 正负方向移动 1.5 mm。
- 6 个受阻拉动：沿 x/y/z 正负方向，目标超过几何首次接触位置 12 mm。

移动台架固定银件、对金件重力补偿，以实际外力 / 力矩驱动，不写入零件位姿。
先保持 0.3 秒、平滑移动 1.2 秒、带载保持 0.7 秒，2.2 秒时撤去驱动，观察至 5 秒。
平移 PD 限力 20 N；转动按世界坐标惯量计算力矩，限幅 3 N·m。
这是**接触台架**，不代表机器人夹持或官方路线执行。

碰撞求解器每步记录接触，独立凸体 SAT 每 5 ms 检查相对位姿，能检测实体包含情形。
此离散采样不是整个物理轨迹的连续碰撞证书。
门槛包括最大求解穿透 / SAT 重叠小于 0.5 mm、自由移动跟踪误差小于 0.5 mm、
受阻不越过首次接触位置 2 mm、静置末段漂移小于 0.2 mm。
`qualify.py` 要求两组完整 11 场景、配置仅时间步不同、源文件哈希一致且未在运行期间变化；
最终相对位置差小于 1 mm、姿态差小于 0.02 rad。通过台架仍不允许宣称完整解法或机器人 demo 合格。

早期较弱姿态控制有 4 项受阻方向偏转过大；直接增大固定力矩增益又使细长板姿态振荡。
这些失败结果分别保留在 `weak_orientation_*` 与 `fixed_gain_nominal`。
惯量归一化后，32 位精度下 1 / 0.5 / 0.25 ms 的 33 项单场景测试均通过；
相邻时间步比较各有一项卸载后最终位置差超过 1 mm（约 1.37 / 1.56 mm），
故未放宽门槛，追加 64 位精度复核。
当前结论及实际数值见[审阅页](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/index.html)
与[台架验收报告](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/contact_qualification.json)。

64 位 1 / 0.5 ms 两组 **22 / 22 项通过，时间步一致性亦全部通过**：
最大接触穿透约 0.168 mm，最终相对位置最大差 0.715 mm、姿态最大差 0.0121 rad。
这是上述 5 秒台架工况的验收结果，不保证所有动作或完整机器人场景均无问题。
`cast_keyhole_preview.yaml` 与台架入口采用 64 位精度；共享环境及其他任务默认值未修改。
回到包含静止 Panda 参照的 Nyx 场景后，渲染与 0.5 秒静置复核也通过，最大接触穿透约 0.120 mm；
产物见 [`precision64_scene/`](../../../runs/environment_bootstrap/cast_keyhole/precision64_scene/index.html)。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.physics_probe \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/float64_nominal --dt .001 --precision 64
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.physics_probe \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/float64_refined --dt .0005 --precision 64
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.route_probe \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/route_probe
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.review
```

GPU 运行需要访问设备；本机使用 Genesis 1.2.1 / CUDA。历史 32 位报告对应旧版 probe 源文件哈希，
保留作诊断记录，不复用为当前源码验收。

## 历史顶部候选与官方逐图对应的边界

2026-09-17 重新核对了 [Huzzle 官网的 16 步解法 PDF](https://www.huzzle.eu/wp-content/uploads/2018/01/515061-Huzzle-Cast-Keyhole-Oct-2017.pdf)，
确认标准实物有解；当时完整工程路径尚未找到。逐图动作、三个标注的半圈转动与当前阶段定义的区别，
见[官方解法核对记录](cast_keyhole_reference_audit_zh.md)。现有 68 / 69 段通过不能解释为官方路线完成比例。

`route_candidates.json` 使用规范轮廓坐标（金件位于 XY 面），与 bootstrap 的下部孔道初态不同。
已找到顶部穿插、四分之一圈转动、进入第一槽的 7 段几何候选；
`route_probe.py` 以凸体 SAT 和区间内最大材料点位移界，验证连续间隙至少 0.15 mm（3 倍场景）。
三正交投影为诊断图，不是机器人三视角视频。

第一槽直接插值到第二槽会发生碰撞，负对照正确拒绝。
继续使用三维倾斜与转动搜索后，第一槽到第二槽已找到 17 段连续连接；
倒数第二槽到最后一槽也找到 17 段连接，银件底部外凹口参与避让。
这些连接使用原始板厚和槽形，通过独立凸体 SAT 的连续区间检查；
它们按教程关键槽位组织，不能宣称精确复现官方 16 幅示意图。

完整工程候选保存在 `assets/tasks/cast_keyhole/diagram_reference_v1/official_milestones_candidate.json`，
涵盖顶部穿插起点、第一槽、第二槽、第一次半圈翻转、下部孔道、倒数第二槽、最后一槽、
第二次半圈翻转与退出。**69 段中 68 段通过，但整条路线未通过**：
第二槽到倒数第二槽仍只有一个用于诊断的直连，区间中点 SAT 重叠为 3.675 mm（3 倍场景）。
该段不允许执行；后半段是独立片段证据，不能跳过缺口拼成完整 demo。
末端候选的分离间隙下界为 55.5 mm，也不代表已经从起点成功到达该处。
证据见[逐段报告](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/full_route_candidate/certificate.json)
及[失败连接三视投影](../../../runs/environment-solvability/cast_keyhole/diagram_reference_v1/full_route_candidate/witness_views.png)。

有限搜索覆盖固定高度、不同槽高、顺逆转向、三维倾斜，以及有无虚拟末端封口的诊断。
虚拟封口只曾用于搜索以限制提前绕出，未添加到实际模型或连续 SAT 验证中。
尚未找到中段连接，不构成模型无解证明；初始穿插朝向、教程槽位对应与照片推断尺寸仍需进一步核对。
`solution.py` 检查阶段顺序、首尾连接、显式半圈翻转、整条间隙、最终分离与源码哈希。
`trajectory_probe.py` 已增加严格入口检查，会在初始化仿真前拒绝失败、不完整或过期证书；
该历史失败候选未运行完整轨迹力控台架。当前实际初态的完整台架证据见本文开头。

```bash
# 当前候选应返回非零退出码，并明确指出中段连接失败。
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.solution \
  --solution assets/tasks/cast_keyhole/diagram_reference_v1/official_milestones_candidate.json \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/full_route_candidate/certificate.json
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.solution_diagnostics \
  --solution assets/tasks/cast_keyhole/diagram_reference_v1/official_milestones_candidate.json \
  --certificate runs/environment-solvability/cast_keyhole/diagram_reference_v1/full_route_candidate/certificate.json \
  --output runs/environment-solvability/cast_keyhole/diagram_reference_v1/full_route_candidate/witness_views.png
```

**选用双臂 ALOHA（两台 ViperX300）进入后续操纵阶段。**
单臂加固定夹具并非运动学上不可能，但两件需要独立支撑，夹具会增加翻转避让、换抓和路径设计工作。
双臂可分别支撑金件与银件；当前初态的共同可达空间及采样夹爪碰撞已验证，受力抓持单独验收。
现有 bootstrap 中的 Panda 保持为静止尺度参照，不是选定的解谜执行器。

完整 demo 按项目归档规范保留 ALOHA 的四路同步视角：
`cam_high / cam_low / cam_left_wrist / cam_right_wrist`，保存共有的物理步号与时间。
先完成接触台架、当前实例完整路径、真实接触抓持与最终分离验收，
再生成完整 demo。若采用接触后辅助焊接，只允许双指先实际接触零件，必须在报告中明示；
不能用逐帧位姿覆写、无接触吸附或隐藏夹具替代机器人执行。

完整 demo 的视频副本统一归档至 `runs/demos/cast_keyhole/`，
文件名为 `<date>_<run_id>_<camera>.mp4`；该目录只放独立 MP4 文件。
播放页、配置、报告、轨迹和哈希清单放在 `runs/demo_metadata/cast_keyhole/<date>_<run_id>/`，
归档时同步更新 `runs/demo_metadata/` 的索引、说明和目录清单，并检查视频可解码与各视角同步。
完整物理执行与 `kinematic` 运动学预演已分别归档，入口见本文开头；相机绕行视频和历史局部诊断继续保留在原运行目录。

新增回归入口：

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_cast_keyhole_solution tests.check_cast_keyhole_physics tests.check_cast_keyhole \
  tests.check_configs_compose tests.check_task_baseline_catalog tests.check_project_layout
```

当前 31 项回归通过，增加实际场景初态对应和新证书入口负对照，并覆盖原有资产验证、实体包含 / 孔道负对照、端点无碰撞但中途碰撞、
转动扫掠、时间步 / 源码 / 完整场景门槛和部分路径的连续证据；
另检查失败路线不能启动动力学，以及组合平移转动、绕轴翻转的质心速度与加速度符合有限差分。
