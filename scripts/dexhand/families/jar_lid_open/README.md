# jar_lid_open: authoring notes

Physical DexHand version of scene T14 "Open a jam jar" (scene-expansion catalog; the approved film is a kinematic
demo with prescribed lid motion). Here a dexterous hand on the right arm of a Tianji Marvin robot unscrews, lifts and
sets aside the lid in physics; only the 58 (Sharpa Wave) or 54 (Wuji Hand 2.2) motor targets of the two 7-DoF arms
and the two hands are commanded (the left arm stays parked).

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: worktop, free jar and lid with the contact-only lug thread, the Marvin rig (`shared/arm_rig.py`, Wuji via `hands.py`) |
| `checker.py` | strict verdict: ordered stages, terminal hold, fail-fast invariants (evaluated after every physics substep) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), optional mp4 with a status overlay |
| `task.json` | frozen instance (geometry, robot base, physics step, reset targets per hand, task text) |
| `assets/` | visual jar meshes and the printed label copied byte for byte from the T14 build (`manifest.json`, sha256-checked at build) |
| `solution/trajectory.npz` | Sharpa Wave witness on the arm (1,159 rows, success after 1,009) |
| `solution/wuji/trajectory.npz` | Wuji Hand 2.2 witness on the arm (1,242 rows, success after 1,097); packaged as the per-hand oracle `solution/wuji/` of both modes |
| `tools/arm_port.py` | authoring only: records the wave-2 floating-stage witness's hand poses, sets the arm start pose and tracks those poses with the arm (`shared/arm_ik.py`), re-timed for the arm |
| `presentation.py`, `studio_renderer.py` | authoring only: exact native pose export of a successful replay and the Blender 4.5.3 Cycles studio film (T14 film materials, lights and camera direction) |
| `tests/test_jar_lid_open.py` | authoring tests (`python -m pytest tests/test_jar_lid_open.py` or `python -m unittest` from `tests/`) |

## Modelling choices

- Rig (wave 3): the Tianji Marvin stand with two 7-DoF arms (`shared/arm_rig.py`: pot_shelf_transfer's robot, kp 700,
  kv 48, no gravity compensation) at base (-0.56, 0.08, 0), facing +x; the right flange carries the working hand under
  the fixed body `wrist_stage` (the checker's hand root), the left arm is parked at `arm_rig.PARK` with its hand open.
  Both hands and the arm links count as robot for every contact rule. The Sharpa tweaks of wave 2 (fingertip friction
  1.5, dissipative finger velocity feedback -0.9) are applied before mounting, so both Waves carry them. Wuji Hand
  2.2 replaces both Waves under the same flange mounts via `hands.replace_wave_hands`.
- Placement: the scene keeps the T14 objects and their relation, with the worktop raised to a table height for the
  robot (top z = 0.75, was 0.30 on the floating stage) and the jar at (-0.22, -0.08), 0.34 m in front of the shoulders;
  the lid's set-aside spot then stays inside the right arm's reach with the wrist clear of the worktop.
- Stand clearance (exact check, `stand_check` in the wave-3 status): the floor is 0.1 m below the stand origin (the
  stand's plate rests on it) and the worktop is 1.16 m wide (|y| <= 0.58) so its legs stand outside the stand's
  floor plate (x <= -0.167, -0.313 <= y <= 0.473); no robot collision or visual geom overlaps the worktop, its legs or
  the floor at reset or during either oracle (only fingertip pads touch the worktop while the lid is set down).
- Controllers: the arm witnesses track the hand-root poses of the accepted wave-2 floating-stage witnesses
  (`tools/arm_port.py`: closed-loop IK from the measured arm state with a joint integral for servo sag). The unscrew
  and carry are re-timed 2x slower and the grip turns 0.08 rad further about the jar axis (the arm lags the stage's
  fast wrist turn); everything else follows the old hand path. Sharpa uses one continuous turn; the Wuji witness
  (weak servos, kp 0.2-0.7 N m/rad) keeps its two regrasp strokes.
- Jar: free rigid body, 550 g (glass plus jam; the jam is not simulated), 67 mm body, 110 mm tall; collision is a body
  cylinder, a shoulder and a finish (neck) cylinder, and twelve 1.5 mm glass pads on the base ring (friction 0.8 on
  the worktop, which resists about 0.13 N m of twisting torque by weight alone). Visuals: the T14 revolved glass mesh,
  printed label and jam fill.
- Lid: free rigid body, 32 g steel, 64.8 mm; collision is the top panel, a 24-segment skirt ring, a sealing liner that
  rests on the rim, and four inward lugs (3.0 x 2.6 x 1.6 mm).
- Thread (lug closure): four inclined glass ramps, each built from box segments: a 1.0 rad run that rises 3 mm
  counter-clockwise of the seated lug and a 0.2 rad lead that drops 1.5 mm clockwise of it (turning clockwise jams the
  lug against the lead and presses the liner onto the rim). Seated lugs sit 0.3 mm under the ramps, so the closed lid
  cannot be lifted (verified: 40 N pull with the jar pinned lifts it by 0.3 mm). After a 1.049 rad counter-clockwise
  turn the lugs pass the ramp ends into the gaps and the lid lifts off freely until the lugs reach the next ramp's
  lead end at 1.261 rad (turned further without lifting they run into the next ramp). The lugs have 0.8 mm radial play
  to the glass finish (neck contact radius 28.3 mm): with 0.1 mm play a slightly tilted lid bound on the neck like a
  jammed drawer and could not be lifted. The ramps collide only with the lugs (collision bit 2): they are enclosed by
  the steel skirt, and this keeps a compliant fingertip pad pressed into the thin skirt from touching them. Box
  segments are used instead of convex mesh wedges because thin mesh-on-box contacts let a lug slide through.
- Lightly closed lid (as in the T14 source): no vacuum, seal adhesion or preload torque.
- State hash: `state_sha` covers the MuJoCo integration state, the verdict state and the physics/predicate parameters of
  `task.json` (never its prose), plus the hand.
- Physics: MuJoCo 3.4.0, 2 ms steps, implicitfast, elliptic cones, 80 iterations, multi-CCD, Sharpa impratio 10.
  Thread contacts use solref (0.004, 1), solimp (0.98, 0.999, 0.0001).

## Verdict (exact predicate)

Stages (latched in order):
1. `lid_unscrewed`: while the lid origin is less than 6 mm above its seated height and within 4 mm of the jar axis
   (jar frame), the unwrapped counter-clockwise lid-vs-jar turn (updated after every substep) reaches 1.049 rad.
2. `lid_lifted_clear`: then the lowest point of the lid skirt is more than 30 mm above the jar rim.
3. `lid_set_aside`: then for 50 consecutive controls (1 s): lid touches the worktop, not the hand, not the jar; lid tilt
   <= 0.15 rad; lid centre >= 90 mm horizontally from the jar axis; lid speed <= 0.02 m/s and angular speed <= 0.3 rad/s;
   jar touches the worktop, not the hand; jar tilt <= 0.10 rad; jar speed <= 0.02 m/s. Success ends the episode.

Fail-fast (after every 2 ms substep, permanent): `jar_tipped` (tilt > 15 deg), `jar_slid` (> 30 mm from its reset
position), `jar_lifted` (> 15 mm), `lid_knocked_off` (lid touches the worktop before stage 2), `lid_dropped` (the lid touches
nothing while its centre of mass moves down faster than 0.3 m/s - no catch window - or moves down faster than
1.0 m/s at any time), `lid_off_table` / `jar_off_table` (floor contact, origin below the worktop
top by 5 mm, or outside the worktop footprint), `object_left_workspace`, `lid_forced_through_thread` (the lid leaves the
thread zone upward while its lugs are not in a ramp gap, +-0.03 rad), `left_arm_contact` (the parked left arm or left hand touches the jar or the lid), `unstable_physics`, `episode_budget` (3000 controls).

## Evidence commands

```bash
export DEXHAND_ASSET_DIR=<checkout>/images/dexhand/assets/hand MUJOCO_GL=egl
python tools/arm_port.py poses --hand sharpa --old <wave-2 jar_lid_open folder> --out out/poses_sharpa.npz
python tools/arm_port.py ready --hand sharpa --poses out/poses_sharpa.npz        # initial_targets in task.json
python tools/arm_port.py author --hand sharpa --poses out/poses_sharpa.npz --slow 2 --extra 0.08 --slow-end 480 \
    --out out/jar.npz                                    # regenerates solution/trajectory.npz
python tools/arm_port.py author --hand wuji --poses out/poses_wuji.npz --slow 2 --extra 0.08 --slow-end 480 \
    --out out/wuji.npz                                   # solution/wuji/trajectory.npz
python replay.py --task jar_lid_open --traj solution/trajectory.npz --out out/r1.json   # twice: same state_sha
python replay.py --task jar_lid_open --traj solution/trajectory.npz --video out/jar.mp4 --fps 25 --width 1280 --height 720
```

The authoring evidence (fresh-replay JSONs, negative variants, Harbor trials, preview videos, frames) is kept with the
review records outside the repository.
