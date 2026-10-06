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
      tilt; privileged 1), then this file (`docs/rcb/ORACLE_FIXES_2_FOR_JIANWEN.md`, `1f47263de`); all on origin.
    - second round, all on origin: O2-6 `faa9774f1` (horseshoe rows clamped to the standard step limit; hard graded
      1/1; via your merge b1ab6b18d), O2-8 `66522387e` (buzz medium re-timed replay; graded 1/1), O2-9 `42e4237ce`
      (buzz hard re-timed replay with an earlier release; graded 1/1; rebased onto v18 8d7d16489), then this file.
  - Graded tree vs commits (second round): every grade ran on image `oraclefix2/rcb-topogym:0.2.14-dev-cu128`
    (sha256:824f9b3331bc, the d5e71c6ae image, never rebuilt) with the lab tree above. Its packaged horseshoe and buzz
    files equal the commits, except for the buzz grades' `harbor_bridge/actions.py`, `harbor_bridge/callbacks.py` and
    `planning/solvability.py`, which stayed at a3604ea7e: your helper-pipeline versions (b1ab6b18d) add
    `schema_version=2` / `rgb_available` to the policy initialize context and a `"session"` QualificationWorkflow mode
    for `run_stages`. The re-timed replay (`retimed.run_retimed`) never calls `run_stages` or the workflow, and its
    policies read only `action_spec` and `timing_spec` from the context, so those changes do not reach the buzz
    medium/hard path; the manifest differs only by your below-easy entries.
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
| horseshoe_ring | hard | **1** | **1** | + O2-6 (rows clamped to the standard step limit, no extra steps) | `tree/runs/test_results/harbor_grade_of2_hs_hard7`: 10763 rows, 269.1 s sim, live oracle 54.7 min end to end, standard 10763/10763 rows; lab `exp/X12` identical (spreading the row instead failed, `exp/X11`, `X13`) |
| buzz_wire_3d | easy | **1** | **1** | O2-2: rate-limited staged run + 1 cm lowered release | `tree/runs/test_results/harbor_grade_of2_bz_easy`: 8733 rows, 218.3 s sim, live oracle 27 min end to end in Harbor, 2 CPU replays deterministic; release study `exp/Z1`, `Z5`; full lab run `exp/Z6` |
| buzz_wire_3d | hard | **0** | not run (needs a privileged pass) | O2-3 (not committed; superseded by O2-9 below): compiled rows to 43434 + measured finish nudge | the nudge's gripper touches the end post (`exp/Y5h`); grade `tree/runs/test_results/harbor_grade_of2_bz_hard`: 43450 rows, 1086.2 s sim, live oracle 116 min |
| buzz_wire_3d | medium | **1** | **1** | O2-8: traverse re-timed 4x under a clearance guard + wand lowered 2.5 mm before your release | graded live oracle 45.4 min end to end in Harbor; lab `exp/Z7m` (Harbor callback): success at 438.4 s sim, 17536 rows (was 29544), 45 min end to end; lowering margins about 0.5 mm to the regrasp failure at 2 mm, 0.9 mm to the hand-wire touch; grade `tree/runs/test_results/harbor_grade_of2_bz_medium2` |
| buzz_wire_3d | hard | **1** | **1** | O2-9: traverse re-timed 3x + your retreat stopped after row 43488, open, retreat 4 cm | graded live oracle 74 min end to end in Harbor; lab `exp/R3h3`: success at 808.6 s sim, 32344 rows, 87 min end to end on a busier host (over the 72 min rule; accepted by the user, as for fiber hard); finish margins 0.12 mm / 1.2 deg; grade `tree/runs/test_results/harbor_grade_of2_bz_hard2` |
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
- **hard: fixed by O2-4 + O2-5 (privileged) and O2-6 (standard twin).** Under Harbor's physics the released
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
  - **Spreading the fast row (first try, not committed).** `run_stages(..., runner=standard_rate.rate_limited_runner(
    session))` as buzz easy does (`oraclefix2/patches/unused_O2-6_horseshoe_rate_limited_stages.patch`): hard's row
    3397 becomes 2 steps and everything after it shifts by one control step.
    - Lab run (`exp/X11`): the limiter slowed exactly that row. The closed-loop stages absorb the shift at first (fold
      end 117.1 s vs X10's 116.55 s), but the left ring grasp then takes another path: a direct approach, grasped at
      164.1 s (X10: an RRT transit through 3 via points, grasped at 175.1 s). The +22 cm relocation of the held pair
      that follows (`release_translation_m` [0, 0.22, 0], `settling.plan_held_pair_translation`) fails its plan check
      at sample 85: left/upper_forearm_link would press 1.07 mm into horseshoe_left (limit 1.0 mm). Oracle stops at
      165.1 s sim.
    - A relocation fallback (fixed variants of the translation: +1/+2 cm z, +-1/+-2 cm x, x0.9/0.8/1.1; `exp/X13`, the
      same spread run) does not rescue it: all 10 fail at about 85 mm with the same forearm/horseshoe_left contact
      (1.03-1.31 mm). Dropped (`oraclefix2/patches/unused_O2-7_horseshoe_relocation_fallback.patch`).
  - **O2-6: clamp instead of spread (no shift).** `standard_rate.RateLimiter(mode="clamp")`: one control step per row;
    an arm joint that asks for more than 0.039 rad (the 0.04 rad limit with a 2.5 % float32 margin) moves by 0.039
    toward its target, and the remainder carries into the next rows. The default stays "spread" (buzz easy, keyhole,
    lock and knot unchanged). `public_session` runs the horseshoe stages with `rate_limited_runner(session,
    mode="clamp")`. Offline check on the graded trajectory: only row 3397 is above 0.039; clamped, it leaves row 3398
    a step of 0.0035 rad (was 0.0053), so the carry ends there. Easy is unchanged (largest step 0.0372 rad).
    - Lab run (`exp/X12`, the Harbor callback, O2-4 + O2-5 + O2-6): exactly one row clamped (0.00175 rad carried);
      the closed-loop fold ends 75 ms later than X10 (116.63 s), but the ring grasp (RRT through 3 via points) and the
      relocation are X10's; native success at 269.1 s sim, 10763 rows, largest recorded step 0.0390 rad (0 rows above
      0.04), 44 min end to end on lab.
    - Grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_hs_hard7`): privileged **1** (10763 rows, 269.1 s
      sim, 2 CPU replays deterministic, strict goal, no review or forcing events; live oracle 54.7 min end to end in
      Harbor, verifier 48.2 min) and standard **1** (live and replay success, 10763/10763 rows streamed, live matches
      replay, 0 hold steps). The grade reproduced `exp/X12` exactly.
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
      Not committed; buzz hard stopped here in the first round (solved in the second round, O2-9, section 2b).
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
    the end of the post descent alone take 46 min plus the scene build. No grade in the first round (solved in the
    second round, O2-8, section 2b).
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

### 2b. Second round (2026-10-05 afternoon): re-timed compiled rows (O2-8, O2-9); medium and hard graded 1/1

- **Re-timing (O2-8, `buzz_wire_3d/retimed.py`).** Your compiled traverse creeps (about 2 mrad per row; medium 29544
  rows, hard 43568). `RetimedJointPolicy` replays the same joint path in fewer rows by path-parameter resampling: inside
  a segment of source rows the source index advances `factor` rows per control step (fractional positions interpolate
  the joint targets, the gripper keeps the reached row's value); outside every segment your rows are emitted as
  recorded. A guard measures the wand's clearance to the wire's metal pieces from privileged state on every row
  (`BuzzIK.wand_clearance`, the FCL hulls your planner uses): below 1 mm the source advances one row per step (your
  timing) until 2 mm again; below 0.5 mm the targets hold (at most 40 steps per event). The same thresholds for every
  tier. Your robot-wire guard stays; every row goes through `standard_rate.rate_limited_runner`. `run_retimed` can
  insert a BuzzWirePolicy script at a source row and stop the replay there. `reference_policy` uses it when recipe.json
  has a `retime` entry.
  - Segments must start after the regrasp holds the wand (medium holds at row 2572, hard at 2687): a hard segment
    starting at 2600 compressed the regrasp and the wand was never picked up (`exp/R1h4_start2600`).
  - Traverse alone (rows through traversal complete; `exp/R1m1-4`, `R1h2-4`):

    | tier | factor | rows | touches | min clearance | guard |
    |---|---|---|---|---|---|
    | medium | 1x | 18990 | 0 | 0.567 mm | (logged only) |
    | medium | 2x | 10972 | 0 | 0.567 mm | 3 slow-downs |
    | medium | 3x | 8292 | 0 | 0.567 mm | 3 slow-downs |
    | medium | 4x | 6942 | 0 | 0.567 mm | 3 slow-downs |
    | hard | 2x | 11238 | 0 | 1.023 mm | 0 |
    | hard | 3x | 8418 | 0 | 1.027 mm | 0 |
    | hard | 4x | 7015 | 0 | 1.016 mm | 0 |

    The re-timed runs never come closer than your own path (medium's closest approach, 0.567 mm, runs at 1x under the
    guard). The traverse is not the hard part; your terminal regrasps are.
  - Your terminal regrasps are open loop and do not survive compression: terminal 2x (and 3x on hard) end with the wand
    released and quiet but 3-8 mm / 31-64 deg from the finish (`exp/R2m3e2`, `R2m4e2`, `R2h4e2`, `R2h4e3`).
- **medium: passes, graded 1/1 (O2-8).** Recipe: traverse 2600-18960 at 4x; at source row 19388 (end of the
  post descent; the held wand is right above the finish, dx 0.15 / dy 0.1 mm, but 16.9 mm high, 52 deg, not supported)
  the held wand is lowered 2.5 mm (body move, 1 s) before your recorded release; your three terminal regrasps as
  recorded.
  - Release study from your 1x post-descent state (`exp/Y6a-c`, server `Y6s`): unlowered, your release lets the wand
    touch the wire 0.6 s later; lowered 0.1, 0.2, 0.3, 0.5, 1, 1.5, 2, 2.5 or 3 mm it lands supported, released and
    quiet; lowering 1 cm, or until supported, makes the hand touch the wire at about 3.4 mm. Yaw +5/+10 deg: the hand
    touches; yaw -5 deg without lowering: the wand touches; yaw -10 deg would clip a joint. Kinematic robot-to-fixed
    clearance (`BuzzIK.clearance`): 2.1 mm unlowered, 1.3 mm at 1 mm, 0.6 mm at 2 mm, 0 at 3 mm. Waiting 0.5, 1 or 2 s
    before your release without lowering still touches: the lowering itself, not the delay, avoids the touch.
  - With your terminal: 1x path, 3 mm, 2 mm and 2 mm + yaw -5 deg finish (`Y6s` f1, f20, f5); 4x path, 2.5 and 3 mm finish, 2 mm
    does not (no touch, but 7.3 mm / 61 deg at the end) (`exp/R2m4e1d25`, `R2m4e1`, `R2m4e1d20`). So the binding window
    on the 4x path is about 2.5-3.3 mm: 2.5 mm keeps 0.9 mm to the hand-wire touch (kinematic clearance about 0.3 mm)
    and up to 0.5 mm to the regrasp failure at 2 mm. Deterministic, but your open-loop terminal is the fragile part.
  - Full run through the Harbor callback (`exp/Z7m`): native success at 438.4 s sim, 17536 rows (was 29544), largest
    arm step 0.0252 rad, 0 touches, min clearance 0.567 mm, 45 min end to end on lab incl. a 4.3 min scene build.
  - Grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_bz_medium2`): privileged **1** (17536 rows, 438.4 s
    sim, 2 CPU replays deterministic, strict goal, 0 hold steps; live oracle 45.4 min end to end in Harbor, verifier
    84.5 min) and standard **1** (live and replay success, 17536/17536 rows streamed, live matches replay, 0 hold
    steps; agent 41.3 min). The grade reproduced `exp/Z7m` exactly.
  - v18 check (`exp/H14m`, `H18m`): the graded privileged trajectory replayed in a fresh process on 0.2.14 (graded
    package) and on v18 (labv18/rcb-topogym:0.2.16-dev-cu128, cand_v18 package): Session.state_sha identical after
    every one of the 17536 rows, success at row 17536 on both, minimum wand-wire clearance 0.5668 mm at row 3651 on
    both (the per-row clearance series equal).
- **hard: passes, graded 1/1 (O2-9); over the 72 min rule, accepted by the user.** From your last held placement (row 43434: 4.72 mm / 11.5 deg) your
  recorded retreat drags the wand to 5.023 mm / 8.0 deg; opening in place leaves 4.59 mm / 11.5 deg (`exp/Y7s` h1-h4).
  The drag happens in your first 23 retreat rows (43472-43495). Stopping your rows after 43486 / 43489 / 43492, then
  opening fully and retreating 4 cm along the approach axis: native success at 4.72 mm / 9.7 deg, 4.85 mm / 8.9 deg,
  4.97 mm / 8.2 deg; after 43483 the angle stays 10.3 deg. Chosen: 43489, **margins 0.15 mm and 1.1 deg** - thin;
  deterministic CPU physics reproduces them, but they are not robust to any change of the path or the physics.
  - Traverse factor with this finish (`exp/R3h2`, `R3h3`, `R3h4`, `R2h4e1`): 2x success at 4.45 mm / 9.3 deg (35163
    rows), 3x success at 4.88 mm / 8.8 deg (32344 rows), 4x fails: the faster traverse changes the outcome of your
    open-loop regrasps (the wand ends 8.7 mm / 5.9 deg from the finish with or without the finish). 1x through the
    Harbor callback (`exp/Z8h`, the same insert/stop code path as the grade): success at 1090.6 s sim, 43626 rows,
    99 min end to end.
  - O2-9 recipe: traverse 2750-19674 at 3x, terminal as recorded, stop after source row 43488, then the finish above.
    Lab run (`exp/R3h3`): native success at 808.6 s sim, 32344 rows, 0 touches, minimum clearance 1.027 mm, 87 min end
    to end on lab: over the 72 min rule (compressing the terminal breaks it). **The user accepted this 87 min
    reference execution (2026-10-05), as for fiber hard** (measured on the lab tree with image 0.2.14-dev; the v18
    estimate is below). Finish margins on this path: 0.12 mm and 1.2 deg.
  - Time per row (lab `exp/P1h`, the 3x replay's first 3834 rows at load 24): 0.125 s, of which Session.step (physics
    and recording) 0.113 s, the clearance guard 0.004 s, observation/policy/limiter 0.008 s; scene build 2-5 min. So
    the 32344-row hard reference takes about 69-72 min at that load and 87 min under the heavier load of `exp/R3h3`
    (0.151 s/row). With v18's buzz step (92 -> 74 ms, x0.80 on Session.step): about 0.103 s/row, 56 min of rows plus
    the build, about 58-61 min end to end at load 24 and about 71 min at R3h3's load.
  - v18 check (`exp/H14h`, `H18h`): the graded privileged trajectory (32344 rows) replayed in a fresh process on 0.2.14
    and on v18 (labv18/rcb-topogym:0.2.16-dev-cu128, cand_v18 package): Session.state_sha identical after every row,
    success at row 32344 on both, minimum wand-wire clearance 1.027 mm at row 7834 on both.
  - Grade (`oraclefix2/tree/runs/test_results/harbor_grade_of2_bz_hard2`): privileged **1** (32344 rows, 808.6 s sim,
    2 CPU replays deterministic, strict goal, 0 hold steps, no review or forcing events; live oracle 74 min end to end
    in Harbor incl. the scene build, verifier 152 min) and standard **1** (live and replay success, 32344/32344 rows
    streamed, live matches replay, 0 hold steps; agent 72.8 min). The grade reproduced `exp/R3h3`'s outcome; the
    graded live run took 74 min against the lab's 87 min because the lab host was busier then.

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

## 4. horseshoe_ring below-easy (very_easy, easier): scene review, oracle, grades (2026-10-06)

William's 10-02 drafts (`topogym/tasks/horseshoe_ring/below_easy.py`, `horseshoe_ring_{very_easy,easier}.py`, their settled
layouts) had no oracle and were never built. Lab work: `/DATA2/qineng/rcb/topogym_v1/hsbe/` (JOURNAL.md, `exp/`, `bin/`).

- **Difficulty review (the user's rule: very_easy < easier < easy).** The section check of `below_easy_witness.py` (the
  ring's bore against the shoe's 137.8 x 24.8 mm section along the chain axis, 90 phases 2 deg apart):

  | tier | bore | passing phases | best clearance |
  |---|---|---|---|
  | very_easy | 144 x 144 mm | 90 / 90 | 3.05 mm |
  | easier, draft | 146 x 120 mm | 27 / 90 | 4.03 mm |
  | **easier, now** | **146 x 136 mm** | **61 / 90** | **4.04 mm** |
  | easy (enlarged ring) | 142.6 x 135.9 mm | 53 / 90 | 2.34 mm |

  The draft easier ring passed at fewer phases than the current easy ring (the draft was designed against the original
  easy ring, 135 x 128 mm, which passes at none). Only the short axis changes: 146 x 136 mm passes at more phases than
  easy and with more clearance, and still needs a turn at the other 29 (witness design "easier": route certified at
  90 deg with 1.04 mm, the slide at 0 deg collides; start entangled, span crossings 3/3).
- **Physics.** The draft easier layout was not settled (ring still moving at 4 mm/s and 0.06 rad/s after its 5 s settle).
  The new layout: the template assembly spawned 1 mm above the table and settled 8 s on CPU (2.5 ms x 4, robot at home)
  in the v18 image; the ring comes to rest next to the left shoe after about 2 s (final speeds below 0.03 mm/s). very_easy
  keeps William's layout (settled). Instances: built by your candidate pipeline (`topogym_merge_candidate.py`,
  `topogym_candidate_pipeline.py --phase build`) in candidate `hsbe/tree2/runs/test_results/cand_hsbe_v2`; birth
  state_sha very_easy cd53c55076a70899, easier cddcb02aa13b01be, identical in two independent builds.
- **Image.** The easier change is public source (`topogym/tasks`, `topogym/assets/resources`), so the v18 image (built
  from be53c149e) does not contain it. The grades ran on `hsbe2/rcb-topogym:0.2.16-dev-cu128` = your
  `images/topogym/Dockerfile` built from 7f0b002cc plus this change (every other build input identical to cand_v18b's
  snapshot; all layers before `COPY topogym/` from the v18b build cache), warmed with `warm_cache.py` on these two
  instances. The next release image needs a rebuild to carry the easier scene.
- **Oracle.** Your easy oracle (`gravity_release_table_pickup_stages`: shoe grasps, fold, suspended release, table
  pickup, placement) with per-tier inputs in `reference_data/horseshoe_ring/{very_easy,easier}/` (manifest-pinned;
  below-easy recipes may not reuse another tier's files, `ci_checks/test-harbor-below-easy.py`):
  - `reference.json`, `fold.json`, `support.json`: the easy tier's, with the below-easy assembly template in
    reference.json (only the ring differs; `load_reference` checks it);
  - `grasps.json`: the easy grasp poses (within 0.07 mm and 0.12 deg on these instances), the left hand fully open
    (27 mm) on its descent: with 18 mm the inner left finger enters the larger ring standing next to the left shoe
    (1.9-15 mm contact in the approach recheck);
  - `approach.json`: planned and checked on each frozen instance (`hsbe/bin/hs_be_plan.py`, as
    `run_horseshoe_policy.py` plans it);
  - rows clamped to the standard step limit (O2-6).
  - `harbor_bridge/below_easy.py`, `catalog.BELOW_EASY_FAMILIES` and `references.py` dispatch horseshoe_ring's
    below-easy tiers to `horseshoe_ring.public_session`.
  - very_easy's placement (`place_ring` gets an optional `tracking_m`, 0.5-5 mm, default 2 mm as before): the larger
    ring is carried 2-4 mm off the placement route (2.0 mm at 20 %, 3.1 mm at 31 %, peak 4.09 mm at 32 %), so a 2 mm
    or 3 mm gate stalls the route clock (`exp/X2_very_easy`, `X3a`); very_easy's recipe sets 4 mm, with which the
    route completes after a short hold at the peak (`X3b`). A thin margin: deterministic on CPU, not robust to path
    changes. A 20 mm ring-grasp backoff instead loses the ring binding (`X3c`).
  - Lab runs (the Harbor callback in a frozen privileged Session on the graded instances): very_easy native success at
    334.0 s sim, 13362 rows, 48 min end to end (`X3b`); easier at 353.6 s sim, 14143 rows, 50.5 min (`X2_easier`);
    no row clamped, largest arm step 0.0372 rad.
- **Grades** (your unchanged `run_harbor_oracle_grades.sh`, `--tiers very_easy,easier`; candidate `cand_hsbe_v2`, image
  `hsbe2` above; lanes `hsbe/tree2/runs/test_results/harbor_grade_hsbe_{very_easy,easier}`): all four pass.

  | tier | privileged | standard | rows | live min (priv / std) | verifier min (priv) |
  |---|---|---|---|---|---|
  | very_easy | 1 | 1 | 13362 | 48.4 / 24.3 | 56.8 |
  | easier | 1 | 1 | 14143 | 51.3 / 25.7 | 56.0 |

  - Privileged: both replays deterministic, strict goal reached, hold 0, review 0, forcing 0.
  - Standard: live and replay success, live_matches_replay 1, hold 0.
  - One execution takes about 48-51 min, under the 72 min rule.
  - Visual check of the easier replay video: shoes grasped, fold, suspended pair, ring on the table with the remainder
    held up by the right arm, ring carried to the goal; at the end the ring is inside the dashed goal region and the
    remainder is away from it.

## 6. Below-easy orbits, blanket_flatten and knot_untying of your 7571e4194: lab grades and findings (2026-10-06)

Every below-easy oracle that 7571e4194 provides for these three families, graded on lab in both modes with your
launcher (`run_harbor_oracle_grades.sh --tasks-root <candidate>/tasks`). Lab work: `/DATA2/qineng/rcb/topogym_v1/obe/`
(`JOURNAL.md`, `bin/`, `exp/`, grades in `tree_g/runs/test_results/harbor_grade_obe_*`). No change to your tasks, rules,
graders or runtime. Commits on 7571e4194: 01245b248 (your launcher accepts orbits: case list and
`check-oracle-portability --families` choices, test in `test-harbor-oracle-launcher.py`) and the next one (two orbits
oracle fixes with unit tests, this section).

- **Setup.** Image `obejw/rcb-topogym:0.2.16-dev-cu128` = your Dockerfile on 7571e4194 with the v18 build args (runtime
  source fc5ac3e1, tooling a9d09d66), candidates from your merge / pipeline scripts; builds, fresh-process restores and
  nops pass. Your blanket corner-fold archives are `cuda_sm89_mp128_*` and `require_compatible` refuses them on lab's
  sm120 GPUs, so both states were prepared again on lab with your `prepare_blanket_initial_states.py` (same tick counts
  and layouts as yours) and passed with `--blanket-initial-state`; `topogym_merge_candidate.py` then needs torch, so it
  ran inside the image.
- **Grades** (every line deterministic 1, grader_error 0, infra_error 0, forcing 0):

  | family / tier | privileged | standard | rows | where it stops |
  |---|---|---|---|---|
  | blanket_flatten very_easy | **1** (only inside the replay hold) | 0 (live strict 0) | 1454 | settled gate: one chattering particle, below |
  | blanket_flatten easier | 0 | blocked | 633 | `lay_half: assisted grasp lost`, edge ratio 1.3014 > 1.3 |
  | knot_untying very_easy | **1** (strict at row 848) | **1** | 848 | none; live 18-20 min, rope speed 0.973 mm/s at worst (limit 1) |
  | knot_untying easier | running at commit time (`harbor_grade_obe_knot_untying_very_easy_easier`) | | | |
  | orbits very_easy | 0 (twice) | blocked | 99 / 238 | row 99: action past a joint limit; row 238: first align (both fixed below) |
  | orbits easier | 0 | blocked | 195 | first align (fixed below); cut afterwards, below |

  blanket easier: the lab state matches yours (coverage 0.4112, top 30.5 mm); `lay_half` ending at x -0.29 or -0.28
  instead of -0.305 still loses the grasp (1.3020 / 1.3009), so the peak is not set by the final x. Left for you.
- **blanket very_easy: one particle never reads settled** (read-only probe `bin/ob_bprobe.py`, `exp/bprobe2`). The sheet
  is flat (coverage 0.978) but particle 7458 reports 33.04 mm/s from 0.75 s after the release to the end, the same in
  every run and both Harbor replays. It is not assist state: it is not in the only binding (27 particles centred 7944),
  it is free (w = 1/m) and unlinked at acquisition, release and end, nothing is non-free or linked after the release, and
  the v18 cached admission matched the pre-cache reference on all 81 compared `candidates()` calls. It is a PBD 2-cycle:
  every 0.625 ms substep stretch/bending moves it about 50 um and the self-collision projection (with its position-based
  friction) puts it on the other of two points 20.65 um apart; Genesis reports the last substep's (pos - ipos) / dt, so
  33 mm/s at a fixed end-of-tick position. Its partners (1887, 7338, 7579; rest 8.5-18 mm) sit at 7.96-7.99 mm, right at
  the 8 mm particle-size collision threshold, in a crumpled spot by the laid corner. Privileged passes only through the
  0.08 m/s replay tolerance and standard fails the strict 0.03 m/s gate. Options (yours / the user's, not changed): a gate
  speed from end-of-tick displacement (about 0 here), or a `fold_layout` stage for very_easy as easier has.
- **orbits fixes (this commit, `planning/orbits/native_session.py`):**
  - `submit`: the IK put the left forearm roll at its model limit, one float32 step past the public range
    (`Action would be clipped by the public robot adapter`, very_easy row 99); an excess of at most 1e-4 rad is clamped,
    anything larger still raises.
  - `grasp_one` align: on a cord resting on the table or the fixture base, the pads stop 1.6-5 mm above the cord centre
    (still descending after the 0.3 s settle, then held by the support), so `bias += cord - contact` aims below any pose
    with the 0.5 mm support gap (`No close contact pose above the support surface`, both tiers' first align). Now an
    update with no support pose keeps only its in-plane part, and from then on the loop converges on the in-plane error.
    Natively the very_easy left leg grasp then aligns, pinches and lifts (1.2 mm grasp error), and easier's 0.65 grasp
    too.
  - Unit tests in `ci_checks/test-orbits-native-oracle.py`; both fail on 7571e4194 with the lab errors.
- **orbits, where it stops now (not fixed):** very_easy's right-arm approach row fails your own collision check
  (`inter_arm` gap 0.47 mm < 1 mm) with the left hand at its standoff (y 0.105, z 0.075); runs with a wider or higher
  standoff were stopped before that point (speed, below). easier is cut: in `fresh_bight_carry` the grasp error grows from
  14 to 23 mm and the episode ends (`connection_or_volume_invalid`, cord crushed 0.25 s, volume ratio -0.075), so the ring
  pass needs route work.
- **orbits speed: a task-level decision for you and the user (nothing changed).** One control step is 10 IPC ticks of
  2.5 ms (Newton 1e-3, PCG 1e-5). Your native oracle runs at 7.8 s per step on an idle GPU (host load 26), the same as
  under load; physics alone (grading replays) 3.7-5.2 s per step, and the rest is the oracle's per-row checks. Your
  very_easy route comes to about 2500-3300 rows: 5-7 h live and 3-4 h per replay, against the 72 min rule and close to
  the whole 6 h budget, so even a working oracle fails speed acceptance. The likely lever is a profile like rope's
  regular tiers (`contact_relaxed_v16`: one 40 ms IPC frame per step, Newton 3e-3 / PCG 3e-5, a coarser softer mesh,
  finger-only robot contact), which brought rope to 0.156 s per step near rest (orbits easy: 2.5 s on the same benchmark)
  and rope medium to 33 min end to end. Rough bound, not measured: 4-10x on the physics (one solve per step instead of
  10, each needing more Newton iterations), so 0.5-1 s per step and 25-55 min for the route, plus about 2 h of oracle
  checks unless they are trimmed. It changes the physics the scenes were settled and checked with (your eps_velocity
  0.001 calibration, birth states, difficulty), so scenes and oracle would need re-validation.
- **orbits births** (checked on the v1 instances; your v2 adds only eps_velocity 0.001): the profile equals orbits easy's,
  the goal is not met at birth and the difficulty words order as very_easy 1 < easier 2 < easy 4 ball letters. With the
  libuipc default eps_velocity 0.01 a cord at rest creeps 2.0-2.5 mm/s (10 mm in 5 s, above the 1 mm/s goal limit);
  0.001 gives 0.37-0.54 mm/s and 0.0001 0.06 mm/s. The original orbits tiers still use 0.01 and creep about 2 mm/s.
