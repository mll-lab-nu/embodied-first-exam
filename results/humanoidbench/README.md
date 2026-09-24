# HumanoidBench results

What coding agents score on the 24 selected HumanoidBench tasks (23 scored + the `sit_simple` fixture), in both
modes. [`runs.csv`](runs.csv) keeps one line per trial, whatever the model or config; the table below shows the
standard config only.

## Standard config

| mode | the agent gets | resets | budget |
|---|---|---|---|
| limited | head cameras, joint angles and velocities, IMU, `room_camera`; no reward | 50 | 60 min |
| full | the simulator in its own process, full physical state; no reward; submits one trajectory | unlimited | 60 min |

Codex through OpenRouter (`harbor_agents/codex_openrouter.py`, web search off), reasoning effort `medium`. After a
run, `--add` appends its line to `runs.csv` (every column but the note measured) and rebuilds the pages
(`jobs/results/humanoidbench/index.html`, not in git: an overview, one page per task, one per run):

```bash
sg docker -c 'RCB_RESET_BUDGET=50 RCB_OBS_IMU=1 RCB_OBS_ROOM_CAMERA=1 RCB_MODEL=openrouter/openai/gpt-6-luna \
  scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00-limited \
  --job-name hb-limited-walk-codex-gpt6luna-medium-60min-reset50-imu-roomcam --ak reasoning_effort=medium'
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00 \
  --job-name hb-full-walk-codex-gpt6luna-medium-60min --ak reasoning_effort=medium'
python3 scripts/results/build.py --add jobs/hb-limited-walk-codex-gpt6luna-medium-60min-reset50-imu-roomcam
```

The analysis on a task page is `<trial>/report/notes.md`, written after reading the run (a phase table at its top
colours the limited timeline; see `scripts/results/collect.py`).

## Results

A cell is ✅ or ❌ with the graded return (limited: the last episode; full: the submitted trajectory, replayed) and
the model cost. Empty: not run yet. "All-zero" is what the all-zero action scores on the same instance.

| # | task | robot | class | bar | all-zero | GPT-6 Luna · limited | GPT-6 Luna · full |
|---|---|---|---|---|---|---|---|
| 1 | sit_simple | h1 | fixture | 750 | 637.6 | ✅ 750.6 · $0.08 | ✅ 977.8 · $0.02 |
| 2 | walk | h1 | C1 | 700 | 6.6 | ❌ 7.6 · $0.13 | ❌ 149.6 · $0.14 |
| 3 | hurdle | h1 | C2 | 700 | 17.9 | ❌ 12.4 · $0.16 | ❌ 12.6 · $0.46 |
| 4 | balance_simple | h1 | C3 | 800 | 37.1 | ❌ 64.2 · $0.07 | ❌ 130.8 · $0.33 |
| 5 | door | h1 | C4 | 600 | 30.9 | ❌ 7.8 · $0.36 | ❌ 182.2 · $0.19 |
| 6 | powerlift | h1hand | C5 | 800 | 20.4 | ❌ 47.6 · $0.16 | ❌ 333.4 · $0.19 |
| 7 | push | h1 | C6 | 700 | −253.7 | ❌ −237.5 · $0.43 | ✅ 948.1 · $0.03 |
| 8 | cube | h1hand | C7 | 370 | 5.0 | ❌ 15.2 · $0.22 | ❌ 247.6 · $0.35 |
| 9 | package | h1 | C8 | 1500 | −2192.0 | ❌ −1838.9 · $0.10 | ❌ 359.7 · $0.22 |
| 10 | bookshelf_simple | h1hand | C9 | 2000 | 30.5 | ❌ 257.1 · $0.35 | ❌ 740.0 · $0.41 |
| 11 | stair | h1 | C2 | 700 | 8.6 | | |
| 12 | balance_hard | h1 | C3 | 800 | 29.0 | | |
| 13 | maze | h1 | C4 | 1200 | 120.6 | | |
| 14 | highbar_simple | h1 | C5 | 750 | 0.1 | | |
| 15 | basketball | h1 | C5 | 1200 | 10.8 | | |
| 16 | reach | h1 | C8 | 12000 | 275.2 | | |
| 17 | sit_hard | h1 | C8 | 750 | 13.6 | | |
| 18 | truck | h1 | C9 | 3000 | 544.4 | | |
| 19 | window | h1hand | C6 | 650 | 1.6 | | |
| 20 | spoon | h1hand | C6 | 650 | 7.5 | | |
| 21 | insert_normal | h1hand | C7 | 350 | 2.5 | | |
| 22 | room | h1hand | C8 | 400 | 8.8 | | |
| 23 | cabinet | h1hand | C9 | 2500 | 10.4 | | |
| 24 | kitchen | h1hand | C9 | 4 | 0.0 | | |

Classes (`scripts/humanoidbench/subset.toml`): C1 flat gait · C2 constrained gait · C3 stabilisation · C4 navigation ·
C5 whole-body power · C6 bimanual manipulation · C7 in-hand precision · C8 mobile manipulation · C9 long-horizon.
h1 has 19 actuators, h1hand 61 (hands included).

Order: rows 1–10 are the first round, one task per class plus the fixture, run in both modes; the rest by robot (h1
first) and by class.
