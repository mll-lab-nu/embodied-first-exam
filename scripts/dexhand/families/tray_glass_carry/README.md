# tray_glass_carry (authoring notes)

Physical DexHand version of scene-expansion task T48 "Carry a tray with filled drink cups" (a kinematic demo before:
tray and glass poses were prescribed). Two hands on two six-axis wrist stages lift the original perforated serving
tray by its open handle slots, carry it with two loose filled glasses around the bottle and across the counter gap,
set it down on the receiving counter and let go.

## Files
| file | role |
|---|---|
| `scene.py` | builds the MJCF: frozen T48 tray + glasses (`assets/t48_tray_glasses.xml`), counters, bottle, glass/water visuals, two wrist stages with the left/right Sharpa Wave (`assets/sharpa_bimanual_hands.xml`); Wuji via `hands.replace_wave_hands` |
| `checker.py` | ordered stages (lifted, placed, released + 1 s hold) and the fail-fast list, from simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4), incl. `snapshot`/`restore` |
| `replay.py` | fresh-process replay CLI (section 5), optional `--video` |
| `task.json` | frozen instance: thresholds, geometry, stage gains, cameras, instruction text |
| `tools/extract_assets.py` | authoring: froze `assets/` from `scripts/hand_support/tasks/T48/model.xml` and `families/sweep_dustpan/assets/sweep_sharpa.xml` (source sha256 in `assets/manifest.json`) |
| `tools/controller.py`, `tools/oracle_params.json` | authoring: closed-loop scripted controller that records the oracle rows (per-hand parameters) |
| `tools/presentation.py`, `tools/studio_render.py` | authoring: export exact MuJoCo poses of a replay and render the Blender studio film (renderer copied from the approved T48 film, `scripts/scene_expansion/tasks/drink_tray/trajectory_r1/studio_render.py`) |
| `tests/test_tray_glass_carry.py` | authoring tests (positive, float32, slack, nop, truncation, drop, low release, knock, forged members, shadowing member, NaN, widths, hand labels, Wuji stages, state hash independent of texts) |
| `solution/trajectory.npz` | Sharpa oracle (1,072 rows, success at control 952), both modes |
| `solution/wuji/trajectory.npz` | Wuji Hand 2.2 oracle (1,148 rows, success at control 1,028), packaged by the generator as `solution/wuji/` |

## Modelling choices
- Tray: the T48 meshes, mass 1.0 kg and inertia unchanged; friction 0.5 (T48). The rim has an open handle slot
  (16 mm tall, about 17 cm long, between the 4 mm lower band and the 8 mm top bar) at both ends of the long axis; these
  are the grasp affordances ("hand access/handles retained" in T48).
- Glasses: T48 base cylinder + 48 faceted wall pieces, 0.275 kg (glass + 150 mL water), friction 0.4. Liquid is not
  simulated: spill = glass tilt above 15 degrees (stated in the instruction). Glass shell and water volume visuals use
  the T48 builder's lathe profiles.
- Counters (0.40 x 0.80 m, tops at z = 0.88 m, 30 mm gap) and the bottle (r = 28 mm, 0.28 m tall, at (0.52, 0.22))
  from the T48 builder; bottle collision = two cylinders.
- Rig: two wrist stages (x/y/z slides then rx/ry/rz hinges at the wrist, position actuators), base poses
  (0.35, +-0.272, 1.15) m, fingers down, palms toward the tray. No gravity compensation; the stages sag ~3 mm under the
  hand weight, which the controller absorbs. Nothing attaches an object to a hand; no forces on objects.
- Physics: 2 ms implicitfast, elliptic cones, 100 iterations, multi-CCD; max contact penetration in the oracle is
  0.09 mm (Sharpa) / 0.13 mm (Wuji).

## Verdict details
- Stages, hold and fail-fast list: `checker.py` docstring and `task.json` `instruction` (the generator copies the latter
  into both instructions). Fail-fast runs after every 2 ms physics step. Drops: any tray/glass COM moving down faster
  than 0.6 m/s, or faster than 0.2 m/s while unsupported (tray: no hand or counter contact; glass: no tray, glass, hand
  or counter contact) - no drop-and-catch window. Hand-bottle contact fails like tray/glass-bottle contact.
- Speeds are `data.cvel` of root free bodies without children, i.e. the COM velocity (checked against finite
  differences of `xipos`). `state_sha` hashes the integration state, the physics/predicate parameters of `task.json`
  (texts, cameras and titles excluded), the predicate state and the hand.

## Evidence commands (from this folder, pinned venv)
```bash
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand
python tools/controller.py --hand sharpa --out solution/trajectory.npz        # deterministic rows
python replay.py --traj solution/trajectory.npz --out out/r1.json           # twice: identical state_sha
python tools/controller.py --hand wuji --out solution/wuji/trajectory.npz
MUJOCO_GL=egl python replay.py --traj solution/trajectory.npz --out out/v.json --video out/tray.mp4
python tools/presentation.py --trajectory solution/trajectory.npz --export out/film-export      # exact poses
python tools/studio_render.py --export out/film-export --output out/tray_glass_carry.mp4 \
    --width 1280 --height 720 --samples 32 --fps 25 --crf 21   # DEXHAND_BLENDER=<Blender 4.5.3>, OptiX GPU
python -m pytest -q tests/test_tray_glass_carry.py
```
