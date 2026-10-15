# stool_brace_insert (DexHand family, wave 2)

Physical version of scene T27 "Assemble a wooden stool cross brace" (source:
`robot_coding_bench/scripts/scene_expansion/repairs/stool_meta_delivery_trajectory_r1`, a kinematic demo). One
dexterous hand (Sharpa Wave default, Wuji Hand 2.2 selectable) on the six-axis wrist stage of `assemble_hamburger`.

## Why two parts are moved
A rigid frame cannot accept the brace between two fixed legs: the brace is 0.29 m tip to tip while the opposing bore
entries are 0.26 m apart. The task therefore keeps the source scene's own assembly order: the brace's first dowel goes
into the empty bore of the lower side frame (lying flat, three rails already seated), then the opposite side frame is
lowered onto all four upper dowels, which seats the brace's second dowel in the opposite leg. The final upright turn
of the source film is not part of the task.

## Modelling choices
- Geometry from the source `geometry.py` (legs, factory crossrails, rails, dowel/bore dimensions, positions, masses and
  inertias). Bores as in the source (wave 3): radius 4.1 mm for the 4.0 mm dowels (0.1 mm radial clearance), no
  entry chamfer, 24 convex sectors (circumscribed, so the clearance is at least 0.1 mm everywhere); dowels are capsules
  (rounded ends) of the source radius and exposed length. Wave 2 had widened the bores to 5.0 mm with a 4 mm entry
  chamfer; the authoring controller seats all eight dowels with the source clearance as well.
- Collision bitmasks (`scene.BITS`): bore walls touch only dowels; frames touch the table through invisible 1 mm skids
  under each leg face (fewer redundant box/box contacts, ~4x faster); everything else collides normally.
- Solver: implicitfast, elliptic cones, impratio 10 (source values), plus `noslip_iterations = 5`: without it the
  carried 0.58 kg side frame creeps (rolls) in a firm 4-finger grip by several degrees per second.
- Seat and screws are static, non-colliding decor. Pine texture copied to `assets/` (sha256 in `assets/manifest.json`).
- Hand mount: zero wrist angles = palm down, fingers +x, thumb +y (quat `0.7071 0 0.7071 0` under the stage); stage
  origin `task.json` `stage_origin`. Wuji via `hands.replace_wave_hands`, same stage and initial wrist targets.

## Verdict
`checker.py` (stages, seating test, fail-fast list) and the task text in `task.json` `instruction` are the contract.
`state_sha` hashes the integration state, the non-text `task.json` parameters, the checker state and the hand.

## Authoring
`demo.py` + `ctl.py` (not shipped): closed-loop scripted controller reading Session state, recorded as open-loop rows.
`presentation.py` + `studio_renderer.py` (not shipped): PR film from exact saved poses (approved T27 studio look).
Run from this folder with the pinned MuJoCo environment and `DEXHAND_ASSET_DIR` pointing at the Sharpa assets:
```bash
python demo.py --out stool_demo.npz            # ~90 s; success after 2,806 controls
python replay.py --traj solution/trajectory.npz --out replay.json     # ~85 s; success, state_sha afe276e9...
python replay.py --traj solution/trajectory.npz --out replay.json --video replay.mp4 --fps 25 --width 1280 --height 720
python -m pytest -q tests                      # 17 tests, ~4 min (positive, nop, partial, fail-fast, trust boundary, Wuji)
python presentation.py export --trajectory solution/trajectory.npz --export film_export --stride 5
DEXHAND_BLENDER=<blender 4.5.3> python studio_renderer.py --export film_export --output film.mp4 \
    --engine eevee --width 1280 --height 720 --samples 32 --frames-only
python presentation.py encode --export film_export --output film.mp4 --fps 20 --crf 18
```

## Evidence (wave 3 source bores, 2026-10-15; wave-2 structure)
Oracle: two fresh replays success at control 2,806 with identical state_sha `afe276e9...`; float32 rows succeed at
the same step; Harbor oracle 1 / nop 0 in privileged and standard mode, Wuji nop 0. Negatives: nop, truncation
before assembly, one seated brace dowel (stage 2), brace released mid-air (fail-fast `brace_dropped` at control 507),
hand swept into a pre-seated rail (fail-fast `rail_knocked` at control 1282). Replay costs about 0.03 s per control
(noslip solver); `replay_sec` = 1200 s covers 6,000 rows with margin.
