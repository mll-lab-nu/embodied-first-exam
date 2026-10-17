# envelope_letter_insert (T38, DexHand wave 2, arm rig and lip from wave 3)

Authoring notes for the DexHand family made from scene T38 "Put a letter into an envelope"
(`robot_coding_bench/scripts/scene_expansion/repairs/envelope_meta_delivery/contact_v2_trajectory_r1`, a kinematic
demo). Here the letter moves only through contact with a dexterous hand (Sharpa Wave by default, Wuji Hand 2.2
selectable) on the right arm of the Tianji Marvin dual-arm robot (`scripts/dexhand/shared/arm_rig.py`, the frozen
pot_shelf_transfer Marvin; robot id `marvin-bimanual-sharpa-wave`). Wave 3 (2026-10-15): the robot arm replaces the
wave-2 six-axis wrist stage, and the envelope mouth starts closed as in the source scene (wave 2: lip parted 0.45 rad).

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: desk, envelope pocket, letter, Marvin stand + arms with the hands (`arm_rig.mount_marvin`; `rig: floating` builds the wave-2 wrist stage for authoring) |
| `checker.py` | ordered stages, released hold and fail-fast invariants, from simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4) incl. `snapshot`/`restore` for authoring search |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), optional mp4 |
| `task.json` | frozen instance: geometry, thresholds, cameras, initial targets per hand |
| `assets/` | `letter.png` (the scene's project-original letterhead texture) + `manifest.json` (sha256) |
| `demo.py` | authoring controller (not shipped) on the floating wrist stage (`tools/floating_task.json`) |
| `tools/arm_port.py` | authoring (not shipped): follows the floating oracle's hand-root poses with the right arm (IK + joint integral) and writes `solution/trajectory.npz` |
| `tools/floating_task.json`, `tools/floating_oracle.npz` | authoring inputs: the floating-stage instance and its oracle rows |
| `tools/check_robot_furniture.py`, `tools/tri_box.py`, `tools/clearance.py`, `tools/check_static_exact.py` | stand check (not shipped): every robot geom vs every static furniture geom at reset and over the oracle (hull distance, exact triangle-vs-box test, vertex clearance, floor height) |
| `tools/robot_contacts_audit.py` | contact audit (not shipped): active contacts per geom pair over every substep (robot self-contacts, arm/stand/parked hand vs furniture or objects) |
| `tools/make_negatives.py` | authoring evidence: nop, truncations, one row short, early release, envelope shove (+ then oracle) (not shipped) |
| `tests/test_envelope_letter_insert.py` | authoring tests (oracle x2 + float32, nop, truncations, envelope shove, wall pass-through + slab guard, robot contact, forged/bad archives, Wuji nop) |
| `presentation.py`, `studio_renderer.py` | PR film: export exact native poses, render with Blender 4.5.3 (Eevee), encode (not shipped) |

## Modelling choices (all passive, contact only)

- Layout, dimensions and colours from the approved T38 scene: desk top z = 0.70 m (0.60 x 0.80 m), DL envelope
  110 x 220 mm centred at (0.48, 0.16) with the mouth on its +X long edge and the 30 mm open flap on the desk, A4 letter
  folded in thirds (99 x 210 mm) at (0.48, -0.14).
- Letter: one free rigid card, 2 mm thick, 5 g (A4 at 80 g/m2), whose two long edges are rounded (capsules: the folds of
  the tri-fold) so it rides over the open flap. Paper bending is not simulated.
- Envelope: one free rigid pocket, 6 g: back and front walls (0.8 mm) 4 mm apart, 3 mm side seams and 4 mm bottom seam as
  solid walls (the side seams narrow to nothing over the last 10 mm before the mouth, like a wallet envelope's
  tapered side flaps: a small entry funnel), the open flap as a thin wedge lying on the desk, and a 30 mm mouth lip that is a passive elastic hinge
  (stiffness 0.001 N m/rad, range 0..1.2 rad). It starts closed (0 rad, resting on its lower stop, flush with the
  front wall) like the source T38 start, whose mouth is parted (6 mm) only during the prescribed insertion and relaxes
  to 0.3 mm at the end. The modelled walls are 4 mm apart (the cavity the rigid 2 mm letter card needs; the source's
  paper walls are 0.2 mm apart), so the closed mouth admits the letter's rounded leading fold: in the oracle the lip
  never opens (max 0.0 rad). A fingertip or the letter can lift the lip; it springs back when released. (Wave 3
  first tried a lip pre-parted 6 mm; the closed start is the source start and needs no parting in this model.)
- Friction: paper 0.35, desk 0.5, fingertip pads 1.5 (MuJoCo max rule). Paper geoms use `solmix = 20` so the paper's stiff
  contact dominates the soft elastomer fingertip pads (otherwise a pad sinks through the 2 mm letter onto the desk).
- Robot: Marvin stand at (1.15, -0.25, 0.10) m facing -X (beyond the desk's +X end, beside the envelope mouth); the rig's
  floor convention (floor = base_z - 0.1) puts the base plate on the floor, and its 0.79 m footprint clears the desk's
  +X legs (x 0.73) by 6 mm (exact triangle-vs-box check, `tools/check_robot_furniture.py`); right arm active,
  left arm parked (`arm_rig.PARK`). Rows: 14 arm joint targets, then the left and the right hand's finger targets
  (58 Sharpa / 54 Wuji). The arm, the stand and the parked hand touching the letter or the envelope fails fast
  (`robot_arm_contact`). Both hands start from the same arm pose (the floating oracle's start pose of the hand root).

## Verdict (see `task.json` `instruction` for the agent-facing text)

Letter corners (centre plane) in the envelope frame; mouth line x = 55 mm.
1. `letter_at_mouth`: both leading corners >= 10 mm past the mouth line, |y| <= 107.6 mm, height 1.2..4.4 mm, while both
   trailing corners are still outside the mouth line (the letter enters through the mouth).
2. `letter_inserted`: outermost corner <= 4.95 mm (5 % of 99 mm) beyond the mouth line; all corners |y| <= 107.6 mm,
   x >= -51.6 mm, height 1.2..4.4 mm.
3. `released_hold`: stage 2 with zero hand contacts on letter and envelope (lip included) and both objects at rest
   (<= 0.01 m/s, <= 0.2 rad/s) for 50 consecutive controls. Success ends the episode.

Fail-fast after every 2 ms substep: the letter pressed through an envelope wall, seam or the lip (any of 105 mid-plane
sample points, inset 1 mm from the edges, inside a wall slab; reviewer EL-1) or interpenetrating the envelope by more than
0.7 mm (the oracles' maximum is 0.51 mm), letter/envelope origin below z = 0.698 m, touching the floor, dropped (touching
nothing while the COM falls faster than 0.1 m/s; the oracle's own peak is 0.012 m/s), origin outside the desk
rectangle or above z = 1.00 m, envelope moved > 5 cm or tilted > 0.35 rad, robot arm/stand/parked-hand contact with
the letter or the envelope, unstable physics; budget 6000 controls.

## Authoring controller (`demo.py`) and the arm port (`tools/arm_port.py`)

`demo.py` is closed loop at authoring time (it reads the letter and envelope poses) on the floating wrist stage of
wave 2 (`tools/floating_task.json`): four leveled fingertips press the letter centre and slide it (+X, then +Y) in front
of the mouth; translate/rotate corrections square it; re-grip on the trailing half; feed in 8 mm increments with
lateral/yaw correction until a fingertip touches the lip; lift, move behind the trailing fold edge and push it in under
the closed lip in 5 mm increments, stopping once the letter is inserted with 1 mm margin (`stop_outside_m` 0.004, so
the fingertip does not drag the envelope along); withdraw. With the closed mouth it succeeds after 1,196 controls
(`tools/floating_oracle.npz`).

`tools/arm_port.py` replays those rows on the stage, records the world pose of the hand root (`right_hand_C_MC`) and the
finger targets after every control, and drives the arm task toward them with `arm_ik.track` (damped-least-squares IK
from the measured arm state, joint integral ki 0.25 for servo sag), each pose held for 2 controls, then 300 hold poses;
executed rows are float32-exact. Result: success after 2,346 controls (tracking error mean 0.6 mm / max 17 mm, 0.001 /
0.04 rad), no contact of any arm link, the stand or the parked hand; 100 slack rows -> 2,446 rows. A Wuji Hand 2.2 run
of the same pipeline (floating success after 1,453 controls) did not finish the insertion on the arm, so no Wuji
reference is packaged for the arm rig.

```bash
export DEXHAND_ASSET_DIR=<robot_coding_bench>/images/dexhand/assets/hand
python demo.py --out out/float/trajectory.npz --params '{"stop_outside_m": 0.004}'   # floating oracle (= tools/floating_oracle.npz)
python tools/arm_port.py --float-rows tools/floating_oracle.npz --out solution/trajectory.npz [--write-initial]
python replay.py --task envelope_letter_insert --traj solution/trajectory.npz --out r1.json   # success at 2346
python tools/check_robot_furniture.py --traj solution/trajectory.npz --every 5 --out stand_check.json
python tools/make_negatives.py --out-dir out/negatives
python -m pytest -q tests
# film: python presentation.py export --trajectory solution/trajectory.npz --export out/film --stride 8
#       BLENDER=<blender 4.5.3> python presentation.py render --export out/film --output out/film.mp4 --engine eevee --samples 24
```
