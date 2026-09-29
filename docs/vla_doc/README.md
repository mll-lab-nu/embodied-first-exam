# TopoGym VLA 评测上手

本文是 TopoGym 仿真器一侧的使用手册，供在 TopoGym 上搭 VLA 评测流程的开发者参考。内容只涉及怎样调用仿真器：怎样建环境、观测和动作的格式、怎样读出任务结果，以及有哪些限制。VLA 端的开发（模型服务、观测与动作的适配、训练、评测框架）由使用方负责，本文不做规定。

同目录的 [`vla_eval_demo.py`](vla_eval_demo.py) 是一个最小的调用示例，模型部分是占位函数。其中的适配器写法（选哪些相机、扁平向量怎样排列、夹爪怎样归一化）只是示例，不是项目约定。

## 1. 一个具体场景

在 ALOHA 双臂机器人上评测 `cast_coil`（桌上分开放着两片金属工件，要装配成交替四层的目标构型并松手）的 `base` 变体，seed 取 0–49：

1. 用 `topogym.make` 建一个环境，按 seed 逐个 `reset`，每次 `reset` 都会重建一个新的场景实例。
2. 每个控制步：从观测 `obs` 中取相机图像和关节状态，交给模型推理；模型输出的动作写成 TopoGym 的动作字典，调用 `step` 执行。
3. 任务判定完成、判定失败或时间用尽时，这个 episode 结束，记下结果。
4. 50 个 seed 跑完后算成功率。

这里的几个词：

| 词 | 含义 |
|---|---|
| episode | 从一次 `reset` 到结束的一次完整运行 |
| 物理 tick | Genesis 推进一次物理，默认 2.5 ms |
| 控制步 | 执行一个动作；默认包含 10 个物理 tick，即 25 ms（40 Hz） |
| 变体（variation） | 同一任务的不同场景设定，难度用它来区分（`easy` / `medium` / `hard` 等），不是连续数值 |
| seed | 同一变体内的随机实例编号；同 seed、同配置重建出的初始场景相同 |
| 管理方 / 操作方 | 管理方持有 `Env`，负责 `reset` 和 `close`；操作方只拿到当前 episode 的 `interaction()` 句柄，只能 `step` 和读观测，没有 `reset`。评测脚本本身是管理方，模型只通过操作方句柄交互 |
| 动作块（action chunk） | VLA 一次推理输出的连续多步动作 |

## 2. 运行环境

```bash
cd /home/jianwen/topogym
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"   # Nyx 渲染用的 HDRI 与材质
.venv-gs121-nyx/bin/python your_script.py
```

- 相机图像由 Nyx 渲染，只能在 CUDA 上跑。`enable_rgb=False` 时可以用 CPU 跑纯物理，但 VLA 评测需要图像，所以一律用 CUDA。
- 在新机器上安装依赖，见 [`tests/README.md`](../../tests/README.md) 中的 `env_setup_gs121.sh` 命令。

## 3. 任务与机器人

`topogym.env_list()` 列出任务名，`topogym.env_list(details=True)` 列出每个任务的可用变体。当前 13 个任务如下：

| 任务 | 默认机器人 | 物理模型 | 有无可解证据 |
|---|---|---|---|
| `cast_coil` | ALOHA | 刚体 | 有，easy / medium / hard 各 1 个实例 |
| `cast_keyhole` | ALOHA | 刚体 | 有，easy / medium / hard 各 1 个实例 |
| `horseshoe_ring`、`interlocked_claws` | ALOHA | 刚体 | 无 |
| `blanket_flatten` | ALOHA | PBD 布料 | 无 |
| `rope_threading`、`knot_untying`、`orbits`、`slotted_post_ring` | ALOHA | FEM/IPC 柔体 | 无 |
| `buzz_wire_3d`、`hedgehog_in_cage` | Panda + Robotiq | 刚体 | 无 |
| `lock_picking`、`fiber_bundling` | Panda + Robotiq | 带关节的刚体 | 无 |

"可解证据"指 [`solvability_proof/`](../../solvability_proof/README.md) 里保存的实例：机器人从默认姿态出发，连续执行到任务判定成功，并经过独立复核。**这些证据的运行配置与 VLA 评测不同**：它们用的是 CPU 双精度、每 tick 25 ms / 40 个求解子步、`EE_ABS` 控制、开启辅助抓持（`contact_weld_v1`），而且不渲染图像。在 CUDA + RGB + 默认时序 + 不开辅助抓持的配置下，还没有任何任务被证明可解。因此某个任务上得 0 分，目前分不清是模型能力不足，还是这个配置下任务本来就做不到。

每个任务都有 `base`、`easy`、`medium`、`hard` 四个变体，部分任务还有额外的具名变体（例如 `knot_untying` 的 `double_overhand`）。

## 4. 核心调用

| 调用 | 调用方 | 作用与返回 |
|---|---|---|
| `topogym.make(task_id, **config)` | 管理方 | 返回 `Env`，此时还不建场景。`config` 是 `SimulatorConfig` 的字段，见下表 |
| `env.reset(seed=...)` | 管理方 | 重建场景，返回 `(obs, info)` |
| `env.interaction()` | 管理方 | 返回当前 episode 的操作方句柄 `actor`。每次 `reset` 后旧句柄失效，要重新取 |
| `actor.step(action)` | 模型侧 | 执行一个控制步，返回 `(obs, reward, terminated, truncated, info)` |
| `actor.observe()` | 模型侧 | 返回当前观测，不推进物理 |
| `actor.action_spec` / `observation_spec` / `timing_spec` | 模型侧 | 动作格式、观测格式、时序（物理 tick 长度、每控制步的 tick 数） |
| `env.episode_metadata` | 管理方 | 本 episode 的 seed、变体、资产哈希、控制模式、辅助抓持配置等，用于记录复现信息 |
| `env.close()`，或 `with topogym.make(...) as env:` | 管理方 | 释放场景和显存 |

`make` 的常用参数（完整定义见 [`topogym/simulator/config.py`](../../topogym/simulator/config.py)）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `variation_id` | `"base"` | 变体名 |
| `robot_id` | `"auto"` | 用任务的默认机器人 |
| `control_mode` | `"JOINT_ABS"` | 四种之一，见第 6 节 |
| `observation_mode` | `"JOINT"` | `JOINT` 或 `EE`，见第 5 节 |
| `control_decimation` | `10` | 每个控制步的物理 tick 数 |
| `physics_dt_s` | `0.0025` | 物理 tick 长度（秒）；改它会改变物理本身，一般不要动 |
| `max_physics_steps` | `10000` | 物理 tick 数达到此值就判超时（`truncated=True`）；默认即仿真 25 s |
| `enable_rgb` | `True` | 渲染相机图像 |
| `grasp_assist` | 关闭 | 辅助抓持配置，见第 9 节 |

## 5. 观测 obs

`JOINT` 模式下 `actor.step` 和 `actor.observe` 返回的 `obs`：

```text
obs = {
  "state":   {episode_id, branch_id, state_id, physics_step, sim_time_s},
  "robot":   {<arm>: {"joint_position_rad":   (n,),   # 实测关节角
                      "joint_velocity_rad_s": (n,),   # 实测关节角速度
                      "finger_position_m":    (2,)}}, # Panda 为 finger_position_rad
  "task":    {...},                                   # 任务公开的测量量，VLA 不要用
  "rgb":     {<camera>: uint8 数组 (480, 848, 3)},
  "cameras": {<camera>: 内参与外参},
}
```

- `EE` 模式下，`robot[<arm>]` 不给关节角和角速度，改为给夹爪中心的世界坐标 `tcp_position_world_m` (3,) 和姿态 `tcp_orientation_wxyz` (4,)。
- 机械臂分组名：ALOHA 为 `left`、`right`，各 6 个关节；Panda 只有一组 `arm`，7 个关节。关节名和顺序见 `actor.action_spec["groups"][<arm>]["arm_joint_names"]`。
- 相机名：ALOHA 为 `cam_high`、`cam_low`、`cam_left_wrist`、`cam_right_wrist`；Panda 为 `agentview`、`front_oblique`、`wrist`。每次取观测都会用 Nyx 渲染全部相机，目前没有只渲染其中几路的配置。
- `finger_position_*` 是两根手指的实测位置。ALOHA 的第 0 个值是夹爪命令驱动的那根手指（另一根随动）；Panda 的两个值是 Robotiq 的两个驱动关节，都跟随同一个命令。两者都可以直接和第 6 节的夹爪命令比较。
- 观测里的数组都是只读的，要修改先 `np.array(x)` 复制一份。
- **观测里没有语言指令。** 项目目前没有逐任务的正式语言指令字段，评测时的 prompt 需要自己写，并和结果一起记录。任务目标的描述可以参考 [`configs/task_cards/<task>.yaml`](../../configs/task_cards/) 中的 `title_zh` 与 `initialization.description`。

## 6. 动作 action

动作是按机械臂分组的字典。ALOHA、`JOINT_ABS` 模式的例子：

```python
action = {
    "left":  {"joint_position_rad": [q0, q1, q2, q3, q4, q5], "gripper_position_m": 0.037},
    "right": {"joint_position_rad": [q0, q1, q2, q3, q4, q5], "gripper_position_m": 0.002},
}
```

四种控制模式各自的字段：

| `control_mode` | 每组的位姿字段 | 含义 |
|---|---|---|
| `JOINT_ABS` | `joint_position_rad` (n,) | 关节目标角 |
| `JOINT_DELTA` | `joint_delta_rad` (n,) | 相对于动作提交前实测关节角的增量 |
| `EE_ABS` | `position_world_m` (3,) + `orientation_wxyz` (4,) | 夹爪中心的世界系目标位姿，两个字段必须同时给，四元数必须是单位四元数；内部用 IK 换算成关节目标 |
| `EE_DELTA` | `translation_world_m` (3,) + `rotation_world_rad` (3,) | 相对于动作提交前实测位姿的增量；旋转是世界系的旋转向量，左乘 |

夹爪字段在四种模式下相同，都是**原生关节坐标，不是开口宽度**：

| 机器人 | 字段 | 全开 | 全闭 |
|---|---|---|---|
| ALOHA | `gripper_position_m`（手指导轨位置，米） | 0.037 | 0.002 |
| Panda + Robotiq | `gripper_position_rad`（Robotiq 驱动关节角，弧度） | 0.0 | 0.8 |

其他规则：

- **传空字典 `{}`，或省略某条臂、省略夹爪字段**：对应部分保持上一个目标，仍然推进一个控制步。
- **超出范围不会被自动截断**：关节角超出限位、夹爪超出上表范围，`step` 都会抛出 `ValueError`。模型输出要先自己截断，限位见 `action_spec["groups"][<arm>]["joint_limits_rad"]`。
- VLA 模型通常输出扁平向量，需要一层适配把它拆成上面的字典，并换算夹爪单位。demo 中的约定是：按 `action_spec["arms"]` 的顺序，每条臂依次放关节角和 1 个归一化夹爪开度（0 全闭，1 全开），ALOHA 共 14 维，Panda 共 8 维。接真实模型时，按模型训练时的约定改写。

## 7. 时序

- 默认一个控制步 25 ms（40 Hz），`actor.timing_spec` 给出实际值。
- 模型训练数据的控制频率如果不同（例如 50 Hz），有两种处理：一是改 `control_decimation`（每步 8 个 tick 就是 20 ms，即 50 Hz）；二是保持 40 Hz，对模型的动作块按时间重新采样。不要为此改 `physics_dt_s`。
- 默认 `max_physics_steps=10000`，即仿真 25 s 后超时。长任务要按需调大，并把这个值写进结果。

## 8. 读结果

`actor.step` 返回的 `info` 已经过筛选，评测只需要看下面几个字段：

| 字段 | 取值 |
|---|---|
| `task_outcome` | `success` / `failure` / `ongoing`（未结束）/ `unknown`（判据不可用） |
| `task_success` | `True` / `False` / `None`，`None` 表示这个任务目前给不出判定 |
| `termination_reason` | `None` / `task_terminal`（任务判定结束）/ `time_limit`（超时） |
| `evaluation_status` | `available` / `unavailable` |
| `failure_code` | 任务判定失败时的原因，例如 `wire_touched` |

仿真器给出的 episode 结束情况可以分成下面六类，demo 中的 `classify` 函数是其中一种写法：

| 结果 | 条件 |
|---|---|
| `success` | `task_outcome == "success"` |
| `task_failure` | `task_outcome == "failure"`，例如电流棒碰到导线 |
| `time_limit` | 超时，且判据可用 |
| `unevaluated` | 超时，但这个任务的判据不可用（`evaluation_status == "unavailable"`） |
| `invalid_action` | `step` 抛 `ValueError`：动作格式错或超出范围。此时物理没有推进，episode 仍可继续，demo 直接判负 |
| `env_error` | `step` 抛 `RuntimeError`：仿真出错，Env 进入故障状态，只能 `reset` |

部分任务的完整判据还没做完（`rope_threading`、`knot_untying`、`orbits`、`slotted_post_ring`、`lock_picking` 等），这些任务超时时通常得到 `unevaluated`，不能算作失败。以运行时的 `info["goal_evaluation_complete"]` 和 `env.support_report()` 为准。

## 9. 必须知道的约束

1. **一个进程只能有一个活跃的 `Env`**（Genesis 是进程级全局状态）。要评测多个任务，只能在一个进程里逐个 `with make(...)`，或者开多个进程并行；多进程时要注意显存。
2. **每次 `reset` 都会整体重建场景**，而不是把物体摆回原位。cast_coil 实测一次约 14–17 s，同一进程里第二次 `reset` 并不更快。
3. **仿真比实时慢得多。** cast_coil 实测每个控制步（25 ms 仿真时间）要 6–10 s 墙钟时间，默认 25 s 的 episode（1000 个控制步）要跑约 2–3 小时，见第 10 节。评测前先在目标任务上实测吞吐，据此定 episode 时长和 seed 数。
4. **GPU 物理不是逐位确定的**：同一 seed 重跑，结果可能有微小差异，逐步放大后可能改变结局。所以要跑多个 seed，报告成功率，不要依赖单次重放。
5. **FEM/IPC 柔体任务显存占用大**：`orbits` 和 `slotted_post_ring` 目前在共享 GPU 上被显存不足阻塞。
6. **辅助抓持（`grasp_assist`）默认关闭。** 开启后，夹爪接触物体时会用约束把物体固连在手上，属于评测条件的一部分，开和不开的成绩不能放在一起比。Harbor 层已决定开启被动辅助抓持（规则参照 BEHAVIOR-1K），VLA 评测是否跟随需要和项目负责人确认。
7. **不要改下列目录**，它们由其他开发线维护：`topogym/simulator/`、`topogym/tasks/`、`tasks/`、`harbor_agents/`、`ci_checks/`，以及 `scripts/` 中从参考仓库复制来的文件。如果评测确实需要改仿真器，先提出来。

## 10. 最小 demo

[`vla_eval_demo.py`](vla_eval_demo.py) 由三部分组成：

- `VLAPolicy`：模型适配器。`initialize(context)` 在每个 episode 开始时从 `action_spec` 读取机械臂分组、夹爪范围和相机列表。`act(obs)` 在动作队列为空时调用一次模型，取动作块的前 10 步放进队列，每次弹出一步，转成动作字典返回。`_infer` 是占位函数，把当前关节状态重复成动作块，机器人只保持姿态；接真实模型时只替换它。
- `run_episode`：一个 episode 的主循环，即第 1 节场景的代码形式：

  ```python
  env.reset(seed=seed)
  actor = env.interaction()
  policy.initialize({"action_spec": actor.action_spec})
  obs = actor.observe()
  while True:
      obs, reward, terminated, truncated, info = actor.step(policy.act(obs))
      if terminated or truncated:
          break
  outcome = classify(info)
  ```

  实际代码还分别捕获了策略异常、`ValueError` 和 `RuntimeError`。
- `main`：一个 `Env` 按 seed 逐个跑，每个 episode 写一行 `results.jsonl`，最后写出 `summary.json`（成功率和各类结果的数量）。

运行（输出目录必须尚不存在）：

```bash
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"
.venv-gs121-nyx/bin/python docs/vla_doc/vla_eval_demo.py --task cast_coil --seeds 0 1 \
    --max-control-steps 40 --output runs/vla_eval/demo_01
```

2026-09-29 实测（RTX 4090，cast_coil / base，ALOHA，`JOINT_ABS`，占位策略保持姿态，每个 episode 40 个控制步即仿真 1 s）：

| 运行 | `reset` 墙钟 | 40 步墙钟 | 每控制步 | 结果 |
|---|---|---|---|---|
| 普通循环，seed 0、1（同一进程） | 未分项 | 每个 episode 连同 `reset` 共 263 s / 253 s | 约 6 s | 两个 episode 都是 `time_limit`，`task_success=False` |
| 普通循环，seed 0 | 16.6 s | 259 s | 6.5 s | `time_limit` |
| `--record`（SegmentRunner），seed 0 | 15.4 s | 355 s | 8.9 s | `time_limit`；4 路相机 MP4 加 1 个拼接 MP4（31 帧），日志约 280 MB |
| 关闭 RGB（`enable_rgb=False`），`step({})`，seed 0 | 13.9 s | 396 s | 9.9 s | 仅计时 |

测量时这张 GPU 同时在跑另外 2–3 个进程，利用率约 95%，所以耗时只能当量级参考。关闭 RGB 后单步反而更慢，说明波动主要来自 GPU 被共用，渲染不是唯一的耗时来源。独占 GPU 时的吞吐需要重新测。

结果文件在 `runs/test_results/vla_doc_demo_20260929/`：`plain/` 和 `plain_timed/` 是普通循环，`recorded/` 是 `--record`。每个目录都有 `results.jsonl`，每个 episode 一行；另有 `summary.json`。

## 11. 需要录像时：SegmentRunner

加 `--record` 后，demo 改用仿真器自带的策略调度器 `SegmentRunner.run_policy`。它按同样的 `act(obs)` 接口调用策略，并额外写出多视角 MP4 和逐 tick 日志：

```python
from topogym.simulator import SegmentRunner

env.reset(seed=seed)
with SegmentRunner(env, output_dir) as runner:        # output_dir 必须尚不存在
    result = runner.run_policy(request_id=f"seed-{seed}", policy=policy,
                               submission_hash=source_sha256,   # 策略源码的 SHA-256，小写十六进制
                               mode="limited")
outcome = classify(result["feedback"])  # result["reason"] 为 env_terminal / env_time_limit 时
```

与普通循环的差别：

- `mode="limited"` 时，策略拿到的 `obs` 只有 `rgb`、`robot`、`state`、`execution_state` 四项，没有 `task`，确保模型拿不到物体真值。`robot[<arm>]` 固定提供 `joint_position_rad`、`tcp_position_world_m`、`tcp_orientation_wxyz` 和 `finger_position_*`，但**没有关节角速度**。
- 策略的 `act` 返回 `None` 表示主动结束。
- 每个物理 tick 都写日志，数据量和耗时明显更大。实测 cast_coil 仿真 1 s（40 个控制步）写出约 280 MB 日志，单步 8.9 s，同条件普通循环为 6.5 s（见第 10 节）。适合挑少量 episode 看视频，不适合大规模评测。

实测的输出目录结构（`output_dir` 即上面代码中传入的目录）：

```text
<output_dir>/
  report.json、config.json、asset_manifest.json、source_manifest.json
  segments/
    segment_0/            # SegmentRunner 创建时自动生成的零步初始段
    segment_1/            # run_policy 执行的这一段
      result.json         # 段结果，含 reason、control_steps、feedback（即上面的公开 info）
      steps.jsonl         # 每个物理 tick 的公开记录
      videos/             # cam_high.mp4 等每个相机一个，另有横向拼接的 combined.mp4，30 fps
  private/                # 逐 tick 完整状态和数组，体积最大
```

`docs/develop/modules/simulator_api_zh.md` 中"合成 MP4 直接放在根目录"的说法与实测不符，以上面的结构为准。

## 12. 与 Harbor 层的关系

仓库里的 Harbor 层（`tasks/`、`harbor_agents/`、`ci_checks/`）评测的是写代码的 LLM agent：agent 交出一段动作序列，验证方在隔离容器里重放打分。这一层正在另一条开发线上重建，目标是与 robot_coding_bench 完全对齐，接口还在变。

VLA 评测直接用本文的 `Env` 接口，不经过 Harbor。以后如果要和 coding agent 在同一批实例上比较，需要对齐三件事：Harbor 生成的实例列表（任务、变体、seed）、夹爪单位（Harbor 已决定改成开口宽度，单位米）、辅助抓持配置。

## 13. 参考文件

| 文件 | 内容 |
|---|---|
| [`topogym/simulator/env.py`](../../topogym/simulator/env.py) | `reset` / `step` 的完整实现 |
| [`topogym/simulator/interaction.py`](../../topogym/simulator/interaction.py) | 操作方句柄，以及 `info` 的筛选规则 |
| [`topogym/robot/control.py`](../../topogym/robot/control.py) | `action_spec` 与四种控制模式的换算 |
| [`topogym/sensors/observation.py`](../../topogym/sensors/observation.py) | 观测的组装 |
| [`topogym/simulator/rollout_simulation/policy.py`](../../topogym/simulator/rollout_simulation/policy.py) | `SegmentRunner.run_policy` 的调度逻辑 |
| [`docs/develop/modules/simulator_api_zh.md`](../develop/modules/simulator_api_zh.md) | 仿真器接口的完整说明 |
