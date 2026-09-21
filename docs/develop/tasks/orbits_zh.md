# 第 13 项：Orbits 四环阶梯解绳

任务 ID：`orbits`，版本 `video_reconstruction_v1`。按用户指定的
[SiamMandalay 视频](https://www.youtube.com/watch?v=B-EB9Q-JqXA)重建整套器具及约第 10 秒的受困初态。
该视频标题是 Orbits，实际为 **四环、五杆**；“九连环”是用户对连环解绳类的称呼，未据此擅自增加五只环。
视频为厂商的解法渲染演示，不能作为本项目物理求解通过的证据。

2026-09-21 开发状态：完整解绳尚未通过。最新局部运行 `robot_natural_loop_14`
修正了木柄附近的内凹绳圈，并完成双臂撑圈越过顶球；四路实测状态录像已核对。
后续穿环、换抓和最终解脱仍未完成。

## 初始场景

长方形木底座上有五根依次降低的竖杆。四只水平木环分别固定在下一根杆的顶端，
前一根较高的杆穿过其内部；最高杆顶部是一颗木球。
环心与被包围支杆有小偏移，保证低环的另一端不会撞入更早的高杆。
黄色绳的 U 形弯头位于最低环下方，只绕末端第五杆；两条绳腿延伸到一个木质拉柄。

原始几何基准（`scale=1`）的底座 470 × 180 × 24 mm，杆距 82 mm，环中心线半径 66 mm、管半径 8 mm；
四环离桌高度分别为 330 / 262 / 194 / 126 mm，顶球半径 24 mm，绳半径 2.2 mm。
这些是按画面比例制定的机器人桌面尺度，**不是视频实测尺寸**。
木柄内部接绳方式不可见，当前以两个真实小孔和插入孔内的绳端表示；这是显式建模假设。
绳尾长度和桌面排列做了适配，未声称逐像素复制视频。

共用环境为 Nyx / `compact_lab` / ALOHA 双臂，机器人停在 home。
本次完成范围是整套器具、穿套关系、可重载资产与静态场景初始化。
所有任务对象固定、碰撞关闭，录像仅相机运动，`simulation_steps=0`。
该静态初态未经过重力静置。另行开发的动力学与抓持探针见下文；完整解绳尚未通过。

## 双臂居中摆放 v2（2026-09-20）

按用户要求，将整套器具绕世界竖直轴旋转 **90°**，移到两臂之间。
木座、四环五杆、顶球、黄绳和木柄使用同一个刚性变换；各件内部几何与绳初态保持一致。
v2 采用 `origin_xy_m=[-0.1356786, -0.133]`、`yaw_deg=90`。
整套器具（含木柄）的平面包围盒中心为 `[-0.1356786, -0.019] m`，
与 ALOHA 两个基座的中点重合；距桌边的最小余量为 **332 mm**。
四环排布方向与两臂基座连线垂直，两臂可从器具两侧操作。

使用与场景相同的 ALOHA 模型和关节限位，检查 11 个接近位置：
每只环的左右外侧各一个，另有顶球上方、绳套上方和木柄上方。
**22 个单臂接近姿态均通过 IK、机器人自身、器具和桌面碰撞检查**，最大位置误差约 **0.081 mm**；
四组环两侧的双臂同时接近姿态也通过检查，机器人 home 初态无新增相交。
部分跨侧目标需要约 45° 绕侧、30° 下倾的夹爪姿态，直接跨环伸入会碰木件。

该结果仅验证有限个接近姿态：另一臂在 home，另行检查四组同时接近姿态。
夹爪沿用 home 的 8.4 mm 指轨位移。没有验证连续轨迹、全工作空间体积、
实际抓绳、夹持木柄或解法执行，不能据此声称完整双臂解绳已经可用。
[详细可达性报告](../../../runs/demo_metadata/orbits/2026-09-20_static_bimanual_v2/workspace_report.json)
保存全部目标位置、关节角、误差、模型哈希和验证范围。

保留的 v2 三视角初态（各 8 秒、120 帧、15 fps）：

- 双臂与居中器具全景（旧产物已清理：`2026-09-20_static_bimanual_v2_overview.mp4`）
- 旋转后斜前近景（旧产物已清理：`2026-09-20_static_bimanual_v2_front_oblique.mp4`）
- 俯视：两臂之间的完整占地（旧产物已清理：`2026-09-20_static_bimanual_v2_topdown.mp4`）

[v2 配置、检查及归档清单](../../../runs/demo_metadata/orbits/2026-09-20_static_bimanual_v2/README.md)。

## 玩具尺度 v3（2026-09-20，保留的 35% 版本）

按用户要求，整套器具等比缩至原来的 **35%**，保持原尺寸机械臂、夹爪和桌面。
厂商[Orbits 产品说明](https://www.siammandalay.com/product/orbits/)列出的尺寸为
6 × 2.25 × 5.5 英寸，约 152.4 × 57.15 × 139.7 mm。
同页附加信息又将相同数字标成 cm，存在单位不一致；这里采用正文的英寸标注作为近似参照，
不声称已实测玩具或人手尺寸。缩小后的模型与厂商标注尺度接近。

| 尺寸 | v3：35% 版本 |
| --- | --- |
| 底座长 × 宽 × 厚 | 164.5 × 63 × 8.4 mm |
| 整套最高点 | 142.45 mm |
| 环外径 / 内径 | 51.8 / 40.6 mm |
| 杆间距 | 28.7 mm |
| 绳直径 | 1.54 mm |
| 木柄长 × 宽 | 23.1 × 12.95 mm |

`task.scale=0.35` 统一缩放木座、环、杆、顶球、绳、孔、木柄及内部连接间隙。
`task.geometry` 保留原始基准参数；生成的 `assets/layout.json` 记录实际米制尺寸和模板缩放系数。
几何缩放在资产生成时完成，Genesis 场景和离线碰撞审计使用同一批实际尺寸。
生成器的绳肘部、孔位和固定连接偏移也随比例缩放，避免只缩主体留下错位的绳和孔。

新原点为 `[-0.1356786, -0.0589] m`、朝向仍为 90°；整套包围盒中心仍精确位于
两臂基座中点 `[-0.1356786, -0.019] m`，最小桌边余量 558.85 mm。
环外侧和顶部接近目标保留夹爪所需的毫米级工具间隙，不随器具一起缩小。
已重新通过 14 项几何检查、13 项回归、22 个单臂接近姿态和四组双臂同时接近姿态检查。
这仍是有限姿态的 IK / 静态碰撞证据，不代表小尺寸绳已能物理抓取或完成解法。

保留的 v3 三视角初态（各 8 秒、120 帧、15 fps；全景与俯视沿用 v2 相机便于比较尺寸）：

- 全景：器具与双臂比例（旧产物已清理：`2026-09-20_static_toy_scale_v3_overview.mp4`）
- 拉近的斜前细节（旧产物已清理：`2026-09-20_static_toy_scale_v3_front_oblique.mp4`）
- 俯视：玩具尺寸与夹爪比例（旧产物已清理：`2026-09-20_static_toy_scale_v3_topdown.mp4`）

[v3 报告与资产归档](../../../runs/demo_metadata/orbits/2026-09-20_static_toy_scale_v3/README.md)。
v1、v2 保留，可直接比较实际几何缩放；新预览不替代完整机器人 demo。

## 75% 尺度 v4（2026-09-20，保留的原摆放）

按用户要求，改为**原始几何基准的 75%**（`task.scale=0.75`），
是 v3 线性尺寸的约 2.14 倍。底座为 **352.5 × 135 × 18 mm**，
总高 **305.25 mm**，环外径 / 内径 **111 / 87 mm**，绳直径 **3.3 mm**。
整套器具等比缩放，机械臂与夹爪保持原尺寸。

朝向仍为 90°，原点更新为 `[-0.1356786, -0.1045] m`；含木柄的完整包围盒中心
保持在两臂基座中点 `[-0.1356786, -0.019] m`，最小桌边余量为 **419.25 mm**。
重新通过几何检查、13 项回归、22 个单臂接近姿态和四组双臂同时接近姿态检查。
这仍是静态初态和有限接近姿态验证，没有执行连续运动、实际抓绳或完整解法。

v4 三视角各 8 秒、120 帧、15 fps；三台相机采用 v2 的配置，便于与原尺寸直接比较：

- 全景：75% 器具与双臂比例（旧产物已清理：`2026-09-20_static_scale75_v4_overview.mp4`）
- 75% 斜前近景（旧产物已清理：`2026-09-20_static_scale75_v4_front_oblique.mp4`）
- 75% 俯视（旧产物已清理：`2026-09-20_static_scale75_v4_topdown.mp4`）

[v4 检查、配置和独立资产](../../../runs/demo_metadata/orbits/2026-09-20_static_scale75_v4/README.md)。
原尺寸及 35% 视频继续保留。

## 木底座双轴居中 v5（2026-09-20，当前默认）

按用户要求微调位置，以**木底座的横纵中心线交点**对齐两臂基座中点。
相对 v4，整套器具沿世界 Y 正方向平移 **85.5 mm**，新原点为
`[-0.1356786, -0.019] m`。75% 尺度、90° 朝向、内部几何及相机配置沿用 v4。
木底座长轴与两臂连线垂直，短轴与其平行；底座中心到两臂基座的平面距离相等。
木柄和绳尾仍向一端伸出，因此含木柄的完整包围盒中心不再作为对齐基准。

22 个单臂接近姿态、四组双臂同时接近姿态重新通过 IK、关节限位和静态碰撞检查，
并重载关节状态复核。底座中心与两臂基座中点的 XY 偏差为零，最小桌边余量 **371.75 mm**。
几何检查与 13 项回归通过；三路视频完整解码通过，各 8 秒、120 帧、15 fps。
范围仍为静态初态和有限接近姿态验证，尚未执行连续运动、物理抓持或解法。

- [俯视：底座两条中心线对齐双臂](../../../demos/orbits/varaition_base_centered/topdown/2026-09-20_static_base_centered_v5_topdown.mp4)
- [全景：居中后的双臂与器具](../../../demos/orbits/varaition_base_centered/overview/2026-09-20_static_base_centered_v5_overview.mp4)
- [斜前近景](../../../demos/orbits/varaition_base_centered/front_oblique/2026-09-20_static_base_centered_v5_front_oblique.mp4)

[v5 配置、可达性和归档证据](../../../runs/demo_metadata/orbits/2026-09-20_static_base_centered_v5/README.md)。
v1 至 v4 均保留，便于对照尺寸和位置变化。

## 双臂解法开发（2026-09-21，未完成）

已找到厂商的[完整图解](https://ecommerce-static.s3.amazonaws.com/siammandalay/solutions/orbits_solution_printable.pdf)，
以及[四环梯二进制状态演示](https://www.youtube.com/watch?v=ZryDkIDJxLQ)、
[三环梯实物单手操作演示](https://www.youtube.com/watch?v=1bKKljbpd5E)。
厂商图解前三页包含 46 个拆解小步骤；四环梯演示提供了 15 次状态切换的对应顺序。
[状态序列及来源哈希](../../../assets/tasks/orbits/video_reconstruction_v1/solution_reference.json)已整理，
抓点、翻套方向及机器人连续路径仍在物理验证中。符号状态不是实测绕数或环盘穿越次数。

`dynamics.py` 提供 MuJoCo 原生一维 flex 绳、重力、自接触、真实环孔和闭合绳端连接。
`robot_dynamics.py` 接入原尺寸 ALOHA 关节、碰撞体和执行器；`robot_runtime.py` 在双侧手指
接触目标绳段或木柄后才允许启用辅助抓持，并支持两臂分别释放和换抓。
动力学探针当前使用约 1.7 m 的工作绳和额外桌面余绳，尚未完成绳长与翻套流程的适配。
这些模块与默认静态场景入口分开，木器具保留 v5 的 75% 尺度、90° 朝向和底座居中位置。

`robot_grasp_lift_04` 完成了**预抓取初始化、合爪、0.5 秒无辅助保持、带辅助的双臂抬升**。
左爪夹绳，右爪夹木柄；无辅助保持期间，左侧绳约下滑 1.93 mm，木柄约移动 0.36 mm。
它不是从桌面拾取，也不是完整解环。四路视频重渲染同一次原生执行记录的实测状态，
均为 1280×720、181 帧、20 fps、9.05 秒，已完整解码并核对同步与哈希：

- [v04 俯视](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_grasp_lift_04/four_views/cam_high.mp4)
- [v04 斜视](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_grasp_lift_04/four_views/cam_low.mp4)
- [v04 左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_grasp_lift_04/four_views/cam_left_wrist.mp4)
- [v04 右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_grasp_lift_04/four_views/cam_right_wrist.mp4)

局部流程可用 `python -m topogym.tasks.orbits.grasp_demo <新目录>` 复现，
再用 `python -m topogym.tasks.orbits.motion_render <新目录>` 生成四路录像。

`robot_ring4_09` 进一步完成了**从最低环下方预抓取、穿过最低环抬升、夹爪越过顶球、
降到第一环外侧**的连续局部执行。右臂持木柄，左臂持绳。
逐阶段绳索检查发现，绳套从顶球旁侧绕过，最高杆绕数仍为零；
所以这只是机械臂路径测试，尚未完成参考解法中将绳套翻过顶球的动作。
本版在真实双侧手指接触后直接启用辅助抓持，没有通过无辅助保持测试；
此前相同竖直夹爪姿态在撤除辅助后会滑绳。记录的机器人接触仅包含手指与绳，
抬升转腕期间最大接触穿透约 1.24 mm，其余运动阶段不超过 0.50 mm。
四视角均为实测状态重渲染，291 帧、20 fps、14.55 秒，已完整解码并核对哈希：

- [v09 高位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_ring4_09/four_views/cam_high.mp4)
- [v09 低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_ring4_09/four_views/cam_low.mp4)
- [v09 左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_ring4_09/four_views/cam_left_wrist.mp4)
- [v09 右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_ring4_09/four_views/cam_right_wrist.mp4)

运行目录中的 `recipe.json` 保存抓持参数及各阶段目标，可传给
`python -m topogym.tasks.orbits.grasp_demo <新目录> --recipe <recipe.json>` 重跑。
绳索规划探针支持碰撞／抓持误差超限停止，并分别保留各阶段的物理检查点；
平面绕数和环盘穿越次数仅作诊断，不能作为完整解脱的成功判据。

全套解法尚未完成一次连续机器人执行，以上探针未作为完整 demo 收录到 `demos/orbits/`。

`robot_bight_spread_12` 改为两臂分别握住绳圈两条腿，让开口保持横向展开，木柄自由运动。
从最低环上方的预抓取状态出发，执行合爪、接触确认、撑圈抬升、跨过顶球、在第一环外下放。
它使用接触后启用的辅助抓持，未测试无辅助保持，也没有包含桌面拾取和此前的提绳准备。
最高杆的平面绕数由 0 变为 −1，与 v09 绳圈从球旁绕过的失败结果不同；
这一指标只验证局部绕柱变化，不能证明完整解脱。
实际机器人运动期间记录的最大接触穿透约 0.405 mm，机器人接触对只有手指与绳。
四路视频均来自同一次执行的实测状态，1280×720、351 帧、20 fps、17.55 秒，已完整解码并核对哈希：

- [v12 高位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_bight_spread_12/four_views/cam_high.mp4)
- [v12 低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_bight_spread_12/four_views/cam_low.mp4)
- [v12 左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_bight_spread_12/four_views/cam_left_wrist.mp4)
- [v12 右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_bight_spread_12/four_views/cam_right_wrist.mp4)

复现入口为 `python -m topogym.tasks.orbits.bimanual_bight_demo <新目录>`，
再用 `python -m topogym.tasks.orbits.motion_render <同一目录>` 渲染。
`scope.json`、`report.json`、`decode_report.json` 分别记录初始化范围、执行接触和视频核对结果。
新版运行器还保存完整 MuJoCo 积分状态、抓持绑定和抓持点偏移，支持同模型、同后端版本续跑；
回归测试验证保存／恢复后继续步进与不中断步进一致。v12 生成于该改动前，没有这份完整检查点，
不能将它的录像帧当作完整物理状态续接。5 项机器人回归测试通过。

2026-09-21 端部绳圈修正：v12 木柄实际是自由刚体。其内凹来自工作绳的手工余绳排布：
两条腿先越过木柄，再折回连接孔；木柄仍放在旧的 `x=0.3225 m` 位置。
提绳准备结束后，绳的最远点超过木柄中心约 148 mm，桌面摩擦保留了这个折返。
这不符合参考视频中绳腿顺畅通向椭圆木件的初态。

`natural_working_state` 保持 1.69788 m 工作绳及原始第五杆穿套关系，
将自由木柄移至器具局部 `x=0.60 m`，两侧余绳向外展开，每条腿沿纵向连续通向连接孔。
绳与木柄一起经过 2 秒无抓持约束的重力静置，再进行提绳准备。
准备完成后，绳端位于木柄中心之前 15 mm，消除了远端折返；两端连接误差不超过 0.048 mm。
新位置距桌边至少 94 mm，两臂各自的木柄接近姿态均通过 IK 和碰撞检查。
这些是有限姿态检查，未据此认证连续木柄抓取或完整解法。

`bimanual_bight_demo` 默认使用新绳圈；`--cord-layout legacy_folded` 可复现 v12 的旧排布。
已有规划探针和测试夹具继续保留旧模型，避免旧检查点被不同的绳初态解释。
新运行器逐阶段保存轨迹和完整检查点；相同模型的准备检查点可用 `--prepared-state <目录>` 重用。

验证运行 `robot_natural_loop_14` 从修正后的预抓取状态重新执行整段撑圈、跨球和下放，
自由木柄随绳索拉动移动了约 241 mm。整个局部运动中，绳的最远点一直位于木柄中心之前，
没有重现旧的远端折返；最大接触穿透 0.400 mm，机器人接触记录仅包含手指与绳。
原生执行后的四视角重渲染均为 351 帧、20 fps、17.55 秒，完整解码、同步和 SHA-256 核对通过。
7 项机器人回归测试通过，包括保绳长／初始穿套关系、末端不折返和移动木柄后的双端连接检查。

- [v14 高位：修正后的自然绳圈](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_natural_loop_14/four_views/cam_high.mp4)
- [v14 低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_natural_loop_14/four_views/cam_low.mp4)
- [v14 左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_natural_loop_14/four_views/cam_left_wrist.mp4)
- [v14 右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_natural_loop_14/four_views/cam_right_wrist.mp4)

该版仍使用接触后启用的辅助抓持，准备阶段的提绳不属于机器人执行。
`natural_loop_validation.json` 保存木柄实测位移、绳端关系、连接误差和接触数据；
`decode_report.json` 保存视频核对结果。初态修正不表示完整解法已通过。

## 连续路径检查与换抓进展（v19，仍未完成解脱）

`robot_fold_19` 从 v14 的完整动力学检查点继续执行，保留速度、控制量、求解器状态和
抓持绑定。原 v14 的全部记录逐项一致；没有用零速度重置或独立探针替代机器人状态。
当前连续执行 41.75 秒，覆盖双臂跨球、右手松开和重新夹住指定绳段、左手退让，
以及右手绕开最高环、转腕并将新折环送至环下方。仍从辅助准备后的预抓取状态开始，
抓持使用双侧接触确认后启用的约束。

新增 `continuous_motion` 在执行前按最多 4 mm / 0.04 rad 的间隔求解整段笛卡尔路径，
检查关节分支连续性、关节限位和机器人碰撞，然后由原生关节执行器跟踪路径。
运行中监测接触深度并逐阶段保留完整检查点。`trajectory_audit` 复核全部实测记录；
有限采样检查不等于解析的连续碰撞证明。

v19 的 1671 个记录状态没有机器人与固定器具、自身或桌面的碰撞违规；
最大采样接触深度 0.846 mm，双绳端连接误差不超过 0.309 mm，记录点与模型正运动学一致。
8 项机器人回归测试通过，包括不可达路径在规划失败后不改变物理状态的检查。
四路视频均为 836 帧、20 fps、41.8 秒，完整解码和同步核对通过。

- [v19 高位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_fold_19/four_views/cam_high.mp4)
- [v19 低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_fold_19/four_views/cam_low.mp4)
- [v19 左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_fold_19/four_views/cam_left_wrist.mp4)
- [v19 右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_fold_19/four_views/cam_right_wrist.mp4)

**全流程验证尚未通过。** 接下来将折环从最高环内提起的 28 条候选路径，
以及双臂闭合夹爪的 192 个倾斜／垂直插入候选姿态，均被碰撞或 IK 容差检查拒绝。
这些有限尝试不能证明所有换手策略均不可行；需要继续开发环上下的绳段交接。
递归穿环和末端完整取出也尚未由同一次机器人执行验证。
完整结果见 [验证报告](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_fold_19/full_flow_validation.json)。
因此 v19 保留在开发目录，未作为完整 demo 收录到 `demos/orbits/`。

## 检查与资产

生成器检查封闭正体积网格、四只真实环孔、五根杆、十处有意的固定连接、
非预期刚体相交、绳与木件的保守间隙、绳自身的非局部间隙、桌面高度、
最低环下方的绳套，以及沿绳两端在木柄内部闭合后的杆轴绕数。
初态绕数绝对值应为 `[0, 0, 0, 0, 1]`。这只是初态检查，不是全程可解性证明。

输出包括 OBJ、内嵌木纹的 GLB、整套 `scene.glb`、尺寸 JSON、绳中心线 NPY、
几何报告和 SHA-256；场景构建后另核对 Genesis 导入坐标与原始网格的一致性。
[来源记录](../../../assets/tasks/orbits/video_reconstruction_v1/source.json)保留观察时刻、
可见结构和未决项。资产生成不依赖视频下载，木纹复用本仓库已有资产。

原 v1 三路同步初态预览（保留旧摆放供对照；各 8 秒、120 帧、15 fps，非完整机器人 demo）：

- 实验室与双臂全景（旧产物已清理：`2026-09-20_static_initial_v1_overview.mp4`）
- 四环与黄绳斜前近景（旧产物已清理：`2026-09-20_static_initial_v1_front_oblique.mp4`）
- 穿套初态俯视（旧产物已清理：`2026-09-20_static_initial_v1_topdown.mp4`）

配套资产、报告和清单位于
[`runs/demo_metadata/orbits/2026-09-20_static_initial_v1/`](../../../runs/demo_metadata/orbits/2026-09-20_static_initial_v1/README.md)。
视频目录只放独立 MP4，不生成 HTML。

## 先验证无机械臂路径（2026-09-21）

按最新要求，当前先开发绳索自主运动的完整解法，再把路径改造成双臂动作。
完整解套尚未完成；已经核验的无臂 v66 是从自然初态开始的 38 秒连续局部流程。
它用指定绳段上的位置约束驱动绳索，保留重力、木件碰撞、自碰撞和两端连接；
木柄是自由刚体。器具仍为 75% 比例，本次规划试验使用 1.1 m 工作绳，
没有替换机器人场景原有的 1.69788 m 绳索默认值。

- [v66 总览](../../../runs/environment_bootstrap/orbits/solution_development_v1/reference_probe_66/rope_views/overview.mp4)
- [v66 正面](../../../runs/environment_bootstrap/orbits/solution_development_v1/reference_probe_66/rope_views/front.mp4)
- [v66 侧面](../../../runs/environment_bootstrap/orbits/solution_development_v1/reference_probe_66/rope_views/side.mp4)
- [v66 俯视](../../../runs/environment_bootstrap/orbits/solution_development_v1/reference_probe_66/rope_views/top.mp4)

四路均为同一轨迹的状态重渲染，761 帧、20 fps、38.05 秒、1280×720，已完整解码。
积分期间每 10 步检查的最大接触深度为 0.594 mm，最大控制点误差为 4.047 mm。
对全部 1521 个保存状态的独立复核确认记录点与模型一致，环的有向穿越数之和均为零；
绳端连接误差最大 1.156 mm。最终绳索仍被器具约束，不能据此认定完整解套或机器人成功。

新增 `rope_only_demo` 用于复现该局部流程；`rope_render` 输出无臂四视角，
`rope_audit` 核验记录并单独检查绳索及木柄是否全部移动到器具右侧的分离区域。
环穿越数、杆轴绕数和仿真稳定性都是诊断信息，不能替代最终脱离检查。
后续试跑发现，相似的外观可能对应不同绳段形成的小绳套；抓错绳段会让动作返回旧状态，
或在最低环边缘留下额外绳套。因此更长的试跑暂不作为完整 demo 交付。

迁移到双臂时，需要把每次控制的绳段编号与双手接触点对应起来，
并在穿环前后安排真实的松手、接取和余绳供给。绳索中心线可以通过的路径，
还须按夹爪体积和姿态重新规划；此前 v19 的直接抬升路径未通过环口碰撞检查，
需要从环两侧交接绳段。展圈宽度、木柄活动空间和运动时序也要在加入机械臂后重新验证。
这里是迁移约束的整理，尚未构成完整 IK 或物理执行验证。

```bash
# 仅复现已核验的局部前缀；不会声称完成解套。
.venv-gs121-nyx/bin/python -m topogym.tasks.orbits.rope_only_demo \
  runs/environment_bootstrap/orbits/rope_prefix_reproduction
.venv-gs121-nyx/bin/python -m topogym.tasks.orbits.rope_audit \
  runs/environment_bootstrap/orbits/rope_prefix_reproduction
MUJOCO_GL=egl .venv-gs121-nyx/bin/python -m topogym.tasks.orbits.rope_render \
  runs/environment_bootstrap/orbits/rope_prefix_reproduction
```

## 复现

```bash
# 几何、穿套关系和间隙检查，无物理后端。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.orbits \
  run.build_scene=false run.render=false

# ALOHA + Nyx 初态三视角录制，需要 CUDA。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.orbits

# 初态检查、任务登记、全部主配置 compose / resolve。
.venv-gs121-nyx/bin/python -m unittest tests.check_orbits \
  tests.check_task_baseline_catalog tests.check_configs_compose

# 使用默认摆放进行有限接近姿态的 IK / 碰撞检查，不步进物理。
.venv-gs121-nyx/bin/python -m topogym.tasks.orbits.workspace \
  --output runs/environment_bootstrap/orbits/static_base_centered_v5/workspace_report.json
```

主配置：[`configs/orbits_preview.yaml`](../../../configs/orbits_preview.yaml)。
默认输出：`runs/environment_bootstrap/orbits/static_base_centered_v5/`。
几何尺寸可配置，但当前仅支持视频四环实例，未提供随机家族生成器；
任何改动必须重新通过几何检查。

后续需要完成参考图中的绳段识别、连续换抓、余绳供给和递归穿环动作，
并在同一次机器人执行中验证最终绳与木柄完全脱离器具。当前局部结果不能替代完整 demo。
