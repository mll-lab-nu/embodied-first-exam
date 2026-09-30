# Simulator action segment 执行、录制与特权日志工程计划

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

日期：2026-09-25。状态：本地接口、逐 tick 证据、录制封装与测试场景已实现，并完成本轮分层验收。以下保留设计要求；具体配置、源码快照、跟踪资格及资源限制以[实施记录](../dev-logs/simulator_segment_implementation_20260925_zh.md)为准，不继承其他会话的通过结论。

2026-09-26 后续实现：首选由管理方 `SegmentRunner.run_policy()` 调度 `act(obs)`，policy 只产出低层动作；执行代码集中到 `topogym/simulator/rollout_simulation/`，保留根层公开导出与原直接交互接口。输出根采用 `task_rollouts/<experiment_content>_<experiment_date>/<task_name>/rollout_<编号>/`，覆盖本文原先的路径示例。新接口、limited 观测范围和真实方块样板见[后续计划](scripted_policy_execution_plan_20260926_zh.md)、[本地 API](simulator_api_zh.md)与[新一轮实施记录](../dev-logs/scripted_policy_execution_implementation_20260926_zh.md)。下文的 2026-09-25 源码坐标和验收记录保留原日期。

> 2026-09-25 最新范围：agent/scripted policy 直接生成低层控制动作，采用现有 Env.step；不开发公共高层动作接口或 ActionExecutor，不增加 high_level/low_level 双模式。[原高层计划](../../../legacy/cleanup_20260929/docs/develop/modules/simulator_high_level_actions_plan_20260925_zh.md)已标为历史设计，方块测试改为本计划第 10 节的低层 policy 验收。无单段 action 数、token、仿真时间／墙钟预算及新增 runner 累计额度；保留 Env 已有 episode 时限。

## 1. 结论、范围与依赖

**可以现在独立完成。** 所需闭环是：接收符合当前 action_spec 的动作 → 同一个 Env 连续 step → 每个已完成 physics tick 留证 → 当前段录像与日志落盘 → 按 operator 权限返回产物。段执行基础设施不依赖任务 planner、生产任务完整成功／失败判据、可解性证明或 assist 部署；方块测试另具备自己的 scripted policy 与 Task 成功判据。

这里独立指功能和验收可独立推进，并非所有修改文件都没有并行会话：`simulator/env.py` 是共享文件，必须按函数增量集成。Task 负责产生 terminal 信号；本模块负责忠实执行、截停和记录信号。没有判据的任务仍能运行，但不能据此确认任务成功或用于正式成功率统计。

本轮实现范围限定为本地 simulator 管理端、受限操作句柄、segment 产物和验证。Harbor、网络 RPC、不可信 Python 进程沙箱、模型 API、token 预算、生产任务的完整判据及任务策略另行集成；方块测试 Task、低层 scripted policy 及测试判据纳入第 10 节。本轮不会执行 operator 提交的任意源码；本地直接策略仅是可信调用方。操作系统级隔离必须由之后的 worker／容器边界实现并验收，Python 句柄不是安全沙箱。

## 2. 当前源码已具备什么

以下坐标为核对时位置；实施时以函数名为准。

| 当前脚本／锚点 | 已有能力 | 本轮补充 |
|---|---|---|
| `topogym/robot/control.py:10`，`action_spec`；`:44`，`compile_action` | 四种控制模式、动作字段、单位、维度与原子校验 | 直接复用，不另造动作编码或 IK |
| `topogym/simulator/interaction.py:29`，`Interaction.step` | 绑定 episode，转交 `Env.step`；普通 get／rewind 拒绝 | 受 segment 约束的操作句柄；普通反馈过滤 |
| `topogym/simulator/env.py:282`，`Env.step` | 每 tick 物理推进、Task.update、保存历史、检查 terminated／truncated；终止后禁止再 step | 管理端逐 tick 事件、重入保护、段内控制步事件 |
| `topogym/simulator/env.py:369`，`_save_state` | 每 tick checkpoint 与单调 state_id | checkpoint 成功提交后发只读测量事件 |
| `topogym/simulator/env.py:159`，`add_transition_sink` | 控制步完成事件 | 原样复用；另记录执行前请求和异常，覆盖没有 Transition 的失败 |
| `topogym/simulator/history.py` | 当前 episode 唯一有效路径、rewind 废弃未来、状态 ID 不复用 | 新增测量记录类型；不另建可恢复历史 |
| `topogym/recording/session.py:20`，`RecordingSession` | 同步多相机录像、frame_map、complete／incomplete、分支身份 | 公共 segment 媒体封装、末帧证据、合成与标准目录发布 |
| `tests/integration/test_policy_action_receiver.py` | 直接策略、两段连续 step、四种控制模式与两种机器人测试代码 | 新增真正公共 segment API 验收；测试文件存在不等于本轮已通过 |
| `tests/runtime_evidence.py` | 测试报告、控制步证据与公共录像接入 | 参考模式，不把测试模块作为运行时依赖 |

关键事实：当前 frame sink 和 transition sink 在控制动作完成后触发，不能把它们叫作逐 physics tick 日志；完整内部 checkpoint 也不等于已导出的可读日志。

## 3. 输入合同：action 与 segment 分层

### 3.1 单步 action 沿用现有合同

`action` 仍是以机器人组名为键的 mapping；组名、维度、夹爪字段由当前 `Interaction.action_spec` 提供。模式在管理方创建 Env 时固定：

| control_mode | 组内机器人目标字段 |
|---|---|
| JOINT_ABS | `joint_position_rad` |
| JOINT_DELTA | `joint_delta_rad` |
| EE_ABS | `position_world_m`、`orientation_wxyz` |
| EE_DELTA | `translation_world_m`、`rotation_world_rad` |

夹爪始终使用 action_spec 中的绝对原生坐标字段。world 坐标、米、弧度、wxyz 沿用现有定义；delta 按动作前实际测量解析。`{}` 保持已有目标，但仍推进一次控制步；双臂同步目标必须放在同一个 action。每个 action 默认推进 `control_decimation` 个 physics ticks，terminal／环境时间上限可提前结束。

**segment 信息不塞进机器人 action。** 它是外层请求和生命周期边界，否则会破坏现有动作校验。

### 3.2 拟新增的本地调用合同

管理方构造 `SegmentRunner(env, output_root)`，绑定已 reset 的 episode，发布 `segment_0` 初态包；operator 只接收 `runner.interaction(privileged=False)` 返回的 episode 绑定句柄。拟定方法：

```python
# 当前接口用法；真实验收状态见实施记录。
interaction = runner.interaction(privileged=False)  # 只能由管理方授权
segment = interaction.begin_segment(request_id="move-001")
result = interaction.step(action)                  # 活跃段内可连续调用
segment_result = interaction.end_segment()         # 不推进物理
```

- 同一 Env 同时只能有一个活跃段；活动段之间不能交错动作。begin 分配 `segment_id` 和不复用的段令牌，step 必须匹配当前 episode／令牌；序列化入口防止并发 begin／step／end。
- 可提供 `interaction.run_segment(request_id="move-001", actions=[{}, {}])` 便利入口，内部调用相同 begin／step／end。列表中每个元素只执行一次 step，不自动等待到达、不插入额外保持步。不另写物理循环；预先动作列表与活动段内逐步根据 observation 决策两种调用方式共用此路径。
- 列表入口先校验 envelope、静态动作字段，再逐步调用唯一 `compile_action`；不能预先编译所有 delta／IK 目标，因为它们依赖当时真实状态。中途动态校验失败保留已执行前缀，不宣称整段原子回滚。
- 空列表合法：生成零物理时长段、同一初末 state_ref 和静帧证据，不调用 step。本地首版不设置单段动作数量额度；未来网络入口的传输限制另行定义。未知字段、NaN、Inf、非整数计数等明确拒绝。
- 输出目录、权限、控制模式、seed 和 segment 编号由管理方决定，不能从 operator payload 覆盖；本轮不新增段预算或 runner 累计额度。
- 同 episode 的 request_id 用于幂等：已完成请求返回原结果，不重放动作；相同 ID 不同内容拒绝；执行中返回状态；中断且无法确定完成时返回 incomplete，不能静默重试。流式动作增加段内序号，重复序号不得再次推进。
- 此幂等合同首版保证当前管理进程内；崩溃后可读取产物状态，但不恢复 Env 或重放未确认动作。跨进程恢复另行设计。
- `end_segment` 幂等；过期句柄、结束后的 step、跨 episode 请求明确拒绝。episode 尚可运行时允许 begin 下一段。

## 4. 生命周期与 terminal

管理态：`ready → active → finalizing → ready / ended / faulted`。只有 active 可 step；finalizing 完成后才能开始下一段。Env 的终态和故障是事实来源，runner 不复制 Task 判据。

| 结束来源 | 段结束原因 | 之后能否开始下一段 |
|---|---|---|
| 动作列表耗尽／脚本正常返回／显式 end | `segment_complete` | 可以，沿用当前状态 |
| `terminated=True` | `env_terminal`，保留可信原始 reason | 不可以，除非授权 rewind 到非终态 |
| `truncated=True` | `env_time_limit` | 不可以，除非合法 rewind |
| 非法 action | `invalid_action` | 结束本段并留证；Env 未 fault 时可以另开段 |
| 引擎／Task／观测故障 | `env_error` | 不可以，保留最后成功 checkpoint 与错误阶段 |
| 日志／录像写入失败 | `evidence_error` | 不可以继续正式执行，标 incomplete |
| 管理方取消 | `cancelled` | 按 episode 取消状态决定，不推断成功 |

terminal 已在 Env 的每个 physics tick 检查；例如 decimation=10，第 3 tick 终止时只运行 3 ticks，并保存这次状态，不执行剩余 7 ticks 或剩余 action。runner 在返回后立即进入 finalizing；不得再发一次空 action 来“取最终帧”。在已有终态上 begin，执行前就拒绝。

`task_success`、`goal_evaluation_complete`、`terminated`、`truncated`、`evidence_complete` 分开记录。判据未完整时管理报告标 `evaluation_status=unavailable`；保留原始 task_success 布尔值，同时将可评估结果设为 null，不能转成正式失败分数。若未来 Task 增加 evaluation_status／terminal_revision，按版本适配，未知／缺失能力不得乐观推断。测试 terminal 可用测试专用 Task／World 夹具，不修改生产任务来假造成功。

不设置单段动作数、token、仿真时间或墙钟预算，也不新增 runner 的 episode 累计额度。Env 自有 max_physics_steps 保留逐 tick 截断。控制目标与操作阶段切换由 policy 决定，runner 不判断移动／抓取是否完成。管理方取消在调用边界协作检查；强制中断卡住的底层调用需要未来进程监督层。

特权 rewind 仅允许在没有活跃段时执行；活动段先结束。恢复非终态后重新采样 RGB，并以新分支、新段号继续；审计日志保留原记录并标 invalidated，当前有效历史仍只有一条。reset／close 为管理方操作，先取消／收尾活动段；新 episode 使旧 runner／operator 失效，使用新 trail，绝不在原段链中偷偷 reset。

## 5. 逐 tick 日志与权限

### 5.1 可信管理端始终留证

在 `_save_state()` 提交 checkpoint 和 state_id 后增加 `Env.add_state_sink(callback)`／unsubscribe。记录 t=0 和每个成功 tick；runner 在 reset 后绑定时显式补初态一次，按 episode/state_id 去重。订阅回调只接收冻结的测量数据，不能取得可改引擎对象或调用 step／reset／rewind；增加重入检查。直接绑定现有 Env 的管理方采集能力，不要求普通 episode 开启 operator 特权。

记录分为：

- `control_steps.jsonl`：动作请求开始／完成／拒绝／异常事件、段内序号、输入 action、实际目标、起止 state_ref、实际 tick 数、奖励及终态。请求记录失败则禁止施加动作。缺少完成 Transition 的异常仍有请求及已完成 tick 前缀。
- `physics_states.jsonl`：初态及每 tick 的 episode／branch／state／parent、control_step、physics_step、sim_time，机器人测量与目标、World 可用动态测量、Task 状态与结果。大数组引用分块文件，不只存摘要。
- `arrays/chunk_*.npz`、`static_model.json`：有界缓冲的数值块和重复静态资料；chunk 原子提交后发布索引，收尾刷新尾块；禁止依赖 pickle 加载不可信对象。
- `history_events.jsonl`：rewind/reset/close 与失效 state_id；审计记录不删除、ID 不复用。

采集复用当前 tick 的只读 world/task 数据和已提交快照，避免再次物理推进或重复保存第二套引擎 checkpoint。采样不能触发 RGB 渲染。定义 TickRecord schema，与原内部 checkpoint 分开；恢复求解器状态不在可读日志承诺内。

报告明确 `physics_tick_complete`、`control_step_complete`、`ipc_contact_coverage`、`actuator_force_coverage`、`checkpoint_exported`。当前不可用的完整 IPC 接触／实际执行器力不填零、不假装已记录。此处 tick 指 Env 的 physics tick，不承诺 solver substep 全量日志。

### 5.2 operator 可见范围

| 权限 | 返回内容 |
|---|---|
| 普通 operator | 授权 observation／RGB、段录像、初末 RGB、最小段清单、执行状态与经白名单筛选的反馈；无详细 log、内部路径、Task metrics、配置或 traceback |
| privileged operator | 上述内容，加管理方授权的当前 episode 日志查询／导出；沿用 get 白名单与 rewind 权限；不获得 reset／make／close |
| 管理方 | 完整证据、配置、来源、故障及资格报告 |

`Interaction.step()` 当前直接返回 Env 的完整 info，其中含 seed、support、executed_joint_targets 等；实现公共反馈投影，保留 step 五元组形态和必要状态标识。管理方 Env.step 仍保留完整数据；现有测试需改从管理证据断言内部目标，不能依赖普通 operator 泄露信息。终止 reason 也按公开枚举映射，详细 reason／metrics 留私有。

日志读取采用当前 episode 的逻辑 segment ID 与受限查询，不接收任意文件路径。授权由管理方创建句柄时决定，每次读取校验 episode；operator 不能靠 payload 的 `privileged=true` 获权。普通响应、媒体 metadata、异常文本均过白名单；禁止将整个 trail 作为普通产物返回。

落盘管理报告、配置和 private 文件使用管理方目录权限；公开交付由 artifact resolver 只发布允许的媒体和清单。**同一 OS 用户下运行的不可信程序仍可能直接读文件／反射 Python 对象，本轮不把 API 权限测试当作容器隔离已通过。** Harbor 集成时另验不同用户／挂载／socket 和符号链接访问边界。

## 6. 录制、身份与异常产物

沿用 planner 计划 §7 指定的目录和 `trail` 拼写：

```text
task_rollouts/<experiment>_<YYYYMMDD>/<task>/trail_<x>_<difficulty>/
  segment_1.mp4                       # 公共层生成的同步多视角合成
  segments/segment_0.json             # 必需初态包，物理时长为 0
  segments/segment_1.json             # 普通可见字段的段清单
  rgb/segment_0/<camera>.png
  rgb/segment_1/{initial,final}/<camera>.png
  views/<camera>/segment_1.mp4
  recording/segment_1/{frame_map.jsonl,recording_manifest.json}
  private/{control_steps,physics_states,history_events}.jsonl
  private/arrays/chunk_000000.npz
  private/static_model.json
  report.json                        # 管理方完整索引与覆盖声明
  config.json
  source_manifest.json
  asset_manifest.json
```

`segment_0.mp4` 仅为可选静态预览。segment_0 不执行动作；动作从 1 开始，失败段也消耗编号。已存在路径拒绝覆盖，由管理方分配新的 trail。生产核心接受配置的输出根，不写死开发机绝对路径；测试产物放 `runs/test_results/`。

每段开始 append 当前 SensorFrame，之后通过 Env frame sink 消费控制边界帧；每 tick 写日志，但不要求每 tick 渲染。保持 Nyx＋compact_lab、默认 848×480、30fps 及机器人规定视角。`observe/render/RecordingSession` 共用帧；输出帧由 SimulationTimeline 按物理时间取样，重复帧须有来源映射，不插值虚构状态。

末状态必须有 final PNG 和 state_ref。若终态落在 30fps 网格之间，明确记录最后 MP4 帧与 final state 的差别，不假设两者一致。公共录制层可追加带标记的终态展示帧，使终态可见；其 presentation padding 单独记录，不能增加 simulated duration。零时长段同理：至少一个真实静帧，媒体时长与物理时长分开。

新增公共媒体封装复用 RecordingSession、VideoWriter、timeline；从相同源帧序列生成独立视角和合成画面，记录固定视角顺序、拼接布局和相同帧数。临时目录写完、所有 writer 关闭、probe 解码和 hash 检查后，再原子发布完成清单；禁止把只写出 MP4 路径当作完整录制成功。

异常收尾遵循：停止接收动作 → 尽力封存已有日志／有效视频前缀 → 标记缺口及原始错误 → 解除订阅 → 必要时由管理方关闭 Env。Env faulted 后不调用 observe/render/get(world) 来伪造末态，最后可用图像和最后已保存 state 分开记录。录制失败也不能覆盖原始物理异常；每个错误按阶段留存。SIGKILL／磁盘满可能无法写最终清单，保留预先落盘的 running/incomplete 标记，下次扫描识别中断，不自动声称恢复成功。

## 7. 具体修改坐标与做法

下表保留原计划的文件分工；当前已实现范围和验收结果见实施记录。

| 路径 | 修改点和实现方式 |
|---|---|
| **新增** `topogym/simulator/segment.py` | SegmentRunner、episode 绑定 SegmentInteraction、begin/step/end/run_segment、段状态机、令牌与序号、幂等、累计执行计数；唯一动作路径调用已有 Interaction.step |
| **新增** `topogym/simulator/segment_contract.py` | SegmentRequest／Result／TickRecord schema、公开清单白名单、envelope 校验和版本；不硬编码任务组名 |
| **新增** `topogym/simulator/evidence.py` | 管理端 tick／control／lifecycle 消费器、JSONL＋数组块、覆盖声明、错误前缀和原子最终报告 |
| **新增** `topogym/simulator/artifacts.py` | trail 分配、产物逻辑 ID、公共／特权视图、episode 校验、路径约束和只读日志导出；不承担 OS 沙箱 |
| `topogym/simulator/env.py`：`__init__`、sink 注册、`step`、`_save_state`、reset／restore／close | 逐 tick 只读 sink、回调重入保护和订阅清理；复用既有 fault 语义；Task.update／advance 仍各调用一次；不改任务终止算法 |
| `topogym/simulator/interaction.py`：`step`、`rewind_to` | 统一 ordinary／privileged 反馈投影，避免 step 与 rewind 返回不同权限视图；保持旧 episode 失效规则。segment 句柄委托此接口，不能把底层 unrestricted step 句柄交给段内策略交错执行 |
| `topogym/simulator/privileged.py` | 优先保持现有 get 白名单；新日志权限由 SegmentInteraction＋artifact resolver 实现，不把文件系统访问混入 world 查询 |
| `topogym/simulator/__init__.py` | 导出稳定管理方 segment 类型；导入不启动引擎、不引入 Harbor/planning 依赖 |
| **新增** `topogym/recording/segment.py` | 标准 RGB／视角／合成／清单布局，复用公共 writer 与时间轴，处理同状态去重和零时长段 |
| `topogym/recording/session.py`、`timeline.py` | 如需支持终态展示帧，增加显式接口和 padding 元数据；保留原行为默认值、帧映射和 branch 检查；不复制 encoder |
| **新增** `tests/contracts/test_segment_execution.py` | 多段连续、动作格式、终止截断、无段额度限制、幂等、并发入口、过期句柄、rewind 和异常前缀 |
| **新增** `tests/contracts/test_segment_artifact_access.py` | 普通返回无私有数据、特权读取、跨 episode 拒绝、路径／符号链接越界、异常脱敏；区分 API 与 OS 隔离验收 |
| **新增** `tests/recording_data/test_segment_recording.py` | 零步／短段／终态末帧、同步合成、frame_map、原子提交、encoder 和磁盘故障 |
| **新增** `tests/integration/test_simulator_segments.py` | Genesis＋Nyx 短策略真实闭环、两机器人四模式、实际日志 tick 覆盖和媒体解码 |
| `tests/integration/test_policy_action_receiver.py` | 保留动作语义／跟踪测试；内部执行目标改从管理端读取；连续段组织复用公共 runner，避免长期保留测试自有段管理 |
| `tests/contracts/test_privileged_access.py`、`test_env_lifecycle.py`、`test_episode_rewind.py` | 补反馈投影、重入及历史行为回归，不降低原断言要求 |
| `docs/develop/modules/simulator_api_zh.md`、模块 README、`tests/README.md` | 实施后更新真实 API、operator 权限、CLI、验收状态；只写已实现接口 |
| planner／Harbor 两份工程计划 | 公共 runner／evidence 归属改为 simulator，planner 仅提供策略适配，Harbor 仅提供 worker/client 调用；不保留两份执行器 |

本轮不改生产 `tasks/`、现有场景资产与 Task terminal 阈值、assist、World 求解器或 deferred agent 实现。第 10 节新增独立方块测试 Task 及其专用判据，使用现有公共构造路径。现有 simulator/history.py 的 checkpoint 结构尽量不改；TickRecord 作为独立测量类型放新 contract 文件。

## 8. 实施顺序与验收门槛

1. **合同与权限基线。** 冻结 schema、公开字段、动作／段计数和目录规则（计数只留证，不限额）；以测试夹具验证 active／ended／faulted 分支及普通反馈过滤。记录工作树实际文件哈希；不只记 Git HEAD。
2. **执行与逐 tick 证据。** 加 state sink、管理证据写入和 segment runner；用已知 tick 的夹具断言日志是初态＋每个已完成 tick，没有 reset／重复 step；故障明确停在哪一阶段。
3. **媒体与原子交付。** 接 RecordingSession 和共用拼接；验证首末 RGB、帧映射、零时长、失败段和 writer 关闭。此阶段不需要任何完整解法。
4. **真实 simulator 集成。** 在独立源码快照、固定配置／资产下，运行 ALOHA 和 Panda、四种模式、两段短策略；验证实际推进、状态连续、逐 tick 覆盖、权限和真实 Nyx 视频。保留原动作跟踪阈值；短时物理误差与 segment 工程结果分开报告。
5. **对接点交付。** 发布本地 API 示例和 schema，供 planner 与 Harbor 后续调用；任务完整成功／正式评分／Harbor 进程隔离另设验收，不阻塞此公共模块交付。

必须覆盖的关键用例：

- decimation=10，第 3 tick terminal：恰好 3 次 advance／Task.update、3 条新增 tick、1 次部分 action 完成记录；剩余 action 从未提交，最终图像不再推进时间。
- terminal 成功、terminal 失败、环境时间上限分别出现；未完成判据输出 unavailable；同 tick terminal 和环境时限沿用 Env 的 terminal 优先。
- 两段首尾 state_ref 相接；段间 observe／视频封装／等待不改变 physics_step；segment_0 不推进物理。
- 非法 action 的输入校验无物理副作用；动作列表中后续 action 失败保留已执行前缀。tick N 的物理／Task／checkpoint／日志／RGB／encoder 故障分别注入，报告实际已保存前缀，禁止伪造完整性。
- 普通模式仍生成管理日志但读不到；特权只能读当前 episode；step/info、rewind、异常、媒体 manifest 不泄露私有内容。
- rewind 前后 branch 不拼接、旧未来失效、段号与 state_id 不复用；实际执行计数保留以供审计，不施加新增额度。
- 重复请求／重复 action 序号无重复推进；重复 end 安全；在 finalizing、reset 后旧句柄、并发第二活跃段等情况下拒绝执行。
- 所有相机与合成视频可完整解码、帧数同步；tick↔state↔segment↔frame 可追溯；最终 PNG 对应实际末状态，padding 不冒充仿真时长。

先跑新增合同／录制测试及现有生命周期、权限、rewind 回归；通过后再执行真实集成。真实测试前准备报告、源码快照、配置身份与录像落盘，不以无录像探针替代 RGB 验收。GPU／Nyx 不可用时明确标 blocked 并提供可执行 CLI，不能静默改 Rasterizer。内存和 I/O 报告记录每 tick 字节量、峰值内存与墙钟耗时；证据流有背压、不丢 tick。已有 Env 全量历史仍会增长，不宣称本轮解决长期运行的 checkpoint 内存问题。

## 9. 并行开发协调与完成定义

Task terminal 会话继续维护 TaskResult、goal_complete 和未来判据版本；本模块只消费这些数据。若接口版本变化，增加显式适配及回归，不能复制任务逻辑。assist／planner 同理：未来新增可测量字段可版本化扩充日志，不要求本轮虚构不存在的字段。

`env.py`、`interaction.py`、录制模块及共用测试实施前再次核对当前 diff，按函数修改，不覆盖其他会话文件。冲突时列出具体函数和影响，保留现有工作后协调。验收绑定实际源码／依赖／资产哈希，之后合入新版本要跑对应回归，旧快照不能代表新代码已通过。

完成本计划意味着：**公共 simulator 能可靠执行分段 action、消费 terminal、形成可追溯录像和特权日志，并提供经过验证的权限视图。** 它不意味着完整任务可解、全部 terminal 判据正确、Harbor 已部署或不可信策略已安全隔离。

## 10. 低层 scripted policy 合同与方块搬运验收

### 10.1 agent 与 simulator 的责任

agent 编写 policy，用循环、插值、公开观测及自己的阶段逻辑生成现有 action_spec 格式的目标；每次 step 对应一次控制更新。simulator 校验目标、执行控制与物理、更新 Task 并返回观测。runner 组织段与记录结果，不判断某次控制目标是否到达，也不提供 move_to/grasp/release 公共接口。

一个 action chunk 是若干连续控制步目标，不是若干需要逐项停稳的高层操作。脚本可自行定义便利函数并多次调用 step，但 simulator 不执行提交的任意源码；本轮用本地可信测试脚本验证，未来 agent 脚本进程隔离由 worker/Harbor 处理。

控制周期必须让 policy 可知。当前默认 `physics_dt_s=0.0025`、`control_decimation=10`，即 0.025 s／40 Hz；Nyx 30 fps 是录像采样率，不是 policy 控制频率。应增加受限只读 timing_spec（拟定：physics_dt_s、control_decimation、control_dt_s），经 Interaction/SegmentInteraction 公开，不把完整 config 或 seed 暴露给 policy，不允许 policy 修改。每次反馈保留实际 physics_steps/action_duration_s，供提前终止及时间累计使用。配置变化时 policy 适配时间采样，不能盲目按 RoboWits 的 30 Hz 或按墙钟 sleep。

空 action `{}` 保持已有目标但推进控制步；重复 delta 会基于新的实测状态产生新目标，不能当作 hold。段间 observe／录像收尾／policy 推理不推进物理。不新增段预算，继续保留 Env 终态与 episode 时间上限；无约束循环可因 episode 截断而结束。

### 10.2 方块测试保留，但不依赖高层执行器

用专用测试 Task、公共 Env/GenesisWorld 和 Panda/Robotiq 构建 compact_lab 桌面场景：动态刚体方块边长候选 0.04 m、质量候选 0.05 kg、起终目标水平相距约 0.20 m。实际位置从工作空间推导，摩擦与控制参数在正式验收前校准冻结。测试注册仅作用于测试进程；不改变生产 Task 或永久扩大生产 registry。

测试 policy 采用 EE_ABS，按公开控制周期生成接近、下降、闭合、试提、抬高、横移、下降、张开、撤离的低层目标；阶段变量与反馈逻辑全部在测试 policy 内。根据机器人 action_spec 获取组名、原生夹爪字段及限制，不把 aperture 与原生坐标混用。policy 只用允许的机器人观测和公开场景目标，物体真值供独立测试评价使用，不作为普通 policy 的隐藏权限。

从 robot_control.home.qpos 开始录制；仅靠关节控制、接触、摩擦和重力抓持，禁止位置瞬移、物体绑定、焊接及外力托举。Task 根据真实物体状态独立判断成功，不能将 policy 阶段标签或列表耗尽作为成功证据。

验收候选值：方块底面离桌 ≥0.05 m、空中横移 ≥0.15 m；释放后距目标中心 ≤0.02 m、底面与桌面高度差 ≤0.003 m、线速度 ≤0.01 m/s、角速度 ≤0.1 rad/s，连续稳定 0.50 s；夹爪打开且撤离 ≥0.05 m。正式验收前冻结阈值并记录版本。Task 记录曾提起、搬运、释放及撤离的历史，状态纳入 snapshot；未撤离时不提前成功终止。

### 10.3 测试与产物

- 先验低层序列合同：N 个合法 actions 正常恰好执行 N 个控制步；不自动插入等待、不因目标未到达拒绝下一控制目标；terminal 时立即截断剩余列表。
- 固定 seed 0 与预先登记的 seeds 1–4 完整运行，另核对同 seed 初态复现；不剔除失败。低层 scripted policy 的成功单独报告，不等于任意 agent policy 都成功。
- 同一策略分别单段执行和拆成两段执行；段间无 reset、无额外 physics tick，验证状态连续。失败输入、引擎异常沿用原计划检查。
- 空抓、受阻、掉落的测试应证明 Task／评价器不会误报成功；若 policy 没有主动检测或停止，runner 不能凭空返回高层 action_failed，它继续按低层合同执行直到终态、截断或 policy 结束。
- 通过公共录制保存从 home 到放下撤离的三路 Nyx 848×480、30 fps 视频、末帧、逐控制步／tick 证据及 report/config/source/asset 身份；完整解码并核对 frame_map。日志关联 segment_id → action_index/control_step → physics_tick/state_ref → frame，不新增高层 action_id。
- 测试产物放 `runs/test_results/low_level_policy_cube_transfer_<run_id>/`。GPU/Nyx 不可用时给 CLI 并标 blocked，不转用其他渲染器冒充通过。

新增文件拟定为 `tests/fixtures/cube_transfer.py`、`tests/integration/test_policy_cube_transfer.py` 和 `scripts/test_policy_cube_transfer.py`；测试 policy 随集成测试组织，避免新建生产高层动作库。为 timing_spec 增加只读规格及权限合同；与 segment 测试共同实施，不修改低层 step 的含义。

实施顺序：冻结并公开动作／时间规格 → 完成段执行和证据 → 建立方块测试 Task 与低层 policy → 真实运行并交付录像和报告。该范围已实现；验收配置、实际结果及限制见实施记录。
