# STEGESUND reference

`stegesund.npz` is the reference of `ikea-stegesund-i00-{privileged,standard}` under the final physics (prism rule,
the arm joint-speed clamp, MuJoCo 3.14.0 with the EPA byte patch, numpy SIMD masking). It is the author's
speed-limited demo (`stegesund_vlim`, the privileged `solution/trajectory.npz` as sent), unchanged: rung 1 of the
reference ladder. It is a normal `rcb_ikea` trajectory file (`ctrl`, `substeps` 4, `timestep` 0.000625, `actuators`).

| | |
|---|---|
| rows | 357,221 (893.05 s of simulated time) |
| sha256 | `2181d216a5559c9835e67403d3d06b6ed608e69c77f36b77cdf9dc451aaaf486` |
| rows over the speed limit | 0 against the previous row, the first row against the keyframe ctrl (step 0); largest step = the limit itself (ratio 1.0000000000005, inside the 1e-9 rad tolerance); 0 outside the control range; `slewed_ticks` 0 |
| initial state | `917b2bc63ab1ec62…` = bindings.json (frozen birth loaded unchanged) |
| end / settled state sha | `f82c5e47715a7363…` / `281f267cd99afc10…`, identical in every replay below |
| verdict | success: half_B 0.26 mm / 0.03°, shelf 0.42 mm, rod 0.34 mm / 0.14°, bolts 1-4 seated and welded (axial ≤ 0.25 mm, lateral ≤ 0.17 mm, tilt ≤ 0.18°), upright 0.016°; released, at rest (max part speed 1.4e-7 m/s, the hex key), no breakdown; max part contact depth 1.24 mm; the same after the 1.0 s hold |

The arms are named Menagerie-style (`left/actuator1` …); the worktree's `rcb_ikea.py` (slash-aware speed table)
was used everywhere. The scene has no cylinders, so the prism rule changes nothing here. success.py has no release or
rest test of its own; the benchmark's terminal rules add them, and the demo already ends with both hands open and clear
(the hex key lies where the demo left it, at rest, untouched).

## Gates

1. Frozen birth: every replay builds to the bound `initial_state_sha256` (`917b2bc6…`); scene files = assets.json pins.
2. Leak check: `environment/` holds only the Dockerfile and `rcb_ikea.py`; neither the rows nor their sha appear in
   `environment/`, `instruction.md` or `tests/`; `stage_context.pointers()` finds no upstream pointer in the scene
   texts; the instruction has no world coordinates, table height or base pose.
3. Fresh replays (`probe.py`: rcb_ikea Session, clamp in, final_check), all success, all with the hashes above:
   - AMD Zen 4: vast EPYC 9354 (patched venv) x2; ws3 Ryzen 9 7950X (image 0.3.0) x1;
     Harbor verifier on ws3 x2;
   - Intel: Quest Xeon Gold 6230R (SIF `eai-ikea-mujoco_0.3.0_ed950d0`) x4 (two Slurm jobs, two processes each).
4. Harbor privileged on ws3 (image 0.3.0), re-run with fresh per-run file mtimes against the BuildKit context reuse (2026-10-16
   afternoon): oracle reward 1 (`sk_steg_priv_oracle2/ikea-stegesund-i00-privileged__bcnYEBG`: deterministic 1,
   instance_exact 1, both replays `f82c5e47…` / `281f267c…`, replay_wall 1721 s for 2 parallel replays), nop reward 0
   (`sk_steg_priv_nop2/…__tnjSc23`, missing trajectory). The earlier runs with the old script gave the same
   (`sk_steg_priv_oracle` 1, `sk_steg_priv_nop` 0).
   Final, with the replay-video verifier (task re-rendered): oracle reward 1
   (`sk_steg_priv_oracle3/…__DsEwq8R`: deterministic 1, instance_exact 1, `f82c5e47…` / `281f267c…`, replay_wall
   1508 s; video_rendered 1, replay.mp4 751 frames at 25 fps, 1.19 s simulated per frame, its end state sha =
   the verdict's, render 1857 s), nop reward 0 (`sk_steg_priv_nop3/…__oVbFPAW`, missing trajectory, no video).
5. Stress: see below.
6. Timing (one replay, 2 processes per job on a dedicated Slurm allocation): Quest Xeon 6230R 3357-3518 s =
   23.3-24.4 % of the 14,400 s budget: above the ~20 % bar, below the 30 % ceiling, FLAGGED. vast EPYC (box load ~30):
   1612 s (11.2 %); ws3 7950X (loaded, load ~25-30): 1736 s (12.1 %).

## Stress

203 episodes on Quest (Xeon 6230R, SIF 0.3.0; our stress harness with RoboARC's observer v2.13b),
29 per strategy (random, prefix_random, prefix_jerk, mutate, fast, grip, push), seeds 960000-960202, 3-10 s each,
from 20 checkpoints of THIS reference (every 5 % of its rows; the checkpoint run itself ended on `f82c5e47…`,
success).

**Harness fix (the observer's weld partners, no physics change).** stegesund's seat welds are authored part-first
(body1 = the bolt or the clamped half, body2 = the shelf), the reverse of the other scenes. The shim's
`MechanismWelds` made body2's partner body1, so a welded bolt dragged along with its shelf had no partner and the
shelf had a bolt as its partner. The first run (b29950c shim) gave 20 BREAKDOWN, all "uncaused jump bolt_N". The shim
now makes each weld's part partner its host (the body in more active welds; on a tie body1, as before, so the
first-batch scenes are unchanged). The same 203 seeds re-run:

| strategy | n | CLEAN | VIOLENT | BREAKDOWN |
|---|---|---|---|---|
| random | 29 | 0 | 29 | 0 |
| prefix_random | 29 | 0 | 27 | 2 |
| prefix_jerk | 29 | 3 | 23 | 3 |
| mutate | 29 | 13 | 16 | 0 |
| fast | 29 | 23 | 3 | 3 |
| grip | 29 | 0 | 29 | 0 |
| push | 29 | 27 | 2 | 0 |
| total | 203 | 66 | 129 | 8 |

- Non-jerk BREAKDOWN 5 / 174 = 2.9 % (shipped set 1.75 %); the three `fast` ones are one event (the same
  checkpoint and speed-up, so the same rows: s960004 / 074 / 102), so 3 distinct non-jerk cases. prefix_jerk 3 / 29.
- All 8 confirmed from the birth in a fresh process (the reference prefix to the checkpoint matches the checkpoint
  hash; the episode ends on the same state hash; same verdict).
- Mechanism, 7 of 8: "uncaused jump shelf". In every one, at the same tick a welded member of the stand (half_A or
  half_B, clamped to the shelf by the seat weld) has a CAUSED jump (partner: a robot finger / link5 / hand at 1-2 m/s)
  at least as fast as the shelf. The robot hits the welded stand, and the weld carries the shelf along; the observer
  gives each body one weld partner, so the shelf (host of six welds) has none. Candidate: observer limitation
  (weld-transmitted push), not a physics breakdown.
- The 10-50 m/s launches (fast s960004 / 074 / 102, one event from checkpoint row 125,027 at 4x; prefix_random
  s960176 from row 214,332), explained by `diag/forensic.py` (a per-tick replay from the checkpoint; it ends on the
  episodes' own state hashes):
  - the robot pushes the stand: fast, ticks 974-1072, the left fingers / hand hit half_A (100-250 N, 0.3-0.9 J of
    positive robot contact work per hit, 5.9 J in all; the stand, about 1.0 kg, goes 0 -> 2.3 m/s exactly at the hits);
    s960176, ticks 710-786, right/link6 and the hand hit half_B (1.5 J, 0 -> 1.6 m/s);
  - the stand slides and flies across the table to its front edge (x = 1.0 m) and leaves it (fast ~tick 1300,
    s960176 ~tick 970);
  - the floor plane is decorative (class `deco`, contype 0), so nothing stops the fall: from there on the speed is
    free fall (17 m/s and -15.5 m after 1.6 s; 125 m after 5 s in the longest episode). The "tunnel" events of s960176
    are welded bolts (their contacts are off by design) passing the table edge with the falling shelf.
  - No stored energy is released: energy_forensics shows no creation (X falls), no v2.11/v2.13b pop (pop_speeds
    empty), no seat weld arms or switches on during these episodes (at the checkpoints bolt_1 is welded with half_A clamped, for s960176 also bolt_3 with half_B; the mechanism's arm / weld event lists do not grow), max part contact
    depth 0.95-0.99 mm, no MuJoCo warning, rcb_ikea Validity breakdown None. The final grader would not flag such an
    agent episode as a breakdown (it fails on the goal instead); in 14,400 s a falling part stays far below MuJoCo's
    1e10 BADQPOS/BADQVEL bounds.
  - Minimal reproducer: checkpoint row 125,027 + the first ~1,320 rows of `ep/rows/stegesund__fast__s960102.npz`
    (launch at tick 974, off the edge at ~1,300); checkpoint 214,332 + the first ~1,000 rows of
    `stegesund__prefix_random__s960176.npz`.
- Diagnostic observer variant (not adopted, not kept in this repository): the host additionally takes its fastest
  welded part as its weld partner. The 8 BREAKDOWN episodes re-run (same seeds, same state hashes): 7 become VIOLENT
  (all the "uncaused jump shelf" ones, the launches included); only prefix_random s960120 stays BREAKDOWN. The variant
  can mask an uncaused jump of a whole welded group (each member's partner moves with it); the energy rules still see
  one.
- By distinct cause, non-jerk: 1 genuine BREAKDOWN (s960120, energy at the finger joint limit) = 1 / 174 = 0.57 %;
  2 distinct events (4 episodes) are the weld-partner artefact on a robot push off the table. prefix_jerk: 3, all the
  same artefact.
- 1 of 8 (prefix_random s960120): energy created at the right finger joint limit (`limit:right/finger_joint2`,
  +0.5 J), then a 5 m/s shelf jump: the first batch's "energy created at robot joint limits under random arm targets"
  class.
- VIOLENT: most episodes trigger on a 4033 N finger-on-finger force (`force_finger_finger`, a hand closing empty at
  full speed): the first batch's finger-slam residual while the Franka Hand slew is off; no breakdown follows.
