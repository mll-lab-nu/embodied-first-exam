# buzz_wire_3d -> YAMLab

Port of the old RoboTangle `buzz_wire_3d` family ("Guide the metal loop along the entire wire without
touching it, then release the tool on the finish support and let it settle.") to YAMLab (YAM bimanual,
Isaac Sim 5.1 / Isaac Lab 2.3.2). The robot is unchanged; only task files are added.

State: very_easy and easier DONE (oracle, bit-identical replays, nop and naive, state-playback video; see STATUS.md).

Lead-approved deviations (details and evidence in STATUS.md):
- a taller, longer wooden handle: 45 x 9.8 x 16 mm instead of 30.52 x 9.8 x 7 mm (`tool_old_vs_new.png`);
- the start yaw about the start post is 60 deg instead of 11.3 deg (`start_old_vs_new.png`);
- the wand is carried by a ring grip;
- wand-metal friction is 1.0 and the wand's solver velocity iterations are 4.

## Layout of this folder

| path | what |
|---|---|
| `yamlab_task/` | files to drop into a yamlab clone: `configs/tasks/buzz_wire_3d.yaml`, `envs/tasks/buzz_wire_3d_manager{,_cfg}.py`, `envs/tasks/__init__.py` and `envs/robot_registry.py` (= upstream + 2 registration lines each) |
| `assets/<tier>/` | USD assets (`wand`, `rail`, `stops`, `deck`) + `geometry.json`; install at `<yamlab clone>/assets/buzz_wire_3d/<tier>/` (or set `BUZZ_WIRE_ASSETS`) |
| `tools/make_assets.py` | builds `assets/` from the STL package (plain pxr) |
| `tools/oracle_r.py`, `tools/stages_a.py` | scripted oracle (+ `--mode nop`, `--mode naive_skip_traverse`); `stages_a.py` is the stage sequence |
| `tools/dry_run_a.py` | offline kinematic dry run of the oracle: `python dry_run_a.py <start yaw deg> <tier>` |
| `tools/replay.py` | open-loop replay of a saved action file; `--enable_cameras` writes top + wrist frames |
| `tools/bw_runner.py` | env creation, stepping, per-step logging (`*_states.npz`), metrics JSON, state hash |
| `tools/plan_r.py`, `ik.py`, `yam_kin.py`, `grasps.py`, `bw_geom.py` | numpy planning: YAM kinematics from yam.usd, batched DLS IK, grasp frames, collision samples, RRT-Connect |
| `tools/*study*.py`, `plan_r_keys*.py`, `layout_sweep.py`, `finish_post_grid.py` | reach / feasibility studies (see STATUS.md) |
| `data/stl/<tier>/` | the old RoboTangle STL package for very_easy and easier (rail centreline, layout, deck/stop meshes); the planning tools read it (`BUZZ_STL_ROOT` overrides) |
| `tools/finish_grip_map.py`, `tools/diag_wire_hits.py` | easier finish studies: grip feasibility maps, nearest arm links to the wire |
| `video/very_easy/`, `video/easier/` | rendered oracle videos (state playback) |
| `sync_to_vast.sh` | host-specific helper (ssh key, vast port): mirror this folder to vast and install the task into the per-family yamlab copy |
| `results/` | copies of the small evidence files (metrics JSON, action files, plots) |

## Python requirements for the planning tools

numpy, scipy, trimesh and pxr (usd-core) for `make_assets.py`. The YAM kinematics are cached in `data/yam_kin.npz`.
The Isaac runs (`oracle_r.py`, `replay.py`) use the Isaac Lab Python of the yamlab install. All tool paths are
relative to this folder; run the tools from `tools/` or with `tools/` on `sys.path`.

## Oracle knobs (env, defaults per tier in `tools/stages_a.py`)

| variable | what |
|---|---|
| `BUZZ_FINISH` | finish strategy: `gdown` (pen grip, default) or `relay` (left pen grip, then right side pinch) |
| `BUZZ_GD_ROLL`, `BUZZ_GD_YAW`, `BUZZ_GD_TILT`, `BUZZ_GD_XTIP`, `BUZZ_GD_HEIGHTS` | finish pen grip: roll and yaw (deg), tilt (deg), tip position (m) and release heights (m) |
| `BUZZ_HZ_FINISH` | loop height above the deck at the end of the carry (handover 2) |
| `BUZZ_FINISH_ATT` | release attitudes tried in order, `roll:yaw_short,...` (deg): wand roll about the handle, yaw stopped short of the finish yaw |
| `BUZZ_MIRROR=1` | mirrored sequence (right picks and places, left carries) |
| `BUZZ_RELAY_HZ`, `BUZZ_RELAY_OPEN`, `BUZZ_RELAY_WAIT` | relay finish: heights, release opening, wait steps |
| `BUZZ_STOP_AFTER_LIFT=1` | stop after the pick-and-lift (lift test) |

## Install into a yamlab clone

```bash
Y=<yamlab clone>
cp yamlab_task/configs/tasks/buzz_wire_3d.yaml $Y/yamlab/configs/tasks/
cp yamlab_task/envs/tasks/buzz_wire_3d_manager*.py yamlab_task/envs/tasks/__init__.py $Y/yamlab/envs/tasks/
cp yamlab_task/envs/robot_registry.py $Y/yamlab/envs/
mkdir -p $Y/assets/buzz_wire_3d && cp -r assets/* $Y/assets/buzz_wire_3d/
```

Gym ids: `BuzzWire3D-VeryEasy-v0`, `BuzzWire3D-Easier-v0`. The task YAML sets CPU physics, 1 env and 300 s episodes; use mode=evaluation (the runners do).
`BUZZ_NO_CAMERAS=1` drops the camera sensors (physics-only hosts such as vast).

## Run (vast)

```bash
. /workspace/yamlab_port/env.sh
RUN=/workspace/yamlab_port/runs/buzz_wire_3d
export PYTHONPATH=$RUN/yamlab BUZZ_NO_CAMERAS=1
python $RUN/src/tools/oracle_r.py --headless --tier very_easy --mode oracle --out OUT   # oracle
python $RUN/src/tools/oracle_r.py --headless --tier very_easy --mode nop --nop_steps 9100 --out OUT   # nop
python $RUN/src/tools/oracle_r.py --headless --tier very_easy --mode naive_skip_traverse --out OUT   # naive
python $RUN/src/tools/replay.py --headless --tier very_easy --actions OUT/oracle_actions.npy --out OUT2
```

## Render (host with working RTX)

Install the task as above into the yamlab used there, unset `BUZZ_NO_CAMERAS`, then
`python tools/replay.py --headless --enable_cameras --tier very_easy --actions oracle_actions.npy --out DIR --frame_every 2`
and assemble `DIR/frames/top_camera_*.png` / `right_wrist_camera_*.png` with ffmpeg.
