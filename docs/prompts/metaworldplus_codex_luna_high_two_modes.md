# MetaWorld+ 全量评测执行 Prompt：Codex / GPT-6 Luna / high / 60 分钟

请直接实施并完成下面的评测，不要只给计划。本次只运行 MetaWorld+。沿用本仓库此前 VLABench 的评测流程：全量清单冻结 → 两种模式配置 → oracle/nop 与隔离验收 → 模型接入 smoke → 首个正式实例 → 全量单次正式评测 → 独立重放 → 耗时和用量汇总 → Markdown、离线网页及视频包。

“沿用”指评测纪律、时间预算、单次尝试、证据和交付形式一致；MetaWorld+ 的观测、控制、初始状态和原生成功判定必须按其实际实现适配。不要把 VLABench 客户端或动作格式直接复制过来，也不要把旧 smoke 当作本次 high 配置的验收。

## 1. 范围、仓库和保护要求

- 仓库：`/home/changhe/projects/robot_coding_bench`。先确认实际路径，阅读适用的 `AGENTS.md`、`README.md`、`docs/PROTOCOL.md`、`CONTRIBUTING.md`。
- 阅读 `docs/ROBOT24.md`、`docs/ROBOT24_API.md`、`docs/BENCHMARK_COVERAGE.md`、`suites/metaworldplus.json`，以及实际任务的 instruction、task.toml、runtime、solution 和 verifier。可信主控可以读 oracle，正式受测 agent 不可以。
- 参考 `docs/VLABENCH_CODEX_SUBSCRIPTION.md`、`docs/VLABENCH_LIMITED.md`、`scripts/vlabench/run_codex.py` 和 `scripts/vlabench/codex_subscription/` 的已有实现。阅读相应验证报告，区分已经验证的能力与尚未正式运行的实验。
- 不查找或依赖 `ROBOTWIN_TASKS_AND_TWO_MODES.md`；本 prompt 是本次模式要求。
- 保留所有历史任务、评测、视频和网页，包括 VLABench、旧 MetaWorld+、unlimited、limited 及其他 benchmark。不要删除历史结果，不要重命名历史成绩为本次结果，不要干扰其他正在运行的作业。
- 新增 MetaWorld+ 专用入口和独立实验目录；按仓库协议生成自包含的任务副本，不覆盖源任务。运行目录建议 `jobs/metaworldplus-codex-luna-high-60min-<UTC时间>/`，两种模式分开存储。
- 只覆盖当前仓库中属于 MetaWorld+ suite 的全部任务和已定义实例；不要顺带运行 VLABench、RoboCasa、RoboPaint 或旧的独立 `metaworld-button-press-i00`。是否属于 suite 以元数据、清单及实际实现交叉核对，不只凭名字。

## 2. 模型、agent、认证和 high 设置

- 正式受测 agent 使用 Codex，模型必须是 `gpt-6-luna`，reasoning effort 必须是 `high`。
- 使用已经接好的 **Codex + ChatGPT 订阅登录**。不要使用 Terminus-2，不要使用 OpenRouter，也不要使用 OpenAI API key。此前对话中的 API key 不适用于本次实验，禁止复制到文件、环境配置、日志或报告。
- Harbor 的模型名优先沿用当前适配器使用的 `openai/gpt-6-luna`；核对实际版本如何映射到 Codex 的 `gpt-6-luna`。这个 provider 前缀本身不能证明请求走 API 或订阅，必须核验认证模式和运行证据。
- 优先复用仓库的 `SubscriptionCodex` 适配器与隔离出口机制，保持 Codex 原生 agent 循环。记录真实 agent 类/import path，不能仅在报告中写 `-a codex` 却实际运行其他 agent。
- **现有 VLABench Codex 入口有 `reasoning_effort='medium'`。本次必须在新的 MetaWorld+ 配置中显式设为 `high`，不要原样继承。** 核对当前 Harbor/Codex 支持的实际参数，使最终 Codex 配置为 `model_reasoning_effort = "high"`；不要只在自然语言提示中要求“多思考”。
- 在 smoke 和每次正式 trial 保存不含凭据的生效配置及可取得的原生日志证据，确认模型、high、认证通道和 agent 版本。请求不支持该模型或 high 时停止派发新 trial，报告具体问题，不降级模型或 effort，不切回 API。
- 静默检查 ChatGPT 登录状态；登录材料仅通过已有私有临时注入机制交给 main。不得写入镜像构建上下文、任务目录、sim、产物或离线包；不得打印 token 或整个登录 JSON。
- 如果登录失效，完成无需认证的工作，再请用户通过安全的交互登录恢复。不要要求用户把凭据贴进聊天，不覆盖宿主机已有登录配置。
- 清理本次子进程中可能引导 API-key 认证或自定义 API base 的变量，保持宿主机配置不变。复用已有仅允许订阅所需目标的 TLS CONNECT 代理并实际检查；代理不记录授权信息或请求正文。
- 固定并记录 Harbor、Codex 二进制及 companion helper、模型、reasoning effort、镜像 digest 和适配器指纹。正式阶段不自动升级工具或依赖。

## 3. 明确授权使用其他 agent 监控

请创建并使用独立的监控/审计 sub-agent，主控负责实现与唯一的正式任务派发：

1. **运行监控 agent**：只读检查 trial 进程、容器健康、agent 计时、心跳、CPU/内存/磁盘、订阅额度或鉴权异常、完成和排队数量；持续向主控报告异常。
2. **评测审计 agent**：只读核对全量覆盖、seed/实例哈希、两种模式边界、实际模型与 high、一次正式尝试、重放证据、tokens 汇总及视频链接；提出问题供主控处理。

监控 agent 在受测容器之外工作，不是受测 Codex 的助手。不得向受测 agent 提供解题代码、物体位置、隐藏成功信息、oracle 动作或跨 trial 经验；不得操作机器人、reset、改评分或发起额外正式尝试。每个受测 trial 使用独立上下文，不能读取另一模式或另一 trial 的对话与解法。

监控可以读取可信侧日志，但只能向主控反馈，不能把隐藏信息注入受测 agent。监控所用模型和 tokens 单独记录，不计入受测模型用量。

硬超时由宿主机/Harbor/sidecar 的可靠计时与进程控制实施，不能依靠监控 agent 的定期对话来保证。根据环境能力持续监控，至少在 trial 开始、结束和异常时留存事件；主控定期提供总进度，避免无意义高频轮询。

如果当前执行环境没有 sub-agent 工具，明确说明限制，使用独立只读监控进程和结构化日志完成可实现的监控，不要声称已启动其他 agent。

## 4. 全量清单与固定实例

自动枚举 task.toml、suite/manifest、相关 staging 及已有模式目录，核对属于 MetaWorld+ 的任务与实例。2026-09-28 的仓库检查发现 `tasks/metaworldplus-*` 与 suite 一致：**50 个任务族、70 个 privileged 实例**；这只是核对基线，不是筛选白名单或固定上限。运行时重新枚举，解释任何增减。

输出并保存完整 JSON/CSV/Markdown 清单，至少包括：任务族、原生 environment ID、源任务目录、task ID、实例 ID、真实 seed、初始实例 SHA、源任务 digest、原模式、两种新模式目录、资产与镜像需求、原生控制步上限、预检状态和不能运行的具体原因。

- 保持原有 seed、冻结初始状态、任务条件、对象、目标、机器人、物理参数和成功判定。instance index、demonstration index 和 seed 是不同字段，不能相互代替。
- 同 ID 且内容完全相同的目录别名可以去重，但必须保存映射；不同 seed 或配置的实例不得合并。
- 为每个发现的实例分别建立 unlimited 和 limited 记录。原仓库只有 privileged 时，生成同初始实例的 limited 派生版本，不把“尚无 limited 目录”视为已经评测。
- 缺资产、原生故障、空任务指令、无法可靠评分或无法提供不泄密的必要观测时，记录错误、排查证据和受影响模式，标记未评测并保留在总分母。
- 不重新采样更容易的 seed，不创建额外简单实例替代失败实例，不仅运行容易成功的任务。
- 冻结 git HEAD、工作区差异/源码快照哈希和所有实际使用文件指纹。当前仓库可能有未提交文件，仅保存 git commit 不足以复现。

## 5. MetaWorld+ 原生接口适配

本仓库 MetaWorld+ 是基于 Meta-World v3/reward-v2 的 suite 名称。先以代码核验版本和以下现有行为，再形成两种模式的公开 API 文档：

- 当前 privileged API：`from mw_runtime import Session; s = Session()`，没有 VLABench 的参数约定，也不要假设 `Session(render=True)` 可用。
- 原生动作是四维 `[dx, dy, dz, grip]`，范围 `[-1, 1]`；XYZ 位移比例 0.01 m，固定腕部，正 grip 关闭。
- 当前物理 timestep 为 0.0025 秒，frame_skip 为 5，即 80 Hz 控制。控制步和物理步分别统计，不能把两次 verifier 重放的步数加总当作在线 episode 的步数。
- 当前轨迹上限为 500 个控制步。核对每个任务实际原生终止和 horizon，保留单 episode/提交轨迹约束；60 分钟墙钟预算不等于可以突破物理步数上限。
- 原生判定采用轨迹中的 ever-success，不以 dense reward 或最后一帧看起来正确代替。limited 服务应在达到原生成功或其他终止条件时封存该 episode；独立 verifier 保持同一原生判定语义。
- privileged 的 goal-observable 模式需要正确处理 `sawyer_observation_space` 缓存，防止目标被错误裁剪为 0。
- 当前 `observe()` 包含原生 observation、目标、body 真值及其他内部量，**不能直接作为 limited 的 observe 返回值**。原生 observation 及其历史部分可能泄露物体或目标坐标，必须逐字段审计。
- 当前 MetaWorld Session 还有 reset 40 次、累计 16000 控制步等实现级限制。区分这些探索预算与原生单 episode 的 500 步上限：为本次 unlimited 派生版本去掉额外 reset/累计探索配额，保留计数及原生单轨迹上限，并记录这个版本差异。不要原地修改历史任务。

## 6. Unlimited / privileged-state 模式

- agent 可以读取任务允许的完整 privileged state：机器人状态、物体真实位置和姿态、公开目标及已有状态查询接口。
- 可以编写控制代码，使用现有通用 primitive/skill，例如 agent 指定目标位置的比例控制；可以多次 reset 到**完全相同的初始实例**，record、replay、观察和调试。
- 不额外限制模型调用次数、tokens、reset 次数或累计探索步数；所有探索均受同一个 60 分钟墙钟限制。保留每条原生 episode/提交轨迹的物理步数上限。
- 不提供完整任务专家策略、oracle 轨迹或一键完成任务接口；不得传送物体、直接写在线仿真状态、修改 checker/runtime 或伪造 reward。
- 最终提交符合当前协议、绑定原实例 SHA 的轨迹。只有最终提交轨迹经可信 verifier 独立重放后的结果参与成绩；探索中成功过但未提交有效轨迹不算成功。
- 原生公开调试反馈按现有 privileged 任务契约提供；独立 verifier 的隐藏结果在 agent 结束前不可见。
- 跨 reset、多个 Session 和子进程汇总 reset、动作和物理成本，不能只拿最后一个 budget.json 代表总成本。分别记录探索总成本与最终轨迹长度。
- 复用现有 privileged 架构时，如其同容器 root 权限不具备强防篡改隔离，应如实记录限制；不要声称其具有 limited sidecar 的安全边界。

## 7. Limited / 单连续 episode 模式

### 容器和公开接口

- `main` 仅包含 Codex、轻量 client 和必要依赖；`sim` sidecar 独占仿真器、资产、实例、seed、真实状态、原生成功判定和完整轨迹记录。
- main 只通过 `spec()`、`observe()`、`step(action)`、`status()` 四个公开方法与 sim 交互；没有 reset、恢复快照、重新初始化或另一实例入口。主控启动/封存接口必须处于 main 无法访问的控制平面。
- main 不挂载仿真源码、实例配置、oracle、sidecar 数据目录、宿主机文件或 Docker socket；无特权、禁止提权，网络只允许受控仿真接口和必要订阅出口。
- 实际验证隐藏端点、旁路端口、文件路径、进程、reset 及任意公网访问均不可达。不能仅靠 client 不展示某个方法。

### 观测与动作

- 允许公开任务语言、RGB 图像、实际可用的相机内外参，以及机器人关节、夹爪、末端等允许的 proprioception。记录单位、坐标系和图像获取方法。
- Codex 必须能通过原生图像工具查看 `observe()` 产生的真实图像；不能把图片路径当作已经看到图像，也不复用 Terminus 特有的 RGB bridge。
- 禁止物体/目标真实位姿、原生隐藏 observation、seed、实例配置、分割/语义真值、仿真内部状态、专家策略/轨迹、成功谓词、隐藏 reward 和阶段进度等泄露。相机标定不能夹带物体或目标真值。
- 对目标位置或任务目标，优先沿用原生公开可视标记和已有任务语言；如某实例移除 privileged 信息后无法确定目标，先调查可用观测。无法在不更改任务、不泄密的条件下解决时，标为未评测，不能编造提示或静默改变任务。
- `step(action)` 服务端严格检查四维形状、数值有限性及范围；拒绝非法动作，不默默裁剪。不得提供按物体 ID 抓取、自动选抓取点、物体传送或专家策略端点。
- 服务端顺序执行动作并记录其真实推进步数；异常动作若已推进物理，也必须进入完整记录。无效且未推进的请求仍记录事件并注明 0 步。

### 连续性、终止和封存

- 一次 trial 只有一个连续 episode。所有观察、思考、失败动作和调试都发生在这个 episode 内。
- 每个控制步后由 sim 私下检查原生成功与终止；达到成功、horizon、原生终止或超时后拒绝进一步动作。公开 status 可以告知仍可操作或已结束及公开计数，不泄露隐藏判定详情。
- 重启 client、重新连接、新建 Session、并发请求或重启 agent 都不能获得新 episode、重置计数或延长 deadline。
- Agent 结束或超时后，可信主控停止其进程和后台任务，由 sidecar 封存并导出**从初始状态开始的完整服务端轨迹、事件和状态证据**。不接受 agent 自选成功片段或自己写的“成功”声明。
- 正式成功要求：在线 episode 达到原生成功、完整轨迹在两个独立新进程从同一初始实例重放均成功、重放与在线可信记录可复现，并且 trial 未超时。

## 8. 时间预算、尝试次数和资源

- 两种模式每个实例均只运行 **1 次正式尝试**；每次 agent 上限 **3600 秒（60 分钟）**。不额外设置人为 token、模型调用或 turn 配额；如工具自身有不可取消的限制，记录实际限制，不能伪称无限。
- 计时从仿真服务就绪、agent 安装/认证准备完成且被允许操作的时刻开始。观察、模型思考、代码、控制、reset、调试和模型请求等待都计入；镜像构建、冷启动、结束后收集和 verifier 重放不计入。
- 将 monotonic deadline 与 UTC 起止时间同时记录。超时立即阻断新动作并终止受测进程，有限时间内可信封存。不得等一个长工具调用结束才认定 deadline。
- Timeout 是独立最终类别；事后重放成功或最后时刻的临时成功不能把已超时 trial 改成成功。保留 raw verifier 分数与最终裁决，解释差异。
- Verifier 单独限时。读取 MetaWorld+ 各任务当前配置并冻结合理的总超时及每个 worker 超时；现有示例为 verifier 1900 秒、单 replay worker 300 秒，不能直接用 VLABench 常数覆盖。任何调整在正式运行前说明依据。
- 默认串行正式评测，避免订阅额度和 CPU 渲染争抢。只在有资源证据时增加并发；记录资源配置和排队时间，不让多个 trial 的争抢改变有效预算。
- Harbor attempts=1，正式 trial 自动重试关闭。进程中断后不得重启同一 episode；保留已有尝试及故障证据。
- 如订阅限额、鉴权或模型不可用，暂停派发新 trial，保留待运行清单；运行中的 deadline 不暂停。恢复条件未满足时，明确报告阻塞，不能把未启动项当作模型失败或宣称全量完成。

## 9. 按顺序实施和运行

1. **只读审计与清单冻结**：完成上述源码、协议、实例和版本检查，输出完整范围与两种模式的适配差异。建立唯一 trial ledger，保存源目录与新目录映射。
2. **实现一个稳定实例的两种模式**：复用已有 Codex 订阅/隔离实现，新增 MetaWorld+ 专用入口；确认 high 真正传入。保持原始任务条件不变。
3. **无正式模型成绩的验收**：可信 oracle 应得 1，nop 应得 0；检查动作校验、原生步数上限、限时执行、不能 reset/越界、封存和双重独立重放。Oracle 只在可信验收环境使用，不能安装到正式 main；limited oracle 也应经过同一受控动作通道并产生完整服务端记录。
4. **模型接入 smoke**：两种模式分别使用 GPT-6 Luna/high/Codex 订阅完成短 smoke，确认实际模型与路由、图像可见、动作可用、提交/封存和 replay 正常。Unlimited smoke 额外验证 privileged 查询、同实例 reset、record/save；limited 验证一次 episode 和 reset 不可达。预期 noop 得 0 可以是通过的接入测试，不要求 smoke 解题成功。
5. **冻结正式配置**：保存验收证据、任务和 runner 指纹、high 配置与真实启动命令。将机制适配到清单中每一个实例，逐项检查 API/目标观测/原生判定兼容性并做适当的 oracle/nop 与 replay 验证，不能由一个实例成功推断所有实例都兼容。
6. **首个正式实例**：每种模式先运行一个稳定实例的正式 trial，该结果计入本轮且不得在全量阶段重复。门槛是模型接通和评分可信，不是要求模型必须解题成功；正常失败或 timeout 不能成为额外重试理由。
7. **全量正式评测**：继续剩余全部实例，两种模式分别记录，每实例每模式一次。单项原生故障继续其他可运行项；全局订阅/基础设施故障先停止新派发并修复，不能消耗整份清单制造同类失败。
8. **独立 verifier 与收集**：每次 agent 结束立即可信封存并独立评分；agent 异常时仍尽量收集已有完整 limited 轨迹。补做 verifier 不等于重启 agent，必须有独立记录且不改原始证据。
9. **审计与交付**：主控和审计 agent 检查计数闭合、视频可用、tokens 来源、失败类别和敏感信息清理，生成下面的全部交付物。全部 MetaWorld+ 可执行项处理完后停止，不运行其他 benchmark，也不自动追加更长时限或第二轮。

基础设施接入修复后的新 smoke 与旧 smoke 分开存档。正式尝试一旦开始，不能通过改名、删目录或修复后重启伪装成“首次”。若正式运行发现影响有效性的实现问题，保留该 trial、说明失效范围；修复后的补充正式实验需要单独方案，不自动重跑。

## 10. 重放与可信评分细节

- 使用 verifier 自有工具、固定初始实例和新进程，agent 停止后才允许进入 verifier 阶段；不信任 agent 写下的分数。
- 保留现有两次独立 replay 和状态 hash 检查；limited 还需将在线可信状态与 replay 对照。调查并覆盖 integration、warmstart、缓存、随机状态及任务历史中影响演化的内容。
- 当前 MetaWorld+ 协议要求精确 hash 一致，不为本轮降低为宽松容差或直接关闭 determinism。若精确复现失败，保存偏差、最早分歧步和环境证据，修复初始化/缓存问题；无法修复则标记无法可靠评分、未评测。需要改变协议时先单列提案，不把放宽后的结果混入本轮。
- 数值 reward 字段遵守 Harbor `reward.json` 契约；文字原因、堆栈和审计信息放在其他 JSON/日志中。
- 审计两次重放都一致但都偏离在线轨迹的情况，避免只比较两个 verifier 进程就声称 limited 在线记录可复现。

## 11. 每个实例必须保存的指标与证据

每个 mode × instance 一行，至少记录：

- benchmark、任务族、environment ID、task ID、instance ID、seed、初始实例 SHA、源/派生任务 digest、git 与源码指纹。
- phase（acceptance/smoke/formal）、唯一 trial ID、attempt index、模型、实际 Codex 模型、high 生效证据、agent 类、Harbor/Codex/镜像版本、认证通道。
- UTC 开始/结束、agent wall time、实际机器人 episode 时长、排队/冷启动/收集/verifier 耗时；计时起点定义。
- reset 次数、控制请求数、有效动作数、失败/非法动作数、物理步数；unlimited 的探索累计与最终提交分别记录，limited reset 必须为 0。
- 提交/可信封存状态、在线成功、两次 replay 成功、deterministic、状态差异、原始 verifier 分数、最终成绩、终止原因及证据路径。
- input/output/cached/reasoning tokens 和 turns（仅当实际返回），注明统计来源。Harbor 缺失时读取 Codex 原生日志，累计 token_count 取可靠最终值，不能把每个累计事件相加重复计费；无法获得写 null。
- 订阅实际增量费用不可得时写 null，并标明 ChatGPT subscription。不要将 API 价目表估计当成账单，也不要把订阅费用写成 0。监控、smoke 和正式用量分开汇总。
- 服务端轨迹、事件、agent 日志、原始 Harbor/native JSON、verifier 日志、回放视频及其 SHA256。分享包过滤所有登录材料和敏感授权信息，不改写内部原始证据。

最终类别区分：成功、模型正常失败、agent timeout、认证/订阅额度/模型调用故障、仿真或基础设施故障、不能可靠评分、未启动/未评测。后四类保留详细子类别，不统称模型失败。所有类别互斥统计，分母与冻结清单相符。

## 12. 报告、离线网页和视频包

生成完整 Markdown 报告、JSON/CSV 结果和本地直接打开的离线网页。网页参考旧 VLABench 汇报的呈现方式，但写入新的 MetaWorld+ 目录；不改旧网页或视频。

- 给出任务族数、实例数、每模式预期 trial 数、成功/模型失败/timeout/各类未评测数量；逐项列出未评测原因和证据。
- 逐任务、逐模式表列出成功数/全部发现实例数、成功率、耗时统计、timeout 数和主要失败原因。另列可评分实例分母上的成功率，明确分母，不悄悄剔除故障。
- 逐实例页面关联完整指标与实际视频，支持任务/模式/状态筛选。展示成功、失败和 timeout，不仅挑成功案例。
- limited 视频对应完整服务端 episode；unlimited 主视频对应最终提交轨迹。额外探索视频单独标注。缺失视频说明原因；没有提交时不能用 oracle 视频代替。
- 视频按真实仿真时间播放，说明控制频率、采样或加速倍率；agent 思考墙钟时间单独显示，不能从视频长度推断任务耗时。
- 同一实例、模型、high、agent 版本、初始状态与预算一致时才能做两种模式的配对比较，并明确差别包含 privileged 观测与 reset 权限，不能将差值全部归因于单一因素。不同旧 agent/effort/认证配置的成绩只作分组历史参考。
- 分析应由轨迹、事件及 verifier 证据支持，区分视觉定位、控制、规划、物理步数耗尽、60 分钟 timeout、订阅/基础设施问题；未知原因如实标记，不编造模型内部推理。
- 网页使用相对路径、本地 CSS/JS/视频，不依赖 CDN、联网或必须通过 HTTP fetch 的数据加载；验证 `file://` 打开、链接、视频编码及播放。生成可下载离线压缩包、文件清单和 SHA256。
- 提供所有实际可执行的复现命令：prepare、acceptance、smoke、单实例、全量两种模式、report、打包，以及带真实远程路径和占位主机/用户名的 scp 下载命令。命令不得包含凭据。
- 最后给出结果目录、Markdown、网页和离线包位置。不要把后台进程仍在运行说成评测完成；若有外部阻塞，给出已完成范围、保留的待运行清单及安全续跑方式。

请现在从只读审计和全量清单开始，随后按顺序自主完成已授权工作；仅在确有外部登录、权限或协议冲突阻塞时请求用户处理。不要运行其他 benchmark。
