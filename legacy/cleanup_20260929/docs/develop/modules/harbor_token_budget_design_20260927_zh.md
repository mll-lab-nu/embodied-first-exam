# Harbor 共享 token 计量与预算控制方案

后续规划：2026-09-28 新建 [共享 pipeline 与 agent 适配子模块重构计划](usage_pipeline_agent_adapters_plan_20260928_zh.md)，明确拆分当前三种接线、通用配置、数据位置和迁移验收；本次重构尚未实施。下面保留初版设计与实施记录。

日期：2026-09-27。状态：**共享核心、observed 网关、三种 agent 适配、预算停止与方块验收 CLI 已实现，完成本地初步测试；Docker/GPU/真实模型验收待运行。strict 核心已测试，但实际 provider 能力尚未开放。** 本文保留 review 时的原始问题与设计目标；当前实现范围、限制与手动 CLI 以 [usage README](../../../topogym/agents/usage/README.md) 和本文 §11 为准。

本方案细化[原 Harbor 计划 §7.2 与 §10.6](harbor_shared_image_pipeline_plan_20260925_zh.md)。本次需求把默认额度明确为 **input 50,000,000、output 20,000,000，分别累计和判断**；不是 70M 的可互换总额度，也不是旧文中的 20M total 示例。

用户已指定新模块位于 `topogym/agents/usage/`，即 `/home/jianwen/topogym/topogym/agents/usage/`。这覆盖原规划中的 `topogym/usage/` 位置；模块的独立计量职责保持相同。

暂定每个 trial（一次 attempt）独立额度，包含全部模型、重试及子 agent 调用；同一 trial 的 segment、上下文压缩、进程重启和物理回溯不重置额度。task/job 共享额度作为可选上层范围。运行中允许管理端调整额度。这两项是本次规划的默认假设，待用户偏好确定。

## 1. Review 结果

| 位置 | 已确认的现状 | 对此次需求的影响 |
|---|---|---|
| `harbor_runners/usage_bridge.py:4` | 只接受 `{mode: off}`，未知用量为 null | 目前没有 token budget enforcement；显式限额会提前报错 |
| `harbor_runners/run.py:19` | 启动整个 `harbor run` 子进程，读取 stdout；人工中断给整个宿主进程组发信号 | 尚无按 trial 的模型请求检测与主动停止；stdout 静默时不能依赖该读循环做 watchdog；宿主进程退出也不能证明容器内 agent 已退出 |
| Harbor 0.23.0 `Trial._sync_agent_output()` | 运行结束／恢复阶段下载日志，再调用 `populate_context_post_run()` | 最终 AgentContext 可用于对账，不能直接充当实时计数器 |
| `topogym/agents/rollout/worker.py:115` | `cancel()` 每次覆盖 `stop_reason`；admin 只接受 finish/cancel，不能携带结构化预算原因 | 预算失败必须独立锁存，避免 verifier 的 finish 或后续信号覆盖它；需幂等终止协议 |
| `topogym/agents/rollout/worker.py:187` 与 `verify.py:78` | session/verifier 固定写 off 与未启用预算 | 必须注入受信最终预算快照，再封存归档 |
| `harbor_runners/rollout_output_report.py:14` | success_rate 只以 pipeline_passed 且 scoring_eligible 的记录作分母 | 接入预算后，如果继续用该分母，超限失败会被排除；正式预算成功率应把有效实验中的超限 trial 计为失败 |
| 原计划 §7.2 | 已规划独立 `topogym/usage/`、UsageSource、ledger、StopRequest | 沿用这一边界，不在每个 agent 中各写一套预算判断 |

三种已安装 adapter 的日志形态不同：Codex 解析 token_count 的 last/total usage，Claude Code 组合 input/cache read/cache creation，OpenCode 解析 step_finish，并把部分 reasoning/cache write 字段保存在 extra。必须按来源版本核对总量与分项语义，不能无条件相加各 adapter 的字段。日志文件如果可被 agent 改写，只能作为辅助证据，不能作为严格控制的唯一依据。

`topogym/agents/deferred/rollout/{token_budget,budget_proxy}.py` 有旧的请求前预留思路，但面向单一总额度、OpenAI Responses、单请求串行，并引用旧接口。仅参考其约束和测试场景，不恢复 deferred 执行链，也不把它直接视为多 provider 实现。

Review 时执行了：

```bash
.venv-harbor/bin/python -m pytest --confcutdir=tests/harbor tests/harbor -q
```

结果：52 passed in 0.37s。只证明现有 runner 合同通过，不证明新增计量或预算功能；未运行真实模型调用或 GPU 测试。

## 2. 共享架构与信任边界

```text
Harbor agent / 子 agent / 自定义 adapter
        │ 受控模型请求（绑定 trial 身份）
        ▼
请求网关 ── 申请输入/输出预留 ──► UsageLedger + BudgetController
        │ 放行后的请求                       │
        ▼                                   │ StopRequest
模型 provider ── usage 事件 ─► UsageSource ────┘
                                            ▼
                                  Harbor trial supervisor
                                  ├─ 拒绝新模型请求
                                  ├─ 取消请求与 agent 进程树
                                  ├─ 管理 socket 取消 policy
                                  └─ verifier / 失败结果 / 归档
```

核心建议文件为 `topogym/agents/usage/{types,ledger,budget,store}.py`，只接收事件、时钟、存储抽象并输出快照与停止决策。provider 协议解析放在 `topogym/agents/usage/sources/`；`service.py` 协调事件、健康、快照和政策更新，`gateway.py` 负责受控请求入口，依赖不能反向污染纯核心。`harbor_runners/usage_bridge.py` 负责身份绑定、生命周期、可信快照交付；新增 `harbor_runners/supervisor.py` 负责实际停止。

宿主 supervisor 与独立于 agent 的受信网关管理预算。真实 provider 凭据只留在网关；agent 获得绑定 trial 的临时凭据。安装阶段与运行阶段分别配置网络，运行时阻断绕过网关的模型端点。Harbor 的 external agent 可能在宿主发请求，也必须接入同一受控路径，不能只控制 Docker 内 CLI。

优先复用 Harbor 的生命周期 hooks、网络配置和自定义 adapter 扩展点；不修改 site-packages。若原生 CLI 入口无法提供 trial 监督控制，增加仓库内的 Harbor Python 启动入口，继续使用 Harbor 原生 Job/Trial 调度。先用兼容性测试确认具体接点，不假设 asyncio 取消等于容器进程终止。

“所有 agent 共用”指计量、预算和结果合同统一；不同 agent/provider 只适配取数、路由、输出上限和停止能力。不能通过拦截请求或可信事件覆盖的组合，在要求预算控制时 preflight 拒绝，不能悄悄改为 off。新协议、OAuth/订阅认证、WebSocket、远程子 agent、托管 server tools 均需独立证明覆盖后才开放。

## 3. 统计口径与账本

采用各模型 provider 报告的原生 token 数，不强行用一种 tokenizer 重算所有模型。相同文本在不同模型上的 token 数不同；这里统一的是口径和控制合同。

| 维度 | 口径 |
|---|---|
| input_tokens | 每次请求的完整输入累计：系统指令、历史、工具 schema、工具结果、多模态输入、缓存读写等，按该 provider 总量定义归一化 |
| output_tokens | 每次请求全部生成 token，包括 provider 已计入的推理、文本、工具调用与协议结构等；不按可见文字长度代替 |
| cache / reasoning | 明细字段；总量已包含时不重复相加。明细缺失为 null，不能当 0 |
| 重试 / fallback | 每次实际上游调用单独记账；同一请求的重复 usage 事件不重复记账 |
| 子 agent / 辅助模型 | 汇入同一 trial，保留 parent_request_id 与 agent/model 维度便于分析 |
| 工具 / 物理操作 | 工具返回内容再次进入模型时计 input；纯 shell 和物理 tick 本身不算模型 token |
| 不完整用量 | 保存已确认部分、未结算预留、覆盖状态及原始凭证引用；不得补 0 或标预算通过 |

来源映射须版本化。例如 Claude Messages 的输入总量需组合 input、cache creation 和 cache read；OpenAI 已包含在 input/output 总量中的 cache/reasoning 明细不再加一次。字段缺失、累计计数回退、口径冲突均进入显式异常状态。

事件包含 `scope_id/trial_id/request_id/upstream_attempt_id/source/event_id/sequence`、来源与采集时间、计数语义（delta 或 cumulative）、确认状态和细分字段。同一上游请求选择一个权威来源，CLI 日志与 provider receipt 做对账而非累加。不能按 prompt hash 去重真实调用：相同 prompt 的两次生成仍可能各自消耗 token。

首版采用单写入者与 SQLite 事务持久化，另导出 JSONL 事件和原子 JSON 快照。预留在转发请求前持久化；事件接收后同步判断预算，不等待 UI/快照刷新。累计事件以同一请求的差值更新，最终结算替换在途估计并释放剩余预留，不能再加一遍流式累计量。恢复时重放不重复结算；无法确认的在途请求保持预留并停止新请求。

## 4. 时间粒度与保证范围

| 检查点 | 处理方式 | 能保证什么 |
|---|---|---|
| 每次请求转发前 | 原子检查双额度、占用预留、约束最大输出 | 有可验证输入上界及 provider 输出限制时，阻止会越界的请求；并发不能各自占用同一剩余额度 |
| 每个可信 usage 事件 | 同一处理路径立即更新账本并判断 | 最早在收到该事件时发现超限；不等 segment/turn/trial 结束 |
| 每个流式内容事件 | 可记录可见文本估计，与精确计量分开 | 不把 chunk 当 token，不从可见文本推断隐藏推理；估计不能授予严格资格 |
| 请求完成 / 断流 / provider 错误 | 最终结算或标记不完整，拒绝不明用量后的新调用 | 避免遗漏部分已消费请求，错误重试仍需重新占用额度 |
| 独立 watchdog | 建议 100ms 周期检查计量器心跳和停止状态 | agent 不输出日志、等待工具或模型时，管理端仍可工作 |

初步性能目标：可信事件进入计量器后，预算判断及停止指令发出 P99 ≤100ms；本地 agent/policy 停止目标 ≤1s。它们是待压测的目标，不是已经满足的保证。归档和视频封存单独计时，不算停止计算完成；单次不可中断的物理/GPU 调用可能需要更长时间，超出停止期限则强制终止相应 trial 并报告证据不完整。

必须分别记录 `provider_event_at`（可得时）、`received_at`、`decision_at`、`cancel_sent_at`、`agent_stopped_at` 和 `worker_stopped_at`。本地耗时用单调时钟，来源时间仅作关联；不同机器时钟不能直接当作可靠延迟测量。

官方资料确认的限制：

- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)：流式精确 usage 在最后一条 SSE 中返回。频繁检查文件无法消除这段来源延迟。
- [Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)：message_delta 的 usage 是累计值，不能逐事件直接相加；有流式文本不代表逐 token 精确 usage。
- [OpenAI token counting](https://developers.openai.com/api/docs/guides/token-counting)：可请求输入计数，最大输出限制覆盖非可见 token；只数输出文本无法代替正式 output usage。
- [Claude token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)：预先计数是估计值，且部分输入/托管工具不受该接口支持。固定百分比余量不能自动成为数学上可证明的输入上界。
- [Claude prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)：缓存用量有独立字段，来源归一化必须处理这一差异。

因此保留两种执行资格：`observed` 在最早可信超限事件后强制停；`strict` 额外要求请求前有可验证的消费上界和完整流量控制。共同使用同一个核心和停止通道。不能同时对任意黑盒 agent 承诺“每个 token 实时精确可见”和“服务端零超额”。

在 observed 下，超出量由来源延迟、在途请求和停止延迟决定；没有各请求的消费上界时，不声称一个固定 token 超出上限。strict 的上界保证只在所验证的输入/输出及工具调用合同内成立。断开连接也不等于服务端立即停止计费，终止后仍应接收可得到的最终 receipt。

## 5. 双额度预留与边界

对每个维度分别维护 `confirmed`、`pending_reservation` 和 `remaining`。`pending_reservation` 表示尚未计入 confirmed 的剩余占用，防止部分 usage 到达后重复占用。

```text
remaining_input  = input_limit  - confirmed_input  - pending_input_reservation
remaining_output = output_limit - confirmed_output - pending_output_reservation

admit(request) 必须原子检查输入和输出两个维度。
```

请求输入上界超出 remaining_input 时拒绝。输出上限取调用方请求值、provider 约束和 remaining_output 的允许值；如果小于模型/思考模式所需最小值则拒绝。并发请求一律先原子预留再发送；允许排队等待在途结算，不能因为额度暂时被预留就错误判为实际超限。

额度视为包含端点：`used > limit` 为 `budget_exceeded`；刚好等于限额并且不再调用模型可以完成。下一次调用无可用额度，或其最小需要量放不下时，以 `budget_exhausted` 结束失败。若实验希望“达到即失败”，应单独改明确合同和边界测试，不混用比较符。

使用实际 receipt 完成结算；中断后未知消费保留未结算预留，标记 `usage_incomplete`。确认未发送的请求可释放预留；已发送但未知的请求不能因超时自动释放。对账发现 provider 用量超过预留时立即停止，并记录 `reservation_violation` 与实际超出量。

为减少预算接近上限时的浪费，可使用已验证的输入上界预留；只有估算值的来源保持 observed。严格模式可选择可信的保守最大输入上界，代价是额度利用率较低；没有上界就拒绝 strict。复杂 server-side loop、自动压缩与非生成计量端点也必须声明覆盖，不能靠客户端一次请求的输出 cap 推定整个服务端流程有界。

## 6. 强制终止和失败结果

停止必须在管理侧执行，不能依赖 agent 自己读取提示后退出：

1. 在账本事务中锁存首次预算失败、维度、快照、政策版本和时间，并关闭该 scope 的新请求入口。
2. supervisor 收到幂等 StopRequest；撤销 trial 临时模型凭据，取消在途请求，并封闭新 policy 提交。
3. 同时停止 installed CLI 进程树或 external agent 任务，以及正在执行的 policy。优先使用受控进程组／cgroup；不只 kill 最外层 shell，也不直接结束整个 job。
4. worker 在当前物理步安全边界停止，不再进入下一步。短宽限期后仍未停止则强制终止该 trial 容器，记录实际终止范围和证据缺口。
5. 收尾流程有界运行：补齐可获得的 usage、封存已有物理证据、生成 verifier reward=0、归档。无法运行容器内 verifier 时，由宿主生成明确的失败记录，保留最后可信用量和未完成归档状态。

`budget_exceeded` 等终态不可被 `agent_finished`、超时、迟到成功或后到 usage 改回成功。并发发生的其他错误作为次级事件保留。只有首次有效终态转换拥有成功/失败决定权；成功发布之前关闭该 trial 新模型入口并核对无未结算用量，避免“先成功后补出超限”。

扩展 admin 协议接收受信的 `reason/stop_id/usage_snapshot_ref`；保持 root-only socket，预算逻辑不下沉到 simulator 物理核心。当前 worker 会退出主进程，具体停 agent 和封存日志的顺序必须在真实 Harbor 容器中验证，不能只测试 Python 协程被取消。

建议结果包含：

```json
{
  "outcome": "failed",
  "failure_reason": "budget_exceeded",
  "exceeded_dimensions": ["input"],
  "reward": 0,
  "budget_qualified": false,
  "usage_complete": true,
  "usage": {"input_tokens": 50000123, "output_tokens": 19000000},
  "limits": {"input_tokens": 50000000, "output_tokens": 20000000},
  "overshoot": {"input_tokens": 123, "output_tokens": 0},
  "policy_revision": 1
}
```

这里是完整 receipt 的示例；实际未结算时 usage_complete=false，不能把示例当默认值。保留 simulator 原始 task_success 作为物理事实，但预算失败时实验结果始终失败。Harbor 原生结果、verification、rollout_index、summary 和 CLI 非零退出须一致。超限不自动重试。

正式预算成功率以具有有效评测资格的计划 trials 为分母，超限属于其中失败；基础设施故障另列，不静默丢掉。归档完整性与实验成功分开：预算失败也可以有完整归档。保留旧 success_rate 的含义或明确版本化，避免无提示改变历史报表。

## 7. 配置和运行中修改

已实现的 observed 配置（strict 仍会在当前 provider preflight 拒绝）：

```yaml
usage:
  mode: observed
  scope: trial
  limits:
    input_tokens: 50000000
    output_tokens: 20000000
  on_usage_unavailable: fail
  watchdog_interval_ms: 100
  stop_grace_ms: 1000
```

要求严格额度的实验显式用 `mode: strict`，preflight 按 agent/provider/协议/认证组合验证能力；不能自动降级。off 继续保持原行为，并拒绝 off+limit。

启动前经 YAML/CLI 设定，冻结到 experiment.resolved.json。运行中走管理端更新命令，采用版本号和事务校验；不直接修改被冻结的 task/job 文件。记录旧额度、新额度、操作者、修改原因、生效时间和 policy revision。公开的 `/rollout/budget.json` 只读，展示确认值、预留、限额与覆盖状态。

下调到已确认用量以下立即终止；下调到“已确认 + 在途承诺”以下，在严格模式下立即关闭新入口并取消受影响在途请求，明确记录已有承诺可能仍会结算，不能宣称新限额可追溯保证。新限额仍能覆盖已确认用量与全部在途承诺时继续正常执行。已经因预算失败的 trial，即使后来提高额度也不复活；新 attempt 使用新的身份。

若增加 task/job 总额度，所有相关 scope 的预留要在同一事务或具有等价原子性的服务中完成。trial 超限只停止该 trial；job 总额度超限停止其活跃 trials 并禁止调度新的 trials。

## 8. 实施顺序与验收

1. **独立核心与停止链路。** 先实现双额度事件/账本/存储/政策、预算结果合同，以及 trial supervisor 和 worker 幂等停止。用确定性 fake provider 与真实睡眠子进程验证；这是第一批交付。
2. **接通现有三个组合。** Codex + OpenAI、Claude Code + Anthropic、OpenCode + OpenRouter；优先开发 Responses、Messages、Chat Completions 协议来源，再补每个 agent 的端点路由与进程生命周期适配。原始 CLI 日志用于交叉对账。固定并记录 CLI/Harbor/协议版本。
3. **预留与严格能力。** 请求前计数／输入上界、输出限额、并发预留、重试/子 agent 覆盖、直连阻断及异常关闭；逐组合授予 observed/strict 能力。
4. **运行管理与报告。** 热更新、公开快照、usage JSONL、最终结算、归档和成功率统计；更新配置、instruction 和 README 的 off-only 描述。
5. **真实小额度验收。** 分别用小限额触发 input/output 停止，验证真实 provider receipt、停止延迟与超出量；另执行 §10 的真实方块抓取案例，每个 trial 的 input 上限为 3M、output 上限为 1M。任务成功、预算执行正确和故障测试通过分别验收；通过后才启用 50M/20M 正式默认配置。真实 API 测试遵循仓库已有显式启用入口。

必须覆盖的验收场景：

- input/output 独立的小于、等于、大于边界，下一次请求放不下、双维度同时不足。
- 增量/累计/重复/乱序/重连/迟到最终事件；不同来源重复上报；缺失字段不能当 0。
- 缓存读写、推理、图片输入、工具调用、上下文压缩、模型切换、真实重试与子 agent。
- 多请求争抢最后额度、部分使用后的预留更新、进程崩溃恢复、账本写入失败。
- agent 无输出、模型长时间思考、provider SSE 断流、网关心跳失联；没有输出不等于心跳丢失。
- 超限时 agent 正在请求模型、等待工具、执行死循环、policy 阻塞或物理步进行中；都须管理端主动停止。
- budget stop 与正常 finish/timeout 同时发生；失败原因不丢失、不重复归档、不自动重试。
- trial A 超限不误杀 B，job 总额度超限时关闭全部相关请求与后续调度。
- 强杀后的宿主失败结果、归档保留、后续 collect 恢复；正常结束前无在途未结算调用。
- 启动前不支持的能力拒绝，运行时直连/备用端点/远程模型路径不能绕过所声明控制范围。
- 无 Harbor、无 GPU 的独立核心导入/运行；核对 `topogym/__init__.py` 的传递导入，必要时惰性导出，避免宿主计量器被迫安装仿真依赖。

每个实际支持组合交付能力表：精确 usage 可用时点、输入预留依据、输出 cap 语义、子调用覆盖、取消方式、测试版本、停止延迟分布、最终超出量与账本完整性。只有合成事件测试通过时，不能声明真实模型预算已验收。

## 9. 拟修改文件清单

以下为实施范围，不表示这些文件已经修改或新增。本次只更新设计文档、主工程计划与模块索引。

### 新增共享模块

```text
topogym/agents/usage/
├── __init__.py                  # 公共接口，轻量导入
├── types.py                     # UsageEvent/Snapshot、BudgetPolicy、StopRequest、能力声明
├── ledger.py                    # 双维度累计、去重、在途预留与结算
├── budget.py                    # 边界判断、终态、限额修订规则
├── store.py                     # SQLite 事务、恢复、事件导出
├── service.py                   # 事件消费、独立心跳、快照、运行中配置更新
├── gateway.py                   # 临时凭据、请求准入、流式转发与取消
├── sources/
│   ├── __init__.py              # 来源接口及注册
│   ├── openai_responses.py      # Responses 协议计量及请求约束
│   ├── anthropic_messages.py    # Messages 协议及缓存字段归一化
│   └── chat_completions.py      # Chat Completions/OpenRouter 协议
└── README.md                    # 口径、独立使用、来源扩展与能力限制
```

### Harbor 接入与停止

| 操作 | 文件 | 修改目的 |
|---|---|---|
| 新增 | `harbor_runners/supervisor.py` | trial 生命周期监听、agent 进程树与 policy 取消、有界收尾；需要 Python 启动入口时在此承接原生 Job 调度 |
| 新增 | `harbor_runners/agents/usage_adapter.py` | 现有 agent 的网关端点、临时凭据与运行方式适配，不重复预算逻辑 |
| 修改 | `harbor_runners/usage_bridge.py` | 从 off 占位扩展为共享服务接入、trial 身份绑定及快照交付 |
| 修改 | `harbor_runners/config.py` | 双额度、模式、范围和监控配置校验 |
| 修改 | `harbor_runners/preflight.py` | 验证来源、路由、计数/输出上界及取消能力，拒绝无法满足的模式 |
| 修改 | `harbor_runners/task_generator.py` | 冻结预算配置，生成运行所需的网络、挂载与服务配置 |
| 修改 | `harbor_runners/run.py` | 启停监督器/计量服务，CLI 限额参数、查询与管理更新命令 |
| 修改 | `harbor_runners/agents/resolve.py` | 解析计量能力及 agent 接入配置 |
| 修改 | `harbor_runners/agents/credentials.py` | 区分网关真实凭据与 agent 临时凭据，覆盖脱敏 |
| 修改 | `harbor_runners/agents/scripted.py` | 为同一 cube_pick_place 场景增加无模型 Harbor 参考路径，复用已有被动策略 |
| 修改 | `harbor_runners/collect.py` | 归档用量凭证、预算失败与不完整结果 |
| 修改 | `harbor_runners/rollout_output_report.py` | 用量和停止延迟报告、预算失败计入实验失败次数 |
| 修改 | `topogym/agents/rollout/protocol.py` | 管理停止消息的结构化原因、幂等身份和校验 |
| 修改 | `topogym/agents/rollout/worker.py` | 停止原因锁存、可信快照接入、拒绝后续动作 |
| 修改 | `topogym/agents/rollout/verify.py` | budget failure 强制 reward=0，并在封存前纳入最终预算记录 |

### 包入口、配置与说明

- `topogym/__init__.py`：当前会立即导入 simulator，再间接导入 NumPy/SciPy。计划改为保留现有公共 API 的惰性导出，使宿主可独立导入 `topogym.agents.usage`。
- `pyproject.toml`：声明所需的可选 usage 依赖/入口并核对打包；现有 `topogym*` 发现规则已经覆盖新目录。
- `configs/harbor/{smoke_api,cast_coil_sweep}.yaml`：提供双额度设置；正式实验默认值在对应能力通过验收后启用。
- 新增 `configs/harbor/pick_cube_budget.yaml`：真实 cube_pick_place 抓起/放回案例，`evaluation: task_success`，每 trial input 3M / output 1M；与两段微动 smoke 分开。
- `configs/harbor/agents/profiles/{codex,claude_code,opencode_openrouter}.yaml`：具体来源/网关接入声明；自定义扩展模板位于 `agents/templates/{template_custom,template_env_http}.yaml`。
- `harbor_runners/templates/instruction.md`：同步公开预算快照的含义与失败规则。
- `harbor_runners/README.md`、`topogym/agents/README.md`、原 Harbor 计划与 rollout 协议文档：同步使用方法、最终目录和已验收范围。

`docker/Dockerfile.topogym` 已复制整个 `topogym/`，无需仅为新增 usage 目录修改。但本次新增方块例使用的 `tests/fixtures/cube_pick_place.py` 当前未进入镜像，需修改 Dockerfile 与 `.dockerignore` 的测试夹具复制/允许清单。`harbor_runners/config.py` 和 `rollout/worker.py` 同时扩展该测试 fixture 的校验/临时注册；preflight 校验镜像内夹具身份。新增宿主依赖时同步 `requirements/harbor-runner.lock`。`hooks.py` 和 `rollout/policy_process.py` 优先复用，若新增资源的恢复/清理或幂等终止需要扩展再列入实际改动。

### 测试与验收入口

- 新增 `tests/usage/{conftest,test_ledger,test_budget,test_sources,test_gateway,test_imports}.py`：fake provider/时钟、并发计量、双额度边界、来源口径、流式故障和轻量导入。
- 新增 `tests/harbor/{test_usage_bridge,test_supervisor}.py`：Harbor 生命周期接入、真实子进程强停及 trial 隔离。
- 修改 `tests/harbor/{test_runner,test_credentials}.py`：配置、冻结、结果汇总和凭据路径回归。
- 修改 `tests/contracts/test_rollout_service.py`：预算取消、停止原因竞态、失败结果与证据封存。
- 修改 `scripts/test_harbor_pipeline.py`：小额度真实停止测试入口、实际停止时间和最终 usage 的验收报告。
- 新增 `tests/harbor/test_pick_cube_budget.py`：核对新 case 的 fixture/config、3M/1M 参数、API 门禁、任务失败与预算失败分类，以及预算失败不能获得成功退出码；物理真值仍由既有 Task 与运行证据验收。
- 复用 `tests/fixtures/cube_pick_place.py`、`topogym/planning/examples/cube_pick_place.py`、`tests/contracts/test_cube_pick_place_policy.py`、`tests/contracts/test_cube_transfer_task.py` 和 `scripts/test_scripted_policy_rollout.py` 的场景、参考策略、正负判据及本地基线，不另造一套抓取实现。

原分批顺序仍作为设计依据；本次已推进至 service/gateway、三类协议、三种 native agent 适配及 CLI，实际完成项见 §11。真实 Docker/GPU/API 验收与 strict provider 上界验证仍未完成。

## 10. 新增真实方块抓取案例：input 3M / output 1M

### 10.1 案例定位与复用边界

用户要求：在真实 simulator rollout 成败接入及功能测试之外，再增加一个实际 pick 方块案例，用较小预算 input 3,000,000 / output 1,000,000 运行；需要用户手动运行的检查必须交付 CLI。

复用现有 `CubePickPlaceTask`（`tests/fixtures/cube_pick_place.py`）和 `CubePickPlacePolicy`（`topogym/planning/examples/cube_pick_place.py`）。任务是从默认 home 连续接近、抓起、持稳、原位放回、松爪、撤离并等待稳定。抓取例使用已有原位判据；`cube_transfer` 仍保持其空中搬运距离要求，不为新例降低原 Task 标准。

现状核对：

- 本地参考策略已有入口 `scripts/test_scripted_policy_rollout.py --case pick_place`，历史真实验收范围见[实施记录](../dev-logs/scripted_policy_execution_implementation_20260926_zh.md)。该策略使用获准 world 真值，按 unlimited 运行；不能把历史 scripted 成功视为新 agent 已成功。
- 当前 Harbor 只注册/打包 `cube_transfer`，`smoke_api.yaml` 的目标是 TCP 上下微动，且明确不抓方块。新案例须增加 `cube_pick_place` 的 fixture 接线及独立配置，不能直接改旧 smoke 的名字。
- 新案例必须真实经过 Harbor → agent → policy 提交 → worker → SegmentRunner → Genesis/Nyx → verifier/collect。宿主参考策略成功和 fake provider 通过都不能替代这条链路。

首版真实 agent 案例显式沿用 unlimited + `state_fields: [world]`、`enable_privileged: true`，保留 RGB 及实际录像。这样与已有 pick/place 基线保持可比较的观测条件；报告明确记录特权状态，`visual_reasoning_verified` 不因此变为 true。以后 limited 视觉抓取另设案例和资格。

agent 可以自行生成策略或复用公开样板，报告记录 `policy_origin` 与实际提交哈希。必须有真实模型调用和 provider 用量凭证；单纯运行 scripted policy 不算 API 预算案例。sample 是测试夹具，不增加生产任务 catalog，也不加入第二套物理/录制循环。

### 10.2 冻结配置与成功判据

已新增 `configs/harbor/pick_cube_budget.yaml`，其中关键字段如下；observed 配置和验收 CLI 已接入，真实物理/API 结果仍待运行：

```yaml
experiment: harbor_pick_cube_budget
image: topogym-rollout:usage-v1
agent_profile: agents/profiles/opencode_openrouter.yaml
attempts: 1
concurrency: 1
gpus: 1
timeout_sec: 1800
usage:
  mode: observed
  scope: trial
  limits:
    input_tokens: 3000000
    output_tokens: 1000000
  on_usage_unavailable: fail
  watchdog_interval_ms: 100
  stop_grace_ms: 1000
instances:
  - name: cube-pick-place-budget-seed0
    fixture: cube_pick_place
    evaluation: task_success
    mode: unlimited
    state_fields: [world]
    simulator:
      task_id: cube_pick_place
      robot_id: panda_robotiq
      variation_id: base
      seed: 0
      control_mode: EE_ABS
      enable_privileged: true
      compute_backend: cuda
      render_backend: nyx
      enable_rgb: true
      physics_dt_s: 0.025
      control_decimation: 1
      solver_substeps: 40
      max_physics_steps: 1000
```

实际文件还须提供明确的 pick/place instruction。时序沿用既有长程样例配置并单独记录，不等于 simulator 默认时序的资格；默认 home、Genesis + Nyx + compact_lab、三视角和共享 recording 沿用现有规则。参考基线和模型案例都记录 grasp assist 的实际配置，禁止静默更换辅助方式或更改阈值使样例通过。

每次 attempt 独立使用 3M/1M；重试、子 agent、压缩和同一 trial 的全部 segments 共用此额度。3M/1M 是主案例上限，不要求故意消耗完，也不替换正式实验 50M/20M 的默认目标。任务耗尽墙钟/物理时间的结果与 token 失败分开。

Task 判据来自受信物理状态和历史：方块底面离桌 ≥5cm、夹持稳定 ≥0.2s（沿用已有相对位置及夹爪条件）；随后原位放回误差 ≤2cm、桌面高度差 ≤3mm、线速度 ≤0.01m/s、角速度 ≤0.1rad/s，松爪撤离 ≥5cm，连续稳定 ≥0.5s。仅 TCP 上升、空抓、推方块、瞬时飞起或 agent 自述成功都不成立。阈值、fixture/model revision、镜像及源码哈希在运行前冻结。

### 10.3 分开验收的测试矩阵

| 层级 | 运行方式 | 必须证明 |
|---|---|---|
| F0：核心功能 | CPU、fake provider、真实可终止子进程 | §8 全部计量/预算/并发/恢复/热更新/取消合同；input/output 两项均有单独边界和超限测试 |
| F1：已有本地参考例 | 真实 GPU/Nyx、无模型 | 当前源码下抓起/放回 Task 成功、视频及物理证据有效；不授予 token/API 资格 |
| F2：Harbor 参考例 | 新 `pick-cube-scripted` case，真实容器/GPU、无模型 | 新 fixture、policy 进程和实际终态经 Harbor 完整通过；复用同一场景与参考策略，usage 明确 off |
| F3：3M/1M 实际 agent | 新 `pick-cube` case，真实模型/GPU | 真正执行抓取；分别得到物理结果、完整用量、预算结果、实验结果与录像 |
| F4：输入额度停止 | fake 确定性超限 + 真实小额度 `budget-input` case | 单独触发 input 维度；strict 可在请求前拒绝，observed 在确认越界时强停；不能由 timeout 代替预算原因 |
| F5：输出额度停止 | fake 确定性超限 + 真实小额度 `budget-output` case | 单独触发 output 维度，处理隐藏推理及最终 receipt；证明停止 agent/policy 和拒绝后续请求 |
| F6：生命周期及隔离 | 真实进程/容器，所需场景再接 GPU | 无输出/阻塞、断流、cancel/finish 竞态、失败归档、两个 trials 互不误杀、额度下调后立即停止 |
| F7：复用 | 同 agent 独立 attempts，再换其他 agent/provider | 使用同一场景/口径/失败合同；逐组合报告计量模式和覆盖，不能继承另一个组合的资格 |

F4/F5 使用明显低于 3M/1M 的专用额度，分别收紧 input 或 output；开发时依据请求大小/协议最小输出限制冻结测试值。由可控请求序列触发，保留真实 receipt，不要求模型自然输出到 1M，也不为预算测试浪费 3M 输入。需要模拟账本事件的测试必须标 synthetic，不能伪称真实消费。

strict 的预先拒绝为 `budget_exhausted`，实际已越界为 `budget_exceeded`，两者均必须得到失败 trial/reward=0；明确记录期望原因，不能只断言任意非零退出。达到限额但无需再调用时按 §5 的包含端点合同处理。

3M/1M 主案例只有同时满足 `task_success=true`、用量完整、预算资格通过和必要证据完整时才能标案例成功。预算控制正确但没有抓成功，保留 `task_success=false`，不能标案例通过；物理已成功但预算超限，实验仍失败。当前 `launch()` 主要以 pipeline 完整性决定返回码，新增验收入口须额外检查 Task 及预算，不能仅凭退出码 0 判抓取成功。

故障测试则允许 `expectation_met=true` 表示正确识别了预期失败，但底层 trial 的 outcome 仍为 failed、reward=0；故障验收脚本退出码与 trial 结果分别保留。模型不一定在 3M/1M 内完成抓取，未成功记录仍属于有效实验结果，不能通过自动增加预算、改为 off 或无限重试掩盖。

### 10.4 谁运行、何时交付 CLI

开发者先完成 CPU 合同、fake provider、独立进程终止和 CLI/schema 静态验收；可访问 Docker 时继续做容器检查。GPU/API 环境能执行时按既有显式入口验收；若当前环境缺少 GPU、Docker 权限或模型凭据，交付以下 CLI，由用户在具备条件的机器运行，再由开发者复核报告和录像。

本次已完成代码与初步测试，未启动真实模型或 GPU 仿真。下方新增 CLI 已与实际 `--help` 和 `--prepare-only` 参数测试核对，GPU/API 验收保持 pending；完整顺序与负例限制见 [usage README](../../../topogym/agents/usage/README.md)。

**当前可用的本地参考抓取命令（无模型、不验证预算）：**

需已有 `.venv-gs121-nyx`、CUDA、Nyx 和场景资产。在仓库根目录执行：

```bash
cd /home/jianwen/topogym
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py \
  --case pick_place --seed 0 \
  --physics-dt 0.025 --control-decimation 1 --solver-substeps 40 \
  --experiment pick_cube_reference_20260927
```

输出由现有驱动分配到 `task_rollouts/pick_cube_reference_20260927/cube_pick_place/rollout_<编号>/`，含 `run_report.json`、源码身份和录像。这是已有入口的命令核对，本次未运行它。

**以下为已实现、待用户运行真实验收的 Harbor 命令：**

`scripts/test_harbor_pipeline.py` 已提供 `pick-cube-scripted`、`pick-cube`、`budget-input`、`budget-output` 及 `--usage-mode`、`--input-token-limit`、`--output-token-limit`。保留 `--allow-api`、`--prepare-only`、`--agent-profile`、`--model` 和报告位置。新 API case 同样要求显式 `--allow-api`；prepare-only 不调用模型或 Docker。

开发完成后构建包含新 fixture 和预算接入的镜像，再做无模型 Harbor 参考验收：

```bash
cd /home/jianwen/topogym
bash scripts/setup_harbor_runner.sh
bash scripts/build_harbor_image.sh topogym-rollout:usage-v1
.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case pick-cube-scripted --image topogym-rollout:usage-v1 \
  --gpu-devices 0 --attempts 1 --concurrency 1 --seed 0 \
  --timeout-sec 1800 --run-id harbor_pick_cube_scripted_01
```

3M/1M 的实际 agent 命令如下。凭据由所选 profile 从 `.secrets/harbor.env` 读取；`TOPOGYM_MODEL` 由用户设为对应 agent 接受的模型 ID，OpenCode 需包含 provider 前缀。首个示例沿用项目已有 OpenCode/OpenRouter profile，不预先声称此组合已具备预算资格。

```bash
.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case pick-cube --image topogym-rollout:usage-v1 \
  --agent-profile configs/harbor/agents/profiles/opencode_openrouter.yaml \
  --model "${TOPOGYM_MODEL:?Set the model ID for the selected agent profile}" \
  --usage-mode observed \
  --input-token-limit 3000000 --output-token-limit 1000000 \
  --gpu-devices 0 --attempts 1 --concurrency 1 --seed 0 \
  --timeout-sec 1800 --run-id harbor_pick_cube_budget_01 --allow-api
```

先只检查配置时，将该命令的 `--allow-api` 换成 `--prepare-only`，并使用单独 run-id，例如 `harbor_pick_cube_budget_prepare_01`；正式运行再使用另一个未占用的 run-id。strict 仅在该 agent/provider 的能力检查与请求约束验收通过后显式选用，不能无提示替换模式。

输入/输出独立停止的命令如下。当前输入负例默认 1 / 1M，输出负例默认 3M / 1024；这些是真实 provider 待标定的初始参数。输出 case 会要求持续工具调用，若模型提前退出或拒绝过小输出 cap，测试会明确失败，不以任意异常代替预算验收。实际额度在冻结配置中可见，使用两项 token-limit 参数覆盖。

```bash
.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case budget-input --image topogym-rollout:usage-v1 \
  --agent-profile configs/harbor/agents/profiles/opencode_openrouter.yaml \
  --model "${TOPOGYM_MODEL:?Set the model ID for the selected agent profile}" \
  --usage-mode observed --gpu-devices 0 \
  --attempts 1 --concurrency 1 --seed 0 --timeout-sec 1800 \
  --run-id harbor_budget_input_01 --allow-api

.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case budget-output --image topogym-rollout:usage-v1 \
  --agent-profile configs/harbor/agents/profiles/opencode_openrouter.yaml \
  --model "${TOPOGYM_MODEL:?Set the model ID for the selected agent profile}" \
  --usage-mode observed --gpu-devices 0 \
  --attempts 1 --concurrency 1 --seed 0 --timeout-sec 1800 \
  --run-id harbor_budget_output_01 --allow-api
```

首轮单次通过后，换新 run-id，使用 `--attempts 3 --concurrency 1` 检查重复隔离；3 次各自拥有 3M/1M，不是共用。更换 Codex/Claude Code 时同步 profile、模型 ID 与凭据声明，保留同一实例和额度。

### 10.5 报告与交付要求

Harbor 新案例产物沿用：

- `runs/test_results/<run-id>/report.json`：测试状态、任务成败、预算控制是否通过、expected failure/expectation_met、报告与录像链接。
- `runs/harbor/<run-id>/`：冻结配置、模型/CLI/镜像/源码身份、原生 Harbor trial 结果、受信用量账本与事件、停止延迟、最终汇总。
- `task_rollouts/<run-id>/cube_pick_place/rollout_<编号>/`：完整/部分动作段、三视角视频、物理证据、最终预算快照与归档清单。

报告至少保存实际 input/output、双额度、cache/reasoning 明细可用性、usage 完整性、模式与覆盖声明、终止维度/原因、在途请求、超出量、停止各阶段时间，以及 agent 子进程/policy 是否确已退出。实际字段名在 §3/§6 合同落地时固定。

测试报告和源码/配置身份在启动模型/仿真前创建。真实录像使用共享 recording，从 home 连续记录，失败也保留已完成证据。开发者核对结果后分别标记 implemented/cpu_validated/gpu_validated/api_validated；手动命令未跑或预算能力未实现时维持 pending，不能因为历史抓取成功或新文档写完就报告新增验收通过。

先前计划阶段仅完成文档语法及旧入口核对；以下是本次开发后的实际状态。

## 11. 初版实施与初步验证（2026-09-27）

已实现 `topogym/agents/usage/` 的类型、SQLite 账本、事件去重、双额度、版本化热更新、来源归一化、HTTP/SSE 网关与容器 relay。每个 usage 事件同步判定；默认 100ms watchdog，根身份刷新公开预算文件并在宿主心跳丢失后取消本地执行。真实 provider 凭据保留在宿主，使用 Harbor 原生阶段网络控制和临时 trial 凭据；只支持本机 Linux Docker。

Harbor 通过仓库内 `UsageAgent` 组合原生 Codex、Claude Code、OpenCode adapter；继续由原生 Job/Trial 调度。Responses（含 compaction）、Messages、Chat Completions 均有确定性协议测试。运行结束前关闭新请求入口；预算失败时终止 agent UID 进程、root admin 取消 policy，宽限期后升级为当前 trial 容器停止。原生 adapter 收尾不能绕过已经关闭的执行入口。worker 锁存预算原因，verifier 强制 reward=0；收集器保留容器丢失时的宿主失败记录。

新增方块配置及四个 CLI case 已通过 `--prepare-only` 与参数门禁测试；镜像复制 cube_pick_place 及其基础 fixture，preflight 核对 fixture SHA。`pick-cube` 要求物理成功和预算通过，不能以 pipeline 完成代替任务成功。CLI、测试启动报告、额度更新、归档和预算成功率已接入。依赖仅用标准库，未增加宿主 SDK/依赖锁；沿用原生 provider profile 与凭据加载逻辑。

本地验收结果：

| 范围 | 实际结果 | 不代表什么 |
|---|---|---|
| usage + Harbor：账本、fake HTTP/SSE、真实 Unix gateway、host-loss watchdog、原生 adapter 路由/生命周期、进程组强停、配置/CLI/归档/报告 | **126 passed，0 skipped** | 不代表真实 Docker 网络或 provider 已通过 |
| rollout IPC、运行中真实 policy 子进程预算取消、停止原因竞态、迟到物理成功仍记失败、现有方块 policy/Task 合同 | **26 passed，0 skipped** | CPU world 合同，不是 Genesis/Nyx 物理验收 |
| SQLite 可信 receipt 更新事务，100 个样本 | 中位数 **2.87ms**、P99 **6.77ms**；最后一次事件进入账本至超限决定 **0.225ms** | 不含 provider 来源延迟、Docker 命令与 GPU 停止时间 |
| 真实 Docker / GPU / API | **pending** | 本轮未调用付费 API、未重建镜像或启动真实抓取 |

报告和对应源码 SHA-256：[report.json](../../../runs/test_results/harbor_usage_20260927/report.json)，原始测试记录 [host.xml](../../../runs/test_results/harbor_usage_20260927/host.xml)、[rollout.xml](../../../runs/test_results/harbor_usage_20260927/rollout.xml)。最初沙箱执行遇到本地 socket 权限限制；在允许本地 socket 的测试环境重跑后以上测试全部通过。回归期间修复了 policy 关闭时的 BrokenPipeError、响应 socket 取消与重复关闭问题。

剩余资格：strict 核心预留已测试，但实际 provider 缺乏经过验证的输入上界，preflight 明确拒绝；不声称 observed 零超额或每个生成 token 都有实时精确计量。其他 agent / OAuth / WebSocket / provider 托管工具等必须增加受控适配后才能启用。100ms 决策/1s 本地停止仍为真实部署验收目标；仅本地账本测试不能证明整个链路已满足。

用户手动顺序：重建镜像 → `pick-cube-scripted` → `pick-cube` 3M/1M → `budget-input` / `budget-output` → 另两个 agent 组合及重复 trial。完整可执行命令、输出负例尚待标定的 1024 cap、结果位置及热更新示例见 [usage README](../../../topogym/agents/usage/README.md)。
