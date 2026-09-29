# 本地 Simulator 接口

入口、Env、配置和历史统一在 `topogym/simulator/`。管理方创建并重置环境；交互操作方只获得当前 episode 的操作句柄，两种权限模式都没有 reset。

```python
import topogym

print(topogym.env_list())
with topogym.make("cast_coil", observation_mode="JOINT",
                  control_mode="JOINT_ABS", enable_privileged=True) as env:
    observation, info = env.reset(seed=17)          # 管理方
    initial = info["state_ref"]
    actor = env.interaction(privileged=True)       # 只把 actor 交给操作方
    observation, reward, terminated, truncated, info = actor.step({})
    images = actor.render()
    observation, info = actor.rewind_to(initial)   # 同一 episode，删除旧未来
    details = actor.get("world")
    observation, info = env.reset(seed=18)         # 管理方可以切换 seed
    actor = env.interaction(privileged=False)     # 上一个 actor 已失效
```

- `reset(seed=...)` 创建新 episode。相同 seed 和配置复现初始环境；不增加 last_seed 属性。`reset()` 使用 make 中配置的 seed；没有配置则生成并返回 seed。
- 普通 actor：`step/observe/render/is_solved/action_spec/observation_spec`。特权 actor 另可 `rewind_to/get`；无 reset、make、close、config 或 seed 设置入口。
- StateRef 包含 episode_id 和 state_id。仅当前 episode 的有效状态可回溯，不能跨 seed、跨 episode，也不能访问被截断的旧未来。默认每 2.5 ms 物理 tick 保存一次；一个 step 默认 10 tick；没有后台墙钟推进。
- `state_id` 是身份，不能当作时间索引。回溯不产生额外 tick，新 tick 的 ID 不复用已作废 ID。回溯后下一 step 提交新 action，不自动补完旧 action。
- `get` 白名单：history、state_info、当前 world/robot/task、diagnostics；返回隔离的只读数据，不提供原生 Scene 或任意对象访问。
- 普通 observation 包含 state、robot、task、rgb、cameras；完整 World 数据从特权 get 读取。Task 成功为 info.task_success，完整判据是否存在由 goal_evaluation_complete 明示；数值故障不作为正常失败终态返回。
- 模式独立：EE/JOINT 观察分别可搭配四种控制。EE_ABS 使用世界坐标 position_world_m 与 wxyz 四元数；EE_DELTA 使用 translation_world_m 与 rotation_world_rad（世界轴旋转向量、左乘）。delta 相对 action 提交前实测状态。
- JOINT_ABS 字段 joint_position_rad；JOINT_DELTA 字段 joint_delta_rad。夹爪始终使用 action_spec 中的绝对原生坐标；Robotiq 角度不是开口宽度。`{}` 保持原控制目标。
- RGB 默认 Nyx + compact_lab，848×480。双臂 cam_high/cam_low/cam_left_wrist/cam_right_wrist；单臂 agentview/front_oblique/wrist。公共 RecordingSession 默认 30 fps，记录真实采样 tick 到视频时间的对应关系。
- 显式 `enable_rgb=False` 可运行纯物理；CPU 不启用 Nyx。物理/渲染/IPC 依赖和资产准备见 tests/README.md；缺资源明确报错。

此处是本地 API 权限划分，不是恶意同进程 Python 反射的安全沙箱。操作方隔离进程、网络服务及 agent rollout 仍未启用。

实现、验证和剩余缺口见[本轮报告](../dev-logs/simulator_public_api_implementation_20260924_zh.md)。

## 低层动作 segment（2026-09-25 新增实现）

管理方在 reset 后创建 `SegmentRunner`；它绑定当前 episode 并接管动作入口。普通与特权句柄均不提供 reset/make/close/config 设置。新增实现与真实 GPU 验收状态分开记录，见 [segment 实施记录](../dev-logs/simulator_segment_implementation_20260925_zh.md)。

```python
from topogym.simulator import Env, SimulatorConfig, SegmentRunner

with Env(SimulatorConfig(task_id="cast_coil")) as env:
    env.reset(seed=0)
    with SegmentRunner(env, output_root="task_rollouts/manual_20260926/cast_coil/rollout_0001") as runner:
        interaction = runner.interaction(privileged=False)
        segment = interaction.begin_segment(request_id="move-001")
        try:
            for action in actions:  # 每项必须符合 interaction.action_spec
                obs, reward, terminated, truncated, info = interaction.step(action)
                if terminated or truncated:
                    break
        finally:
            result = interaction.end_segment()
```

列表便利入口：`interaction.run_segment(request_id="move-002", actions=actions)`。每项只执行一次既有控制步，不自动等待目标到达，也不生成额外动作。列表静态字段先校验，IK/delta 的动态解析在各项执行时发生；后续动态失败保留已执行前缀，不回滚物理。

`interaction.timing_spec` 是只读物理步长、控制步包含的 ticks 和控制周期；默认 0.0025 s × 10 = 0.025 s，即 40 Hz，与 30 fps 录像采样率不同。`{}` 保持已有目标并推进一个控制步，重复 delta 则重新相对实测状态产生目标。段没有 action 数/token/时间预算，Env 的 episode 时限和 terminal 仍有效。

begin 捕获起始 RGB，执行中同步记录逐 tick 测量和控制步帧，end 不推进物理，只封存首末 PNG、各视角/合成 MP4 与日志，并完整解码校验。末状态不在 FPS 网格上时追加有标记的展示帧，其时长不计入仿真。终态会自动收尾，随后 end 幂等返回同一结果；下一段继承当前物理状态。零步段合法，生成静帧证据。

结果区分 `reason`、`evidence_complete`、`feedback.task_success`：段执行结束不意味着任务成功；判据不可用时 task_success 为 null。`SegmentError` 只给公开原因，内部异常留在管理报告。故障时末图像可能早于最后保存 tick，结果提供 `final_frame_state_id`，不能把旧图像当作最新物理状态。

管理报告和逐 tick 记录中的 `schema_version: 1` 是这些数据字段/结构的格式版本，供读取方识别；不是物理版本、控制周期或动作数量。录像清单及嵌套的 Task 状态各自使用自己的格式版本；当前 Task 状态格式为 2，不要求与外层 tick 记录相同。

- 普通句柄：公开 observation、过滤后的 step/rewind info、`initial` 初态包、段结果。用 `read_artifact(artifact_id)` 读取授权媒体字节，不传文件路径。
- 特权句柄：额外 `get_log(segment_id, kind, start=0, limit=100)`，kind 为 control_steps/physics_states/history_events；数组块用 `get_log_array(chunk_id, key)` 读取。保持 get 白名单与当前 episode 的 rewind 权限。活动段内拒绝 rewind。
- 管理方：输出根下的 report/config/source_manifest/asset_manifest，private 目录下完整日志与数值块；不把这些路径或私有字段交给普通 policy。

同进程内 request_id 去重。重复批量请求返回原结果，同 ID 不同动作拒绝；流式 step 可提供从 0 开始的 `sequence`，重复序号及相同内容返回原反馈而不执行物理。流式 begin 的已完成重复请求不会重开段，此时应直接 end 取原结果。不同活动段、并发/回调重入以及绕过 runner 的 Env.step 均拒绝。进程崩溃后不自动恢复或重放请求。

runner.close 或管理方 reset/close 会收尾当前段并使旧段句柄失效；特权 rewind 的旧未来保留为审计记录并标注失效，后续段使用新分支。权限是本地 API 合同，不是同一 OS 用户下任意 Python 程序的安全沙箱。
## 管理方调度 policy（2026-09-26）

执行模块集中在 `topogym/simulator/rollout_simulation/`，公开导入仍是 `from topogym.simulator import SegmentRunner`。policy 必需的方法只有 `act(obs)`：返回一条符合 action_spec 的 mapping，或返回 None 结束本段。`{}` 仍推进一个保持控制步。可选 `initialize(context)` 和 `on_segment_end(obs, result)` 必须返回 None；policy 不持有 Env／Interaction／Runner 句柄。

```python
from topogym.planning.base import ActionSequencePolicy

# 管理方：env 已 reset，submission_hash 已按源码、依赖和参数计算。
with SegmentRunner(env, output_root=rollout_directory) as runner:
    result = runner.run_policy(
        request_id="move-001",
        policy=ActionSequencePolicy(actions),
        submission_hash=submission_hash,  # 小写 SHA-256
        mode="limited",
        observation_profile={
            "calibration_camera_ids": [],
        },
    )
```

每步输入为 `obs.rgb / robot / state / execution_state`。robot 同时提供关节位置、TCP 位置／wxyz 朝向、原生单位的实测夹爪坐标，独立于 Env 普通 observation_mode 的 JOINT／EE 选择。规格和单位见 context.observation_spec。任务目标只在 Harbor 的 `instruction.md` 中提供，policy obs 不再包含 task instruction；`observation_profile` 不接受 `task_instruction`。spec/context 及观察 profile 的 `schema_version=2` 标识这次格式变化；动作、权限和执行步语义不变。execution_state 记录最近一次 Env.step 的执行情况及累计步数；正常返回不等于抓取成功。

limited 严格排除物体真值、接触、隐藏 Task 指标和控制器内部目标；它不等于原有 `interaction(privileged=False)` 的普通视图。可用 `rgb_camera_ids` 选择任务 rig 内的视角，段媒体也按该列表生成；默认全部配置视角。`calibration_camera_ids` 默认空，只能列出上述公开视角中的固定相机；发布内外参及坐标约定，若相机移动或标定变化则拒绝。腕部 RGB 保留，腕部标定不提供。首版两种 mode 均只发布固定机位标定，动态标定查询仍未接入。

unlimited 需要管理方在 Env 配置中启用 privileged，并在 run_policy 中显式选择 `state_fields=("world",)` 等字段。支持 robot/world/task；默认无额外字段。获准数据放在 obs.privileged，动作权限保持一致。reward 不自动放入 actor obs，RL 训练数据消费者需另行按管理侧合同接入。

第一次 act 的 previous 为 None；正常控制步反馈进入下一次 obs.execution_state。终态不再取动作，而向结束通知提供最后一步观测；执行失败使用最后可用观测；当它早于当前状态或引擎状态不可信时，标明 observation_is_current=False。必要 policy 报告写入后才发布段完成结果。通知失败独立记录，不重放动作；进程内同 request ID／提交／权限配置重试不再调用 policy。段外 rewind 后需新请求和明确初始化的 policy，未实现 Python 策略状态 checkpoint。

输出根按管理约定放在 `task_rollouts/<experiment_content>_<experiment_date>/<task_name>/rollout_<编号>/`，合成 MP4 直接是根目录下的 segment_N.mp4，逐视角视频在 views 下，日志在 private 下。若管理方已预建根目录用于 source_snapshot 和 run_report.json，可传 `prepared_output=True`；runner 会独占保留自己的输出名称，拒绝覆盖已有 segment 结果。

可读样板在 `planning/examples/cube_pick_place.py`。它只使用 act(obs) 产生 EE_ABS 动作；第一版明确需要 unlimited 的 world 状态，支持原位拾起放下和可选搬运。运行 CLI、源码快照及真实验收资格见[本轮实施记录](../dev-logs/scripted_policy_execution_implementation_20260926_zh.md)。这是本地可信 Python 接入，未实现任意源码上传／进程隔离、模型调用或 RL 训练器。

## Blanket 管理侧冻结初态（2026-09-26）

新增 `TaskSpec.initial_state: InitialStateSpec | None`。声明了冻结初态的任务在 `build → robot home → task.bind` 后导入版本化数值状态，再归零公开时钟、初始化 Task、保存首个 checkpoint 和 RGB。导入不调用 `World.advance()`；`reset_physics_steps != 0` 与此模式冲突，会明确失败。未声明初态的任务保持原 reset 路径。

Genesis 自身 `Scene.build()` 包含一次编译用的内部 simulator step，随后立即 reset；该过程发生在导入冻结状态之前。这里的零推进指初态导入和导入后的 episode 初始化，不表示删除了引擎建场编译过程。首个可回溯状态和 RGB 来自导入后的状态。

Blanket 可显式声明 `table_friction`，由 `World.advance()` 同时用于离线准备和正常运行。该模型为水平静止桌面上的接触粒子施加 `N=m*g` 近似的切向摩擦冲量，补足当前 Genesis PBD/rigid 分支未实现的桌面摩擦；不是抓取 assist。默认未启用，不更改原有任务的物理模型。材料阻尼等候选参数也必须随冻结资源一致重建。

Blanket 的显式管理参数为 `initialization_mode="frozen"`、`initial_state_path`（开发候选）或 `initial_state_resource`（包内资源，二选一），并要求 `initial_state_sha256`。材料、seed、时序、场景、出生资产和机器人资源必须与生成候选时匹配。数值包只支持当前锁定版本的 rigid＋PBD，声明式接入首版限定 ALOHA；不能用于 IPC，也不能作为通用跨版本 checkpoint。普通／特权 interaction 都没有初态导入接口。

`episode_metadata.initial_state` 保存管理侧初态来源和准备资格，标准 segment evidence 会保留它。冻结包包含求解器／耦合器缓冲区、控制目标、源时钟和 RNG；原 `WorldState` 的同 World 限制没有放宽。离线准备录像中的塑形、放桌和静置不计入 agent 的 episode。

`flat_for_preparation` 只用于明确的离线制作。准备脚本通过标准 World 推进，并用 `SensorSuite → SegmentMedia → RecordingSession` 录制真实状态；它是管理侧速度控制，不是机器人解题。正式三档是否切换、候选材料和物理资格以 [Blanket 冻结初态计划](../tasks/blanket_frozen_initialization_plan_20260926_zh.md) 及实际验收报告为准。
