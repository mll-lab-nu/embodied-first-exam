# Trial review: recap analysis, annotated video, review platform

Per trial, this produces three things a person (or another platform) can check against the raw log:

1. a **recap**: how the trial ended, how far it got, every failure, the point of no return, the decisions behind the
   failures, script-measured time problems and the likely fix, each item with verbatim quotes and event ids;
2. an **annotated whole-trial video** on the agent's wall clock, aligned with the log;
3. a **review page** where a person judges each recap item (correct / disagree / not enough evidence).

The analysis rules and categories are in [docs/analysis.md](docs/analysis.md), the video in
[docs/video.md](docs/video.md), the logs, files and page contract in [docs/data.md](docs/data.md). The model's only
job is one prompt, [prompts/recap.md](prompts/recap.md); everything else is code and costs no tokens.

## Pipeline

Run from this directory: `python -m pipeline <step> [-h]`. Steps read and write the work directory `$REVIEW_DATA`.

| # | step | does | reads | writes | model |
|---|---|---|---|---|---|
| 1 | `sample` | choose trials (per agent n failures + m successes, fixed seed) | `../data/trials.csv` | `sample.json` | — |
| 2 | `prep` | event list, script facts, evidence packet | trial cache `$XB_RAW/<key>/` | `events/ facts/ packet/` | — |
| 3 | `looks` | images the agent received, per event | `agent/trajectory.json` | `looks/` | — |
| 4 | `codes` | category tables from the report's codebook into the prompt | `../meta/codebook.json` | `prompts/codes.json`, `prompts/recap.md` | — |
| 5 | `annotate` | run the recap prompt once per trial | `packet/`, `search` | `recaps/` | **yes** |
| 6 | `check` | find every quote in the full log, check decision order, add time codes | `recaps/ events/ facts/` | `verified_recaps/` | — |
| 7 | `sync` | wall clock ↔ graded replay (`--fetch` downloads the service logs) | `service/`, replay | `videomap/` | — |
| 8 | `video` | annotated whole-trial video and its time map | replay, `service/`, `verified_recaps/` | `fullvideo/` | — |
| 9 | `pages` | one page per trial: cards, turns, video maps | all of the above | `pages/` | — |
| 10 | `summary` | tables over all trials (+ agreement with the report's labels) | `verified_recaps/` | stdout | — |
| — | `python -m web.app` | review platform on port 8046 | `pages/`, media | `judgments.csv` | — |

Steps 2–4 and 6–10 are deterministic. Re-run a step after its inputs change; `--keys K ...` limits most steps.

## Set up

| need | how |
|---|---|
| Python 3.10+ with `requirements.txt` | `uv venv && uv pip install -r requirements.txt` |
| `ffmpeg`, `ffprobe`; a CJK font for the video overlay | `apt install ffmpeg fonts-noto-cjk` (or set `REVIEW_FONT`, `REVIEW_FONT_BOLD`, `REVIEW_FONT_INDEX`) |
| trial cache | `../tools/fetch.py --media` (needs `BEL_TOKEN`, the eval board token) |
| `../data/trials.csv`, `features.csv` | `../tools/index.py`, `../tools/features.py` |
| an agent CLI for step 5 | default `claude -p` with Sonnet; any CLI that reads the prompt on stdin: set `REVIEW_AGENT` |

| variable | default | what |
|---|---|---|
| `REVIEW_DATA` | `/data/pingyue/cross-bench/pilot-hl` | work directory (outputs, `sample.json`, `judgments.csv`) |
| `XB_RAW` | `/data/pingyue/cross-bench/raw` | trial cache |
| `XB_DATA` | `../data` | `trials.csv`, `features.csv` |
| `REVIEW_AGENT` | `claude -p --model sonnet --permission-mode dontAsk --allowedTools Read Write Bash --add-dir {data} --add-dir {review}` | annotator command |
| `BEL_TOKEN` | — | eval board token, only for `fetch.py` and `sync --fetch` |

Example (10 trials already in the cache):

```
export REVIEW_DATA=/data/me/review
python -m pipeline sample --agents "GPT-6 Astra" "Opus 5.5" --mode standard --core --fail 3 --succ 2
python -m pipeline prep && python -m pipeline looks
python -m pipeline annotate --jobs 4
python -m pipeline check
BEL_TOKEN=... python -m pipeline sync --fetch && python -m pipeline video
python -m pipeline pages && python -m web.app
```

## Cost and size (measured on 10 trials, 10-22)

| item | per trial | notes |
|---|---|---|
| recap tokens (Sonnet 5.5) | ~110k (96k–144k by agent) | grows with the packet: long reasoning (Gemini) costs most |
| recap time | 3–4 min per worker | run several workers (`--jobs`) |
| scripts (prep, check, pages) | seconds | — |
| annotated video render | ~0.3 × video length on CPU | demo: 30-min session → 57 s video in 16 s |
| annotated video size | ~1.1–1.5 × the replay | demo 3.5 MB (replay 2.3 MB); `--max-idle 0` drops the thinking pauses: 25 s, 2.5 MB |

Replays in the local cache (1771): median 31 s and 1.3 MB, mean 125 s and 7.2 MB, p90 349 s and 22 MB.
So 1000 trials ≈ 110M tokens, ~60 worker-hours of annotation, ~12 CPU-hours of video, 8–11 GB of video.

## Moving to another platform

What to take: the prompt (`prompts/recap.md`), the checker (`pipeline/check.py`, `timing.py`), and either the page
JSON (`pages/K.json`) or the checked recap (`verified_recaps/K.json`) plus the event list (`events/K.jsonl`). The page
contract, the judgment format and the JSON endpoints are in [docs/data.md](docs/data.md). A platform must:

- show each card with its quotes, and on a click show the event in the log (all quotes carry an event id and a minute);
- map the video to the log: `fullvideo/K.json` gives beats `[video s0, s1, wall min0, min1]` (docs/video.md);
- store one verdict per (reviewer, trial, card) with an optional comment.

## Limits and open items

- The whole-trial video needs the service log (`episode.jsonl`) of each trial: `sync --fetch` with a valid board
  token. Without it the page shows the graded replay, without labels and not aligned.
- The replay holds only the episode after the last reset; trials that used resets (14% of the standard trials of
  Astra, Argon and Opus) show a placeholder for earlier episodes until those are re-rendered from the action log.
- Labels are checked for evidence and time order, not for correctness: per-category agreement with people
  (`judgments.csv`) decides which categories can be labeled by a model alone. On the 10-trial pilot the primary
  cause agreed with the report's earlier labels in 1/6 trials (docs/analysis.md, "Evaluating the labels").
- The page and the overlay text are in Chinese (names from the report's codebook); the prompt is in English.
