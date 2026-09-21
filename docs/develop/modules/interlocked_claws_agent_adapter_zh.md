# Interlocked Claws 基础变体 agent adapter

2026-09-21。接入固定基础实例 `cspace_claw_wang_v1`。新建任务包采用 spec v5 / `pilot_claw_separation_v2`；旧包及历史结果保持其原判据，不追溯改写。任务实现为
[`agent_adapter.py`](../../../topogym/tasks/interlocked_claws/agent_adapter.py) 和
[`agent_spec.py`](../../../topogym/tasks/interlocked_claws/agent_spec.py)，复用
[`AlohaRigidAdapter / RigidRobotAdapter`](../../../topogym/agent_bridge/robot_adapter.py)。
关节控制、动作校验、抓持辅助、稳定窗口、本地文件传输、预算和存档均沿用公共模块；
任务侧只提供配置、初始化和私有判定。见 [公共模块分层](agent_adapter_architecture_zh.md)。

## 初态、控制与信息边界

- 保留基础版的原始非凸网格、固定放置支架及 20 mm 机器人垫座；不加载随机变体。
  私有静态 `reference_scene.json` 保存几何、FK 和初态，校验整个文件及原 OBJ 的哈希。
  初始化和运行不读取 `recorded_motion.json`、参考动作、既有 demo 或规划结果。
- 双手分别辅助预抓持橙色和青蓝色零件。tick=0 已有明确声明的双侧辅助约束、未推进物理。
  不声称自主接近、首次抓取或纯摩擦夹持。
- ALOHA 2 双臂，每侧六个关节目标（rad）和单根手指轨位移（m），不是 Panda 的半开口单位。
  控制步长 2 ms、每步四个物理子步，沿用基础物理配置的有界位置控制及原电机力上限。
  当前关节和夹爪值读 `observation.robot`；通用 `home_qpos` 不是初态。
- 增大某手夹爪目标立即解除该手辅助；减小目标启用重新抓持尝试。
  只有接触力 >0.01 N 的双指简单承载路径上的零件才能新建辅助，固定支架不能附着。
  重新抓持逻辑来自公共模块，本 adapter 的完整重新抓持过程尚未物理验证。
- 初始及每个执行步保存 `cam_high / cam_low / cam_left_wrist / cam_right_wrist` 四路 PNG。
  高位和斜前固定相机针对较高的悬空互锁件调整，初态两件和支架可见；腕部保留标准安装位，
  提供局部抓持近景。公开投影和安装参数，每帧返回实际相机位姿。
- 公开信息限于任务说明、机器人/相机知识、本体状态、辅助状态及本轮 RGB。
  不提供参考图、物体网格、真值位姿、目标误差、退出路线或其他运行记录。

```python
# 保持当前双臂目标 20 步，即 0.04 秒；只是语法示例，不是解法。
env.step({}, steps=20)
```

成功要求两件世界 AABB 至少一轴间隔 >20 mm，线速度各 <5 mm/s、角速度各
<0.05 rad/s，连续满足 1 秒。**允许继续抓持，不要求搬运、落架或松爪。**
AABB 是明确的保守分离门槛，不要求模型对齐隐藏的目标位姿或复现参考轨迹。

每个控制步检查引擎接触及原三角网格：两件三角接触深度 >0.15 mm、完整包含，或谜题相关、
机器人自碰撞/桌面/支架/垫座接触穿透 >1 mm 会失败；另检查掉落、非有限状态、固定支架位姿，
以及持续关节跟踪失控。失败锁存。三角深度是局部诊断，不是精确体积穿透距离，
不宣称逐物理子步或连续路径证明。

本版为 `physics_qualified=false`。原任务的独立非凸接触可靠性对照仍未通过，已有参考执行
不能转移为本 adapter 任意动作的物理资格。完整自主分离和随机变体尚未验证。

## 本地创建任务包

由操作者在 `/home/jianwen/topogym` 执行，无需 HTTP、端口或浏览器：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task interlocked_claws \
  --output runs/agent_test_demos/states/claws_codex_001 \
  --package runs/agent_test_demos/agent_solutions/claws_codex_001 \
  --no-allow-internet
```

两个目录必须均未存在；等待 `Local task ready` 后，只把 `agent_solutions/claws_codex_001/`
交给新的求解会话。环境子进程需保持存活，退出后不能恢复同一个 episode。若宿主会清理
后台进程，由 operator 在稳定本机终端创建。联网开关只约束 solver 的外网工具使用，
不控制模型服务通信，也不是文件系统或网络的强制隔离。

默认 manual 模式不会自动采集原生 Codex usage：真实余额未知，不能宣称通过严格 2M 验收。
API metered harness 继续复用公共预算机制，累计输入＋输出，缓存输入不重复相加。

## 可直接复制给新 Codex 会话的 prompt

先创建环境与任务包。**只复制下面代码块，不把整份开发文档、验证视频或仓库源码交给受测模型。**
改运行名时同步替换工作目录。

```text
你是 Interlocked Claws 基础变体机器人任务的受测求解 agent。请从本轮观测出发，自行编写动作段，持续尝试完成任务。

你的工作目录是：
/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/claws_codex_001

先进入该目录，读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json 和 bridge_config.json。
只将这个任务包、本轮 bridge 返回的观测和允许的通用知识作为任务输入。不要搜索或读取父目录中的仓库文档、实现源码、demo、参考图、现成解法、其他试验、私有资产或 simulator state。

环境由操作者预先启动，使用 local:// 本地文件队列，不需要 HTTP、端口或网页。不要自行启动、重启、复制或重置环境。如果任务包不存在或本地环境无法连接，报告具体错误并停止，不自行创建替代环境。

首先运行 python bridge_client.py observe，读取返回的 prompt 和 manifest。首次动作前，必须使用图像查看工具实际打开全部四路初始图片：cam_high、cam_low、cam_left_wrist、cam_right_wrist。只读路径或关节数值不算观察。物体构型、相对关系和可行操作需要你从本轮多视角图像及动作反馈中自行推断。

目标是将橙色和青蓝色互锁件完全分离并短暂停稳。允许继续抓持，不要求搬运、落架或松爪。机械臂为 ALOHA 2 双臂，每侧六个关节目标为 rad，夹爪值为单根手指轨位移米数。初始为明确声明的双手辅助预抓持，初态、抓持规则、限位、时间步和成功判据以任务包为准；已有旧版本任务包遵守包内原判据。

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

## 验证与视频

真实 Genesis / CPU / 64 位 / rasterizer 共三段：保持 50 步、小幅关节运动 50 步、
打开左手并执行 1 步，共 **101 步 / 0.202 秒**。检查四路 tick=0 初态、非法动作不推进、
请求幂等、跨段状态与图像连续、真实关节运动和左手辅助解除后右手保持。
释放只执行 1 步，**不代表夹爪已完全张开，也不是完整拆解落架 demo**。诊断进程已关闭，
诊断包不能作为新的求解任务包。`claws_live_v1` 是默认相机裁切问题的历史诊断，修正后使用 v2。

- [高位短程 MP4](../../../runs/agent_bridge_validation/claws_live_v2/videos/cam_high.mp4)
- [斜前短程 MP4](../../../runs/agent_bridge_validation/claws_live_v2/videos/cam_low.mp4)
- [左腕短程 MP4](../../../runs/agent_bridge_validation/claws_live_v2/videos/cam_left_wrist.mp4)
- [右腕短程 MP4](../../../runs/agent_bridge_validation/claws_live_v2/videos/cam_right_wrist.mp4)

四路均为同次物理执行的原始逐步图像，去除段边界重复帧后 102 帧，50 fps、2.04 秒、10 倍慢放。
完整解码、同步时长/帧数及每张源图片 SHA-256 已核对；不涉及新动力学执行。
见 [probe 报告](../../../runs/agent_bridge_validation/claws_live_v2/probe_report.json)、
[视频来源清单](../../../runs/agent_bridge_validation/claws_live_v2/video_manifest.json) 和
[验证记录](../../../runs/agent_bridge_validation/claws_live_v2/validation.md)。

Claws 的 8 项检查与既有任务、公共协议检查合计 67 项通过。覆盖静态初态校验、信息边界、
双臂动作、原网格相交/包含、双件释放、支架支撑方向、速度与连续窗口、失败锁存。
其中 6 项 HTTP 检查需要本机临时端口；与不依赖 socket 的本地接入是独立验证路径。

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_claws_agent -v
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m tests.probe_rigid_agent --task interlocked_claws --output runs/agent_bridge_validation/claws_new_probe
```
