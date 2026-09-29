# Results pipeline

Everything below is code, except the three rows marked **written**, which a person or an agent writes.
Nothing here calls a model. One pipeline serves every benchmark: what differs is its adapter, `benches/<bench>.py`
(see [Adding a benchmark](#adding-a-benchmark)); every other module is written against it.

## What a Harbor trial leaves in `jobs/<job>/<trial>/`

| path | written by | what |
|---|---|---|
| `result.json`, `config.json`, `trial.log` | Harbor | the trial's stages, times, config |
| `agent/sessions/**/*.jsonl` | the agent harness (codex or Claude Code) | every request's usage, the model's messages (and Claude's thinking), every tool call with its command and output, every image the model was shown |
| `artifacts/data/episode.jsonl` | the sim sidecar (`rcb_service.py`), limited only | one line per request: each step with its exact action, every reset with the state it left, how each episode ended, which cameras each answer carried |
| `artifacts/data/{final.json, trajectory.npz, replay.mp4}` | the sim sidecar | the graded episode, replayed fresh at the end |
| `artifacts/app/output/` | the agent | its own files (`gen.py`, notes) |
| `verifier/` | `tests/grade.py` | `reward.json`; full mode also `diagnostics.json` and `replay.mp4` |

Nothing is recorded as video during the run: every video below is rendered afterwards from these logs.

## After the run

| step | command | output (in `<trial>/report/`) | needs |
|---|---|---|---|
| measure | `build.py --add jobs/<job>` (runs `collect.py`) | `summary.json`: tool calls, what each robot command changed (`attempts.py`), images viewed, cost | the OpenRouter key for cost (`--no-billing` skips it) |
| replay | `collect.py` → `scripts/<bench>/replay.py` | `episodes.json` (every episode replayed from the service's log; HumanoidBench's re-scored with the restored reward), `episodes/epN.mp4` | Docker and the sim image; a GPU renders faster |
| session video | `collect.py` → `session_video.py` | `session.mp4` | the same; `--no-video` skips both videos |
| digest | `digest.py <trial>` | `digest.md`, a one-page view for whoever writes the notes | — |
| **written** | `NOTES_GUIDE.md` | `notes.md` (with the `phases` table the timelines colour by), and the run's `note` in `runs.csv` | a person or an agent |
| **written** | — | `results/<bench>/analysis/*.md`: the overview and per-task analysis | a person or an agent |
| **written** | — | the cells of `results/<bench>/README.md` (`build.py` flags a mismatch) | a person |
| pages | `build.py` (`--bench NAME` for one, and with it `--bundle DIR` for a copy small enough to publish) | `jobs/results/<bench>/` | — |

Without the written files the pages still build: the analysis blocks and notes are simply missing.

Agent logs are read for codex and Claude Code (`collect.codex_session`, `collect.claude_session`); another harness
needs its own parser. Claude Code's session files are root-only in the trial: `chmod` them through Docker first.

## Adding a benchmark

| file | what |
|---|---|
| `benches/<bench>.py` | `BENCH`, a `bench.Bench` subclass: names, the standard config, cameras, task labels, what limited mode gives; `scored` when an episode has a return and a pass mark (HumanoidBench), else success only (KinDER) |
| `scripts/<bench>/replay.py` | run in the sim image: a limited trial's episodes replayed from the service's log and rendered |
| `results/<bench>/README.md` | the `## Results` table: `#`, `task`, the benchmark's own columns, then one column per model · mode |
| `results/<bench>/runs.csv` | the same header as the other benchmarks'; `build.py --add` appends the rest |

`--add` and `digest.py` find a trial's adapter from its task's `task.toml` (`[metadata] simulator`).
