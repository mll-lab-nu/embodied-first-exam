# DexHand family `pot_shelf_transfer` (T17 "Place a two-handle pot into a shelf")

Authoring folder of the generated pair `tasks/dexhand-pot-shelf-transfer-i00-{privileged,standard}`
(`scripts/dexhand/generate.py --only-family pot_shelf_transfer`; registration per the DexHand family plugin,
`family.json`). Only the files named in `family.json` reach a task directory; `tools/`, `tests/` and this README stay
in the repository.

## What is frozen

| file | content |
|---|---|
| `assets/pot_sharpa.xml` | the manager-accepted T17 MJCF (`artifacts/scene-expansion-50/evidence/pot_transfer/trial-14/model.xml`, sha256 `eb4a5469...`), byte for byte except that absolute mesh paths become `@SHARPA@` / `@TIANJI@` / `@POT@` placeholders and three named static cameras (`overview`, `front`, `shelf`) are appended to `<worldbody>` |
| `assets/manifest.json` | sha256 + size of that XML and of every mesh it references, per asset root (Sharpa: `DEXHAND_ASSET_DIR`, image `/opt/dexhand/hand`; Tianji Marvin arms: `DEXHAND_TIANJI_DIR`, image `/opt/dexhand/tianji`; pot: `assets/pot/`) |
| `assets/pot/*.stl` | the five pot meshes (CC0 Innerscene Harvest Pot, converted by `scripts/scene_expansion/tasks/pot_transfer/`) |
| `assets/reset.json` | the accepted keyframe by joint/actuator name (the Wuji reset reuses the arm and pot values) |
| `solution/trajectory.npz` | the accepted 8,850 x 58 Sharpa rows (`actions`, `hand`, `task`) |

`tools/freeze.py` derives all of them from the read-only sources (`--check` compares). The runtime verifies every
file against the manifest before compiling, so a changed mesh or XML is an error, never a silently different scene.

## Runtime and predicate

`runtime.py` (`Session`): one action row = one 2 ms physics step (500 Hz, `control_dt = 0.002`, `substeps = 1`),
because the accepted controls change on every physics step. `mj_step` then `mj_forward` per row, exactly like the
accepted audit; the predicate is evaluated on the post-step state. Thresholds are in `task.json` `predicate`:

- fail-fast: pot base below z 0.70 or outside the workspace box; tilt > 0.5 rad; dropped (downward speed > 0.6 m/s,
  or no contact of any force for > 30 steps); pot contact (>= 0.02 N) with anything but hands/worktop/shelf board;
  robot-furniture / robot-robot collision (internal hand contacts excepted); hand-pot penetration > 3 mm; joint
  overshoot > 5 mrad; unstable physics; 30,000 rows without success.
- stage 1 (bimanual carry): >= 250 steps with pot z > 0.785, no support load, each hand's upward load >= 0.5 N
  (the accepted audit's airborne definition).
- stage 2 (released hold, 1,000 consecutive steps): base within 4 cm / 12 mm of (0.46, 0.31, 0.79), tilt <= 0.10 rad,
  speed <= 0.03 m/s and <= 0.15 rad/s, shelf board the only contact, vessel footprint (r 0.143 m) on the board,
  whole pot inside the bay (open-front overhang <= 5 cm), every hand collision geom >= 4 cm from the pot.

Margins of the accepted episode under this predicate (tools/verify_oracle.py, tests): peak tilt 0.273 rad, peak
downward speed 0.499 m/s (the release drops the pot about 13 mm), longest contact-free streak 16 steps, penetration
0.70 mm, joint overshoot 6.4e-9 rad, front-handle overhang 34 mm, hand clearance >= 4 cm from step ~7450; the
released hold starts at step 7,603 and completes at row 8,602 (episode end; the remaining 248 rows are not executed).

Wuji Hand 2.2: `hands.replace_wave_hands(root, "wuji")` on the frozen tree (same arms, same mounts), 54 targets,
neutral fingers, arm/pot reset from `assets/reset.json`. No successful Wuji trajectory is claimed.

## Evidence (workspace `artifacts/ready-10-2026-10-14/pot/`)

```bash
cd robot_coding_bench
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python3 scripts/dexhand/families/pot_shelf_transfer/tools/freeze.py --check
python3 scripts/dexhand/families/pot_shelf_transfer/tools/verify_oracle.py \
  --out ../artifacts/ready-10-2026-10-14/pot/verify/oracle-verification.json
python3 -m pytest -q scripts/dexhand/families/pot_shelf_transfer/tests
python3 scripts/dexhand/generate.py --only-family pot_shelf_transfer --refresh-manifest
```

`verify_oracle.py` checks: the 8,850 rows equal the accepted actions; the packaged scene's initial state equals the
recorded initial state; every recorded qpos/qvel is reproduced exactly; the final integration-state digest equals the
accepted `5bcddef8...`; `Session` succeeds; two fresh `replay.py` processes agree on `state_sha`.
