# Buzz Wire 3D 基础实例 agent adapter

2026-09-19。接入紧凑单臂基础实例 `spatial_maze_robot_v3 / compact_single_arm_v1`，
复用公共 [`RigidRobotAdapter`](../../../topogym/agent_bridge/robot_adapter.py) 和
[`PandaPort`](../../../topogym/agent_bridge/panda_contract.py)。任务实现为
[`agent_adapter.py`](../../../topogym/tasks/buzz_wire_3d/agent_adapter.py)、
[`agent_scene.py`](../../../topogym/tasks/buzz_wire_3d/agent_scene.py) 与
[`agent_spec.py`](../../../topogym/tasks/buzz_wire_3d/agent_spec.py)。

## 范围与初态

- 本轮只接已有紧凑基础实例；不接高低双拱、错层八字、换平面等新家族及随机变体。
- 圆环已穿在绿色端附近，Panda 位于蓝色握柄的预抓取位置。tick=0 无物理预推进，
  夹爪初始半开口 7.1 mm、闭合目标 0 mm，等待执行后形成真实指垫接触。
  不包含桌面拾取、远处接近或首次穿环。
- **保留真实摩擦抓持，无焊接或辅助抓持约束。** 公共模块在候选集合为空时不启用辅助；
  `grasp_assistance.arm.active / armed` 始终为 false。张爪、闭爪和再次尝试抓取均通过真实接触发生。
- 不使用历史 demo 的自动路径跟踪、私有位姿反馈 IK 或抓持变换修正。
  环杆无外力驱动、重力补偿或运行中位姿赋值；Panda 采用常规重力补偿和有界关节位置控制。
- 私有静态包 [`agent_episode/`](../../../assets/tasks/buzz_wire_3d/compact_single_arm_v1/agent_episode/)
  只保留原碰撞 URDF、物理导线、单个初态与配置，全部绑定哈希。
  启动不读取 `robot_seed.json`、参考动作、历史执行、参考姿态曲线，也不调用路线规划器。
  静态模式复用既有场景建造器，普通几何/参考 demo 入口继续保留原流程。

## 控制、观测与判定

Panda 七关节目标单位为 rad；Robotiq 2F-85 的 `gripper` 为**半开口米数**，
`0.04` 对应总开口 80 mm。控制步 4 ms、16 个积分子步；每个驱动关节 Kp=50、Kv=5、
力矩上限 2.5 N·m。沿用接触时间常数 0.5 ms、`noslip_iterations=100 / noslip_tolerance=1e-12`。
这是实验性摩擦收敛后处理，不添加连接约束。实际参数完整写入公开 task spec。

```python
# 保持当前目标 20 步，即 0.08 秒；只是接口示例。
env.step({}, steps=20)
```

每步完整保存 `agentview / front_oblique / wrist` 三路 PNG、相机位姿和机器人本体观测。
两路外部图覆盖玩具及机械臂；腕相机使用固定于手部的侧向安装角，初态可见环孔和导线。
腕相机不会利用环杆真值自动瞄准。只向 solver 公开基础机械臂/相机知识和本轮图片，
不公开导线坐标、物体尺寸/网格、环杆真值位姿、线路进度、参考图或解题动作。

目标为：**从绿色端沿整条导线移动到橙色端，通行不触线；通过最后弯道后松手，
让圆环靠重力沿末端立柱滑到橙色限位球并稳定静置。**

私有 evaluator 每控制步检查穿环数和实际穿孔交点沿物理导线的位置。允许回退纠错，
交点单步沿线跳跃 >30 mm 会失败，不能从相邻空间段直接跳过未通过的线路。
只有连续通过最后弯道、位于末端立柱且已脱离机器人接触时才允许环杆与导线接触。
终态要求距橙色球中心 <50 mm、交点位于最后 50 mm 导线、仅由末端向上承载 >0.01 N，
线速度 <2 mm/s、角速度 <0.02 rad/s，连续 1 秒。仍被抓持或只停在终点附近不能成功。

其他失败包括：失去穿环、通行触线、环杆穿透 >0.5 mm、机器人/固定物或自身穿透 >0.2 mm、
非指垫机器人部位接触环杆、固定玩具位姿改变、掉落、非有限状态、异常速度及持续关节跟踪失控。
末端无机器人接触期间还检查机械能，额外增长超过 1 mJ 会失败。
接触与拓扑按控制步检查，不能解释为每个积分子步的穿透上界或连续几何证明。

本版为 `physics_qualified=false`。完整自主通行、重新抓取和终态仍需独立物理验证，
历史参考控制器的成功不转移为本 adapter 的任意动作资格。

## 本地创建任务包

操作者在 `/home/jianwen/topogym` 执行以下命令；两个输出目录必须是新目录：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task buzz_wire_3d \
  --output runs/agent_test_demos/states/buzz_wire_codex_001 \
  --package runs/agent_test_demos/agent_solutions/buzz_wire_codex_001 \
  --no-allow-internet
```

等待 `Local task ready` 后，只将 `agent_solutions/buzz_wire_codex_001/` 交给新求解会话。
无需 HTTP、端口或浏览器；常驻仿真子进程必须保持存活，退出后不能恢复同一 episode。
若宿主清理后台进程，请由操作者在稳定本机终端运行创建命令。

默认 manual 不自动采集原生 Codex usage，真实余额未知，不能宣称严格在 2M 内完成。
API metered harness 沿用公共预算机制；输入含重复上下文与缓存输入，缓存不重复相加。
联网开关是 solver 工具策略，不是强制文件权限或网络隔离，也不控制模型服务通信。

## 可直接复制给新 Codex 会话的 prompt

先由操作者创建环境和任务包。**只复制以下代码块，不附整份开发文档、验证视频或源码。**
运行名不同时替换工作目录。

```text
你是 Buzz Wire 3D（立体电流棒）基础实例的受测求解 agent。请从本轮观测出发，自行编写动作段，持续尝试完成任务。

你的工作目录是：
/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/buzz_wire_codex_001

先进入该目录，读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json 和 bridge_config.json。
只将这个任务包、本轮 bridge 返回的观测和允许的通用知识作为任务输入。不要搜索或读取父目录中的仓库文档、实现源码、demo、参考图、现成解法、其他试验、私有资产或 simulator state。

环境由操作者预先启动，使用 local:// 本地文件队列，不需要 HTTP、端口或网页。不要自行启动、重启、复制或重置环境。如果任务包不存在或本地环境无法连接，报告具体错误并停止，不自行创建替代环境。

首先运行 python bridge_client.py observe，读取返回的 prompt 和 manifest。首次动作前，必须使用图像查看工具实际打开全部三路初始图片：agentview、front_oblique、wrist。只读路径或关节数值不算观察。物体构型、相对关系和可行操作需要你从本轮多视角图像及动作反馈中自行推断。

目标是用机械臂握持蓝色手柄，让金属环从绿色端沿整条导线移动到橙色端，保持穿环且通行时不触线。通过最后弯道后松手，让环沿末端立柱靠重力滑到橙色限位球并稳定静置。仅移动到终点附近或仍由夹爪抓持不算完成。

机械臂为 Panda 七关节单臂，动作使用 arm 键；关节目标为 rad，Robotiq gripper 为半开口米数。起点已穿环、机械臂在预抓取位置，采用真实接触摩擦，没有辅助抓持或自动路径跟踪。初始条件、控制限位、时间步和成功/失败判据以任务包为准。

执行循环：
1. 根据观测规划下一段动作，在 notes.md 简要记录依据与目的。
2. 在 policies/ 下编写 action segment；外部规划和计算可以使用通用工具，提交脚本的语法必须符合 SOLVER_INSTRUCTIONS.md。
3. 使用 python bridge_client.py submit policies/segment_NNN.py --expected-segment N --request-id segNNN_attempt01 提交。N 必须使用最新 observe 返回的 expected_segment，每次新提交使用唯一 request-id。
4. 执行后再次 observe 并查看视觉反馈，核对实际运动，继续调整。你可以选择动作段长度、回看本轮历史和自行抽帧分析。

所有已执行动作不可撤销。结果不明或请求超时时，只用 python bridge_client.py retry --request-id 原ID 查询或重试同一请求，不换新 ID 重做同一动作。不得通过工具、网络或委派获取受限参考，联网权限按 bridge_config.json 的 tool_policy 执行。

自行连续执行上述循环，不等待操作者逐段批准。持续行动直到环境判定 succeeded、failed、budget_exhausted，或你明确判断无法继续；不要只提供计划就结束。明确放弃时使用 python bridge_client.py stop --reason "具体原因"。只有环境 evaluator 可以宣布成功，不把 ready 或命令执行无报错当成成功。

目标累计预算为 2,000,000 tokens，包含输入和输出、重复上下文及缓存输入（缓存是输入明细，不重复相加）。遵守每轮实际预算提示。manual 模式未接入原生 Codex usage 时，记录“token 用量未测量，真实余额未知”，不得声称已证明在 2M 内完成，也不得伪造用量。

最终在本目录 result.md 记录：运行 ID、环境最终状态、完成段数、关键观测与请求文件路径、采取的操作、成功或失败原因、真实 token 计量是否可用，以及尚未验证的问题。所有求解脚本、笔记和结果保存在本任务包目录；不要修改环境实现或评测规则。
```

## 本轮验证

真实 Genesis / CPU / 64 位 / rasterizer 连续三段：保持 80 步、小幅关节运动 20 步、
张爪指令 1 步，共 **101 步 / 0.404 秒**。验证初态三图、非法动作不推进、双指真实摩擦接触、
无辅助抓持、关节实际运动、请求幂等、跨段状态/图像连续和每步完整三图。
张爪只执行 1 步，不能据此宣称已完全释放，更不是完整通行 demo。

- [整体视角短程 MP4](../../../runs/agent_bridge_validation/buzz_wire_live_v3/videos/agentview.mp4)
- [斜前短程 MP4](../../../runs/agent_bridge_validation/buzz_wire_live_v3/videos/front_oblique.mp4)
- [腕部短程 MP4](../../../runs/agent_bridge_validation/buzz_wire_live_v3/videos/wrist.mp4)

视频来自同次物理执行的原始 PNG，去除段边界重复帧后每路 102 帧、25 fps、4.08 秒、10 倍慢放。
完整解码、帧数/时长及源图和视频哈希已核对。诊断进程已关闭，诊断包不能作为新求解任务包。
见 [probe 报告](../../../runs/agent_bridge_validation/buzz_wire_live_v3/probe_report.json)、
[来源清单](../../../runs/agent_bridge_validation/buzz_wire_live_v3/video_manifest.json) 和
[验证记录](../../../runs/agent_bridge_validation/buzz_wire_live_v3/validation.md)。

新增 11 项检查，连同公共协议、其他 adapter 和原 Buzz Wire 几何/动力学逻辑检查，共 95 项通过。
包括静态资产哈希、实际导线碰撞几何对应、信息边界、摩擦模式不启用辅助、终点捷径/脱环反例、
触线、非指垫碰撞、末端释放/支撑/速度/静置窗口和被动机械能异常。

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_buzz_wire_agent -v
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m tests.probe_rigid_agent --task buzz_wire_3d --output runs/agent_bridge_validation/buzz_wire_new_probe
```
