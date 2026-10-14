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
