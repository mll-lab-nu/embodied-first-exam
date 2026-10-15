# rope_threading (YAMLab port)

Port of RoboTangle `rope_threading` to YAMLab (two YAM arms, Isaac Lab 2.3 / Isaac Sim 5.1, CPU PhysX).
Gym ids `RopeThreading-Easy-v0`, `RopeThreading-Medium-v0` (D12 layout, see STATUS.md). State and findings: `STATUS.md`.

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
- `tools/medium_layout_search.py` - medium re-layout + reach study (numpy only, batched IK; see STATUS.md "Medium");
  `tools/plot_layout.py` - top view of the medium re-layout (old vs new, arm per stroke).
- `evidence/` - small copies of the key runs: `or3/` (easy deliverable oracle: actions.npy, metrics.json, goal-log
  tail, stage plot), `rp1/`, `rp2/` (replays), `nop2/`, `naive1/`, `naive2/` (negatives), `or1_hold/`, `or2_hold/`,
  `or4_release_diag/`, `studies/` (stiffness probe, easy layout study, asset build), `medium_layout/`; the full runs
  (states.npz, goal_log.jsonl) stay on vast in `work/runs/<run>/`. `video/easy/` = the lead's render of or3.
  Medium: `mor1/` (deliverable oracle), `mrp1/`, `mrp2/` (replays), `mnop1/`, `mnaive1/`, `mnaive2/` (negatives), `R2a/`,
  `R2a_rp/` (development run with the same actions); full runs on orbits3 `/data/pingyue/yamlab/runs/rope/work/runs/`.
  `video/medium/` = state-playback render of mor1 (`top.mp4`, `rings.mp4`).
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
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/oracle.py --variant naive_nolast --out runs/naive2"
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/oracle.py --variant naive --out runs/naive1"
# open-loop replay (bit-identity: compare rope_state_sha16 with the oracle's metrics.json)
./vssh.sh "$R/task/vrun.sh 3600 $R/task/tools/replay.py --actions $R/work/runs/or3/actions.npy --out runs/rp1"
# options: --finish hold|release (default release), --env_mode replay (diagnostic: no terminations),
# --save_ckpt (snapshot after every regrip) + --resume <run>/ckpt_ring2.pt (development only: resume from ring 2)
# medium: --task RopeThreading-Medium-v0 (finish defaults to hold; per-ring --feed_start/--feed_stop/--pull_xyz/--drop_xyz)
```

Medium (orbits3; `run.sh` = vrun.sh's equivalent, runs in `$R/work`; ~20 min per oracle run):
```bash
R=/data/pingyue/yamlab/runs/rope
A="--task RopeThreading-Medium-v0 --feed_tip start --pick_arm left --flip 1 --ledge_align 0 --reseat 0 --finish hold --repush 0 0
   --chain LR,RR,R --grasp_from_tip 0.24 --overhang 0.31 --recv_env_clear 0.01 --flip_x 0.622 --flip_y 0.345
   --pull_xyz [[0.58,-0.1,1.0],[0.635,-0.532,1.0]] --drop_xyz [[0.58,-0.12,0.9],[0.5,-0.4,0.95]] --lay [null,[0.51,-0.42,18,0.17]] --lay_drag 0.10"
$R/run.sh 7200 $R/task/tools/oracle.py $A --out runs/mor1                                  # deliverable
$R/run.sh 7200 $R/task/tools/oracle.py --task RopeThreading-Medium-v0 --variant nop --nop_steps 9000 --out runs/mnop1
$R/run.sh 7200 $R/task/tools/oracle.py $A --variant naive --out runs/mnaive1
$R/run.sh 7200 $R/task/tools/oracle.py $A --variant naive_nolast --out runs/mnaive2
$R/run.sh 3600 $R/task/tools/replay.py --task RopeThreading-Medium-v0 --actions runs/mor1/actions.npy --out runs/mrp1
# video (state playback; render needs LD_LIBRARY_PATH=/data/pingyue/yamlab/deps/lib for libGLU/libOpenGL on orbits3)
$R/run.sh 3600 $R/setup/render_states.py dump --task RopeThreading-Medium-v0 --actions runs/mor1/actions.npy --out render/mdump
$R/run.sh 5400 $R/setup/render_states.py render --task RopeThreading-Medium-v0 --states render/mdump/states_full.npz --out render/mvideo \
  --frame_every 2 --fps 15 --cameras top --closeup rings=0.90,0.35,1.35:0.62,-0.17,1.02:55
```

Rendering (needs a host where Isaac RTX works, e.g. ws in `eai-robolab:0.1.2`): copy the yamlab copy with the overlay
and assets, then `python tools/replay.py --task RopeThreading-Easy-v0 --actions <run>/actions.npy --out <dir> --enable_cameras`
(top + one wrist camera frames every 3 control steps, top.mp4 / wrist.mp4 if imageio is present).

Runs stop at the first terminated step (YAMLab auto-resets the env after it); the last logged rope state is
therefore the reset state, and the goal values at the latch are the last row of goal_log.jsonl.
Each oracle/replay run writes `actions.npy`, `states.npz` (rope link positions/quats, both TCPs, joints, actions per
control step), `goal_log.jsonl` (goal diagnostics per step) and `metrics.json`.
