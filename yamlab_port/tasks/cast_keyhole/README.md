# CastKeyhole port (YAMLab)

Port of RoboTangle `cast_keyhole` (robotangle-r2, topogym 2dafa5f) to YAMLab (two YAM arms, Isaac Lab 2.3 / Isaac Sim 5.1).

## Layout

- `tools/keyhole_geometry.py` – ported plate generator (exact convex slab prisms + STL-identical visual), old start pose, goal rule.
- `tools/records/<tier>.json` – verbatim copies of the old geometry records.
- `tools/route.py`, `tools/route_check.py`, `tools/swept_map.py` – the old relative disassembly route, its clearance (fcl), swept regions.
- `tools/layout.py` – re-layout transform (old table mm -> YAMLab world m) and goal region.
- `tools/build_assets.py` – builds `assets/<tier>/keyhole_{gold,silver}/*.usd` + `layout.json` (needs pxr; run on vast).
- `tools/yam_kin.py` – numpy FK/IK of the unchanged YAM USD (validated vs Isaac: < 1 micron).
- `tools/plan.py`, `tools/plan_search.py` – object keyframes + IK feasibility search.
- `tools/install_task.sh <yamlab_repo> <assets_dir>` – copies the task files into a YAMLab clone and adds the registration lines.
- `task/configs/tasks/cast_keyhole.yaml`, `task/envs/tasks/cast_keyhole_manager{,_cfg}.py` – the YAMLab task (gym ids `CastKeyhole-<Tier>-v0`).
- `scripts/scene_smoke.py` – load/settle check + FK validation.
- `scripts/oracle.py` – scripted oracle (`--variant nop|naive_pull|oracle`).
- `scripts/replay.py` – open-loop replay of `actions.npy` (`--enable_cameras` writes top + wrist frames).

## Build and run (vast)

```bash
. /workspace/yamlab_port/env.sh
cd /workspace/yamlab_port/runs/cast_keyhole
cp -r /workspace/yamlab_port/yamlab yamlab            # own copy
python src/tools/build_assets.py very_easy assets      # USD + layout.json
bash src/tools/install_task.sh yamlab assets           # task files + registration
export PYTHONPATH=$PWD/yamlab:$PWD/pylib OMP_NUM_THREADS=2
nice -n 19 python src/scripts/oracle.py --tier very_easy --out runs/oracle_ve --params src/params/very_easy.json
nice -n 19 python src/scripts/replay.py --tier very_easy --actions runs/oracle_ve/actions.npy --out runs/replay_ve \
    --reference runs/oracle_ve/states.npz
# negative checks: oracle.py --variant nop | naive_pull ; video (RTX host): replay.py ... --enable_cameras
```

Physics-only by default (camera sensors stripped via `YAMLAB_NO_CAMERAS=1`, set automatically unless
`--enable_cameras` is passed).

## Oracle (design v4) in one paragraph

Settle 3 s (the authored X-shaped start falls nearly flat). Left arm: face clamp on the gold's +x prong band
(x 20..39 mm, never swept by the silver). Right arm: face clamp on the silver's -x side bar at its COM (the gold
only ever occupies the silver's x_s ~ 0 plane). *stand*: the silver pivots about its lower edge on the table until
perpendicular to the gold (nominal relative pose). *move*: rigid assembly motion to the work pose (gold flat,
silver standing on its edge, carrying the gold through its bar; pose chosen by `tools/plan_search2.py`).
*lower* + 3 s hold with relative feedback (silver follows the filtered measured gold). *turn*: the old +90 deg
key turn, gold yaws 44 deg / silver -46 deg about the bar axis. *channel*: the old channel guides + 40 mm,
mostly done by the silver. Then gold down + release, left arm home; silver carried upright over the goal,
set down leaning 30 deg, tipped to 65 deg about its edge and released; success latches 0.5 s later.
Parameters: `params/very_easy.json` (`--params`). Per-step 14-D actions in `actions.npy`.
