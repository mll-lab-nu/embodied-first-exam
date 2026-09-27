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

The limited knobs can also come from a profile instead of the shell: `-c scripts/humanoidbench/configs/limited.yaml`
(the standard config above) or `limited-depth.yaml` (plus depth from the head cameras).

The analysis on a task page is `<trial>/report/notes.md`, written after reading the run:
`python3 scripts/results/digest.py jobs/<job>` puts it on one page, and
[`scripts/results/NOTES_GUIDE.md`](../../scripts/results/NOTES_GUIDE.md) says what goes in it.

## Results

A cell is the latest standard-config run: ✅ or ❌ with the graded return (limited: the last episode; full: the
submitted trajectory, replayed) and the model cost. Empty: not run yet. "All-zero" is what the all-zero action
scores on the same instance.

| # | task | robot | class | bar | all-zero | GPT-6 Luna · limited | GPT-6 Luna · full | GPT-6 Sol · limited | GPT-6 Sol · full | Claude Opus 5.5 · limited |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sit_simple | h1 | fixture | 750 | 637.6 | ✅ 750.1 · $0.02 | ✅ 954.1 · $0.41 |  |  |  |
| 2 | walk | h1 | C1 | 700 | 6.6 | ❌ 14.9 · $0.08 | ❌ 158.0 · $0.37 | ❌ 45.8 · $0.85 | ❌ 603.1 · $15.52 | ❌ 10.4 · $3.45 |
| 3 | hurdle | h1 | C2 | 700 | 17.9 | ❌ 13.0 · $0.33 | ❌ 38.8 · $0.52 |  |  |  |
| 4 | balance_simple | h1 | C3 | 800 | 37.1 | ❌ 78.9 · $0.11 | ❌ 139.2 · $0.29 |  |  |  |
| 5 | door | h1 | C4 | 600 | 30.9 | ❌ 7.0 · $0.56 | ❌ 209.9 · $0.44 | ❌ 131.7 · $6.31 | ❌ 301.2 · $6.70 | ❌ 120.7 · $1.93 |
| 6 | powerlift | h1hand | C5 | 800 | 20.4 | ❌ 10.2 · $0.25 | ❌ 258.5 · $0.48 |  |  |  |
| 7 | push | h1 | C6 | 700 | −253.7 | ❌ −215.5 · $0.23 | ✅ 991.8 · $0.44 |  |  |  |
| 8 | cube | h1hand | C7 | 370 | 5.0 | ❌ 39.1 · $0.24 | ❌ 252.5 · $0.46 | ❌ 91.9 · $0.59 | ✅ 399.6 · $12.73 | ❌ 36.6 · $0.61 |
| 9 | package | h1 | C8 | 1500 | −2192.0 | ❌ −3699.6 · $0.11 | ❌ 875.1 · $0.44 | ❌ −3592.7 · $1.43 | ❌ −337.5 · $9.13 | ❌ −1000.9 · $1.81 |
| 10 | bookshelf_simple | h1hand | C9 | 2000 | 30.5 | ❌ 650.1 · $0.81 | ❌ 806.5 · $0.57 | ❌ 706.3 · $11.80 | ❌ 853.3 · $11.70 | ❌ 709.3 · $0.88 |
| 11 | stair | h1 | C2 | 700 | 8.6 | ❌ 42.9 · $0.11 | ❌ 94.8 · $0.48 |  |  |  |
| 12 | balance_hard | h1 | C3 | 800 | 29.0 | ❌ 49.2 · $0.03 | ❌ 59.6 · $0.54 |  |  |  |
| 13 | maze | h1 | C4 | 1200 | 120.6 | ❌ 123.0 · $0.23 | ❌ 1122.6 · $0.37 |  |  |  |
| 14 | highbar_simple | h1 | C5 | 750 | 0.1 | ❌ 67.0 · $0.19 | ❌ 199.4 · $0.64 |  |  |  |
| 15 | basketball | h1 | C5 | 1200 | 10.8 | ❌ 23.0 · $0.64 | ❌ 1044.0 · $0.09 |  |  |  |
| 16 | reach | h1 | C8 | 12000 | 275.2 | ❌ 1059.3 · $0.15 | ✅ 15672.1 · $0.59 |  |  |  |
| 17 | sit_hard | h1 | C8 | 750 | 13.6 | ✅ 750.8 · $0.38 | ✅ 918.9 · $0.43 |  |  |  |
| 18 | truck | h1 | C9 | 3000 | 544.4 | ❌ 604.9 · $0.08 | ❌ 1406.3 · $0.37 |  |  |  |
| 19 | window | h1hand | C6 | 650 | 1.6 | ❌ 71.4 · $0.54 | ❌ 389.5 · $0.50 |  |  |  |
| 20 | spoon | h1hand | C6 | 650 | 7.5 | ❌ 8.8 · $0.71 | ❌ 362.1 · $0.60 |  |  |  |
| 21 | insert_normal | h1hand | C7 | 350 | 2.5 | ❌ 60.6 · $0.56 | ❌ 152.5 · $0.51 |  |  |  |
| 22 | room | h1hand | C8 | 400 | 8.8 | ❌ 33.9 · $0.08 | ❌ 196.3 · $0.41 |  |  |  |
| 23 | cabinet | h1hand | C9 | 2500 | 10.4 | ❌ 34.8 · $0.47 | ❌ 538.4 · $0.60 |  |  |  |
| 24 | kitchen | h1hand | C9 | 4 | 0.0 | ❌ 0.0 · $0.67 | ❌ 0.0 · $0.53 |  |  |  |

Classes (`scripts/humanoidbench/subset.toml`): C1 flat gait · C2 constrained gait · C3 stabilisation · C4 navigation ·
C5 whole-body power · C6 bimanual manipulation · C7 in-hand precision · C8 mobile manipulation · C9 long-horizon.
h1 has 19 actuators, h1hand 61 (hands included).

Order: rows 1–10 are the first round, one task per class plus the fixture, run in both modes, again after the
task text changed in 06b0ab3, and a third time on e95d382 (limited-mode rules and `spec()`'s robot facts, image
0.1.6); `runs.csv` keeps all three. The rest are ordered by robot (h1 first) and by class. GPT-6 Sol ran five of
the tasks GPT-6 Luna failed in both modes, one per class: walk, door, cube, package, bookshelf_simple. Rows 1–10's
Luna cells are e95d382 runs; every other cell (Luna on rows 11–24, all Sol cells) is on 8e09011, which differs for the
agent only in `spec()` no longer listing `wall_clock_s`. Claude Opus 5.5 ran Sol's five tasks in limited mode only, through Claude Code
(`harbor_agents/claude_code_openrouter.py`, 2.1.283, effort medium), on 8e09011's tasks with the sidecar logging
exact actions (uncommitted when run). Round 7 re-ran GPT-6 Luna in limited mode on every task with the task text
in the working tree (job names end in `-text5`; committed afterwards in e897737, cube there at text 6: the rules say a fallen robot's episode runs on,
`spec()` names the axes and signs, the service clock starts at the agent's first request, the head cameras' near
plane is 1 cm); cube's cell is `-text6`, the same with every camera at 512×512. Its non-standard extras, listed on
the task pages: depth from the head cameras on 10 tasks (`-depth-text5`) and 100 resets on the 16 tasks whose
`-text5` run used its 50 with 20 minutes or more left (`-reset100-...-text5`).
