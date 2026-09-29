# Harbor rollout 本地提交协议 v1 草案

日期：2026-09-26。状态：**首版客户端、worker 和隔离代理已实现，CPU 核心／IPC 合同测试已执行；真实容器、GPU 和 API 闭环待验收。** 文件名保留 draft 以兼容旧链接。配套 [共享镜像 pipeline 计划](harbor_shared_image_pipeline_plan_20260925_zh.md)，可执行命令见 [runner README](../../../harbor_runners/README.md)。本文定义最小的“持续会话 → 提交 policy → 查询结果”合同，不新增 Env、segment 调度器、动作语言或录制系统。

`topogym-rollout` 命令、`api_version`、`request_status`、`session.json` 和路径映射是本轮实现的接入层；`run_policy`、policy 输入输出、底层 segment 结果和 artifact 描述符复用已有实现。兼容性以实际锁定的源码／镜像身份为准，不能混淆两层 schema。

## 1. 已核对的实现与输入输出

本草案按以下当前调用链核对，不从旧 agent/deferred 代码推定可用能力：

| 源码 | 当前输入与输出 | 接入决策 |
|---|---|---|
| [api.py](../../../topogym/simulator/api.py)、[config.py](../../../topogym/simulator/config.py) | `make(task_id, **configuration)` → Env；`SimulatorConfig` 校验配置 | task、variation、机器人等由管理方冻结，不能夹带进每次 agent 提交 |
| [env.py](../../../topogym/simulator/env.py) | `reset(seed=...)` → observation/info；`step(action)` → observation/reward/terminated/truncated/info；action/timing spec、逐 tick/transition/frame hooks | worker 创建一次 Env；首版 agent 不调用 reset、step、close |
| [interaction.py](../../../topogym/simulator/interaction.py)、[privileged.py](../../../topogym/simulator/privileged.py) | episode 绑定、普通／特权 get/rewind、`public_info` | 复用授权和公开字段筛选；不把原始 Env.observe 当作 limited policy 观测 |
| [segment.py](../../../topogym/simulator/rollout_simulation/segment.py) | `SegmentRunner(env, output_root, prepared_output=False)`，`initial`，`run_policy(...)`，动作批次／逐步本地接口，artifact/log 读取 | 只对接已有 run_policy；段号、连续状态、录制和日志仍由其管理 |
| [policy.py](../../../topogym/simulator/rollout_simulation/policy.py) | mode/profile 校验、initialize/act/end 调度、重复请求、段结束与错误 | 不复制 act/step 循环；hash 与权限由管理方传入 |
| [policy_observation.py](../../../topogym/simulator/rollout_simulation/policy_observation.py) | `validate_profile`、`build_context`、`project_observation` | 初态规格和执行观测使用同一投影合同；不另造字段白名单 |
| [segment_contract.py](../../../topogym/simulator/rollout_simulation/segment_contract.py)、[robot/control.py](../../../topogym/robot/control.py) | request ID、数值 action、执行状态检查；四种控制模式与 IK 转换 | 复用校验、单位和 action_spec；JSON 仅作传输编码 |
| [artifacts.py](../../../topogym/simulator/rollout_simulation/artifacts.py)、[evidence.py](../../../topogym/simulator/rollout_simulation/evidence.py) | artifact ID/hash/size、按权限读取；私有控制／物理／历史日志和 policy 报告 | 公开路径由授权 artifact 导出；不把私有日志整棵映射给 agent |
| [recording/segment.py](../../../topogym/recording/segment.py) | 初末 PNG、各视角／拼屏 MP4、frame map、视频校验 | 保留原产物，逐段发布；不再编码或另写录像循环 |
| [planning/base.py](../../../topogym/planning/base.py)、[cube_pick_place.py](../../../topogym/planning/examples/cube_pick_place.py)、[方块调用入口](../../../scripts/test_scripted_policy_rollout.py) | passive policy、动作序列包装、同一 runner 中 pickup/transfer 两段 | 已有完整本地执行样例；新缺口是等待并接收 agent 后续生成的脚本 |
| [tasks/base.py](../../../topogym/tasks/base.py) | TaskResult：reward、terminated、task_success、reason、metrics、evaluation_status | 任务真值继续来自 Task；Harbor reward 是评测包装，不由 policy 声明 |

### 1.1 管理配置与单次提交严格分开

以下内容由 prepare/worker 冻结：

- `SimulatorConfig`：task_id、variation_id、task_parameters、robot_id、seed、compute_backend、precision、physics_dt_s、solver_substeps、control_decimation、max_physics_steps、reset_physics_steps、enable_rgb、observation_mode、control_mode、enable_privileged、render_backend、asset_root、work_dir。容器路径由管理方解析，不能使用 agent 提供的宿主路径。
- `run_policy` 授权：`mode`、`observation_profile`、`state_fields`。观测 profile 当前接受 `rgb_camera_ids`、`calibration_camera_ids`（任务文字只在 `instruction.md` 中提供）；policy 特权字段仅 `robot/world/task`，不是 PrivilegedAccess 的全部可读名称。
- 实验外层设置：镜像／源码身份、Harbor agent、trial 超时、评测类型、输出归档与 token 模式。本轮 token 为 off，无单段 token、action 数或墙钟配额。

agent 单次提交只描述“在当前 episode 执行这份 policy 及其参数”。不能覆盖 seed、控制周期、权限、相机、输出根目录或 Task 判据。

### 1.2 policy 合同直接复用

已有 `run_policy` 签名：

```python
runner.run_policy(
    request_id=request_id,
    policy=policy_object,
    submission_hash=submission_hash,
    mode="limited",
    observation_profile=observation_profile,
    state_fields=(),
)
```

`policy` 实现 `act(obs) -> Mapping | None`；可选 `initialize(context)` 和 `on_segment_end(obs, result)` 必须返回 None。Mapping 执行一个控制步，空 `{}` 也推进保持步；None 正常结束本段。环境 terminal/time limit 可先结束，不要求脚本把所有动作跑完。

`initialize` 的 context 已包含 `schema_version=2`、mode、action_spec、timing_spec、observation_spec、observation_profile、rgb_available。这里的 context 是 simulator 给 policy 的规格，**不是 Harbor 的 AgentContext**。

limited 的 obs 已包含 RGB、机器人本体状态、任务说明、state 和 execution_state；可选固定相机标定。state 字段为 episode_id、branch_id、state_id、physics_step、sim_time_s；execution_state 包含已执行步数、上一动作回执、观测对应状态及是否最新。unlimited 才按授权增加 privileged。数组与映射保持已有只读语义；跨进程传输需保持 dtype、shape 和 None，不使用 pickle 传任意对象。

| control_mode | 每个机器人组可用的主要字段 |
|---|---|
| `JOINT_ABS` | `joint_position_rad` |
| `JOINT_DELTA` | `joint_delta_rad` |
| `EE_ABS` | `position_world_m` 与单位四元数 `orientation_wxyz`；提供位姿时必须完整 |
| `EE_DELTA` | `translation_world_m`、`rotation_world_rad`；增量相对动作前实测状态 |

各组还支持其 action_spec 声明的夹爪字段，表示原生关节坐标，不统一解释为开口宽度。组名、自由度、范围从运行时 spec 读取，不硬编码 `arm` 或关节数量。EE 输入由现有控制层执行 IK，agent 不需要提交新类型的“IK 指令”。

## 2. 首版范围与可变更边界

第一版使用同一 trial 容器中的本地通信；CLI 是 agent 的稳定入口，底层可先用 Unix socket。JSON 消息负责 submit/status/result 等控制信息，不用 HTTP、云队列或逐 tick JSON-RGB 服务。policy 跨进程观测传输复用现有数组语义，是另一条内部通道。

对外仅提供：

| 操作 | 用途 |
|---|---|
| `ready --check-initial` | 非阻塞就绪探针：检查 worker、当前 episode、初态规格和授权 RGB 可读；不启动／reset 环境 |
| `status` | 读取会话状态、当前请求和已发布产物位置；不推进物理 |
| `submit FILE --request-id ID [--params FILE] [--wait]` | 读取脚本与可选 JSON 参数，提交一次 policy；可等待结果 |
| `result --request-id ID [--wait]` | 查询同一提交，或等待其结果；不重复执行 |

普通 agent 不提供 `make/reset/step/rewind/get-private/set-mode/close` 等远程命令；这些本地能力继续存在于 simulator。管理取消走独立管理通道，不能与阻塞的提交共用串行等待。第一版每个 episode 最多一个执行中提交；新的不同请求在忙碌时拒绝，不实现批量排队。

采用 `api_version: "topogym.rollout.v1"`；未知版本拒绝。允许以后兼容增加返回字段，输入未知字段先拒绝以发现拼写或越权配置；破坏现有字段语义时升级版本，并把版本绑定到本次 run 的模板／镜像／manifest。旧任务定义和历史结果不重写。

## 3. 一次提交实际长什么样

### 3.1 agent 写文件并执行 CLI

worker 已生成初态。agent 按 instruction 读取 `/rollout/session.json`、`/rollout/spec.json`、初态清单和对应 PNG，然后写 `/workspace/segment_1.py`。下面仅示范保持两个控制步，实际可换成任意符合合同的策略：

```python
from topogym.planning.base import ActionSequencePolicy

def create_policy():
    return ActionSequencePolicy([{}, {}])
```

```bash
# 在通过 healthcheck 的 trial agent shell 内执行
topogym-rollout submit /workspace/segment_1.py --request-id req-001 --wait
```

首版源码加载约定为模块导出 `create_policy(**parameters)`，参数缺省为空对象。工厂产生实现 act 的对象；工厂本身也属于待隔离的用户代码。该工厂入口是接入层新增约定，不是现有 SegmentRunner 要求 agent 提供的函数名。

### 3.2 CLI 发给 worker 的消息

```json
{
  "api_version": "topogym.rollout.v1",
  "operation": "submit_policy",
  "request_id": "req-001",
  "episode_id": "episode-abc",
  "policy": {
    "source_utf8": "from topogym.planning.base import ActionSequencePolicy\n\ndef create_policy():\n    return ActionSequencePolicy([{}, {}])\n",
    "filename": "segment_1.py",
    "factory": "create_policy",
    "parameters": {}
  }
}
```

| 字段 | 首版规则／如何连接现有 API |
|---|---|
| `api_version`、`operation` | 接入层固定版本与操作；不传入 simulator 配置 |
| `request_id` | 沿用现有非空字符串、最长 256 字符校验；CLI 可生成，必须输出以便失败后查询 |
| `episode_id` | CLI 从当前 session 取得，worker 验证匹配。它防止过期请求，不是身份认证凭据 |
| `policy.source_utf8` | CLI 读取文件后的实际源码内容；worker 固化收到的字节。后续修改 workspace 原文件不影响已接受提交 |
| `policy.filename` | 仅用于回溯和错误定位的单个文件名，不决定服务器读取或写入路径 |
| `policy.factory` | v1 固定为 create_policy，不开放任意函数路径 |
| `policy.parameters` | 可选 JSON 对象，默认 `{}`；传给工厂，禁止 NaN/Infinity 和任意对象反序列化 |

worker 根据固化源码、工厂、规范参数和协议版本计算 SHA-256，作为 `submission_hash` 传给 run_policy；不采信 agent 自报的哈希。固定镜像／依赖身份另进入 run manifest。内部保存／加载位置由管理方确定，`filename` 仅是报告标签，不用来设置模块名、工作目录或加载路径，不改变执行身份。

**请求传脚本内容，worker 不根据 agent 给出的任意路径打开文件。** `/workspace/segment_1.py` 是 CLI 的本地输入；最初讨论中的 `policy_file` 不作为 wire 消息的路径读取授权。首版提交一份自包含源文件，可导入共享镜像中公开的已安装库，不默认动态加载 workspace 中其他文件；后续若支持多文件包，要把全部源文件一起冻结、哈希和验证。

按既有语义，同 episode、同 request ID、同执行身份返回原结果；不同内容复用 ID 为冲突，不再执行。传输重试期间重复 submit 只订阅／查询已有状态，不再次调用正在执行的 run_policy。进程退出后不能从录像恢复活 Env；只读历史结果可以保留，不能把重启当作继续同一 episode。

### 3.3 接收与结束回执

submit 不等待时，先返回接入层回执；段号尚未由核心分配时为 null：

```json
{
  "api_version": "topogym.rollout.v1",
  "request_id": "req-001",
  "episode_id": "episode-abc",
  "request_status": "accepted",
  "segment_id": null,
  "result_path": null,
  "artifacts_manifest": "/rollout/public_artifacts.json",
  "error": null
}
```

`--wait` 等待以下回执；数字仅为示例，段号由现有 runner 分配：

```json
{
  "api_version": "topogym.rollout.v1",
  "request_id": "req-001",
  "episode_id": "episode-abc",
  "request_status": "finished",
  "segment_id": 1,
  "result_path": "/rollout/segments/segment_1.json",
  "artifacts_manifest": "/rollout/public_artifacts.json",
  "error": null
}
```

首版直接引用已有 segment JSON，不再在回执里复制一套 `terminal/video/success` 字段。agent 读取 `result_path` 中的 reason、feedback、media，再经路径映射打开 PNG／视频。`finished` 表示有可读结果，**不是 Task 成功，也不保证 evidence_complete**。native result 为 policy_error、invalid_action 或 incomplete 时仍需如实读取和处理。

接入层请求状态为 `accepted → running → publishing → finished`；初始化／协议拒绝为 `rejected`，没有可发布核心结果的基础设施故障为 `error`。段清单发布成功且授权媒体／映射可读后才返回 finished。失败运行可发布带缺失说明的结果，不能伪造完整媒体。

```json
{
  "api_version": "topogym.rollout.v1",
  "request_id": "req-001",
  "episode_id": "episode-old",
  "request_status": "rejected",
  "segment_id": null,
  "result_path": null,
  "artifacts_manifest": null,
  "error": {"code": "episode_expired", "message": "Submission belongs to an expired episode."}
}
```

已存在的核心错误码继续使用，如 episode_expired、episode_ended、execution_busy、request_id_conflict、runner_faulted。新增的版本／源码格式／发布错误使用接入层代码，并保存 layer/stage 到管理报告；不把原始 traceback、私有状态或凭据写入公共错误。

CLI 约定：正常取得回执退出 0，参数／请求拒绝退出 2，通信／内部错误退出 1，等待超时退出 3。退出 0 不代表谜题成功；wait 超时或客户端退出不取消已接受的物理执行，应按 request ID 查询。`ready` 特例为仅就绪返回 0，其余返回非 0。状态查询读管理方发布的快照，不在 run_policy 持锁期间另开线程调用 Env 或竞争 runner.close。

## 4. 环境向 agent 提供哪些现有结果

### 4.1 初态与规格

`/rollout/session.json` 是接入层原子写入的会话快照：api_version、episode_id、phase、active_request_id、initial_path、spec_path、artifacts_manifest、latest_result_path、stop_reason。phase 区分 initializing、ready、executing、terminal、faulted、closing、closed。最新结果和 state 引用只描述已发布数据；运行中不能冒充最新物理 tick。

`/rollout/spec.json` 保存从同一份已验证 observation profile 派生的 policy context，包括 action_spec、timing_spec 和 policy observation_spec。不能原样使用 `Env.observation_spec` 替代 policy 投影规格；init 规格不包含管理配置、真值或凭据。

初态 `segments/segment_0.json` 已有字段：segment_id=0、episode_id、state_ref、rgb、simulated_duration_s=0。rgb 值是 artifact 描述符，不是路径；没有 agent policy，没有 segment_0.mp4 要求。底层 initial 可能包含全部相机，公开副本须按冻结 profile 只保留授权相机条目，保持同一字段结构并记录投影身份，管理方原件不改写。首版声明所有标准 RGB 实验必须发布所选相机 PNG。

### 4.2 动作段结果

以下是当前核心结果字段，v1 不改名或删改语义：

| 字段组 | 含义 |
|---|---|
| `segment_id/request_id/episode_id/branch_id` | 段、提交、episode 与历史分支身份 |
| `status/reason` | status 为 complete/incomplete；reason 区分 policy_done、env_terminal、env_time_limit、invalid_policy_output、invalid_action、policy_error、observation_error、evidence_error、env_error、cancelled 等 |
| `start_state_ref/end_state_ref` | `{episode_id, state_id}`；正常连续两段前末等于后初 |
| `control_steps/attempted_control_steps` | 已完成控制步和尝试控制步，不与物理 tick 混用 |
| `physics_steps/saved_physics_steps/uncheckpointed_physics_steps` | 实际推进、已保存及未 checkpoint 的 tick 计数，失败时尤其不能合并 |
| `simulated_duration_s` | 本段真实仿真时长；展示补帧不增加该值 |
| `physics_tick_complete/control_step_complete/evidence_complete` | 对应执行与证据完整性，不能以视频存在代替 |
| `feedback` | 现有 public_info 的公开结果，含 evaluation_status、task_success、task_outcome、task_terminated 等可用字段 |
| `media.initial/media.final/media.videos` | 按相机名称映射 artifact_id、sha256、size_bytes；videos 可有 combined |
| `media` 的其他字段 | camera_order、frame_count、presentation_padding_frames、final_frame_state_id 在可用时存在；错误时不能假设齐全 |

feedback 的任务结果区分 available/unavailable，task_outcome 区分 success/failure/ongoing/unknown，task_success 在 unavailable 时为 null。policy_done 不是任务成功，env_time_limit 不是任务 terminal；是否还接受动作同时受会话 phase 和现有 Env 状态决定。agent 不需要推导隐藏评分逻辑。

### 4.3 路径映射、公开日志与完整证据

公开发布层通过现有 `read_artifact` 取得授权字节并核对 hash/size，再原子发布 `/rollout/public_artifacts.json`。拟议映射条目包含 artifact_id、episode_id、segment_id、kind、camera_id、path、sha256、size_bytes。路径只属于本 trial 的 `/rollout/`；以后换传输方式不改变底层 artifact 身份。

segment_N 的新增媒体逐段追加，已完成段不覆盖。底层 `segments/segment_N.json` 曾有 active 描述符且可能含内部 token；**只发布已经结束的公开结果，不把 active 描述符或整棵工作目录原样同步给 agent**。发布媒体和路径映射后，再提交公开结果清单及 finished 回执；掉线后可按 request ID 补查。

首版给 agent 的“log”以现有公开段 JSON、feedback 和接入层提交／完成／错误回执为准。完整的 `private/control_steps.jsonl`、`physics_states.jsonl`、`history_events.jsonl`、数组块、policy 错误详情仍完整保存给管理方和归档。当前 get_log/get_log_array 是特权接口；此前例子中的 `/rollout/logs/segment_1.jsonl` **尚不是已有产物，也不作为 v1 必需文件**。若以后要发布逐步公开日志，应增加字段白名单和测试，不能直接公开物体真值。

授权了 unlimited 也不等于开放全部文件：policy 的 world/robot/task 与日志访问是不同授权。基础协议先不提供通用 get/log/rewind，避免无意扩大当前实验范围。

## 5. instruction.md 应当写什么

**需要写 agent 面向的使用合同，不需要把内部 wire JSON 全部塞进任务说明。** instruction 来自一份模板，至少包含：

1. 本任务目标、允许的观测／控制方式，以及 worker 已由环境启动、不能自行 reset 的说明。
2. 初态与规格路径、artifact ID 到文件路径的查法；图片需要实际打开，而不是只读文件名。
3. `create_policy(**parameters)` 加现有 initialize/act/end 合同，None／空 action 的语义和一个最小示例。
4. submit、result、status 命令及 request ID 的复用规则；等待超时先查询，不以新 ID 重放不确定动作。
5. 完成回执、公开段结果与成功判据的区别；哪里读视频／RGB／公开日志，何时继续或停止。
6. off 模式不等待 budget.json。显式 observed 时，root 发布 `/rollout/budget.json`，预算失败经 root-only `budget_stop` 管理消息锁存，取消 policy 并强制 reward=0；公开 agent socket 不接受此管理操作。真实 provider 验收状态见 usage README。

详细 v1 字段文档可随镜像安装到 `/opt/topogym/docs/rollout_protocol_v1.md`，CLI 提供 `--help`，instruction 引用它。模板和 CLI 的示例须做合同检查，防止文档命令漂移。若某个外部 agent 想直接构造消息，再读取完整协议文档即可；不为不同 agent 维护不同 policy schema。

## 6. 初始化顺序与首版测试

环境 command 启动 worker → 创建 Env/reset/SegmentRunner → 发布初态、规格和会话 → Harbor 原生 environment healthcheck 通过 → agent setup/run。具体配置与版本核验见主计划 §4.3.1；无需修改 Harbor 核心，healthcheck 失败时不进入 agent run。

我在开发阶段负责无 GPU 的格式、生命周期和失败合同测试：配置越权字段拒绝；单文件内容冻结；同 ID 幂等／冲突；过期 episode；重复查询不推进；wait 超时不重放；active token 不公开；首次 ready 前无 agent.run；健康检查失败不调用模型；core 结果不被重命名或把 unavailable 改成 false；示例和 CLI 帮助一致。

用户在开发完成后运行提供的 GPU CLI：真实 reset/Nyx 初态检查；同一 Env 连续两段；真实视频、RGB、tick 日志与段边界对应；容器用户可读公开产物且无法访问管理证据；真实 API 读图／写脚本／再读反馈。完整责任表和交付命令要求见主计划 §10.7。本文没有执行这些验收，也没有将旧方块验收视为新 Harbor pipeline 已通过。
