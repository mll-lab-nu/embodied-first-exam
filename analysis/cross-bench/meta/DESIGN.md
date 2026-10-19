# Cross-benchmark analysis: design

Scope: every run on the batch-eval monitor (all benchmarks × agents × modes).
Goal: interesting findings and failure cases, backed by evidence; statistics only where a claim would otherwise be wrong.
This file is the stable design. Decisions and changes go in `PLAN.md` (append-only); current state in `HANDOFF.md`.

## Principles

| Principle | Meaning here |
|---|---|
| Findings first | Every page leads with a claim; tables/figures are evidence for a claim, not the content |
| Agent = model + native harness | No harness/model split (user, 10-16) |
| Progressive | Coverage sample first, then targeted deepening; stop a topic at saturation (N new reviews add no new code) |
| Incremental | Work keyed by trial fingerprint; reruns/new tasks only touch what changed |
| Read once | A trial is read at most once per depth per codebook major version; synthesis reads review JSON, never raw logs |
| Flexible | Codebook and topics are versioned and expected to change; reviews store raw observations so re-coding rarely needs re-reading |
| Single source | Each fact/case/finding exists in one place; pages link, never copy |

## Data sources

| Source | Gives | Notes |
|---|---|---|
| `api/pool` → `jobs` | one job per cell (catalog task × run): state, reward, exception, `trial_id`, tag, attempts | decides what is current; a rerun replaces the cell's job in place (no history); no job = not scheduled |
| `api/tasks` | catalog (task, bench, mode, base, family, timeout), `luna_filter` | `filtered` = non-Luna cell skipped by design (Luna passed) |
| `api/monitor` | per-trial record: flags, end reason, tokens, `usage_limit`, `api_fatal`, ext tools, answer packages | used only for the trials it lists; on 10-17 it listed either ~180 live trials or all ~9,300 |
| `api/trial?id=` + `api/file` | detail (reward.json, gateway, file list); `result.json` (`task_checksum`, times, `exception_info`); trajectory, logs, code, replay | `fetch.py` takes only what the depth needs; trials on hosts no longer served give HTTP 500 |
| `api/model?run=<run>&source=archive` | the monitor's global results: one row per run × task dir (latest counted run) | `tools/perf.py` → `$XB_DATA/perf.json` (fields u t b m s sc e v c id + fetch time; run by publish.sh when BEL_TOKEN is set); every success rate reads it (`queries.load_perf`: sc = 1, graded = success / failed, core = e = 0, rsb out; `filter=drop` leaves out Gemini content-filter stops, which the monitor counts as failures). RoboOlympics dirs are `roboolympics-fun-…` / `roboolympics-match-…` there and in core_set.toml, `roboolympics-…` in the index (`queries.dir_name` / `index_name`) |
| work-e5 Astra analysis | 79 reviews, `reviews/xm/compare.json` (HB/KinDER/BiGym2/MolmoSpaces) | cite, do not redo |

Known selection effect: from the 10-09 batch, non-Luna agents ran only cells Luna had not passed. Their rates are on that subset.

## Data layer (`index.py`, 10-17)

All tools read and write `$XB_DATA` (default `data/`, which the published report reads). Stage a refresh in
`XB_DATA=…/data-next` and copy it over `data/` only when the report is rebuilt from it.

| File in `$XB_DATA` | One row per | Key columns |
|---|---|---|
| `cells.csv` | catalog task × run in `common.AGENTS` | `status`, `reason`, `trial` (key), `trial_id`, `job_*`, `attempts`, `finished`, `task_checksum`, `version_same`, `review` |
| `trials.csv` | current trial of a finished cell | today's columns + `trial_id`, `task_checksum`, `job_tag`, `attempts`, `fields_from` (monitor / detail / pool) |
| `superseded.csv` | trial key no longer current (cumulative) | `replaced_by` = new key, `outside-pool` (cell has no job) or empty (rerun pending; `job_state`) |
| `tasks.csv` | catalog task | + `versions` (distinct `task_checksum` among current trials), `checksum` (most common) |
| `snapshots/<YYYYmmdd-HHMM>/` | index run | `cells.csv.gz`, `trials.csv.gz`, `changes.json` (added / changed / gone / replaced vs the previous snapshot) |
| `prn.csv`, `c30_plan.csv` | catalog cell / selected cell | fixed random number `u` (`meta/sample30.json`); `sample.py c30` plan |

| Cell status | Meaning |
|---|---|
| `done-valid` | finished, current trial valid |
| `done-rerun` | finished but infra: usage limit, rate limit, gateway refused, `api_fatal`, transport cut, no reward, infra / grader error |
| `done-excluded` | rule or suspect trial; or `no_trial` (result imported without a trial) |
| `in-progress` / `held` / `infra-failed` | pool job state |
| `skipped` / `not-scheduled` | no job; `skipped` = non-Luna cell with `luna_filter = filtered` |

- Matching: a trial is its trial name (text after the last `/` of either id format); key = `<run>__<trial name>`, so old raw caches and reviews still apply.
- A trial seen before keeps its row and fingerprint; identity columns follow the pool (renamed tasks, e.g. `cell-*` → `rsb-*`). Pool-only rows are rebuilt each run.
- A new trial gets detail + `result.json` once, cached in `/data/pingyue/cross-bench/index-cache/<trial name>.json` (with its monitor record); a kept trial fetches `result.json` only. At most 8 parallel requests; errors are retried next run.
- Monitor-only fields (empty when the monitor does not list the trial): `end_reason`, `gave_up`, external tool calls, answer packages, `api_fatal`, `usage_limit`, `transport_cut`, `live_success`. Gateway refusals then come only as a refused-host count.
- `review` per cell: `current` (current trial reviewed or selected in the ledger), `replaced` (only an older trial of the cell was), `outside-pool` (cell has no job), `none`. `queries.load` maps `done-*` to `done` for the pages.
- `TokenBudgetExceeded` / `OutputTokenExceededError` stay valid failures; `index.py` prints them per agent.
- Open: `task_checksum` differs for most trials of one task (10-17: 7,516 distinct among 9,221 trials), so it seems to
  cover per-run files; `versions` / `version_same` are not yet a reliable task-change signal.

Task sets (user 10-18; `queries.SETS`, `load(which)` / `load_all(which)`, env `XB_SET=core|all`, default core):

| Set | Tasks | Built by `build.py` |
|---|---|---|
| core (核心集) | every task dir listed in `tools/data/core_set.toml` (embodied-first-exam `docs/core_set.toml`, user 10-18 night; 843 dirs, each mode dir its own task, owner picks included; `queries.in_set` matches the trial's `task` = base + mode suffix) | `--set core`; `--both` → `<out>/` (internal + `share/`) |
| all (全部任务) | every task | `--set all`; `--both` → `<out>/all/` (internal + `all/share/`) |

- RoboSafeBench (`rsb`) is left out of both sets for now (trials, cells, tasks, cases, bench nav). The text is written on core.
- `data/easy_bases.txt` (the old easy set, rcb `docs/easy_set.toml`) is kept but no code reads it.
- Every trial carries the EFE Task Atlas fields from `data/atlas_tasks.json` (`queries.atlas`): `tasktype` (list), `body`,
  `cap` (list); a base not in the Atlas is `unclassified`, an Atlas task without capabilities `cap = none`. Names and
  definitions: codebook `trial_zh`. Both files are inputs, read from `HERE/data` whatever `XB_DATA` says.
- `--both` also runs `compare_sets`: per finding, each `{{bars:…}}` and `{{q:…}}` on both sets; flagged when a strip's top
  group changes or a share moves by more than 10 points (values from fewer than 20 not compared) →
  `/data/pingyue/cross-bench/core_vs_all.md` and a note on the all build's home page. Each page has a 核心集 ⇄ 全部任务 switch.

Time limit per trial: `cutoff_min` = the limit the trial's own instruction stated (features `budget_min`, else the digest header "agent X of Y min"), never the catalog timeout alone — the catalog can be stale (RoboWits: 60 in the catalog, 90 in the instruction and the runs).

## Pipeline

| Stage | Covers | Output | LLM |
|---|---|---|---|
| `index` | all pool cells | `$XB_DATA/{cells,trials,tasks,superseded}.csv`, `changes.json`, `snapshots/` (see Data layer) | no |
| `features` | all valid trials | per-trial process features: time split, clock checks, first deliverable time, test/reset counts, image views, approach heuristics from final code | no |
| `digest` | sampled trials | `skeleton.md` (agent messages, commands, result lines, final claim; ≤8k tok) and `timeline.md` (full, long outputs head/tail-trimmed) | no |
| `sample` | frame = valid finished trials | review queue with reason per trial (`coverage` / `contrast` / `all-fail` / `near-miss` / `anomaly` / `hypothesis:<id>`) | no |
| `review` | queue | `reviews/<key>.<depth>.json` per codebook (`skim` reads skeleton; `deep` reads timeline + frames + final code) | yes, subagents, batched per benchmark |
| `approach` | reviewed trials | `annot/approach/<key>.json` (prompt approach-1): who decides each action, techniques, perception, deliverable — from the review text | yes, subagents |
| `integrity` | trials with `int_*` signals or monitor rule flags | `integrity.py sample` → focused excerpts → `annot/integrity/<key>.json` (prompt integrity-1) | yes, subagents |
| `remedy` / `grasp` / `reasoning` | reviewed failures | `annot/<kind>/<key>.json`: smallest change that flips it (remedy-1), how a grasp failed (grasp-1), the thinking error behind it (reasoning-1: level high / both / low / external + kinds) | yes, subagents |
| `progress` | sampled reviews (failures and successes) | `annot/progress/<key>.json` (prompt progress-1): first time each level 0–5 was reached, where it got stuck, and for a failure the critical point (kind, time, noticed, what the agent did next) — from skeleton + review | yes, subagents |
| `packet` | — | per-topic numbers + review lines for synthesis (`packet.py <topic> / overview / integrity / entities`) | no |
| `build` | — | site JSON + pages; numbers and charts computed at build time (`queries.py` metrics, `figs.py` + `charts.py` charts) | no |

Measured sizes (Astra cache): trajectory.json median 2.6 MB, digest median 140 KB (~35k tok). Full reads of every trial are not worth it; the depth ladder below is.

## Who runs what (model roles, from the 10-16 pilot)

Pilot: 24 trials that already had an Opus skim review (16 failures, 8 successes, 24 benches) were re-reviewed blind by
Opus, Sonnet and Haiku (`/data/pingyue/cross-bench/pilot/`, `tools/agreement.py`). Agreement with the original review:

| Field | Opus again | Sonnet | Haiku |
|---|---|---|---|
| primary cause, exact (16 failures) | 12 | 10 | 9 |
| primary cause group | 13 | 11 | 11 |
| stage of the decisive error | 13 | 11 | 9 |
| claim / clock checked (24) | 24 / 22 | 24 / 24 | 23 / 24 |
| style fields (on_failure, plan_vs_act, verification, loop) | 15–20 | 16–23 | 13–20 |

Sonnet's disagreements are defensible root-vs-symptom choices, the same kind Opus makes against itself. Haiku wrote
concrete text but twice coded a cause that contradicts its own `decisive.what`. All three use ~20–30k tokens per skim.

| Work | Model | Check |
|---|---|---|
| skim reviews in bulk; label passes (approach, remedy, grasp, reasoning) | Sonnet | Opus re-reviews 10% of every batch; agreement on primary cause group < ~65 %, or any code that contradicts its own text → redo the batch with Opus |
| mechanical checks: code vs text consistency, missing fields, JSON validity | Haiku (or scripts) | flags go to Opus |
| deep reviews, adjudicating disagreements, findings, entity notes, synthesis | Opus | reviewer pass + `tools/check.py` |

Each review records `reviewer` (opus / sonnet / haiku), so a batch can be audited or redone later.

c30 QA (10-17; Opus blind re-review of one trial per batch, 244 batches, 168 failures): outcome 100 %, claim 95 %,
clock 91 %, loop 81 %; the same primary cause group per trial 59 %, but Opus's primary group is among Sonnet's
primary + secondary causes in 80 % and the pooled group shares differ by at most 4.8 points — time is the largest gap
(primary 8 % Sonnet vs 13 % Opus). Re-picking the primary with Opus from Sonnet's text did not help (48 % on 87), so it
was dropped. Haiku consistency checks flagged 74 records (`c30/check_flags.json`); Opus adjudicates and fixes them.
Rules that follow:

QA rate adapts (user, 10-17): start at ~10 % (one per batch); once ~150 re-checks show a field is stable, stop
re-checking it. progress-1 reached that after 175 (best level 91 % exact, 99 % within one level; critical kind 86 %),
so its remaining batches run without QA. Mechanical work (bulk reviews, labels, text clean-ups, small code edits from a
precise spec) goes to Sonnet, checks to Haiku; Opus only for QA, adjudication, chart design and writing findings.

| Field | Source for shares |
|---|---|
| failure cause groups, stage, claim, clock, loop, labels | Sonnet + Opus reviews; time-family claims are cross-checked with primary-or-secondary counts and state that the primary share is a lower bound |
| `style.on_failure`, `style.plan_vs_act` | Opus reviews only (Sonnet labels "tweak" / one extreme where Opus says "mixed": 89 vs 37 tweak); n stated |

## Sampling rounds

| Round | Selection | Depth |
|---|---|---|
| 1 coverage | per cell (bench × agent × mode): 1 random failure + 1 random success, seeded by cell | skim |
| 1 coverage | per bench × agent: 1 random trial | deep |
| 2 targeted | contrast pairs (same task, mode or agent flips), tasks every agent fails, near-misses, anomalies | deep |
| 3+ | follow open hypotheses and new codes until saturation; new trials join the frame automatically | skim → deep |
| c30 | `done-valid` cells with `u < 0.30` per agent × bench × mode × outcome; strata below `max(1, round(0.30 N))` topped up (coverage-r* reviewed first, then lowest `u`); never removed; rule in `meta/sample30.json` | skim |

Every selection is logged in `ledger.csv` with its reason and seed.

Success rates (q:rate, q:unsolved, the common / modes / unsolved charts, the results table, agent and bench rate lines) use the monitor's global results (`perf.json`, see Data sources), not the sample. The report writes counts, k/n, not percentages (user 10-18 night, reversing the proportions-only rule): q placeholders print `k/n`, `show=k` / `show=n` print one side; chart labels and tips give k/n; `check.py` WARNs about findings / notes lines that still give a percent or share word (`/data/pingyue/cross-bench/rewrite/v21_pct_hits.tsv`).

Shares use the random sample only: every share in a figure or a `{{q:…}}` value counts reviews and labels (integrity
labels too) of the current trial of a c30-selected cell (`queries.sampled`); the other reviews (coverage-r*, integrity,
hypothesis, contrast, near-miss) stay cases and deep-read material. Weights are off by default; `XB_WEIGHTS=1` weights
each row by done-valid cells in its stratum / sampled rows in it (`queries.tally`; the n shown stays the plain count).
`tools/weights_check.py` prints unweighted vs weighted shares; `site.sample_note` is the data-status line.

## Analysis topics (each topic = one site page)

Hierarchy (user, 10-17): a top-level finding §t.n is one general claim that holds across agents or benchmarks, with
the pooled numbers; a child §t.n.m is one mechanism or sub-type of it (seen in at least two agents or benchmarks);
agent- and benchmark-specific facts are indented examples inside a child and on the agent / benchmark pages, never a
finding of their own. About 3–5 top-level findings per topic.

Agent focus (user, 10-17): the strongest agents lead everywhere — GPT-6 Astra, Gemini 4 Argon, Opus 5.5 — then GPT-6
Luna, GPT-6.1 Sol, GPT-6 Sol, GLM-5.3 Flash, DeepSeek V4.1 Flash, Gemini 3.8 Flash, Qwen3.8 27B (`site.json`
`agent_order`; every chart, table and list uses it). Findings describe the strong agents first and bring the others
in as contrast. A child's title starts with the category name its parent's chart uses (e.g. §4.4.1 「抓取·没拿进手里」).
Every example says first why it was chosen — the claim it shows (e.g. 「standard 一次物理事故就定局：…」).
Agent pages follow the same focus: the three strongest get the fullest pages — every section 3–4 bullets, each with 1–2
examples, plus a short 「强在哪 / 还会输在哪」 part built from contrast deep reads (Opus): per strong agent ~5 tasks it
solved where most others failed and ~5 it failed where another agent solved; the other agents keep compact pages
(2–3 bullets per section, one example each).

| Topic | Question |
|---|---|
| 1 Outcomes | who solves what on the same cells; never-solved tasks |
| 2 Solution paradigms | who decides each action (code open / closed loop, search, agent step by step), techniques, perception, deliverable; what works where |
| 3 Agent styles | plan vs act first, exploration, pivot vs tweak (Opus-reviewed trials), verification, stopping, honesty of the final claim |
| 4 Failure modes | why trials fail, one taxonomy (shares add to 100 %): overview (two layers + critical point); low level = action family (grasp / contact, collision and motion, fall) and time family (no deliverable at the deadline, deliverable saved late, misjudged remaining time, reset or token budget used up); 关键点与进展 (below); high level = the five thinking-error groups (理解 / 方法 / 计划 / 查证 / 调整) behind the direct cause |
| 5 时间的用法 | how agents treat time regardless of outcome: clock checks, budget planning, mental arithmetic, running to the limit vs stopping early; environment-side clock issues |
| 6 Mode gaps | what breaks from privileged → standard → realtime |
| 7 Improvement | the smallest change that would flip a failure (the reviewer's judgement, not a rerun): agent side, harness side, longer term; benchmark side last (internal) |
| 8 Validity (internal) | infra losses, filters, rule flags, suspect tasks: recorded only, benchmark internals untouched |

关键点与进展 (topic 4; labels progress-2, relabels of progress-1 in `annot/progress2`):
- Two kinds of critical point. **Key steps** (关键进展) = the milestones of the ladder below. **No-return events** (不可挽回点) = the first event after which a failure could no longer pass and no reset could undo it: fall, object out of reach, terminated by the task, or none. Charts: `fig:noreturn` (kind per mode / agent), `fig:nrafter` (with time left after it: stopped / kept trying, and the time left), `q:progmed` for when it falls and the minutes wasted.
- Time-out, resets used and a bad deliverable are not critical points: they are **end types** (how the trial ended: time-out / resets-used / deliverable / agent-stopped / goal-done / crash; `fig:end`). The progress-1 critical point (`crit`, `fig:crit` / `crit_time` / `after`) is retired and kept only until the text moves over.
- Thinking-error level per failure (reasoning-1 + when-1): high, before (事前想错), after (事后没挽回), low (both→low included), external; a both without a when label stays both (未细分) and is drawn after low.
- Time-point charts (figs_time, 10-18): `fig:arrive|event=` level1 / level3 / level5 / deliverable / noreturn / end (x = share of the trial's own limit, y = share with the event by then; lines success vs failure, or by=agent one per agent in slots --cat1… with panels by mode); `fig:best` = best level of all sampled trials (`fig:stuck` = failures only); `fig:swimset` = k swimlanes picked by rule (`swim_candidates`).
- Progress over time on one ladder (0 no working control · 1 moves or sees · 2 reached the target area · 3 key contact or action once · 4 most of the task · 5 done; privileged = the agent's own test runs, standard = the live episode). Charts: a progress staircase on every case page with the critical point marked; "卡在哪一步" = share of failure time spent at the last level reached, per agent; progress curves = share of trials that reached each level by time, success vs failure.

## Site (artifact) structure

```
Home  = summary cards (findings/_summary.md blocks, one chart each) · top findings · topics · data status (internal)
├ Topics      one page per topic; a page is a list of findings for that topic
├ Benchmarks  grouped by category; entity page = data table + links to its findings and cases
├ Agents      first entry links to topic 6 三家对比 (`#topic-compare`, findings 6.x; the old `#agent-compare` redirects
│             there); then one entity page per agent = profile table + links to its findings and cases
├ Cases       filterable index (thumbnails) → one page per case
└ Method      data status, sampling, codebook version, changelog
```

Audience: two builds from one source. **Internal** (for the authors, `<out>/index.html`) shows everything and has a
`#samples` page (one real example of each chart kind, a finding block, a child section, a case card, a legend: the
reference for restyling). **Share** (for other readers, `<out>/share/index.html`, media linked) leaves internal items out
of its data: findings with `audience: internal` (validity §8, benchmark-side improve §7.17–§7.18) and their children,
the issues register, data status, integrity labels, cases cited only by internal items, a bench note's **注意** bullet
and an agent note's internal sections. Internal topics come last, so both builds use the same numbers. Text for one
build only is marked `<!-- internal -->…<!-- /internal -->` / `<!-- share -->…<!-- /share -->`; in the share build a
bracketed reference to an internal item is dropped. A 内部版 ⇄ 分享版 link sits top right (`--no-switch` to omit).

Ownership (high cohesion, low coupling):
- **Child section** (`findings/<topic>.<n>.<m>.md`, `parent:`, shown as §4.2.1 inside its parent): one category of a list the parent names (definition, how common, 2–3 concrete examples, how to avoid); no figure.
- **Finding** (`findings/<topic>.<n>.md`, shown as §4.3): one claim, one topic, entity tags, evidence = queries + case ids, status `current` / `recheck` / `retired` (retired files are deleted; old versions are in `/data/pingyue/cross-bench/backup/*.tgz`). Numbers follow the reading order; when a restructure breaks that, the topic is renumbered and the map recorded in `renumber_map.json`; a new finding takes the next free number in its topic (`order: 1` puts an overview first in its section). Issues are `问题 N`. Rendered on its topic page only; elsewhere as a link.
- **Case** (`cases/C###.json`, generated from a deep review + curator note): rendered on the case page only; elsewhere as a thumbnail card.
- **Numbers**: computed by `queries.py` at build time; never typed into prose. Each carries a hover note (`qtips.py`) naming its denominator and numerator; the sentence names them too.
- **Bar strips**: `{{bars:<kind>|<filters>|by=agent3|mode|agent}}` evaluates `{{q:<kind>|<filters>}}` for 全部 and once per row with one filter added (agent3 = the first three of `agent_order`, then the other seven pooled; mode; agent = all ten) and draws label · bar filled to k/n · "p%（k/n）" (`build.bars_block`). A muted caption above says what is counted and out of what (`qtips.counted`); each row has its `q:` hover note; rows with n < 20 are italic with 样本少. A finding's 多常见 bullet is one strip on the body's first line, so it sits under the title. Styles in `tools/site/style.css` (`.qbars`); `check.py` fails on an unresolved strip.
- Entity pages hold no prose except a ≤3-line summary owned by that page.
- Same page template everywhere: claim → figure/table → points → cases.
- Finding body (findings-4; findings-3 plus: a `图意：` line under every figure, one bold phrase, optional `star:` case): 要点 bullets (no prose paragraph) → 证据 bullets → optional chart → 解读 → 适用范围; terms explained once from the shared glossary in prompts/findings.md; cases cited as numbered
  marks `[n]` (cards below carry the same numbers); bare finding IDs auto-link; only IDs are links in lists.
- Topic page: section index at top, findings grouped by `section:`; an overview (`order: 1`) leads its section. Home findings (`top:`) carry a 重点 tag; starred cases a 精选 tag.
- Charts: CSS bars, legend + hover tip + folded table view; categorical slots `--c1…--c8` in fixed order, `--c0` neutral; families share a hue (Code to Control = `--way-open` / `--cat1` / `--way-search`, the tokens of `figs_way.css()`; stages by phase: before acting `--b1…--b4`, acting `--c2`, wrapping up `--g1/--g2`, time `--c7`). Every chart has a one-sentence takeaway (written `图意` in findings, computed on entity pages); `build.py` puts it above the chart's caption.

Media: key cases embed a compressed replay (≤960 px, 15 fps, key moments marked); others show last frame or 3 thumbnails; overflow is listed in the Cases index with a monitor link. Publish limits: 255 files, 15 MB per binary.

## Report standard (from the user's reviews, 10-16; every new report run must meet it)

| # | Requirement | Enforced by |
|---|---|---|
| 1 | Clear, simple, logical, consistent; each change merges into the existing structure and never makes it messier | reviewer pass before publish |
| 2 | Hierarchy: topic → section → finding §t.n → child §t.n.m; numbers follow reading order; no letters or pinyin; issues are 问题 N | `build.py`, `check.py` |
| 3 | Bullets, not paragraphs; conclusion first; one fact per bullet; nothing said twice; length limits of findings-5 | prompt findings-5, `check.py` |
| 4 | Explain, with examples: every list of categories (error kinds, loop types, time problems, symptoms) gets child sections with definition, how common, 2–3 concrete examples (what the agent believed or did and what happened, task named), how to avoid | prompt findings-5 |
| 5 | Every non-obvious term explained at first use from one glossary: `codebook.json` → `glossary_zh` (the findings prompt points to it; the page shows it as a hover / tap note on a term's first use in a block, and on mode tags); names must explain themselves (no 交付太晚 → 很晚才存交付物); a cell (one task, mode included, given to one agent; a rerun replaces its trial) is **评测项** in all Chinese text | `glossary_zh`, codebook `cause_zh` |
| 6 | Every ratio names its denominator and numerator in words; each number also has a hover note | prompt, `qtips.py` |
| 7 | Prefer charts to tables; > 5 numbers in a row become a chart; a chart is kept only if it shows its finding's claim | prompt, reviewer pass |
| 8 | Every chart has one takeaway line (图意 in findings, computed lead on entity pages; the takeaway only) and, right under its title, one generated 怎么读 line: what one row is, what the bar or cell is, what the number counts, who judged it; a fraction in either uses the n the row shows | prompt, `check.py`, `figs._lead`, `charts.howto` |
| 9 | Legends print each category's definition (never hover-only) | `charts.legend` |
| 10 | Colours as in the Colours section below: one palette in fixed slot order, every legend's colours clearly apart, valence charts keep success green `--ok` and failure red `--n1` | `palette.py`, `figs.py`, `check.py` |
| 11 | Group structure inside a row is drawn per row (each row's own dividers), not as panels aligned across rows | `charts.phased` |
| 12 | Interesting items stand out: home findings carry 重点, ≤ 1 starred 精选 case per finding, one bold phrase per finding | prompt, page |
| 13 | Numbers only from placeholders; fair comparisons on shared cells (`with=`); state the Luna-failed-cell bias | prompt |
| 14 | Cases: numbered marks [n] with agent · bench · task · mode; every card's bold lead line is the claim it shows: the first clause (≤ 24 字) of the bullet that cites it, or of its parent bullet when that bullet is only an example line (例 / 例子 / "agent · task：…"), else the finding title's first clause; never a generic word; a child shows its own cards; video on hover; a missing video states why (usually no saved trajectory) | `build.py`, page |
| 15 | Entity pages (agent, benchmark): title → summary bullets → one-line row of numbered section links → numbered sections (badge + name, rule above; an agent page uses the topic numbers). In a section: 2–4 pattern bullets, each with its numbers and one example as indented sub-bullets (notes-4), then chart cards (title → takeaway bullets → chart); every computed takeaway carries one sampled example with a case link. Sizes: section heading > chart title > body ≥ takeaways and bold phrases | `app.js entSections`, `build.takeaways`, notes-4 |
| 16 | Chinese text without English words except names, code and the listed terms; never the word "oracle" or 判读 (the term is 分析); never how a task "should" be solved | prompt, `check.py` |
| 19 | Every 100% bar shows its 0–100% scale and what the count column is (分析过的 trial 数 = sampled reviews, not totals); rows from < 20 reviews keep their colours, the label is italic with a 样本少 tag and the tip gives the error margin; the note says why the Sol / Qwen rows have few trials | `charts.py` |
| 20 | Classifications stay few and non-overlapping; a structure that repeats itself (same pattern in two findings) is merged into one parent with children | reviewer pass |
| 21 | A search box finds any finding, child section, case, issue, benchmark or agent by plain words (all terms must match) | page `search` |
| 17 | Phone width: no page-level horizontal scroll; wide charts and tables scroll inside their own box; table headers never break one character per line | route check (HANDOFF), page |
| 18 | Task-side oddities go to the issues register; benchmark internals are never changed | prompt, `_issues.json` |
| 22 | Two audiences (Audience, above): the share build holds no internal item, ID, issue text or link to one, not even hidden; internal topics are numbered last | `build.py --both`, `check.py --audience share` |
| 24 | Never a number without what it counts, out of what, and who judged it (分析, 评分程序 or log counts); plain words over coined ones (主改动 → 分析认为最该补的一步) | prompt, 怎么读 line, `qtips.py`, `glossary_zh` |
| 23 | Layout = style B 工作台: a left rail (search; this topic's contents, titles wrapped, never cut; topics; folded Benchmark / Agent lists); a finding is a card: title, 要点, main chart panel (图意 → caption → chart), folded 证据 / 解读 / 适用范围, child panels, cases, 上一节 / 下一节; home = one card per `_summary.md` block with one compact chart (≤ ~12 rows, no long legend below) picked in `site.json` → `home` (`fig`, `from`, `say`; no `say` = the 图意 of the same figure in `from`) | `tools/site/*`, `build.home_blocks` |

## Colours

- Approaches (v17, user 10-18; `queries.way`, `figs.LOOP` / `WAY_FAMILY`, codebook `approach_zh.way_family`; English names
  from embodied-first-exam.ai, user 10-18): Code to Control (code-open 开环, code-closed 闭环, search 搜索参数), Direct
  Control (agent-segment), Train Model to Control (technique `rl`, whatever the loop), 混合, 无. `fig:loop` is a grouped chart (charts.phased: family shares above each row, the Code to Control members one blue family,
  the others rust / magenta / gold, 无 grey; validate_palette.js passes light and dark).
- Groupings: figures take `by=tasktype | body | cap` (Atlas; tasktype and cap multi-label, the 怎么读 line says a task
  counts in each group: `figs.with_multi`), and the same keys as filters (`q:rate|tasktype=dynamic`); `category` (the
  bench navigation groups of `site.json`) is kept only for old text.
- A chart's categories take `palette.CAT` slots in fixed order (`--cat1`, `--cat2`, …; never cycled, past eight fold into 其他; 其他 / none / 外部 grey `--c0`), so categories outside declared groups always differ in hue; only declared groups (a phased chart's legend groups) may share a hue family, and valence charts keep success green `--ok`, failure red `--n1`.
- `check.py` fails a page where two legend colours of a chart are closer than OKLab ΔE 15 (`validate_palette.js` normal-vision floor) in either theme: every pair without groups; with groups, adjacent members and every pair across groups.

## Incremental rules

- Fingerprint = trial (id or name) + finished time + agent end + reward + state, set when `index.py` first sees the trial. A changed fingerprint, or a trial that a rerun replaced (`superseded.csv`), retires its reviews and flags findings citing it as `recheck`. Task versions are tracked apart (`task_checksum`, `version_same`).
- Codebook minor bump (new code): re-code from stored review JSON. Major bump (changed definitions): re-review only affected trials.
- Topics, codebook and prompts live under `meta/` with versions; each review records the versions it used.

## Layout

| Path | Content | In git |
|---|---|---|
| `analysis/cross-bench/meta/` | DESIGN, PLAN (decision log), HANDOFF, codebook (codebook.json), prompts | yes |
| `analysis/cross-bench/tools/` | index, features, digest, sample, build, queries | yes |
| `analysis/cross-bench/{reviews,annot,findings,notes,ledger.csv}` | analysis records | yes |
| `/data/pingyue/cross-bench/` | raw downloads, digests, frames, media | no |
| `~/Work/cross-bench-artifact/` | published site mirror (registered with `art`) | no |
