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
- Robot: Sharpa Wave right hand (default) or Wuji Hand 2.2 (`hands.replace_wave_hands`) on a six-axis wrist stage
  (world-frame x/y/z slides, serial x-y-z hinges; position actuators kp 2500/120). Only these actuators exist
  (`model.nu` 28/26, no mocap, no equality constraints).
- Sheets: three free rigid boxes, 0.210 x 0.148 x 0.0005 m, 2.5 g (real A5 at 80 g/m2; thickness five times real
  paper for contact stability). Friction: sheet-sheet 0.4 (geom), sheet-desk 0.15 and sheet-chrome 0.1 (explicit
  contact pairs).
- Stapler: one free body (base + rigid magazine, 0.120 kg) with a passive head hinge (handle + driver blade,
  0.053 kg): stiffness 1.5 N m/rad, springref -0.15 rad (preload against the open stop), damping 0.03, frictionloss
  0.003, range 0..0.1701 rad. The bottom stop is computed (`scene.head_stop`) so the blade bottom sits 0.2 mm inside
  the top of a three-sheet stack lying on the anvil. Handle-base contacts are excluded (the handle wraps the
  magazine, as in the source).
- Paper stop: a 1 x 24 x 10 mm steel plate behind the anvil (base frame x = 0.052 m). Added part (a common desk
  stapler paper guide): it sets the staple about 10.5 mm from both edges and squares the leading edges when the
  stack is fed against it.

## Simplifications (declared in the instruction)
- Feed: the source film lifts the sheets into the throat. Rigid thin plates cannot be lifted reliably by one hand
  (an edge-overhang pinch was tried in phase A and abandoned), so the reset starts from a settled rest pose with the
  bottom sheet's corner on the anvil mouth and the far edge on the desk (`tools/settle_sheets.py` simulates the
  settle and freezes the poses in `task.json`); the agent slides the stack in.
- No staple: legs, piercing and clinching are not simulated; stage 3 is the head at its bottom stop with the blade on
  the aligned, inserted stack.
- One head hinge: the magazine does not open separately.

## Predicate (checker.py)
Ordered, latched stages from simulator state each control: (1) aligned (corner offsets <= 2 mm in sheet 0's plane,
stacked 0.25-1.5 mm apart, sheets 0-1 and 1-2 in contact); (2) staple point inside every sheet 3-30 mm from both edges
of a corner and 0-6 mm below every sheet mid-plane; (3) head within 0.01 rad of the bottom stop with the blade on the
top sheet; (4) head <= 0.02 rad, no hand contact with sheets or stapler, sheet COM speeds <= 0.02 m/s for 50
consecutive controls -> success (ends the episode). Fail-fast after every 2 ms substep (permanent): sheet centre
below 0.77925 m or a corner below 0.765 m, a sheet centre off the desk or out of the workspace box, a sheet or the
stapler touching the floor or a desk leg, a contact-free object falling faster than 0.2 m/s (no catch window), the
stapler displaced > 3 cm or tilted > 0.26 rad, unstable physics, 6000 controls. `state_sha` hashes the integration
state, the checker state, the non-prose `task.json` keys and the hand.

## Reference solutions
`demo.py` is the authoring controller (closed loop on `Session` state, recorded as open-loop rows; motor targets
with a gravity feed-forward only): a two-fingertip rake (index and pinky spread, pointing down, 0.3 mm above the desk;
Wuji: 0.7x abduction spread, 0.4 mm into the desk) pushes the sheets' +x edges toward -x until the stack corner
meets the paper stop and the edges are flush, presses 3 mm further, lifts off, then index and middle fingertips press
the handle 3 cm in front of the base origin down to the bottom stop, hold 15 controls, release and withdraw; 200 hold
rows follow success as slack.

```bash
cd scripts/dexhand/families/paper_staple
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand MUJOCO_GL=egl
python demo.py --out out/trajectory.npz               # Sharpa: success at control 746 of 946 rows
python demo.py --hand wuji --out out/wuji.npz         # Wuji: success at control 925 of 1125 rows
python replay.py --task paper_staple --traj solution/trajectory.npz --out out/r1.json   # x2, identical state_sha
python -m pytest -q tests/test_paper_staple.py
```
`solution/trajectory.npz` (sha256 a96a594d...) and `solution/wuji/trajectory.npz` (sha256 36179146...) are those
rows (sidecar files of `demo.py` are not part of the solution). The open-loop rows are deterministic but sensitive to
the rake height (+1 mm on every wrist z target fails the squaring); a closed-loop agent can watch the edges.
