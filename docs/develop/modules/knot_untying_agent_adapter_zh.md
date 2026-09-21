# Knot Untying agent adapter

2026-09-19。固定开放单结实例，ALOHA 双臂、连续 FEM 绳体与 IPC 接触。
实现：[任务 adapter](../../../topogym/tasks/knot_untying/agent_adapter.py)、[公开说明](../../../topogym/tasks/knot_untying/agent_spec.py)、
[公共 FEM 执行层](../../../topogym/agent_bridge/fem_robot_adapter.py)。

## 接入范围

- 复用公共 Session、本地文件队列、任务包、动作预检查、请求幂等、多视角存档及预算机制。
  FEM 抓持单独放在 `FEMRobotAdapter / RopeGraspBank`，不将软绳当作刚体焊接。
- 固定基础绳形，两端自由、直绳材料参考态；双臂从张爪 home 开始，无隐藏静置或初始附着。
  使用既有 `external_articulation` 轴向兼容层，机械臂通过位置目标受力运动。
  不读取 demo 的抓点、动作、轨迹或准备位；当前不接入其他结型或随机变体。
- 动作与其他 ALOHA adapter 一致：`left / right`，每侧六关节 rad，夹爪为单指轨位移 m。
  `0.037` 是张开目标；不是 Panda 的半开口。5 ms 控制步，4 个 IPC 子步。
- 初始及每控制步保存四路 `cam_high / cam_low / cam_left_wrist / cam_right_wrist`；默认 640×360。
  task spec 提供机器人、单位、相机标定，观测提供对应的实际外参与本体状态。
  不公开绳节点／中心线／材料索引／交叉点／参考图／结型答案／解结路线。

### 自行选择抓点

沿初始材料曲线每约 6 mm 声明一个半径 8 mm 的局部软约束带，全部初始关闭。
这覆盖整根绳，不预选 demo 使用的抓点。模型减小夹爪目标后，环境根据当前实际手位选择附近候选；
只有两侧原生 IPC 指垫表面到同一带表面的距离均 ≤0.801 mm，才能启用该带。
距离使用独立表面特征检查，不把“顶点近邻”或“只有一指接触”当作双指接触；不宣称测得抓持力。

每手最多一带，不允许两手同时约束重叠顶点。接触后保持实测指间距，软位置目标随实测手部位姿更新；
不直接写绳的位置或速度。动作段重复闭爪命令时仍保持附着时的实测指间距，避免继续挤压；增大开口目标解除该手辅助，可以再抓。
这是明确的辅助机制，不是纯摩擦抓持。动态选带、双手交接和全程解结仍需物理验证。
公共 IPC 动画回调先清除约束容量再写入活跃带，防止未激活的重叠候选抹掉有效抓持。

### 成功和失败

目标为解开、落桌、双手松开并撤离后稳定保持。
内部采用保守的平面展开判据：整绳在桌面水平范围内、节点在桌面上方 12 mm 内；
XY 中心线无交叉，投影弧长间隔 >24 mm 的非局部线段间距 >8 mm，防止平行重叠漏判。
双手无辅助，指垫与绳的世界包围盒间隔 >0.8 mm；原生速度 RMS <1 mm/s、最大 <5 mm/s，
连续 2 秒且节点最大漂移 <2 mm。
这不是一般结型的拓扑不变量，部分已解开的立体弯曲形状仍需放平才能通过。

失败包括 FEM 倒置／体积比 ≤0.2、非有限状态、独立自接触或 FEM/刚体 CCD 拒绝、
桌面穿透 >0.05 mm、总长变化 >5%、局部轴向应变 >20%、刚体穿透 >0.5 mm、实际关节超限、
原生与可视机器人表面偏差 >2 mm、辅助跟随误差 >2 mm，或持续关节失跟踪。
原生 FEM 位置和速度由 libuipc accessor 读取，避免误用陈旧的 Genesis FEM 速度缓存。

CCD 逐 IPC 子步检查，失败锁存到当前控制步末尾，保存视觉反馈；底层崩溃或严重后端异常仍可能留下不完整动作段。
初版 `physics_qualified=false`，不继承历史 demo 的全程资格，也不宣称完整 Newton 收敛或网格收敛认证。

## 本地创建

**必须有可用 CUDA 显卡和足够空闲显存；CPU 不能替代 FEM/IPC。**
无需 HTTP、端口或浏览器。由操作者在仓库根目录运行：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task knot_untying --backend cuda \
  --output runs/agent_test_demos/states/knot_untying_codex_001 \
  --package runs/agent_test_demos/agent_solutions/knot_untying_codex_001 \
  --no-allow-internet
```

目录必须是新目录，等返回 `Local task ready` 后才把 solver 目录交给新会话。
初态与动作反馈均来自这个常驻进程；关闭后不能恢复该 episode。启动失败时保留日志，下一次使用新的目录。
联网开关也可由 operator 选 `--allow-internet`；其他通用工具开放，但受限参考仍禁止读取。
原生 Codex manual 模式没有自动取得真实 token usage，余额未知；API harness 继续复用真实 usage 计量。
累计目标 2M，缓存输入已经包含在输入总量中，不重复相加。

## 可直接复制给新 Codex 会话的 prompt

先确认本地环境 ready。只复制下面代码块，不把开发文档、验证材料或历史视频给受测模型。

```text
你是 Knot Untying（解绳结） 机器人任务的受测求解 agent。请从本轮观测出发，自行编写动作段，持续尝试完成任务。

你的工作目录是：
/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/knot_untying_codex_001

先进入该目录，读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json 和 bridge_config.json。
只将这个任务包、本轮 bridge 返回的观测和允许的通用知识作为任务输入。不要搜索或读取父目录中的仓库文档、实现源码、demo、参考图、现成解法、其他试验、私有资产或 simulator state。

环境由操作者预先启动，使用 local:// 本地文件队列，不需要 HTTP、端口或网页。不要自行启动、重启、复制或重置环境。如果任务包不存在或本地环境无法连接，报告具体错误并停止，不自行创建替代环境。

首先运行 python bridge_client.py observe，读取返回的 prompt 和 manifest。首次动作前，必须使用图像查看工具实际打开全部四路初始图片：cam_high、cam_low、cam_left_wrist、cam_right_wrist。只读路径或关节数值不算观察。物体构型、相对关系和可行操作需要你从本轮多视角图像及动作反馈中自行推断。

目标是解开桌上的单根绳结，把整根绳放回桌面，双手松开并撤离后稳定保持。不得切断、穿透或删除绳索。初始条件、辅助抓持规则、控制单位、时间步和成功判据以任务包为准。

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

## 验证记录

复验入口（必须使用新目录）：

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_knot_agent tests.check_knot_robot_control tests.check_knot_physics -v
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  -m tests.probe_knot_agent --output runs/agent_bridge_validation/knot_new_probe
```

首个启动检查 `knot_live_v1` 因 CUDA 内存分配失败停在 tick=0，未产生初始图像或可用任务包。
[失败状态](../../../runs/agent_bridge_validation/knot_live_v1/episode/session.json) 与
[worker 日志](../../../runs/agent_bridge_validation/knot_live_v1/episode.ipc/worker.log) 已保留。

相关自动检查共 **64 项通过**（36 项 FEM／机器人／判据检查，28 项公共 bridge／本地协议检查）；
新增独立进程心跳的本地回归也已通过。这个数量不包含真实 FEM 仿真通过。

`knot_live_v2` 首次原生编译阻塞 Python 线程心跳，被客户端误判停止；已将本地心跳移到独立轻量进程，
其读取 worker 的 PID 和进程启动时间，跨 PID namespace 的客户端仍通过共享文件检测。
`knot_live_v3` 在 IPC 初始化时出现 `cudaErrorInvalidDevice` 并中止，根因尚未确认。
最后复查 GPU 空闲显存约 3.7 GB；不能把该错误直接认定为显存不足，也没有降低物理门槛或替换后端绕过。

**当前状态：代码接入和离线检查完成，真实四图／分段物理验收未通过；尚无可交给 solver 的本轮 ready 任务包。**
上述创建命令是后续复验入口，需先解决原生初始化错误。此轮没有生成新的物理视频，
没有执行抓绳／解结，也没有验证两只手的动态选带实效或 2M 内任务成功。

- [第二次启动日志](../../../runs/agent_bridge_validation/knot_live_v2/episode.ipc/worker.log)
- [第三次启动日志](../../../runs/agent_bridge_validation/knot_live_v3/episode.ipc/worker.log)
- [本轮验证汇总](../../../runs/agent_bridge_validation/knot_adapter_review_v1/validation.json)

以下仅是**历史 v9 完整环境视频**，不是本轮 adapter 的验证产物，不能给受测 solver 看：

- [历史高位 MP4](../../../demos/knot_untying/cam_high/2026-09-17_bounded_spread_trefoil_v9_cam_high.mp4)
- [历史低位 MP4](../../../demos/knot_untying/cam_low/2026-09-17_bounded_spread_trefoil_v9_cam_low.mp4)
- [历史左腕 MP4](../../../demos/knot_untying/cam_left_wrist/2026-09-17_bounded_spread_trefoil_v9_cam_left_wrist.mp4)
- [历史右腕 MP4](../../../demos/knot_untying/cam_right_wrist/2026-09-17_bounded_spread_trefoil_v9_cam_right_wrist.mp4)
