# Multi-turn encoder knob with fixed-wrist finger gait

Keep the wrist fixed. Rotate the rotary encoder knob to +720 degrees, then reverse to +360 degrees and hold it still. The real encoder cap has its actual rounded outer profile, normal surface friction and bearing resistance, and a passive unlimited-turn hinge. There is no task-object actuator or powered turning assistance. Maintain load-bearing hand contact throughout and perform at least four contact handoffs involving overlapping fingers.

## Real object and physics

The rotating object is a real 3D-printable rotary-encoder cap by Luis Aros Illanes, licensed CC BY 4.0. Its original CAD-like dimensions are interpreted as millimeters and converted to meters: approximately 53.7 mm diameter and 15 mm height. The visible cap and collision hull share the same centered frame and scale. Its convex collision hull approximates the outer profile and omits the mounting bore; there is no hidden 60 mm drum.

An original stationary controller housing provides the shaft, front panel, display recess and four fasteners. The housing uses a box collision approximation with a 2.5 mm visual edge bevel; it never actuates the cap. The hinge has normal bearing friction and damping, is unlimited in angle, and has no object actuator or gearing. Six equality constraints lock the native wrist coordinates. Independent finger pads contact the opposite faces of the thin cap and repeatedly hand off contact to produce the long rotation.

`render.json` specifies the camera and matte polymer/anodized housing presentation. The marker is a flush, noncolliding inlay. Asset provenance stays in the authoring manifest; runtime receives only the meshes, panel texture and attribution file.

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

`solution/wuji/trajectory.npz` (1,498 x 26 rows, `hand` = `wuji`, sha256 `50a211ed...`) completes both stages and the
terminal hold with the Wuji Hand 2.2 (success at control 1,498, the last row; float32-rounded rows also succeed at
control 1,498). Wrist targets stay at the locked pose; only Wuji finger position targets change. The index and middle
fingers follow periodic joint-space orbits in antiphase, pressing on the knob's rear rim in turn (overlapping
handoffs); a second orbit turns the knob back. The margin is thin on the terminal window: the final angle 6.243 rad is
0.080 rad above its lower bound (window 6.163..6.403 rad); the stage-1 stop angle 12.556 rad is 0.11 rad inside its
window, and the peak knob speed is 5.6 rad/s (limit 12). Replays are bit-deterministic, so the margins matter only if
the scene or `wuji_reset.json` changes. The generator packages it as `solution/wuji/` of both task directories, and
the oracle uses it when the run selects the Wuji hand. `tools/wuji_gen.py` (authoring only, never copied into a task)
replays the orbit parameters found by a cross-entropy search over gait parameters and rewrites the identical archive.
Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/essential_rotary_gait/`.
