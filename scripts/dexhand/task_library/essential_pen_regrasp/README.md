# Paper Mate palm-to-tripod pen regrasp

With the wrist fixed, move the unsupported pen 30 mm along its initial longitudinal axis relative to the palm, then turn its axis by 45 degrees and hold its marked grip band with thumb, index and middle fingertips. The initial pen rests against the central palm surfaces; the final pen must clear those central palm surfaces. All three named fingertips must contact the marked band. Other finger links may also contribute contact; an exclusive fingertip-only grasp is not required. No table support, other hand or whole-object release is allowed.

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

The writing instrument uses Chad / cpenfold's [Paper Mate Kilometrico model](https://sketchfab.com/3d-models/pen-76d3050b6c2646278feaa28007d180cb), licensed under CC BY 4.0 and obtained from the official Allen Institute for AI Objaverse mirror. The original uncapped body measures 149.954 mm long and 7.787 mm in diameter. This calibrated derivative is 150 mm long and 12 mm in diameter; its cap is removed to expose the writing tip. It is a dimension-adapted mesh, not a claim to retail product dimensions.

A capsule of the same diameter follows the source's straight shaft, with convex collision meshes fitted to the actual writing tip and tail. All three physical parts count toward palm, hand and fingertip contact. Narrow painted rings show the fixed 30 mm wide grip band. The pen starts nearly horizontal with a measured central-palm contact, advances along its initial axis, and finishes with the required three named fingertips in that band. Other hand links may contribute contact, and the object receives only gravity and ordinary contact/joint forces.

`assets/provenance.json` records the source, license, axis conversion and size adaptation; `assets/manifest.json` explicitly lists offline runtime assets and their checksums. Source GLB/provenance stay in authoring storage. The runtime package contains converted meshes, textures and credits, with no action policy.

## Wuji reference solution

`solution/wuji/trajectory.npz` (1,571 x 26 rows, `hand` = `wuji`, sha256 `ff5cb69c...`) completes both stages
(advance the pen at control 552; turn it into the tripod grip at control 992) and the terminal hold with the Wuji
Hand 2.2 (success at control 1,571, the last row). It starts from the packaged Wuji start (`wuji_reset.json`). Wrist
targets stay at the locked pose; only Wuji finger position targets change. Margins are thin on two bounds: the pen
angle when stage 2 completes is 0.913 rad (stage window 0.65..0.92 rad), and the peak pen speed during the terminal
hold is 0.057 (limit 0.06); the largest object displacement is 39.8 mm (limit 70 mm). Float32-rounded rows do not
complete the terminal hold (no failure; also with up to 200 extra hold rows), so this oracle depends on float64 rows
like the sweep_dustpan Sharpa oracle; the standard oracle submits float64 and replays are bit-deterministic, so the
margins matter only if the scene or `wuji_reset.json` changes. The generator packages it as `solution/wuji/`
of both task directories, and the oracle uses it when the run selects the Wuji hand. Authoring code (never copied into
a task): `tools/beam.py`, a sampling-based beam search over short Wuji finger-target segments executed by the task's
own Session (states are forked only between candidates), and `tools/wuji_gen.py`, which runs its five recorded
searches and rewrites the identical archive (about 12 min with 3 workers).
Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/essential_pen_regrasp/`.
