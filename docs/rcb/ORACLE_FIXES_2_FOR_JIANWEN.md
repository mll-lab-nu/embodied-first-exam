# Oracle fixes, part 2: horseshoe easy/hard, buzz easy/medium/hard, slotted_post_ring, orbits (oraclefix2, 2026-10-05)

Companion to `docs/rcb/ORACLE_FIXES_FOR_JIANWEN.md` (the first oracle agent's notes; its numbering of patches 01-12 and
bundle 0001-0012 is kept). Paths are on lab under `/DATA2/qineng/rcb/topogym_v1/oraclefix2/` unless stated. Base of
the graded tree: your dev/jianwen **d5e71c6ae**. Every change is planning-side (`topogym/planning/**`); no task rule,
threshold, grader, instance or agent-facing tooling changed.

- Tree: lab `/DATA2/qineng/rcb/topogym_v1/oraclefix2/tree` = `jianwen_d5e71_fix` (d5e71c6ae + oraclefix 09/10 + sweep FIX 5)
  + bundle **0001** (sweep FIX 2) + bundle **0008** (horseshoe 05/05c/05d) + the patches below.
  - 0001 is required for horseshoe on d5e71c6ae: without it `HorseshoePolicy.initialize` raises `KeyError: 'mode'` at step 0
    (`SessionPolicyRunner.run_policy` passes no `mode`), the same failure as the lock oracle (first notes, section 9).
  - Later also the first agent's patch 14 and the planning files of origin/dev/jianwen (the code the commits below
    apply to); the graded horseshoe planning dir and reference data equal the commit worktree's (checked by md5).
  - Commits for you (laptop worktree `tmp/2026-10-05_oraclefix2/wt`):
    - O2-2 `56039a64c`: buzz easy standard-executable (graded 1/1); on origin/dev/jianwen;
    - on top of it, horseshoe hard: O2-4 `4b2ca84d5` (transit budget in queries), O2-5 `5465ecf68` (fast handoff
      tilt; privileged 1), then this file (`docs/rcb/ORACLE_FIXES_2_FOR_JIANWEN.md`). O2-6 (rate-limited horseshoe
      stages) was lab-tested and failed; it is not committed (`oraclefix2/patches/unused_O2-6_*.patch`).
- Patches: `oraclefix2/patches/`. Diagnostics (never grades): `oraclefix2/exp/X*`. Notes: this file.
- Grading: your unchanged `bash_scripts/run_harbor_oracle_grades.sh`, through `oraclefix2/bin/lane2.sh`:
  - it runs your candidate steps (`topogym_merge_candidate.py`, `topogym_candidate_pipeline.py --phase build`) without
    `build_image.sh`, then the launcher with `--tasks-root`;
  - image `oraclefix2/rcb-topogym:0.2.14-dev-cu128`: a second tag of the d5e71c6ae image the first agent's launcher built
    (`824f9b3331bc`), never rebuilt; the pipeline checks image runtime source == frozen source;
  - Harbor through `oraclefix2/bin/harbor_of2.sh` (GPU pin, subnet pair 10.233.2xx checked free first, containers labelled
    `rcb.probe=oraclefix2`).
- The d5e71c6ae horseshoe instances equal your v16 (7293af9d6) ones except `topogym_source.sha256` (12f7c4fc... vs
  936e6ceb...): same scene, same physics.

## Status

| oracle | tier | privileged | standard | change | evidence / state |
|---|---|---|---|---|---|
| horseshoe_ring | easy | **1** | **1** | none beyond the bundle | `tree/runs/test_results/harbor_grade_of2_hs_easy`: 10153 rows, 253.8 s sim, live oracle 52 min end to end in Harbor; standard stream 10153/10153 rows, 0 resumes |
| horseshoe_ring | hard | **1** | **0** (one fold row over the step limit) | O2-4 (query-budgeted transits) + O2-5 (fast handoff tilt) | `tree/runs/test_results/harbor_grade_of2_hs_hard`: 11887 rows, 297.2 s sim, live oracle 51 min end to end, 2 CPU replays deterministic, strict goal at row 11887; lab `exp/X10` identical |
| horseshoe_ring | hard | lab: no success | not graded | + O2-6 (rate-limited stages; not committed) | lab `exp/X11`: the one fast row is gone (largest step 0.0364 rad), but the ring-grasp relocation then fails its contact check (1.07 mm, limit 1 mm) at 165 s sim |
| buzz_wire_3d | easy | **1** | **1** | O2-2: rate-limited staged run + 1 cm lowered release | `tree/runs/test_results/harbor_grade_of2_bz_easy`: 8733 rows, 218.3 s sim, live oracle 27 min end to end in Harbor, 2 CPU replays deterministic; release study `exp/Z1`, `Z5`; full lab run `exp/Z6` |
| buzz_wire_3d | hard | **0** | not run (needs a privileged pass) | O2-3 (not committed): compiled rows to 43434 + measured finish nudge | the nudge's gripper touches the end post (`exp/Y5h`); grade `tree/runs/test_results/harbor_grade_of2_bz_hard`: 43450 rows, 1086.2 s sim, live oracle 116 min |
| buzz_wire_3d | medium | no grade | - | - | section 2 (facts for you) |
| slotted_post_ring | easy / medium / hard | no oracle | - | - | section 3 (task-level decision) |
| orbits | easy / medium / hard | no oracle | - | - | section 3 (task-level decision) |

## 1. horseshoe_ring easy and hard

All diagnostics run the Harbor callback (`public_session.run_feedback_policy`) in a frozen privileged Session on the
v16 candidate instance (same scene as d5e71c6ae's, only the source sha differs), CPU fp64, never a grade. Horseshoe is
deterministic: a lab run reproduces the graded run tick for tick (checked: the easy grade's phase times equal `X2e`'s).

- **easy: no new fix.** On d5e71c6ae the original easy recipe's suspended release drops the ring to the table
  (separating gap 111 mm at the end of support_release, `exp/X1e`; the exit check needs 20 mm). The ba01 runs of the
  first oracle agent kept the ring on the lower shoe because the live run then still had BUG 7 (FK/IK queries left
  the rigid state 1e-16 off); with the runtime fix the release takes the other branch.
  - Full diagnostic (`exp/X2e`, unchanged oracle = d5e71c6ae + bundle 0001/0008): native Task success at 253.8 s sim,
    10153 rows, 43 min end to end on lab (incl. ~4 min scene build).
  - Grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_hs_easy`): privileged **1** (2 CPU replays,
    deterministic), standard **1** (stream 10153/10153 rows, live and replay success, 0 resumes). Live oracle execution
    in Harbor: 52 min end to end incl. the scene build (rule: about 72 min). No code change for easy.
- **hard: privileged fixed by O2-4 + O2-5; the standard twin stays 0 (open).** Under Harbor's physics the released
  ring ends on the right hand, not on the table; the fix keeps it free and lets the active pickup take it off the
  right wrist.
  - Mechanism (`exp/X1h`, `X3a`): during orient_for_handoff (90 deg in 0.5 deg samples at 0.05 s, 8 s hold) the ring
    slides 43 mm along the lower shoe's band (folded-ring longitudinal position 0.025 -> 0.068 m; your reference 0.0145)
    into the right gripper and wedges between its fingers (contacts with both finger links). After the release the
    separating gap is -23 mm. 11 post-release motions of the held lower shoe (shakes in x/y/z, +-30 deg tilts about
    x/y/tool, a rotary shake, lowering 6 cm) leave it at -21 to -56 mm (`exp/X1h`).
  - Your active pickup (`exp/X4`): the left hand grasps the ring, but it is still threaded through both chain links; the
    contact lift (also after lowering 4 cm or rotary shakes) lifts the right shoe and chains with it (gap -33 to -44 mm).
  - Handoff search from one checkpoint at the end of the fold (`exp/X3a-f`, `X8`, 19 variants): yaw +-30, angle
    75/110/120, roll +-20/-30/-40, holds of 1 and 8 s, combinations; angle -90 and yaw 180 are unreachable, as are
    several combinations. Only a fast tilt (0.02 s per 0.5 deg sample) moves the ring off the shoes (gap +36 mm with a
    1 s hold, `X3e`; +34 mm with 8 s, `X8`), but it ends looped around the right wrist
    (`exp/X3e/frame_hold1_fast.png`):
    - the table pickup cannot clear the remainder (the ring rests on the hand; `exp/X6b`);
    - your active pickup finds no left-hand grasp of the ring at the right wrist (785 of 960 candidates unreachable,
      the rest inter-arm or contact; `exp/X7`).
  - The lead (`exp/X9`): from the same fast-tilt release state the left ring
    grasp does plan when the planner gets its time: ring_grasp found angle 270 deg (approach -1, flip -1) in place, and
    angle 225 deg after moving the held lower shoe 10 cm in +y (+x 10 cm: no grasp; -y, +z, -x: unreachable moves). In
    `X7` the same planning failed only because 4 candidates hit the free-arm RRT's **wall-clock** budget
    (`joint_transit.plan_transit`: `deadline=time.monotonic()+seconds`, 20 s from ring_grasp) under the night's CPU
    load. The live oracle's planning, and with it its success, therefore depends on machine load (the recorded
    trajectory still replays exactly). Replacing the wall-clock deadline by an iteration budget would make the
    horseshoe planners reproducible (O2-4 below).
  - **O2-4, a separate small fix: the transit budget counts queries.** `joint_transit.plan_transit` stopped its seeded
    RRT at a `time.monotonic()` deadline, so the live oracle's planning (ring_grasp's 20 s transits, the released hand's
    30 s retreats) changed with the host's load. The budget is now `round(seconds * QUERIES_PER_SECOND)` collision
    queries with `QUERIES_PER_SECOND = 100` (one ContactHorseshoeIK query costs 10.8 ms of CPU on a lab core,
    `exp/C1`): `seconds` keeps its meaning as an idle host's budget and the search is reproducible. The budget is
    checked where the deadline was (between extensions), so a search can overshoot it by one extension's edge checks:
    X10's ring-grasp transit returned after 3662 queries (104 iterations), the released hand's retreat after 2192.
    Easy and medium are unaffected: their only transit (the left-hand retreat) is a direct one (170 queries), tried
    before any RRT. (Other wall-clock caps remain in `ring_route.py` (900 s) and `joint_route.py` (600 s); they did
    not bind tonight.)
  - **O2-5: the fast handoff tilt.** Hard's orient_for_handoff uses 0.02 s per 0.5 deg sample and a 1 s hold (was
    0.05 s, 8 s); `stages.py` accepts 0.02 s samples (was >= 0.05 s); recipe.json and manifest.json re-pinned.
  - With both (lab `exp/X10`, the Harbor callback): fast tilt, suspended release with joint retreat, the left hand
    grasps the ring hanging around the right wrist, relocation +22 cm, the right hand opens and its planned retreat
    withdraws it out of the ring, contact lift, placement, goal: native Task success at 297.2 s sim, 11887 rows, 48 min
    end to end on lab incl. the scene build.
  - Grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_hs_hard`): privileged **1** (11887 rows, 297.2 s sim,
    2 CPU replays deterministic, strict goal at row 11887, no review or forcing events; the live oracle reproduced X10
    row for row, 51 min end to end in Harbor incl. the scene build; verifier 62 min). Standard **0**: "Standard service
    clipped or rejected reference actions", the stream stopped at live row 3601. Exactly one of the 11887 recorded rows
    asks for more than the 0.04 rad per-step joint limit: row 3397, 0.0408 rad on right/elbow at about 84.9 s sim,
    inside flip_and_fold (your fold; O2-4/O2-5 do not touch it). The service spreads such a row over extra steps and
    the standard bridge refuses a slowed reference row. Easy's largest step is 0.0372 rad.
  - **O2-6, lab-tested and failed (not committed): the horseshoe stages run rate-limited.**
    `public_session.run_feedback_policy` passes `runner=standard_rate.rate_limited_runner(session)` to `run_stages`,
    as buzz easy does (O2-2, fix 15 of the first pass;
    `oraclefix2/patches/unused_O2-6_horseshoe_rate_limited_stages.patch`). A row within 0.039 rad (the limit with a
    2.5 % margin for float32 rounding) is submitted bit-identically; a faster row is reached in as many steps as the
    limit needs, with the same targets. Easy would be unchanged (no row above 0.039 rad); hard's row 3397 becomes 2
    steps, and everything after it shifts by one control step.
    - Lab run (`exp/X11`, the Harbor callback, O2-4 + O2-5 + O2-6): the limiter slowed exactly that row (6604 rows
      requested, 1 slowed, 1 step inserted; largest recorded step 0.0364 rad). The closed-loop stages absorb the shift
      at first (fold end 117.1 s vs X10's 116.55 s, support_release end 154.5 s vs 153.7 s), but the left ring grasp
      then takes another path: a direct approach, grasped at 164.1 s (X10: an RRT transit through 3 via points,
      grasped at 175.1 s). The +22 cm relocation of the held pair that follows (`release_translation_m` [0, 0.22, 0],
      `settling.plan_held_pair_translation`) fails its plan check at sample 85: left/upper_forearm_link would press
      1.07 mm into horseshoe_left (limit 1.0 mm). The oracle stops at 165.1 s sim, after 24 min on lab. No grade.
    - So hard's success depends on the exact state the fold leaves: a 25 ms shift changes the ring grasp, and the
      relocation is planned only after that grasp has been executed. A standard-executable hard reference needs
      grasp_ring to pick a ring grasp whose follow-on relocation plans (or to try other relocations, for example a
      shorter or slightly raised one, when the first fails), then one lab run and one grade (about 4 h). Not done here
      (time box).
  - Prepared but unused: a measured `disentangle` option of support_release (bounded shakes / tilts of the held lower
    shoe until the 20 mm separating gap; `oraclefix2/patches/unused_hs_hard_disentangle_and_fast_tilt_draft.patch`).

## 2. buzz_wire_3d: your references under Harbor's 2.5 ms x 10 physics

Lab: CPU fp64 Buzz in a frozen privileged Session (`oraclefix2/exp/Y*`, `Z*`), 0.14 s per control step under the
night's load. Your compiled medium/hard actions and the easy staged proof were recorded at 25 ms x 40 substeps.

- **hard (compiled, 43568 rows, `exp/Y1h`)**: the rows carry the tool along the whole wire without a touch (traversal
  complete at row 19674, tracked from row 625) and through your terminal regrasps. Your last rows release the tool on
  the deck supported, released and quiet, but **5.023 mm** and 8.0 deg from the finish pose (limit 5 mm, 10 deg); no
  Task success. The full run takes 103 min of execution plus the scene build.
  - O2-3 (one graded attempt, the lead's decision): your rows up to 43434 (the last held, deck-supported placement),
    then `final_nudge`: the held tool moved into the Task's finish pose (endpoint_pose, the symmetric frame nearer the
    measured one) 1.5 mm above its resting height under closed-loop tracking of the measured tool pose, released in
    place, the hand backing off slowly; rate-limited rows.
    - **Result: privileged 0.** The graded live oracle stops 0.4 s into the nudge with "Robot touched the wire" (your
      BuzzWirePolicy guard: the gripper touches the end post's metal; the Task itself fails only on wand-wire contact,
      but your oracle guard and audit standard forbid robot-wire contact). At row 43434 the held tool rests on the deck
      right at the end post: every measured nudge touches the post with the gripper within 0.4 s, the graded one and
      5 lab variants (lift 1 / 1.5 / 2.5 mm, release grip 0.6, a 5 s nudge; `exp/Y5h`, all at the same tick).
    - Launch-order slip: the grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_bz_hard`) was started before
      the lab run had reached row 43434; both reached the nudge at about the same time. The verifier replays were left
      to finish for the record: privileged 0 (43450 rows, 1086.2 s sim, 2 replays deterministic, no strict goal; live
      oracle 116 min in Harbor, verifier 241 min); the standard twin was not run (blocked on the privileged result).
      Not committed; buzz hard stops here (lead's decision).
  - So under Harbor physics your compiled path ends 5.023 mm / 8.0 deg from the finish, 0.023 mm over the position
    limit, and a closed-loop correction from its last held pose is blocked by the end post. A closed-loop solution needs
    a planned traverse and finish (future work). Such a reference would also break the 72 min rule as compiled (116
    min of execution in the graded run). The cause is the compiled path, not the task: 43.5k rows at about 0.14 s/step, of which 18.4k do not move the arm. A planned faster traverse (the easy
    traverse moves at about 18 mm/s; hard's 2.18 m wire would take about 2 min of sim time) plus a planned finish that
    keeps the gripper off the end post is future work for you; the decision on a longer reference is the user's (as
    for fiber hard).
- **medium (compiled, 29544 rows, `exp/Y1m`)**: the traversal completes at row 18960; your release then touches the
  wire 26 rows after the post descent (row 19413: `wire_touched`), and the episode ends.
  - A held placement at the finish pose from the post-descent grasp is infeasible: 48 to 90 planned candidates (finish
    yaw +-180 deg in 15 deg steps, both symmetric frames, xy offsets; your checked_turn planner with the Task's finish
    frame) have no collision-free IK path (`exp/Y3m`, `Y4m`; also from hard's row 21139, `Y3h`, `Y4h`).
  - A regrasp after hard's deck release (row 21420) finds no collision-free free-hand goal for 6 grasp candidates (`exp/Y3h`).
  - A closed-loop medium within 72 min needs a planned fast traverse plus a new regrasp finish: the compiled rows up to
    the end of the post descent alone take 46 min plus the scene build. No grade.
- **easy (staged proof)**: privileged 1 with fixes 09 + 10 (first oracle pass). The standard twin needs rows within
  the 0.04 rad per-step limit; with every row rate-limited (fix 15) your release from the flatten pose touches the wire
  0.12-0.17 s after opening, in every variant that releases at that height (`exp/Z1`, `Z5`: recipe, open-in-place, slow
  opening, retract up, retract along x, slow retract). The slowed regrasp rows (the first at row 1621) leave the tool
  in a slightly different state at the flatten pose; the release speed is not the cause (0 rows of the release itself
  are slowed).
  - From 1 or 2 cm lower (or yawed +-5 deg) the same release leaves the tool on the deck supported, released and quiet
    with the traversal complete (`exp/Z5`).
  - O2-2: release_onto_deck first lowers the held tool 1 cm in 2 s (measured tool-pose tracking); fix 15 is back
    (`run_stages(..., runner=rate_limited_runner(session))` for the staged easy proof). selection.json, recipe.json and
    manifest.json re-pinned.
  - Full run (`exp/Z6`, the Harbor callback in a frozen privileged Session): native Task success at 218.3 s sim, 8733
    rows, largest arm-joint step 0.0385 rad (0 rows above the 0.04 rad limit), 35 min end to end on lab (14 min of it
    the scene build under load).
  - Grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_bz_easy`): privileged **1** (live oracle 27 min end to
    end in Harbor incl. the scene build, 8733 rows, 2 CPU replays deterministic), standard **1**. The graded tree's
    reference_policy.py also carried the (unused for easy) hard finish of O2-3; the easy code path is the committed
    one. Commit O2-2 also updates `ci_checks/test-buzz-harbor-reference.py` (its fake Session publishes the action
    layout the limiter reads; the easy case asserts the rate-limited runner).

## 3. slotted_post_ring and orbits: no oracle; feasibility and speed need a task-level decision

Not developed (lead, 2026-10-05): both are multi-day research projects, and both break the speed rule (one full oracle
execution at most ~20 % of the 6 h agent budget, ~72 min) by a wide margin. Facts, with file references (d5e71c6ae):

- **slotted_post_ring: the imported route worked only in a different scene.**
  - `topogym/planning/slotted_post_ring/README.md` lines 27-31 list the handoff scene against the local one:
    - slot 34 mm vs local 28 mm;
    - cord E = 1 MPa vs local 50 kPa (20x softer here);
    - upright end discs on fixed stands vs local flat discs;
    - a longer cord (about 1.105 m);
    - IPC sync tolerance 5 mm vs local 2 mm.
  - `policy.py:84-89` refuses a full run on flat discs ("The imported pickup stage requires an upright disc"). Only
    `--stop-after bead_to_slot` runs, and that prefix is unverified.
- **No evident flat-disc grasp.**
  - The disc is 110 mm across, 11 mm thick, and lies 1 mm above the table (`topogym/assets/geometry/slotted_post_ring.py:38-40`).
  - The ALOHA gripper opens at most 57.4 mm: the width range of the rigid families' instructions; here the action is the
    native finger target 0.002-0.037 m (instruction line 100).
  - This family has physical friction grasps only: no grasp assist (instance `simulator.grasp_assist.model = "none"`;
    instruction line 104).
  - So a top-down pinch across the disc is impossible, and there is no room under the rim. A pickup needs a new
    manipulation, for example tipping the disc up against the base first; nothing like that exists.
- **The ring passes the slot edge-on with almost no margin.**
  - Slot 28 mm against a 20 mm ring tube (`tasks/slotted_post_ring/slotted_post_ring_{easy,medium,hard}.py`) leaves 4 mm
    per side.
  - With ring outer radii of 74 / 72.5 / 71 mm, that allows only about 3 deg of yaw or roll while the whole ring passes,
    with a friction grasp and the cord pulling on it.
- **Speed.**
  - The handoff's only successes started from development checkpoints, not from home. One finished at t ≈ 348 s of
    simulated time (README line 89): about 14k control steps.
  - Measured IPC step time on lab: 2.49 s median (`/DATA2/qineng/rcb/topogym_v1/bench_new.out`, line 11). That gives
    roughly 9-10 h per execution, against the 72 min rule.
- **orbits.**
  - `topogym/planning/orbits/README.md` line 20: the import is a MuJoCo 1-D rope planner with virtual point grippers.
    "Native robot execution and complete success are still to be implemented".
  - There is no Genesis/IPC robot oracle to fix. Measured IPC step time: 2.39 s
    (`/DATA2/qineng/rcb/topogym_v1/bench_v12_orbits.out`). Grasps are physical only here too.
- **Harbor side, for whenever an oracle exists.**
  - `bash_scripts/run_harbor_oracle_grades.sh:15,67` excludes both families.
  - `topogym/planning/harbor_bridge/catalog.py:22-23` has empty `RUNNERS` and no `SESSION_CALLBACKS` entry.
  - A bridge entry is planning-side (a `public_session.run_feedback_policy` per family plus the two lists); the
    generic packager and graders need no change.
- **Conclusion:** no oracle for these six tasks. Whether they stay in the benchmark as they are, change (slot, cord
  stiffness, disc pose) or get a separate speed allowance is a decision for you and the user.
