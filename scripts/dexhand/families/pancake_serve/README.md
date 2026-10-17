# pancake_serve (authoring notes)

DexHand family built from scene T16 "Serve food from a frying pan with a spatula" of the 50-scene expansion
(local authoring folder `scripts/scene_expansion/repairs/pan_sharpa/`, approved kinematic film of the scene review).
The source scene prescribed every object pose; here the pancake moves only through contact with a hand-held turner.

## Files
| file | role |
|---|---|
| `scene.py` | MJCF builder: counter, pan, plate, pancake, OXO turner (3 passive bending strips), one hand on the six-axis wrist stage (`hands.replace_wave_hands` for Wuji) |
| `checker.py` | ordered stages, terminal hold, fail-fast list (simulator state only) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4; adds `snapshot`/`restore` for search) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), optional `--video` |
| `task.json` | frozen instance: thresholds, cameras, wrist ranges, per-hand settled reset (`initial_qpos`, `initial_targets`) |
| `assets/` | source meshes + browning texture copied byte-for-byte, `manifest.json` (sha256 + size, checked at build) |
| `tools/make_reset.py` | authoring only: settles the pre-held turner grasp and writes the reset into `task.json` |
| `tools/demo.py` | authoring only: closed-loop turner-pose servo recorded as open-loop rows (the oracle); `--params '{"hand": "wuji"}'` for Wuji, `variant` drop/toss/knock for negatives |
| `tools/film.py`, `tools/film_blender.py` | authoring only: export exact native geom poses of a passing replay, Blender 4.5 studio render (T16 film materials/lights/camera), encode |
| `tests/test_pancake_serve.py` | authoring tests (oracle x2 + hash, Wuji oracle, float32, nop both hands, truncation, one row short, drop fail-fast, archive abuse) |
| `solution/trajectory.npz` | Sharpa Wave oracle rows (`actions`, `hand`, `task`), used in both modes |
| `solution/wuji/trajectory.npz` | Wuji Hand 2.2 oracle rows (875 rows, success after 725 controls) |

## Modelling choices (all declared)
- Geometry, masses and inertias are the source's (pan 0.90 kg, plate 0.48 kg, pancake 0.06 kg rigid coherent disk
  140 x 9.5 mm, turner 0.11 kg root + 0.04 kg blade). Blade strips: hinge stiffness EI/length with E = 190 GPa and a
  0.25 mm steel core, damping 0.002, range +-0.35 rad. Physics: 1 ms steps (thin 0.5-1.5 mm blade), implicitfast,
  elliptic cones, impratio 10, 80 iterations, multiccd; 20 substeps per 50 Hz control.
- Pair frictions via geom `priority`: pancake-pan 0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60,
  hand-handle 1.2, objects-counter 0.7. These are estimates for a cooked pancake, a greased thin turner edge and a
  glazed plate; the low blade friction is what lets a rigid pancake ride onto a rigid-edged blade.
- The hand: one Sharpa Wave (default) or Wuji Hand 2.2 on the six-axis wrist stage of `assemble_hamburger`, with
  world-frame slide ranges x [0, 1.3], y [-0.8, 0.6], z [0.85, 1.45] m (the counter top is at 0.85 m as in the source)
  and hinge ranges +-3.5 rad (the palm-down start pose has `wrist_rx` = pi).
- Pre-held turner: `tools/make_reset.py` holds the turner still only while the fingers close on the handle (authoring
  time), then releases it and integrates the whole scene freely (grasp settling, a conditioning wrist motion, rest).
  The resulting state is frozen in `task.json`; the runtime reset writes only that state with zero velocity. No weld,
  equality or object actuator exists at any time; a no-op keeps the turner in the hand and fails on the budget.
- Checker thresholds: the plate-centre tolerance is 0.058 m (plate rim radius 0.128 m minus pancake radius 0.070 m,
  i.e. the whole pancake inside the plate outline), stricter than the "plate radius - 2 cm" (0.108 m) starting point.
  Pan/plate "tilt" is the angle between the body's up axis at reset and now.
- Drops fail at the first substep (no debounce): pancake touching nothing with centre-of-mass vz < -0.35 m/s (about
  6 mm of free fall; the oracles peak at 0.29 m/s when the blade slides out from under the pancake in the plate), or
  the turner without hand contact and vz < -0.35 m/s; plus counter/floor contact. Speeds come from
  `mj_objectVelocity(mjOBJ_BODY)` (centre of mass, checked against a finite difference of `xipos`).
- `state_sha` hashes the integration state, the verdict counters/failure, the physics/verdict keys of `task.json`
  (`Checker.HASHED_KEYS`) and the selected hand's frozen reset, never instruction prose or cameras.

## Evidence commands
```bash
export DEXHAND_ASSET_DIR=<checkout>/images/dexhand/assets/hand OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python tools/make_reset.py --hand sharpa --write          # re-author the Sharpa reset (changes the instance)
python tools/demo.py --out solution/trajectory.npz        # oracle rows (success after 724 controls + 150 hold rows)
python replay.py --task pancake_serve --traj solution/trajectory.npz --out r1.json   # x2 in fresh processes
python replay.py --task pancake_serve --traj solution/trajectory.npz --video oracle.mp4 --camera overview
```
Film: `python tools/film.py export --trajectory solution/trajectory.npz --export E --stride 4`, then
`blender -b -P tools/film_blender.py -- --export E --output F --samples 16`, then
`python tools/film.py encode --export E --frames F --output pancake_serve.mp4` (1x physics playback at 12.5 fps).

Negative variants: `tools/demo.py --params '{"variant": "drop", "slack_rows": 0}'` (pancake rolled off the blade
over the counter: `pancake_dropped`) and `'{"variant": "knock", "slack_rows": 0}'` (pan shoved through its handle:
`pan_displaced`).

## Wave 3 (2026-10-15): Marvin arm rig

The hand now sits on the right arm of the Tianji Marvin stand (`scripts/dexhand/shared/arm_rig.py`, robot
`marvin-bimanual-sharpa-wave`, stand at the origin facing +x, `base_z = floor_z + 0.1`; the left arm is parked). The
mount body on the right flange is named `wrist_stage`, so the checker's hand lookup is unchanged; arm links and the stand
count as robot ("hand") for every contact rule. The decorative cabinet under the counter starts behind the stand's base
plate (x >= 0.77 m); no robot geom overlaps furniture (exact `mj_geomDistance` check) and over the oracle no arm link or
the stand touches anything (per-substep contact audit). Rows: 14 arm targets (left J1-J7, right J1-J7), then the left
and the right hand's fingers (58 Sharpa / 54 Wuji).

- `tools/make_reset_arm.py --legacy <wave-2 task.json> --hand <h> --write`: the wave-2 settled grasp transferred to the
  arm (same hand-root pose by IK, same fingers and object poses), settled 1.5 s with a closed-loop arm correction,
  frozen with its final targets.
- `tools/demo_arm.py`: the wave-2 turner-pose servo (`tools/demo.py`) with the hand pose converted to right-arm joint
  targets by IK + joint integral (`shared/arm_ik.py`), rows rounded to float32 before they are executed (lossless
  float32 round trip).
- Realism (wave 3): the turner starts at rest on the counter at the T16 source pose (0.76, -0.30, 0.878), quat
  (0.9895, 0.1443, 0, 0), handle end and blade base on the counter (`tools/pickup_arm.py make-reset --hand <h> --write`:
  turner placed there, hand opened, scene settled 1.5 s with the arm held by a closed-loop correction, frozen).
  `tools/pickup_arm.py author --out solution/trajectory.npz`: palm-down power grasp of the handle 30 mm from the root
  toward the neck (index toward the blade, fingers +x; handle 35 mm under the proximal finger segments), squeeze,
  lift 10 cm, then the demo_arm serve. Sharpa: success at control 1,017, 1,167 rows. No Wuji oracle is packaged.
- Not done (time): the other hand supporting and tilting the pan (~8 deg, 4 cm lift in the source trajectory); the
  left arm stays parked.
