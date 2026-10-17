# VESKEN closed-loop reference

`vesken.npz` is the reference of `ikea-vesken-i00-{privileged,standard}` under the final physics (prism rule, eket's
fix 3b, the arm joint-speed clamp, MuJoCo 3.14.0 with the EPA byte patch, numpy SIMD masking). It is a normal
`rcb_ikea` trajectory file (`ctrl`, `substeps` 4, `timestep` 0.000625, `actuators`). Its numbers:

| | |
|---|---|
| rows | 353,125 (882.8 s of simulated time; the demo has 344,359 rows) |
| sha256 | `32040cc6d5006953cd3abd5ab85044b6fbf102afb868312f06ab952327d2bda2` |
| rows over the speed limit | 0 against the previous row, starting from the keyframe ctrl; 0 outside the control range; `slewed_ticks` 0 |
| end / settled state sha | `2ea9b4bf…1f044` / `4e2c03be…87566` (two fresh processes, identical) |
| verdict | success: 23 / 23 operations passed, released, at rest, no breakdown; max part contact depth 2.1 mm |
| robot–robot contact | at most 6.6 N (finger on finger). The original reference had 6.9 kN (left_link2 on left_hand) |
| one replay | 630 s wall on the vast box (Zen 4), which is 4.4 % of the 14,400 s budget |

The original demo fails under the clamp in two ways:
- The box phase (rows 0-57,560) is chaotic. The left hand digs feet and caps out of the parts box, stages them on the
  bench and grasps them again, and the demo has several failed grasps that it retries. A sub-millimetre change from
  the slewed rows decides whether foot_1 is grasped.
- column_0_2 hits the columns still on the rack while it is carried. Without the clamp it recovers. With the clamp it
  slips 35 mm in the grasp and never reaches the approach zone, so the demo stops at 6 of 23 snaps.

## The controller (`vesken_oracle.py`)

The demo is used as a phase guide. Its unclamped run is the reference run (`ref/`):
- `plan.json`: per operation, the release row H, which the mechanism's own weld event gives.
- `sched.json`: per arm, the gripper intervals of the demo ctrl, and the part each interval carries in the reference run.
- `eref_free.npz`: per operation, the connector error of the reference run.
- `pos_free.npz`: every part's pose every 20 rows. It is 16 MB and not committed; `tools/posrec.py` regenerates it.

Operation k is demo rows [H_{k-1}, H_k). The controller reads the true state on every row, and each arm does one of
four things:
- **approach**: up to 1,500 rows before a grasp, the TCP is offset by where the part really is compared with the
  reference run. The offset covers translation, plus the part's rotation when that is under about 14°. The hand
  then closes on the part the same way it did in the reference run.
- **carry**: during a grasp interval, an integral loop moves the TCP's position and orientation offset so that the
  carried part follows its reference pose. Near its host, the error used is the connector error relative to the host
  (the mechanism's own geometry) minus the reference run's error. When two arms hold the same part, each gets half
  the gain.
- **idle**: the offset decays to exactly zero, and the demo row is then used unchanged.
- **weld**: before the release row, the controller keeps tracking on the last row until the operation's weld is on
  (at most 1.5 s). If the part is seated but its contact force is below 0.1 N, the hand presses 0.1 mm deeper every
  20 rows (`seek`, at most 3 mm). This is the "press until the snap is seated" step: a part that is exactly seated
  but floating misses the gate's 0.03 N contact force.

Offsets become joint targets through damped least squares IK on `left_tcp` / `right_tcp` (`mj_jacSite`). Each emitted
row moves at most 0.999 × the speed limit from the previous applied target. A longer step is split into the ticks
it needs, so `Session.applied()` never changes a recorded row.

One demo motion is replaced (`DEMO_PATCHES`). On its way from home to cap_3 (rows 324,600-325,600), the left arm folds
j4 to -3.03 rad with the wrist bent, and the hand hits left_link2: 4.9 kN in the unclamped demo, 6.9 kN in the
original reference. That motion is replaced by a smooth straight joint-space path between the same two end
configurations.

## Gates and search (`search.py`)

For each operation, from the checkpoint of the operation before it, `search.py` runs 8 candidates in parallel
(`CANDIDATES`: tracking gains, rotation tracking off, a shorter approach, an extra press depth, a longer wait,
feed-forward off). A candidate passes if:
- the operation's weld is on; and
- every part not yet placed is within 3 mm of its reference-run pose.

The first candidate that passes is kept, unless a later one is at least 0.5 mm closer. The parameters kept are in
`params.json`:
- ops 0-3: g 0.02, gr 0.01;
- ops 5 and 10: no rotation tracking;
- op 6: g 0.005, gr 0.0025;
- op 18 (s7-tray): no approach feed-forward;
- all other ops: the defaults.

At the release rows, every part was within 0.3 mm of the reference run up to op 21, and within 7 mm at op 22.

## Checks (2026-10-16)

**Fresh replays.** Two fresh processes on vast give success, with the same end and settled hashes as the search
session. The reference also reaches the same end state on these hosts:
- Quest (Xeon Gold 6230R): the stress checkpoint run;
- ws3: the Harbor verifier.

**Rebuild.** `rebuild.py` reproduces the reference rows exactly (`np.array_equal`) in 749 s on vast. Like the
search, it starts every operation from a restored checkpoint: `set_state` runs `mj_forward`, and the controller
reads the state that results.

**Harbor on ws3** (image `eai-ikea-mujoco:0.2.0` 98fa2d354818, `-sim:0.2.0` bf1f9623686c):

| Mode | Run | Result |
|---|---|---|
| privileged | oracle | 1: deterministic, 2 replays, 1135 s wall on the loaded host |
| privileged | nop | 0 |
| standard | oracle | 1: live_success, live_matches_replay, rows_match, deterministic. The live run reaches success at 352,000 rows. |
| standard | nop | 0 |

**Stress.** 30 episodes on Quest: 10 prefix_random, 10 mutate and 10 fast, from 21 checkpoints of
this reference.
- 10 CLEAN, 17 VIOLENT, 3 BREAKDOWN.
- All 3 BREAKDOWNs are prefix_random: under random arm targets, energy is created at a robot joint limit
  (left_finger_joint2 or left_joint5, 0.7-1.2 J). `confirm` reproduces all three from the birth,
  with the reference prefix and then the episode's rows.
- The VIOLENT force triggers of 11.6 kN are finger-on-finger contacts: random or flipped gripper commands close a hand
  on nothing. The Franka Hand slew is off. The reference itself peaks at 6.6 N robot–robot.

## Reproduce

All commands run with `PYTHONPATH=<rcb_ikea dir>:<scene dir>`, `IKEA_SCENES` set, and the numpy masking env.

1. Build the reference-run data from the demo (`vesken.npz` of the IKEA tree, the demo's ctrl rows):
   - `tools/annotate.py demo free ann_free` and `tools/zone_rows.py free demo zone_free.pkl`, then `tools/mkplan.py`,
     give `plan.json`;
   - `tools/posrec.py` and `tools/eref.py`, then `tools/mksched.py`, give `sched.json` and `eref_free.npz`.
2. Either:
   - `search.py --dir ck`, then `finish.py ck/op22.pkl out.npz`; or
   - `rebuild.py demo ref params.json out.npz`, which reruns the kept parameters op by op and gives the same rows.
3. Check with `verify.py out.npz` in a fresh process: rows over the limit, then `final_check()`.
