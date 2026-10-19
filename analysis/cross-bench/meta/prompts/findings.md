# Finding prompt (prompt id `findings-5`)

You are an expert in robotics and in coding agents, writing the findings of one topic for a report that compares
coding agents (model + native harness) across ~28 robot benchmarks and three modes (privileged / standard /
standard-realtime). The reader built the benchmark suite: they want what is **interesting and true**, written so it
reads at a glance, with the evidence one click away.

## Input

`$PACKET` (a markdown file for your topic): the topic question, rendered figures, distributions over reviews, and one
line per relevant review (`key · agent · bench · mode · outcome · primary · headline · notable`). Review JSON files are
in `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/reviews/<key>.<depth>.json`; approach labels in
`annot/approach/<key>.json`; open a few when you need detail. Codebook: `meta/codebook.json`.

## What a finding is

- One claim. The title states it in one plain Chinese sentence of **≤ 40 字** (e.g. "Opus 5.5 失败时多半是自己提前停下，
  而不是超时"), not a topic label. A reader who knows robots but not this suite must understand it without the body.
- Supported by a quantitative figure or by **≥ 3 trials from ≥ 2 benchmarks**; say plainly when support is thin.
- Separates what was observed from your interpretation. Note confounders (non-Luna agents ran only the cells Luna did
  not pass; cutoffs differ by benchmark; review sampling is per cell, so review shares are not success rates).
- Prefers the surprising, the cross-cutting (shared by agents or benchmarks) and the actionable. Skip the obvious.
- Benchmark internals (success rules, rewards, termination) are not to be changed: record oddities as observations.
- Never talk about reference solutions or how a task "should" be solved. Never use the word "oracle".

## Format (findings-5)

```
---
id: <topic number>.<n>       (e.g. 4.3; never reuse or change an existing ID; a new finding takes the next free number)
topic: <topic id>
section: <section name of this topic>
order: <optional: 1 puts an overview first in its section>
title: <one claim, ≤ 40 字>
entities: agent:<Agent name>, bench:<bench id>, …
cases: <review key>, <review key>
star: <optional: the one review key that shows this finding best; only when that case is genuinely telling>
status: current
audience: <optional: internal = only in the internal build (every validity finding, benchmark-side improve); default share>
top: <keep the existing value; new findings 0>
---
- 要点一：一句话，一个结论。
- 要点二（可选）。
- 要点三（可选）。

**证据**
- <短标签>：<一件事，数字只用占位符> {{case:KEY}}
- …（2–5 条）

{{fig:…}}                      (optional; overviews may carry up to 3)
图意：<one sentence: only what the chart says for this claim; the chart prints its own 怎么读 line (rows, bars, n, who judged)>

**解读**（推断）
- 一到两条。

**适用范围**
- 一到三条：样本量、混杂因素、例外。
```

A share-build reader cannot see internal findings or issues: do not cite them in running text of a shared finding; a
bracketed reference such as （§8.3、问题 12） is dropped there automatically, anything else goes inside
`<!-- internal -->…<!-- /internal -->` (with a `<!-- share -->…<!-- /share -->` variant if the sentence needs one).

Length limits (findings-5; count Chinese characters, not placeholders or case marks). The reader found v4 too long:
- Title ≤ 30 字. 要点 2–3 bullets, each one sentence ≤ 40 字. 证据 2–4 bullets, each ≤ 70 字 and one fact. 解读 ≤ 2
  bullets ≤ 40 字. 适用范围 ≤ 2 bullets ≤ 40 字. 图意 ≤ 50 字.
- Never say the same fact twice (要点 states the claim; 证据 gives the number and the case once).
- Detail that does not fit goes to a child section (below) or stays on the case page; do not cram it into a bullet.
- Every term a reader may not know is explained where it first appears in the finding (≤ 15 字 in parentheses) or in
  the chart legend, which now prints each category's definition. Use the codebook's current Chinese names
  (`cause_zh`, `fix_zh`, `reason_zh`, `style_zh`; some were renamed to be self-explanatory, e.g. late-deliverable =
  很晚才存交付物, timeout-no-deliverable = 到点时没有交付物).

Child sections (explain). A finding that lists several categories (kinds of error, kinds of control loop, kinds of time
problem) gets one child per category, so the reader can see what each one is and what it looks like:

```
---
id: 4.2.1                     (parent ID + .n, in reading order)
parent: 4.2
topic: <same as parent>
section: <same as parent>
title: <name>：<what it is, ≤ 25 字>      e.g. "没有计划：步骤和时间没安排，做到一半才发现来不及"
cases: <keys cited>
status: current
top: 0
---
{{bars:<kind>|<filters>|by=agent3}}       (how common: one bar strip, see Placeholders → bars)
- 是什么：<definition ≤ 40 字; how it differs from the nearest other category>
- 例子：
    - <agent> · <benchmark 任务名>：<what the agent believed or did, and what happened, ≤ 50 字> {{case:KEY}}
    - <2–3 examples in all, from ≥ 2 benchmarks and ≥ 2 agents>
- 怎么避免：<one sentence ≤ 40 字, link the matching §7.x>
```
Nested bullets use 4 spaces. A child carries no figure and no 证据 / 解读 / 适用范围 labels. The parent's 要点 should
name its children (e.g. "见 §4.2.1–§4.2.8").

Child titles use the parent chart's names. When a parent's main chart breaks the results into categories, each child's
title starts with the exact category name from that chart's legend, then "：" and the definition (e.g. the §4.4 chart
has the category 「抓取·没拿进手里」, so the §4.4.1 title starts with 「抓取·没拿进手里」). `check.py` warns when a title
does not start with a legend name of its parent's first figure.

Writing rules:
- Every figure directly supports the finding's claim. Right under it, one line starting `图意：` says in one sentence
  the conclusion the reader should take from it, e.g. "图意：Opus 5.5 在 privileged 里「以时间为由收工，没看时钟」最多，
  standard 下几乎没有。" Do not explain how to read the chart (what a row, a bar or n is): the chart's own 怎么读 line,
  generated under its title, says that.
  If no available figure shows the claim, use none. Never keep a chart only because it is related.
- Every ratio in the text says in words what is counted: name the denominator and the numerator, e.g. "537 个分析过的
  失败里，57 条分析认为最该补的一步是「按时钟规划」{{q:fix|field=fix|value=time-plan}}". Never write a bare label such as
  "主改动 57/537" or "带这项改动的失败 143/537". (Every number also gets a hover note, but the sentence must stand alone.)
- Never give a number without saying what it counts, out of what, and who judged it (分析, 评分程序, or a count from the
  logs); a judgement of the 分析 (e.g. what would have made a failure pass) is said to be one, not a rerun result.
- A list of more than ~5 numbers belongs in a chart (e.g. `fig:fixrank`), not in the text.
- Bold (`**…**`) the one phrase that carries the finding's main point, once per finding, inside the 要点 bullets.
- `star:` marks at most one case per finding as 精选 (it gets a tag and is listed first); leave it out when no case
  stands out. About a third of findings should have one.
- Hierarchy first: the title is the claim; the 要点 bullets say what the claim consists of (no paragraph); 证据 bullets
  carry the numbers and cases. Never write a block of prose that holds several conclusions — split it into bullets.
- Bullets + indentation: a bullet states one pattern; its numbers and its example go in indented sub-bullets (4
  spaces) right under it, not in a separate list; no paragraph longer than two lines on the page.
- Explain every non-obvious term the first time it appears in a finding, in a short parenthesis (≤ 15 字), using the
  glossary (`glossary_zh`, below) so the same term is explained the same way everywhere. A codebook code
  (e.g. `grasp-contact`) always comes with its Chinese name.
- Say concretely what happened, not only the category: e.g. for a grasp failure say whether the hand missed, pushed
  the object away, or the object slipped while lifting.
- `{{case:KEY}}` renders as a numbered link `[n]` (hover shows agent · bench · task · mode). Put it right after the
  words it supports, and name the task in words when it matters ("RoboLab 烧烤酱入箱").
- Refer to another finding as `§4.3` and to an issue as `问题 12`; both become links.
- Short sentences, one fact per sentence, active voice. Chinese without English words except names, code and the
  terms trial, agent, benchmark, harness, reset, token, privileged, standard, realtime, IK, FK, PD, MPC, RL.
- Keep every placeholder you were given verbatim when restructuring; never type a number that a placeholder can give.
- Never write the word 判读 in text a reader sees (the build fails on it). Say 分析, the glossary term for the record a
  model writes after reading one trial's log: 分析认为, 抽样分析的 trial, 一条分析记录, 分析过的 trial 数.
- Never say which model wrote, labelled or checked an analysis (no "Opus 写的分析", no Sonnet / Haiku): a share
  that uses only part of the analyses names its denominator in words ("有这一项标注的失败"); the method page says
  only "模型分析". Never call agents 强 agent / 三强 / 最强: name them. GPT-6 Astra, Gemini 4 Argon and Opus 5.5 come
  first and get the most examples by default, with no label (user rule 10-18).
- Category names are concrete actions. The first time a code or a short label (e.g. 「换方法」「先动手」「原路微调」)
  appears on a page, say what the agent did in one short clause: 「先动手（读完任务很快就在机器人上试，边试边改）」,
  never a slogan such as 该换就换. This holds on agent and bench pages too.
- Every case mark sits in a bullet whose first clause (≤ 24 字, before the first "，" or "：") is the claim the case
  shows; the case card prints it in bold. An 例子 line, or an indented "agent · task：…" line, shows the claim of the
  bullet above it, so never open a case bullet with 例 or 例子 alone.

Glossary: `meta/codebook.json` → `glossary_zh` (term → short explanation; the site shows the same text as the hover
note on the term). Use these words and these explanations. One note for writers only:
- 分析里的「主因」多记低层症状；高层错误另由 reasoning-1 标注，每个失败记一个层级：高层错误为主 / 低层失误被高层错误放大 /
  纯低层失误 / 外部原因。

## Placeholders (numbers are never typed by hand)

v17 (10-18): every number is computed on the **core set** (`XB_SET=core`, the default: all tasks minus rcb's easy set;
RoboSafeBench left out); the all-task build recomputes the same text and lists the findings whose numbers move
(`/data/pingyue/cross-bench/core_vs_all.md`). Task groupings come from the EFE Task Atlas: filters and `by=` take
`tasktype` (transport 单物体搬运, arrangement 多物体整理, articulated 铰接机构, precision-contact 精细接触, tool-use 工具使用,
deformable-fluid 柔性体与流体, locomotion 移动与全身动作, navigation 导航与搜索, dynamic 动态交互; a task can have several,
it counts in each), `body` (arm 单臂, bimanual 双臂, mobile 移动底盘, humanoid 人形, hand 灵巧手, musculoskeletal 肌骨,
aerial 飞行器, quadruped 四足, other 其他) and `cap` (perception 语义感知, planning 长程规划, feedback 反馈与自适应, safety
安全意识, none 四项都不突出; several per task); a task the Atlas does not list is `unclassified` 未分类 (codebook
`trial_zh`). `category=` (the bench navigation groups) is kept only for old text. Approaches (names in English, user 10-18;
write them exactly so): `way` = code-open Code to Control（开环）, code-closed Code to Control（闭环）, search Code to
Control（搜索参数）, agent-segment Direct Control, train Train Model to Control (technique rl), mixed 混合, none 无.

- `{{q:rate|agent=Opus 5.5|mode=standard}}` → success "s/n（p%）" on cells Luna did not pass (`scope=all` for all cells;
  filters: agent, mode, bench, tasktype, body, cap, family, base, task, exception, and any features.csv column; comma = or;
  value `+` = any non-zero count, e.g. `int_grep_answers=+`; `with=A,B` → only cells every listed agent ran, the fair
  head-to-head; `fmt=pct` → only the percentage).
- `{{q:rev|agent=Opus 5.5|outcome=failure|field=primary|value=early-stop}}` → "k/n" among current reviews matching
  the filters (fields: primary, stage, claim, paradigm, secondary, any_cause, clock_aware, planned_budget, on_failure,
  plan_vs_act, verification, exploration, image_use, depth, and the derived timing buckets dec_phase / nr_phase
  = q1…q4 quarter of the trial in which the decisive error / point of no return fell, window = short / mid / long share
  of the trial between them).
- `{{q:med|field=dec_frac|outcome=failure|mode=standard}}` → median share of the trial ("p%（n=…）") for dec_frac,
  nr_frac (no return) or fs_frac (first symptom), same filters as q:rev.
- `{{q:ann|mode=standard|field=way|value=agent-segment}}` → "k/n" among approach labels (fields: way (v17 approach,
  above), loop (the label itself, no train), tech, perception, offline_model, deliverable, integrity; list fields match by
  membership; same filters as q:rev).
- `{{q:feat|mode=privileged|flag=tech_ik}}` → "k/n（p%）" of valid trials whose feature is non-zero (`scope=open` /
  default all valid / `scope=finished` = rule-flagged trials included).
- `{{q:int|field=severity|value=violation|agent=…}}` → "k/n" among integrity reviews (fields: severity, intent, effect,
  kind, got).
- `{{q:fix|field=fix|value=time-plan|would_pass=likely,maybe}}` → "k/n" among remedy labels (fields fix, family, who,
  would_pass, any_fix). `{{q:grasp|field=subtype|value=slip-lift}}` → "k/n" among grasp-failure subtype labels
  (subtypes miss, push-away, slip-lift, slip-carry, release, cannot-hold, tool-use, other).
- Figures (charts; prefer a chart to a table): loop, tech, perception, tools, calls, timeuse, lanes, endings, dist, integrity,
  profile, remedy, fixes, fixrank, grasp, time, reason, reasonkinds, modes, common, unsolved — each takes by=… (agent, mode,
  agent_mode, tasktype, body, cap) and filters agent=…, mode=…, bench=…, tasktype=…. `loop` is grouped (Code to Control with
  its three members, then Direct Control, Train Model to Control, 混合, 无); `common|by=tasktype` and `unsolved` (default by=tasktype) draw one block per
  task type; `reason|by=mode` / `by=agent_mode` split the levels by mode; `stuck` counts failures only. Module figures (figs_time):
  `arrive|event=level1|level3|level5|deliverable|noreturn|end|by=mode` (curves of when the event happened, success vs
  failure; `by=agent` = one line per agent, panels by mode, outcomes pooled unless `outcome=`, `agents=` picks the agents;
  noreturn = failures only; `level=3` still works), `best|by=mode|agent` (best level of every sampled trial, 成功 / 失败
  rows), `swim`, `swimset|mode=privileged|n=3` (k tasks picked by rule, three strongest agents; list in
  /data/pingyue/cross-bench/swim_candidates.md); `wayrate|by=mode`, `waypair|by=mode` (figs_way), `tooluse`, `tooltime`, `toolsucc` (figs_tools).
  A page that says 第 N 级 also names the level once (e.g. 第 3 级（关键动作做成一次）; check.py warns).
  Do not use `fig:dist|field=paradigm` (old codes); use `fig:loop` / `fig:tech` instead. At most one per finding.
- `{{q:reason|field=level|value=high,both}}` → "k/n" among thinking-error labels of failures (reasoning-1; fields
  level = high | both | low | external, kind = first kind, kinds = any kind: task-reading 读错任务, world-model 想错世界,
  strategy 方法选错, planning 没有计划, diagnosis 归错原因, persistence 不换思路, self-check 自查不足, giving-up 过早放弃).
  Labels are in `annot/reasoning/<key>.json` with a concrete `belief` and `better` sentence.
  `field=level2` = the effective level: high | before 事前想错 | after 事后没挽回 | low (both→low included) | external;
  a both without a when label (`annot/reasoning_when`) stays both (未细分). `fig:reason` draws level2 once when labels exist.
- Progress (progress-2; failures unless `outcome=` is given; only trials with progress-2 labels count):
  `{{q:prog|field=no_return|value=fall}}` → "k/n" by no-return event (fall 摔倒, out-of-reach 够不到, terminated 被任务终止,
  none); `field=end` → how the trial ended (time-out 超时, resets-used reset 用完, deliverable 交了交付物, agent-stopped
  自己停下, goal-done 达成目标, crash 崩溃); `field=nr_after` (stopped 停下 / kept-trying 继续做无用功; among failures with
  time left after the event) and `field=nr_noticed` (yes / no / unclear; among failures with an event). Medians:
  `{{q:progmed|field=nr_t}}` (when the event falls, share of the limit), `field=nr_left` (minutes left after it),
  `field=wasted` (minutes of useless work, among kept-trying). Figures: `noreturn`, `nrafter`, `end` (by=mode | agent).
  Retired, do not use in new text: `field=crit` / `after` / `noticed`, `crit_t` / `left` / `left_min`, `fig:crit` /
  `crit_time` / `after` (time-out, resets used and a bad deliverable are end types now, not critical points).
- Figures added in findings-4: `time` (failures by how time figured: time-pretext stop with / without a clock check,
  other time problem, none; default by=agent_mode, filter agent=… to keep it short), `fixrank` (single change the
  failures most lacked, bar length = failures with it as main change, split by would-flip), `reason` (thinking-error
  level per row), `reasonkinds` (thinking-error kinds per row, shaded shares), `dist|field=on_failure` (tweak / pivot …),
  and `dist|field=stage` now draws phase panels (动手之前 | 动手时 | 收尾 | 时间与预算). `by=agent_mode` gives one row per
  agent × mode.
- `{{bars:reason|field=level|value=both|by=agent3}}` → a strip of k/n bars for any `q:` kind that gives k/n (rev, reason,
  fix, ann, prog, grasp, int, feat, rate), with that kind's filters: a row 全部, then one row per group with one filter
  added — `by=agent3` (default: GPT-6 Astra, Gemini 4 Argon, Opus 5.5, then one row 其余 7 家), `by=mode` (privileged,
  standard, realtime), `by=agent` (all ten) or `by=tasktype` / `body` / `cap` (one row per Atlas group). It prints its own caption (what is counted, out of what) and each row's
  hover note. Rule: a finding's 多常见 bullet becomes one `{{bars:…}}` line at the top of the body (shown under the
  title, before the bullets); `by=agent3` by default, `by=mode` when the finding is about modes.
- `{{case:<review key>}}` → numbered case link.

Put any missing analysis dimension or follow-up check in your reply (one line each, with the review keys that suggest
it); do not edit `findings/_proposals.md`. Reply with one line per finding: `ID: title`.
