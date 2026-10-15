# envelope_letter_insert (T38, DexHand wave 2)

Authoring notes for the DexHand family made from scene T38 "Put a letter into an envelope"
(`robot_coding_bench/scripts/scene_expansion/repairs/envelope_meta_delivery/contact_v2_trajectory_r1`, a kinematic
demo). Here the letter moves only through contact with a dexterous hand (Sharpa Wave by default, Wuji Hand 2.2
selectable) on the six-axis wrist stage used by `assemble_hamburger`.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: desk, envelope pocket, letter, hand on the wrist stage (`hands.replace_wave_hands` for Wuji) |
| `checker.py` | ordered stages, released hold and fail-fast invariants, from simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4) incl. `snapshot`/`restore` for authoring search |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), optional mp4 |
| `task.json` | frozen instance: geometry, thresholds, cameras, initial targets per hand |
| `assets/` | `letter.png` (the scene's project-original letterhead texture) + `manifest.json` (sha256) |
| `demo.py` | authoring controller (not shipped): produces `solution/trajectory.npz` |
| `tools/make_negatives.py` | authoring evidence: nop, truncations, partial insertion, knock-offs (not shipped) |
| `tests/test_envelope_letter_insert.py` | authoring tests (oracle x2 + float32, nop, truncations, knock-off, wall pass-through, forged/bad archives, Wuji) |
| `presentation.py`, `studio_renderer.py` | PR film: export exact native poses, render with Blender 4.5.3 (Eevee), encode (not shipped) |
| `solution/wuji/trajectory.npz` | Wuji Hand 2.2 rows from the same controller (`demo.py --hand wuji`) |

## Modelling choices (all passive, contact only)

- Layout, dimensions and colours from the approved T38 scene: desk top z = 0.70 m (0.60 x 0.80 m), DL envelope
  110 x 220 mm centred at (0.48, 0.16) with the mouth on its +X long edge and the 30 mm open flap on the desk, A4 letter
  folded in thirds (99 x 210 mm) at (0.48, -0.14).
- Letter: one free rigid card, 2 mm thick, 5 g (A4 at 80 g/m2), whose two long edges are rounded (capsules: the folds of
  the tri-fold) so it rides over the open flap. Paper bending is not simulated.
- Envelope: one free rigid pocket, 6 g: back and front walls (0.8 mm) 4 mm apart, 3 mm side seams and 4 mm bottom seam as
  solid walls (the side seams narrow to nothing over the last 10 mm before the mouth, like a wallet envelope's
  tapered side flaps: a small entry funnel), the open flap as a thin wedge lying on the desk, and a 30 mm mouth lip that is a passive elastic hinge
  (stiffness 0.001 N m/rad, rest angle 0.45 rad: the mouth is held parted, range 0..1.2 rad). A fingertip or the
  letter can lift the lip; it springs back when released.
- Friction: paper 0.35, desk 0.5, fingertip pads 1.5 (MuJoCo max rule). Paper geoms use `solmix = 20` so the paper's stiff
  contact dominates the soft elastomer fingertip pads (otherwise a pad sinks through the 2 mm letter onto the desk).
- Wrist stage: origin (0, 0, 0.40) m; hand mount quat (0, 0, 1, 0): at zero rotation the fingers point down, the palm
  faces -X (towards the mouth), the thumb side is +Y. Same stage, gains and start targets for both hands.

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
rectangle or above z = 1.00 m, envelope moved > 5 cm or tilted > 0.35 rad, unstable physics; budget 6000 controls.

## Authoring controller (`demo.py`)

Closed loop at authoring time (it reads the letter and envelope poses), recorded as open-loop rows: four leveled
fingertips press the letter centre and slide it (+X, then +Y) in front of the mouth; translate/rotate corrections square
it; re-grip on the trailing half; feed in 8 mm increments with lateral/yaw correction until a fingertip touches the
lip; lift, move behind the trailing fold edge and push it in under the parted lip in 5 mm increments; withdraw. 100
hold rows are appended after the last executed row (slack). The friction transport is chaotic (stick-slip), but the
later closed-loop feed, the seam funnel and the parted lip make the recorded rows robust: 40/40 replays with i.i.d.
row noise up to 1e-4 succeed (3e-4: 1/10). `--hand wuji` runs the same controller for Wuji Hand 2.2 (vertex-based
fingertip geometry, slip-corrected transport legs, wedge-following push height): success after 1,488 controls, kept as
packaged as `solution/wuji/trajectory.npz` (the envelope is pushed ~3.7 cm of the allowed 5 cm; 11/12 noisy replays
succeed).

```bash
# film: python presentation.py export --trajectory solution/trajectory.npz --export out/film --stride 4
#       BLENDER=<blender 4.5.3> python presentation.py render --export out/film --output out/film.mp4 --engine eevee --samples 32
export DEXHAND_ASSET_DIR=<robot_coding_bench>/images/dexhand/assets/hand
python demo.py --out out/oracle/trajectory.npz        # rows + .live.json / .phases.npz evidence; copy the npz to solution/
python demo.py --hand wuji --out out/wuji/trajectory.npz
python replay.py --task envelope_letter_insert --traj solution/trajectory.npz --out r1.json
python tools/make_negatives.py --out-dir out/negatives
```
