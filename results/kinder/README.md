# KinDER results

What coding agents achieve on the 11 selected KinDER tasks (10 scored + the `dynamo` fixture), in both modes.
[`runs.csv`](runs.csv) keeps one line per trial of the current version (09-29 night: `spec()` gives the gripper's
grasp point, the PyBullet robot reports a refused move as `blocked`): the standard config below, and a control with
no reset. The tasks and what each mode gives: [`docs/benchmarks/kinder.md`](../../docs/benchmarks/kinder.md);
earlier versions: [Earlier versions](#earlier-versions).

## Standard config

| mode | the agent gets | resets | budget |
|---|---|---|---|
| limited | the robot's own cameras: base RGB, wrist RGB-D; odometry, arm joints, gripper; no goal check | 50 | 60 min |
| full | the simulator in its own process, full state and the goal check; submits one trajectory | unlimited | 60 min |

Codex through OpenRouter (web search off), reasoning effort `medium`. After a run, `--add` appends its line to
`runs.csv` and rebuilds the pages (`jobs/results/kinder/index.html`, not in git):

```bash
sg docker -c 'RCB_RESET_BUDGET=50 RCB_OBS_DEPTH=1 RCB_MODEL=openrouter/openai/gpt-6-luna \
  scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00-limited \
  --job-name kinder-limited-tossing-codex-gpt6luna-medium-60min-reset50-depth-ee --ak reasoning_effort=medium'
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00 \
  --job-name kinder-full-tossing-codex-gpt6luna-medium-60min --ak reasoning_effort=medium'
python3 scripts/results/build.py --add jobs/kinder-limited-tossing-codex-gpt6luna-medium-60min-reset50-depth-ee
```

Why 50 resets: KinDER's episode (1000 steps, 100 s of robot time) is the time to carry the task out with the whole state
known; finding things and calibrating get earlier episodes, and the graded one is the execution. The control sets
`RCB_RESET_BUDGET=0` (jobs end in `-reset0-depth-ee`): exploring and executing share the one episode.

## Results

A cell is the latest standard-config run: ✅ or ❌ (KinDER's own goal check, no partial credit) and the model cost.
Limited mode is the real robot's view: the MimicLabs lab scene, the base and wrist cameras only (wrist depth), no
room camera, 50 resets. The first six full runs had the earlier white floor, which changes only their images.
Rows 7–11 were kept from a screening of every KinDER family (09-29) because GPT-6 Luna failed them in limited mode.

| # | task | upstream env | role | GPT-6.1 Sol · limited | GPT-6.1 Sol · full | GPT-6 Luna · limited | GPT-6 Luna · full |
|---|---|---|---|---|---|---|---|
| 1 | dynamo | Dynamo3D-o3 | fixture | ✅ · $0.21 | ✅ · $0.10 | ✅ · $0.05 | ✅ · $0.01 |
| 2 | tossing | Tossing3D-o1 | scored | ✅ · $0.47 | ✅ · $0.30 | ❌ · $0.61 | ✅ · $0.30 |
| 3 | balance-beam | BalanceBeam3D-o3 | scored | ✅ · $0.21 | ✅ · $0.22 | ❌ · $0.59 | ✅ · $0.03 |
| 4 | sweep-into-drawer | SweepIntoDrawer3D-o5 | scored | ✅ · $0.53 | ✅ · $0.70 | ❌ · $0.66 | ❌ · $0.35 |
| 5 | scoop-pour | ScoopPour3D-o30 | scored | ✅ · $0.77 | ✅ · $2.27 | ❌ · $0.69 | ❌ · $0.31 |
| 6 | shelf | Shelf3D-o2 | scored | ✅ · $0.62 | ✅ · $0.32 | ❌ · $0.53 | ✅ · $0.16 |
| 7 | constrained-cupboard | ConstrainedCupboard3D-o6 | scored | ✅ · $1.86 | ✅ · $0.47 | ❌ · $0.68 | ✅ · $0.31 |
| 8 | sweep-simple | SweepSimple3D-o10 (island, left) | scored | ✅ · $0.80 | ✅ · $1.35 | ✅ · $0.59 | ❌ · $0.34 |
| 9 | sort-blocks | SortClutteredBlocks3D-o4 (bins) | scored | ✅ · $0.48 | ✅ · $0.38 | ✅ · $0.41 | ✅ · $0.20 |
| 10 | obstruction-3d | Obstruction3D-o4 (PyBullet) | scored | ✅ · $0.27 | ✅ · $0.22 | ❌ · $0.70 | ✅ · $0.06 |
| 11 | packing-3d | Packing3D-p3 (PyBullet) | scored | ✅ · $0.25 | ✅ · $0.27 | ✅ · $0.76 | ✅ · $0.05 |

Scored tasks: GPT-6.1 Sol (the main result, one attempt per task and mode, 2026-09-30 and 10-01) limited 10/10,
full 10/10; GPT-6 Luna limited 3/10 (sweep-simple, sort-blocks, packing-3d), full 7/10. The control, the same limited twins with
no reset: 0/10, the fixture included; the nine MuJoCo runs used up their one episode's 1000 steps in 6–46 min.

## Earlier versions

Their rows are out of `runs.csv`; their conclusions are in `analysis/`, under 和旧版比.

- **09-30, the two PyBullet no-reset runs before a `blocked` fix** (2 of 16 and 2 of 27 refused moves came back
  unflagged, fooled by round-off on the base's yaw): obstruction-3d passed, packing-3d failed; both were redone.
  Jobs end in `-reset0-depth-ee-blockedbug`.
- **09-29, 50 resets, before the grasp point and `blocked`**: scored 2/10 (sweep-into-drawer, balance-beam) and the
  fixture. Jobs end in `-reset50-depth`.
- **09-28, white floor, room camera, no depth**: 0/5 on the first six (dynamo passed). Jobs end in `-reset50-roomcam`.
- **The screening's other 19 families** (09-29, one run per mode): `docs/benchmarks/kinder.md`, the ⬜ rows.
