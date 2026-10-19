# Entity notes prompt (prompt id `notes-4`; bench and agent notes)

Each benchmark page and each agent page opens with a short structured note. It is the reader's first view of that
entity: the few things worth knowing, each one click from its evidence. Write Chinese, plain words, findings-5 writing
rules (`meta/prompts/findings.md`), no heading.

## Inputs

- `/data/pingyue/cross-bench/packets/entities.md` (per bench / per agent: results, top causes, review headlines) and
  `/data/pingyue/cross-bench/packets/overview.md` (per-agent method, tool and time numbers).
- Finding titles: `grep -m1 '^title:' findings/[0-9]*.md`; issues: `findings/_issues.json` (问题 N = id IN).
- Reviews `reviews/<key>.<depth>.json` and approach labels `annot/approach/<key>.json` when you need detail.

## Shape (notes-4: bullets + indentation, both kinds)

- A **pattern bullet** states one pattern (≤ 40 字, conclusion first, § link at its end).
- Under it, indented 4 spaces (the page's markdown needs 4), at most two **sub-bullets**:
  - a numbers sub-bullet that first names what it counts, then the values: `分析过的 privileged 失败里…的：Astra k/n，Luna k/n`;
  - one example sub-bullet `例：<task named> <what the agent believed or did> → <what happened> {{case:KEY}}` (≤ 50 字).
- Every pattern bullet that a trial can show carries its example right there; no separate list of examples.
- No line longer than two lines on the page (≈ 80 字); no prose paragraph; one case mark per example sub-bullet.

Bench note `notes/bench/<bench id>.md` — 3 to 5 labelled pattern bullets in this order (skip a label with nothing worth
saying):

```
- **难在哪**：…
    - <numbers, optional>
- **成功靠什么**：…（方法；可引 §2.x）
    - 例：… {{case:KEY}}
- **常见失败**：…（可引 §4.x / §6.x）
    - 例：… {{case:KEY}}
- **值得一看**：…（only when the case illustrates none of the bullets above）{{case:KEY}}
- **注意**：…（评分或任务侧问题，引问题 N；没有就省略；the share build drops this bullet with its sub-bullets）
```

Agent note `notes/agent/<slug>.md` — the agent page mirrors the topics: its sections carry the topic numbers and names
(1 结果, 2 解题方式, 3 agent 风格, 4 失败模式, 5 时间与预算, 6 模式差距, 7 改进方向, 8 有效性). The page draws this agent's
charts under each section; every chart's computed takeaway gets one sampled example automatically (`build.takeaways`),
so the note does not restate a chart. The note gives the summary and each section's 2–4 pattern bullets:

```
- **一句话**：…（这个 agent 最突出的一点，≤ 40 字）
- **强项**：…
    - <numbers>
- **最该注意**：…（最常见、最值得改的问题）
    - <the one or two concrete forms it takes, § linked>

## 2 解题方式
- <pattern: what is distinctive for this agent>（§2.x）
    - 分析过的 privileged trial 里…的：<Agent> k/n，Luna k/n
    - 例：<task> … {{case:KEY}}
## 3 agent 风格
## 4 失败模式
- **低层**：…（§4.1 / §4.4.x）
    - …
    - 例：… {{case:KEY}}
- **高层**：…（最常见的一两类高层错误，名字用 §4.8.x 的叫法）
    - 例：… {{case:KEY}}
- **阶段**：…（§4.2）
## 5 时间与预算
## 6 模式差距
## 7 改进方向
- …（这个 agent 最常缺的一两处改动，链 §7.x）
## 8 有效性
- …（only if something is specific to this agent: integrity, filters, token limits; else omit the section）
```

Input: `uv run --no-project --with markdown==3.7 --with pillow python tools/agent_packet.py "<agent>"` prints each
section's chart numbers and this agent's labelled examples (thinking errors, grasp failures, approach notes, remedies).
Rules: say what is distinctive compared with the other agents (the chart already shows the numbers; do not restate a
chart cell by cell); every example says what the agent believed or did and what happened, task named; numbers only via
placeholders with `agent=<name>`, naming numerator and denominator; link the topic finding (§t.n or §t.n.m) that
gives the cross-agent picture; findings-5 length limits; one case numbering runs down the whole page (note and chart examples).
Check each note with `cd tools && uv run --no-project --with markdown==3.7 --with pillow python render_check.py note:agent/<slug>`
(or `note:bench/<id>`): every placeholder resolves and every sentence matches its numbers.

Rules (both kinds): numbers only through placeholders (`{{q:rate|bench=…|mode=…}}`, `{{q:rev|…}}`, `{{q:ann|…}}`); refer to findings as §t.n
and issues as 问题 N; at most one case mark per bullet; say what is distinctive, not what every benchmark or agent
shares; when comparing with GPT-6 Luna, remember non-Luna agents ran only the cells Luna did not pass. Never use the
word "oracle". Never write the word 判读 in text a reader sees (the build fails on it); say 分析, the glossary term
(分析认为, 抽样分析的 trial, 一条分析记录, 分析过的 trial 数). Reply with the list of files written.
