# 用 Harbor 接口运行 VLA：π0.5 示例

本文和 [vla_eval_demo.py](vla_eval_demo.py) 复用 Harbor task 已有的 `rcb_topogym.Session`：读取冻结实例、取图和本体状态、执行模型动作、保存轨迹、在线录像。**不依赖 SegmentRunner，也不另写视频 writer。** 这里使用本地 Session，不必启动完整的 `harbor run` 调度。

示例以 Cast Coil / ALOHA 为例，假定 CUDA + Genesis + Nyx 环境和**已适配 TopoGym 动作约定的 π0.5 模型服务**可用。脚本实际调用 openpi 推理，不再用保持姿态的占位策略。本次更新只验证代码接口与控制流程，未运行真实 π0.5 checkpoint 或 GPU episode，不表示模型已能完成任务。

## 1. 从观测到结果的完整流程

```text
Harbor task/environment/instance.json
    ↓ Session(task, instance=..., strict=True)
冻结实例起点
    ↓ render_frame(camera) + joint_positions()
三路 RGB + 14 维本体状态 + instance.text
    ↓ openpi WebsocketClientPolicy.infer(...)
π0.5 返回 (H, 14) 动作块
    ↓ 取前 K 行，逐行 Session.step(action)
任务结束 / 达到本次评测步数上限 / 继续取观测推理
    ↓
trajectory.npz + result.json + 可选 live.mp4
```

模型一次预测 H 行，默认只执行前 10 行，再用新观测重新推理。没有物理后台线程在推理时继续走步；推理等待会增加墙钟耗时。评测脚本只向模型发送图像、本体状态和任务指令，不发送物体位置、任务真值或成功标志；本地 Session 自身具备特权访问能力，不是进程隔离的 limited 模式。

## 2. 复用的 Harbor 方法

以下方法来自 task 自带的 [rcb_topogym.py](../../tasks/topogym-cast-coil-i00/environment/rcb_topogym.py)，demo 按 `--task-dir` 加载该文件，避免复制一份实现。

| 方法 | 本示例用途 |
|---|---|
| `Session(task, instance=path, strict=True)` | 按冻结配置建场景并恢复实例起点；初始状态不匹配时拒绝运行 |
| `session.action_layout` / `control_hz` | 核对动作排列和模型动作频率 |
| `render_frame(camera)` | 当前 RGB，HWC uint8；不推进物理 |
| `joint_positions()` | 当前实测关节角和夹爪开口宽度 |
| `step(action)` | 一行绝对关节目标和米制夹爪宽度，执行一个控制步 |
| `episode_end` / `status()` | 任务结束原因，以及 success、progress、sim_steps 等结果 |
| `record_start()` / `record_stop()` | 记录动作序列；**不是录像** |
| `save_trajectory(actions, path, meta=...)` | 保存 Harbor 可重放的 `trajectory.npz` |
| `start_video(path, fps=..., every=1)` / `stop_video()` | 在线输出当次执行的多相机拼接视频 |
| `close()` | 释放仿真环境 |

`strict=True` 不等于要求 GPU 状态逐位一致：Session 接受哈希相同，或物体与关节姿态在其既定容差内匹配。demo 保存 `instance_exact` 和 `instance_matches`。

Session 的 `reset()` 是恢复当前冻结实例；更换 seed/变体应选择对应的 Harbor 实例文件。本示例一次进程运行一个实例，不再使用旧版 `--seeds` 循环或自己构造 simulator 配置。任务实例与 Harbor 的组织方式见 [Harbor 手册](../rcb/README.md)。

## 3. π0.5 模型服务的前提

π0.5 不自带一个可通用于所有机器人的动作格式。本例假定已有匹配的配置、checkpoint、归一化统计和观测/动作适配，服务对外约定如下：

| 项目 | 本示例的服务边界 |
|---|---|
| 输入 `images` | `cam_high`、`cam_left_wrist`、`cam_right_wrist`；每张为 CHW、uint8、224×224，保比例缩放并补边 |
| 输入 `state` | float32、14 维：左臂 6 个关节角 + 左夹爪宽度 + 右臂 6 个关节角 + 右夹爪宽度 |
| 输入 `prompt` | 默认取冻结 `instance.json["text"]`，可用 `--prompt` 显式覆盖并记录 |
| 输出 `actions` | float32、`(H, 14)`；排列与 state 一致，关节是**绝对目标角 rad**，夹爪是**开口宽度 m** |
| 频率 | 每行对应一个 Harbor 控制步；用 `--policy-hz` 声明，脚本核对冻结实例和实际 Session |
| 归一化与 delta | 模型服务负责归一化/反归一化；若模型内部预测 delta，服务输出变换须还原为绝对目标 |

ALOHA 每臂的关节顺序是 `waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate`，再接该臂的 gripper。脚本与实例中的完整 `action_layout` 做精确核对；当前示例不支持 Panda 的 8 维动作。

**不能直接把官方 `pi05_aloha` 的输出当成 Harbor 动作。** openpi 的默认 ALOHA 适配包含关节符号和夹爪编码换算；Harbor 的宽度（m）既不是归一化的 0–1，也不是 simulator 原生手指关节坐标。DROID/LIBERO checkpoint 的机器人和动作空间同样不能直接套用。

如果模型使用按 Harbor 单位采集的数据训练，可在对应 openpi 配置中使用 `LeRobotAlohaDataConfig(adapt_to_pi=False, ...)`，并配置匹配的归一化统计、三相机训练数据映射，以及与训练一致的 `use_delta_joint_actions`。若复用其他机器人/实机 ALOHA checkpoint，则需经过标定的双向适配。**只改这个布尔值或关闭归一化，并不会让原 checkpoint 自动适配。**

服务应基于 `Pi0Config(pi05=True, ...)` 和实际 checkpoint 对应的完整训练配置。本仓库不在本例中注册一个假定可用的 `pi05_topogym_aloha` 配置，也不提供已经训练好的配套权重。

接口依据：

- [openpi 远程推理文档](https://github.com/Physical-Intelligence/openpi/blob/main/docs/remote_inference.md)：模型服务与客户端分环境运行。
- [ALOHA 输入/输出变换](https://github.com/Physical-Intelligence/openpi/blob/main/src/openpi/policies/aloha_policy.py)：图像布局与 `adapt_to_pi` 的实际行为。
- [训练配置](https://github.com/Physical-Intelligence/openpi/blob/main/src/openpi/training/config.py)：π0.5、ALOHA 数据变换和动作变换。

本次同时核对了本地 `.external/openpi` 源码（HEAD 为 `15a9616a00943ada6c20a0f158e3adb39df2ccac`；工作树可能含本地扩展），没有改动 openpi。

## 4. 假定环境就绪，启动一次推理流程

### 4.1 模型环境：启动已经适配的 π0.5 服务

以下变量替换为你已有的 openpi 路径、**已注册配置名**和匹配 checkpoint。配置名不应仅凭模型叫 π0.5 就选成另一个机器人的配置。

```bash
export OPENPI_ROOT=/path/to/openpi
export PI05_CONFIG=your_registered_topogym_aloha_config
export PI05_CHECKPOINT=/path/to/matching/checkpoint

cd "$OPENPI_ROOT"
uv run scripts/serve_policy.py --port 8001 policy:checkpoint \
    --policy.config="$PI05_CONFIG" \
    --policy.dir="$PI05_CHECKPOINT"
```

模型服务和仿真可以放不同进程或不同机器。模型服务使用其已有 openpi 环境；仿真侧只需额外有 `openpi-client`，不必把完整模型依赖装进 simulator 环境。缺客户端时，在仿真环境安装 `$OPENPI_ROOT/packages/openpi-client`。

### 4.2 仿真环境：运行文档示例

```bash
cd /home/jianwen/topogym
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"

.venv-gs121-nyx/bin/python docs/vla_doc/vla_eval_demo.py \
    --task-dir tasks/topogym-cast-coil-i00 \
    --policy-host localhost --policy-port 8001 \
    --policy-id 'your_registered_topogym_aloha_config:checkpoint_hash' \
    --policy-hz 40 \
    --execute-steps 10 --max-control-steps 40 \
    --record --output runs/vla_eval/pi05_coil_001
```

这是 **40 个控制步的接线检查**，在此实例的 40 Hz 下只有 1 秒仿真时间；不代表完整任务评测。正式运行应显式制定实例集、步数/墙钟预算和模型 checkpoint，再增加步数。输出目录必须尚不存在。

`--policy-id` 是操作者填写的复现标识，应包含实际配置和 checkpoint 版本/哈希；客户端不能凭它验证远端加载了哪套权重，脚本另存服务返回的 metadata。如果模型训练动作频率不是 40 Hz，先在模型适配层按明确规则重采样；不能只是把 `--policy-hz` 改成 40 就声称完成适配。

### 4.3 主循环对应的代码

完整脚本包含维度/有限值检查、错误保存和资源清理，核心逻辑是：

```python
# session 已由 Harbor 的 Session(task, instance=..., strict=True) 创建
session.record_start()
session.start_video(output / "live.mp4", fps=round(session.control_hz), every=1)
try:
    policy.reset()
    steps = 0
    while steps < max_control_steps:
        obs = observation(session, prompt)
        chunk = action_chunk(policy.infer(obs))       # 真实 openpi 推理
        for action in chunk[:min(execute_steps, max_control_steps - steps)]:
            guard_reached = session.step(action)     # Harbor 已有执行实现
            steps += 1
            if session.episode_end is not None or guard_reached:
                break
        if session.episode_end is not None or guard_reached:
            break
finally:
    session.stop_video()
    actions = session.record_stop()
    session.save_trajectory(actions, output / "trajectory.npz")
```

超出机器人限位的有限动作由 Harbor 的 `Session.step` 按既有规则裁剪；脚本在整块提交前拒绝空动作、维度错误、NaN 或 Inf。保存的轨迹是提交给 Session 的动作行；重放时经过相同的裁剪，不应把它称为逐 tick 实测机器人状态。

## 5. 录像、轨迹与结果

`--record` 只控制是否调用 Harbor 的在线录像方法，执行仍使用同一个 Session 循环；不切换到 SegmentRunner。当前输出是所有 `VIDEO_CAMERAS` 的一个拼接 MP4，加 Harbor writer 保存的最后一帧图片。模型只读取其中三路，录像可包含 `cam_low`。

本例使用 `every=1`、fps 等于控制频率，确保包含任务终止控制步并保持正常播放速度；为此仅支持整数控制频率。它会增加取帧和编码开销，需要先测吞吐，不能沿用旧版 SegmentRunner 的耗时数据。

```text
runs/vla_eval/pi05_coil_001/
  run.json                  # 参数、prompt、模型标识、源码与实例文件哈希
  instance.json             # 本次冻结实例副本
  policy_metadata.json      # openpi 服务返回的 metadata
  session.json              # 实际配置、动作顺序、频率、实例匹配情况
  rcb_session_log.jsonl      # Harbor 自带会话日志
  trajectory.npz            # record_start/stop + save_trajectory
  result.json               # 本次停止原因、步数、推理次数、Harbor status、错误
  live.mp4                  # --record：当次闭环执行的拼接视频
  live.last.png             # --record：Harbor writer 的最后一帧
```

`result.json` 需要这样解读：

- `harbor_status.success` 是 Session 当前的任务判定；`progress` 是其公开进展值。
- `stop_reason=control_step_limit` 表示达到**本示例自己设的上限**，不等于 Harbor 标准时间预算耗尽，也不自动等于任务失败。
- `session.episode_end` 有值时立即退出。**`step()` 的布尔返回值只表示达到 Session runaway guard**；仅检查它会在任务已经结束后继续记录无效动作。
- 推理、动作格式或执行错误单独记为 `error`，保存出错阶段及可保留的轨迹/视频；清理失败写入 `cleanup_errors`，脚本非零退出。建场景/连接阶段错误会直接抛出，不保证已有 episode 结果文件。
- `Session.status()` 不暴露完整的 `evaluation_status`。不能仅用 `success=False` 区分任务失败、未完成和判据不可用；跨任务汇总须结合 Harbor 的任务支持情况和正式 verifier，不能把所有 false 都当成可比较的失败率。

`Session.render_video(actions, ...)` 是 reset 后**重新执行动作轨迹**再录像；本例使用的 `start_video/stop_video` 保存的是当前 VLA 闭环执行，二者不混称。

需要用 Harbor 原有重放路径检查已保存轨迹时，可以在独立进程运行：

```bash
.venv-gs121-nyx/bin/python tasks/topogym-cast-coil-i00/environment/rcb_topogym.py replay \
    --task cast_coil \
    --instance runs/vla_eval/pi05_coil_001/instance.json \
    --traj runs/vla_eval/pi05_coil_001/trajectory.npz \
    --repeat 2 --strict
```

这检查固定轨迹的开环重放，不会重新调用 VLA，也不等于完成隔离容器里的 Harbor 正式评分。GPU 重放可能有差异；闭环成绩、重放成绩应分别保存。

## 6. 与 coding agent 对比，以及 limited 服务

这条路径直接复用选中 Harbor task 的实例配置，包括任务、变体、seed、辅助抓持、控制参数和相机设定；以冻结实例和实际 `session.json` 为准。不要再根据旧文档统一假定辅助抓持开或关。复用 Session 也不会自动对齐模型推理墙钟、reset 权限、观测权限或评测预算，比较成绩时应明确这些条件。

如果需要和 **Harbor limited** 模式保持相同隔离边界，可把适配器改接其已有 `rcb_client.Robot`：

| 本地 Session | limited 客户端 |
|---|---|
| `render_frame` + `joint_positions` | `get_obs(seconds=0)` 的相机帧和按 `spec()` 布局解码的 proprio |
| 循环 `step(action)` | `submit("joint_position", actions, dt=..., ...)` |
| `start_video/stop_video` | `submit(..., video="both")` 返回每次调用的 MP4/帧，`Result.save(...)` 保存 |
| 本地 `status()` | 客户端 `status()`、响应 done/reason，以及服务端最终评分 |

客户端文件在 [rcb_client.py](../../tasks/topogym-cast-coil-i00-limited/environment/rcb_client.py)，服务协议见 [LIMITED_MODE_PROTOCOL.md](../rcb/LIMITED_MODE_PROTOCOL.md)。limited 的 proprio 不应整体直接当成 14 维 state：必须按其布局取所需关节与夹爪列。一次调用返回的视频也不自动等于整局的连续 MP4。

当前 demo 实现的是本地 Session 路径；它没有实现 limited HTTP 适配或 `harbor run` VLA agent。两种方式都不要求 SegmentRunner。

## 7. 本次验证范围与旧结果

本次 Python 语法和 CLI 帮助检查通过；6 项流程检查通过，覆盖动作块重规划/步数预算、任务中途结束、Session 步数保护、推理失败、非法动作块，以及录像封口失败时保留轨迹。检查复用真实 Harbor 的 step、动作记录和轨迹保存方法，替换物理、模型与视频编码，不代表真实执行通过。报告在 [validation.json](../../runs/test_results/vla_harbor_pi05_doc_20260929/validation.json)。真实 π0.5 + CUDA/Nyx 的可运行性、吞吐和成功率需要按上面的命令另行实测。

旧版直接 Env / SegmentRunner 占位策略的产物仍在 `runs/test_results/vla_doc_demo_20260929/`，未删除或改写。它们属于旧接口和旧配置的历史记录，不能作为本版 Harbor + π0.5 的运行证据。
