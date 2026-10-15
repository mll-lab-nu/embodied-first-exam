# jar_lid_open: authoring notes

Physical DexHand version of scene T14 "Open a jam jar" (scene-expansion catalog; the approved film is a kinematic
demo with prescribed lid motion). Here a dexterous hand unscrews, lifts and sets aside the lid in physics; only the
28 (Sharpa Wave) or 26 (Wuji Hand 2.2) motor targets of the hand and its six-axis wrist stage are commanded.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: worktop, free jar and lid with the contact-only lug thread, hand on the wrist stage (`hands.py` swaps in Wuji) |
| `checker.py` | strict verdict: ordered stages, terminal hold, fail-fast invariants (evaluated after every physics substep) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), optional mp4 with a status overlay |
| `task.json` | frozen instance (geometry, physics step, reset targets per hand, task text) |
| `assets/` | visual jar meshes and the printed label copied byte for byte from the T14 build (`manifest.json`, sha256-checked at build) |
| `solution/trajectory.npz` | Sharpa Wave authoring witness (825 rows, success after 675) |
| `solution/wuji/trajectory.npz` | Wuji Hand 2.2 witness (905 rows, success after 755); packaged by the generator as the per-hand oracle `solution/wuji/` of both modes |
| `grasp.py`, `demo.py` | authoring only: fingertip grasp IK and the closed-loop scripted controller recorded as open-loop rows |
| `presentation.py`, `studio_renderer.py` | authoring only: exact native pose export of a successful replay and the Blender 4.5.3 Cycles studio film (T14 film materials, lights and camera direction) |
| `tests/test_jar_lid_open.py` | authoring tests (`python -m pytest tests/test_jar_lid_open.py` or `python -m unittest` from `tests/`) |

## Modelling choices

- Controllers: Sharpa uses one continuous wrist turn (its compliant pads grip well). The Wuji servos are weak
  (kp 0.2-0.7 N m/rad, 0.3-0.6 N m caps), so its witness commands fingertip targets 20 mm inside the skirt as a grip
  force, turns in two regrasp strokes and regrasps lightly before lifting.
- Rig: one Sharpa Wave on the six-axis wrist stage used by `assemble_hamburger` (same joints, ranges, gains, force
  bounds), mounted palm-down (`quat 0.7071 0 0.7071 0`) with the stage origin about 4 cm below the palm, so
  `wrist_rz` turns the hand about a vertical axis near the grasped lid. Wuji Hand 2.2 replaces the Wave under the same
  wrist stage via `hands.replace_wave_hands`; its reset is the neutral pose (all finger targets 0, inside the ranges).
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
thread zone upward while its lugs are not in a ramp gap, +-0.03 rad), `unstable_physics`, `episode_budget` (3000 controls).

## Evidence commands

```bash
export DEXHAND_ASSET_DIR=<checkout>/images/dexhand/assets/hand MUJOCO_GL=egl
python demo.py --out out/jar.npz                          # regenerates solution/trajectory.npz bit for bit
python demo.py --hand wuji --angles 140 30 -10 -50 --squeeze 0.02 --joint-squeeze --ratchet 0.9 --twist-steps 60 \
    --height 0.004 --regrasp-before-lift --turn 1.07 --lift-squeeze 0.010 --out out/wuji.npz   # solution/wuji/trajectory.npz
python replay.py --task jar_lid_open --traj solution/trajectory.npz --out out/r1.json   # twice: same state_sha
python replay.py --task jar_lid_open --traj solution/trajectory.npz --video out/jar.mp4 --fps 25 --width 1280 --height 720
```

The authoring evidence (fresh-replay JSONs, negative variants, Harbor trials, preview videos, frames) is kept with the
review records outside the repository.
