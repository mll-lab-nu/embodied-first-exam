# 绳穿环：五档场景

## 三变体完成目标：模型与闭环接力开发（2026-10-03，已完成）

easy／medium／hard 均已从 home 经统一 Env／SegmentRunner 完成原生任务，视频按本轮范围暂不制作。
本轮证据位于 `runs/test_results/rope_threading_goal_20261003/`，汇总见该目录 `goal_completion.json`。

| 变体 | 原生结果 | 仿真时长 / 完整 tick | 证据 |
| --- | --- | --- | --- |
| easy | `task_success`，`R1− R2+` | 49.76 s / 1244 | [实测报告](../../../topogym/planning/rope_threading/reference_relays/easy_evidence.json) |
| medium | `task_success`，`R1− R2+ R3+` | 74.68 s / 1867 | [实测报告](../../../topogym/planning/rope_threading/reference_relays/medium_evidence.json) |
| hard | `task_success`，`R1− R2+ R3+` | 74.92 s / 1873 | [实测报告](../../../topogym/planning/rope_threading/reference_relays/hard_evidence.json) |

三轮成功的 `from_default_home`、`robot_execution_verified`、`plan_complete`、
`physics_tick_complete`、`control_step_complete`、`evidence_complete` 均为 true，原生停稳持续 0.52 s。
这些是显式加速开发配置下的成功；报告保留 `qualification=unqualified`，未执行默认模型的
物理精度、收敛性或视频验收。打包参考与单命令执行见 [oracle 入口](../../../topogym/planning/rope_threading/README.md)。
Hard 的 489 个校准／重算路点另行开启整臂环架检查复核，未检出接触；该离线采样复核
不改变当前候选仅让机器人手指参与 IPC 环架接触的物理条件。
Medium 同样检查 489 个路点，3 点有环架重叠，最大估计 2.794 mm，均未超过 3 mm 额度；
该估计来自 FCL 几何检查，不是接触力测量或连续路径证书。

Agent 执行侧审计（2026-10-03）：仓库现有 easy／medium／hard 的 standard、privileged 共六个
Harbor 任务包，均为 `task_parameters={}`、`grasp_assist.model=none`，并加载旧的
`instance_assets/ipc_state/manifest.json`。它们没有同步到本轮成功 oracle 的模型、接触范围与抓持辅助；
不能把页首成功直接当作这六个冻结实例的可解证明。逐包配置与哈希见
[`agent_constraints_audit_20261003.json`](../../../runs/test_results/rope_threading_goal_20261003/agent_constraints_audit_20261003.json)。

- oracle 的固定回放分支、直线归位、FCL 规划间隙、名义材料站点偏差和丢抓即停，均不是
  普通 agent 关节动作的必经检查。agent 可自行换手、绕行、恢复抓取；Task 不规定 oracle 动作顺序。
- 原生 Rope Task 的孔内余量、穿环顺序和停稳是最终成功条件；中途不满足不会立即判失败。
  该 Task 没有“触碰环架即失败”规则，原生体积／IPC 有效性失败仍终止。
- 当前 standard 的只读 `/kinematics` 默认容差为 2 mm／0.02 rad，可由请求调整，不做场景碰撞检查。
  `ee_pose` 提交接受至 2 cm／0.35 rad；失败手臂保留原关节目标并返回逐行失败信息，
  夹爪及另一手仍可能执行。不能把 oracle 的 0.1 mm／0.001 rad 精度当作该入口的限制。
- 直接使用原生 Env 的 `EE_ABS/EE_DELTA` 才会走 0.1 mm／0.001 rad 的 `solve_checked` 默认门槛。
  不可达输入以 `ValueError` 拒绝且保持 episode 可用；这条接口适合增加明确可配置的容差。
- 共享 soft grasp 的全物体最大边长比、单 tick 跟随误差解除约束、`lost` 后需先打开才能重新抓取，
  仅在启用辅助抓持后适用。现有六包没有启用它；后续对齐 oracle 时应同时提供相同辅助条件，
  再评估局部材料健康检查、短时恢复窗口与重新抓取机制。

优先统一 agent／oracle 的场景、抓持、孔径检查和停稳条件，并同步生成的任务说明；
随后再增加抓持恢复与原生 EE 容差选项。现有 HTTP EE 的 2 cm／20° 额度不建议继续整体扩大。
本节为源码与冻结配置审计，未新增 agent 物理执行证据。

以下按版本保留试验过程；“尚未成功”等阶段性结论只描述对应旧版本，最终结果以页首表格为准。

新增显式 Task 候选参数 `rope_mesh`、`rope_material`、`rope_reference_shape`、
`robot_riser_height_m`，通过 object witness → IK → runner 传递并绑定实例及资产身份。
默认值与旧任务身份保留。`rope_reference_shape=initial` 令初始 U 形成为弹性无应力形状；
不可变材料坐标仍为原直绳坐标，不改变材料跟踪、抓持站点或穿环判断。
IPC 读取独立的 `elastic_reference_coordinates`，未提供的体积资产继续使用原参考坐标。

- v1：细网格间距 5.5 mm、12 边，4,939 顶点／23,008 四面体，原细网格为
  33,070／141,247；E=5 MPa、底座升高 30 mm。物体路径通过，第一段 IK 未通过，未执行物理。
- v2：保留原底座，使用上述较粗 TetGen 网格和初始 U 形无预应力参考。easy 完整 523 点
  重新通过 IK／碰撞检查。4090 实测初始抓取误差约 0.8 mm／1.1°，在约 16 s 时原生
  `crossing_sequence` 已为 `R1−`，厚度通过、无歧义；完整接力仍在验证。
- v3：在 v2 基础上整体向左平移 50 mm；hard 对象路径通过，材料方向约束下的 R2 送绳
  IK 仍未通过，未执行物理。
- v4：显式 `structured_baseline` 网格（11 mm、8 边）及密度 65 kg/m³ 的开发候选。
  easy 原 523 点复验通过；增加辅助抓持后的完整 622 点也通过。
  粗网格、低密度、放宽求解容差或更大步长均需按各自运行报告理解，不继承默认物理资格。

`--support-regrasps --support-separation .2` 在换抓前增加另一只手的静止抓持，顺序为
辅助手抓住、原手释放并换抓、辅助手释放；10 cm 的候选支点碰到 R1，20 cm 候选通过。
`--recover-wrist-branch` 尝试保持抓取点及 TCP 姿态的小幅变化来切换腕部 IK 分支，仍检查
关节插值和碰撞；该分支恢复候选尚在验证。`--settle-seconds` 可保留最后抓持更久以等待
原生停稳，不修改成功判据。47 项 oracle 合同检查通过，不能替代原生物理成功。

后续实测已明确：v2 能完成 R1 穿环和左手接绳；无人抓持的换抓会让绳子回弹、失去 R1。
v4 两次运行在第一段推进中因原生材料跟踪误差超过 1 cm 失去抓持，暂不继续采用该网格。
v2 辅助抓持方案在约 21.24 s 保持 R1 与左手抓持，但辅助站点相对名义模型偏移 14.56 cm，
超过反馈门槛而停止。新 `--measured-keeper` 使用独立 CPU 机器人场景重选姿态，真实失败状态
下 across 45° 的接近路径通过。但 `easy_physics_measured_keeper` 实测中，右臂在接近时
把绳段推低约 25 cm，最终辅助抓持超时；静态可达不能代替动态抓取。

v10 加入显式 `rope_robot_contact=fingers`，只让四个手指链接参与机器人的 IPC 接触。
核对底层 `coup_collision_links` 后明确：过滤同时作用于 IPC 环架，并非仅对软绳；
绳／环、手指／环、机器人自碰撞及机器人／台面刚性接触保留。v14 起规划环架检查
采用相同链接集合，避免对不参与原生接触的手臂额外拒绝；台面、自碰撞、双臂和底座
检查仍覆盖整臂。原生 IPC 状态记录实际启用链接；默认 Task 仍使用全机器人接触。
`easy_physics_v10_fingers` 使用 40 ms／1 子步、v12 容差倍率 3、E=5 MPa、抓持强度 1000、
材料边长比门槛 2、跟随误差门槛 25 mm、挤压门槛 6 mm，已复现 R1 与左手接绳，继续验证换抓。
这些是显式开发条件，不能转移成功标签给默认任务。

hard v9 调整 R2 位置／朝向、R3 前移 6 cm 并换侧安装支架，保持环数量、孔径和原生有向
目标 `R1− R2+ R3+`。修复了提前把上一持绳手冻结在交接点进行全段检查的过度限制；
按接住后撤手的实际顺序检查后，通过前六段。最后一次接绳另有 IK 限制，因此缩短至
最后送入 5 cm 后保留抓持，完整 632 点通过。medium 在自身场景复验时，将间距从 5–10 mm
放宽到 0.5 mm 后，同一 632 点轨迹通过。easy 保留 6 cm 的最后送绳，精确截取完整缓存的
前四段并重新认证对象路径和机器人样本，已通过；不会用局部缓存冒充完整目标。

用户进一步授权接受轻度接触／挤压后，规划增加 `--max-penetration-mm`，显式记录 FCL
估计接触深度，原生物理仍处理真实接触。44 项 oracle、16 项 runner、16 项 calibration grasp 合同检查通过。三个变体尚无完整原生成功。
v10 easy 在辅助抓取处再次超时；诊断中双指近接与局部材料候选均满足，但重力向上的
`exposed_patch` 排除了竖直绳段的侧抓。保存状态的离线复核显示，547 个邻近材料中心
没有一个通过这项遮挡检查。新 `--allow-covered-grasp` 显式关闭该 target 的遮挡要求，
保留双指表面近接、材料归属及抓后健康检查，其他任务默认不变。
新 `--normalize-keeper` 在辅助抓稳后把下垂绳身抬回参考位置／姿态，再允许原持绳手释放；
真实状态的 87 点路径已通过静态复验，easy/hard 的 v11 从 home 实测均完成辅助抓持、
抬正和原手释放；分别在 32.84／33.32 s 因 R2 换抓站点偏差 11.09／9.50 cm 超过
8 cm policy 上限而停止，IPC 有效、仍有一手保持抓持。
`--measured-regrasps` 将同一实测规划与抓后归位用于后续接力抓取；easy 保存现场的
70 点换抓／归位路径已通过静态预检。v12 三档对象证书与 IK 复验通过；easy／medium
4090 实测分别到 40.80／41.16 s，均完成 R2 送绳手的新抓取及归位，R1 保持、IPC 有效。
随后撤手校准输入中的 NaN 材料占位符触发严格 JSON 序列化错误，两轮完整留证但未成功。
修复后撤手只传递所需姿态字段，异常原因也写入 policy tracking。
另外发现归位 TCP 相同但腕部 IK 分支不同；校准现在要求回到后续缓存分支。
保存现场分别找到 easy／medium 79 点、hard 78 点的合法分支路径（across −20°）。
显式 Task 参数 `aperture_contact_allowance_m=.001` 给保守的绳中心线穿孔判定增加
1 mm 接触／压缩余量；默认 0，上限为绳半径的一半。物理环孔、IPC 接触和有向穿越
目标不变，原生判据与规划副本共用同一计算，参数进入实例身份。
v11 保存现场还揭示厚度检查的直筒近似偏保守：easy／hard 的 R1 后侧检查平面分别
超出恒定孔径约 1.47／1.95 mm，而中心线球形膨胀模型到圆环表面仍有 0.51／0.12 mm
正余量（`v11_aperture_audit.json`；不是接触力测量或整个 FEM 表面的证书）。
新增显式 `aperture_check_profile=round_ring` 按圆环膨胀截面计算两侧孔径，中央孔径不变，
默认仍为 `cylindrical`。v13 候选采用此选项；已有运行不追溯改写配置或成功标签。
旧 hard v10 在 R1 接绳后被属主中断，避免重复运行已明确的旧遮挡检查失败；有独立中断说明。

v13 hard 连续实测到 45.28 s，原生有向序列为 `R1− R2+`，IPC 有效且左手健康持绳；
随后 R2 右手接绳规划失败，仍不是完整成功。v13 easy 走完路径并等待停稳，但只保持 R1；
实际绳端在 R2 平面附近的径向偏差约 9.7 cm，属于几何漏穿。v14 easy 将 R2 对齐到
hard 已实际穿过的姿态，保留较大孔径；完整对象路径和 367 点机器人路径重新通过。
`easy_physics_v14_aligned` 已从 home 走完 367 点，原生序列 `R1− R2+`、
厚度通过；15 秒末尾观察后仅因未达到 1 mm/s 停稳而未成功。末速约 6.42 mm/s。
离线阈值复核中，1 cm/s 条件曾连续满足约 6.68 s；不追溯改写旧运行结果。

v16 新候选显式将停稳速度改为 1 cm/s，保留 0.5 秒持续时间，三档对象证书和完整
机器人路径均重新通过。Hard 的原孔径现场接绳预检也已通过：across 45° 抓后归位
使用可达的另一腕部分支，并将后续 10 个推进目标重新求解、完整检查，保持原 TCP
路径。`hard_receiver_continuation_preflight_v16/result.json` 保存 68 个抓取／归位路点
与 10 个后续关节替换；只属静态校准，不是完整物理成功。此前增加 R2 内半径 8 mm
未解决腕部分支问题，v16 不采用该尺寸变化。新增单环孔径接口仍可用于后续建模。
53 项 oracle、16 项 runner 合同检查通过。`hard_physics_v16_continuation` 和
`easy_physics_v16_quiet` 已取得页首所列完整原生成功。Medium 的 v14 实测也完成 `R1− R2+`，
在 44.20 s 的右手接绳规划中停止；其接近关节弦碰到 R2，估计挤压 5.2 mm。v17 增加
肩／肘短绕行，保存现场的 69 点抓取／归位与 10 点后续推进已通过，允许挤压实际使用值为 0。
`medium_physics_v17_detour` 已从 home 完整成功，真实 R2 接绳、分支续接及第三环推进均通过。Hard 在新 A 腕部分支下，
第三环的名义绳形接绳及撤手预检通过后，真实第三环抓取与完整原生成功也已通过。

旧 `medium_ik_v9_held/prefix_01.npz` 因失败复验导出范围错误不可执行，修正记录在该目录
`validation_correction.json`；当前实现只导出实际检查通过的前缀，失败样本和未检查尾部均排除。

## 接力 oracle 的连续性修复与实测（2026-10-03）

当前执行器使用 JOINT_ABS 回放规划分支，抓取接近采用规划关节作种子的实测站点反馈。
已接入 `--tooling-ipc`：v12 rope 的单子步、Newton/PCG 1e-3/1e-5、linear_bvh。
75° Harbor 包的冻结静置态不适用于当前 0° 场景。属主证据用共享 history reference 模式去重，
策略仍明确声明 world 权限。calibration adapter 记录材料站点、关节跟踪和抓持拒绝原因。

发现并修复了 IK 分支搜索用整机 home 作为种子的问题：原 medium/hard 的 R3 pinch
会使另一只持绳手跳变超过 2.4 rad。轨迹加载器现在拒绝非运动手跳变。
hard 重算通过 546 点；medium 的 20 cm 换抓配方在真实保留送绳手后无法撤手，
窄开度尝试也未通过，现改用 24 cm 配方，重新检查目标场景的 546 点后通过。
easy 原 452 点未出现该跳变。三者仍只有采样运动学资格。

RTX 4090 的两次 easy 实测保存在
`runs/test_results/rope_threading_relay_continuation_20261003/`：

- `easy_attempt01`：5 ms／1 子步，5.58 s 获得原生辅助抓持；6.175 s 因边长比
  1.300079 超过辅助抓持门槛 1.3 而失去抓持。原生绳体有效性未失败。
- `easy_attempt02`：10 ms／1 子步，辅助抓持门槛显式放宽为 2.0，持绳速度 0.04 m/s。
  连续执行至 25.59 s／2559 tick，进入首次左手接绳时 IK 分支偏差 0.280 rad 而停止。
  更早的实测已表明接绳材料站点偏离计划约 0.137 m，R1 穿越序列仍为空；
  根因包含自由绳端下垂及抓持材料方向与几何路径不一致，不能仅靠放宽 IK 门槛解决。

两次执行均有完整逐 tick 证据，明确关闭 RGB，没有新增正式 demo。
第二次的 10 ms 时序使 Genesis 自动把约束时间常数从 10 ms 调为 20 ms，
这是显式开发条件，不属于默认时序验收。三档均尚无完整原生 task_success。
默认任务材料和成功检查未改动。后续实验加入了以下能力与证据：

- 材料方向规划：`--material-tangent`、离桌后逐渐对齐、有限轴倾角，以及仅约束长自由绳端。
  严格约束所有接力阶段的若干候选仍不可达；`easy_ik_material_pushers` 用短拉绳配方
  `A10_B_pull12_B10_recvA` 得到新的完整 523 点 IK。它只约束两个送绳阶段，接绳端仅露出
  1–2 cm，仍保留姿态自由度。审计中 R2 送绳的材料轴误差约 5°；这不是物理通过。
- 局部探针：`--max-holds` 明确导出 `robot_ik_prefix_verified`，执行需要 `--allow-prefix`。
  曾遗漏局部标签的原始产物已另存，修正说明及前后哈希保存在 `easy_ik_first_handoff_probe`。
- 建场材料实验通过 calibration tools 将 E 从 50 kPa 提高到 5 MPa，报告保留完整候选差异。
  `easy_material_probe01` 在 3.69 s 因反馈关节偏差超过 0.25 rad 停止；硬绳初始展开使
  抓取站点偏移约 5.6 cm。`easy_material_probe02` 放宽到 0.6 rad，并显式使用 v12 容差的
  3 倍值，约 5.5 s 成功抓取。实测抓取材料轴与规划相差约 26°，仅位置反馈无法消除。
  该探针最终连续执行 22.14 s／2214 tick，完成第一段计划与保持，抓持未丢失，但 R1
  穿越序列仍为空；终点绳尖偏差约 10 cm，状态为 `not_passed`。
- 新增 `--material-feedback`，绕真实材料站点修正接近方向，保持指垫偏置；超过 0.8 rad
  拒绝执行，随后在最初 10 cm 的持绳段平滑回到计划姿态。新轨迹附带材料切线，旧轨迹
  需重新生成或逐点复验后导出。calibration adapter 同时记录实测材料轴在 TCP 坐标系中的方向。
  `easy_material_probe03` 在 3.69 s 因反馈关节偏差 0.805 rad 超过本次 0.6 rad 门槛停止，
  尚未抓取。随后用该 tick 的真实绳形进行静态复验：完整方向修正出现
  `shoulder_link / gripper_base` 自碰撞；0、0.25、0.5、0.75、1 五种方向反馈比例
  均没有整段无碰撞的接近路径（部分还碰到 base／finger）。因此没有继续增大门槛跑物理。
- hard 首选配方的长绳端方向约束在 R2 送绳未通过，记录为 `hard_ik_material_pushers`。
  medium/hard 当前仍以先前 546 点名义轨迹为采样运动学证据，不能继承 easy 的材料方案。

后续物理缺口是：按真实绳形重新选择抓取分支／初态布局、控制自由绳端的形状，及用持续托持
替代模型中的无人抓持换抓。现有 native 运行没有解决这些问题，不能宣称完整 oracle 已通过。
当前相关回归为 32 项 oracle 检查、16 项 runner 检查通过。

逐项状态、轨迹路径、源码哈希和回归结果见
[本轮报告](../../../runs/test_results/rope_threading_relay_continuation_20261003/continuation_report.json)。
旧 `easy_ik_material_tilt15` 虽通过几何／IK，但审计发现部分材料轴曾偏离 27°；不能按
15° 方向约束使用。后续已修正对齐窗口，并独立重新规划，不覆盖旧快照和证据。

## easy / medium / hard 的首次 Wang oracle 整合（2026-10-03）

已按提供的 Wang 源码接入三档物体路径、接力 IK 和 `JOINT_ABS` 回放策略。
算法位于 `topogym/planning/rope_threading/`；执行入口与其他 oracle 一致，位于
`scripts/oracle_runners/run_rope_threading_relay.py`。只读规划入口按既有约定放在
`scripts/plan_rope_threading_oracle.py` 和 `scripts/plan_rope_threading_ik.py`。
完整三步命令见 [oracle README](../../../topogym/planning/rope_threading/README.md)。

本轮没有修改 Task、场景资产、home、0° 布设、材料或公共物理参数。
三档均采用 `A=right / B=left` 和 10 mm 的 hold 采样间隔：

| 变体 | 已接入默认方案 | 当前仓库 seed 0 复验 |
| --- | --- | --- |
| easy | `A10_B_pull19_B20_recvA` | 物体路径通过；双臂 IK 452 个采样点通过 |
| medium | `A10_B_pull19_B20_keep_recvA6` | 物体路径通过；双臂 IK 466 个采样点通过 |
| hard | `A10_B_pull19_B24_keep_recvA5` | 物体路径通过；双臂 IK 500 个采样点通过 |

三次 IK 均首选方案通过，包含从 home 接近、抓持姿态、接力及末端释放／撤回的运动学检查，
但不推进任务 FEM/IPC。当前实体垫座也纳入碰撞检查，固定机器人底座与垫座的接合面除外。
18 项 oracle 接入回归、6 项五档场景回归和 4 个 CLI 帮助入口通过。
证据、源码哈希、输入和资源记录见
[整合验证报告](../../../runs/test_results/rope_threading_wang_integration_20261003/integration_report.json)。
medium/hard 首次本地复跑因磁盘写满退出，失败日志完整保留；空间恢复后两档重跑均通过。
easy 的快照早于 CLI 异常报告重构和 profile 文档调整，核心 IK／碰撞代码与最终版本一致；
报告列出了精确源码差异，不把所有 run 视作同一快照。

执行器默认使用当前 simulator 的 2.5 ms tick、4 子步、10 倍控制降采样、CUDA FEM/IPC，
从标准 home 开始，经共享 `SegmentRunner` 和 Nyx 四视角录制；可显式 `--no-rgb`。
采用附件的 `ipc_soft_band_v1`，等待接触触发的 native 抓持实际求解成功，并检测抓持丢失。
轨迹记录变体、seed、实例、资产、robot mount 与 home 身份，执行前逐项核对；旧无身份 NPZ 需重建。
`policy_done` 不能替代原生 Task success，成功还要求终止和完整逐 tick 证据，允许仍保持抓持。

**完整物理执行未验收**：附件也注明三档物理作业均取消，已验证部分为 IK。
几何模型假设绳沿轨道滑动，未抓持换抓阶段假设形状保持；关节插值及实测反馈不会继承
离散 IK 样本的关节分支或连续碰撞证明。本轮未新增实际机器人成功或正式演示视频。
现有 very_easy/easier 使用独立 `ThreadingPolicy` 和原 `run_rope_threading_policy.py`，保持原验证范围。

## 0° 布局与两档简化任务（2026-10-02）

按本轮场景确认要求，五档统一采用 Wang 参考的 0° 布设：
`translation_m=[-0.1356786, 0, 0.0009]`、`yaw_deg=0`。
ALOHA 底座抬高 20.9 mm，并在两臂原底座轴线下增加 70 × 70 × 20.9 mm 实体垫座；
保留统一 ALOHA 默认 home（含手指位置），机器人、夹爪和绳均不缩放。
垫高配置仅作用于 Rope Threading 的 ALOHA 场景，在机器人资产选择和 IPC 初始化前生效。

| 入口 | 本轮场景 | 目标与状态 |
|---|---|---|
| `rope_threading_very_easy` | 单个 R1 的下半圆，上方整个半圈移除，管端封闭，保留原侧支柱与底座 | 搭绳判据已启用；完整机器人解法待验收 |
| `rope_threading_easier` | 单个完整 R1，净孔径 138 mm | 单环穿越、双手换绳历史及终态判据已启用；完整机器人解法待验收 |
| `rope_threading_easy` | 原 R1、R2 双环，净孔径 138 mm | 保留原判据，更新 0° 摆位与模型版本 |
| `rope_threading_medium` / `base` | 原 R1、R2、R3 三环，净孔径 138 mm | 保留原判据，更新 0° 摆位与模型版本 |
| `rope_threading_hard` | 原三环，净孔径 100 mm | 保留原判据，更新 0° 摆位与模型版本 |

沿用包内 `rope_threading/reference.json`，无新增外部资源依赖。五档共用约 1.1 m 长、
8 mm 直径、双端自由的 U 形绳，以及原 FEM 材料、体网格配方和 IPC 参数。
绳两端 XY 为 `(-0.50600535, 0.05)`、`(0.1943214, 0.05)` m；
R1/R2/R3 法线水平角为 0°/36.8699°/71.5651°，R3 仰角 18.4349°。
R1 中心距桌面 331.9 mm、中心线半径 75 mm、环管直径 12 mm；very-easy 仅删除上半圈，
既不降低高度，也不放大开口。旧三档本轮均更新模型版本，不沿用旧 75° 场景的实例身份。

两档新入口现在均为 `goal_complete=True`，分别使用 `rope_drape_v1` 和
`rope_single_ring_handoff_v1`。可通过统一 `topogym.make()`、`Env`、交互句柄和
`SegmentRunner` 执行、评分、保存和回溯。任务注册状态为 integrated，验证状态为
`terminal_implemented_pending_robot_qualification`；启用评分不表示已有成功机器人演示。
`seeded` 仍只在原 easy/medium/hard 间选择。此轮交付 simulator 任务定义，未生成新的 Harbor 包。

### 成功条件

- **very-easy**：绳身跨过半圆所在平面，搭在下方中央弧段内侧（跨越点至少低于环中心半个中心线半径）。
  名义绳面到支承弧的间隙不超过 1 mm、重叠不超过 0.5 mm；跨越点沿绳的两侧各至少保留 25 mm，
  两侧沿材料距离 20 mm 的点必须处于环平面的相反侧，并越过环管与绳半径合计的厚度。
  悬空、只碰切口、仅绳尖触碰或与环相切不算搭上。
- **easier**：沿原绳材料方向恰有一次 `R1−` 穿越，绳全厚度通过中心面和前后两侧厚度面。
  送绳手先在入口侧抓住某一端的 120 mm 材料区；穿过后，接绳手在出口侧抓同一端区，
  两手有同时抓持的重叠阶段，再由送绳手放开。每次抓持至少持续 20 ms；入口／出口抓持中心
  须分别离开环平面至少 12 mm。单手穿环、第二只手无关触碰、先放开再接住均不计换手。
  抓持证据使用健康的原生接触触发 FEM 辅助抓持，或同一端区与两块实际指面同时近接触（0.3 mm）。
  不使用 TCP 距离或夹爪指令冒充接触。退出环孔、反向穿越或原生完整性证据缺失会取消换手信用。
- 两档都检查整条 FEM 绳的原生有效性及正体积；整绳最大速度不超过 1 mm/s，并持续满足目标 0.5 s。
  允许继续抓持，不额外要求释放或放回桌面。绳体失效立即终止失败；缺少完整性证据时不能成功。
  easier 的送绳／接绳历史与稳定窗口随正式 Task checkpoint 保存和回溯，旧未来不会保留信用。

```python
from topogym.simulator import Env, SimulatorConfig
from topogym.tasks.rope_threading.simplified import recommended_grasp_assist

config = SimulatorConfig(
    task_id="rope_threading", variation_id="easier", compute_backend="cuda",
    grasp_assist=recommended_grasp_assist("easier"),  # 可选，必须显式启用
)
with Env(config) as env:
    observation, info = env.reset(seed=0)
    # 后续由交互句柄或 SegmentRunner 提交真实机器人动作。
```

离线检查入口：

```bash
.venv-gs121-nyx/bin/python ci_checks/test-rope-threading-scenes.py
.venv-gs121-nyx/bin/python ci_checks/test-rope-threading-terminal.py
```

模拟器截图与逐场景配置、资产哈希、机器人实测初态、相机参数、资源记录存放于
`runs/test_results/rope_threading_scenes_20261002/`。
截图使用 Genesis + Nyx + compact_lab，在 reset 后、物理步 0 拍摄；`cam_*.png` 是标准观测，
`overview.png` / `detail.png` 是同一初态的展示视角。它们不证明接近、抓取、双手换绳或完整可解性。
首轮正常建场在引擎的动力学预热阶段出现 `Newton Iteration Exits with Max Iteration: 1024`，
452 秒后主动停止，日志保留于 `very_easy_warmup_attempt01/`。本轮静态截图仅在独立预览进程中
跳过 `Scene.build()` 内随后会被 reset 丢弃的那一个预热步；仍使用相同的 FEM/IPC 资产、
原生建场和 Nyx 渲染，没有修改当时的公共引擎或任务物理参数。这批旧图片仅用于确认场景几何和摆位，
后续物理验收不使用跳过预热的方式。

本轮 7 项离线检查通过，五档各保存 6 张截图；逐数组核对确认五档 FEM 绳的参考态、
初态、四面体、材料坐标和中心线完全一致，实测双臂 home 一致。
详见[截图与验证清单](../../../runs/test_results/rope_threading_scenes_20261002/preview_manifest.json)。

- [very-easy 全景](../../../runs/test_results/rope_threading_scenes_20261002/very_easy/overview.png) · [半圆近景](../../../runs/test_results/rope_threading_scenes_20261002/very_easy/detail.png)
- [easier 全景](../../../runs/test_results/rope_threading_scenes_20261002/easier/overview.png) · [单环近景](../../../runs/test_results/rope_threading_scenes_20261002/easier/detail.png)
- [easy](../../../runs/test_results/rope_threading_scenes_20261002/easy/overview.png) · [medium](../../../runs/test_results/rope_threading_scenes_20261002/medium/overview.png) · [hard](../../../runs/test_results/rope_threading_scenes_20261002/hard/overview.png)

### 初始化修复与执行入口

正常初始化已修复：Genesis 为 IPC 创建的碰撞几何采用 home 姿态，但其 Python 关节参考初始为零，
预热首步因此把整个 home 角度作为增量。`topogym/world/physics/ipc.py` 现在在 native build 后、
预热前同步关节参考，复用 reset 的同一同步逻辑，不改变绳材料、碰撞模型或求解容差。
在原 Newton 容差 `1e-4`、物理步长 2.5 ms、4 子步下，easier 正常预热并完成 4 个空闲物理步；
末步 native frame 16，最小体积比约 0.99087、最大体积比约 1.00986。
该诊断显式使用线性系统容差 `1e-5` 与 `linear_bvh`，只证明初始化和短程推进，不证明穿环成功。
证据见[初始化复测报告](../../../runs/test_results/rope_threading_development_20261002/init_reference_fix_attempt03/report.json)。

`scripts/oracle_runners/run_rope_threading_policy.py` 提供从标准 home 开始的开发控制器，
复用原生 IK/FK、实际机器人碰撞网格和非凸环网格进行采样预检，再通过普通关节动作执行。
FEM 辅助抓持只有双指实际接触后才建立，禁止写物体姿态、直接注入抓持或替换绳物理。
录制、动作记录、状态证据和回溯均由共享 `SegmentRunner` 管理，RGB 使用 Nyx + compact_lab。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_rope_threading_policy.py \
  --variant very_easy --part pickup \
  --output runs/test_results/rope_threading_pickup_new
# --variant easier 选择单环；--part solve 执行完整候选动作。
# 默认物理时间步 0.0025 s、4 子步；更改时序仅作为显式记录的开发试验。
```

该控制器仍是开发候选，`run_report.json` 分开记录 `pickup_passed`、原生 `task_success` 和
`qualification`，不能以进程退出码、路径预检、局部抓取或合成状态测试宣称完整 oracle 成功。
源代码快照、失败尝试、资源监控和视频保留在
`runs/test_results/rope_threading_development_20261002/`；只有系统内存达到 90% 才因资源使用停止本轮进程。

当前验证范围：6 项场景／公开目标检查、12 项终态／接触／回溯检查通过；原三档目标描述及
IPC 诊断的相关回归也通过。`very_easy_pickup_attempt02` 从默认 home 连续执行 547 步／5.47 s，
原生完整性在全部 548 条含初态的记录中有效，没有误报成功。最后下降姿态因张开的手指与右臂底座
发生预测自碰撞而被预检拒绝，尚未抓取；这是开发失败尝试。它使用显式 10 ms／1 子步，
Genesis 相应把约束时间常数从 10 ms 调为 20 ms，不属于默认物理资格。
后续只读全路径预检确认：距材料末端 65 mm 的两种夹爪朝向均碰底座，改为距末端 85 mm 后通过。
这项修正仅改变抓取策略，保留所有场景、机器人和绳尺寸。

- [接近阶段四路视频记录与结果](../../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt02/run_report.json)
- [俯视视频：home → 抓绳前，未成功抓取](../../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt02/segments/segment_1/videos/cam_high.mp4)
- [连续物理记录审计](../../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt02/execution_audit.json)
- [85 mm 抓取候选与 easier 正常初始化报告](../../../runs/test_results/rope_threading_development_20261002/pickup_preflight_attempt03/report.json)

`very_easy_pickup_attempt04` 已在不改变场景的情况下从 home 到达 85 mm 抓取点。
第 506 步获得真实双指接触（指面间隙约 0.019／0.015 mm），注册了 632 个顶点的 FEM 抓持区；
第 507 步继续收紧夹爪时出现局部负体积，抓持健康检查报 `inverted_material`，Task 报
`rope_volume_invalid` 并终止。这次仍使用 10 ms／1 子步，不能据此声称默认时序夹取失败或任务已解。
控制器已改为逐小步收紧，并在双指接触进入 qualifying／registered 时保持当前闭合目标；
默认时序的局部诊断与从 home 的完整复验分别记录，局部预抓取初态不计为完整机器人流程。

- [双指夹取后失效的简要证据](../../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt04/grasp_summary.json)
- [实际接近与闭合视频（失败尝试）](../../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt04/segments/segment_1/videos/cam_high.mp4)

默认时序局部诊断 `grasp_default_timing_attempt06` 使用明确标注的预抓取机器人初态，未改正式任务的
home、绳或环。完全张开的初态通过检查，完成 144 步／0.36 s，已保存步的原生状态全部有效、
最小体积比约 0.9821；在 600 秒墙钟预算到期时尚未建立双指抓持，按超时结束。
因此“小步收紧后能稳定夹取／抬起”的修正还没有获得物理通过证据；完整搭绳、双手穿环及
默认时序的完整机器人演示均仍待验收。
见[局部诊断报告](../../../runs/test_results/rope_threading_development_20261002/grasp_default_timing_attempt06/report.json)、
[超时退出记录](../../../runs/test_results/rope_threading_development_20261002/grasp_default_timing_attempt06/process_result.json)和
[最终代码检查清单](../../../runs/test_results/rope_threading_development_20261002/implementation_checks.json)。

以下是历史记录，其中 75° 摆位、旧入口和旧验证结论不代表本轮更新后的场景。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

## 历史三档场景（2026-09-29，75° 布局）

三档均已接入统一 `topogym.make("rope_threading", variation_id=...)`，本轮先完成场景布设。
`base` 继续选择 medium，原 medium 的配置、实例身份、三环几何和绳初态保持一致。

| 档位 | 目标环／材料顺序 | 净孔径 | 场景差异 |
|---|---|---|---|
| easy／`two_rings` | R1− → R2+ | 138 mm | 保留青、绿两环，移除紫环 R3 及其支架、底座 |
| medium／`wang_reference_v1` | R1− → R2+ → R3+ | 138 mm | 沿用原三环参考与默认实验室放置 |
| hard／`three_tight_rings` | R1− → R2+ → R3+ | 100 mm | 三环中心、法向、顺序和 12 mm 环管外径不变，支架与底座沿径向内移 19 mm，保持与环连接 |

三档共用 1.1 m 长、8 mm 直径的绳及完整 U 形初态；材料、FEM 网格和 IPC 接触参数不变。
绳两端自由，初始穿越为空；任务整体沿用 `translation_m=[-0.1156786, 0.03, 0.0015]`、`yaw_deg=75`，
由统一场景放置到实验桌。easy/hard 的环选择及内半径不能通过参数覆盖悄悄变成另一档。
100 mm 是本轮冻结的场景候选尺寸，难度递增、连续机器人可达与完整解法仍待验证。

资产重复构建、封闭通孔、支架连接、绳初态间隙和 FEM 正体积已检查；
[资产检查报告](../../../runs/test_results/rope_threading_scenes_20260929/assets/report.json)与
[Medium 一致性记录](../../../runs/test_results/rope_threading_scenes_20260929/medium_regression.json)保留具体证据。
[三档几何对照图](../../../runs/test_results/rope_threading_scenes_20260929/scene_geometry.png)直接绘制本轮导出的模型，不包含机器人或动力学。
31 项相关检查通过；Nyx 首轮建场因并行任务占用显存而在 CUDA 分配阶段中止，
[首次运行报告](../../../runs/test_results/rope_threading_scenes_20260929/preview.md)和
[限时等待显存后的重试](../../../runs/test_results/rope_threading_scenes_20260929/preview_retry.md)分别保留，
不能把静态图当成 Nyx／物理通过证据。完整交付索引见[场景验收记录](../../../runs/test_results/rope_threading_scenes_20260929/README.md)。
新场景不继承历史三环的解法或物理资格，`goal_complete=False`。

复现三档场景验收（使用新的输出目录）：

```bash
.venv-gs121-nyx/bin/python scripts/record_initial_scenes.py \
  --variations rope_threading_easy rope_threading_medium rope_threading_hard \
  --seconds 0.5 --timeout 1800 --min-free-gpu-mib 14000 \
  --output runs/test_results/rope_threading_scenes_repeat \
  --index runs/test_results/rope_threading_scenes_repeat/preview.md
```

## 原三环参考与历史执行记录

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
详见[新 IK 动作、门控与验收边界](../../../legacy/cleanup_20260929/docs/develop/tasks/rope_threading_feedback_ik_zh.md)。
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
保存三路展示视角、ALOHA 四路相机初态、静置前后状态、
解析后的配置、世界坐标资产及 JSON 报告。预览入口只输出静态图，不再生成环绕视频，
不能当作机器人执行；`run.settle_steps=0` 仅建场，
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
生成该视频的诊断脚本已随录制代码收敛移除；保留的 `manifest.json` 记录源轨迹哈希、时间映射和解码核对。
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
  --config-name rope_threading_soft_start_preview
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

新方案已接入完整执行器，详见 [反馈 IK 说明](../../../legacy/cleanup_20260929/docs/develop/tasks/rope_threading_feedback_ik_zh.md)。
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


### 接绳继续验证与录制尝试 5

已补充第二环的表面接触扫描和 [7 秒接绳近景预演](../../../runs/environment-solvability/rope_threading/grasp_geometry_20260921/conditional_grasp_v2_closeup.mp4)：
预测绳尾下，手指关节开度 11.9–12.5 mm 存在双侧接触且不相交的几何候选；这不是实际抓持结果。
控制器仍要求转动后重新观测，原生双指接触后才启用辅助抓持，接稳后才释放另一手。

发现并修复了新机器人网格检查与物理库同进程加载的 pybind 枚举冲突，改为独立 CPU 子进程。
50 项相关控制与证据检查通过，其中包含真实库加载顺序集成测试。
尝试 4 因此在启动前取消；当前尝试 5 已自动排队，显存足够后从初态连续执行。

增加 CPU 摄像渲染选项并修复 Genesis 1.2.1 OSMesa 的 FBO 能力声明问题：
先实际验证 FBO，再使用已有按相机尺寸的渲染回读，独立场景已获得正确 320×240 图像。
原物理配置和网格未降级。启动探针曾完成 0.05 s / 40 个收敛子步，但未录出成功物理视频。
后续原生 CUDA 设备错误前追踪到显存分配失败；当前约 7.8 GB 空闲不足，另有多项任务使用 GPU。
最新状态见 [当前录制入口](../../../runs/environment-solvability/rope_threading/current_recording.json)，完整 demo 仍未完成。
