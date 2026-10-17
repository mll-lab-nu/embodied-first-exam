# ikea365 closed-loop reference

`ikea365_ref.npz` is the one reference for both modes of `ikea-ikea365-i00` (privileged `solution/trajectory.npz`,
standard `solution/oracle_actions.npz`). Its rows are the EXECUTED targets: `data.ctrl` after
`rcb_ikea.Session.applied()`. Every row is within the arm joint-speed limits + 1e-9 of the previous row, starting from
the keyframe ctrl, so the clamp never changes a row on replay. Keys: `ctrl` (89126, 16) float64, `substeps` 4,
`timestep` 0.000625, `actuators`.

The physics is the final one: the prism rule, the arm clamp, MuJoCo 3.14.0 with the EPA byte patch, and numpy SIMD
masking.

## Files
- `i365_lib.py`: the session wrapper. It records the executed rows and measures from the true state: the screw against
  its seat in member_a (gap, lateral, tilt), the screwdriver tip against the screw axis, and the contact forces. It also
  has Jacobian IK on `left_tcp` / `right_tcp` (`mj_jacSite`, damped least squares).
- `rec_guide.py`: makes the phase guide (`scan_old_noclamp.npz`). It replays the original demo WITHOUT the clamp on the
  PRE-prism scene, where the demo passes all seven operations. It stores the part and TCP poses on every row. The guide
  is only a target; it is never executed.
  - The scene is a scratch copy of the ikea365 scene files of that day ( its `ikea_runtime.py` is older than the
    bit-identical `_cross` speed-up).
  - The guide's sha256 is `e5407a95c852bda1…` (35 MB, not kept in this repository).
  - On the prism scene, even the unclamped demo never seats the screw, so its later part poses are no guide.
- `build_ref.py`: the controller. `build_ref.py --out DIR` writes `DIR/ref.npz` and a checkpoint per stage (A-E). Use
  `--from STAGE --src DIR0` to search later stages from a checkpoint.
  - A resumed build is close to a continuous build, but not bit-identical. After a restore, `mj_forward` refreshes the
    kinematics that the controller reads; in a continuous run they lag one substep. The physics replay of the rows is
    exact in both cases.
  - The reference is a continuous build.
- `check_ref.py REF.npz`: a fresh-process check. It counts rows over the limit, then replays open-loop through
  `rcb_ikea` (the grader's path) and runs `final_check()`.
- `std_agent/controller.py`: the standard agent's first version (phases A-E, unchanged), which this controller builds on.

Rebuild: `I365_GUIDE=runs/scan_old_noclamp.npz python build_ref.py --out runs/r2`. The scene dir goes on
`IKEA_SCENES`, the shared `rcb_ikea.py` on `PYTHONPATH`, the demo at `I365_DEMO`, and the masking variables must be
set. The result is bit-identical to `ikea365_ref.npz` (rebuilt twice).

## Phases (demo rows; the demo is 85296 rows)
| stage | demo rows | what | gate (mechanism.py) |
|---|---|---|---|
| A | 0-41200 | demo rows through the clamp: the left screwdriver unthreads the screw, the right hand parks it, the left lays member_b across, the right brings the screw back to the thread entry | remove (23847), park (24228), cross (33725), return (36942) |
| B | inserted, 7157 ticks | the right hand, still holding the screw at the entry, threads it 7 turns: right j7 at 2.5 rad/s, the TCP lowered by 0.5 mm per turn by IK, then a 0.3 s hold. Gap 4.89 → 1.51 mm, tilt 0.49 deg | none |
| C | 41200-53635 | demo rows, right arm offset by B: joints 1-6 ramped out over 1 s from 0.3 s after its release, j7 keeps the 7 whole turns. Handover of the screwdriver to the left hand | none |
| D | inserted, 6538 ticks | closed-loop screwing (below) | reinstall_same_screw (welds on) |
| E | 63500-85296 | demo rows from the demo's screwdriver 2 cm up; left arm blended onto the demo over 1 s (j7 by whole turns); guide tracks for the grasps | turn_stand, place_bowl, then the terminal rules |

**D, closed loop on the true state.**
1. Lift the screwdriver to 3 mm above the head and centre its tip on the true screw axis (3 IK passes; residual 0.02 mm).
2. Advance the left j7 target at 2.5 rad/s. Once the screw is within 0.6 mm of its seat, the speed drops to 2.0 rad/s.
   - The target's lead over the joint is bounded by the damping lead + 99 N m / kp. This is above the actuator's 12 N m
     force range, so it only bounds the windup.
   - The axial force of the tip on the head is held at 5-15 N: 2 µm IK steps down or up per tick.
   - The tip is re-centred every 40 ticks.
3. Once the screw is within 0.04 mm of its seat, the j7 target follows the joint (q7 + kd·qv/kp, zero actuator torque).
   The mechanism's 0.15 s dwell then accepts the screw, and the welds engage on an unloaded screw.
4. Hold 0.2 s at zero torque, then lift the screwdriver 4 mm straight up.

The decisive change is step 3. The standard agent's version left the spin's stall torque on through the acceptance,
the hold and the lift. That torque twists the freshly welded screw by 4.03 deg relative to member_a, and turn_stand
(max relative angle < 1 deg from its start) is never accepted. The demo itself backs j7 off by 0.1 rad at row 62933
(torque release) just before its acceptance at 63014. E therefore starts after that row, so the demo's slow
post-seat turning (5.3 → 8.2 rad) is never replayed on the welded screw.

**Guide tracks (E).** On each tick of a window, the arm's TCP is steered toward the guide's TCP pose relative to the
object at the same demo row:
- desired = T_obj(now) · T_obj(guide)⁻¹ · T_tcp(guide);
- the gain is 0.02 per tick, capped at half the joint limit per tick, through damped-least-squares IK;
- the increments add up in the arm's offset, which is ramped out over 400 ticks after the gripper opens again.

| window (demo rows) | arm | object |
|---|---|---|
| 66000-69060 | right | member_b (the right grasp that lifts and turns the stand) |
| 71000-73460 | left | member_a (the left takes the turned stand) |
| 77500-79420 | right | bowl (grasp) |
| 79420-83254 | right | member_a (bowl placement on the turned stand) |

The stand moves 2 mm in y during B-D, so the demo's open-loop grasp of member_b lands on member_a (standard agent's
finding). The tracks absorb this. Ablation from the D checkpoint without tracks: it still passes, but the bowl's support
contact is 0.14 N instead of 0.29 N (the gate is 0.1 N).

## Gate metrics of the reference
| operation | accepted (sim s) | metrics |
|---|---|---|
| remove_same_screw | 59.620 | gap 10.01 mm, 9.43 turns |
| park_same_screw | 60.572 | 40.6 mm away |
| cross_members | 84.315 | gap 0.001 mm, lateral 0.03 mm, 0.013 deg |
| return_same_screw | 92.357 | error 0.092 mm, tilt 0.006 deg |
| reinstall_same_screw | 167.625 | gap 0.018 mm (< 0.1), lateral 0.023 mm (< 0.6), tilt 0.18 deg (< 1.5), 11.37 turns, contact member_a 4.56 N / member_b 0.228 N (> 0.01) |
| turn_stand | 186.875 | lift 0.293 m, up_z -0.950, relative drift 0.02 mm (< 1), 0.374 deg (< 1.0) |
| place_bowl | 217.958 | support contact 0.29 N (> 0.1) |

## Searches (D variants from the C checkpoint of run b1; all with the B, C and E above)
| run | change | result |
|---|---|---|
| std agent | spin until accepted, stall torque left on | reinstall accepted; turn_stand never (4.03 deg) |
| b1 | lead capped at damping lead + 2 / 0.6 N m (near the seat) | too weak (the lead is used up within a tick): gap 0.23 mm after 60 s, not accepted |
| d1 | uncapped, w_slow 1.0 | pass; head contact at acceptance 0.011 N, turn drift 0.19 deg |
| d2 | w_slow 2.5 | pass; 0.48 N, 0.59 deg |
| d3 | seat_gap 0.08 mm | zero torque at 0.055 mm: never accepted |
| d4 | w_slow 0.5 | 0.024 mm but head contact < 0.01 N: never accepted |
| d5 | w_slow 1.5 | pass; 0.025 N, 0.28 deg |
| d6 | slow_gap 0.3 mm, w_slow 1.0 | pass; 0.022 N, 0.19 deg |
| d7 → reference | w_slow 2.0 | pass; 0.235 N, 0.37 deg (the best margins on both) |

## Verification (2026-10-16)
- **Reference.** `ikea365_ref.npz`: sha256 `d32ff622ac43e1143a9fa4e637aaf21de3fb55603d6243d3d6876ce738927449`, 89126
  rows (222.8 s of simulated time). 0 rows over the limit + 1e-9; the largest step is 1.0000000000005 x the limit.
  Rebuilt twice from `build_ref.py`, bit-identical.
- **Fresh replays.** `final_check()` passes, with 0 slewed ticks. End state `bc2108ab48d7ebd9…`, settled
  `3f561d45c8053fe3…`. The hashes match in 2 processes on vast (EPYC, patched venv, masking) and in 2 Slurm jobs on
  Quest (Xeon Gold 6230R, SIF 98fa2d3, patched .so 52e2a24e). Max part depth 1.027 mm, no breakdown.
- **Timing.** One unobserved replay takes 293 s on vast (2.0 % of the 14400 s budget), 674-690 s on Quest (4.8 %), and
  357 s in the Harbor verifier on ws2.
- **Harbor on ws2.** Image 0.2.0 98fa2d354818; jobs on the run host.
  - h1_priv_oracle: 1, deterministic, all_success. h1_priv_nop: 0.
  - h1_std_oracle: 1, live_success at 88000 rows (22 calls; the first success ends the episode), live_matches_replay,
    rows_match, deterministic, n_clipped 0 on all 22 calls. h1_std_nop: 0.
- **Stress.** 30 episodes from checkpoints of this reference (10 each of prefix_random, mutate and fast; seeds
  7570000-7570029). Result: 10 CLEAN, 20 VIOLENT, 0 BREAKDOWN. The
  VIOLENT ones are the Franka finger-slam forces of 11.6 kN (the hand slew is still off) and 3-5 kN in fast.
