# Free-held cube layer reversal

With the wrist locked, turn only the top layer +90 degrees, return it to zero, and turn it +90 degrees again. Stabilize the free cube body with other fingers; no external support or object actuation is allowed.

## Authoring contract

- `task.json`: canonical geometry, initialization, ordered predicates and safety bounds.
- `scene.py`: task-owned scene and contact-feature entry point.
- `assets/`: object meshes, textures, license records and checksums in `manifest.json`.
- `render.json`: task camera and presentation profile.

Edit this folder for task-specific work. Common hand physics, replay, grading and render utilities remain in `shared/`.
Run `python3 scripts/dexhand/sync_essential_catalog.py` and then `python3 scripts/dexhand/generate.py --refresh-manifest`.
Generated Harbor modes stay under the repository `tasks/`; do not edit those copies.
Successful authoring actions and videos stay outside task directories and are never packaged as an agent-visible policy.

## Wuji reference solution

`solution/wuji/trajectory.npz` (940 x 26 rows, `hand` = `wuji`, sha256 `067e402f...`) completes the three ordered
layer turns (+90 deg, back to 0, +90 deg) and the terminal hold with the Wuji Hand 2.2 (success at control 940, the
last row; float32-rounded rows also succeed at control 940). The cube rests on the open Wuji palm; the thumb pad lands
on the passive layer's top face and drags it about the layer axis, lifting and landing again at the end of its reach.
Wrist targets stay at the locked pose; only Wuji finger position targets change. Peaks: body rotation 0.055 rad
(limit 0.35; 0.24 before 2026-10-14), body drift 1.6 mm (20 mm), force 0.51 N (80 N). The generator packages it as `solution/wuji/` of both
task directories, and the oracle uses it when the run selects the Wuji hand. Authoring code (never copied into a
task): `tools/run_turn.py` (thumb-drag controller with an integral law on the measured layer angle), `tools/thumb_turn.py`
(thumb IK) and `tools/wuji_gen.py`, which runs the accepted parameters and rewrites the identical archive.
Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/essential_cube_layer/`.
