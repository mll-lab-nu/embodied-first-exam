# KinDER results

What coding agents achieve on the 6 selected KinDER Dynamic3D tasks (5 scored + the `dynamo` fixture), in both
modes, and (rows 7–30) a one-off screening of every other KinDER family for hard tasks. [`runs.csv`](runs.csv) keeps one line per trial; the tasks and what each mode gives:
[`docs/benchmarks/kinder.md`](../../docs/benchmarks/kinder.md).

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
  --job-name kinder-limited-tossing-codex-gpt6luna-medium-60min-reset50-depth --ak reasoning_effort=medium'
sg docker -c 'RCB_MODEL=openrouter/openai/gpt-6-luna scripts/run_deepseek_openrouter.sh tasks/kinder-tossing-i00 \
  --job-name kinder-full-tossing-codex-gpt6luna-medium-60min --ak reasoning_effort=medium'
python3 scripts/results/build.py --add jobs/kinder-limited-tossing-codex-gpt6luna-medium-60min-reset50-depth
```

## Results

A cell is the latest standard-config run: ✅ or ❌ (KinDER's own goal check, no partial credit) and the model cost.
Empty: not run yet. Limited mode is the real robot's view: the MimicLabs lab scene, the base and wrist cameras only
(wrist depth), no room camera. The full runs had the earlier white floor; the lab changes only their images. `dynamo` is the pipeline check, like HumanoidBench's `sit_simple`.
Screening rows (09-29): one run per mode, not counted in the pass rates; an empty limited cell means the task has no
limited twin (the 2D tasks: a map of the scene would be their only sensor).

| # | task | upstream env | role | GPT-6 Luna · limited | GPT-6 Luna · full |
|---|---|---|---|---|---|
| 1 | dynamo | Dynamo3D-o3 | fixture | ✅ · $0.02 | ✅ · $0.01 |
| 2 | tossing | Tossing3D-o1 | scored | ❌ · $0.51 | ✅ · $0.30 |
| 3 | balance-beam | BalanceBeam3D-o3 | scored | ✅ · $0.41 | ✅ · $0.03 |
| 4 | sweep-into-drawer | SweepIntoDrawer3D-o5 | scored | ✅ · $0.33 | ❌ · $0.35 |
| 5 | scoop-pour | ScoopPour3D-o30 | scored | ❌ · $0.61 | ❌ · $0.31 |
| 6 | shelf | Shelf3D-o2 | scored | ❌ · $0.28 | ✅ · $0.16 |
| 7 | constrained-cupboard | ConstrainedCupboard3D-o6 | screening | ❌ · $0.39 | ✅ · $0.31 |
| 8 | rearrange | Rearrange3D-o2 (drink left, can right) | screening | ✅ · $0.31 | ✅ · $0.02 |
| 9 | sweep-simple | SweepSimple3D-o10 (island, left) | screening | ❌ · $0.38 | ❌ · $0.34 |
| 10 | sort-blocks | SortClutteredBlocks3D-o4 (bins) | screening | ❌ · $0.42 | ✅ · $0.20 |
| 11 | pick-place | PickPlace3D-o1 | screening | ✅ · $0.03 | ✅ · $0.02 |
| 12 | franka-pick-place | FrankaPickPlace3D-o1 | screening | ✅ · $0.07 | ✅ · $0.01 |
| 13 | base-motion-3d | BaseMotion3D | screening | ✅ · $0.05 | ✅ · $0.00 |
| 14 | obstruction-3d | Obstruction3D-o4 | screening | ❌ · $0.32 | ✅ · $0.06 |
| 15 | table-3d | Table3D-o3 | screening | ✅ · $0.10 | ✅ · $0.03 |
| 16 | transport-3d | Transport3D-o2 | screening | ✅ · $0.36 | ✅ · $0.09 |
| 17 | packing-3d | Packing3D-p3 | screening | ❌ · $0.65 | ✅ · $0.05 |
| 18 | kinematic-shelf-3d | KinematicShelf3D-o3 | screening | ✅ · $0.35 | ✅ · $0.07 |
| 19 | cylinder-shelf-3d | KinematicCylinderShelf3D-o3 | screening | ✅ · $0.45 | ✅ · $0.09 |
| 20 | prpl-lab-3d | PrplLab3D-o2 | screening | ✅ · $0.35 | ✅ · $0.04 |
| 21 | dyn-obstruction-2d | DynObstruction2D-o3 | screening | | ✅ · $0.03 |
| 22 | dyn-push-pull-hook-2d | DynPushPullHook2D-o5 | screening | | ✅ · $0.22 |
| 23 | dyn-push-t-2d | DynPushT2D-t1 | screening | | ✅ · $0.05 |
| 24 | dyn-scoop-pour-2d | DynScoopPour2D-o10 | screening | | ✅ · $0.09 |
| 25 | motion-2d | Motion2D-p5 | screening | | ✅ · $0.01 |
| 26 | stick-button-2d | StickButton2D-b10 | screening | | ✅ · $0.02 |
| 27 | obstruction-2d | Obstruction2D-o4 | screening | | ✅ · $0.06 |
| 28 | cluttered-retrieval-2d | ClutteredRetrieval2D-o10 | screening | | ✅ · $0.08 |
| 29 | cluttered-storage-2d | ClutteredStorage2D-b7 | screening | | ✅ · $0.07 |
| 30 | push-pull-hook-2d | PushPullHook2D | screening | | ✅ · $0.05 |

## Earlier setup

09-28, limited with a white floor, the room camera and no depth: 0/5 scored (dynamo passed). The agents found things
through the room camera; grasping took ~20 min where they did, and heights were guessed wrong without depth. Rows
retired from `runs.csv`; the jobs end in `-reset50-roomcam`. Per-task comparisons: `analysis/<task>.md`, "和旧版比".
