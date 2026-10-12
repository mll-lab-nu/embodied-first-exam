# fiber_bundling in YAMLab

Port of the old RoboTangle `fiber_bundling` family (cable through a copper ring, strands combed
first) to YAMLab (Isaac Sim 5.1 / Isaac Lab 2.3.2, bimanual YAM). Gym ids:
`FiberBundling-VeryEasy-v0`, `FiberBundling-Easier-v0`.

## Layout of this folder

| path | what |
|---|---|
| `STATUS.md` | state, numbers, re-layout transform, deviations, blockers |
| `yamlab_task/configs/tasks/fiber_bundling.yaml` | task config (thresholds, modes) |
| `yamlab_task/envs/tasks/fiber_bundling_manager_cfg.py` | scene (fixtures, cable articulation, strand contact sensor), terminations |
| `yamlab_task/envs/tasks/fiber_bundling_manager.py` | env: goal evaluation each control step, latched success/failure, gym registration |
| `yamlab_task/envs/tasks/fiber_bundling_goal.py` | pure-numpy goal check (old `terminal_v4_fiber_ring_plane` + `advance_passage`) |
| `tools/build_assets.py` | builds `cable.usda`, `fixtures.usda`, `layout_world.json` per tier from the old STL package |
| `tools/yam_kin.py` | numpy FK/IK of a YAM arm (chain constants from `yam.usd`; matches Isaac to < 1 um) + coarse gripper boxes |
| `tools/approach.py` | collision-checked approach (home -> ready -> pre-grasp -> grasp) |
| `tools/oracle.py` | scripted oracle (+ `--variant nop / naive_nocomb / naive_offset` negative checks) |
| `tools/replay.py` | open-loop replay of saved actions; `--enable_cameras` writes top / left-wrist frames + mp4 |
| `tools/analyze.py` | per-phase summary of a run |
| `install.sh` | copies the task files + assets into a YAMLab clone and adds the registration lines |
| `assets/<tier>/` | generated assets (copied back from vast) |
| `sync.sh`, `vs.sh`, `run.sh`, `replay.sh`, `checks.sh` | mirror to vast, ssh with retries, run oracle / replay / the full evidence set on vast |
| `render_on_rtx.sh` | for the lead: install + replay the final runs with `--enable_cameras` on an RTX host |
| `out/{vef,eaf}*` | final evidence (metrics.json, actions.npy, states.npz, plots; replay_metrics.json) |
| `tools/jacket_clearance.py`, `plot_run.py`, `strand_local.py`, `grasp_slip.py`, `test_goal.py` | analysis / offline goal test |
| `tools/strand_drift_test.py`, `env_drift_test.py`, `env_props.py` | physics diagnostics (strand drift) |

## Build and run (vast)

```bash
R=/workspace/yamlab_port/runs/fiber_bundling
. /workspace/yamlab_port/env.sh
FB_OLD_PKG=$R/old_pkg python $R/task/tools/build_assets.py --tier very_easy --out $R/assets --tx 0.25 --ty -0.01   # also --tier easier
bash $R/task/install.sh $R/yamlab $R/assets
bash $R/task/checks.sh <prefix> FiberBundling-VeryEasy-v0   # oracle, nop, 2 replays, 2 naive -> $R/out/<prefix>*
bash $R/task/run.sh <name> --task <id> [--variant oracle|nop|naive_nocomb|naive_offset] --max_steps 8900
PYTHONPATH=$R/yamlab YAMLAB_STRIP_CAMERAS=1 python $R/task/tools/replay.py --actions $R/out/<name>/actions.npy \
    --reference $R/out/<name>/states.npz --out $R/out/<name>_replay --device cpu
```

## Render (RTX host, e.g. ws/ws3 Isaac 5.1 container)

Install into a YAMLab clone with `install.sh <clone> assets`, then (no `YAMLAB_STRIP_CAMERAS`):

```bash
PYTHONPATH=<clone> python tools/replay.py --actions <run>/actions.npy --out <dir> --device cpu --enable_cameras
```
