# Hedgehog in Cage agent adapter

2026-09-19。CLASSIC wood 固定基础实例的单臂分段接入。
实现为 [`agent_adapter.py`](../../../topogym/tasks/hedgehog_in_cage/agent_adapter.py) 与
[`agent_spec.py`](../../../topogym/tasks/hedgehog_in_cage/agent_spec.py)，复用
[公共 adapter](agent_adapter_architecture_zh.md) 的执行、抓持生命周期、观测存档和传输。

## 本版范围

- 固定 CLASSIC wood 基础几何、3 倍尺度、固定笼体和支架；从声明的预抓取位置开始。
  独立私有 `agent_initial_state.json` 只保存初始化参数、初始关节和模板哈希。
  运行不读取历史 demo、动作轨迹或规划器；不包含从远处自主接近的考核。
  本版尚未接入生成器 v2 的随机实例和其他家族。
- 单臂 **Franka Panda 7DOF + Robotiq 2F-85**，位置控制，每步 5 ms、10 个内部物理子步。
  初始无辅助约束、无隐藏预推进。夹爪以名义半开口 5.4 mm 初始化、闭合目标 4.4 mm；
  实测开口由观测给出。只有实际双指承载接触路径的力 >0.01 N，才建立辅助抓持。
  增大开口目标立即解除辅助，减小目标重新启用抓取尝试；这是接触辅助，不是纯摩擦抓持。
- 三路 `agentview / front_oblique / wrist`，默认各 640×480。
  任务包包含本轮 tick=0 的全部三图；每个控制步也保存三图及对应实际相机位姿。
  初态整体视角有机械臂遮挡，斜前方补充笼体全景，腕部提供刺球和笼条近景；已实际打开检查。
- 公开机械臂关节顺序／限位／控制参数、坐标系、夹爪单位、相机标定与腕部安装偏移、机器人本体状态。
  物体构型由模型从实时图片判断；不提供参考图、物体网格、真值位姿、退出路线或目标误差。

动作格式：

```python
# 保持现有目标 20 个控制步，即 0.1 秒。
env.step({}, steps=20)

# q 为模型自行选择的七个关节目标，单位 rad。
# gripper 是半开口米数；0.04 对应总开口 80 mm，不是 ALOHA 的指轨位移。
env.step({"arm": {"qpos": q, "gripper": 0.04}})
```

未提供的字段保留原目标；实际运动经物理控制器执行。不要把通用 home 当作当前关节状态，
应读 `obs["robot"]["arm"]["arm_qpos"]`。示例只说明接口，不是推荐求解动作。

目标是**取出刺球，放到桌面并松手稳定静置**。私有 evaluator 要求：刺球与笼体世界 AABB
至少一轴间隔 >5 mm；刺球全体处于桌面水平范围内、辅助已解除、桌面承载 >0.01 N，
其他接触均不超过 0.001 N；线速度 <1 mm/s、角速度 <0.5°/s，连续 2 秒且漂移 ≤0.2 mm。
仍被夹持或刚取出悬空不算成功。

失败包括：刺球／笼体或机器人／固定物穿透 >0.15 mm；其余刺球接触或机器人自碰穿透 >1 mm；
掉落、非有限状态、固定笼位姿改变，或关节跟踪误差 >0.2 rad 持续超过 0.2 秒。
判定逐控制步运行，失败锁存；不宣称逐物理子步的连续几何证明。
本版为 `physics_qualified=false` 的接入试验版，完整取出、重新抓持及任意动作尚需独立验证。

## 本地创建任务包

由操作者在 `/home/jianwen/topogym` 运行；无需 HTTP、端口或浏览器：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task hedgehog_in_cage \
  --output runs/agent_test_demos/states/hedgehog_codex_001 \
  --package runs/agent_test_demos/agent_solutions/hedgehog_codex_001 \
  --no-allow-internet
```

这是创建新 episode 的命令，两个目录均须未存在。等待 `Local task ready` 后，只将
`agent_solutions/hedgehog_codex_001/` 交给求解会话。常驻子进程通过本地文件队列执行；
求解期间保持它存活，停止后不能恢复或重置同一 episode。后续重试改用新的运行目录。
联网开关由 operator 选择 `--allow-internet` 或 `--no-allow-internet`；其余通用工具开放，
不得借工具获取受限参考。当前是遵循协议的 pilot，严格隔离还需宿主文件权限和 harness 落实。

默认 manual 模式与既有 adapter 一致：累计目标 2,000,000 tokens，但不自动获得原生 Codex usage。
未计量时余额未知，不能宣称证明在 2M 内完成。API harness 的真实 usage 仍通过公共预算机制累计；
输入含重复上下文和缓存输入，缓存是输入明细、不重复相加。传输方式不改变计量规则。

## 可直接复制给新 Codex 会话的 prompt

先由操作者创建任务包。**只复制下面代码块，不把整份开发文档、验证视频或仓库源码交给受测模型。**
如果运行名不同，替换工作目录。

```text
你是 Hedgehog in Cage（刺球出笼）机器人任务的受测求解 agent。请从本轮观测出发，自行编写动作段，持续尝试完成任务。

你的工作目录是：
/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/hedgehog_codex_001

先进入该目录，读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json 和 bridge_config.json。
只将这个任务包、本轮 bridge 返回的观测和允许的通用知识作为任务输入。不要搜索或读取父目录中的仓库文档、实现源码、demo、参考图、现成解法、其他试验、私有资产或 simulator state。

环境由操作者预先启动，使用 local:// 本地文件队列，不需要 HTTP、端口或网页。不要自行启动、重启、复制或重置环境。如果任务包不存在或本地环境无法连接，报告具体错误并停止，不自行创建替代环境。

首先运行 python bridge_client.py observe，读取返回的 prompt 和 manifest。首次动作前，必须使用图像查看工具实际打开全部三路初始图片：agentview、front_oblique、wrist。只读路径或关节数值不算观察。物体构型、相对关系和可行操作需要你从本轮多视角图像及动作反馈中自行推断。

目标是将刺球从固定笼体中完整取出，放到桌面，松开并稳定静置。机械臂为 Panda 七关节单臂，Robotiq 夹爪动作值为半开口米数；动作使用 arm 键。初始条件、接触辅助规则、控制限位、时间步和成功判据以任务包为准。

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

## 验证范围和视频

真实 Genesis / CPU / 64 位 / rasterizer 三段检查：保持 80 步、关节小幅运动 20 步、
发出打开夹爪指令并执行 1 步，共 **101 步 / 0.505 秒**。验证了真实双指接触后附着、关节实际运动、
打开命令解除辅助、非法动作无推进、请求幂等、跨段状态与图像连续、每步完整三图。
最后一段只验证辅助解除，不代表夹爪已完全张开、刺球已取出或已落桌。
这些诊断进程已关闭；诊断包不能用作新的求解任务包。

- [整体视角短程 MP4](../../../runs/agent_bridge_validation/hedgehog_live_v1/videos/agentview.mp4)
- [斜前方短程 MP4](../../../runs/agent_bridge_validation/hedgehog_live_v1/videos/front_oblique.mp4)
- [腕部短程 MP4](../../../runs/agent_bridge_validation/hedgehog_live_v1/videos/wrist.mp4)

三路均为同次物理执行的原始图像，102 帧、20 fps、5.1 秒、**10 倍慢放**，完整解码和逐帧来源哈希已核对。
见 [probe 报告](../../../runs/agent_bridge_validation/hedgehog_live_v1/probe_report.json) 与
[视频清单](../../../runs/agent_bridge_validation/hedgehog_live_v1/video_manifest.json)。
公共模块扩展后，Keyhole 的 150 步双臂物理回归也通过，
[回归记录](../../../runs/agent_bridge_validation/keyhole_single_arm_refactor_v1/probe_report.json)。

离线检查覆盖 Panda 单位／限位、三图要求、无隐藏步进、公开信息边界、释放／桌面承载、
静置窗口／漂移反例、碰撞与固定笼异常；连同已有 bridge、ALOHA 和抓持回归共 57 项通过。
这些检查不替代完整求解和全程物理验证。

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_hedgehog_agent -v
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m tests.probe_rigid_agent --task hedgehog_in_cage --output runs/agent_bridge_validation/hedgehog_new_probe
```
