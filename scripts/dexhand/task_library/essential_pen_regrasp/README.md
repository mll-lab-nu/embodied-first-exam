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
