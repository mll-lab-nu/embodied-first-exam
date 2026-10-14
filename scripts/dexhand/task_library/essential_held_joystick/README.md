# Held Joy-Con thumbstick sequence

With the wrist locked, keep the controller steady and move the joystick through left, front, right, back, then center, holding each checkpoint. Checkpoints are joint angles relative to the shell, not world tilt.

## Authoring contract

- `task.json`: canonical geometry, initialization, ordered predicates and safety bounds.
- `scene.py`: task-owned scene and contact-feature entry point.
- `assets/`: object meshes, textures, license records and checksums in `manifest.json`.
- `render.json`: task camera and presentation profile.

Edit this folder for task-specific work. Common hand physics, replay, grading and render utilities remain in `shared/`.
Run `python3 scripts/dexhand/sync_essential_catalog.py` and then `python3 scripts/dexhand/generate.py --refresh-manifest`.
Generated Harbor modes stay under the repository `tasks/`; do not edit those copies.
Successful authoring actions and videos stay outside task directories and are never packaged as an agent-visible policy.

## Object asset and physical calibration

The object uses Hayley Jacka's [Nintendo Switch right Joy-Con model](https://sketchfab.com/3d-models/nintendo-switch-joycon-a530c8c7eef04235bc865b85dcfc0ac8), licensed under CC BY 4.0 and obtained from the official Allen Institute for AI Objaverse mirror. It is uniformly scaled to 80%: approximately 80.86 mm long, 28.74 mm wide and 24.84 mm deep including the stick and shoulder features. This size adaptation preserves the original shape and proportions.

The shell collision follows a three-piece CoACD convex decomposition of the actual source shell. The visible shell, buttons, labels, screws, rail and LEDs remain separate source meshes with their original PBR textures. The source stick cap and stem are both real moving collision meshes bound to an unactuated two-axis spring gimbal. The source geometry is not grafted over the old square box, and the stick is not represented by an oversized hidden ball. The thumb can manipulate the stick while other fingers retain the shell, then withdraw to permit physical spring return to center.

Only the 28 hand/wrist targets are actuated; all six wrist targets are fixed. The controller has normal gravity and no world fixture, object actuator or replay-time pose assignment. All shell collision pieces participate in contact and support checks. The five ordered cardinal checkpoints and original body stability and terminal speed bounds are unchanged.

`assets/provenance.json` records source licensing, transforms, articulated-part binding and collision decomposition. `assets/manifest.json` lists the offline meshes, textures and credits with checksums. Original GLB and source metadata remain authoring-only; no action policy is packaged.

## Wuji reference solution

`solution/wuji/trajectory.npz` (146 x 26 rows, `hand` = `wuji`, sha256 `eb0c14ee...`) completes all five cardinal
checkpoints and the terminal hold with the Wuji Hand 2.2 (success at control 146, the last row; float32-rounded rows
also succeed at control 146). Wrist targets stay at the locked pose in every row; only Wuji finger position targets
change. Peaks: body rotation 0.071 rad (limit 0.35; 0.24 before 2026-10-14), body drift 0.8 mm (20 mm), force 2.2 N (80 N). The generator
packages it as `solution/wuji/` of both task directories, and the oracle uses it when the run selects the Wuji hand.
Authoring code (never copied into a task): `tools/ctrl.py` places the thumb pad on the stick cap (60 rows; middle and
ring MCP curl to 0.3 rad to prop the shell), `tools/mpc.py` then picks thumb targets by short physics rollouts from
snapshots of the authoring session (`tools/snap.py`), and `tools/wuji_gen.py` runs both and prints the rows' sha256
(`eb51d40e...`). Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/essential_held_joystick/`.
