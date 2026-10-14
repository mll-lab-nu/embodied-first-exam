# Fixed-wrist multi-axis marked sphere reorientation

With the wrist fixed, rotate the free marked sphere +90 degrees around palm-local Y, then +90 degrees around palm-local X from that pose, then return to its exact initial orientation. Maintain hand contact and avoid any external support throughout; stabilize each ordered checkpoint with at least two fingertips.

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

`solution/wuji/trajectory.npz` (165 x 26 rows, `hand` = `wuji`, sha256 `7d12c7e2...`) completes the three ordered
orientation stages and the terminal hold with the Wuji Hand 2.2 (success at control 165, the last row; float32-rounded
rows also succeed at control 165). Wrist targets stay at the locked pose; only Wuji finger position targets change.
Margins are thin on two invariants: peak object speed 10.5 (limit 12) during a fast spin of the 5.7 g sphere, and
object displacement 0.0615 m (limit 0.07 m); force 2.2 N (limit 80 N). Replays are bit-deterministic, so the margins
matter only if the scene changes. The generator packages it as `solution/wuji/` of both task directories, and the
oracle uses it when the run selects the Wuji hand. `tools/wuji_gen.py` (authoring only, never copied into a task) is a
physics-shooting controller (cross-entropy search over Wuji finger targets on separate MjData copies of the task's
model, two deterministic phases) that rewrites the identical archive in about 3.5 min.
Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/essential_cube_reorient/`.
