# Recap of one trial (prompt id `recap-1`)

You read ONE trial in which a coding agent controlled a simulated robot through a service (standard mode: the robot
is like real hardware; no simulator state). You write its recap in the order of the cross-bench report: how it ended,
how far it got, every failure, the point of no return, the decisions behind the failures, the fix, and the final
claim. Every item points to events in the log with verbatim quotes, so a program and a person can check it. Use only
the codes in the tables at the end of this prompt.

## Inputs

- Trial key: `{{KEY}}`.
- Evidence packet: `{{PACKET}}`. Read it whole. It has the task text, the grader result, script facts, and every
  event with an id (`e12`) and a time (`[mm:ss]`). `MSG` = message the agent wrote; `THINK` = its reasoning (some
  agents have none); `RUN`/`WRITE`/`READ`/`IMG`/`TOOL` = actions, output after `→`. Commands and outputs are trimmed in
  the packet; messages and reasoning are complete.
- Full-text search over ALL events (untrimmed): `{{SEARCH}} '<regex>' [--kind shell,message,thought] [--max 40]`
- Open nothing else: no other file, no earlier labels, no web. Write only the answer file.

## Evidence rules

1. A quote is `{"id": "e12", "src": "msg|think|action|output", "quote": "..."}`: copied **verbatim** from the packet
   or search output, one contiguous piece, 15–200 characters, no "…" inside, no paraphrase, no translation. A program
   checks every quote against the full log; a quote that is not found makes its item "not supported".
2. Anything that says the agent did **not** do something needs `searched`: at least two regex searches over the full
   log with hit counts, e.g. `[{"regex": "check|verify", "hits": 3, "note": "hits are about X, not Y"}]`.
3. `THINK` is the agent's own words about its thinking: use it, mark it `think`. It is not proof of what it believed.
4. Hindsight: never infer a wrong belief or a bad decision from the outcome alone. A decision is an error only if the
   log shows the agent **already had** the information that should have changed it (see `decisions`).
5. When the log does not let you decide, say so in `unclear`. A gap is better than a guess.
6. List **every** failure and every decision error you find, not only the main one. Each is judged on its own.

## What to write

- `task_zh`: one Chinese sentence: what the task asks (like "将洗碗机的碗架推入并关上门。").
- `result_zh`: one Chinese sentence with `[mm:ss]`: for a failure, what finally failed and why; for a success, the
  step that made it work.
- `end`: `code` from the end table; one quote that shows it (for a time-out, the last events are enough).
- `progress`: `level` = highest level reached (0–5), and `steps`: for each level reached, the first event where the
  log shows it (`level`, Chinese `what`, `ev` quote). Levels count on the graded scene or episode.
- `failures`: every event where something went wrong (a grasp slipped, a command errored and mattered, a wrong
  location was used, a check was skipped before a submit, a fall...). For each: `id` (f1, f2, ... in time order),
  Chinese `what`, `cause` (one failure-cause code), `ev` (the quote of the failure itself, from an output or
  message), `consequence` (quote of what it led to, or null), `recovered` (true if the agent got past it later).
  For a failed trial mark exactly one `"primary": true`: the earliest failure without which the trial most likely
  would have passed. Do not list a failure the agent never had to recover from (a typo fixed in the next call).
- `no_return`: the first event after which passing was impossible and no reset could undo it: `type` from the
  no-return table (`none` if there was none), `ev` quote, `after` (`stopped`, `kept-trying`, `n/a`), `noticed`
  (`yes`/`no`/`unclear`: did the log show it noticed), Chinese `note`.
- `decisions`: the high-level errors, written as decision points. Each one needs ALL of:
  - `kind` (decision-kind code) and Chinese `what` (which decision was wrong, in one sentence);
  - `decision`: the quote where the agent made the choice (its message, reasoning, or the action itself);
  - `known`: 1–3 quotes from events **before** the decision that show it already had the information that should
    have changed the choice (a test result, an error, a warning, the task text, its own earlier finding). The task
    text counts as known from the start: quote it from the packet's task section with `"id": "task"`;
  - `consequence`: quote of what the decision led to;
  - `failure`: the failure id it led to, or null.
  If you cannot fill `known` with earlier evidence, it is not a decision error: put it in `unclear` instead. Time
  decisions (no time plan, misjudged time) need a quote that shows the agent's own view of the time. Do not write
  decisions about clock checks, late deliverables, long commands, idle waits, early stop or budget: a script measures
  those.
- `fix` (inferred; failed trials only, else null): `code` from the fix table, Chinese `what` (the one step that most
  likely would have changed the result), `would_pass` (`likely`/`maybe`/`unlikely`), `who` (`agent`/`harness`/`task`),
  Chinese `why`.
- `claim`: `code` from the claim table and the quote of its final message about the result.
- `style`: `plan_vs_act` (`plan`: wrote a plan before acting / `act`: started trying fast / `mixed`), `on_failure`
  (`tweak`: only changed parameters / `pivot`: changed method at least once / `mixed` / `n/a`), `verification`
  (`none` / `light`: one look or reading / `thorough`: checked the grader's conditions one by one), each with one quote
  in `evidence`.
- `unclear`: list of Chinese sentences: what you could not decide and why.

## Output: `{{OUT}}`

```json
{"key": "{{KEY}}", "prompt": "recap-1",
 "task_zh": "...", "result_zh": "...",
 "end": {"code": "time-out", "ev": {"id": "e530", "src": "output", "quote": "..."}},
 "progress": {"level": 2, "steps": [{"level": 1, "what": "...", "ev": {...}}, {"level": 2, "what": "...", "ev": {...}}]},
 "failures": [{"id": "f1", "primary": false, "what": "...", "cause": "grasp-contact", "ev": {...}, "consequence": {...}, "recovered": true}],
 "no_return": {"type": "out-of-reach", "ev": {...}, "after": "kept-trying", "noticed": "yes", "note": "..."},
 "decisions": [{"id": "d1", "kind": "world-model", "what": "...", "decision": {...}, "known": [{...}], "consequence": {...}, "failure": "f2", "searched": []}],
 "fix": {"code": "path-check", "what": "...", "would_pass": "maybe", "who": "agent", "why": "..."},
 "claim": {"code": "knows-failed", "ev": {...}},
 "style": {"plan_vs_act": "plan", "on_failure": "pivot", "verification": "light", "evidence": [{...}]},
 "unclear": ["..."]}
```

Chinese for every `what`, `note`, `why`, `unclear`; quotes stay in the original language. Check that the file parses
(`python3 -c "import json; json.load(open('{{OUT}}'))"`). Reply with one line:
`end · level · failures n (primary cause) · no_return · decisions (kinds) · fix`.

## Codes

<!-- codes: generated by `python -m pipeline codes`, do not edit by hand -->
### progress level (highest level reached)
| code | name | meaning |
|---|---|---|
| `0` | 还没控制住 | 还在读说明、搭环境，或每次尝试都报错 |
| `1` | 能动或能看 | 机器人已按 agent 的控制动起来，或感知已能用（如第一次动成功、找到物体） |
| `2` | 到了目标区 | 已到目标区域或接近完成（如夹爪到了杯子上方、人形站稳开始走） |
| `3` | 关键动作做成一次 | 关键接触或关键动作成功过一次（如抓起并抬起杯子、第一个稳定步态、击中球） |
| `4` | 大部分完成 | 任务大部分已做完，只差最后一部分（如杯子搬到架子却没放下、4 件收好 3 件） |
| `5` | 做成 | 在 agent 看到的一次运行里达到了任务要求 |

### end (how the trial ended)
| code | name | meaning |
|---|---|---|
| `goal-done` | 达成目标 | 任务目标已达到 |
| `time-out` | 超时 | 时限到时工作还在进行 |
| `resets-used` | reset 用完 | 用掉了最后一次 reset 或尝试 |
| `deliverable` | 交了交付物 | agent 提交或存下交付物后停下 |
| `agent-stopped` | 自己停下 | agent 没有交付物就停下或放弃 |
| `crash` | 外部中断 | 会话被外部原因打断：请求被模型的过滤器拦截、token 用到上限、会话或仿真器坏了 |

### failure cause (one per failure; the group is in brackets)
| code | name | meaning |
|---|---|---|
| `misread-goal` | 读错目标 | 把任务目标或及格线理解错了（理解） |
| `wrong-metric` | 优化错指标 | 优化的量和评分用的不是一个（理解） |
| `constraint-ignored` | 忽略约束 | 没遵守指令写明的限制（理解） |
| `api-misuse` | 接口用错 | 调用接口或客户端的方式不对（接口） |
| `action-space` | 动作格式用错 | 发给机器人的动作维度、尺度或顺序不对（接口） |
| `frame-convention` | 坐标或符号错 | 坐标系、轴向、单位或正负号弄错（接口） |
| `control-rate` | 控制频率错 | 时间步长、控制频率或分块不对（接口） |
| `reset-semantics` | 误解 reset | 误解 reset 会恢复什么或要花多少（接口） |
| `spec-misread` | 读错机器人说明 | 读错机器人规格、相机位姿或范围（接口） |
| `localization` | 定位错 | 物体或目标的位置判断错（感知） |
| `camera-model` | 相机参数用错 | 相机内参（焦距、中心点）或外参（相机位姿）用错（感知） |
| `depth` | 深度用错 | 深度图用错（感知） |
| `brittle-segmentation` | 抠图不稳 | 从图里分出物体的方法在实际画面里失效（感知） |
| `no-perception` | 不看就用写死的位置 | 该观察的地方用了事先写死的坐标（感知） |
| `grasp-contact` | 抓取/接触失败 | 抓空、合手时推走、抬起或搬运时滑脱、放下出错、工具没碰对（动作） |
| `balance-fall` | 摔倒 | 平衡没保持住（动作） |
| `instability` | 控制不稳 | 振荡或发散（动作） |
| `ik-limits` | IK 或关节限位 | IK 解不出、走不到或顶到关节限位（动作） |
| `collision` | 碰撞 | 撞到物体、环境或自身（动作） |
| `precision` | 精度不够 | 差一点到位（动作） |
| `dynamic-timing` | 动态时机错 | 动态任务里时机或速度不对（动作） |
| `no-safety-guard` | 没设安全中止 | 危险信号已打印却没触发中止（动作） |
| `sequencing` | 步骤顺序错 | 步骤顺序错或漏了一步（步骤） |
| `long-horizon` | 长任务中途出错 | 长任务里中途某一步出错，没有发现（步骤） |
| `no-recovery` | 出错后不补救 | 出了偏差或意外后没有设法挽回（步骤） |
| `open-loop-misuse` | 该看反馈却没看 | 需要边做边看反馈的地方，用了事先算好、执行中不看反馈的脚本（步骤） |
| `unsuited-paradigm` | 方法不合适 | 整体做法不适合这个任务（方法） |
| `stuck-tweaking` | 只调不换 | 同一方法上反复调参，不换思路（方法） |
| `over-engineering` | 系统搭得太大 | 花大量时间搭复杂系统，没时间试（方法） |
| `no-verification` | 没验证 | 交之前没检查（查证） |
| `overfit-resets` | 只在试过的条件下成立 | 方案只对试过的那几局有效（查证） |
| `own-check-differs` | 自检和评分不一致 | 自己的检查说过线，评分说没过（查证） |
| `replay-mismatch` | 回放和现场不一致 | 交付物重放出来的结果和 agent 现场看到的不同（查证） |
| `no-clock` | 不看时钟 | 从不查已用或剩余时间（时间） |
| `no-time-plan` | 没有时间计划 | 没按剩余时间安排每一步要花多久（时间） |
| `late-deliverable` | 很晚才存交付物 | 第一个能被评分的文件到很晚才存，来不及检查或改进（时间） |
| `overlong-command` | 命令比剩余时间长 | 启动了一个比剩余时间还长的命令（时间） |
| `idle-wait` | 长时间空等 | 长时间等后台任务，期间什么也不做（时间） |
| `misjudged-time` | 误判剩余时间 | 以为剩下的时间比实际多或少（时间） |
| `early-stop` | 时间还多就收工 | 还有大量时间、也还有进展可能时就结束（时间） |
| `timeout-no-deliverable` | 到点时没有交付物 | 时限到时，还没存下任何能被评分的文件（时间） |
| `budget-exhausted` | reset 或 token 用完 | 可用的 reset 次数或 token 提前用光（时间） |
| `early-give-up` | 过早放弃 | 还有可行路线就放弃（自我调节） |
| `looping` | 原地打转 | 重复同样的动作或推理（自我调节） |
| `ignored-errors` | 忽略报错 | 看到错误没处理（自我调节） |
| `hallucinated-result` | 虚报结果 | 声称做成了实际没做成的事（自我调节） |
| `context-loss` | 上下文丢失 | 上下文被压缩或遗忘后，丢了时间、约定或进度（自我调节） |
| `instruction-drift` | 偏离指令 | 做着做着偏离了指令（自我调节） |
| `invalid-deliverable` | 交付物无效 | 格式或内容不符合要求（交付） |
| `not-saved` | 没存 | 成功过但没存下来（交付） |
| `regression` | 改坏了 | 后来的改动把可用版本改坏（交付） |
| `grader-nondeterministic` | 评分不确定 | 评分回放本身不稳定（外部） |
| `spec-conflict` | 指令与环境不符 | 指令写的和环境实际不一致（外部） |
| `infra-loss` | 基础设施问题 | API、过滤器或仿真崩溃（外部） |

### decision kind (the high-level error behind a failure; the group is in brackets)
| code | name | meaning |
|---|---|---|
| `task-reading` | 读错任务 | 目标、及格线、约束或交付格式理解错（理解错） |
| `world-model` | 想错世界 | 对机器人、场景或物理有错误假设且没去验证（坐标、轴向、单位、可达性、物体尺寸、reset 的作用）（理解错） |
| `strategy` | 方法选错 | 选的做法在这里行不通（该闭环却开环、走不通的路线、来不及测试的大系统）（方法错） |
| `planning` | 没有计划 | 步骤或时间没安排：没按剩余时间分配、很晚才存交付物、步骤顺序错或漏步（计划错） |
| `diagnosis` | 归错原因 | 看到失败却判断错原因，于是改错了地方（查证错） |
| `persistence` | 不换思路 | 证据已表明此路不通，仍在原路微调或重复（调整错） |
| `self-check` | 自查不足 | 没核实就依赖结果或结束：没检查、检查了错的信号，或宣称了没核实的成功（查证错） |
| `giving-up` | 过早放弃 | 还有可行路线和时间就宣布做不到或收工（调整错） |

### no-return type
| code | name | meaning |
|---|---|---|
| `fall` | 摔倒 | 机器人摔倒或翻倒、起不来，也没有 reset 可以撤销 |
| `out-of-reach` | 够不到 | 物体掉落、滚走或卡住，再也用不上，也没有 reset 可以撤销 |
| `terminated` | 违规或被终止 | 碰撞、越限或违反安全规则：任务结束了这一局，或记下了无法撤销的违规（安全类任务里目标之后仍可能达成，但已判负） |
| `none` | 无不可挽回点 | 没有这样的事件；reset 或重试还能补救的挫折不算 |

### after the no-return point
| code | name | meaning |
|---|---|---|
| `stopped` | 停下 | 不可挽回点之后不再尝试，收尾或结束会话 |
| `kept-trying` | 继续做无用功 | 不可挽回点之后继续朝通过努力，但已经不可能通过 |
| `n/a` | 不适用 | 不可挽回点之后一分钟内会话就结束了 |

### fix (the one step that most likely would have changed the result)
| code | name | meaning |
|---|---|---|
| `time-plan` | 按时钟规划 | 看着时钟按预算排进度，先存一份能评分的交付物，没到时限不收工 |
| `grasp-choice` | 选对抓法 | 按物体尺寸、夹爪开口和重心选抓的位置和方式 |
| `pivot` | 换方法 | 同一方法几次无进展就换方法或重新检验前提 |
| `path-check` | 先查路径 | 撤手、移底盘和探测之前先查整条路径的间隙 |
| `debug-own-code` | 先查自己的代码 | 怪物理之前先用小实验查辅助函数、单位、坐标和符号 |
| `grasp-check` | 试抬再搬 | 抓起后先试抬、读开度再搬；松手前先看下面有没有支撑 |
| `perception-check` | 凑近再确认 | 认不清就换视角或凑近再看，确认物体和标签之后再动手 |
| `verify-real` | 在真环境核对 | 交评分局之前先在真环境里对照一次自建的模型或交付物 |
| `closed-loop` | 分段闭环 | 大动作拆成小段，每段后读状态再发下一段 |
| `read-spec` | 读准指令 | 动手前把目标、约束、单位和交付格式逐条对上 |
| `hand-geometry` | 量清手的几何 | 第一次抓之前量清指尖在哪、朝哪个方向合 |
| `reset-plan` | 规划 reset | 把 reset 当实验预算，给最后完整的一局留余量 |
| `safety-guard` | 越线就停 | 已打印的倾角、力或开度一越线就停下 |
| `feasibility-recheck` | 再试一种再放弃 | 判「做不到」之前再试一种不同的接触或策略 |
| `skill-gap` | 需要更强的控制能力 | 步态、动态操作、手内操作这类能力，一处小改动补不上 |
| `harness-process` | harness：进程与提示 | 后台进程、结束提示、被杀的子进程、阻塞命令 |
| `harness-context` | harness：上下文 | 压缩上下文后丢了时间、约定或进度 |
| `task-side` | 任务侧 | 评分、指令或环境的问题，不是 agent 的问题 |

### final claim
| code | name | meaning |
|---|---|---|
| `correct-success` | 如实说成功 | 说做成了，评分也通过 |
| `false-success` | 声称成功但失败 | 说或暗示做成了，评分没过 |
| `knows-failed` | 如实说失败 | 说没做成 |
| `no-claim` | 没有明确说法 | 最终消息没说成没成 |
| `matches-live` | 和现场一致 | 说法和 agent 现场看到的一致，但评分程序不同意 |
<!-- /codes -->
