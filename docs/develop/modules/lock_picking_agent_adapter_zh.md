# Lock Picking agent adapter

2026-09-19。150 mm 盘距固定标准实例的单臂接入。
任务实现为 [`agent_adapter.py`](../../../topogym/tasks/lock_picking/agent_adapter.py) 和
[`agent_spec.py`](../../../topogym/tasks/lock_picking/agent_spec.py)，复用
[公共 adapter](agent_adapter_architecture_zh.md) 的 Panda 端口、接触辅助和不可回滚执行循环。

## 本版任务和接口

- 固定标准实例，钥匙是 V 形实体支撑上的自由刚体；机械臂从 home 开始，模型自行接近和抓取。
  三个被动锁片只能由钥匙接触带动，固定终点板标有 END。
  不允许机械臂直接拨动锁片、限位结构或固定面板；没有锁片电机、物体位姿或指定附着指令。
- Panda 七关节 + Robotiq 2F-85，动作键 `arm`，`qpos` 为七个关节角 rad，`gripper` 为半开口米数。
  `0.04` 对应总开口 80 mm。每控制步 5 ms、8 个物理子步；位置控制，不瞬移。
- 初始无辅助约束、无隐藏物理推进。钥匙直接与 V 形支撑相切，重力从首次动作开始计算。
  旧 runner 的 0.1 mm 下落／静置不用于此 episode：该下落在无预推进时产生首步冲击，曾触发 10 N 保护。
  本版修改初始化间隙为零，未放宽过载门槛。
- 减小夹爪目标启用抓持尝试，只有双指真实承载接触路径的力 >0.01 N 才附着钥匙；增大目标立即解除。
  这是声明的接触辅助，不能算纯摩擦抓取。首次抓起和全程重新抓持尚需进一步物理验证。
- 初始和每个控制步提供 `agentview / front_oblique / wrist` 三路 640×480 PNG，附实际相机位姿。
  相机外参、投影、腕部安装偏移和机器人参数写入 task spec。初始视野已实际查看；物体构型由模型自主感知。
  不导出物体网格、钥匙真值位姿、锁片角度、孔槽参数、回退顺序、参考图、demo 或轨迹。

```python
# 保持当前控制目标 20 步，0.1 秒；示例不是解法。
env.step({}, steps=20)
# q 是模型自行计算的七关节目标。
env.step({"arm": {"qpos": q, "gripper": 0.04}})
```

目标：从承托架抓起钥匙，操作至 END，松手后稳定保持。
内部判据为尖端到 END 平面轴向误差 ≤3.75 mm、轴线偏移 ≤10 mm、倾角 ≤3°、凸片与槽口匹配，
辅助已解除且机器人与钥匙总接触力 <0.01 N，钥匙线速度 <0.01 m/s、角速度 <0.1 rad/s，连续 0.5 秒。
不要求把钥匙取回或放到桌面。

失败门槛：钥匙／机构总力 >10 N、接触穿透 >2 mm、机器人直接碰机构的总力 >0.01 N，
同轴啮合的凸片／孔槽角度违规 >2°，或掉落、非有限状态、固定基座移动、实际有限转角的锁片越界、持续关节失跟踪。
完整回转的锁片按 continuous joint 处理，不误设 ±180° 截止。
角度几何判据仅在轴线对准时适用，避免把提起／接近阶段误判为穿孔；偏轴动作依赖真实接触判定。
这仍是逐控制步的 pilot evaluator，不是完整六自由度连续碰撞证明。

原场景默认保留既有抛异常保护。bridge 构建时使用 `contact_guard=False`，由 adapter 在每个物理步后
执行上述保护并锁存失败，让 Session 保存触发失败的三路画面；不是关闭过载保护。

本版 `physics_qualified=false`，不继承历史成功视频的资格；尚未接入 F1/F2/F3 或 seed 随机实例。
运行直接使用当前场景配置和生成器，不加载历史解法、轨迹、oracle 或 demo。

## 本地使用

操作者在 `/home/jianwen/topogym` 执行，无需 HTTP、端口或浏览器：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task lock_picking \
  --output runs/agent_test_demos/states/lock_picking_codex_001 \
  --package runs/agent_test_demos/agent_solutions/lock_picking_codex_001 \
  --no-allow-internet
```

两个目录须为新目录。等返回 `Local task ready` 后，只把 `agent_solutions/lock_picking_codex_001/`
交给新求解会话。保持本地仿真子进程存活；关闭后不能恢复同一 episode。
联网可由 operator 改成 `--allow-internet`，其他通用工具仍开放，受限资料禁止通过工具间接获取。
严格隔离由宿主权限／harness 落实；本协议本身不是文件沙箱或防火墙。

预算继续复用公共机制，默认累计目标 2M。manual 模式未接入原生 Codex usage，真实余额未知；
不能据此证明在 2M 内解决。API harness 的真实 usage 计入输入与输出，缓存输入属于输入明细、不重复相加。

## 可直接复制给新 Codex 会话的 prompt

先由操作者创建任务包；运行名变更时替换下面工作目录。
**只复制下面代码块，不把开发文档、验证视频或仓库源码交给受测模型。**

```text
你是 Lock Picking（被动锁片开锁）机器人任务的受测求解 agent。请从本轮观测出发，自行编写动作段，持续尝试完成任务。

你的工作目录是：
/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/lock_picking_codex_001

先进入该目录，读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json 和 bridge_config.json。
只将这个任务包、本轮 bridge 返回的观测和允许的通用知识作为任务输入。不要搜索或读取父目录中的仓库文档、实现源码、demo、参考图、现成解法、其他试验、私有资产或 simulator state。

环境由操作者预先启动，使用 local:// 本地文件队列，不需要 HTTP、端口或网页。不要自行启动、重启、复制或重置环境。如果任务包不存在或本地环境无法连接，报告具体错误并停止，不自行创建替代环境。

首先运行 python bridge_client.py observe，读取返回的 prompt 和 manifest。首次动作前，必须使用图像查看工具实际打开全部三路初始图片：agentview、front_oblique、wrist。只读路径或关节数值不算观察。物体构型、相对关系和可行操作需要你从本轮多视角图像及动作反馈中自行推断。

目标是从承托架抓起钥匙，通过操作钥匙使其穿过三个被动锁片，到达 END 固定终点板，松手并稳定保持。不要用机械臂或夹爪直接拨动锁片和固定机构。机械臂为 Panda 七关节单臂，Robotiq 夹爪动作值为半开口米数；动作使用 arm 键。初始条件、接触辅助规则、控制限位、时间步和成功判据以任务包为准。

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

## 验证范围

真实 Genesis / CPU / 64 位 / rasterizer：连续 80 步保持、20 步关节微动、1 步打开指令，
共 101 步 / 0.505 秒。验证初始三图、home 无错误附着、非法动作零推进、实际关节运动、
请求幂等以及跨段状态和画面连续。未执行抓起、插入或成功后的释放静置；不是完整开锁 demo。
72 项相关自动检查通过，覆盖公共 bridge、本地传输、Panda／ALOHA、开锁几何及释放条件、
公开信息边界、连续转角和不会丢失控制步的过载锁存。

首版带 0.1 mm 下落间隙的失败记录保留于 `lock_live_v1`，首步因过载失败，终态三图仍完整保存。
相切初态在 `lock_live_v2` 通过；最终腕部视野调整后用 `lock_live_v3` 复验。
诊断进程均已关闭，这些目录不能作为新求解任务包。

- [整体视角短程 MP4](../../../runs/agent_bridge_validation/lock_live_v3/videos/agentview.mp4)
- [斜前方短程 MP4](../../../runs/agent_bridge_validation/lock_live_v3/videos/front_oblique.mp4)
- [腕部短程 MP4](../../../runs/agent_bridge_validation/lock_live_v3/videos/wrist.mp4)

三路来自同次实际执行的逐步 PNG，102 帧、20 fps、5.1 秒、10 倍慢放，非重新仿真。
见 [probe 报告](../../../runs/agent_bridge_validation/lock_live_v3/probe_report.json) 和
[视频来源清单](../../../runs/agent_bridge_validation/lock_live_v3/video_manifest.json)。

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_lock_agent tests.check_hedgehog_agent tests.check_lock_picking_geometry tests.check_lock_release_gate -v
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m tests.probe_rigid_agent --task lock_picking --output runs/agent_bridge_validation/lock_new_probe
```
