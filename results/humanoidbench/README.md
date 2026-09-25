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

The analysis on a task page is `<trial>/report/notes.md`, written after reading the run:
`python3 scripts/results/digest.py jobs/<job>` puts it on one page, and
[`scripts/results/NOTES_GUIDE.md`](../../scripts/results/NOTES_GUIDE.md) says what goes in it.

## Results

A cell is the latest standard-config run: ✅ or ❌ with the graded return (limited: the last episode; full: the
submitted trajectory, replayed) and the model cost. Empty: not run yet. "All-zero" is what the all-zero action
scores on the same instance.

| # | task | robot | class | bar | all-zero | GPT-6 Luna · limited | GPT-6 Luna · full | GPT-6 Sol · limited | GPT-6 Sol · full |
|---|---|---|---|---|---|---|---|---|---|
| 1 | sit_simple | h1 | fixture | 750 | 637.6 | ✅ 750.8 · $0.03 | ✅ 905.1 · $0.39 |  |  |
| 2 | walk | h1 | C1 | 700 | 6.6 | ❌ 38.5 · $0.08 | ❌ 159.8 · $0.61 | ❌ 19.5 · $0.28 | ✅ 862.3 · $7.79 |
| 3 | hurdle | h1 | C2 | 700 | 17.9 | ❌ 14.6 · $0.26 | ❌ 132.0 · $0.68 |  |  |
| 4 | balance_simple | h1 | C3 | 800 | 37.1 | ❌ 65.5 · $0.06 | ❌ 108.4 · $0.32 |  |  |
| 5 | door | h1 | C4 | 600 | 30.9 | ❌ 23.5 · $0.19 | ❌ 223.3 · $0.48 | ❌ 110.1 · $3.18 | ❌ 416.0 · $5.32 |
| 6 | powerlift | h1hand | C5 | 800 | 20.4 | ❌ 156.6 · $0.26 | ❌ 327.9 · $0.46 |  |  |
| 7 | push | h1 | C6 | 700 | −253.7 | ❌ −213.9 · $0.60 | ✅ 986.8 · $0.53 |  |  |
| 8 | cube | h1hand | C7 | 370 | 5.0 | ❌ 29.8 · $0.34 | ❌ 224.2 · $0.32 | ❌ 5.5 · $0.31 | ❌ 314.7 · $13.37 |
| 9 | package | h1 | C8 | 1500 | −2192.0 | ❌ −2068.6 · $0.18 | ❌ −767.4 · $0.49 | ❌ −2172.9 · $0.80 | ❌ 701.8 · $4.65 |
| 10 | bookshelf_simple | h1hand | C9 | 2000 | 30.5 | ❌ 6.9 · $0.49 | ❌ 798.2 · $0.42 | ❌ 567.2 · $6.72 | ❌ 717.6 · $6.35 |
| 11 | stair | h1 | C2 | 700 | 8.6 | ❌ 33.0 · $0.18 | ❌ 162.2 · $0.57 |  |  |
| 12 | balance_hard | h1 | C3 | 800 | 29.0 | ❌ 40.6 · $0.11 | ❌ 45.5 · $0.49 |  |  |
| 13 | maze | h1 | C4 | 1200 | 120.6 | ❌ 142.5 · $0.34 | ❌ 386.7 · $0.76 |  |  |
| 14 | highbar_simple | h1 | C5 | 750 | 0.1 | ❌ 63.8 · $0.03 | ❌ 193.8 · $0.34 |  |  |
| 15 | basketball | h1 | C5 | 1200 | 10.8 | ❌ 19.3 · $0.33 | ❌ 1071.0 · $0.36 |  |  |
| 16 | reach | h1 | C8 | 12000 | 275.2 | ❌ 417.4 · $0.10 | ✅ 19127.7 · $0.09 |  |  |
| 17 | sit_hard | h1 | C8 | 750 | 13.6 | ❌ 1.8 · $0.22 | ❌ 618.1 · $0.50 |  |  |
| 18 | truck | h1 | C9 | 3000 | 544.4 | ❌ 103.1 · $0.20 | ❌ 1418.1 · $0.46 |  |  |
| 19 | window | h1hand | C6 | 650 | 1.6 | ❌ 4.8 · $0.57 | ❌ 513.5 · $0.21 |  |  |
| 20 | spoon | h1hand | C6 | 650 | 7.5 | ❌ 196.1 · $0.51 | ❌ 351.2 · $0.48 |  |  |
| 21 | insert_normal | h1hand | C7 | 350 | 2.5 | ❌ 101.6 · $0.58 | ❌ 250.2 · $0.42 |  |  |
| 22 | room | h1hand | C8 | 400 | 8.8 | ❌ 21.7 · $0.07 | ❌ 181.9 · $0.36 |  |  |
| 23 | cabinet | h1hand | C9 | 2500 | 10.4 | ❌ 60.1 · $0.58 | ❌ 591.6 · $0.43 |  |  |
| 24 | kitchen | h1hand | C9 | 4 | 0.0 | ❌ 0.0 · $0.27 | ❌ 2.0 · $0.58 |  |  |

Classes (`scripts/humanoidbench/subset.toml`): C1 flat gait · C2 constrained gait · C3 stabilisation · C4 navigation ·
C5 whole-body power · C6 bimanual manipulation · C7 in-hand precision · C8 mobile manipulation · C9 long-horizon.
h1 has 19 actuators, h1hand 61 (hands included).

Order: rows 1–10 are the first round, one task per class plus the fixture, run in both modes, and again after the
task text changed in 06b0ab3 (`runs.csv` keeps both); the rest by robot (h1 first) and by class. GPT-6 Sol ran
five of the tasks GPT-6 Luna failed in both modes, one per class: walk, door, cube, package, bookshelf_simple.
