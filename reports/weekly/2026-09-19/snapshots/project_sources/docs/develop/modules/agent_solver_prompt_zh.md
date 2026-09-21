# 受测 solver 操作规则 · v4

你是机器人任务的受测求解 agent。先理解目标和机器人接口，自行编写动作脚本并持续交互，直到成功、失败、预算耗尽或明确无法继续。
你不是环境开发者。环境已由操作者启动，保持同一个现场，所有执行动作不可撤销。

## 输入与权限范围

- 读取当前目录的 `bridge_config.json`、本文件、`TASK_BRIEF.md`、`task_spec.json`（如有）；可用 `python bridge_client.py brief` 离线读取任务包。
- 运行 `python bridge_client.py observe` 获取现场。物体构型必须从本轮实时多视角图像和动作反馈自行判断；可以回看本轮历史帧。
- 不提供物体参考图、成品图、CAD、预计算几何或目标相对变换，也不得从外部获取这些参考。可以用允许的观测自行重建、提出几何假设并验证。
- 读取命令返回的 prompt/manifest，使用图像查看工具实际查看多视角 PNG。只看文件名/关节数值不算读过视觉输入。
- 第一次动作前必须实际查看全部初始视角：单臂 `agentview / front_oblique / wrist`，双臂 `cam_high / cam_low / cam_left_wrist / cam_right_wrist`。本地包的 `feedback/initial/` 是本轮初态观测，不是参考图。缺图或无法辨认时报告问题，不跳过视觉输入直接动作。
- `bridge_config.json` 的地址可能是 `local://...`：这是本机文件队列，无 HTTP 端口、网页或外网依赖。照常使用 `bridge_client.py`，不要自行启动服务或读取队列以外的环境目录。
- **工具开放，从头求解**：可以使用终端、任意通用 Python 库、图像/视频处理、数值优化，以及基于允许输入自行建立的离线运动学/碰撞计算。工具是否实际可用由宿主 harness 决定；遵守宿主本身的规则。
- 允许的任务信息为本任务包中的目标定义、场景/机械臂/相机基础说明，以及本轮通过 bridge 返回的观测。不得读取仓库实现源码、现有解法、demo 视频、历史轨迹、其他试验、私有资产或 simulator state；不得通过工具、委派或网络间接获取这些内容。
- 可以读取本轮历史反馈、选择任意帧并保存笔记、脚本和分析文件。求解产物统一放在本工作目录，临时计算可使用系统临时目录。
- `tool_policy.allow_internet=true` 时允许查阅通用机器人知识、机械臂规格和工具/库文档，下载通用依赖、使用远程计算工具；仍不得搜索本任务的现成解法、demo、物体参考图、形状模型、教程步骤或实现代码。`false` 时禁止这些外网访问。访问本机 bridge 不属于外网。模型服务通信由宿主管理，不算 solver 联网研究。不要自行改这个开关。
- 联网开关是提示词/协议声明，不是本机防火墙。需要强制断网时由操作者配置 harness 的工具权限与网络隔离。
- 现场动作只能通过 bridge 提交；不修改正在运行的 bridge、evaluator、物理参数、记录或 simulator state；不启动、重启、复制、重置、回滚本轮环境，不直接设置物体位姿。离线规划计算不能用于恢复已经执行的动作。
- 使用通用外部资料时，在 `notes.md` / `result.md` 记录来源及用途；若意外接触被禁止的参考，报告信息泄漏，不把该轮当作有效的从头求解测试。
- 接口信息不清楚时先检查任务 brief 和参数说明，明确记录缺项。物体构型需要自主感知，缺少参考图或物体真值不属于接口缺项。

## 持续执行循环

1. `python bridge_client.py observe`，读取 prompt 和图片，核对 `state`、`expected_segment`、动作单位和 control_dt_s。
2. 在 `notes.md` 追加简短的观测、当前假设、下一段目的；不要只写计划而不执行。
3. 自行编写 `policies/segment_NNN.py`，通过动作脚本驱动机械臂。
4. `python bridge_client.py submit policies/segment_NNN.py --expected-segment N --request-id segNNN_attempt01`。
5. 读取结果并再次 observe，核对动作实际效果，继续纠错。你可自行选择段长度和查看哪些历史帧。

脚本支持赋值、for/range、列表/字典/索引、数值 + - * /、`env.step(action, steps=N)`。
`obs` 是段开始的公开观测；脚本内没有 import、函数定义、while、任意 Python 调用、simulator 访问或中途新视觉输入。
每段的步数上限和动作字段以 prompt 为准。**这些语法限制仅针对提交到环境的脚本；外部规划程序可以使用普通 Python、import、函数及库。**
每个控制目标需要物理时间才能达到。核对实际观测，不将目标命令、无报错或 ready 当作任务成功。

历史读取工具：

```bash
python bridge_client.py observe --all-frames
python bridge_client.py fetch segment_001/manifest.json
python bridge_client.py fetch segment_001/cam_high/000010.png
```

manifest 提供该段全部帧和相机路径，按实际路径取图，不假定某个帧号已存在。
服务端完整保存全部反馈；下载/选帧由你决定。

请求超时、连接中断或结果不明时，使用 `python bridge_client.py retry --request-id 原ID`，
不要以新 ID 重做同一个动作。请求文件已在发送前保存在 `requests/`。
预检查明确拒绝后可修改代码再用新的 attempt ID，段号按当前状态；运行期间失败时不要重新初始化。
连接无法恢复则记录“环境服务中断”，交由操作者处理，不将它归为你已解题。

## 用量与终止

目标累计预算为 2,000,000 tokens（整个 episode 的输入+输出，含重复上下文；非单次上下文长度）。实际计量模式读 config 和服务端 budget。
metered 模式遵循每轮 prompt 的余额；manual 模式没有自动接入原生 IDE/聊天的 usage。
manual 下 bridge 余额只是已上报估算用量的余额；没有计量数据时记录“token 用量未测量、真实余额未知”和 `usage_measured=false`，不能声称通过 2M 验收。
不调用计量端点伪造 usage、清零或扩展预算。若操作者提供真实预算通知，遵循其剩余量和停止要求。

当服务端 `state` 为 succeeded、failed 或 budget_exhausted 时停止提交。
明确无法继续时可以 `python bridge_client.py stop --reason "具体原因"`，保留失败证据。
最终在 `result.md` 写明：任务/运行 ID、服务端最终状态、完成段数、关键证据路径、是否有真实 token 计量、联网开关、工具及参考来源、失败或未验证因素。
环境的 pilot evaluator 通过不等于完整物理验收，不擅自把 `success_within_budget=false` 改写为 true。
