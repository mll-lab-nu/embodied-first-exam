# knot_untying -> YAMLab

Port of RoboTangle `knot_untying` (tiers very_easy, easier) to YAMLab (two YAM arms, Isaac Lab 2.3 / Isaac Sim 5.1). The rope is a capsule-chain articulation. See STATUS.md for state, numbers and deviations.

## Layout

- `overlay/yamlab/` -> copied into a YAMLab clone's package dir `yamlab/yamlab/` (task files only):
  - `configs/tasks/knot_untying.yaml` (env ids, goal thresholds, CPU in every mode, grasp_detect)
  - `envs/tasks/knot_untying_manager_cfg.py` (scene: rope articulation; events; terminations)
  - `envs/tasks/knot_untying_manager.py` (env class, goal check, gym ids `KnotUntying-VeryEasy-v0`, `KnotUntying-Easier-v0`, factory kwarg `strip_cameras=True` for physics-only hosts)
  - `envs/tasks/knot_untying_lib/` rope geometry + old predicate (`rope_geom.py`), USD writer (`rope_usd.py`), parameters (`rope_params.py`), old start data (`src_data/`), built assets (`assets/<tier>/rope.usda, start_state.npz, rope_meta.json`)
- `overlay/REGISTRATION.md`, `apply_overlay.sh`: the two registration edits (`envs/tasks/__init__.py`, `envs/robot_registry.py`).
- `scripts/`: `build_assets.py` (rope USD + settled start), `oracle.py` (scripted oracle, also `--variant nop|naive`), `replay.py` (open-loop replay, `--enable_cameras` for frames/video), `plot_run.py` (top-view strip from logged states), `probe_env.py`, `probe_kin.py`, `reach_map.py`, `oracle_lib*.py` (USD FK/IK of the YAM arms).
- `probes/`: rope-model probes and sweeps (`probe_joints.py`, `sweep_rope.py` + variant json files), `test_geom.py` (vectorised predicate == reference).
- `sync.sh`, `vssh.sh`, `vrun.sh`: mirror to vast, ssh with retries, run under nice/timeout with our PYTHONPATH.

## Build and run (vast)

```
./sync.sh                                  # local -> vast task/ and overlay -> runs/knot_untying/yamlab/yamlab
./vssh.sh bash /workspace/yamlab_port/runs/knot_untying/task/apply_overlay.sh
# on vast, in /workspace/yamlab_port/runs/knot_untying/work:
../task/vrun.sh 900  ../task/scripts/build_assets.py --tier very_easy
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-VeryEasy-v0 --out oracle_ve
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-VeryEasy-v0 --variant nop   --out nop_ve
../task/vrun.sh 2400 ../task/scripts/oracle.py --task KnotUntying-VeryEasy-v0 --variant naive --out naive_ve
../task/vrun.sh 2400 ../task/scripts/replay.py --task KnotUntying-VeryEasy-v0 --actions oracle_ve/actions.npy --out replay_ve
python ../task/scripts/plot_run.py oracle_ve
```

Video (on a host where Isaac RTX works, e.g. ws/ws3 in an Isaac 5.1 container with this yamlab copy):
```
python scripts/replay.py --task KnotUntying-VeryEasy-v0 --actions runs/very_easy_or8/actions.npy --out replay_cam --enable_cameras
```
writes `replay_cam/frames/top_*.png, wrist_*.png` and `top.mp4`, `wrist.mp4` (imageio) plus `replay_metrics.json`.
