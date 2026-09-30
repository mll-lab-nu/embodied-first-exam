# HumanoidBench results

What coding agents score on the 24 selected HumanoidBench tasks (23 scored + the `sit_simple` fixture), in both
modes. [`runs.csv`](runs.csv) keeps one line per trial on the current task text, text 7 (ef883ec; job names end in
`-text7`; later commits changed no instruction and no score), all in the standard config below. The earlier texts
are summed up under [Earlier versions](#earlier-versions).

## Standard config

| mode | the agent gets | resets | budget |
|---|---|---|---|
| limited | head cameras, joint angles and velocities, IMU, `room_camera`; no reward | 50 | 60 min |
| full | the simulator in its own process, full physical state; no reward; submits one trajectory | unlimited | 60 min |

Codex through OpenRouter (`harbor_agents/codex_openrouter.py`, web search off), reasoning effort `medium`. After a
run, `--add` appends its line to `runs.csv` (every column but the note measured) and rebuilds the pages
(`jobs/results/humanoidbench/index.html`, not in git: an overview, one page per task, one per run):

```bash
RCB_RESET_BUDGET=50 RCB_OBS_IMU=1 RCB_OBS_ROOM_CAMERA=1 RCB_MODEL=openrouter/openai/gpt-6-luna \
  scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00-limited \
  --job-name hb-limited-walk-codex-gpt6luna-medium-60min-reset50-imu-roomcam-text7 --ak reasoning_effort=medium
RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00 \
  --job-name hb-full-walk-codex-gpt6luna-medium-60min-text7 --ak reasoning_effort=medium
python3 scripts/results/build.py --add jobs/hb-limited-walk-codex-gpt6luna-medium-60min-reset50-imu-roomcam-text7
```

The limited knobs can also come from a profile instead of the shell: `-c scripts/humanoidbench/configs/limited.yaml`
(the standard config above) or `limited-depth.yaml` (plus depth from the head cameras).

The analysis on a task page is `<trial>/report/notes.md`, written after reading the run:
`python3 scripts/results/digest.py jobs/<job>` puts it on one page, and
[`scripts/results/NOTES_GUIDE.md`](../../scripts/results/NOTES_GUIDE.md) says what goes in it.

## Results

A cell is the latest standard-config run: ✅ or ❌ with the graded return (limited: the last episode; full: the
submitted trajectory, replayed) and the model cost. Empty: not run yet. "All-zero" is what the all-zero action
scores on the same instance. Run ids, as on the team site and the Hugging Face dataset
(`<harness>-<model>-<effort>`): GPT-6 Luna `codex-gpt6_luna-medium`, GPT-6 Sol `codex-gpt6_sol-medium`, Claude Opus 5.5
`claude_code-claude_opus5_5-medium`.

| # | task | robot | class | bar | all-zero | GPT-6 Luna · limited | GPT-6 Luna · full | GPT-6 Sol · limited | GPT-6 Sol · full | Claude Opus 5.5 · limited | Claude Opus 5.5 · full |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sit_simple | h1 | fixture | 750 | 637.6 | ✅ 750.6 · $0.02 | ✅ 980.7 · $0.41 |  |  |  |  |
| 2 | walk | h1 | C1 | 700 | 6.6 | ❌ 11.3 · $0.12 | ❌ 128.5 · $0.43 | ❌ 52.7 · $1.26 | ❌ 546.6 · $4.74 | ❌ 369.2 · $2.40 | ✅ 834.8 · $0.47 |
| 3 | hurdle | h1 | C2 | 700 | 17.9 | ❌ 22.4 · $0.05 | ❌ 50.2 · $0.37 |  |  |  |  |
| 4 | balance_simple | h1 | C3 | 800 | 37.1 | ❌ 51.9 · $0.09 | ❌ 146.3 · $0.33 |  |  |  |  |
| 5 | door | h1 | C4 | 600 | 30.9 | ❌ 9.1 · $0.12 | ❌ 199.9 · $0.44 | ❌ 164.2 · $2.60 |  | ❌ 132.8 · $2.40 | ✅ 676.0 · $2.71 |
| 6 | powerlift | h1hand | C5 | 800 | 20.4 | ❌ 49.2 · $0.14 | ❌ 296.9 · $0.40 |  |  |  |  |
| 7 | push | h1 | C6 | 700 | −253.7 | ❌ −224.1 · $0.42 | ✅ 997.8 · $0.42 | ✅ 969.3 · $1.41 |  | ✅ 913.2 · $2.26 | ✅ 967.0 · $0.63 |
| 8 | cube | h1hand | C7 | 370 | 5.0 | ❌ 29.3 · $0.19 | ❌ 325.1 · $0.46 | ❌ 96.1 · $0.67 |  | ❌ 87.9 · $0.88 | ❌ 247.5 · $0.96 |
| 9 | package | h1 | C8 | 1500 | −2192.0 | ❌ −1916.1 · $0.13 | ❌ 805.6 · $0.34 |  |  |  |  |
| 10 | bookshelf_simple | h1hand | C9 | 2000 | 30.5 | ❌ 641.2 · $0.35 | ❌ 793.2 · $0.41 |  |  |  |  |
| 11 | stair | h1 | C2 | 700 | 8.6 | ❌ 17.2 · $0.07 | ❌ 69.7 · $0.34 |  |  |  |  |
| 12 | balance_hard | h1 | C3 | 800 | 29.0 | ❌ 45.4 · $0.11 | ❌ 48.0 · $0.38 |  |  |  |  |
| 13 | maze | h1 | C4 | 1200 | 120.6 | ❌ 131.0 · $0.25 | ❌ 393.1 · $0.45 |  |  |  |  |
| 14 | highbar_simple | h1 | C5 | 750 | 0.1 | ❌ 81.1 · $0.12 | ❌ 126.3 · $0.33 |  |  |  |  |
| 15 | basketball | h1 | C5 | 1200 | 10.8 | ❌ 13.0 · $0.06 | ❌ 1091.8 · $0.42 |  |  |  |  |
| 16 | reach | h1 | C8 | 12000 | 275.2 | ❌ 875.3 · $0.08 | ✅ 19184.1 · $0.37 |  |  |  |  |
| 17 | sit_hard | h1 | C8 | 750 | 13.6 | ❌ 13.0 · $0.35 | ✅ 946.3 · $0.23 | ❌ 383.1 · $0.62 | ✅ 963.9 · $4.82 | ✅ 750.2 · $0.96 | ✅ 951.0 · $0.59 |
| 18 | truck | h1 | C9 | 3000 | 544.4 | ❌ 598.0 · $0.15 | ❌ 1332.2 · $0.38 |  |  |  |  |
| 19 | window | h1hand | C6 | 650 | 1.6 | ❌ 303.9 · $0.25 | ❌ 420.4 · $0.51 |  |  |  |  |
| 20 | spoon | h1hand | C6 | 650 | 7.5 | ❌ 341.0 · $0.37 | ❌ 406.6 · $0.41 |  |  |  |  |
| 21 | insert_normal | h1hand | C7 | 350 | 2.5 | ❌ 95.6 · $0.47 | ❌ 194.9 · $0.48 |  |  |  |  |
| 22 | room | h1hand | C8 | 400 | 8.8 | ❌ 7.8 · $0.08 | ❌ 195.3 · $0.26 |  |  |  |  |
| 23 | cabinet | h1hand | C9 | 2500 | 10.4 | ❌ 547.1 · $0.62 | ❌ 467.3 · $0.33 |  |  |  |  |
| 24 | kitchen | h1hand | C9 | 4 | 0.0 | ❌ 0.0 · $0.61 | ❌ 0.0 · $0.40 |  |  |  |  |

Classes (`scripts/humanoidbench/subset.toml`): C1 flat gait · C2 constrained gait · C3 stabilisation · C4 navigation ·
C5 whole-body power · C6 bimanual manipulation · C7 in-hand precision · C8 mobile manipulation · C9 long-horizon.
h1 has 19 actuators, h1hand 61 (hands included).

Order: rows 1–10 are the first round, one task per class plus the fixture; the rest are ordered by robot (h1 first)
and by class. GPT-6 Luna ran all 24. GPT-6 Sol and Claude Opus 5.5 ran five, one per class, in both modes: walk,
door, push, cube, sit_hard (Luna had passed push and sit_hard on earlier texts, not the other three). Opus runs
through Claude Code (`harbor_agents/claude_code_openrouter.py`, 2.1.283, effort medium). Sol's full runs on door,
push and cube were not made: the OpenRouter credit ran out.

## Earlier versions

The runs on texts 1–6 were taken out of these results; their rows are in `runs.csv` at 884d59e (texts 1–2) and
c9449ce (texts 3–6). What they showed, and what the next text changed:

| text | runs | passed | what it showed → the next text |
|---|---|---|---|
| 1 · 070fdcf | Luna, rows 1–10, both modes: 20, $4.39 | Luna limited 1 (sit_simple), full 2 (sit_simple, push) | full beat limited on all ten; the instructions differed from upstream's scoring in places and left out facts (speed targets, head height); five full runs stopped unsolved after 23–46 min → 06b0ab3 checks every text against upstream and says not to stop early |
| 2 · 06b0ab3 | Luna, all 24, both modes; Sol, five tasks, both modes: 58, $66.07 | Luna limited 1 (sit_simple), full 3 (sit_simple, push, reach); Sol full 1 (walk, 862.3), limited 0 | "800 out of 1000 steps" was read as surviving 800 steps; every limited run spent resets finding the action scale, and several read the IMU, a joint or a camera backwards; the 0.1.5 image still gave the reward away through its helpers and comments → e95d382 states the pass mark as a total of rewards, puts the robot's facts in `spec()`, ships image 0.1.6 |
| 3 · e95d382 | Luna, rows 1–10, both modes: 20, $6.78 | Luna limited 2 (sit_simple, push), full 2 (sit_simple, push) | `spec()` listed a `wall_clock_s` beside the service's own clock, and agents misjudged the time left → 8e09011 drops it; the service keeps every image it returns |
| 4 · 8e09011 | Luna, rows 11–24, both modes; Sol, five tasks, both modes; Opus, the same five, limited: 43, $97.48 | Luna full 2 (reach, sit_hard); Sol full 1 (cube); limited 0 | an episode lying or sitting short of the bar ran on to step 1000, and runs took such a controller for a good one; the IMU's fore-aft and the images' left-right were often read backwards; the service clock started 52–96 s before the agent's first request → text 5 says an episode still running may have fallen, `spec()` gives each reading's sign and each camera's right axis, the clock starts at the first request, the head cameras' near plane is 1 cm, maze names its start |
| 5 · e897737 (`-text5`) | Luna, all 24, limited, plus 16 with 100 resets and 10 with head depth: 50, $18.32 | limited 2 (sit_simple, sit_hard), and push with 100 resets | the IMU was mostly read the right way round; more resets or depth changed little (with depth on, the service then rendered some room-camera images and depth maps wrong; fixed 2026-09-29); cube's faces were 10–15 px at 256×256 → text 6 renders cube's cameras at 512×512 |
| 6 · e897737 (`-text6`) | Luna, cube, limited: 1, $0.24 | none | the letters on the faces became readable, but the robot still fell; Sol's full cube run on text 4 stood by keeping its centre of mass over the feet, which a limited run could not compute → text 7 (ef883ec) adds each joint's position, each link's mass and centre of mass and the feet's boxes to `spec()` |
