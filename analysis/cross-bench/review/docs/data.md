# Logs, files and the page contract

## What each run leaves (trial cache `$XB_RAW/<key>/`, from `../tools/fetch.py`)

| file | content | used for |
|---|---|---|
| `agent/trajectory.json` (ATIF) | every step: time, message, reasoning (Gemini, Claude; not Codex), tool calls and outputs, images received | events, packet, search, `looks/`, the log on the page |
| `trial.json` | board record: result, end reason, exception, per-request model times and tokens, file list | facts, external causes (provider block, crash), the service-log path |
| `verifier/reward.json`, `grade.log` | grader result and its metrics | success, the measured quantities the agent should have checked |
| `verifier/replay.mp4`, `replay.last.png` | the graded replay (simulated time) and its last frame | the video, the poster |
| `verifier/episode.jsonl` (on the board; `sync --fetch`) | service log: per call time, physics steps, checkpoints, resets, end | video alignment, whole-trial video |
| `verifier/trajectory.npz` (on the board) | action sequence, no state | re-rendering in the simulator image |
| `artifacts/app/output/` | the agent's own code and deliverables | reading the final method |

## Work directory (`$REVIEW_DATA`)

| path | written by | content |
|---|---|---|
| `sample.json` | `sample` | `[{key, agent, outcome, task, bench, why}]` |
| `events/K.jsonl` | `prep` | one event per line: `{id: "e12", t: minute, kind, name, text, out, img}`; kinds: message, thought, shell, write, read, image, plan, other |
| `facts/K.json` | `prep` | budget, used and left minutes, first submit / output, clock checks, resets, submits, external flags, grader scalars |
| `packet/K.md` | `prep` | what the annotator reads: task text, grader result, facts, every event (messages and reasoning in full, commands and outputs trimmed to fit 160k characters) |
| `looks/K/` | `looks` | `<eid>-<n>.jpg` and `index.json` `{eid: [files]}` |
| `recaps/K.json` | `annotate` | the model's recap (schema in `prompts/recap.md`) |
| `prompts_sent/K.md`, `annotate_logs/K.log` | `annotate` | the exact prompt sent, the agent's reply |
| `verified_recaps/K.json` | `check` | the recap plus, on every quote: `ok`, `found` (event id), `t`, `pos`, `late`; on every item: `ok`, `problems`; on decisions: `at` (minutes and resets left); and `time` (script codes), `resets`, `quotes` |
| `service/K/episode.jsonl` | `sync --fetch` | service log |
| `videomap/K.json`, `fullvideo/K.*` | `sync`, `video` | see video.md |
| `pages/K.json` | `pages` | the page contract (below) |
| `judgments.csv` | web app | verdicts |

## Page contract (`pages/K.json`)

| field | content |
|---|---|
| `key, agent, bench, task, mode, success` | identity and result |
| `budget_min, used_min, left_min, end_reason, resets {budget, used}, submits, level` | header facts |
| `task_zh, result_zh, task_text, reward` | one-line task and result (model), full task text, grader scalars |
| `replay` (bool), `replay_map`, `full` | the videos: `full` is `fullvideo/K.json` or null |
| `cards[]` | `{id, section, kind, title, text, tag?, facts[], note, ok, problems[], slots[], ladder[]?}`; `section` ∈ end, progress, failure, no_return, decision, time, fix, style; `kind` picks the color |
| `cards[].slots[]` | `{label, id (event id or "task"), t (minute), src, text (the quote), ok, late}` |
| `turns[]` | `{n, t, title, events[]}`, one per model step; event: `{id, t, kind, label, text, cut, out (digest), out_len, imgs[], tags[] (err, submit, reset), cited[] (card kinds that quote it)}` |
| `unclear[]` | what the model could not decide |

A card's id is stable within a trial (`end`, `claim`, `progress`, `f1`…, `no_return`, `d1`…, `time-<code>`, `fix`,
`style`); verdicts refer to it.

## Verdicts (`judgments.csv`, append-only; the latest row per reviewer, trial and card counts)

`time, reviewer, key, claim (card id), cat (card kind), method (card section), verdict (正确 | 不认同 | 证据不足), comment, seconds`

## Web endpoints (`web/app.py`)

| endpoint | returns |
|---|---|
| `GET /api/trials` | `[{key, agent, task, success, cards: [ids to judge]}]` |
| `GET /api/page/{key}` | the page JSON |
| `GET /api/event/{key}/{eid}` | full text and output of one event (the page has digests) |
| `GET /api/search/{key}?q=` | ids of events whose full text or output matches |
| `GET /api/judgments?reviewer=` | `{key: {card: {verdict, comment}}}` |
| `POST /api/judge` | `{reviewer, key, claim, verdict, comment, seconds}` |
| `GET /full/{key}`, `/video/{key}`, `/poster/{key}/{full\|replay}`, `/look/{key}/{file}` | media (HTTP range requests work) |

## Privacy

This repo is public: only code, prompts and docs are versioned. Trial logs, recaps, pages, videos and verdicts stay
in the work directory. Tokens come from the environment and are never written to disk.
