# HumanoidBench results

What coding agents score on the 24 selected HumanoidBench tasks (23 scored + the `sit_simple` fixture).
[`runs.csv`](runs.csv) keeps one line per trial, whatever the model or config; the table below shows the standard
config only, one row per task, in the order we run them. Limited mode comes first; full mode after it.

## Standard config

| mode | the agent gets | resets | budget |
|---|---|---|---|
| limited | head cameras, joint angles and velocities, IMU, `room_camera`; no reward | 30 | 60 min |
| full (later) | the simulator in its own container, full physical state; no reward | unlimited | 60 min |

Codex through OpenRouter (`harbor_agents/codex_openrouter.py`, web search off), then the report:

```bash
sg docker -c 'RCB_RESET_BUDGET=30 RCB_OBS_IMU=1 RCB_OBS_ROOM_CAMERA=1 RCB_MODEL=openrouter/openai/gpt-6-luna \
  scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00-limited --job-name hbl-limited-walk-codex-gpt6luna-60min-reset30-imu-roomcam'
python3 scripts/limited_report/report.py jobs/hbl-limited-walk-codex-gpt6luna-60min-reset30-imu-roomcam
```

A cell is ✅ or ❌ with the graded episode's return and the model cost; with several runs, passes/runs and the best
return. Empty: not run yet. "All-zero" is what the all-zero action scores on the same instance.

## Limited mode

| # | task | robot | class | bar | all-zero | limited task | GPT-6 Luna | GPT-6 Sol |
|---|---|---|---|---|---|---|---|---|
| 1 | sit_simple | h1 | fixture | 750 | 637.6 | ready | ✅ 750.6 · $0.02 | ✅ 750.2 · $0.39 |
| 2 | balance_simple | h1 | C3 | 800 | 37.1 | ready | | |
| 3 | walk | h1 | C1 | 700 | 6.6 | ready | | |
| 4 | stair | h1 | C2 | 700 | 8.6 | ready | | |
| 5 | hurdle | h1 | C2 | 700 | 17.9 | ready | | |
| 6 | balance_hard | h1 | C3 | 800 | 29.0 | to build | | |
| 7 | door | h1 | C4 | 600 | 30.9 | to build | | |
| 8 | maze | h1 | C4 | 1200 | 120.6 | to build | | |
| 9 | highbar_simple | h1 | C5 | 750 | 0.1 | to build | | |
| 10 | basketball | h1 | C5 | 1200 | 10.8 | to build | | |
| 11 | push | h1 | C6 | 700 | −253.7 | to build | | |
| 12 | reach | h1 | C8 | 12000 | 275.2 | to build | | |
| 13 | sit_hard | h1 | C8 | 750 | 13.6 | to build | | |
| 14 | package | h1 | C8 | 1500 | −2192.0 | to build | | |
| 15 | truck | h1 | C9 | 3000 | 544.4 | to build | | |
| 16 | powerlift | h1hand | C5 | 800 | 20.4 | to build | | |
| 17 | window | h1hand | C6 | 650 | 1.6 | to build | | |
| 18 | spoon | h1hand | C6 | 650 | 7.5 | to build | | |
| 19 | insert_normal | h1hand | C7 | 350 | 2.5 | to build | | |
| 20 | cube | h1hand | C7 | 370 | 5.0 | to build | | |
| 21 | room | h1hand | C8 | 400 | 8.8 | to build | | |
| 22 | cabinet | h1hand | C9 | 2500 | 10.4 | to build | | |
| 23 | kitchen | h1hand | C9 | 4 | 0.0 | to build | | |
| 24 | bookshelf_simple | h1hand | C9 | 2000 | 30.5 | to build | | |

Classes (`scripts/humanoidbench/subset.toml`): C1 flat gait · C2 constrained gait · C3 stabilisation · C4 navigation ·
C5 whole-body power · C6 bimanual manipulation · C7 in-hand precision · C8 mobile manipulation · C9 long-horizon.
h1 has 19 actuators, h1hand 61 (hands included).

Order: the five limited tasks that exist, then the rest by robot (h1 first, as built) and by class.

## Full mode
Not run yet in the standard config; its table goes here when we start.

## Earlier runs, not in the standard config (details in `runs.csv`)
- walk, limited, 20 resets: Luna ❌ 33.9 (no IMU or `room_camera`); Sol ❌ 7.2.
- walk / stair / hurdle / balance_simple, limited, 3 resets, Luna: ❌ 12.0 / 6.4 / 14.9 / 43.8.
- sit_simple, limited, 30 min, 0–3 resets: DeepSeek V4.1 Flash ❌ twice; Claude Code + Opus 5.5 ✅, from its memory of
  HumanoidBench.
- Before the reward was scrubbed from the image, mini-swe-agent + claude-sonnet-5 passed full-mode walk (784.54);
  not comparable.
