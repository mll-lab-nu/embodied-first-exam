# 绳穿三环：基础场景

目标参考为 [Wang 的三环演示](https://qinengwang-aiden.github.io/demos/constraint_demos/?demo=threading)。
已提供离线资产、共享 ALOHA 双臂实验室与原生子步物理审计入口。
公开动作参考与接触触发的机器人执行入口已接入。原参数时间步对照未通过，
已完成启动间距、接触距离和绳体弹性的检查及局部机器人抓取验证。
先前无阻尼版本的 33 cm 高处完全松手未通过时间步收敛。当前形变耗散候选正在按参考动作中的
受控放回与邻近换手范围完成验收，不覆盖上述高处自由释放，尚无通过验收的完整 demo。

2026-09-19 按用户要求，暂缓亚毫米迟发滑动的静置资格复验，先执行完整穿环动作试跑。
`ring_halfdt_attempt_3` 已在 20.1025 s 有序停止并保存不完整证据；其停止原因是工作优先级调整。
新运行位于 `runs/environment-solvability/rope_threading/full_exploratory_v13_attempt_1/`，
使用同一 v13 材料、网格、接触参数、速度倍率 3 和公共 FEM 辅助抓持，末尾观察 20 s。
`--exploratory-reason` 明确记录暂缓完整资格的原因；所有原生碰撞、形变、求解、抓持跟随及静置指标仍按原门槛记录。
任务动作是否完成与完整物理资格分别报告，试跑不会设置 `full_demo` 或 `full_threading_verified`，
也不会由正式归档入口提升为已验收演示。6 项试跑模式检查与 12 项参考动作检查通过。

### 2026-09-20：明确终态，先完成不录视频的 IK 规划

上述试跑已在 **物理 28.08 s / 参考 81.355 s** 停止，位于第一环前调姿阶段（phase 10）。
两次抓取已完成，尚未发生主动松手。停止错误为 `Actual robot state exceeded an arm joint limit`。
参考右腕 `wrist_rotate` 在约 80.66–192.89 s 长时间接近 −π 限位，最小余量仅
`5.9321e-5 rad`（0.0034°）；本次实测最大越界 `1.6461e-4 rad`（0.0094°）。
旧碰撞预筛直接使用参考关节角，没有检查伺服需要的限位余量，因此不能据其通过推断执行安全。
原失败运行及视频保留，不计为完整流程。

按用户新要求，本轮先生成完整 CPU IK 方案，不启动新视频录制。
帖子链接本轮返回 403，采用之前缓存的作者公开三环参考，重新校验全部 51 个二进制文件、
每个数组及 18,712 帧提取结果；没有声称本轮重新观看了无法打开的帖子视频。

**预期终态**：从绳的材料节点 0 沿绳到 80，依次只有 `R1- / R2+ / R3+` 三次孔内穿越，
对应青、绿、紫三环。正负号表示相对环法线的穿越方向。两端回到桌面，所有辅助抓持解除，
双臂完全撤出环孔，释放后的观察窗口内保持此路径并满足原物理静置门槛。
不要求逐点复原作者最终绳形；要求穿环关系、放回和稳定性成立。

| 动作段 | 参考时间（s，非本地模拟秒或帖子播放器秒） | 手与绳的操作 |
| --- | --- | --- |
| 抓取并抬起 | 0–64.5 | 右手抓末端 80，左手抓另一端 0，建立操作空间 |
| 第一环 | 64.5–120.8 | 右手带 80 穿青环；左手绕开环边，将 0 放下 |
| 第一次换手 | 120.8–161.3 | 左手在末端前 41.25 mm 的节点 77 接住，右手再松开、撤离 |
| 第二环 | 161.3–224.4 | 左手送过绿环；右手在出口抓 80，左手再松开、撤离 |
| 第三环首次穿入 | 224.4–265.1 | 右手送过紫环，并调整夹爪姿态 |
| 第三环换手与撤臂 | 265.1–316.2 | 左手抓距末端 68.75 mm 的节点 75，右手松开并退回；此时会暂有 `R3+ / R3-` 两次穿越 |
| 重新牵引末端 | 316.2–336.2 | 右手从出口侧重新抓 80 并拉过紫环，消除多余反向穿越，再释放左手 |
| 放回与撤离 | 336.2–374.0 | 右手放回末端并释放，双手撤离，绳体自然静置 |

`reference_ik.py` 为每个手部目标求带 **0.02 rad** 限位余量的 IK。
靠近腕部限位时，对夹爪局部 X 轴自转作平滑小幅调整，保留夹爪原点和工具朝向轴；
它明确改变了参考姿态约 1.15°，没有将原姿态的越限解强行裁剪后宣称精确可达。
左手两段空手路径（phase 40、49）增加最大 3 mm 的 +Z 平滑抬高，避开第二环边缘；
绕行在动作段边界及所有抓取/松手时刻均为零。末段右手仍采用此前的 30 mm 抬高适配共享大桌面。
实际执行入口使用同一求解逻辑；接触触发、实测夹爪跟随、原生碰撞和真实关节越限检查保持原门槛。

离线入口：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.ik_plan \
  runs/environment-solvability/rope_threading/new_ik_plan
```

产物为关节轨迹 NPZ、分阶段审计 JSON 和静态参考动作图，无 MP4 或 HTML。
其中绳形图只显示**作者参考**，不是新 FEM 执行；机器人 IK 可达和采样碰撞检查不能代替
实际抓取、换手、绳体穿环及释放稳定性验证。本次动作实现变动需在后续物理执行中重新验证，
不能把旧资格记录直接计为新版动作的完整物理验收。

最终 v3 已完成全程离线检查：18,712 个求解时刻均可达，最小关节限位余量 **1.1512°**；
覆盖原参考点和 3 倍速度、5 ms 控制周期插值的 **43,645 个采样**中，无负接触距离样本。
插值位置误差最大 **0.00982 mm**，姿态误差最大 **0.00510°**。32 项相关回归检查通过。
对应 [完整方案与文件说明](../../../runs/environment-solvability/rope_threading/ik_margin_v3_20260920/README.md)、
[参考动作与终态图](../../../runs/environment-solvability/rope_threading/ik_margin_v3_20260920/reference_sequence.png)、
[审计报告](../../../runs/environment-solvability/rope_threading/ik_margin_v3_20260920/report.json)。
中间 v2 的侧向绕行碰到了第三环，已保留失败报告；正式候选 v3 使用向上的绕行。

### 2026-09-21：按 IK v3 录制完整物理流程

按用户要求启动 `runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/`。
启动前逐文件核对当前 IK、参考动作、碰撞预筛和共用 FK/IK 实现与 v3 报告哈希一致。
运行仍使用 v13 可压缩细网格 FEM、接触触发的公共辅助抓持、参考速度倍率 3，末尾静置 20 s。
同步录制 `cam_high / cam_low / cam_left_wrist / cam_right_wrist / detail` 五路，20 fps、960×540。
五路实际初始画面已打开检查；俯视和外部斜视覆盖整个任务，低视角能看到全部三个环孔。

独立运行驱动负责等待物理执行结束、验证五路视频，并在动作及目标终态通过后保留独立 MP4。
最终视频目标路径为 `demos/rope_threading/2026-09-21_ik_v3_attempt_1_<camera>.mp4`，
配套材料目标路径为 `runs/demo_metadata/rope_threading/2026-09-21_ik_v3_attempt_1/`。
失败或中断则保留原运行目录，不声明完整任务成功，也不覆盖先前证据。

运行是否仍进行、是否完成应分别读取该目录的 `driver_status.json`、`progress.json`、
`report.json` 与 `artifact_status.json`，不能将这条启动记录视为完成证明。
`runs/environment-solvability/rope_threading/current_recording.json` 指向本次录制。
此前按用户要求暂缓的时间步/迟发静置资格仍单独标记；实际物理和抓持检查未放宽。

本次运行现已停止：实际模拟 **66.115 s**，参考时间 **195.0145 s**，耗时约 **6.11 h**。
完整视频各 **66.1 s / 1,322 帧 / 20 fps**，五路均通过解码和同步校验；这些是未完成任务的连续片段。
已完成第一环、左手接取节点 77，以及第二环穿入，最终已观察到 `R1- / R2+`。
停在 phase 32（右手接近第二环出口），右手尚未完成接绳，第三环及最终放回未执行。

直接错误为 `Unreachable right target: position 0.000097 m, rotation 0.002965 rad`。
原生无翻转、绳长/应变、连续碰撞和抓持跟随检查仍通过，实际关节越限最大值为 0。
这次的失败来自带实际绳端反馈的目标姿态：末端相对作者参考偏移
`(-24.464, -10.633, +67.822) mm`，合计 **72.879 mm**。
在线控制将原参考手位平移至实际绳端，但保留原参考朝向，求解结果再次到达规划腕部下界
`-3.12158 rad`。位置残差 0.097 mm 尚满足 0.2 mm 门槛，姿态残差 0.170° 超过 0.115° 门槛。

CPU 复现中，更换为上一帧实测关节作为初值、将迭代上限从 160 提高到 1,000，均得到同一受限解；
因此并非仅增加求解迭代即可修复。只改变停住时刻的工具自转约 2.60° 可得到该单点精确解，
但进一步对固定实测绳端的整段接近作反事实预筛，单纯持续放开自转会产生约 124° 的姿态改变及
机器人自碰，不能据单点成功就启动原样重跑。下一步需要围绕实际绳端重规划接近方向与换手姿态，
同时检查整段碰撞和连续性。诊断保存在 `runs/environment-solvability/rope_threading/ik_feedback_failure_v1_20260921/`。

可播放片段：[外部视角](../../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/detail.mp4)、
[俯视](../../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/cam_high.mp4)、
[低视角](../../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/cam_low.mp4)、
[左腕](../../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/cam_left_wrist.mp4)、
[右腕](../../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/cam_right_wrist.mp4)。

### 2026-09-21：第二环接绳的新 IK 候选

已从上次失败快照生成 `feedback_handoff_v5_20260921`：左手固定节点 77 小转 6°，
右手沿尾段方向接近；接稳后左手仅小幅松开并轴向退出，右手再绕开第三环接回后续参考。
7,656 个采样无负接触距离，最小间隙 1.938 mm，最小关节限位余量 1.527°；
同时核对了实际控制插值和接回参考的关节分支连续性。11 项相关检查通过。

这是**有条件的离线规划**：左手转动后的绳尾形状仍为预测，必须重新观测再规划右手；
尚未接入在线执行器，也没有新的物理录制。37 s 双视角预演不包含绳体动力学或实际接触。
详见[新 IK 动作、门控与验收边界](rope_threading_feedback_ik_zh.md)。
预演：[细节](../../../runs/environment-solvability/rope_threading/feedback_handoff_v5_20260921/kinematic_detail.mp4) ·
[全景](../../../runs/environment-solvability/rope_threading/feedback_handoff_v5_20260921/kinematic_overview.mp4)。

## 几何与坐标

原绳长 1.1 m，半径 4 mm，共 80 个相连胶囊、81 个有序节点。
初态为桌面上的 U 形，两端未抓持，三个环的初始穿越计数均为零。
节点直接取自公开首帧，保留从 `v4_rope_link_0` 到第 79 段远端的材料方向。
目标材料顺序为 `R1- / R2+ / R3+`；`route_crossings` 仅返回有向几何穿越观测，
不将瞬时计数作为连续无穿透或任务成功的证书。

| 环 | 原参考中心（m） | 有向法线 | 颜色 |
| --- | --- | --- | --- |
| R1 | (0.075, -0.019, 0.331) | (1, 0, 0) | 青 |
| R2 | (0.010, 0.170, 0.310) | (0.8, 0.6, 0) | 绿 |
| R3 | (0.090, 0.315, 0.280) | (0.3, 0.9, √0.1) | 紫 |

三环中心线半径均为 75 mm，管半径为 6 mm，净孔径 138 mm。
每根竖直支柱半径 5 mm，与环的侧面连接；底座完整尺寸为 50 × 80 × 8 mm。
这些参数、支柱长度与定位来自公开几何，而非目测建模。

独立 `model/assembly.glb` 的原参考坐标整体增加 `(0, 0, 0.0009)`，桌面顶面为 z=0。
默认仿真转换为 `p_world = p_source + (-0.1356786, 0, 0.9205429)`，
将原桌面顶面 z=-0.0009 对齐到共享桌面 z=0.9196429。
三环相对绳子的布局不变。场景配置中的 `task.origin_xy_m` 可整体平移任务。
共享桌面为 1.5 × 1.4 m。严格初态碰撞审计发现：原共享 ALOHA 适配器相对任务坐标
降低了 20.9 mm，使底座法兰与初始绳端相交。此任务使用 `base_riser_height_m=0.0209`
和两个实体垫座恢复原参考的机器人/桌面相对高度；其他任务的默认安装高度不变。
建场时在原生 IPC 初始化之前设置参考 home 姿态，避免渲染位姿与原生碰撞体不一致。

## 物理模型与资产

源码入口：`topogym/tasks/rope_threading/`，职责为 `ThreadingLayout → ThreadingSceneBuilder → ThreadingScene`。
`reference.py` 从用户给定的公开文件提取首帧并校验哈希；建场不联网。
`prepare_assets.py` 生成可在 Blender 等工具中继续编辑的独立 OBJ/GLB。
`pre_build` 回调可为后续接触触发抓持接入声明；本初态没有端点约束。

- 环：64 × 24 的闭合三角网格，`convexify=False`，通孔真实保留。
  对原 64 段胶囊环的保守离散误差界约 0.142 mm。
- 绳：原中心线每段细分 4 次，321 截面、每截面 12 点，体网格由 TetGen 生成。
  使用连续 FEM+IPC、自接触、桌面/环/支架/机器人接触和直绳材料参考态。
  直绳参考态若导致四面体翻转则拒绝建场，不能悄悄改用弯曲初态作为无应力参考。
- 固定支架与环、底座存在设计连接处的静态重叠；关闭固定刚体间 IPC 接触和全场景交叠检查，
  单独检查绳子与全部夹具的初态正间隙。绳子不使用重力补偿。
- 默认 `E=100 kPa, nu=0.45, rho=650 kg/m³, mu=0.3`，接触距离 0.8 mm，
  摩擦速度正则化 1 mm/s，外步长 5 ms、4 子步；与原演示 MuJoCo 胶囊链的动力学不等价。
- 机器人采用原 ALOHA 双夹爪和 16 个自由度；保留未简化碰撞网格，
  严格执行测试采用 `external_articulation` 与机器人重力补偿。机器人接触操作尚未验收。

## 运行与检查

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.prepare_assets
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.rope_threading
.venv-gs121-nyx/bin/python -m unittest tests.check_rope_threading tests.check_configs_compose
```

默认输出 `runs/environment_bootstrap/rope_threading/wang_initial/index.html`。
保存三路展示视角、ALOHA 四路相机初态、相机环绕视频、静置前后状态、
解析后的配置、世界坐标资产及 JSON 报告。环绕只移动相机，不能当作机器人执行。
可用 `run.record_video=false` 省略视频，`run.settle_steps=0` 仅建场，
`run.output=<新目录>` 保留多次运行。

几何回归包含原尺寸与材料顺序、坐标变换、源布局正间隙、封闭体网格、
三种倾角的中心射线通孔检查、环壁命中对照、有向穿越和切触排除。
默认 40 步 / 0.2 s 自由静置检查有限状态、无翻转、桌面穿透小于 1 mm、
最大绳体位移小于 40 mm、仍未穿环和双臂待命漂移。
这只验证初态初始化与短时接触，不构成长时稳定性或穿环任务验收。

2026-09-17 的 `wang_initial` 实际运行已通过上述 0.2 s 检查；
七路初态图、两路静置后图和 45 帧 / 3 s 初态环绕视频均已生成。
资产、几何、配置组合、项目导入及参数卡相关的 13 项回归检查通过。

## 严格物理审计（2026-09-17）

早期 `wang_initial` 的 0.2 s 检查未覆盖原生机器人底座穿插，不能据此判断场景物理可靠。
`physics_v1/v2` 保存初态穿插失败；`v3` 为明确中止的短试跑；`v4` 完成五秒但末尾两秒
漂移 2.567 mm，超过 2 mm 门槛。修正高度并将低速摩擦参数恢复到项目已校验的 1 mm/s 后，
`physics_v5/free_baseline` 的 4000 个原生子步全部通过：无表面穿透、无四面体翻转，
最大绳长变化 0.208%，末尾两秒漂移 0.416 mm，最大速度 0.210 mm/s，全部 Newton 帧收敛。
`physics_v5/ring_contact` 随后完成 20 s / 16000 个原生子步，抬升、穿入 R1、持续接触滑动、
完全释放和落桌后静置全部通过。100 个接触样本中的穿越点移动 10.156 mm；最大绳长变化
0.872%，最大局部轴向应变 7.285%，最小体积比 0.694；末两秒漂移 1.457 mm，
最大速度 0.799 mm/s，全部 Newton 帧收敛。该试验使用显式软抓持夹具，不能算机器人执行。
时间步/网格对照和机器人接触资格仍须分别通过，不能从前两项推断完整可靠性。

初次并发启动 `free_halfdt` 在 CUDA 初始化时以退出码 134 终止，未产生物理轨迹；
这是运行时初始化失败，不提供机械结论。串行流程将其保留，并为重试新建 `free_halfdt_attempt_2`。

### 初始版本结论：未通过，未录制完整 demo

`free_halfdt_attempt_2` 将外步长减半到 2.5 ms，原生子步从 1.25 ms 减到 0.625 ms，
其余场景、材料和求解参数保持一致。运行在 2.498125 s / 3997 子步处因 GPU 显存不足中断；
此前所有原生子步收敛，没有表面穿透或四面体翻转。这不是一份完整的五秒对照。

但是，已保存的共同前 2.48 s 足以构成数值超差反例：直接匹配 124 个相同采样时刻、
不进行时间插值，在 0.06 s 的 81 个原始材料节点的 RMS 位置差为 **7.759 mm**
（门槛 2 mm），最大单点差为 **8.028 mm**（门槛 5 mm）。
竖直方向的整体弹起主导该差异；此项失败发生在显存中断之前，
不能归因于后续运行时错误。后续模拟也不能消除已经观察到的峰值超差。

初始绳表面离桌面 0.3 mm，位于 0.8 mm 的 IPC 接触作用范围内；9 月 18 日的单因素对照
支持初始化接触预载是启动上弹的主要原因（见下节），几何上没有陷入桌面。应先消除初始接触的时间步敏感性，再重新
完成时间步对照、网格细化、实际机器人抓取和四路完整录制。不能通过删掉起始帧或放宽门槛来计为通过。

可视化报告：`runs/environment-solvability/rope_threading/physics_v5/index.html`。
初始弹起的慢放视频：`physics_v5/initial_bounce_video_v2/index.html`（相对于上述测试目录）。
这段 12 s 视频使用两次运行保存的 0–0.2 s 中心线状态，50 倍慢放，末帧停留 2 s；
空间图 Z 方向放大 10 倍，数值和坐标刻度仍是真实毫米。它是诊断可视化，不是当时的相机录屏。
所有配对帧使用同一物理时刻，20 ms 采样间不插值；视频第 3 秒对应物理 0.06 s 的 RMS 峰值。
`bounce_video.py` 可在 CPU 上生成视频，`manifest.json` 保存源轨迹哈希、时间映射和解码核对。
`qualification.json` 明确标注“不完整共同前缀”与超差，包含各次运行的配置和轨迹哈希。
未运行的 `ring_halfdt / ring_refined / robot_prefix` 保持待验收；没有生成或归档完整 MP4。

相关回归检查通过；全仓检查另在 `fiber_bundling` 参数卡处报
`Unqualified axes must remain candidate`，详见同目录的 `project_regression.log`。
它与本次绳穿环的数值超差是不同问题。

完整复测入口（新目录保留所有历史失败）：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_suite \
  runs/environment-solvability/rope_threading/new_suite --reference-speed 4 \
  --record-to runs/environment-solvability/rope_threading/new_full_reference
```

只有全部试验、数值比较、配置一致性和参考输入校验通过，流程才会启动录制。
当前 `archive.py` 要求完整执行成功、ALOHA 四路及 detail 共五路同步视频可解码，
并核对本次执行的物理配置、实现哈希、参考动作和资格证据一致，才可归档为完整 demo。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_probe \
  --output runs/environment-solvability/rope_threading/new_free
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_probe \
  --mode ring_contact --output runs/environment-solvability/rope_threading/new_ring
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_probe \
  --mode reference_prefix --reference-speed 4 \
  --output runs/environment-solvability/rope_threading/new_robot_prefix
```

`ring_contact` 是显式辅助约束的局部加载试验，不是机器人 demo。
每个原生 IPC 子步读取真实 FEM 顶点、速度和刚体表面；执行连续碰撞检查，或以
“测得间隙大于两倍最大顶点位移”给出该子步全区间的保守分离证明。
证据包含初态交叠检查、原生配置、实现哈希、压缩求解日志、轨迹和独立报告。
这些检查不包含完整弹性能量、真实硬件参数标定或实验误差认证。

`reference_motion.py` 校验公开 51 段二进制及各数组 SHA-256，再提取 18712 个唯一时间样本。
这些文件明确标注为原参考数据，不能当作本地执行结果。
机器人执行只使用关节/手部目标；绳体由 FEM+IPC 重新计算，禁止回写参考绳节点。
两侧原生指面均在接触距离内才启用辅助抓持，目标跟随实测夹爪变换，松手时解除。
完整执行要求单次连续模拟完成参考动作序列，并在释放后保持材料顺序 `R1-/R2+/R3+`。

## 启动接触与绳体弹性对照（2026-09-18）

证据及曲线：`runs/environment-solvability/rope_threading/startup_sensitivity_v1/index.html`。
共 10 次独立 GPU 运行，每次 0.2 s；每个参数分别运行 1.25 / 0.625 ms 原生子步。
没有机器人动作、端点固定、位置回写或速度清零。所有运行通过逐子步连续碰撞、无翻转、
绳长与局部应变检查；由于不足两秒，原始 `report.json` 的完整静置门槛保持未通过。

| 只改变的参数 | 最大平均上抬，1.25 / 0.625 ms（mm） | 时间步最大 RMS（mm） |
| --- | --- | --- |
| 原参数：E=100 kPa，表面间距 0.3 mm，接触距离 0.8 mm | 5.496 / 10.682 | 8.403 |
| E 降至 50 kPa | 4.435 / 6.743 | 3.780 |
| E 降至 20 kPa | 2.697 / 3.764 | 1.845 |
| 初始表面间距增至 1.2 mm，E 保持 100 kPa | 0 / 0（先下落） | 0.087 |
| 接触距离降至 0.2 mm，E 保持 100 kPa | 0 / 0（先下落） | 0.125 |

上抬峰值含初态零点，由每个原生子步读取；RMS 使用每 5 ms 保存的同一物理时刻和 81 个
材料点，不插值。本次原参数最大 RMS 出现在 0.065 s；旧视频每 20 ms 采样得到 0.06 s / 7.759 mm，
差别来自采样更密，不能把旧采样值当作连续时间峰值。
已核对全部体网格连通性和材料点编号一致；抬高试验先对同一源网格四面体化，再整体平移，
避免重新剖分带来的混杂。平移后相对理想平移的最大浮点残差约 3.0e-8 m。

原参数第一个 1.25 ms 子步的质心向上速度为 0.322 m/s；把初态放到接触作用范围外后，
首步变成约 -0.0123 m/s 的自然下落，且两个时间步都不再出现整体上弹。
两种独立接触调整给出相同方向的结果，支持初始接触预载为主因；降低 E 能缓解，不能把它当作
接触初始化的替代修复。当前实体 FEM 的 E 同时影响拉伸和弯曲刚度，尚无独立的绳体弯曲刚度旋钮。
20 kPa 在自由静置短跑中的最大局部轴向应变为 1.001%，但这不证明它在夹持/穿环加载时也适用。

入口保留默认参数，提供明确的试验覆盖：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.startup_study \
  runs/environment-solvability/rope_threading/new_startup_study
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.startup_review \
  runs/environment-solvability/rope_threading/new_startup_study
```

`physics_probe` 另支持 `--young-modulus`（Pa）、`--initial-rope-lift`（m）、
`--contact-distance`（m）、`--sample-interval`（s）和 `--startup-diagnostics`。
初始抬高通过 `task.geometry.rope_height_offset_m` 控制，只移动绳子；桌面、环和机器人保持原位。
这些参数实验不自动修改正式基线，也不会绕过完整执行的资格检查。

### 较软绳体与初始间距的组合

候选配置为 `configs/rope_threading_soft_start_preview.yaml`：E=50 kPa，绳子初态抬高 0.9 mm，
使表面间距为 1.2 mm；接触距离、摩擦、质量密度、直绳材料参考态及场景其他部分保持不变。
已校验此预设的完整物理配置与实际试验配置一致。

`soft50_gap12_settle_v1` 保留两次 2.2 s 试验。两组都消除了启动整体上弹，时间步 RMS 最大
0.159 mm；但末两秒从 0.2 s 开始，仍包含落桌后短暂振动，速度项未通过。
这个失败没有被忽略或放宽门槛；后续 `soft50_gap12_settle_v2` 使用相同参数从初态重新连续运行 3 s，
用于检验最后两秒（1–3 s）的完整稳定窗口。该复测也保留启动全过程的碰撞、形变和时间步对照。

**3 s 复测已完成，两组自由静置检查全部通过**。结果页面：
`runs/environment-solvability/rope_threading/soft50_gap12_settle_v2/index.html`。
分别观测 2400 / 4800 个原生子步，全部 Newton 求解收敛，无穿透或翻转；
最后两秒最大速度为 0.413 / 0.383 mm/s，最大漂移为 0.692 / 0.655 mm。
全过程最大绳长变化为 0.302% / 0.307%，最大局部轴向应变为 0.430% / 0.447%。
直接匹配包含启动阶段在内的 600 个保存时刻，最大 RMS 为 0.159 mm，最大单点差为 0.386 mm，
都在 0.23 s 出现。`verification.json` 保存配置对应、网格一致性、源文件哈希及上述结果的核对。
这是一项 3 s 自由静置验证，不替代原完整流程的 5 s 静置、20 s 接触加载、网格细化及机器人抓取验收。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.startup_study \
  runs/environment-solvability/rope_threading/new_soft_start \
  --variants gap12_soft50 --seconds 3
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.rope_threading \
  --config-name rope_threading_soft_start_preview run.record_video=false
```

较低 E 对实际夹持、悬空和穿环负载的影响仍需单独验收，不能用自由静置数据代替。

## 完整流程推进（2026-09-18）

新证据目录为 `runs/environment-solvability/rope_threading/physics_soft50_v1/`。
`physics_probe` 与 `physics_suite` 均支持 `--config-name rope_threading_soft_start_preview`，
确保候选物理参数贯穿资格测试、机器人执行与录制。

`ring_contact` 已完成 20 s / 16000 原生子步的辅助夹具加载：全部 Newton 子步收敛，
无穿透或翻转，最大绳长变化 1.716%，最大局部轴向应变 11.669%，最小体积比 0.713。
100 个接触样本中的穿越点移动 10.420 mm，释放后末两秒漂移 0.664 mm。
这是单环加载通过，不代替机器人抓取、时间步和网格对照。

公开关节轨迹的 CPU 运动学预检发现：末段右手放回时，夹爪基座落在较大的共享桌面范围内，
原路径可与桌面相交约 22.1 mm。`reference_actions.ending_lift` 从阶段 49 开始，
在 12 s 参考时间内平滑增加右手目标高度 30 mm；源数据保持不变，绳体仍由物理求解。
修改后的轨迹以 20 ms 参考时间间隔检查 18700 个姿态，关节限位和刚体代理接触筛查通过。
此筛查不包含实际柔性绳体、控制滞后和所有原生接触，不能替代完整物理执行。

机器人首轮录像 `robot_prefix` 在首次闭爪阶段停止并保留失败证据：闭合控制每步以滞后的
实测开度为起点，导致接触等待期间闭合过慢。改为积分闭合目标，保留双指实际接触门槛，
新运行保存于 `robot_prefix_attempt_2`。抓持审计同时核对实测手部变换与绳体抓持带中心，
跟随误差超过 2 mm 时立即停止，并保存每个抓持带的中心误差。

`robot_prefix_attempt_2` 已通过：实际连续运行 11.915 s，9532 个原生子步全部收敛，
右手在 4.870 s 建立双指接触（间隙 0.797 / 0.771 mm），绳端实际抬高约 58 mm，
在 6.915 s 解除抓持后继续模拟 5 s。最大抓持顶点跟随误差 1.374 mm，
原生机器人与渲染表面的最大差异 0.713 mm，无关节越界、刚体穿透、绳面穿透或四面体翻转。
最大绳长变化 0.403%，最大局部轴向应变 5.182%，末两秒漂移 0.352 mm，最大速度 0.373 mm/s。
五路同步视频均完整解码：每路 238 帧、20 fps、11.9 s。
播放页为 `physics_soft50_v1/robot_prefix_attempt_2/index.html`；这仍然只是首次抓取的局部验证。

`free_baseline / free_halfdt` 随后均完成 5 s 并通过：分别观测 4000 / 8000 个原生子步，
全部收敛，无穿透或翻转。末两秒漂移分别为 0.538 / 0.522 mm，最大速度为 0.298 / 0.287 mm/s。
每 20 ms 匹配一次保存状态，共 250 对、每对 81 个材料点；最大 RMS 为 0.128 mm（0.22 s），
最大单点差为 0.368 mm（0.30 s）。两项均通过原门槛；未对时间进行插值。
加载步长减半随后发现超差，完整执行尚未开始。

`ring_halfdt` 保留至 3.780 s：匹配的 189 个保存时刻中，最大 RMS 为 3.704 mm，
最大单点差为 5.149 mm，均在 3.12 s 出现并超出原门槛，因此提前停止。
差异主要位于仍接触桌面的绳段，夹持端在 3 s 的位置差约 0.11 mm；这项试验没有机器人动作，
不能归因于 IK。原生物理检查没有报告穿透或翻转，但步长收敛资格未通过。
后续 `loaded_accuracy_v1/tighter_baseline` 用 4 s 短加载诊断，将 Newton 速度容差从
10 mm/s 收紧到 1 mm/s（匹配摩擦平滑速度量级），迭代上限增加到 200。
诊断配置为 `rope_threading_soft_start_precise_preview`；它尚未通过完整资格测试。

收紧容差后的 4 s 基线短诊断完成了 3200 个原生子步，全部收敛、无穿透或翻转；
因为末尾仍在加载，它的完整静置/释放门槛按预期保持未通过。
与 `physics_soft50_precise_v1/ring_halfdt` 保存的共同前 4 s 匹配 200 个时刻后，
最大 RMS 降为 0.676 mm，最大单点差为 1.140 mm；原先约 3.1 s 的超差没有重现。
该结果支持 Newton 收敛精度是此段动态差异的主要来源；后续仍须完成严格容差下的
20 s 加载配对、网格细化、5 s 静置配对和机器人抓取资格，不能直接沿用旧容差下的通过结论。
新证据目录为 `runs/environment-solvability/rope_threading/physics_soft50_precise_v1/`。

严格容差的 `ring_halfdt` 已完整通过 20 s / 32000 原生子步，全部 Newton 帧收敛（最多 44 次迭代），
无穿透或翻转，最大绳长变化 1.685%，最大局部轴向应变 12.546%，最小体积比 0.685。
100 个接触样本的穿越点移动 13.110 mm；释放后末两秒漂移 0.830 mm，最大速度 0.494 mm/s。
同容差的完整 `ring_contact` 基线仍在运行，完整 20 s 时间步对照尚未形成。

该基线随后在释放落桌阶段出现新的超差：共同保存的前 15.06 s 内，最大 RMS 为 7.816 mm
（12.68 s），最大单点差为 34.448 mm（12.70 s）。因此停止该路线的完整录制；
`physics_soft50_precise_v1/high_drop_comparison.json` 保留这项失败，不能改记为通过。

### 受控抓放的演示范围

核对公开动作的六次松手后，发现四次高处松手都已有另一手在 41.25 / 68.75 mm 材料距离内支撑。
缺少邻近支撑的两次松手，原参考绳端离桌面约 76.8 / 40.0 mm；末段手部抬高 30 mm 后，
后者预计约 70 mm，实际高度仍由运行时原生状态检查，不能用参考状态代替。
之前的 33 cm 全部松手试验超出了这些动作条件。

`rope_threading_controlled_release_preview` 保留 E=50 kPa、初态间距 1.2 mm 与 Newton 容差 1 mm/s，
明确限制：释放点距桌面大于 90 mm 时，必须已有另一手在 80 mm 材料距离内抓持，否则立即停止。
相关回归同时覆盖低处释放、高处无支撑拒绝、远端抓持不足以替代邻近支撑、邻近换手允许。
这不是对任意高空自由落绳的物理资格认证；高处完全松手的失败会与最终归档独立保留。

对应局部加载试验保留抬升、穿入和 10 mm 以上接触滑动；12–15 s 将抓持点平滑降至离桌面
80 mm，16 s 完全松手，继续模拟至 24 s。时间步和网格对照继续使用 RMS 2 mm / 单点 5 mm 的原门槛，
并核对各加载测试的动作规格完全一致。首轮目录为 `physics_soft50_controlled_v1`，
`reference_release_envelope.json` 记录原参考的松手高度、支撑距离及源文件哈希。

该首轮发现放回夹具只做垂直下降时，环外自由绳长不足以触桌，释放后末端仍悬空约 5 cm，
因而持续摆动。求解子步收敛不代表已经静止，这一轮保留为放回路径诊断。
后续 `rope_threading_controlled_place_preview` 在下降期间额外水平送出 14 cm，
使末端能够落桌；释放高度及数值门槛不变。目录为 `physics_soft50_controlled_place_v2`。
该轮末端已落桌，尾窗漂移 1.721 mm 通过，但 RMS / 最大速度为 5.314 / 17.169 mm/s，
速度门槛仍未通过。`rope_threading_controlled_settle_preview` 因此把加载测试的释放后观察延长至
24 s（总计 40 s），完整执行在参考序列结束后自然静置 20 s。机器人前缀仍静置 5 s。
这项调整只延长观察时间，不重置速度或引入额外阻尼；新目录为 `physics_soft50_controlled_settle_v3`。
后续机器人前缀和完整执行统一改为参考时钟 3 倍速度。4 倍时被抓材料点的最大目标位移约
1.727 mm / 外步，接近 2 mm 实测跟随误差门槛；3 倍时该运动学位移约 1.295 mm，
为形变和控制滞后保留更多余量。这个估计本身不代替新的机器人前缀实测。

### 形变耗散候选与原生接口核查

40 s 的无阻尼加载已通过静置检查：尾窗 RMS 速度 0.099 mm/s、最大速度 0.183 mm/s，
漂移 0.361 mm。但它与相同加载参数的前一轮在共同 24 s 内的最大绳形 RMS 为
2.516 mm、最大单点差为 10.305 mm；落桌瞬态对数值扰动敏感，延长静置并未解决重复性问题。
证据为 `physics_soft50_controlled_settle_v3/repeatability_v2_v3.json`，这一组未进入完整录制。

`rope_threading_deformation_damping_preview` 增加明确记录的形变耗散，系数 α=2 s⁻¹。
每个原生子步先读取实际位置、速度，将质量加权的整体平移和转动投影出去，再施加
`Fᵢ = −α mᵢ (vᵢ − v_rigid,i)`。该项的合力、合力矩为零，瞬时功率非正；
它是现象性的形变阻尼模型，未经实物绳材标定，不宣称完整材料能量认证。
质量按静止四面体体积分配，以保持网格细化时的尺度一致。

实现使用 [libuipc v0.0.25 的节点外力接口](https://github.com/spiriMirror/libuipc/blob/v0.0.25/docs/specification/constitutions/finite_element_external_force.md)。
它与软抓持共用 `is_constrained` 标记，因此未抓持节点的 `strength_ratio` 始终为零，
仅实际接触后参与抓持的节点具有位置弹簧刚度。5 项专门检查覆盖刚体运动零阻力、动量守恒、
耗散功、坐标变换、质量细分及释放后的零位置刚度；原参考动作检查另外 9 项通过。
`damping_api_smoke_v1` 的 1.25 s / 1000 个原生子步全部收敛，耗散力审计通过，
抓持跟随误差 1.48 μm。它只验证接口，未覆盖完整静置/动作，因此总 `report.passed` 按预期为 false。
新的完整资格目录是 `physics_soft50_damped_v4`；先前 33 cm 无阻尼自由落下的失败仍独立保留，
新模型尚未验证该工况。

该候选的 40 s 基准加载已通过：32000 个原生子步全部收敛，最多 9 次 Newton 迭代，
无求解警告、表面穿透或四面体翻转。最大绳长变化 2.467%，最大局部轴向应变 10.383%；
环上接触滑动 12.374 mm，受控释放及观察时长均通过。末两秒 RMS / 最大速度为
0.135 / 0.250 mm/s，漂移 0.485 mm。32000 次耗散力应用的功率、合力与合力矩检查全部通过。
此结果只代表基准加载通过。其半时间步运行在松手后出现超差，在 17.34 s 停止；
共同保存的 867 个时刻中，最大 RMS 为 24.175 mm，最大单点差为 128.953 mm。
释放前最大 RMS 为 1.200 mm；释放后绳端落桌、回缩并弯折，两条轨迹随后向不同方向偏离。
两组此前均未报告穿透、翻转或求解不收敛，但这不等于轨迹对步长不敏感；该候选未通过资格检查。
`physics_soft50_damped_v4/release_divergence.png` 保留原生状态对照。

后续候选 `rope_threading_deformation_damping20_preview` 将 α 提高到 20 s⁻¹，
对应形变速度约 50 ms 的耗散时间尺度；重力、整体刚体模式和位置约束规则不变。
基准 / 半时间步的 αΔt 分别为 0.025 / 0.0125，低于耗散项的显式稳定性上限。
新证据目录为 `physics_soft50_damped20_v5`。这仍是待验收的仿真参数，不是实物绳材标定结果。

该候选的两组运行已完成共同前 18 s：全程最大 RMS 为 1.614 mm、最大单点差 2.535 mm，
峰值发生在释放前的减速阶段。单独看 16–18 s 的释放与落桌窗口，最大 RMS 为 0.464 mm、
最大单点差 0.973 mm，18 s 时的 RMS 差为 0.157 mm，先前的落桌后明显分叉未重现。
该中间结果保存在 `release_prefix_comparison.json`，不是完整 40 s 的通过证书。
`damping_response.png` 比较 α=2 / 20 s⁻¹ 的基准释放响应，明确区分材料模型比较与时间步比较。
加载及静置的时间步对照还会核对输入网格逐项完全相同，并对 `mesh.npz` 记录哈希。

### 长运行显存修复

`physics_soft50_damped20_v5` 的共同轨迹继续到 22.52 s，数值差异仍在原门槛内，
但两组并发运行最终耗尽显存，分别停在 26.91625 / 22.525625 s；此前 21533 / 36041 个
原生子步均收敛、耗散力审计通过。两份报告仍标记失败和观察不完整，不能当作完整资格证据。

`memory_growth_v1/allocation_owners.json` 将主要增长定位到 Genesis 1.2.1 的
`FEMSolver.save_ckpt`：不计算梯度时也按原生子步创建新的位置、速度、活动状态检查点，
每步约 0.2 MB。状态查询的梯度队列还会保留较小的额外历史。
任务内的 `runtime_memory.ForwardOnlyMemory` 仅在不计算梯度时复用一个新增检查点键，
每步继续调用原方法，保留其读取与 `copy_frame` 操作；查询返回值仍由调用者持有，
只移除无用的梯度队列引用。共享框架和其他环境没有修改。

`memory_growth_fixed_v1/verification.json` 的 2 s / 1600 子步实测通过：采样中的 PyTorch
显存始终为 1873920 字节，查询队列为零，检查点数量固定为初始化已有 4 个加复用的 1 个。
修复前后输入网格、物理配置一致，321 个截面的最大 RMS / 单点差为
0.000047 / 0.000122 mm。此短诊断只验证缓存与轨迹一致性，完整物理门槛按预期仍未通过。
缓存语义、耗散与参考动作相关的 17 项检查通过。新的完整资格目录为
`physics_soft50_damped20_v6`，保持 α=20 s⁻¹；还会记录原始框架检查点方法的源码哈希。

v6 的 40 s 基准加载已通过：32000 个子步全部收敛，无穿透、翻转或求解警告，
末两秒 RMS / 最大速度为 0.128 / 0.230 mm/s，漂移 0.439 mm。
整个运行中缓存保持 5 个检查点，PyTorch 分配量为 1873920 字节；与修复前共同
26.9 s 的最大 RMS / 单点差为 0.000368 / 0.001031 mm。
长时缓存验证通过后，时间步与网格两项独立对照安排并行运行；调度器暂缓启动后续项，
避免重复任务，完成后自动恢复。调度记录为 `parallel_mesh_scheduling.json`。
两项启动后的 GPU 空闲显存约 11 GB；物理参数、完整观察时长与验收阈值均未改变。

v6 的 4×12 与 6×16 网格对照在放回减速阶段超出原门槛：14.2 s 时 RMS 为
2.007170 mm，前 15 s 的最大单点差为 3.726400 mm。求解与机械检查仍通过，
但这不构成网格收敛通过。较粗网格的半时间步运行在 14.9075 s 主动停止，
报告保留为不完整；较细网格继续完成整段加载，作为可复用基准的候选。
完整 40 s 的粗细网格比较最终 RMS / 单点差为 4.039782 / 6.615983 mm，
最大值发生在末态；证据为 v6 的 `parallel_mesh_scheduling.json` 和两份完整加载轨迹。

`rope_threading_damped20_fine_preview` 将正式网格提高至轴向细分 6、周向 16、
四面体最大体积 1e-8 m³；弹性、阻尼、接触参数、动作速度和误差门槛不变。
更细的对照为轴向细分 8、周向 20、最大体积 5e-9 m³。
`--refined` 现在相对当前基准继续细化，避免升级基准后错误地与同一网格比较。
新增检查确认新基准物理配置与 v6 的细网格完全一致，且后续网格确实更细；共 18 项检查通过。

新资格目录为 `physics_soft50_damped20_fine_v7`。仅在 v6 细网格完整运行且单项物理检查通过后，
才独立复制为新基准，并在 `baseline_provenance.json` 中记录来源及哈希；不会宣称重新执行过基准。
新半时间步运行保持相同输入网格，完整机器人演示仍须等待所有资格检查通过。
该细网格基准已完整通过：32000 个子步全部收敛，最多 8 次 Newton 迭代，
无求解警告、穿透或翻转；最大绳长变化 2.591%，最大局部轴向应变 10.851%。
末两秒 RMS / 最大速度为 0.149 / 0.274 mm/s，漂移 0.468 mm。
基准已按上述来源记录复制到 v7，随后启动 8×20 的独立网格比较。

v7 的 6×16 / 8×20 对照在提绳阶段失败：共同 2.24 s 的最大 RMS / 单点差为
5.142712 / 10.839763 mm；8×20 在 2.245 s 主动停止，半时间步也停止并保留不完整报告。
约 1.7 s 后，差异主要出现在桌面上的自由绳段，抓持端差异仍不足 0.5 mm。
已验证这三组的物理实现源码哈希一致，时间步对照的输入网格逐项相同，见
`runtime_source_check.json`。

排查时，最初的自接触距离统计包含了四面体内部节点，不能作为外表面接触证据。
仅保留真实边界顶点后，两种网格初态在 0.8 mm 内均无自接触候选，见
`boundary_only_self_contact_diagnostic.json`。后续在 `mesh_contact_diagnostic_v1` 中
用短时无摩擦诊断区分材料 / 夹具响应与摩擦响应；该配置不作为正式 demo 的物理资格。

### 光滑初始绳形修正

初始 81 个参考点位于同一条平面圆弧上。此前只沿参考折线插点，保留每个原始节点
2.25° 的拐角，反而把弯曲集中到越来越短的 FEM 单元中。轴向细分 4 / 6 / 8 时，
最大离散曲率为 11.42 / 17.14 / 22.85 m⁻¹；这不是对同一条光滑绳形的合理细化。
对应网格的初始应变诊断位于 `mesh_contact_diagnostic_v1/initial_curvature_strain.json`。
无摩擦诊断前 2 s 的 RMS / 单点差为 0.841 / 1.539 mm，表明桌面摩擦会进一步放大差异。

`rope_threading_damped20_smooth_preview` 保留材料与接触参数，改为沿原始点所在圆弧采样。
所有原始材料点保持原位置；不同细分下曲率一致，初始弧长较 1.1 m 的参考折线仅增加约
0.07 mm。新增检查覆盖原始点不变、曲率与长度收敛，共 20 项检查通过。
历史配置仍使用原来的折线模式，避免改变已保存试验的含义。

新的完整资格目录为 `physics_soft50_damped20_smooth_v8`，以 4×12 网格为基准、
6×16 为对照；先检查修正后的空间与时间离散收敛，再进行机器人前缀与完整执行。
自动流程最多同时运行两项 GPU 复验，任何已观测的误差超限都会保留轨迹并停止该组，
全部检查通过后才进入录制。

v8 的粗细网格在释放后仍超限：共同 17 s 的最大 RMS / 单点差为
2.701507 / 5.064532 mm，RMS 峰值在 16.4 s。自动流程停止并保留基准 27.41 s、
细网格 17.045 s 的不完整结果。圆弧建模修正已保留，但 4×12 网格尚未通过完整精度检查。
后续 `rope_threading_damped20_smooth_fine_preview` 用 6×16 网格作为正式候选，
8×20 作为加密对照，保持相同材料、阻尼、接触和验收阈值。
新目录为 `physics_soft50_damped20_smooth_fine_v9`，重新完整执行各项测试。

v9 的 6×16 / 8×20 在前 2 s 再次超限，RMS / 单点差为 3.782898 / 5.445652 mm；
两组分别在 2.42 / 2.015 s 停止并保留证据。因此只继续加密不足以解决当前接触敏感性。
同一 6×16 光滑网格与 v8 的重复运行已确认输入网格相同，前 1 s RMS 差仅
0.000115 mm，重复性本身正常。
完整的 3 s 无摩擦诊断最大 RMS / 单点差为 0.851 / 1.539 mm，全部求解子步收敛；
报告因未执行完整动作和静置按预期不通过。后续短诊断分别测试 0.2 mm 的接触激活距离、
10 mm/s 的摩擦速度正则化，保持其他参数一致，证据保留于 `mesh_contact_diagnostic_v1`。
这些短诊断均不作为正式 demo 的物理资格。

两项接触参数诊断均完成 3 s、全部原生子步收敛，且无机械异常：0.2 mm 接触距离的
最大 RMS / 单点差为 8.353 / 26.417 mm；10 mm/s 摩擦过渡的结果为
8.323 / 26.612 mm。二者均不采用为新正式参数。后续
`rope_threading_damped20_solver_precise_diagnostic` 保持原材料、阻尼和摩擦设置，
将 Newton 速度容差与线性系统相对容差均从 1e-3 收紧到 1e-5，单独检查求解停止误差。
实际原生配置值保存在 `mesh_contact_diagnostic_v1/solver_precision_native_values.json`。
该组仍是 3 s 诊断，不能代替完整资格或完整演示。

收紧求解容差的 3 s 对照仍未通过，最大 RMS / 单点差为 8.162 / 25.910 mm，
与原配置的差异很接近，未支持求解停止容差是主因。
新增解析桌面的对照只替换绳子与桌面箱体的原生接触对：相同平面高度 0.9196429 m、
相同接触对摩擦系数 0.173205（绳材料 0.3 与静态材料 0.1 的几何平均）。
机器人仍与原有限箱体碰撞；绳体每个原生子步必须离桌面边缘至少 1 cm。
原生接触对替换与有限范围检查的两项 CPU 测试通过。解析桌面前 2 s 的 RMS
仍为 3.782856 mm，与箱体结果基本一致，未支持桌面三角网格是主因。

下一组完整资格目录为 `physics_soft50_damped20_plane_finer_v10`，配置
`rope_threading_damped20_plane_finer_preview`，以 8×20 网格为基准、10×24 为对照，
最大四面体体积分别为 5e-9 / 2.5e-9 m³。保留解析桌面的有限范围审计，材料、
阻尼、原求解容差、参考速度和 2 / 5 mm 比较门槛不变。该组仍待验收，尚无完整 demo。

v10 随后在共同前 3 s 超差：最大 RMS / 单点差为 3.062 / 5.410 mm，
RMS 峰值在 2.22 s。两组停止于 4.74 / 3.03 s，报告保留为失败和不完整。
在 10×24 网格原生 2.005 s 的真实表面状态中，独立距离查询发现 106 个
0.8 mm 内的近邻自接触候选，最小间隙 0.787790 mm；全部接触模板涉及的
材料跨度仅为 1.375–2.750 mm。这次仅使用真实边界顶点，未包含内部四面体点。
状态、哈希和局部性统计保存在 v10 的 `fine10_self_contact_state.npz`、
`fine10_self_contact_locality.json`。候选几何并不直接测量原生接触力；后续复验用于
检查这些相邻绳面是否因较大的接触作用范围而影响网格比较。

当前候选 `rope_threading_damped20_plane_contact02_preview` 将接触距离降至
0.2 mm，仍比较 8×20 / 10×24，证据目录为 `physics_soft50_damped20_plane_contact02_v11`。
机器人双指抓持门槛、加载试验接触统计和实际原生距离必须一致；不再把 0.8 mm
写死在说明或接触计数中。相关 22 项检查通过。完整执行仍需等待该候选全部资格检查通过。

v11 的共同前 3 s 仍超差：RMS / 单点差为 3.024 / 5.420 mm，峰值在 2.20 s。
两组停止于 4.175 / 3.020 s，所有已观测原生子步收敛。该结果说明减小作用距离仍不足以
解决网格差异，不能将此前近邻候选直接视为唯一原因。
`mesh_contact_diagnostic_v1/pure_bending_discretization.json` 进一步记录了一个 CPU 辅助检查：
把解析的小变形纯弯曲位移采样到现有四面体顶点，计算其线性弹性能量。
在泊松比 0.45 时，8×20 / 10×24 的能量分别为同体域连续解的 1.393 / 1.281 倍；
泊松比 0.30 时降为 1.182 / 1.131 倍。此项是给定位移场的近似误差，未求解静力平衡，
不能把能量比直接当作已测得的有效弯曲刚度。

当前 `rope_threading_damped20_compressible_preview` 仅将 v11 的泊松比改为 0.30，
检验更易压缩的有效绳材模型；E=50 kPa、密度、摩擦、α=20 s⁻¹、接触距离和所有门槛不变。
该材料候选未经实物标定。完整资格目录为 `physics_soft50_damped20_compressible_v12`，
仍比较 8×20 / 10×24；基础几何的另 7 项检查也已通过。尚无通过完整验收的 demo。

v12 的共同前 3 s 仍未通过，最大 RMS / 单点差为 2.828 / 5.085 mm。
当前 `rope_threading_damped20_compressible_fine_preview` 保持该材料和接触设置，
使用 10×24 / 12×28 网格、最大四面体体积 2.5e-9 / 1.25e-9 m³，目录为
`physics_soft50_damped20_compressible_fine_v13`。共同前 3 s 的最大 RMS / 单点差已降至
0.578 / 1.938 mm，但完整 40 s 加载、时间步对照及机器人测试仍在进行。
资格汇总增加了已记录物理源码在各试验之间的一致性检查；录制之前仍会核对当前源码。
相关的 12 项参考动作与资格逻辑检查通过。

v13 的 10×24 基准已完整通过 40 s 加载与受控释放：32000 个原生子步全部收敛，
无求解警告、穿透或翻转；最小体积比 0.505，最大绳长变化 2.482%，最大局部轴向应变 8.421%。
最后两秒 RMS / 最大速度为 0.159 / 0.298 mm/s，漂移 0.577 mm。环内接触样本 100 个，
穿越点移动 11.037 mm；耗散力、固定内存占用及有限桌面范围检查均通过。
12×28 对照也已完整通过 40 s：32000 个子步全部收敛，最小体积比 0.452，
最大绳长变化 2.492%，最大局部轴向应变 8.715%；末两秒 RMS / 最大速度为
0.160 / 0.302 mm/s，漂移 0.583 mm。
**完整网格对照已通过**：匹配 2001 个实际保存时刻和每帧 81 个原始材料点，
最大 RMS / 单点差为 1.538 / 4.048 mm，分别发生在 17.58 / 16.10 s。
加载半时间步对照共同前 14 s 的 RMS / 单点差为 0.762 / 1.901 mm，仍在门槛内。
**5 s 自由静置配对已完整通过**：4000 / 8000 个子步全部收敛，无穿透或翻转，
末两秒最大速度为 0.284 / 0.269 mm/s，漂移 0.498 / 0.478 mm。
250 个匹配时刻的最大 RMS / 单点差为 0.076 / 0.342 mm。
六项试验的实际配置和已记录物理源码一致性检查均通过；两对时间步试验的初始网格逐项相同。
加载的完整步长对照和已启动的机器人抓取测试尚未完成，不能据此宣布完整资格通过。

v13 首次机器人前段在 14.05 s 完成，但未通过松手后 5 s 的末尾静置验收：
末两秒 RMS / 最大速度峰值为 7.941 / 47.620 mm/s，漂移 2.359 mm。
它在 6.32 s 建立双指接触，9.05 s 从桌面上方约 56.48 mm 释放；
11240 个原生子步全部收敛，抓持跟随最大误差 0.661 mm，原生机器人表面位姿误差 0.546 mm，
抓取、IK、CCD、长度和局部应变检查均通过。失败项是末尾静置，不能把该前段算作通过。
采样记录显示 13.24 s 附近有一次局部运动峰值，14.04 s 已降至 RMS 0.239 mm/s；
仍须完整观察更长尾段，不能用最后一帧替代两秒窗口验收。

`robot_prefix_attempt_2` 从初态重新执行并录制五路视频，将静置时长与完整流程统一为配置中的 20 s；
材料、动力学、动作速度及验收门槛保持不变。首次 `ring_halfdt` 因协调器联动停止于 34.22 s，
其共同前 34 s RMS / 单点差为 0.762 / 1.901 mm，仍在门槛内；
`ring_halfdt_attempt_2` 重新执行完整 40 s，不续接失败进程的状态。
原失败和中断证据均保留，`cases.json` 指向新尝试。
已通过的无机器人试验仅在确认执行代码等价后复用：保留原始源码哈希，
比较去除不可达 `reference_mode` 分支后的驱动 AST，其他物理源码必须逐项一致；
机器人与完整执行仍要求源码完全相同。相关 5 项检查覆盖误复用和存档篡改拒绝路径。

重跑在 13.24 s 的保存样本中复现了迟发运动，RMS / 最大节点速度为 7.789 / 47.497 mm/s。
13.16–13.36 s 间位移最大的原始材料点是另一自由绳端（节点 0），位移约 0.861 mm，
XYZ 分量为 +0.833 / +0.217 / −0.013 mm，主要沿桌面水平方向；这只是该 0.2 s 区间的诊断。
详见 `physics_soft50_damped20_compressible_fine_v13/robot_release_sliding_observation.json`。
该记录来自每 20 ms 保存的样本，不能替代逐原生子步的最终静置验收。

`robot_prefix_attempt_2` 已完整通过 29.05 s：23240 个原生子步全部收敛，
末两秒 RMS / 最大速度为 0.0168 / 0.0959 mm/s，漂移 0.188 mm。
五路视频均为 581 帧、20 fps、29.05 s，已完整解码并核对同步与播放页依赖；
这只是抓取、抬升、释放及静置的前段，不包含三环完整任务。
其中约 9.05 s 的掉落来自测试脚本主动松手：`reference_prefix` 在参考时间 25 s 截断，
显式解除抓持约束并打开夹爪，随后观察自由静置。此时的提前释放并非完整参考动作的一部分；
完整模式没有这个前段截断分支，会继续抓持并执行后续交接。
本次已使用公共 `topogym.primitives.fem_attachment.FEMRopeAttachment`：6.32 s 双指接触后启用，
抓持期间最大跟随误差 0.662 mm；9.05 s 明确解除。13.24 s 的迟发小幅运动发生于解除约 4.19 s 后，
不能把这两个时刻都归因于夹爪内滑脱。原始执行源码哈希、事件和实测手指状态的核对结果保存在
`physics_soft50_damped20_compressible_fine_v13/robot_prefix_release_audit.json`。
局部视频直链：[高位](../../../runs/environment-solvability/rope_threading/physics_soft50_damped20_compressible_fine_v13/robot_prefix_attempt_2/cam_high.mp4) ·
[低位](../../../runs/environment-solvability/rope_threading/physics_soft50_damped20_compressible_fine_v13/robot_prefix_attempt_2/cam_low.mp4) ·
[左腕](../../../runs/environment-solvability/rope_threading/physics_soft50_damped20_compressible_fine_v13/robot_prefix_attempt_2/cam_left_wrist.mp4) ·
[右腕](../../../runs/environment-solvability/rope_threading/physics_soft50_damped20_compressible_fine_v13/robot_prefix_attempt_2/cam_right_wrist.mp4) ·
[细节](../../../runs/environment-solvability/rope_threading/physics_soft50_damped20_compressible_fine_v13/robot_prefix_attempt_2/detail.mp4)。

`ring_halfdt_attempt_2` 也跑完了 40 s，64000 个原生子步全部收敛，无穿透或翻转，
完整 40 s 绳形对照最大 RMS / 单点差为 0.762 / 1.901 mm；
但第 40 s 附近出现迟发运动，末两秒 RMS / 最大速度达到 4.470 / 21.235 mm/s，
漂移 1.087 mm，因此该次试验仍判为未通过。当前已通过 5/6 项，完整 51 阶段尚未录制。
`ring_halfdt_attempt_3` 保持同一加载动作、材料、网格、步长和门槛，从初态连续观察至 60 s；
前 40 s 与基准做数值对照，额外 20 s 只验证细时间步运行的继续静置，明确不计作配对对照。
原 40 s 失败证据继续保留；数值对照结果现在记录两次运行的末时刻及未配对尾段，
相关 6 项证据逻辑检查已通过。

正式录制将使用 `rope_threading_damped20_fine_full_observation`：仅把完整动作结束后的自然静置
延长到 60 s。该停止观察时长与动力学参数签名分开核对，禁止比已通过的机器人前段 20 s 更短；
材料、网格、步长、控制器和释放高度等参数仍须逐项相同。两份实际配置的物理参数一致性已核对，
8 项证据逻辑检查通过。正在运行的协调器通过 `recording_request.json` 把这一录制配置交给新进程，
完整执行与归档前都会再次核对配置、源码和验收证据。

常规串行执行入口如下。全部资格测试通过后才启动完整 51 阶段录制；失败证据不会覆盖。

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_suite \
  runs/environment-solvability/rope_threading/physics_soft50_damped20_compressible_fine_v13 \
  --config-name rope_threading_damped20_compressible_fine_preview --reference-speed 3 --ring-halfdt-seconds 60 \
  --record-config-name rope_threading_damped20_fine_full_observation \
  --record-to runs/environment-solvability/rope_threading/full_damped20_compressible_fine_v13
```

依据 2026-09-19 更新的根目录 AGENTS.md，后续录制与验收只生成 Markdown / JSON 记录，不再生成或维护 HTML。
正式成功后，五路独立 MP4 归档到 `demos/rope_threading/`，证据归档到 `runs/demo_metadata/rope_threading/<run_id>/`。
现有历史页面保留，不作为本次交付入口。协调器已更换为新规则的版本，正在运行的半时间步物理进程未中断、未续接或重置。


## 2026-09-21：三段 IK 串联与反馈执行

新方案已接入完整执行器，详见 [反馈 IK 说明](rope_threading_feedback_ik_zh.md)。
第二环接绳时暂停参考时钟，按当前绳端与尾段方向重规划；确认双指接触和右手辅助抓持后才释放左手。
之后接回第三环，继续放置、退手、解除全部抓持与静置。

整体条件运动学预览为 186.8 s：[细节](../../../runs/environment-solvability/rope_threading/combined_ik_v3_20260921/combined_kinematic_detail.mp4) ·
[全景](../../../runs/environment-solvability/rope_threading/combined_ik_v3_20260921/combined_kinematic_overview.mp4)。
46,454 个采样未检出负接触距离，两处关节接缝连续。两路均为 3,736 帧、20 fps，完整解码及同步检查通过。
画面省略绳体，拼接使用独立检查点，不属于完整物理 demo，不能证明实际绳形和抓取。

串联复核在旧物理记录约 14.35 s 和 53.185 s 确认了原检查遗漏的机器人自身网格相交。
已分别加入接绳前最大 +X 10 mm 的平滑绕行，以及首次换手时保持左手实测位姿、右手窄开后立即退出 80 mm。
同时补充每个控制帧的实测机器人三角网格检查；凸包候选需确认真实三角相交，避免把凹网格凸包接触误判为穿透。
49 项相关测试通过。此前“旧运行原生报告通过”不能推导出机器人自碰也通过。

连续物理录制 `full_feedback_ik_20260921_attempt_4` 已排队等待显存，足够后自动从初态执行并记录五路视频；
以 [当前运行入口](../../../runs/environment-solvability/rope_threading/current_recording.json) 和运行目录最终 report.json 为准。
前两次新尝试在 1.855 s / 1.620 s 主动停止以加入上述修正，证据保留，均未验证新的换手。
第三次在初始化时因 CUDA 显存分配失败退出，未开始物理动作。当前空闲约 8.5 GB，
等待器每 30 s 检查一次，空闲连续两次达到 16,000 MiB 后自动启动；保持物理设置并核对已检查的源码哈希。
本次按用户授权继续完整动作探索，迟发微小滑动的正式资格复验仍暂缓；
整段动作与最终构型通过后才归档完整探索视频，不能据此自动宣告完整物理资格通过。
