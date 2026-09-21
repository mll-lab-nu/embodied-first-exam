# Horseshoe Ring agent adapter 与无 HTTP 本地接入

2026-09-19。接入 `tutorial_solvable_v3` 固定基础实例。实现为
[`agent_adapter.py`](../../../topogym/tasks/horseshoe_ring/agent_adapter.py)、
[`agent_spec.py`](../../../topogym/tasks/horseshoe_ring/agent_spec.py)。
这是 agent 接入试验版，不是任意动作、变体或纯摩擦抓持的正式资格证明。

2026-09-19：关节执行、辅助抓持和稳定窗口已迁入公共 `agent_bridge/robot_adapter.py`，
与 Cast Keyhole 共用；任务侧保留建场和判定。见 [模块分层](agent_adapter_architecture_zh.md)。
拆分后另一次三段 / 150 步真实物理回归通过，见
[本轮报告和四路 MP4](../../../runs/agent_bridge_validation/horseshoe_shared_runtime_v1/validation.md)。

## 本地进程为何仍需常驻

HTTP、浏览器、端口和外网都不是环境交互的必要条件。新增
[`local.py`](../../../topogym/agent_bridge/local.py) 在本机启动一个常驻仿真子进程；
solver 的 `observe / submit / retry / stop` 使用文件请求队列，与 HTTP 版共用同一个
`Session`、动作验证、逐帧存档、幂等和预算逻辑。只有该进程拥有 simulator。

该进程必须在整个 episode 中持续存在，否则不能保留不可回滚的真实现场。
进程退出、崩溃或宿主清理后台任务后，本轮不能恢复。每次新试验使用新目录；
读取历史文件不等于继续仿真。心跳线程只更新进程存活信息，不推进物理，
支持 solver 工具与 operator 处于不同 PID namespace、但共享同一文件系统的情况。
正常退出立即标记 stopped，非正常退出最多约 60 秒后判定心跳失效。
本地文件通道是同机可信 operator/solver 的传输方式，不是文件系统权限隔离；
受测模型仍不得读取仓库源码、私有资产或环境目录。

## Operator 一次创建环境和干净任务包

在仓库根目录执行一个本地命令即可；不需要先启 HTTP 服务或网页。
目录名仅为新运行示例，不能覆盖已存在目录。

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m topogym.agent_bridge.local --task horseshoe_ring \
  --output runs/agent_test_demos/states/horseshoe_codex_001 \
  --package runs/agent_test_demos/agent_solutions/horseshoe_codex_001 \
  --no-allow-internet
```

默认 CPU / rasterizer，首次建场可能需要编译。已有可用 GPU/Nyx 时可显式选择
`--backend cuda --renderer nyx`，这条组合需在对应机器验证。
联网开关仅声明 solver 是否可使用外网通用资料，不控制模型服务通信，也不是防火墙。

命令成功返回后，只把 `agent_solutions/horseshoe_codex_001/` 交给新 solver。
包内含独立客户端、操作规则、任务说明、相机/动作规格，以及本轮 `feedback/initial/`
四张 PNG 和带哈希的 manifest。它们是实时初态观测，未附参考图、demo、源码或轨迹。
`bridge_config.json` 中的 `local://...` 由客户端自动处理，不要改成 HTTP 地址。
若宿主会清理命令的后台进程，应让 operator 在稳定的本机终端运行这条命令。

可以把下面这段话交给 solver：

> 工作目录为这个任务包。读取 SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md 和 task_spec.json，
> 执行 python bridge_client.py observe，实际打开四路初始 PNG 后再做第一次动作。
> 只使用本轮任务说明与观测，自行编写动作段持续尝试取环；遵循不可回滚和信息访问规则。
> 不启动或重启环境，不读已有 demo、源码、解法、私有资产或其他试验。
> 结果写入 result.md，manual 模式不得把未计量的用量写成通过 2M token 验收。

目前原生 Codex 是客户端下载图片后由图像工具读取；prompt 明确要求首动作前看全四路，
但文件传输本身不能证明模型实际看过。自带 API harness 会将全部初始图片作为视觉内容附到首次请求。
manual 模式继续显示真实 token 余额未知；严格 2M 计量需要接入 provider usage 的 metered harness。
无 HTTP 不影响这套计量，也不会自动提供原生 Codex 的 usage。

测试结束后，operator 可关闭常驻进程：

```bash
.venv-gs121-nyx/bin/python -m topogym.agent_bridge.local \
  --stop runs/agent_test_demos/agent_solutions/horseshoe_codex_001
```

## 初态、动作和判定

- 双手分别预抓一只马蹄件，初始辅助约束明确声明。目标环与链节为自由受力刚体。
  仅初始化时设置位姿，运行时无物体位姿赋值、轨迹播放或自动规划。
  私有 `agent_initial_state.json` 仅保存固定初态，绑定模板哈希和尺度；不读取完整演示轨迹。
- 2 ms 控制步、4 个物理子步；ALOHA 双臂每侧 6 关节目标（rad），夹爪为单根指轨位移（m）。
  `home_qpos` 是通用 home，当前初值读取 `observation.robot`。省略字段保留目标。
- 单臂任务声明一只手时要求三路标准相机；双臂声明两只手时要求四路标准相机。
  Horseshoe 使用高位、斜前低位、左腕、右腕。低位是任务专用安装位，避免初始圆环侧视成线；
  所有投影/安装参数公开，腕部实际位姿随每帧返回。
- 夹爪目标增大时解除该手辅助；目标减小时进入抓持尝试。
  接触力超过 0.01 N、位于双指简单承载路径上的马蹄件/目标环才允许新建辅助。
  可夹持两只马蹄件，悬挂在路径外的物体不能附着，链节不提供辅助。
  没有“指定目标物体”、强制附着或重置指令。接触证据留在私有审计记录。
- 成功要求圆环与其余装配 AABB 某轴间隔 >20 mm，圆环无辅助且仅有桌面承载接触，
  线速度 <10 mm/s、角速度 <0.2 rad/s，连续 0.5 s，装配连接始终完整。
- 谜题相关接触/机器人自碰撞/机器人与桌面穿透 >1 mm、掉落、连接丢失、持续跟踪失控会失败。
  判定在每个控制步后进行；不宣称逐物理子步连续几何证明。终态不可撤销。
- evaluator 可以内部读取真实几何和物体状态用于判分；solver 仅接收 RGB、相机位姿、
  机器人本体观测及每手辅助是否激活，不接收物体位姿、目标误差或现成几何。

## 验证范围

逻辑回归：

```bash
.venv-gs121-nyx/bin/python -m unittest \
  tests.check_horseshoe_agent tests.check_agent_local \
  tests.check_agent_bridge tests.check_agent_task_spec -v
```

真实 Genesis 冒烟入口（使用新的诊断目录，不是 solver 试验）：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m tests.probe_horseshoe_agent --output runs/agent_bridge_validation/horseshoe_new_probe
```

检查非法动作不步进、四路 tick=0 初态、小幅关节目标的真实运动、重复请求不重复执行、
跨段状态/图像连续，以及左手打开后右手仍保持真实辅助约束。
每段 50 步得到每相机 51 帧，共 100 物理步 / 0.2 秒。
新 adapter 的完整取环、自主重新抓持、成功终态物理验证仍待完成，不能用这段短程冒烟代替。

当前验证记录与短程视频见 [验证材料](../../../runs/agent_bridge_validation/horseshoe_live_v3/validation.md)。
所有诊断输出都与正式 solver 任务包分开；不得交给受测模型作参考。
