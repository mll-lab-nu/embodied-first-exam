# Asset provenance and read-only reuse

The original task folder `scripts/scene_expansion/tasks/coffee_grinder/` and its
entire scene-expansion evidence tree (outside the repository) remain read-only.
The previous top-level T15 report is preserved in this replacement evidence.
`legacy-source-preservation.json` records SHA-256 hashes of all 27 original
source/asset files, excluding Python bytecode. Frozen Robotiq manifests, native
models, successful controls and failed attempts remain historical evidence.

`mechanism.py` is an exact task-owned copy of the original authored geometry;
its source hash is recorded in every new native embodiment manifest. The HARIO
MSS-1DTB-style product references, author-estimated internal geometry and passive
load limitations remain those documented in the original `ASSET_PROVENANCE.md`.
Existing product photographs and manuals are inspection references only and are
not redistributed as textures or geometry. No manufacturer CAD is claimed.

The read-only Sharpa Wave model and STL/OBJ assets are from
`images/dexhand/assets/hand/`, licensed Apache-2.0, Copyright 2025 Sharpa Group.
The unchanged license is copied to `licenses/SHARPA-APACHE-2.0.txt`. All original
hand mesh hashes are retained in native manifests. `hand_models.py` is imported
read-only; the mirror transformation and dissipative feedback convention are
declared in the specification.

Tianji geometry is reused from `images/everyday_dexterity/assets/tianji/` through
the read-only `tianji_model.py`. The bundle records the DexForceAI asset revision
`48317bd8733182f36d306cc2a7a60ae5e47ed2c9` (Apache-2.0) and Genesis inertia revision
`deffbe1685e5ce6aa289efdd541f762f1eb3353f` (MIT), with the public-estimate inertia
caveat. Its two unchanged license files are copied into `licenses/`.

The new `robot.py` and `replay.py` adapt the original task's DLS arm solver and
native rendering logic in this replacement folder. New hand composition,
kinematic planning, staged approach controls, shell audit, limit flag audit and
checkpoint presentation are task-owned. Original end-effector code/assets are
not imported. No Robotiq body or actuator is present in the new native model.

Inspected visual references include the original grinder's
`presentation-v3/presentation-preview.png` and the genuine Sharpa/Tianji
preview of the accepted sweeping delivery (outside the repository).
The exact native failure movies and checkpoint still use verified native
states; no render pose offsets, invented motion or successful result is shown.

The immutable `sharpa_surfaces` v1.1 package is copied into this authoring folder
with its unchanged source profile and Apache-2.0 license. Validated bundle
SHA256 is `121f2866a77a03de2e21c39043afe203260f9fd2cd173376bddbadbd600cadab`;
the root-corrected immutable 133-file manifest SHA256 is
`8542bc5ae0da04423083bc7401f77719c61252b07497d1d46e1fcbf367ce54a1`.
The optional `sharpa_contact_refinement` v1.0 package and license are also copied
unchanged for the measured index-MP/cup discrepancy. Bundle SHA256 is
`97d70d025a768d545d1968a308030a96b94ec5bcf5d108642eecb2da908d141b`, and source/evidence
manifest SHA256 is `bf419626a0bf6217007c1c47984c83e1d6dbfe48d38617872b099ccee8e6b452`.
These are geometry support utilities, not validated grasp controllers or scene
acceptance. The emitted MP recipe remains optional and unapplied to dynamics.
