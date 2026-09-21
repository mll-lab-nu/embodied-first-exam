# Cast Keyhole agent adapter

2026-09-19。固定基础实例的双臂分段接入，使用共享 ALOHA adapter。
实现为 [`agent_adapter.py`](../../../topogym/tasks/cast_keyhole/agent_adapter.py) 与
[`agent_spec.py`](../../../topogym/tasks/cast_keyhole/agent_spec.py)；公共分层见
[adapter 模块说明](agent_adapter_architecture_zh.md)。

## 已实现的任务范围

- 使用 `perpendicular_lower_bore_v1` 基础几何、3 倍尺度，双臂处于抬高的预抓取位置。
  只读取独立的私有 `agent_initial_state.json`，包含固定初态和模板哈希，没有动作、阶段或解题路线。
  不在运行中读取 `robot_motion.json`、demo、规划器或参考解。
- tick=0 无辅助约束、无预推进。手指初始轨位移 0.0127 m，控制目标 0.0105 m，等待物理闭合接触。
  新建辅助须有力超过 0.01 N 的双指承载接触路径；张爪释放，可再次闭爪尝试抓取。
  这是明确声明的辅助机制，不声称纯摩擦夹持或自主桌面拾取。
- 1 ms 控制步、4 子步；每侧 6 个关节目标（rad）和夹爪轨位移（m）。控制为有界关节位置控制。
  实际控制增益、力上限、坐标系和观测字段写入公开 task spec。
- 初始与每控制步保存高位、低位、左腕、右腕四路 PNG。已人工检查基础初态视野。
  任务包直接包含本轮初态，不包含参考图片。每帧同时返回实际相机位姿。
- 目标是两件完全分离并稳定保持，**允许继续由机械臂抓持，不要求落桌释放**。
  内部凸体 SAT 分离下界 >20 mm、两件线速度 <1 mm/s、角速度 <0.02 rad/s，持续 0.5 秒成功。
  两件 SAT 间隙 <−0.5 mm、相关接触穿透 >1 mm、掉落、非有限状态或持续关节跟踪失控会失败。
- SAT 在加载的实际凸碰撞体局部坐标上计算，包含完整实体包含检查。
  每控制步判定，不宣称逐子步连续几何证明。几何和状态真值只用于私有 evaluator。

首版标记 `physics_qualified=false`，不继承历史演示的完整资格。
新的 agent 控制、重新抓持和完整分离保持尚需独立全程验证；不宣称所有生成变体已接入。

## 本地使用

无需 HTTP、端口或浏览器。由 operator 在仓库根目录执行一次本地创建命令，保持仿真子进程存活。
目录必须是新目录；退出后不能恢复该 episode。

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task cast_keyhole \
  --output runs/agent_test_demos/states/cast_keyhole_codex_001 \
  --package runs/agent_test_demos/agent_solutions/cast_keyhole_codex_001 \
  --no-allow-internet
```

只将 `agent_solutions/cast_keyhole_codex_001/` 交给新的求解会话；按包内 `SOLVER_INSTRUCTIONS.md`
先观察四路图片，再使用独立客户端 `observe / submit / retry` 交互。
模型可以用工具推理和计算，但不读仓库、私有环境目录、现有解法或其他试验。

默认 manual 模式不自动取得原生 Codex usage，不能据此证明在 2M tokens 内完成。
接入真实 provider usage 的 metered harness 继续使用公共预算机制，文件传输无需另写计量逻辑。

## 可直接复制给新 Codex 会话的 prompt

先由操作者运行上面的本地创建命令，确认返回 `Local task ready`，再打开新的求解会话。
下面的目录对应示例运行 `cast_keyhole_codex_001`；若使用其他运行名，只替换工作目录。
**只复制下面代码块，不把整份开发文档、验证视频或仓库源码交给受测模型。**

```text
你是 Cast Keyhole 机器人任务的受测求解 agent。请从本轮观测出发，自行编写动作段，持续尝试完成任务。

你的工作目录是：
/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/cast_keyhole_codex_001

先进入该目录，读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json 和 bridge_config.json。
只将这个任务包、本轮 bridge 返回的观测和允许的通用知识作为任务输入。不要搜索或读取父目录中的仓库文档、实现源码、demo、参考图、现成解法、其他试验、私有资产或 simulator state。

环境由操作者预先启动，使用 local:// 本地文件队列，不需要 HTTP、端口或网页。不要自行启动、重启、复制或重置环境。如果任务包不存在或本地环境无法连接，报告具体错误并停止，不自行创建替代环境。

首先运行 python bridge_client.py observe，读取返回的 prompt 和 manifest。首次动作前，必须使用图像查看工具实际打开全部四路初始图片：cam_high、cam_low、cam_left_wrist、cam_right_wrist。只读路径或关节数值不算观察。物体构型、相对关系和可行操作需要你从本轮多视角图像及动作反馈中自行推断。

目标是将金色和银色零件完全分离并稳定保持，允许继续由夹爪抓持，不要求放回桌面。初始条件、辅助抓持规则、控制单位、时间步和成功判据以任务包为准。

执行循环：
1. 根据观测规划下一段动作，在 notes.md 简要记录依据与目的。
2. 在 policies/ 下编写 action segment；外部规划和计算可以使用通用工具，提交脚本的语法必须符合 SOLVER_INSTRUCTIONS.md。
3. 使用 python bridge_client.py submit policies/segment_NNN.py --expected-segment N --request-id segNNN_attempt01 提交。N 必须使用最新 observe 返回的 expected_segment，每次新提交使用唯一 request-id。
4. 执行后再次 observe 并查看视觉反馈，核对实际运动，继续调整。你可以选择动作段长度、回看本轮历史和自行抽帧分析。

所有已执行动作不可撤销。结果不明或请求超时时，只用 python bridge_client.py retry --request-id 原ID 查询或重试同一请求，不换新 ID 重做同一动作。不得通过工具、网络或委派获取受限参考，联网权限按 bridge_config.json 的 tool_policy 执行。

持续行动直到环境判定 succeeded、failed、budget_exhausted，或你明确判断无法继续；不要只提供计划就结束。明确放弃时使用 python bridge_client.py stop --reason "具体原因"。只有环境 evaluator 可以宣布成功，不把 ready 或命令执行无报错当成成功。

目标累计预算为 2,000,000 tokens，包含输入和输出、重复上下文及缓存输入（缓存是输入明细，不重复相加）。遵守每轮实际预算提示。manual 模式未接入原生 Codex usage 时，记录“token 用量未测量，真实余额未知”，不得声称已证明在 2M 内完成，也不得伪造用量。

最终在本目录 result.md 记录：运行 ID、环境最终状态、完成段数、关键观测与请求文件路径、采取的操作、成功或失败原因、真实 token 计量是否可用，以及尚未验证的问题。所有求解脚本、笔记和结果保存在本任务包目录；不要修改环境实现或评测规则。
```

## 本轮验证

真实 Genesis / CPU / 64 位 / rasterizer 连续三段测试：保持 50 步、小幅关节运动 50 步、左手释放 50 步。
第 1 步双侧分别通过真实承载接触并建立辅助；打开左手后右手约束保留。
检查初态、非法动作拒绝、重复请求幂等、每步四图、跨段状态与画面连续；共 150 步 / 0.15 秒。
这是短程接口验证，不是完整解题 demo。诊断进程已关闭，诊断包不可当作新的 solver 任务包。

- [高位短程视频](../../../runs/agent_bridge_validation/keyhole_live_v1/videos/cam_high.mp4)
- [低位短程视频](../../../runs/agent_bridge_validation/keyhole_live_v1/videos/cam_low.mp4)
- [左腕短程视频](../../../runs/agent_bridge_validation/keyhole_live_v1/videos/cam_left_wrist.mp4)
- [右腕短程视频](../../../runs/agent_bridge_validation/keyhole_live_v1/videos/cam_right_wrist.mp4)

视频为同次物理执行的原始逐步图像，以 50 fps 编码、20 倍慢放；不是新的动力学执行。
见 [检查结果](../../../runs/agent_bridge_validation/keyhole_live_v1/probe_report.json) 和
[视频来源清单](../../../runs/agent_bridge_validation/keyhole_live_v1/video_manifest.json)。

复验入口：

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_keyhole_agent tests.check_horseshoe_agent tests.check_agent_local -v
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m tests.probe_rigid_agent --task cast_keyhole --output runs/agent_bridge_validation/keyhole_new_probe
```
