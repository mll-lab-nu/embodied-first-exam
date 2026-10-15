# `paper_staple` (DexHand plugin family): align and staple three paper sheets

Authoring notes. Generated task pair: `tasks/dexhand-paper-staple-i00-{privileged,standard}`
(`python3 scripts/dexhand/generate.py --only-family paper_staple`).

## Provenance
Scene-expansion scene T36 "Align and staple paper documents" (`scripts/scene_expansion/repairs/
stapler_meta_delivery_polish_r1_trajectory_r1/`, a kinematic demo with prescribed paper, handle and staple motion,
hands omitted). Kept from the source: the desk (top z = 0.78 m), the NOVUS B2 envelope stapler (blue base and handle
shells, anvil plate, outer anvil walls and clinch ramps, rear pivot bracket, magazine sides/floor, front driver guide,
driver blade, return-spring coil, masses), the A5 sheets with printed lines, and the materials' colours.
`tools/export_assets.py` writes the lofted shells and wedge walls from the source's section tables to
`assets/*.obj`; `assets/manifest.json` holds their sha256 and `scene.py` verifies it before building.

## Physical model (what is simulated)
- Robot (wave 3): the Tianji Marvin stand with two 7-joint arms (`scripts/dexhand/shared/arm_rig.py`, the frozen robot
  of `pot_shelf_transfer`; robot id `marvin-bimanual-sharpa-wave`), Sharpa Wave hands on both flanges (default) or
  Wuji Hand 2.2 (`hands.replace_wave_hands` inside `mount_marvin`). The stand origin is at (0.58, -0.66, 0.10)
  (rig convention: its base plate on the floor at z = base_z - 0.1 = 0), heading 135 deg (2.356 rad): the source
  places the robot at the origin facing +x, but from there the right hand cannot reach the stack's far edge (x 0.86 m;
  IK error 0.3 m). Beside the desk's -y edge the stand's 0.79 m square base plate (collision hull of
  `collision_base_link_9`) would enclose the two -y desk legs when facing +y; turned 45 deg it fits between them, and
  every hand pose of the plan stays reachable (wave-3 review PS3-1). Exact stand check (`stand_check` in the wave-3
  status: collision geoms by mj_geomDistance, visual meshes by dense surface samples against every desk box, floor
  plane) at reset and every 5th control of the oracle. The
  right arm does the task, the left arm stays parked. Only these actuators exist (`model.nu` 58/54: 14 arm position
  servos kp 700 / kv 48 without gravity compensation, then the left and the right hand's fingers; no mocap, no
  equality constraints). The right hand mount body is named `wrist_stage` (checker lookups unchanged).
- Sheets: three free rigid boxes, 0.210 x 0.148 x 0.0005 m, 2.5 g (real A5 at 80 g/m2; thickness five times real
  paper for contact stability). Friction: sheet-sheet 0.4 (geom), sheet-desk 0.15 and sheet-chrome 0.1 (explicit
  contact pairs).
- Stapler: one free body at the T36 source pose (base origin (0.575, -0.100, 0.783); base + rigid magazine, 0.120 kg)
  with a passive head hinge (handle + driver blade, 0.053 kg): stiffness 7.0 N m/rad, springref -0.115 rad (preload
  against the open stop), damping 0.05, frictionloss 0.003, range 0..0.1701 rad. Spring torque 0.80 N m at the open
  stop and 2.00 N m at the bottom stop, i.e. about 10 N to start the stroke and 25 N at the bottom stop when pressed
  8.2 cm in front of the hinge (wave 2: 1.5 N m/rad, 3 -> 6 N); the oracle's peak hand force on the handle is 40 N.
  The bottom stop is computed (`scene.head_stop`) so the blade bottom sits 0.2 mm inside the top of a three-sheet
  stack lying on the anvil. Handle-base contacts are excluded (the handle wraps the magazine, as in the source).
- Paper stop: a 1 x 24 x 10 mm steel plate behind the anvil (base frame x = 0.052 m). Added part: the real NOVUS B2
  has no paper guide (retail specifications: 25 sheets, 6.5 cm throat depth, reversible anvil, no stop). It stays
  because squaring needs a vertical counter-face (see Simplifications).

## Simplifications (declared in the instruction)
- Feed: the source film lifts the sheets off the desk into the throat. Kept from wave 2: the reset starts from a
  settled rest pose with the bottom sheet's corner on the anvil mouth and the far edge on the desk
  (`tools/settle_sheets.py`, re-run for the source stapler pose); the agent slides the stack in. Wave-3 evidence
  (the authoring records' `flat_squeeze_test/`, outside the repository): with the source's flat, misaligned
  start, a two-hand fingertip squeeze cannot square or lift the 0.5 mm sheets: the fingertip capsules (radius 8 mm)
  meet a sheet edge 0.25-1.5 mm above the desk at a contact normal 14-33 deg from vertical, so they press the sheets
  down and ride over them (bottom sheet yaw unchanged at -0.036 rad after the squeeze, a 30 mm lift left all three
  sheets on the desk); no part of the Sharpa hand offers a vertical face near the desk (palm and finger meshes are
  sloped there). A desk-edge overhang pinch would need a 0.17-0.39 m slide, a carry and a release with a finger under
  the stack; not attempted tonight.
- Paper stop: kept (see above); without it the squaring would need a vertical counter-face that the hand cannot
  provide on a flat desk.
- No staple: legs, piercing and clinching are not simulated; stage 3 is the head at its bottom stop with the blade on
  the aligned, inserted stack.
- One head hinge: the magazine does not open separately.

## Predicate (checker.py)
Ordered, latched stages from simulator state each control: (1) aligned (corner offsets <= 2 mm in sheet 0's plane,
stacked 0.25-1.5 mm apart, sheets 0-1 and 1-2 in contact); (2) staple point inside every sheet 3-30 mm from both edges
of a corner and 0-6 mm below every sheet mid-plane; (3) head within 0.01 rad of the bottom stop with the blade on the
top sheet; (4) head <= 0.02 rad, no robot contact (hands, arms, stand) with sheets or stapler, sheet COM speeds
<= 0.02 m/s for 50 consecutive controls -> success (ends the episode). Fail-fast after every 2 ms substep (permanent):
sheet centre below 0.77925 m or a corner below 0.765 m, a sheet centre off the desk or out of the workspace box, a
sheet or the stapler touching the floor or a desk leg, a contact-free object falling faster than 0.2 m/s (no catch
window), the stapler displaced > 3 cm or tilted > 0.26 rad, an arm link or the stand touching the desk, stapler or a
sheet (`arm_collision`), unstable physics, 6000 controls. `state_sha` hashes the integration state, the checker
state, the non-prose `task.json` keys (including `marvin` base pose and `initial_targets`) and the hand.

## Reference solution
`demo.py` is the authoring controller for the arm (closed loop on `Session` state, recorded as open-loop rows): every
control it converts the desired world pose of the right hand mount and the finger targets into right-arm joint
targets (`arm_ik.ArmIK` damped least squares, warm-started, with a joint integral against servo sag) plus a finger
gravity feed-forward. Plan: a two-fingertip rake (index and pinky spread, pointing down, 0.3 mm above the desk) pushes
the sheets' +x edges toward -x until the stack corner meets the paper stop and the edges are flush, presses 3 mm
further, lifts off; then the straight index and middle fingers (pointing down, load along the fingers) press the
handle 3 cm in front of the base origin to the bottom stop, hold 15 controls, release and withdraw; 200 hold rows
follow success as slack. Tracking error of the hand mount: 2.2 mm mean, 13 mm max (fast transfer moves), < 1 mm
during the rake push and the press.

```bash
cd scripts/dexhand/families/paper_staple
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand MUJOCO_GL=egl
python demo.py --out out/trajectory.npz               # Sharpa: success at control 742 of 942 rows
python replay.py --task paper_staple --traj solution/trajectory.npz --out out/r1.json   # x2, identical state_sha
python -m pytest -q tests/test_paper_staple.py
python presentation.py export --traj solution/trajectory.npz --out out/film/export   # Blender film bundle
```
`solution/trajectory.npz` (sha256 ebbf2a6b...) holds those rows (sidecar files of `demo.py` are not part of the
solution). Wuji Hand 2.2: the scene composes on the same arms and a no-op is deterministic, but the same plan fails
(the Wuji fingers fold under the 25 N press and the released head tips the stapler), so no Wuji reference is packaged
in this version.
