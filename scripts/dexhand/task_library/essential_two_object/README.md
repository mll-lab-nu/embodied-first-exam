# Independent walnut rotation and selective release

Keep the wrist fixed. Turn walnut A +90 degrees around palm-local Y, return A to its initial orientation, then release only A into the catch tray. Maintain walnut B at its initial position and orientation throughout. The walnuts, standardized to the same maximum dimension, must never contact one another. Before selective release, keep both objects unsupported by the environment and in load-bearing hand contact. Finally let A settle in the tray while continuing to hold B.

## Real objects and physics

Both objects are authentic closed-shell walnut photogrammetry scans extracted from blenderboom's *Walnuts in a wooden bowl*, licensed CC BY 4.0. A and B are different scan components, uniformly scaled to the same 28 mm maximum bounding-box extent. Their shape ratios and surface geometry remain non-spherical. Their collision geometry is a convex hull of the actual scan with MuJoCo collision support capped at 64 vertices, not a hidden sphere. Concave shell grooves and the lower collision LOD are stated simulation approximations; full scanned visual meshes remain unchanged. The contact LOD avoids dense convex-facet jitter in native MuJoCo without loosening target or static-dwell predicates. Both use the same density and Coulomb friction coefficients. Their colors come from the original UV-mapped scan atlases.

The objects are independent passive free bodies. The ordered requirements remain A +90 degrees, A return, A selective deposit while B preserves its initial pose. Object-object contact is forbidden and the wrist is physically locked. Contact identity is determined from the manufacturer hand body ancestry, including unnamed palm/finger collision meshes. Finger load is the sum of real contact-force magnitudes across that finger's contact manifolds, not the net vector; the 5 mN threshold is applied to this per-finger load. Individual whole-hand contact eligibility and global force bounds retain their original thresholds; a mesh's display name cannot make a real 0.075 N hand contact disappear from the grader.

The fixed collector is positioned under the calibrated release path before reset. Its 220 x 220 x 10 mm receiving slab is represented by a bounded, flat 9 x 9 heightfield with all elevations zero: its top, sides and backing thickness exactly match the non-colliding visible plate. This is a finite solid receiver, not an infinite plane, and the visual duplicate contributes no collision. A 24 ms, critically damped contact response models the compliant receiving surface; the original per-contact load thresholds, 40 mm deposit bound, 0.06 static-speed bound and 25-step terminal dwell remain unchanged. [MuJoCo documents the finite heightfield as a union of triangular prisms](https://mujoco.readthedocs.io/en/stable/XMLreference.html#asset-hfield). It supplies no support during the held phases. Base-color and normal maps are preserved; the derived ORM maps encode the source constant roughness 0.6 and metallic 0, with unit occlusion because the downloaded GLB supplies no AO image.

## Authoring contract

- `task.json`: canonical geometry, initialization, ordered predicates and safety bounds.
- `scene.py`: task-owned scene and contact-feature entry point.
- `assets/`: object meshes, textures, license records and checksums in `manifest.json`.
- `render.json`: task camera and presentation profile.

Edit this folder for task-specific work. Common hand physics, replay, grading and render utilities remain in `shared/`.
Run `python3 scripts/dexhand/sync_essential_catalog.py` and then `python3 scripts/dexhand/generate.py --refresh-manifest`.
Generated Harbor modes stay under the repository `tasks/`; do not edit those copies.
Successful authoring actions and videos stay outside task directories and are never packaged as an agent-visible policy.

## Native physical validation

A full actuator-only replay passes all three ordered stages and the original 25-control static dwell in 408 controls (8.16 seconds). Independent native float64 and float32-wire replays both pass at the same final state fingerprint. The stage transitions occur at controls 47, 160 and 284. Both free walnuts remain passive; there are 28 hand/wrist actuators, six locked-wrist equality constraints, and no object actuator or applied object force. Final A deposit distance is 16.37 mm and B orientation drift is 0.00218 rad. A release uses distal opening while retaining the proximal hand grip, followed by small real ring/pinky target corrections to stabilize B; this is demonstrated by actual contacts rather than object state writes. Successful controller files and movies remain outside the runtime task.

## Wuji reference solution

`solution/wuji/trajectory.npz` (266 x 26 rows, `hand` = `wuji`, sha256 `1dc1d5c8...`) completes the three stages
(rotate walnut A +90 deg about palm Y at control 44, return it at 76, release A into the tray while B stays held at
215) and the terminal hold with the Wuji Hand 2.2 (success at control 266, the last row). It starts from the packaged
Wuji start (`wuji_reset.json`). Wrist targets stay at the locked pose, and walnut B's ring/pinky targets never change
from their reset values. The thinnest margin is discrete: `b_finger_contacts` drops to 1 (the allowed minimum) for a
few substeps in stages 1-2; `a_position_error` peaks at 0.0234 (limit 0.035). Float32-rounded rows do not complete the
release (no failure, stage 3 not reached, also with up to 100 extra hold rows), so this oracle depends on float64
rows like the sweep_dustpan Sharpa oracle; the standard oracle submits float64 and the replays are bit-deterministic.
The generator packages it as `solution/wuji/` of both task directories, and the oracle uses it when the run selects
the Wuji hand. `tools/wuji_gen.py` (authoring only, never copied into a task): physics-shooting MPC for stages 1-2,
then a two-via-point opening of thumb/index/middle for the release; it rewrites the identical archive in about 4 min.
Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/essential_two_object/`.
