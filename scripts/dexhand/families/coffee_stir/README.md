# coffee_stir (authoring notes)

Physical DexHand version of scene T11 "Mix coffee and milk". The source is the approved kinematic demo
`scripts/scene_expansion/repairs/coffee_tripod/meta_delivery_polish_r1_gravity_trajectory_r1` (workspace-local,
untracked), whose spoon motion and milk field were prescribed; its native model is the coffee-tripod reference
`geometry02-ring-clear/model.xml` (cup/spoon bodies, masses, inertias, frictions, table top). Here a Sharpa Wave
(default) or Wuji Hand 2.2 on the six-axis wrist stage must pick up the teaspoon, stir and put it back; the mug and
the spoon move only through contact and gravity.

## Files

| file | role | in task dirs |
|---|---|---|
| `scene.py` | MJCF: worktop, mug, coffee surface (visual), teaspoon, cameras, hand rig (hamburger wrist stage; `hands.replace_wave_hands` for Wuji) | yes |
| `checker.py` | ordered stages, terminal hold and fail-fast invariants from simulator state | yes |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus exact `snapshot`/`restore`) | yes |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5) | yes |
| `task.json` | frozen instance: poses, thresholds, start targets, exact instruction text | yes |
| `assets/` | approved T11 refined visual meshes `cup.obj`, `spoon.obj` + `manifest.json` (sha256, checked at every build) | yes |
| `instruction/`, `README.task.md` | instruction and README bodies for both modes | rendered |
| `solution/trajectory.npz` | Sharpa reference rows for both modes (1,265 rows; success after 1,165 controls) | yes |
| `tools/demo.py` | authoring controller (plus `--variant drop/midair` negative examples) | no |
| `tools/knock.py` | knock-off negative example | no |
| `tools/preview.py` | 1280x720 MuJoCo preview film with the verdict overlay | no |
| `tools/presentation.py`, `tools/studio_renderer.py` | exact-pose export and Blender 4.5.3 studio film in the T11 look | no |
| `tests/test_coffee_stir.py` | 16 authoring tests | no |

## Modelling choices and simplifications

- Geometry and masses from the T11 native model: mug 300 g (source inertia), 57/50 mm radii, 100 mm tall, 8 mm
  floor, handle along +x; teaspoon 35 g (source inertia), shaft capsule r = 2.7 mm, 181.7 mm reach; worktop top at
  z = 0.75 m; mug axis at (0.48, 0.015). Friction: mug/worktop 0.6, steel 1.0, Sharpa fingertips 1.5 (hamburger rig).
- Visual meshes: the approved refined T11 presentation meshes (`refined_geometry.npz` sha256 e06813f4..., exported
  verbatim). Contact geometry: mug floor disk, 32 wall boxes, three handle boxes; spoon bowl as two crossed flat slabs
  (the source used 60 convex pieces; a smooth ellipsoid proxy rocked about the spoon axis without damping and never
  came to rest, so flat slabs were used).
- Coffee and milk are not simulated: a visual surface 64 mm above the mug base (the T11 level after its 23.75 ml of
  milk; the task starts with the milk poured). Mixing is summarised by the checker as revolutions of the bowl below
  that surface (BRIEF: non-simulated media); no drag, buoyancy or fluid forces act on the spoon.
- Start: the spoon rests leaning in the mug (bowl on the floor, handle on the rim), a passively settled pose stored in
  `task.json` `spoon_pos`; the hand starts open about 0.3 m above the mug, fingers down. Identical object reset for
  both hands; a Wuji nop moves nothing.
- Rig: the `assemble_hamburger` six-axis wrist stage (same joints, gains, force limits), ranges set to this scene
  (`task.json` `wrist_range`, world coordinates of the hand mount).
- The film's milky coffee colour, stone counter, cabinetry, tiles and lighting are presentation only.

## Predicate (checker.py)

Stages: (1) bowl submerged (bowl centre and both ends below the coffee surface, above the floor, inside the radius)
while the thumb and another finger touch the spoon; (2) three net revolutions of the bowl centre about the mug's
vertical axis line (world frame), counted only while submerged, >= 8 mm off-axis and with thumb + another finger on
the spoon, increments > 45 deg/control ignored, reset to zero when the bowl leaves the coffee; (3) released spoon
resting in the mug (no hand contact, bowl submerged, spoon-mug contact, spoon and mug COM speed <= 0.02 m/s and
angular speed <= 0.5 rad/s) for 50 consecutive controls. Fail-fast after every 2 ms substep: mug tilt > 10 deg, slide
> 20 mm or lift > 5 mm; spoon touching worktop or floor; spoon touching neither hand nor mug while its COM falls faster
than 0.2 m/s (no catch window); mug on the floor; spoon/mug below the worktop; spoon out of the workspace; fingertip in
the coffee; unstable physics; 3,000-control budget. `state_sha` hashes the integration state, the predicate state,
the physics/predicate parameters of `task.json` (not its prose) and the hand.

## Authoring controller (tools/demo.py, Sharpa)

Thumb-index pinch near the top of the handle found by kinematic IK (thumb pad above, index pad below the handle);
approach sideways, close, raise the pinch over the mug axis so the spoon hangs upright (closed-loop depth correction
puts the bowl centre 37 mm above the mug base), drive the pinch around an 18 mm circle (five commanded turns at 110
controls per turn, radius ramps) so the pendulum-like spoon stirs, lower the bowl to the floor, lean the spoon toward
the rim, open the fingers and withdraw. Wrist rows carry a gravity/bias feed-forward. Recorded rows replay open-loop.

## Evidence commands (from this folder; `DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand`)

```bash
python tools/demo.py --bowl-z 0.037 --radius 0.018 --rows-per-turn 110 --turns 5.0 --kp 0 --kd 0 --out <raw>.npz
#   -> success at control 1,165; solution/trajectory.npz = these rows + 100 copies of the last row
python replay.py --task coffee_stir --traj solution/trajectory.npz --out <r1>.json   # twice: identical state_sha
python tools/demo.py ... --variant drop  --out <drop>.npz     # spoon_dropped at control 1,092
python tools/demo.py ... --variant midair --out <midair>.npz  # spoon_dropped at control 968
python tools/knock.py <knock>.npz                            # cup_moved at control 132
python -m pytest -q tests                                       # 16 tests, about 1.5 minutes
python tools/presentation.py export --trajectory solution/trajectory.npz --export <export-dir> --stride 4
python tools/presentation.py verify --trajectory solution/trajectory.npz --export <export-dir>
BLENDER=<blender-4.5.3> python tools/presentation.py render --export <export-dir> --output <film>.mp4
```

Robustness (authoring): float32-rounded rows succeed (control 1,163); 7/8 replays with Gaussian row noise (0.5 mm
wrist position, 2 mrad wrist angle, 10 mrad fingers) still succeed; constant 4 mm wrist offsets in +x or -y miss the
pinch.
