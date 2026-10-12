# rope_threading (YAMLab port)

Port of RoboTangle `rope_threading` to YAMLab (two YAM arms, Isaac Lab 2.3 / Isaac Sim 5.1, CPU PhysX).
Gym ids `RopeThreading-Easy-v0`, `RopeThreading-Medium-v0` (medium assets not built yet). State and findings: `STATUS.md`.

## Layout of this folder

- `overlay/yamlab/` - files added to a YAMLab copy (nothing in the robot is touched):
  - `configs/tasks/rope_threading.yaml` (thresholds, CPU in every mode)
  - `envs/tasks/rope_threading_manager_cfg.py`, `rope_threading_manager.py` (scene, goal check, gym registration)
  - `envs/tasks/rope_threading_lib/` - `threading_geom.py` (re-layout, rings, old success predicate),
    `rope_chain.py`, `rope_usd.py` (capsule chain, from knot_untying), `fixtures_usd.py`, `rope_params.py`,
    `src_data/<tier>/` (copies of the STL package's layout.json, start centreline, start_state.md),
    `assets/<tier>/` (generated: rope.usda, fixtures.usda, start_state.npz, rope_meta.json)
- `apply_overlay.sh` - adds the two registration lines (`envs/tasks/__init__.py`, `envs/robot_registry.py`).
- `tools/` - `build_assets.py`, `oracle.py` (+ `rt_common.py`, `plan_np.py`, `yam_kin.py`), `replay.py`,
  `plot_states.py`, `grip_trace.py`, `grip_axis_trace.py`, `keypose_study.py`, `reach_map.py`.
- `tools/medium_layout_search.py` - medium re-layout + reach study (numpy only; see STATUS.md "Medium").
- `tools/resume.py` - development only: resume the oracle from a `--save_ckpt` stage snapshot.
- `evidence/` - small copies of the key runs: `or3/` (easy deliverable oracle: actions.npy, metrics.json, goal-log
  tail, stage plot), `rp1/`, `rp2/` (replays), `nop2/`, `naive1/`, `naive2/` (negatives), `or1_hold/`, `or2_hold/`,
  `or4_release_diag/`, `studies/` (stiffness probe, easy layout study, asset build), `medium_layout/`; the full runs
  (states.npz, goal_log.jsonl) stay on vast in `work/runs/<run>/`. `video/easy/` = the lead's render of or3.
- `probes/` - measurements (stiffness, predicate unit test, grip probe, handover searches, ...).
- `sync.sh` / `vssh.sh` / `vrun.sh` - mirror to vast, ssh with retries, run under nice 19 + timeout.

## Build and run (vast)

```bash
./sync.sh                                   # local -> /workspace/yamlab_port/runs/rope_threading/{task,yamlab}
./vssh.sh 'bash /workspace/yamlab_port/runs/rope_threading/task/apply_overlay.sh'
R=/workspace/yamlab_port/runs/rope_threading
# assets (rope + fixtures + settled start), ~1 min
./vssh.sh "$R/task/vrun.sh 900 $R/task/tools/build_assets.py --tier easy"
# predicate unit test (numpy only)
python3 probes/test_predicate.py overlay/yamlab/envs/tasks/rope_threading_lib
# oracle / negatives (from env.reset(), mode=evaluation, physics only, cameras stripped; ~8 min each on vast)
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/oracle.py --out runs/or3"                  # deliverable
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/oracle.py --variant nop --nop_steps 5400 --out runs/nop2"
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/oracle.py --variant naive_noR2 --out runs/naive2"
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/oracle.py --variant naive --out runs/naive1"
# open-loop replay (bit-identity: compare rope_state_sha16 with the oracle's metrics.json)
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/replay.py --actions $R/work/runs/or3/actions.npy --out runs/rp1"
# options: --finish hold|release (default release), --env_mode replay (diagnostic: no terminations),
# --save_ckpt + tools/resume.py --ckpt <run>/ckpt_regrip.pt (development only: resume the R2 stages)
```

Rendering (needs a host where Isaac RTX works, e.g. ws in `eai-robolab:0.1.2`): copy the yamlab copy with the overlay
and assets, then `python tools/replay.py --task RopeThreading-Easy-v0 --actions <run>/actions.npy --out <dir> --enable_cameras`
(top + one wrist camera frames every 3 control steps, top.mp4 / wrist.mp4 if imageio is present).

Runs stop at the first terminated step (YAMLab auto-resets the env after it); the last logged rope state is
therefore the reset state, and the goal values at the latch are the last row of goal_log.jsonl.
Each oracle/replay run writes `actions.npy`, `states.npz` (rope link positions/quats, both TCPs, joints, actions per
control step), `goal_log.jsonl` (goal diagnostics per step) and `metrics.json`.
