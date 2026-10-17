# eket closed-loop reference

`eket_ref.npz` is the one reference for both modes of `ikea-eket-i00` (privileged `solution/trajectory.npz`, standard
`solution/oracle_actions.npz`). Its rows are the EXECUTED targets: `data.ctrl` after `rcb_ikea.Session.applied()`. Every row
is within the arm joint-speed limits + 1e-9 of the previous row, starting from the keyframe ctrl, so the clamp never
changes a row on replay. Keys: `ctrl` (70210, 16) float64, `substeps` 4, `timestep` 0.000625, `actuators`.

The physics is the final one: the prism rule, fix 3b dowels, the arm clamp, MuJoCo 3.14.0 with the EPA byte patch, and
numpy SIMD masking.

## Files
- `eket_lib.py`: the session wrapper. It records the executed rows and measures each panel relative to the top from the
  true state (`eket_ops.Measure`). It also has the Jacobian servo (`mj_jacSite` on `left_tcp`, damped least squares,
  increments capped per tick).
- `rec_guide.py`: makes the phase guide's track (`guide.npz`). It replays the original demo WITHOUT the clamp, as the demo
  was made (it passes there), and stores each panel's pose relative to the top on every row. The track is only a target;
  it is never executed.
- `build_ref.py`: the controller. `build_ref.py --out DIR` writes `DIR/ref.npz` and a checkpoint per stage. Use
  `--from STAGE` to search later stages from a checkpoint.

Rebuild: `python rec_guide.py runs/guide.npz && python build_ref.py --out runs/b3` (scene dir on `IKEA_SCENES`, the
shared `rcb_ikea.py` on `PYTHONPATH`, the demo at `EKET_DEMO`, the masking variables set). The result is bit-identical
to `eket_ref.npz`.

## Phases (demo rows; the left arm moves the panels, the right arm holds the top)
| phase | demo rows | gate (eket_ops / success.py) | closed loop |
|---|---|---|---|
| side_a grasp, carry, entry | 0-8913 | side_a_entry: 0.8 mm, 1 deg, top contact, 13 updates | track from 5800 |
| side_a slide | to 10000 | 0.25 mm / 0.1 deg for 25 updates, then < 0.05 mm and < 0.02 deg | goal servo at 10000 |
| release, retreat | 11500-11660 | none | offset ramped out over 400 ticks |
| side_b grasp, carry, entry | 18022-23562 | side_b_entry | track from 18250 |
| side_b slide | to 26000 | as side_a | goal servo at 26000 |
| back carry, regrasp, push | 35409-52260 | back_slide: 0.8 mm, 1 deg, contact with side_a, side_b and top, 1.05 s probe exclusion | track 35650-46300 and 49900-52200; goal servo at 52200 if not yet accepted |
| bottom carry, entry | 56178-62397 | bottom_entry: 0.8 mm, 1 deg, both sides | track from 56400 |
| bottom slide | to 64000 | 0.5 mm / 0.1 deg, 1 s pose window, then < 0.05 mm and < 0.02 deg | goal servo at 64000 |
| releases, retreat, settle | 65346-68906 | released, resting on the table, still after the 1 s hold | offset ramped out |

**Track.** On every tick of a track window, the held panel's pose error against the guide is turned into a TCP twist.
The panel's error twist about its own origin becomes the TCP's twist through the lever arm, and a damped
pseudo-inverse turns it into joint increments. The gain is 0.02 per tick, capped at half the joint limit per tick. The
increments add up in the arm's offset, on top of the demo's rows. This removes the chaos: a 1e-9 change upstream no
longer decides whether a panel enters its keyhole and grooves.

**Goal servo.** At a slide's servo point, if its gate has not accepted, the demo pauses. The same servo then steers the
panel to the gate's goal: position to `goal_in_top_frame`, orientation to identity relative to the top. The gain is
0.02 for the tracks; the goal servos use 0.05 (sides) and 0.03 (bottom). It runs until the gate accepts, at most 4000
ticks. The correction stays in the arm's offset. Once the arm's gripper is open again, the offset is ramped to zero over
400 ticks.

## Searches
| run | change | result |
|---|---|---|
| demo, clamped | none | side_a accepted; side_b_slide never accepted. The panel stays at 0.07 deg, then is dragged off (86 deg). |
| demo, no clamp | none | success (the guide) |
| servo test | side_b goal servo from the clamped demo's row 26000, gains 0.02 / 0.05 / 0.1 | accepted after 99 / 46 / 33 ticks |
| b1 | goal servos only | side_a passes (575 servo ticks); side_b_entry is never accepted (4.8 mm, 1.5 deg off: the panel jams) |
| b2 | + guide tracks, gain 0.05 | sides pass; the back jams. Its goal servo diverges: the offset runs away. |
| b2k = reference | + guide tracks, gain 0.02 | all seven gates and the terminal rules; servo ticks: side_a 583, side_b 269, back 0 (accepted at demo row 51738), bottom 452 |

The servo ticks are inserted rows, so the reference is 1304 rows longer than the demo.

## Verification (2026-10-16)
- **Reference.** `eket_ref.npz`: sha256 `a55a377945679794cfa50127e88c628e0e38cbffb095b5dbc9194ba0d74336a5`, 70210 rows (175.5 s
  of simulated time). 0 rows over the limit + 1e-9; the largest step is 1.000000000000038 x the limit (a clamped step).
  Rebuilt twice from `build_ref.py`, bit-identical.
- **Fresh replays.** `final_check()` passes. End state `0a38212b16dc6143…`, settled `fe1fe33a3ad667c0…`. The hashes match
  in 2 processes on vast (EPYC, patched venv, masking) and on Quest (Xeon Gold 6230R, SIF 98fa2d3). Max part depth
  4.949 mm, no breakdown.
- **Timing.** One unobserved replay takes 518 s on Quest (3.6 % of the 14400 s budget) and ~250 s on vast.
- **Harbor on ws2** (image 0.2.0 98fa2d354818):
  - h1_priv_oracle: 1, deterministic, replays 323 s. h1_priv_nop: 0.
  - h1_std_oracle: 1, live_success, live_matches_replay, rows_match, n_clipped 0 on all 18 calls. h1_std_nop: 0.
- **Stress.** 30 episodes from checkpoints of this reference (10 each of prefix_random, mutate and fast; seeds
  7560000-7560029). Result: 11 CLEAN, 18 VIOLENT (Franka finger-slam forces of 11.6 kN; the hand slew is still off), 1
  BREAKDOWN.
  - The BREAKDOWN is `eket__prefix_random__s7560018`: random arm motion from the checkpoint at row 21060. The local
    top/side_a contact created 0.59 J in 0.1 s, with the speed 3.3 m/s and 15 kN triggers. It was confirmed from the birth
    (same end hash).
