# 第 13 项：Orbits 四环阶梯解绳

## 2026-09-29：两／三／四环场景与稳定性验收入口

Easy、Medium、Hard 的设计方案已有，本轮将前两档从占位类接到标准 Task / Env。
三档共用当前紧凑绳 profile、0.85 尺度、约 0.800 m 绳长、局部 X=0.410 m 的自由木柄、
FEM 材料及桌面摆放，只改变环／柱层数。最低环高度、孔径、柱距与相邻层高差相同，
顶层高度随层数增加；三档绳圈均绕最后一柱且位于最低环下方。

| 入口 | 环／柱 | 初始绕柱绝对值 | 构造与同 seed 重建 | 物理稳定性 |
|---|---|---|---|---|
| `orbits_easy` | 2／3 | `[0,0,1]` | 通过 | 未取得验收结论 |
| `orbits_medium` | 3／4 | `[0,0,0,1]` | 通过 | 未取得验收结论 |
| `orbits_hard` | 4／5 | `[0,0,0,0,1]` | 通过 | 未取得验收结论 |

[场景布设图](../../../runs/test_results/orbits_tiers_20260929_assets/scene_layouts.png)是静态几何示意，
不是仿真录像。[资产报告](../../../runs/test_results/orbits_tiers_20260929_assets/report.json)
包括三档及兼容 `reference85`，四个入口均完整构造并逐文件重建一致。
[Hard 回归](../../../runs/test_results/orbits_tiers_20260929_assets/hard_regression.json)
确认 41 个既有物理／视觉资产哈希不变；`base` 继续指向 `orbits_reference85`。
新实例元数据明确给出环 ID、世界坐标、受困柱和独立的资格字段。

[出生 FEM 审计](../../../runs/test_results/orbits_tiers_20260929_assets/fem_spawn_audit.json)
确认三档四面体无翻转、绳索位于桌面范围内、体积网格仍绕最后一柱。
但相对直线材料参考构形存在局部应变，不能据此宣称初态静稳。
共享 0.8 m 绳长的目的在于固定比较轴，尚不代表两／三／四环均有足够余绳完成解法。
完整解法、机器人可达性及难度排序仍未验证。

新增 [稳定性运行器](../../../scripts/test_orbits_stability.py)从固定源码快照、独立进程串行运行三档，
通过 `Env.step({})` 进行 10 s 无操作重力静置，机器人保持默认 home、无辅助抓持。
通过共享 `RuntimeEvidence / RecordingSession` 保存 Nyx 四路录像、状态和配置身份，
另逐 2.5 ms 物理 tick 记录端点残差、体积比、绳段长度、桌面间隙、固定器具漂移和绕柱诊断。
最后连续 2 s 要求全绳及木柄速度不超过 1 mm/s、木柄角速度不超过 0.02 rad/s；
端点残差全程不超过 1 mm、无四面体翻转、无丢失受困关系。具体阈值写入报告。
投影绕数与当前 IPC 诊断不等于所有原生接触的完整审计，静稳通过也不赋予解题成功资格。

本轮真实尝试受共享 GPU 显存与原生 CUDA 初始化错误阻塞：Hard 首次在初始化时
`cudaErrorMemoryAllocation`；Easy、Medium 重试在首个有效状态前原生中止（`cudaErrorInvalidDevice`），
不能未经诊断将两类错误视为同一根因。
[尝试报告](../../../runs/test_results/orbits_tiers_20260929_runtime_v2/run.json)及
[最终资源检查](../../../runs/test_results/orbits_tiers_20260929_runtime_v3/run.json)分别保留执行与资源等待结果。
未交付首个有效物理状态的运行不能算稳定性失败或通过，也没有可当作验收证据的新视频。
未停止其他 GPU 任务，未降低几何／FEM 精度或切换渲染后端。复现命令如下，输出目录须不存在：

```bash
.venv-gs121-nyx/bin/python scripts/check_variation_assets.py \
  --tasks orbits --repeat --output runs/test_results/orbits_assets_new
.venv-gs121-nyx/bin/python scripts/test_orbits_stability.py \
  --tiers easy medium hard --duration 10 --window 2 --min-free-gib 12 \
  --output runs/test_results/orbits_stability_new
```

下文保留历史四环实例的原始证据范围。

> **2026-09-27 更新：** hard 使用 0.85 比例四环、约 0.800 m 紧凑绳路与外置木柄，并放宽绳路弯头。初始向上弹起减轻但仍有松弛运动，尚未取得静稳初态或完整解法资格。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。


任务 ID：`orbits`，版本 `video_reconstruction_v1`。按用户指定的
[SiamMandalay 视频](https://www.youtube.com/watch?v=B-EB9Q-JqXA)重建整套器具及约第 10 秒的受困初态。
该视频标题是 Orbits，实际为 **四环、五杆**；“九连环”是用户对连环解绳类的称呼，未据此擅自增加五只环。
视频为厂商的解法渲染演示，不能作为本项目物理求解通过的证据。

2026-09-21：**已按指定视频完成整套无机械臂流程 v2**，含最终全绳与木柄脱离、落桌和松手。
旧 v1 增加木柄穿最低环的绕行，不作为本轮视频顺序验收。双臂适配已恢复开发，完整机器人执行尚未完成。

## 从无臂 v2 迁移双臂（进行中）

全程预检已覆盖 93 个动作和 92 个精确目标（不合并亚毫米位置差异）：21 个动作同时使用超过两个控制点，10 个目标在有限姿态搜索中未找到安全的直接抓持。该结果不是不可达证明，也不是连续 IK 已通过；环下抓点、双手接续、远端拉直和落桌必须重新规划。

[全程预检](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_video_retarget_v1/full_route_preflight.json)与[本轮状态](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_video_retarget_v1/status.json)保留实际检查范围。拟采用的调整如下，不能把候选路径直接视为机器人成功：

| 动作 | 对双臂控制的调整 | 当前证据 |
| --- | --- | --- |
| 从桌面拾取 | 使用实际指尖偏移，按绳切线确定夹爪开合方向；另一手保留原挤压指令 | 原装夹爪从 home 拾取通过 |
| 环下送圈与接取 | 先悬空接绳，再侧向供绳、从上方接取；根据实测材料位置修正 IK | 侧向供绳已执行；原装夹爪的环孔交接仍被碰撞检查拒绝 |
| 双腿展圈 | 木柄先落桌，解除原来的额外绳弯控制，只保留两条绳腿 | 两控制点外力候选覆盖完整取绳顺序 |
| 第四／第三环外侧抬升 | 自由绳弯不能再固定；对应两腿抬到 0.29／0.34 m，并调整横向位置 | 指定材料点的环外路径检查通过 |
| 远端拉绳 | 木柄目标 X 收到不超过 0.60 m，随后仍需双臂同时可达及真实换抓验证 | 仅外力候选通过，未认证共同工作空间内的连续机器人动作 |
| 最终放置 | 木柄先放平，避开堆绳，再释放；继续检查整绳分离与停稳 | 尚未通过两控制点版本的落桌／释放验收 |

`rope_twohold_extraction_217` 保存两控制点候选的 **94 个动作、220 s**，含 193 的初态至 168 s 前缀及从其完整检查点继续的 215；边界位置与材料点逐位相同。不是新的不间断执行，也不是机器人运行。[候选审计](../../../runs/environment_bootstrap/orbits/solution_development_v1/rope_twohold_extraction_217/two_control_audit.json)确认 15 个参考阶段、28 次指定材料点过孔、两次环外抬升和整绳／木柄几何脱离；最大接触深度 1.382 mm、抓持误差 13.526 mm，仍在原 1.5／15 mm 阈值内。它在取出时仍保持两处外力抓持，`adapted_external_route_passed=false`，不能替换已归档无臂 v2。

完整从初态重跑 193 曾在最后一轮展圈前的木柄放置处被保护器停止。定位后修正了姿态反馈读取旧派生速度的问题，并将木柄移出堆绳区，后续 215 才通过这段并完成取出。216 的最终放置仍触发 3.257 mm 深度保护；其他放置候选即使完整释放，最后一秒仍有约 5.8–12.9 mm 材料位移，未达到沿用的 3.3 mm 标准。开发入口 `python -m topogym.tasks.orbits.two_control_route <新目录>` 是保留这些保护器的外力探针，不是完整机器人 demo 入口。

`robot_home_pickup_170` 已从原生 home 连续完成接近、两条绳腿拾取和 60 mm 抬升，共 30 s。保留 75% 器具、原长绳索与原装夹爪，使用共享实体桌面。抓取期间保存的左/右手 661/161 帧全部有双侧接触；1201 帧无机器人/器具/自碰撞，绳端最大误差 0.019 mm。此段只是拾取证据，尚未通过最低环。

公共录制已迁移到 `robot_recording.py`：`prepare(lab_default_v1)`、完整 qpos/绳节点 `replay` 和 `validate`。四路使用标准 ALOHA 机位及共享实验室，不重建被动手指。当前 30 s 诊断录像对应已审计的 `robot_home_pickup_170`，640×360、20 fps、601 帧，同步及完整解码通过，未作为正式完整任务归档：

- [高位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_home_pickup_170_recording/videos/cam_high.mp4)
- [低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_home_pickup_170_recording/videos/cam_low.mp4)
- [左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_home_pickup_170_recording/videos/cam_left_wrist.mp4)
- [右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_home_pickup_170_recording/videos/cam_right_wrist.mp4)

抓持使用接触门控点约束；新增运行中保护器会在持续 50 ms 完全失去手指接触或约束误差超过 15 mm 时停止，不允许靠悬空约束继续。左右手直接在环外同步提升会将绳圈挂住最低环环缘，开发尝试已被保护器拒绝。当前检查不对称供绳及环下指尖接近，完整机器人成功仍为 false。

较长开发分支 201 完成右手悬空接取，206/207 完成左手释放辅助抓持后的环下供绳，209 延伸到 58 s。该分支不是合格录像：207 的逐帧审计发现 194 帧与底座或第五杆相交，主要发生在早期近处拾取，另有接取时的微小杆接触。208/211 共 770 个实际双手状态下的接取姿态均未通过，210/213 向孔内提高供绳点的路径也碰到第四环。有限搜索不能证明原装夹爪绝对不可解，但当前全流程 IK、交接和原生物理执行均未通过。未修改夹指、器具尺寸或验收阈值；20 项机器人／录制回归通过。

复现入口：`python -m topogym.tasks.orbits.robot_pickup <新目录>`；全程映射预检：`python -m topogym.tasks.orbits.robot_retarget --model <无臂v2/model.xml> --output <报告.json>`；四视角诊断录制：`MUJOCO_GL=egl python -m topogym.tasks.orbits.robot_recording <运行目录> <新录制目录>`。运行前设置 `PYTHONPATH=.` 并使用项目虚拟环境。

## 按指定视频完成的无臂流程 v2（2026-09-21）

已从自然初态完成 **93 个动作、213 秒**的完整执行，覆盖视频的 15 个阶段：
第四环提圈、四轮第一环回穿、第三环左右侧提圈、第四及第三环外侧展圈，最后整根绳索连同木柄取出、落桌并松手。
保持 **75% 器具、1.6978807 m 工作绳、229 个材料点**。木柄全程位于底座平面范围之外，最小保守净空 63.64 mm。

- [总览](../../../demos/orbits/varaition_rope_only/overview/rope_video_full_v2.mp4)
- [斜前](../../../demos/orbits/varaition_rope_only/front_oblique/rope_video_full_v2.mp4)
- [侧面](../../../demos/orbits/varaition_rope_only/side/rope_video_full_v2.mp4)
- [俯视](../../../demos/orbits/varaition_rope_only/topdown/rope_video_full_v2.mp4)

四路录像由同一次从初态执行的实测轨迹经共享 `topogym.recording` 重渲染生成；
1280×720、20 fps、4260 帧、213.00 秒，中文阶段说明覆盖全程。
[归档与复现](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/README.md)保留视频哈希、参考视频/PDF、模型、控制配置、检查点和源码快照。

| 仿真时间（秒） | 视频对应操作 |
| --- | --- |
| 0–36 | 第四环提圈、越球及第一轮第一环回穿 |
| 36–92 | 第三环左侧／第二环右侧重叠口提圈，第二轮回穿，退到第四环下并拉柄整理 |
| 92–146 | 从第四环外侧展圈，经第三环右侧上提，第三轮回穿并整理 |
| 146–195 | 从第三环外侧展圈，经第二环右侧上提，第四轮回穿并越球向外取出 |
| 195–213 | 全绳与木柄移出，展开落桌，关闭全部控制后继续模拟 4 秒 |

[参考动作审计](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/evidence/source/reference_audit.json)逐项检查 28 次指定材料点过孔及两次环外抬升，
全部通过；这是人工解读视频后对指定材料点的检验，不是逐帧外观一致或所有接触的连续证明。
[物理采样与最终分离检查](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/evidence/source/rope_audit.json)覆盖 8521 个保存状态，重建点误差为零。
末态全绳表面最左 X=0.397766 m，整只木柄也在器具分离边界 X=0.18625 m 之外。

积分中每 5 ms 检查一次：最大接触深度 **0.600 mm**（停止阈值 1.5 mm），
最大抓持误差 **7.032 mm**（停止阈值 15 mm）。绳端连接误差最大 2.775 mm，
单边长度误差最大 0.522 mm。采用 7 次完整求解器检查点续跑，
每次状态及轨迹边界均逐位一致；在 36 s 处有一次显式求解器冷启动，未改写位置、速度或时间。

**这是外部约束驱动的无臂完整演示。** 展圈和放置最多同时控制 4 个点；木柄仅在最终放置时使用姿态转矩。
最后一秒材料点最大位移 **2.949 mm**，小于绳直径 3.3 mm，仍有毫米级余振，未认证精确静力平衡。
绳模型未标定弯曲刚度，也未验证不同初态或扰动下的鲁棒性。
归档策略为 `external_physics_v1`，`physics_qualified=false`；完整机器人 IK、接触抓持和原生双臂执行仍待实现。

```bash
# 完整重跑（目录须不存在），自动进行整绳脱离和参考动作审计。
.venv-gs121-nyx/bin/python -m topogym.tasks.orbits.rope_only_demo \
  runs/environment_bootstrap/orbits/video_reference_reproduction
# 长任务可首轮加 --max-actions 12，之后用同一目录加 --resume --max-actions 12，直到全部动作完成。
MUJOCO_GL=egl .venv-gs121-nyx/bin/python -m topogym.tasks.orbits.recording_adapter \
  runs/environment_bootstrap/orbits/video_reference_reproduction \
  runs/environment_bootstrap/orbits/video_reference_reproduction_recording
```

24 项 Orbits、完整检查点续跑和共享归档回归通过。历史 v1 的木柄穿最低环绕行已弃用；
后续双臂实现应以本 v2 的材料点顺序和穿套关系为起点，重新安排双手交接及共同工作区内的供绳和放置。

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
最早的静态初始化只覆盖整套器具、穿套关系与可重载资产。
该早期预览的任务对象固定、碰撞关闭，录像仅相机运动，`simulation_steps=0`。
这不描述本页上方的无臂完整动力学 v2；机器人局部抓持探针见下文。

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
早期动力学探针使用约 1.7 m 的工作绳和额外桌面余绳，当时尚未完成绳长与翻套流程的适配；
本页上方的无臂 v2 已用原工作绳长完成整套路线。
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
再用 `python -m topogym.tasks.orbits.motion_render <新目录> <输出目录>` 经公共录制模块重渲染四路录像。

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
再用 `python -m topogym.tasks.orbits.motion_render <同一目录> <输出目录>` 经公共录制模块重渲染。
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

## 历史无臂路径 v1（2026-09-21，不满足本次视频顺序）

此前无臂 v1 从自然初态重新运行并最终解脱：
105 个动作、208.5 秒仿真，最后绳索与木柄完全移出器具，释放全部控制后继续静置 4 秒。
器具为 75% 尺度，本规划变体使用 **1.1 m 工作绳、149 节点**；没有替换机器人场景的 1.69788 m 默认绳长。
参照指定视频与厂商解法图，针对模型间隙加入木柄侧立通过最低环的绕行，未声称逐帧复制视频。

- [总览](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/previous_videos/overview/2026-09-21_rope_only_full_v1_overview.mp4)
- [正面](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/previous_videos/front_oblique/2026-09-21_rope_only_full_v1_front_oblique.mp4)
- [侧面](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/previous_videos/side/2026-09-21_rope_only_full_v1_side.mp4)
- [俯视](../../../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/previous_videos/topdown/2026-09-21_rope_only_full_v1_topdown.mp4)

四路均来自 `rope_continuous_98` 同一次从初态执行后的状态重渲染：1280×720、20 fps、
4171 帧、208.55 秒，通过完整解码与同步、哈希检查。没有拼接不同运行或注入位置、速度、时间；
10 个指定阶段边界清空求解器热启动值，保持当时物理状态继续积分。它验证固定指令和数值设置下的完整路径，
尚未验证扰动、不同绳长或移除求解器重启后的鲁棒性。早期检查点续跑视频仍仅作开发复核。

| 时间段（仿真秒） | 动作 |
| --- | --- |
| 0–76 | 从最低环提起绳圈，撑圈越球，按材料点交替穿环；换取下一段绳后重复 |
| 76–113 | 沿阶梯环下放，调整木柄姿态，通过最低环左侧 |
| 113–163 | 分别在第四环、第三环外侧提起大绳圈，并重新整理木柄和余绳 |
| 163–190.5 | 完成最后一组折圈；末次从第二环**外侧**上提，再穿第一环 |
| 190.5–208.5 | 完全取出，木柄放低，松开所有控制并静置 |

积分期间每 5 ms 检查，最大接触深度 **1.218 mm**，小于 1.5 mm 停止阈值；
最大抓持位置误差 **12.324 mm**，小于 15 mm 停止阈值。8341 个保存状态均有限、记录点与模型一致。
终态绳表面最左 X=0.423641 m，整个木柄也位于器具右侧分离边界 X=0.18625 m 之外。
最终脱离依据这一空间分离检查，而非仅凭绕数或截图。

**这是约束驱动的路径预演，不是完整机器人执行或严格物理验收。**
绳端连接误差最高 7.097 mm，单段长度误差最高 1.422 mm，柔绳弯曲刚度未标定；
木柄静止后部分绳段仍有毫米级残余运动。穿环和放置阶段使用外加木柄姿态转矩，
展圈阶段最多同时控制 4 个点。以上限制必须在真实双臂实现时处理，不能从视频直接继承成功标签。

[完整归档与复现说明](../../../runs/demo_metadata/orbits/2026-09-21_rope_only_full_v1/README.md)
保存模型、轨迹、各阶段检查点、控制配置、审计、源码快照和参考资料。15 项 Orbits / 机器人回归通过。

```bash
# 显式复现历史 v1；输出目录须不存在。
.venv-gs121-nyx/bin/python -m topogym.tasks.orbits.rope_only_demo \
  runs/environment_bootstrap/orbits/rope_full_reproduction \
  --route configs/task_variants/orbits/rope_solution_v1.json
# 仅需旧版 38 秒前缀时，在 rope_only_demo 后加 --prefix。
```

## 历史 v1 的双臂迁移分析（本轮暂停）

以下结论来自旧 v1 的控制指令和器具尺寸。木柄穿最低环属于旧绕行，已不作为视频路线的迁移目标；
还没有验证这些改写后的完整 IK 或双臂动力学。

| 无臂路径阶段（仿真秒） | 已发现的限制 | 双臂改写方向 |
| --- | --- | --- |
| 0–113：撑圈、越球、交替穿环 | 控制器可瞬时切换材料点；夹爪有体积，不能跟随绳中心线直接穿所有环口 | 每次切换拆成接近、闭合、接触确认、接取、原手释放；细绳从环内送入，另一手在环外接取 |
| 98–107：木柄经第四环左侧 | 当前木柄用外加转矩侧立通过；第三环下缘与第四环上缘的竖直净空约 39 mm | 先尝试用绳圈交接替代整只夹爪带柄穿缝；若仍要过柄，检查木柄与夹爪整体的姿态和包络 |
| 117–121：在第四环外侧提起大圈 | 同时控制弯头和两条绳腿，共 3 点；横向展圈 280 mm | 用桌面暂存弯头，双手提绳腿，再轮流换抓；需确认松弛绳不重新落进已解开的环 |
| 157–163：在第三环外侧提起大圈 | 弯头、两条绳腿和木柄共 4 点；165–169.5 仍有 3 点 | 先放稳木柄，再做双手展圈；把弯头固定需求改成桌面/器具接触支撑，重新规划余绳供给 |
| 177–190.5：最后一次折圈 | 弯头必须从第二环外侧上提后穿第一环；再次穿第二环会回到旧套绳状态 | 保留穿越关系和材料点顺序，调整空间轨迹及接取姿态；不能仅按相似外观选取另一段绳 |
| 190.5–208.5：取出、放下、松手 | 木柄远端目标为器具坐标 X=0.65 m；无臂场景没有可达性限制 | 先在两臂共同工作空间内设计整理/收绳与放置位置，再整体求 IK、避碰和时间参数；无需照搬远拉终点 |

器具继续使用原始尺寸的 75%；本条规划路径使用 1.1 m、149 节点工作绳。机器人原有默认绳长为 1.69788 m，节点编号不能直接照搬。迁移时以沿绳弧长、绳段所在环口和接触关系识别抓取材料点，重新分配多余绳长。

本次路径最多同时使用 4 个外部抓持约束，并在木柄穿环和放置时使用姿态转矩控制。它提供完整穿套顺序和避障参考，不代表两个夹爪已经能实现所有约束。后续验收应同时满足：最多两只实际夹爪抓持、接触确认后接取、全工具避碰、连续 IK、双臂原生动力学、松手后仍完全脱离。

## 从无臂路径继续开发双臂执行：v109

已把 v19 的原生状态续跑到 **65.5 s**：右臂保持抓绳，先在环外转姿，再斜向送入第一环；绳圈顶部达到 Z=251.50 mm，穿过 Z=247.50 mm 的第一环平面。此时仍需另一只手接取、拉出绳圈，**未完成第一环操作或完整解绳**。

- [高位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_109/four_views/cam_high.mp4)
- [低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_109/four_views/cam_low.mp4)
- [左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_109/four_views/cam_left_wrist.mp4)
- [右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_109/four_views/cam_right_wrist.mp4)

四路视频来自同一条实测状态轨迹，各 1311 帧、20 fps、65.55 s，完整解码及同步检查通过。全部 2621 个记录状态未检出机器人与器具、自身的碰撞；整个前缀的最大采样接触穿透为 0.846 mm，绳端连接误差最大 0.309 mm。记录点与模型重建点一致；有限采样检查不构成完整物理资格。[验证摘要](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_109/development_validation.json)和同目录审计保留具体范围。

这条机器人试验仍用原来的 **1.69788 m 工作绳**、75% 器具，以及第四环已穿入的预抓取初始化；抓持包含接触确认后的点约束辅助。无臂完整版的 1.1 m 绳长和材料节点编号不能直接继承。本轮新增环外关节路径规划、实际抓持点的笛卡尔目标和可选关节积分补偿；避碰使用实测夹爪宽度与指令宽度的较大者，避免夹着绳时低估夹爪包络。20 项 Orbits / 机器人回归通过。

当前瓶颈是环口交接：露出环面的绳圈太短，两只夹爪会互相占据接取空间。v116 让左夹爪实际接触并夹住一条绳腿，但 v120 在原手退出后弯头塌落，左手的实际接触也丢失；这次交接失败。下一步需重新安排双绳腿抓取，或在两只手仍位于环上方时改变供绳顺序。当前柔性绳模型有长度约束和接触，未建模弯曲刚度；不能假设松开后的弯头会自行保持直立。

新增 `python -m topogym.tasks.orbits.grasp_audit <运行目录>` 检查辅助抓持期间的真实夹指接触。v109 没有完全失去接触的采样区间，但右手最长有 0.75 s 未保持双侧接触，不能据此宣称无辅助抓持稳定。v120 最长 **4.925 s 完全没有夹指接触，点约束却仍保持连接**；该审计明确区分“约束还连着”和“夹爪仍夹着绳子”，防止把这类失败作为完整机器人 demo 收录。

## 双手保持绳腿的替代路线：v130 / v132

v109 的环口交接失败后，从原上方撑圈检查点改写供绳顺序。两只夹爪始终保持材料点 100 / 128，
通过转腕、降低和调整间距，让中间自由弯头垂入第二环。v130 到 38.5 s；它是不同路线，
不能与 v109 的 65.5 s 按时长比较完成度，也未证明第一、第二环的完整解法操作已完成。

- [高位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_130/four_views/cam_high.mp4)
- [低位](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_130/four_views/cam_low.mp4)
- [左腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_130/four_views/cam_left_wrist.mp4)
- [右腕](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_130/four_views/cam_right_wrist.mp4)

四路为同一条精确检查点续跑轨迹的实测状态重渲染，均为 771 帧、20 fps、38.55 s，完整解码、
同步和哈希检查通过。1541 个记录状态未检出机器人与器具或自身碰撞；采样最大接触穿透 0.420 mm，
绳端连接误差最大 0.309 mm。每只手在 1481 个接触确认后的采样状态中均保持双侧夹指接触。
仍包含预抓取和辅助抓持，不是新初始化后的一次完整解绳执行。
[验证范围和证据](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_130/development_validation.json)。

v131 能执行收拢、上提和过球，但材料点 114 实际从第一环外侧上去；这条延长路线不满足目标穿套顺序。
新增 `python -m topogym.tasks.orbits.passage_audit <目录> --start-time 38.5`，
按实测绳点轨迹插值定位环平面穿越，报告环孔及支杆间隙，区分穿孔和从外侧绕过。
该诊断不证明整个绳弯通过，也不替代连续物理与最终解脱检查。

独立分支 v132 在 v130 状态关闭两只手的辅助抓持，静握 2 s 后双臂上提 15 mm、历时 3 s。
后续 200 个采样状态中两手均有双侧接触，材料点相对夹爪的最大偏差为左 2.422 mm、右 1.764 mm。
这是局部无辅助夹持验证，不能把之前的辅助前缀或完整解绳标为无辅助通过。
[无辅助接触与偏差审计](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_transfer_132/unassisted_contact_audit.json)。

实现增加同步双臂实际抓点路径预检和指定阶段检查点续跑；回退时排除未来失败轨迹、指标与事件。
24 项 Orbits / 机器人回归通过。尚需完成正确穿套顺序、原生初始拾取及完整连续运行验收。

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

后续需要把已完成的无臂路径改写成连续双臂换抓、余绳供给和穿环动作，
并在同一次机器人执行中验证最终绳与木柄完全脱离器具。无臂路径不能替代完整机器人 demo。
