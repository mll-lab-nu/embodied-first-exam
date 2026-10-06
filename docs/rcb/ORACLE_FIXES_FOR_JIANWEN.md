# Oracle fixes for the non-crash failures of the ba01d029c oracle sweep (oraclefix, 2026-10-04)

Companion to `HANDOFF_FOR_JIANWEN.md`. Base: origin/dev/jianwen **ba01d029c**. Every change is private oracle code in
`topogym/planning/**`. No task rule, threshold, success predicate, grader, standard service, oracle bridge or public
simulator file changed, so the public source identity and the image stay as built from ba01d029c.

- Patches: `/DATA2/qineng/rcb/topogym_v1/oraclefix/patches/0{1..8}_*.patch` (README.md there). Each is a `git diff`
  against pristine ba01d029c, applies on its own with `git apply` from the repo root, and touches no file of another
  patch or of the sweep's FIX 2/4/5 (06 includes the sweep's FIX 6 hunk of `interlocked_claws/object_oracle.py`: the
  visual-glb tolerant witness identity). 02 and 03 import the module that 01 adds; 01, 02 and 05 import 07's module.
  `09_d5e71_harbor_birth_branch.patch` is against your later head d5e71c6ae (section 7b). All eight of 01-08 also apply
  exactly to the merged-v16 head 7293af9d6 (section 9).
- Grading: your own `bash_scripts/run_harbor_oracle_grades.sh` (unchanged), run on lab through
  `oraclefix/bin/run_lane_of.sh` (only GPU pin, 10.233.x subnets and container labels, on a task copy).
- Tree: `oraclefix/tree` = ba01d029c + the sweep's FIX 2/4/5/6 (= `jianwen_ba01_fix`) + patches 01-06.
- Image: the sweep's `labba01fix` build (same id c48b794cd687, also tagged `oraclefix/...`).
- Lane outputs: `oraclefix/tree/runs/test_results/harbor_grade_of_<lane>/`. Diagnostics (never grades):
  `oraclefix/exp/E*`, `oraclefix/evidence/`.

## Final status, 2026-10-06 (v18): every in-scope oracle passes in both modes

All 33 tasks outside orbits and slotted now have an oracle that passes your grading in both modes (the last two
results, fiber hard standard and the v18 blanket hard standard, landed 10-06 ~03:40). orbits x3 and
slotted x3 still have no oracle; they are yours. Nothing failed in the final runs.
The sections below are the history of 10-04 and 10-05. Where they still say "running" or "pending", this
section supersedes them.

- **Release:** merged-v18 (tooling 18, image 0.2.16-dev) at `8d7d16489`. Oracle-only commits after it: `42e4237ce`
  (buzz hard, O2-9) and `960092527` (docs).
- **Final oracle sweep:**
  - Code: lab tree = exact copy of `8d7d16489`.
  - Packages: `cand_v18b`, built from `be53c149e`. Its release identity equals the pushed tree. Your `require_task`
    rejects `cand_v18` under that tree, because your below-easy sources change the source hash.
  - Instances: all 39 are identical to `cand_v18` (state_sha and sim config).
  - Grading: your `test_harbor_oracles.py --candidate --no-nop --execute`, both modes.
- **Live minutes:** the Harbor agent phase, including about 2 min of setup, under the sweep's shared load (up to 10 CPU
  lanes at once; blanket x3 together on one GPU). Rule: one execution <= ~72 min (20 % of 6 h).

| family | easy (priv / std) | medium (priv / std) | hard (priv / std) | graded on |
|---|---|---|---|---|
| cast_coil | 1 / 1 (9 / 7 min) | 1 / 1 (10 / 8) | 1 / 1 (9 / 7) | v18 sweep |
| cast_keyhole | 1 / 1 (32 / 21) | 1 / 1 (29 / 19) | 1 / 1 (36 / 23) | v18 sweep |
| hedgehog_in_cage | 1 / 1 (23 / 12) | 1 / 1 (4 / 3) | 1 / 1 (11 / 8) | v18 sweep |
| interlocked_claws | 1 / 1 (4 / 1) | 1 / 1 (2 / 2) | 1 / 1 (31 / 22) | v18 sweep |
| horseshoe_ring | 1 / 1 (38 / 19) | 1 / 1 (40 / 20) | 1 / 1 (43 / 19) | v18 sweep |
| lock_picking | 1 / 1 (13 / 10) | 1 / 1 (23 / 17) | 1 / 1 (27 / 20) | v18 sweep |
| buzz_wire_3d | 1 / 1 (19 / 13) | 1 / 1 (37 / 33) | 1 / 1 (74 / 73) | v18 sweep; hard: see below |
| fiber_bundling | 1 / 1 (22 / 17) | 1 / 1 (56 / 44) | 1 / 1 (185 / 152) | v18 sweep; hard: v17 |
| blanket_flatten | 1 / 1 (10 / 9) | 1 / 1 (23 / 20) | 1 / 1 (60 / 48) | v18 sweep |
| rope_threading | 1 / 1 (26 / 21) | 1 / 1 (33 / 27) | 1 / 1 (34 / 27) | v18 post-build grades |
| knot_untying | 1 / 1 (26 / 23) | 1 / 1 (62 / 55) | 1 / 1 (71 / 65) | v18 post-build grades |
| orbits, slotted_post_ring | no oracle | no oracle | no oracle | - |

- **v18 post-build grades:** `cand_v18` from the v18 stack before its rebase. The rope and knot oracle code behaves
  the same at `8d7d16489`: your merge only adds the below-easy joint limit, which is `None` for these tiers.
- **Determinism:** every privileged grade above has its two fresh-process replays bit-identical to each other and to
  live. Every standard live run reproduces in its recorded replay.
- **rope medium:** first standard pass. It failed on ba01/v16 at zero margin.
- **buzz hard (O2-9):** graded in both modes on image 0.2.14 (the d5e71 tree), not on the v18 tree.
  - The graded trajectory (32344 rows) replays bit-identically on the v18 image: every per-row state hash, the
    success row and the minimum wand-wire clearance (1.027 mm) are equal.
  - buzz medium was checked the same way (17536 rows) and then graded on v18.
  - Details in `ORACLE_FIXES_2_FOR_JIANWEN.md`.
- **fiber hard:** v17 grade.
  - Privileged passed (live 185 min), the first fiber hard pass.
  - Standard passed too (live 152 min), fiber hard's first standard grade.
  - CPU physics are bit-identical from v17 to v18. Only fiber has an entity above 64 DOFs, and v18 changes no
    CPU-family dynamics.
- **blanket hard, final oracle (11 + 11b + 11c):**
  - 11, `779cc5f43`: lays out the folded corner.
  - 11b, `c6d5860c3`: slides along the base clearance. The robot_clear violator was the fixed base cover, not the
    gripper.
  - With 11 + 11b, v17 privileged passed at row 4075. The standard twin refused row 229: 0.0439 rad, above the
    0.04 rad step limit, coming from the stage-A contact IK re-solve.
  - 11c, `bfd06f77f`: sends blanket rows through 01's standard-rate limiter. Easy and medium are unchanged row for
    row; hard gains one step.
  - v17 result: both modes pass at 4855 rows. Live minutes 113 / 93, on a shared GPU without v18's speed-ups. The
    replays are strict at row 4855. The standard stream had n_clipped 0 and hold 0. live_sha is equal across modes.
  - v18 sweep: both modes pass (live 60 / 48 min; the privileged run shared its GPU with blanket easy/medium at first;
    about 30 min alone).
  - v18's blanket speed-ups are byte-identical to v17 (actions, phases, physics steps, task_result, substituted state
    hashes).
- **Over 72 min, accepted by the user:**
  - fiber hard: 185 min.
  - buzz hard: 74 min graded, 87 min on a busier host. v18 estimate 58-71 min.
- **hedgehog very_easy and easier (10-06):** both now have an oracle and pass both modes on v18. See section 10.

Open items for you:
- **Two CI tests fail after your merge `b1ab6b18d`.** They fail with or without v18, and we did not touch them.
  - `test-harbor-simple-policy-context` (your new test) expects:
    - a dict grasp_assist, but `actions.py` builds it with `dataclasses.asdict` (FIX 2);
    - a proof birth on the restored branch 1 to be rejected, but FIX 5 accepts it at state 0 / physics step 0. Your
      `"session"` mode solves the same problem.
  - `test-cast-keyhole-oracle` also fails on `a8bbd5c12`: `public_row` reads `session.action_layout`, and the test's
    fake session has none.
- **The helper repo is still on v17.** v17 images record agent_sessions / resets / sim_steps as 0, because the
  warm-up baked `RCB_SESSION_LOG=` into the image. v18 fixes this (`76fbec69a`). Rigid instances are identical
  between v17 and v18, so moving the helper to v18 keeps results comparable.
- **Below-easy knot / orbits:** their settled IPC states need v18's deterministic pyuipc. The knot oracles were tuned
  under 2.5 ms full Newton, so re-validate them under K2.
- **Verifier time (suggestion only):** the two privileged replays run one after the other. Running them in two fresh
  processes at once would still meet the protocol's ">= 2 replays", and would halve the CPU families' verifier time.

## Grading change decided by the user (2026-10-05): R-hold. This is not an oracle fix

- Rule: in privileged mode each grading replay may confirm within the same tolerant hold of at most 2 s that v16
  already gives the standard mode, with the same coverage / quiet slack (`rcb_topogym.REPLAY_TOLERANCES`). No replay has
  to meet the strict goal within the rows any more. The live run stays strict.
  - This replaces v16's "at least one strict replay" rule. The recording ends on the live success tick, so that replay
    had zero margin for agents and oracles alike (section 9).
- Patch (its own commit):
  - `harbor_templates/topogym/unlimited/tests/grade.py` drops `and goal is not None` from the success predicate. It
    still reports `strict_goal_reached` / `strict_goal_row` and adds `strict_replay_required: 0`.
  - `ci_checks/test-topogym-grading-replay.py`: the "tolerant passes alone fail" test becomes "...pass".
  - The oracle harness (`harbor_bridge/verification.py`) honours `strict_replay_required`.
  - The block comment in `rcb_topogym.py` still describes the old rule. It is left unchanged so the tooling identity
    stays the same.
- It changes the task packages' `tests/`, so it takes effect through the next candidate build and release. Agent
  trials already recorded can be re-graded from their trajectories.
- Validation:
  - your `ci_checks/test-topogym-grading-replay.py` passes with the patch (26 tests, 1 skipped);
  - re-scoring every existing privileged verdict with v16 grading records (`oraclefix/bin/rescore_rhold.py`), the
    recorded grade equals R-now in every case, and R-hold flips exactly one case:

| case | replay hold steps | strict goal | recorded | R-now | R-hold |
|---|---|---|---|---|---|
| lock_picking easy (`v16_lock_em2`) | 0 / 0 | replay 1, row 4732 | 1 | 1 | 1 |
| lock_picking medium (`v16_lock_em2`) | 1 / 1 | none | 0 | 0 | **1** |
| lock_picking hard (`v16_lock_hard`) | 0 / 0 | replay 1, row 7476 | 1 | 1 | 1 |
| blanket_flatten medium (`v16_blanket_medium`) | 21 / 0 | replay 2, row 1299 | 1 | 1 | 1 |

## Bundle for dev/jianwen: every planning-side fix your head d5e71c6ae (and v16 7293af9d6) still lacks

One push after the oracle sweep (the user's decision, relayed by the lead): a series of focused commits on top of
dev/jianwen, fetched first, fast-forward only.
- Location: laptop worktree `tmp/2026-10-04_oraclefix/bundle_d5e71_wt` (detached; nothing pushed yet), patch exports
  in `oraclefix/bundle_d5e71*/`.
- Every item is in `topogym/planning/**`. Graders, thresholds, success predicates, the service and the tooling are
  untouched, so the release identity and the image do not change.
- Each patch applies on d5e71c6ae in order, and every touched module imports in your gs121 venv.

| # | fix | files | validated by |
|---|---|---|---|
| 1 | sweep FIX 2: `SessionPolicyRunner` gives `policy.initialize` `grasp_assist`, `mode`, `observation_spec` | `harbor_bridge/actions.py` | lock oracle cannot start without it (`KeyError: 'mode'`); lock 1/1 on v16 for easy and hard |
| 2 | sweep FIX 5: proof birth = state 0 at physics step 0 on the restored branch | `solvability.py` | fiber (sweep); buzz easy on your head |
| 3 | sweep FIX 6: claws witness identity ignores visual `.glb` exports | `interlocked_claws/object_oracle.py` | claws 3/3 both modes |
| 4 | 09: buzz `validate_session` / `CompiledJointPolicy` accept the Harbor birth on branch 1 | `buzz_wire_3d/reference_policy.py`, `compiled.py` | buzz easy privileged 1 on your head |
| 5 | 01 (+01b): standard-rate limiter; keyhole uses it | `standard_rate.py` (new), `cast_keyhole/*` | keyhole 3/3 both modes |
| 6 | 03 (03e): knot rate limiter, crush guard, servoed hover gate | `knot_untying/robot_oracle.py` | knot easy 1/1; medium 03e live success (replays running) |
| 7 | 04 (04f): rope finish gate + quiet gate | `rope_threading/{relay_policy,public_session}.py` | rope medium privileged 1 |
| 8 | 05 (+05c, 05d code): horseshoe gate R1 persistence, retreat tolerance, limit margin, RRT retreat | `horseshoe_ring/*` | horseshoe medium 1/1 |
| 9 | 06 (+06b): claws droop start, hard 0.04 rad/s | `interlocked_claws/*` | claws 3/3 both modes |
| 10 | 08: lock rows within the standard joint-step limit | `lock_picking/runner.py` | lock hard standard stream unclipped |
| 11 | 12: the harness checks grades against the v16 rules (strict goal, review hold) | `harbor_bridge/verification.py` | lock medium v16: a correct 0 was reported as evidence_failed |
| 12 | 14: the standard twin holds its last row up to 2 s until `done` (as an agent can) | `harbor_bridge/runtime.py` | lead decision; used in the v16 re-grades |
| 13 | 10: buzz easy turn_2 candidates widened (selection re-pinned) | `reference_data/buzz_wire_3d/easy/*`, `manifest.json` | buzz easy privileged 1 on your head |
| 14 | 13: compiled buzz joint targets 1 urad inside the limits | `buzz_wire_3d/compiled.py` | medium carries past row 13749 |
| pending | 11: blanket hard lays out a measured folded corner (one-hand stage), longer settle | `blanket_flatten/{robot_oracle,routes}.py` | live success, coverage 0.989; replays running |
| pending | 04g: rope quiet gate closed-loop on the Task's speed | `rope_threading/relay_policy.py` | rope hard live success; replays running |
| optional | 05d easy recipe (active ring pickup) | `reference_data/horseshoe_ring/easy/recipe.json`, `manifest.json` | did not make easy pass; the second oracle agent works on horseshoe easy/hard |

- Not in the bundle:
  - 07 (lab shim; your `_query_state` already restores the same fields);
  - 02 (our buzz planner tail; your reference data supersedes it);
  - 15 (rate-limited buzz stages; it broke your release, see section 7b);
  - sweep FIX 4 (task code).

Status at 22:52 CDT (grades come from your launcher; privileged = oracle + 2 verifier replays):

| oracle | tier | privileged | standard | patch | evidence (`oraclefix/tree/runs/test_results/...`) / state |
|---|---|---|---|---|---|
| cast_keyhole | hard | **1** | **1** | 01 | `harbor_grade_of_kh_hard` (20191/20191 rows streamed, 0 restarts) |
| cast_keyhole | medium | **1** | **1** | 01 | `harbor_grade_of_kh_medium` |
| cast_keyhole | easy | **1** | **1** | 01 + 01b | `harbor_grade_of_kh_easy2` (01 alone: 0, goal-transfer preflight collision, `harbor_grade_of_kh_easy`; section 1) |
| interlocked_claws | easy | **1** | **1** | 06 | `harbor_grade_of_claws_easy` |
| interlocked_claws | medium | **1** | **1** | 06 | `harbor_grade_of_claws_medium` (regression check of 06) |
| interlocked_claws | hard | **1** | **1** | 06 | `harbor_grade_of_claws_hard` |
| knot_untying | easy | **1** | **1** | 03 | `harbor_grade_of_knot_easy3` (both replays passed despite the thin live margin, section 2) |
| knot_untying | medium | 0 (03d); 03e: live SOLVED at 51.44 s (gate window), verifier replays running | - | 03 | `harbor_grade_of_knot_medium2`: native success at 48.81 s after a crush-guard relax, but the hover never settled in its band, so the window opened during the plain release; neither replay succeeded within the recording (noise). Rerun with 03e: `knot_medium3` |
| knot_untying | hard | 0 | - | 03 | `harbor_grade_of_knot_hard2` (03d, terminal v5): the live oracle succeeds (final_settle after the gate's lift, row 2516); ba01 strict = 0 from zero-margin IPC replay noise (neither replay succeeded within the 2516 rows; the 2 replays took 5.9 h). Needs v16 grading. It is rerun once under v16 grading after the knot-hard precision settings (between the current setting and MuJoCo-like) are validated |
| rope_threading | hard | 0 (04d, 04f); 04g queued | - | 04 | `harbor_grade_of_rope_hard2` (04d): replay 1 no success within the 2922 rows, replay 2 at row 2917 (noise). `harbor_grade_of_rope_hard3` (04f): the quiet gate engaged, but success (row 2916) came while it was still closed, so the wave did not keep the rope loud; neither replay succeeded. 04g (closed-loop wave, section 2): `rope_hard4`, queued |
| rope_threading | easy | 0 (04d); 04f queued | - | 04 | `harbor_grade_of_rope_easy` (04d): replay 1 succeeded 19 rows before the live run, replay 2 not within the recording (noise). Rerun with 04f: `rope_easy2`, queued (IPC slot) |
| rope_threading | medium | **1** (04f) | 0 (04f) | 04 | `harbor_grade_of_rope_medium2` (04f): live success at row 2897 after the finish gate (1.0 s wait, max 4.27 mm/s vs 10), both replays succeeded (2900 / 2897 steps). Standard: stream live success at row 2894, the single grading replay no success within the 2894 rows (zero-margin noise). 04g rerun `rope_medium3` queued (GPU 3, lowest priority). Earlier `harbor_grade_of_rope_medium` (04e): 0 |
| horseshoe_ring | easy | 0 | - | 05 (+05c/05d/07) | `harbor_grade_of_hs_easy` (ring stays on the lower shoe after the release), `harbor_grade_of_hs_easy2` (active pickup + shim: no checked ring grasp). Not fixed: needs an active disentangling step (section 6) |
| horseshoe_ring | medium | **1** (05 + 05c + 07) | **1** | 05 + 07 | `harbor_grade_of_hs_medium2`. Without the shim (`harbor_grade_of_hs_medium`): 0, live success but both CPU replays without success = BUG 7 (section 6) |
| horseshoe_ring | hard | 0 | - | 05 + 05c + 07 | `harbor_grade_of_hs_hard` (clipped forearm_roll in place_ring, fixed by 05c), `harbor_grade_of_hs_hard2` (with the shim the shoes stay hooked on the lifted ring). Not fixed: needs an active disentangling step (section 6) |
| buzz_wire_3d | hard | not fixed | - | 02 | traverse fixed (E14a/c); unplanned tails touch the wire (E20h/E20h2); the post planner finds no candidate after 1-6 steps (E25h/E25h2) |
| buzz_wire_3d | easy | 0 (02e-02h) | - | 02 | `harbor_grade_of_buzz_easy` (0: original drop touches the post); `harbor_grade_of_buzz_easy2`..`5` (02e-02h: traverse and post descent clean, then the original finish regrasp found no collision-free IK goal for the open-hand transfer). Iteration stopped there (lead): your head d5e71c6ae ships its own buzz data (section 7b) |
| buzz_wire_3d | medium | blocked | - | - | needs your uncommitted `runs/test_results/buzz_staged_inputs_20260929/medium_traverse_guide.json` (section 7) |
| buzz_wire_3d (your head d5e71c6ae) | easy / medium / hard | 0 / 0 / 0 at step 0; with 09: easy 0 (turn_2 planning), medium / hard running | - | 09 | Harbor sessions start on branch 1; three freshness checks refuse that (section 7b). With 09 easy runs 9 stages, then `TURN_2` has no collision-free candidate from the Harbor-measured grasp (`harbor_grade_of_buzzd5g_easy`) |

## 1. cast_keyhole standard: the privileged reference was faster than the standard service allows (patch 01)

- Root cause: the standard service moves an arm joint target at most `JOINT_STEP_LIMIT_RAD` = 0.04 rad per control step
  and spreads a faster row over extra steps; `runtime.stream_standard` refuses any such slowed row. The privileged
  keyhole Session has no such limit, and EE_ABS IK steps of the keyhole policy exceeded it on 56 / 62 / 60 rows (easy /
  medium / hard). They reached up to 0.058 / 0.098 / 0.072 rad, mostly the home reorientation and the regrasp wrist
  turns. One row on the new run asked for a 0.46 rad jump. The standard twin therefore stopped at its first chunk
  (grade 0 in 3 min).
- Fix: `topogym/planning/standard_rate.py` (new). `RateLimiter.step(row)` reaches the row from the Session's current
  (guarded) targets along the same straight joint-space segment, in ceil(reach / 0.039) ordinary `Session.step` calls.
  Grippers switch on the first call, as in the service. Rows within the limit stay one step, unchanged.
  `rate_limited_runner()` is `SessionPolicyRunner` with that executor, and the keyhole runner uses it. The privileged
  trajectory is then the standard reference as recorded: no resampling in the bridge, no change to the limit.
- Results: hard and medium graded 1 in both modes (`harbor_grade_of_kh_hard`, `harbor_grade_of_kh_medium`). The hard
  standard stream executed all 20191 reference rows natively with 0 restarts.
- easy, a side effect with a separate fix (01b): with 01 the easy privileged run failed in planning ("Goal transfer
  failed native IK or full mesh preflight"). The planned straight system-side move of the held gold piece grazed the
  silver piece just above it: frames 55-57 of 60, gold 13.5 cm below silver.
  - 01 changes the timing of 56 rows, which shifts the separated end state by a little.
  - The same instance with the unpatched ba01 planning passes this preflight and succeeds natively at 497.7 s (E17u),
    so the plan's margin there is marginal, and 01 only exposed it.
  - 01b (`cast_keyhole/kinematics.py`, `policy.py`, `runner.py`): the preflight tries the original move first, then
    the same move lowered by 2 cm and by 4 cm; about 12 cm of table clearance is left there.
  - The policy executes the drop that passed (`gold_drop_m`, default 0). Medium and hard pass with drop 0 and are
    unchanged.
  - Rerun: `harbor_grade_of_kh_easy2`.

## 2. Zero-margin replays (knot easy privileged, rope hard standard; patches 03 and 04)

- Why "hold rows after the first success tick" cannot work: `Session.step` ends the episode on the first success tick.
  Later steps are no-ops and are not recorded, and the standard service also stops there. A recorded trajectory
  therefore always ends on the live run's first success tick. A fresh GPU replay is not bit-identical under IPC, so it
  passes only if it reaches success on or before that very tick.
- Measured on lab with diagnostic replays of your graded trajectories (per-tick logs:
  `oraclefix/evidence/E1_knot_easy_settle_summary.txt`, `E2_rope_hard_settle_summary.txt`):
  - knot easy: after the release, the rope's max node speed sits at 0.96-1.1 mm/s, with tail stick-slip bursts up to
    7 mm/s for ~8 s; only then does it calm to 0.83-0.88 mm/s. The quiet limit (1 mm/s) equals the rope's IPC friction
    smoothing velocity (`contact_eps_velocity = .001`), so noise around the limit decides the first 0.5 s window. The
    replay's window completed 1-2 ticks after the live one, which is exactly the verifier's grade 0.
  - rope hard: its quiet limit is 10 mm/s (instance task_parameters). The free tail's swing decays 15 -> 4 mm/s across
    the limit at 74.0-74.2 s; across the graded runs, success fell on rows 1862-1871.
- Fix: the window must start on a robot motion with the rope already quiet with margin (a "gate"):
  - knot (03): before the last holder releases, the free arm hovers its closed fingertips 0.45-0.85 mm above an
    isolated strand. That is inside the 1 mm active-clearance rule and outside the 0.2 mm IPC contact distance. The gap
    is servoed every control step on the Task's own `evaluate_robot_contact` measure, using only that arm's colliders.
    The holder releases, and the rope must stay calm (<= 0.9 mm/s at every sampled step) for 1 s, max 25 s. Then a
    40 mm/s lift from the commanded hover pose opens the window on that motion. An earlier version lifted from the
    measured TCP, which sags below the command: the fingertips first moved down and the rope rebounded. That version
    is superseded.
  - rope (04): in the final relay group, when exactly one crossing is still missing, the relay pauses. It waits until
    every node stays below half the Task's quiet limit for 1 s (max 20 s), then finishes the last segment at half
    speed. The success tick therefore follows a slow motion of an already calm rope. An earlier "wiggle" gate
    escalated and disturbed the threading; it is superseded. The finish gate is tier-independent, so it also covers
    rope medium (zero margin in the sweep) and easy.
- Results so far:
  - rope hard (04d): native success through the finish gate. The gate engaged at relay sample 611, waited 1.0 s (max
    node speed 0.67 mm/s against the 10 mm/s limit), and the last segment ran at half speed. Graded 0: replay 1 did not
    succeed within the 2922 recorded rows, and replay 2 succeeded at row 2917. The last crossing still appears during
    the slow completion at a noise-dependent row.
  - 04e (quiet gate, one bounded attempt): once the relay is complete, the holding hand keeps the rope near it moving
    at twice the quiet limit (a vertical triangle wave a few mm high), so the 0.5 s window cannot open. It continues
    until the threading has been complete (unambiguous, thickness clear) and every node more than 6 cm from the hand
    has stayed under half the limit for 1 s. Then the hand stops at its final pose.
    - Queued as `rope_hard3`; rope medium also runs with 04e.
    - If 04e still lands on noise, these tiers need replay-tolerant grading (v16: live strict, replay tolerant with a
      <= 2 s hold, dev/jianwen 186e42515).
    - Result (04f, the corrected trigger): rope hard live success at row 2916 while the gate was still closed. The
      hand's 20 mm/s triangle wave did not keep the max node speed above the 10 mm/s limit, and neither replay
      succeeded (`harbor_grade_of_rope_hard3`).
    - rope medium with 04f (`harbor_grade_of_rope_medium2`): graded **1**. Live success came at row 2897 after the
      finish gate (1.0 s quiet wait, max 4.27 mm/s), and both replays succeeded (2900 / 2897 steps).
    - Correction: in both 04f runs (medium2, hard3) the relay report ends in `quiet_gate:closed`. So the gate did
      engage at the threading, but the Task's 0.5 s window completed while the hand was still waving: the commanded
      20 mm/s triangle wave did not lift the Task's own measure (max node speed of the whole rope) above 10 mm/s.
      Medium passed anyway, because both replays happened to succeed in time.
    - 04g (bounded, one hard run): the wave is closed-loop on that measure.
      - After 3 consecutive closed-gate ticks at or below the limit, the commanded hand speed grows x1.25 per further
        quiet tick (cap 8 x the limit, i.e. ~2 cm strokes), so the window is reset before it can complete.
      - The hand height is integrated, the gate still opens only at the final pose, and every closed-gate tick is
        traced in `tracking.quiet_gate_trace`.
      - An offline mock of the gate keeps the window from completing for near-hand coupling down to 0.15 of the hand
        speed.
      - Nothing before the gate changes. Medium's ending would change in the same way (its success also came during
        the closed gate).
      - Patch `oraclefix/patches/04g_rope_quiet_gate_closed_loop_on_04f.patch`, tree `oraclefix/tree_04g`, lane
        `rope_hard4`.
    - Conclusion so far: under ba01's strict grader, rope success timing stays noise-bound unless 04g holds the window
      off; whatever still lands on noise needs v16's replay-tolerant grading (final).
  - knot easy (03d): native success, but it came during the hover wait, not after the lift. At the success tick the
    Task's active clearance was 1.0005 mm (limit 1 mm) and the rope speed 0.979 mm/s (limit 1 mm/s), so the margin is
    still thin. Cause: the hover was not servoed while the holder released (1.6 s), and near the band it could only
    descend 50 um per step, so the gap drifted above the band.
  - 03e (prepared): the hover is servoed on every control step while engaged, including the holder's release; band
    0.4-0.7 mm; descent up to 0.2 mm per step; the report also dumps an unfinished gate. It is used for the next knot
    run if a verifier replay of 03d misses.

## 3. knot medium: R2 (rope crushed for 0.25 s) during the end spread (patch 03)

- Root cause: in `straighten`, after the crossings reached 0 (34.0 s), the spread continued for 2 more increments with
  both ends squeezed to 5 / 6 mm. The pads inverted rope elements for 0.25 s at 36.1 s (min volume ratio -0.09).
- Fix (crush guard): while a pull or spread is active, the runner reads `Session.safety()` every control step. A
  continuous inversion of 30 ms stops the motion, opens both jaws to 7 mm (no squeeze of the 8 mm rope) for 0.25 s, and
  then releases as usual. When the crossings are already 0, the release goes through the gate of section 2. R2 itself
  is unchanged; the transients that hard tolerates (<= 12.5 ms) do not trigger the guard.
- Result: lane `harbor_grade_of_knot_medium2` (03d) running.

## 4. knot hard under terminal v5 (patch 03)

- Re-tested under terminal v5 with 03 (rate limiter, crush guard, hover gate): lane `harbor_grade_of_knot_hard2`
  running.

## 5. interlocked_claws easy and hard: piece/piece guard stops (patch 06)

- Observation: `guards.py:81` stopped the oracle at control step 41, the first separation step: piece/piece contact
  6.387 N > 5 N. With the separation joint speed lowered from 0.2 to 0.08 and to 0.04 rad/s (E12a/E12b), the stop is
  identical (6.387 N, same state hash). A gentler separation motion therefore cannot help; the force does not come
  from the separation speed.
- Root cause: the first separation row is the measured post-acquisition posture. Under the held pieces the wrists
  droop 12 mrad (wrist angle target -0.3789 rad, measured -0.3666 rad, both arms). Commanding the measured posture
  moves both wrist targets 12 mrad onto the sagged pose, both arms sag further in one step, and the interlocked
  pieces press together.
- Fix: the guard's existing integral tracking correction starts at the measured droop (actuator target - measured
  joints, per arm) instead of zero. That is the integral's own fixed point, so the first command equals the current
  hold target and the plan is followed from there exactly as before. The 5 N guard is unchanged; it was not arbitrary,
  only the command step was wrong.
- Native check (E13, same image and frozen instances): easy succeeds with piece/piece max 0.0 N over the whole
  separation (was 6.4 N at step 41), and medium succeeds.
- hard stops later, at physics step 56700 (separation step ~5630 of 8257): 5.536 N in the sweep's own f6 run without
  06, and 5.587 N with 06. So 06 is not the cause, and the stop is a separate one. The plan's piece/piece gap there is
  ~10 mm (min 6.1 mm), so the contact comes from execution. Variants (E15, all with 06):
  - separation at 0.04 rad/s instead of 0.08: native success, piece/piece max 0.0 N over all 16137 steps (405 s sim,
    27 min wall);
  - wrist feedforward (`wrist_feedforward=True`) at 0.08: success, but max 4.69 N, i.e. 6 % under the guard;
  - relative servo (`relative_servo=True`): worse, 14 N at step 1200.
  Patch 06 therefore also sets hard's separation speed to 0.04 rad/s (`public_session.py`; easy 0.2 and medium 0.1
  unchanged), which is the "gentler separation" option. The 5 N guard stays.
- Results: easy 1/1 (`harbor_grade_of_claws_easy`); medium 1/1 with 06 as a regression check
  (`harbor_grade_of_claws_medium`); hard: lane `harbor_grade_of_claws_hard`. Experiments: `oraclefix/exp/E12a`, `E12b`
  (speed does not matter), `E13e/m/h` (droop start), `E15a/b/c` (hard variants).

## 6. horseshoe_ring: oracle-internal contact limits stricter than the grading rules (patch 05)

- easy / medium, free-hand retreat (`manipulation.py`): after the upper shoe is released, the left fingers still rest
  on it (FCL depth 58.0 / 61.5 um). The planner allowed the resting depth + 1 um along the retreat. All 29 candidate
  directions exceeded that at their first 1.3 mm sample: +1.1 um (+x) up to +2.2 mm (+z, the shoe rests on the
  finger). So "no checked free-hand retreat" was raised although no candidate needed more than a graze (the sweep's
  `planning/support_release_002/free_hand_plan.json`). Fix: allow 0.2 mm beyond the resting contact. That is far inside
  the ordinary planning allowance (0.8 mm) and the task rule R1 (1 mm for 0.25 s, 3 mm at once).
- hard, stage gate (`stages.py`): `task_contact_within_stage_limit` failed any physics tick above 1 mm, which is
  TopoGym's retired any-tick rule. The run failed in `gravity_settle_folded` at physics ticks 50053-50055: 1.27 / 1.21
  / 1.01 mm for 7.5 ms, target_ring against right/upper_forearm_link. The tooling's R1 accepts that: a non-held task
  contact fails above 3 mm at once, or once it stays above 1 mm for 0.25 s; held fingers 4 / 2 mm. Fix: the gate keeps
  its own limits (1 mm, or 0.8 mm without native screening) but applies R1's persistence over consecutive monitored
  ticks. The same applies to the held-finger check (4 mm at once / 2 mm for 0.25 s). It reads
  `rcb_topogym.CONTACT_RULE` when that module is loaded. `task_not_failed` (the Session's own R1 verdict) is still
  checked every tick.
- Results:
  - medium: native success, verifier replays running (`harbor_grade_of_hs_medium`).
  - hard: passed every stage up to `place_ring`, including the one that failed before. After 487 s in `place_ring`
    (ring inside the goal, progress 0.9987) the bridge refused the next row, "Action would be clipped by the public
    robot adapter": a joint or gripper target outside the public limits. E19h reruns hard with a wrapper that prints
    the offending column before re-raising; the bridge itself is unchanged.
  - easy: the retreat now plans (+y 8 cm, peak 65.8 um), but the following exit check `ring_is_separated` failed. The
    +y retreat dragged the released shoe, which rests on the finger, 36 mm along; the shoe then dropped 6 cm and the
    ring stayed where it was relative to the lower shoe.
  - Your accepted easy proof (2026-10-03, `from_home_09`) had no resting finger contact at the release; under the
    current rules the finger rests on the shoe (58 um). E18a/E18b retry easy with the oracle's own options, as the hard
    recipe uses: `joint_release_retreat`, and `release_turn` 60 deg.
  - Results: with the joint retreat (E18a) the outcome is the same. The upper shoe hangs 61.6 mm below the lower one
    and the ring stays on the lower shoe (+41.5 mm). In medium the upper shoe dropped to -89 mm and pulled the ring off
    to the table.
  - The 60 deg tool-axis release turn (E18b) is unreachable ("Unreachable EE pose").
  - Release turns: +30 deg is unreachable (E18h). -30 deg executes, but the ring still does not separate (E18i).
  - Active pickup (E18g, no shim): easy with the hard recipe's ring pickup (`joint_release_retreat` +
    `active_ring_pickup`, then `grasp_ring` with `release_support`) grasps the hanging ring and releases the support.
    The released right hand then had no checked joint retreat; 05d adds the RRT fallback for that retreat.
  - With 05 + 05c + 05d + 07 (`harbor_grade_of_hs_easy2`): the release outcome changes, and there is "No checked ring
    grasp from the supported physical state". The release outcome is chaotic: the 07 shim makes the live run
    bit-exact with its replay, but different from the earlier unshimmed live runs, and the hanging-ring geometry flips.
- easy and hard, conclusion (bounded effort, not fixed): after the support release the outcome depends on which way
  the hooked bodies fall. That is chaotic and must be replay-exact (07), so a fixed recipe passes or fails by luck.
  These two tiers need an active disentangling step after the release, with a measured check and a retry (tilt or
  shake the held body until the measured separating gap is >= 5 mm), not a parameter.
- medium, a replay problem (BUG 7, fixed by 07):
  - The live run succeeded at its last row (10554). Both CPU replays are identical to each other (deterministic) and
    have no success after the same rows.
  - Genesis entity FK/IK queries on the live rigid solver restore links_state / joints_state / dofs_state / qpos by
    re-running FK, which leaves them 1e-17..1e-16 off (the sweep's BUG 7 evidence:
    `jianwen_v15_lab/evidence/bug7_kinematics_query_live_state`). Horseshoe queries IK every control step, so the live
    run drifts from its replay.
  - Patch 07 (`topogym/planning/exact_kinematics.py`, lab-validation only; the runtime fix is dev/jianwen 7293af9d6)
    applies the fix7b targeted copy-back from the planning side. Horseshoe and buzz kinematics import it. Smoke test:
    an FK query then leaves all eight solver arrays bit-identical.
  - E21m compares the old live run with a replay tick by tick. The rerun is `harbor_grade_of_hs_medium2`.
- hard, place_ring (05c): the refused row had left/forearm_roll = 3.141580104827881. IK returned exactly the 3.14158
  limit, float32 rounds that outward, and the public limit is 3.1415798664. 05c keeps every horseshoe joint target
  1 urad inside the joint limits. Rerun: `harbor_grade_of_hs_hard2` (05 + 05c + 07). The rerun no longer reaches
  place_ring. In the old unshimmed run the ring was already free at the contact lift (separating gap +126 mm at
  2 mm). With the shim the shoes stay hooked on the lifted ring (gap -23 mm at 2 mm, -44 mm at 8 cm), so "Contact
  lift did not separate the ring". It is the same chaotic release outcome as easy; see the conclusion below.

## 7. buzz_wire_3d (patch 02: partial)

- **Root cause for your buzz references on Harbor (read first).** Your audited buzz references were recorded under
  different integration settings than the Harbor instances run, so hand-tuned candidates and compiled open-loop joint
  actions do not transfer.
  - Recorded (`recipe.json` `source_config`): CPU fp64, `physics_dt_s` 0.025, 40 solver substeps, control decimation 1.
  - Harbor instance (`instance.json`): CPU fp64, `physics_dt_s` 0.0025, 4 substeps, decimation 10.
  - The substep length is the same (0.625 ms), but each 25 ms control step is 1 physics step on your runs and 10 on
    Harbor's. Controller, grasp-assist and contact processing therefore run 10x more often, and the measured states
    drift from the audited run.
  - Consequences seen here: easy's tuned turn_2 candidates have no collision-free option from the Harbor-measured grasp
    (section 7b).
  - The durable fix is to re-record (or re-tune) the references under the Harbor instance's physics. Patches 09 and 10
    only remove the Harbor-session freshness refusal and widen one candidate set.

- Patch 02 makes every recorded row respect the standard joint-step limit (rate limiter, as in 01). It also widens the
  route search: after the original first candidate, the planner's own `world_orientation_neighbors` (and roll sectors)
  are tried before the finer lattices. Execution was not changed (the tail is as you wrote it). No buzz tier is graded
  1 yet.
- easy (not fixed): after the route, the hand meets the finish deck about 3 cm before the ring passes the end of the
  vertical end post (E6), so the tool has to be dropped. The dropped tool spins (~2 rad/s at release), its handle lands
  first, the wand pivots, and the ring strikes the bottom tip of the post: `wire_touched`
  (`oraclefix/evidence/E10_buzz_touch.json`). None of the release variants tried avoided it (`evidence/E6*`, `E8*`):
  in-place opening, a slow 2 s opening, your audited easy recipe's release (open while retracting 10 cm in 0.2 s),
  re-centring the ring before the drop, and tool tilts 0/20/30/45 deg. Lowering further instead (a "seat on the deck"
  tail, an earlier version of 02) stalls at route cursor 0.955 (E5): the hand blocks it before the tool rests. The easy
  tail is therefore unchanged.
- medium (not fixed, missing input): with the acquired grasp the bundled planner finds no complete route
  (`evidence/E3_buzz_medium_plan_variants.jsonl`, `E7m_variants.jsonl`, `E9m*_variants.jsonl`). Every rejection is
  robot-vs-wire clearance, not the table guard or IK limits:
  - 8 mm spacing stops at progress 0.146-0.149 (widths 4/12/24, with or without world neighbours).
  - World neighbours + roll sectors (width 24) plans, but refinement dips to 0.40 mm at progress 0.202 (limit 0.5 mm).
  - 4 mm spacing stops at 0.867-0.869.
  Your successful medium came from the staged recipe (`buzz_wire_3d/stages.py:279`). That recipe follows
  `runs/test_results/buzz_staged_inputs_20260929/medium_traverse_guide.json` (sha256 4511df68...). The file was never
  committed (not in any commit of robot_coding_bench) and is not on lab, and the Harbor callback (`runner.py`) does not
  use it. Committing that guide under `harbor_bridge/reference_data/buzz_wire_3d/medium/` and letting the runner
  follow it would most likely fix medium.
- hard (planner fixed, execution not yet): with world-orientation neighbours the route plans (249 coarse frames, min
  clearance 1.0 mm) and refines (2540 frames). The run then traversed for 114 s and touched the wire at route progress
  0.78 (sim 189.1 s, cursor 1.64 m, 0.16 m before the finish). There the plan's clearance is only 0.82-1.1 mm
  (`evidence/buzz_hard_planner_fix_*`), 40 % of the refined frames are below 3 mm, and at the touch the arm was:
  - 0.079 rad (max joint) away from the plan's checked redundant branch: `CheckedJointPolicy` seeds the IK with
    0.98 x measured + 0.02 x planned joints (`joint_seed_fraction` .02), so the null space drifts;
  - lagging its command by up to 0.04 rad (wrist, 0.4 rad/s).
  E14 tests the policy's existing options for the route part only: `joint_seed_fraction` 1.0 (IK seeded on the
  checked branch), `clearance_tracking_fraction` 0.5 (progress paced by the plan's clearance), and both:
  E14b (pacing only) still touched at 197.6 s.
- Tail lab (E20h/E20e/E20e2, `oraclefix/bin/buzz_tail_lab*.py`): it runs the oracle to the start of the tail,
  checkpoints there (Env segment checkpoint plus the Session counters), and tries tail variants from that same state.
  - The original tail reproduces `wire_touched`: during `lower_on_finish_post` for hard, at the release drop for easy.
  - Turning the ring about its centre to align it with the vertical end post fails three ways: the robot touches the
    wire (hard), the target needs a joint at its limit (the bridge refuses the clipped row), or the pose is
    unreachable (easy).
  - Lowering easy's ring straight down the post with its orientation fixed stalls after ~2.4 cm: tracking error
    1.8 mm with no wire touch, i.e. the tool is blocked by the finish support.
  - Geometry, easy: at the end of the traverse the ring normal is 62 deg from the vertical post (centred clearance
    about 4.5 mm), the handle is horizontal, and the post runs from z 1.1706 to 1.0726 above a deck at 1.0621.
  - hard, staged variants (E20h2, 7 tails): every tail touches the wire with the gripper within 0.2-0.5 s, even a
    straight 1 cm/s descent along the post axis with the orientation fixed. Touches are 0-5 um deep, on the
    `gripper` part, against the incoming wire near the top of the post. At the route end the gripper sits within
    ~2 mm of the wire (plan clearance 1.9 mm), so no unplanned motion from there is safe.
  - Planned tail (02e): `BuzzIK.plan_post` continues the route down the end post as a beam search in 3 mm steps.
    The ring stays centred on the rail; per step the orientation changes by at most 8 deg about any axis, or takes
    a guided step towards the resting finish orientation. Checks are as in plan_route: wand and robot >= 1 mm from
    the fixed toy, joint margin >= 5 mrad, no branch jump. It stops 7 mm above the wire's end, inside the 1 cm
    completion tolerance.
    - The runner appends these frames to the route plan, so the joint-seeded following runs on down the post.
    - The policy then opens the gripper over 1 s in place (`post_release`) instead of the original tail. The original
      finish regrasp (re-grasp the resting tool, move it to the finish support pose) follows unchanged.
    - Lab E25e (easy, 3 variants): planned in 29-33 s, min clearance 1.2-1.4 mm. All three reached the bottom with no
      touch (cursor 0.9952 of 0.9954 m), supported, released and quiet. They are 7 mm and some degrees from the
      finish pose; the finish regrasp closes that.
  - Earlier conclusion (now implemented as 02e): the tail has to be planned like the route. Extend the collision-checked IK
    search (BuzzIK.plan_route machinery, robot and wand gaps >= 1 mm, joint continuity) over the end reserve, i.e. the
    last ~10 cm of wire, the vertical post. Execute it with the same joint-seeded following, then open at the bottom
    with the ring around the post just above the deck. For easy the planned tail must also turn the handle towards
    the rest pose within the Panda's joint limits. The original tail's straight moves (and its 6 cm drop) cannot meet
    the no-touch rule. E14a (seed 1.0) and E14c (both) completed the whole traverse without a
  touch. Both then ended `wire_touched` 1.5 s into the original tail `lower_on_finish_post`: the plan ends with the ring
  tilted [66.9, -46.2, -45.3] deg from the wire frame, and the tail moves straight to 6 cm above the end with a further
  20 deg tilt. Patch 02 keeps seed 1.0. The tail and easy's drop remain open.
- Last of our iterations: 02f-02h tried rest clearances 4/8/12 mm, a finish-orientation stop 7 mm above the end, and
  a 1 s release. In `harbor_grade_of_buzz_easy5` (02h) the run traversed and released cleanly at 134.8 s, then the
  original finish regrasp raised "No collision-free IK goal for open-hand transfer" (`runner.py:256`). We stopped
  there (the lead's call), because your head d5e71c6ae ships complete buzz reference data for all three tiers
  (section 7b). If that passes, patch 02 is history.

## 7b. Your head d5e71c6ae on Harbor: sessions start on branch 1 after restoring the frozen birth (fix 09)

- Graded with your unchanged launcher on a pristine d5e71c6ae tree (`jianwen_d5e71`), image built by your launcher
  (`oraclefix/rcb-topogym:0.2.14-dev-cu128`, 824f9b3331bc). All three tiers ended at step 0, before any action:
  - easy / medium / hard (`harbor_grade_of_buzzd5_*`): "Buzz reference requires a fresh, unrewound Buzz Session"
    (`reference_policy.validate_session`, the `branch_id != 0` term).
- Cause: the Harbor bridge's tooling Session restores the frozen birth once at construction (every episode, live or
  replayed, starts from that restore). `SimulatorEnv._restore` puts the restored state on a new branch, so the first tick
  is branch_id 1, state_id 0, physics_step 0. Every check that equates "fresh birth" with branch 0 refuses a Harbor
  session. The sweep's BUG 5 (fiber, ba01) was the same thing in `solvability.py` and was never pushed.
- With only the `validate_session` term relaxed (`jianwen_d5e71_fix`, `harbor_grade_of_buzzd5f_*`), the next check stops
  each tier, again at step 0:
  - easy (staged proof): "A proof execution must start at the fresh episode birth"
    (`solvability.py:156`, `QualificationWorkflow(mode="proof")` from `harbor_bridge/callbacks.run_stages`);
  - medium / hard (compiled joint policy): "Compiled policy requires consecutive ticks from episode birth"
    (`buzz_wire_3d/compiled.py:26`).
- Fix 09 (one item, three checks; `oraclefix/patches/09_d5e71_harbor_birth_branch.patch` against d5e71c6ae). The birth
  is state 0 at physics step 0 on the branch the owner restored, and "not rewound" means still on the birth's branch:
  - `solvability.py`: the sweep's fix5 patch (`jianwen_v15_lab/fix5_files/fix5_ba01_proof_birth_branch.patch`, applies
    unchanged): proof start checks state_id 0 instead of branch 0, continuation checks the birth's branch, and the
    continuity verdict checks state_id 0;
  - `buzz_wire_3d/reference_policy.py` `validate_session`: state_id 0 instead of branch 0 (no steps, no resets and
    physics step 0 as before);
  - `buzz_wire_3d/compiled.py` `act`: at the first action the state must be state_id 0, and its branch is recorded;
    every later tick must be on that branch (and at index x decimation physics steps, as before).
  No grading code changed. The public source identity is unchanged (same 325-file source sha 12f7c4fc..., same image).
- Other `branch_id == 0` checks in planning that a Harbor run might meet the same way (not on the buzz path, not
  changed): `cast_keyhole/oracle_artifacts.py:74`, the audits of blanket_flatten, horseshoe_ring, hedgehog_in_cage,
  interlocked_claws, fiber_bundling, buzz_wire_3d, and `lock_picking/robot_audit.py:139`.
- Rerun with 09: `jianwen_d5e71_fix/runs/test_results/harbor_grade_of_buzzd5g_{easy,medium,hard}`.
  - easy (`buzzd5g_easy`): privileged 0. 09 works, the freshness checks pass, and 9 staged-proof stages pass
    (pickup, regrasp, traverse, flatten_above_finish, release_onto_deck, acquire_1, turn_1, partial_release,
    acquire_2; 82700 physics ticks).
    - turn_2 then fails in planning: "No collision-checked terminal turn from the measured grasp"
      (`recipes.checked_turn`).
    - `TURN_2` tries only yaws 164 / 163 / 161.5 x three xy offsets, tuned to your audited run. That run was CPU fp64 at
      25 ms x 40 substeps; the Harbor instance runs at 2.5 ms x decimation 10. The measured grasp after acquire_2
      therefore differs, and none of the 9 candidates is collision-free.
    - Both replays of the 8270 rows: no success. Possible fix (not applied): a wider `TURN_2` candidate set; later
      hand-tuned stages may need the same.
  - easy, one bounded round (lead): `turn_2`'s candidates were widened in the reference selection
    (`run_stages` takes each step's parameters from `reference_data/buzz_wire_3d/easy/selection.json`, not from
    `recipes.TURN_2`).
    - Your 3 tuned yaws come first, then 155-170 deg in 0.5 deg steps (nearest 163 first), over your 3 offsets plus a
      5 x 5 grid (x 0 / +-1.5 / +-3 mm, y 0 / 1.5 / 2 / 3 / 4.5 mm): 31 x 26 candidates. `checked_turn` and its checks
      are unchanged.
    - `selection.json` is re-pinned in `recipe.json`, and both are re-pinned in `manifest.json`; your
      `references.reference_data()` and `load_reference("easy")` checks pass.
    - Patch `oraclefix/patches/10_d5e71_buzz_easy_turn2_candidates.patch`. Lane `harbor_grade_of_buzzd5h_easy`
      (running). If a later hand-tuned stage breaks the same way, that is the end of it (no further rounds).
  - easy with 09 + 10 (`buzzd5h_easy`): **privileged 1**.
    - All 11 stages pass; turn_2 took yaw 161.5 (yours) with xy offset (3, 3) mm (a new grid offset).
    - Both CPU replays succeed at row 8665 (identical sha). Live oracle execution was 28.9 min end to end.
    - Standard 0: the twin stopped at row 1621, "Standard service clipped or rejected reference actions" (a row above
      the service's per-step joint limit, as keyhole 01 / lock 08).
    - Fix 15 (tried, then reverted): `run_stages` took an optional runner, and the buzz staged reference ran its stages
      through the standard-rate limiter of 01.
      - In `harbor_grade_of_buzzd5j_easy`, `release_onto_deck` then failed 66 ticks in: the slowed release let the
        tool touch the wire (`no_tool_wire_touch`, `task_not_failed`), and the stage's exit check hit
        `KeyError: 'traversal_complete'`.
      - Your release drops the tool with a 10 cm retraction in 0.2 s, faster than the standard 0.04 rad per step
        allows; done slowly, the tool catches the wire.
      - So buzz easy is **privileged 1 / standard 0**. A standard-executable easy reference needs a release designed
        under Harbor's physics and the standard limit. Fix 15 is reverted; it is not in the bundle.
  - medium with 09 + 13 (`buzzd5i_medium`): the open-loop actions carry past row 13749 (no limit refusal), but the
    reference ends without Task success, as hard does.
  - medium with 09 (`buzzd5g_medium`): 0. The compiled actions ran 13749 of 29544 rows; then the bridge refused row
    13749, where joint 7 is commanded exactly at its limit (-2.8973), which the adapter's float32 check rounds outward.
    - Fix 13: `CompiledJointPolicy` keeps every joint target 1 urad inside the action spec's limits (as horseshoe 05c).
    - Rerun: `harbor_grade_of_buzzd5i_medium`, which also shows whether your open-loop actions carry past 46 % under
      Harbor's physics.
  - hard with 09 (`buzzd5g_hard`): 0. The compiled open-loop actions ran all 43568 rows (no wire touch, no limit
    refusal) and ended without Task success ("Complete Buzz reference ended without current Task success").
  - Evidence that the open-loop medium/hard references do not transfer to the Harbor physics: hard runs to the end
    without success; medium is pending (`buzzd5i_medium`). A closed-loop buzz oracle for medium/hard (following the
    wire from privileged state under 2.5 ms x 10) is being written by the second oracle agent
    (`ORACLE_FIXES_2_FOR_JIANWEN.md`).

## 8. Baselines of the ba01 sweep's held-back heavy lanes (run here on the lead's request)

| oracle | tier | privileged | standard | note |
|---|---|---|---|---|
| lock_picking | hard | 1 | 0 | `harbor_grade_of_base_lock_hard`: "Standard service clipped or rejected reference actions"; one reference row steps 0.0417 rad (arm column 4). Patch 08 (01's rate limiter in lock_picking/runner.py) |
| lock_picking | hard (08) | **1** | 0 | `harbor_grade_of_lock_hard2`: 08 fixed the clipping (all 7485 rows streamed, live success at row 7485 = its last row, 0 restarts), but the grader's GPU fp32 replay had no success within the rows (progress 0, live_matches_replay 0): zero-margin replay noise, needs v16's replay-tolerant grading |
| lock_picking | easy (08) | 0 | - | `harbor_grade_of_lock_easy`: live success at its last row (4743; 13 rows slowed by 08), neither GPU replay succeeded within the recording: replay noise, needs v16's replay-tolerant grading |
| lock_picking | medium (08) | 0 | - | `harbor_grade_of_lock_medium`: live success at its last row (6120); replay 2 succeeded at 6120, replay 1 did not (GPU noise): needs v16's replay-tolerant grading |
| blanket_flatten | medium | 0 | - | `harbor_grade_of_base_blanket_medium`: clean live success at row 2088 (coverage 1.000, max speed 1.8e-13 m/s); replay 1 succeeded at row 1953 (135 rows early), replay 2 not within the recording: GPU PBD replay noise, needs v16's replay-tolerant grading |
| blanket_flatten | easy | **1** | **1** | `harbor_grade_of_base_blanket_easy` (baseline, unchanged oracle; both replays success with progress 1.0) |
| blanket_flatten | hard (sweep lane, analysis) | 0; with 11: live success (coverage 0.989), replays running | - | Not an oracle-rule issue: the route leaves the far-left corner folded; the fold crest jitters (PBD self-contact) and the folded corner costs coverage (0.942 vs v16's 0.95). See section 8b |

## 8b. blanket_flatten hard: why the window never completes (E24, diagnostic only)

- Live run (`jianwen_ba01_fix/.../harbor_grade_all_20261004_ba01_blanket_flatten_hard`, `oracle_report.json`): after
  stage B and the 60 s settle, all five gates were true and the final settling check passed only at the very last tick
  (`stable_time_s` 0.0025). Final metrics: coverage 0.9417 (ba01 limit 0.90, v16 0.95), max height 12.3 mm, max speed
  26.4 mm/s.
- E24 (`oraclefix/exp/E24`): replay of that trajectory, logging every 2.5 ms tick of the last 60 s plus a 20 s hold
  with no robot motion.
  - In the hold, 5.6 % of ticks have a particle above 0.03 m/s: 126 distinct particles, spikes p50 45 / p90 80 / max
    221 mm/s.
  - The spiking particles sit 5-12 mm above the table, a second cloth layer. The longest clean stretch is 1.08 s, and
    the median gap between spikes is a few ticks.
- Where: projected into the replay's final frame (`oraclefix/evidence/E24_blanket_hard_spikes.png`), every hold-phase
  spike lies on the crest of the folded far-left corner (the diagonal edge near the left arm) or at its end on the left
  edge.
  - Stage B's left pull does not lay that corner out on these physics, and the folded corner is also what costs the
    coverage.
  - This is the effect your MEDIUM note describes: "Folds left on the table keep jittering under PBD self-contact, so
    the Task's settled gate never holds; the route must lay every edge out."
- So the cause is the oracle's final configuration, not the rules.
  - Proposed fix (not run: it needs hours of a GPU that tonight's agent trials hold): a stage C that grasps the fold
    crest nearest the far-left corner, drags it outward past the flat position at 10 cm so the folded flap hangs
    below the hand, then lowers while moving back about 3 cm and releases 3 cm above the table (your MEDIUM recipe).
  - Alternatively, re-tune stage B's left `pull` / `lower` so that corner opens, followed by a longer settle.
- One bounded try (lead, 23:10): patch 11 (`oraclefix/patches/11_blanket_hard_fold_layout.patch`, `robot_oracle.py` +
  `routes.py`; it also applies cleanly on d5e71c6ae, whose blanket planning equals ba01's).
  - After the route's last stage and a 25 s relax (`HARD.fold_layout`), `fold_stage` fits the sheet's flat pose (a
    rigid 2-D fit of the rest coordinates onto the single-layer core).
  - Particles more than 3 cm off that fit are folded. The corner with the most folded particles (at least 25 within
    15 cm of material) is laid out with the nearer hand, in one extra one-hand stage.
    - Flap on top: grasp its tip and turn it back like a page onto its flat position (stage A's motion).
    - Flap tucked: grasp the raised crest, drag it outward past flat at 10 cm, then lower while moving back 3 cm (your
      medium recipe).
    - Release 3 cm above the table. An unreachable fold stage is skipped.
  - The final settle grows from 60 to 90 s.
  - The stage loop's two-hand code is generalised to "the hands of this stage"; for stages A/B it is identical.
  - Offline synthetic check: flat -> no stage; folded over -> page turn of the tip; tucked -> crest drag.
  - Lane `harbor_grade_of_blanket_hard_c`: **the live oracle succeeds**.
    - Stage C found the far-left corner folded (239 of 596 folded particles there; fit rms 6.8 mm) and tucked under
      (flap 7.8 mm below the sheet). It took the crest variant: left hand at uv (-0.288, 0.162), lift, 240-row drag,
      lower, release, retreat.
    - The settle then reached Task success after 500 control steps (12.5 s).
    - First success: physics step 36756 = control step 3676, sim 91.9 s. The unpatched reference had no success in
      3838 steps.
    - Final coverage 0.989 (v16 needs 0.95; it was 0.942), max height 12.1 mm, max speed 3.6 mm/s.
    - End-to-end live time on lab: 105 min including a 6 min instance build, on GPU 3 shared with knot replays
      (~1.7 s/step). That is still over the 72 min rule, from step cost, not waits.
    - Verifier replays: running.
- Adaptive ends (lead, 23:35, for every later iteration): no fixed wait at the end of a reference.
  - Poll what the privileged tooling exposes (the Task's success / settled state, or the gates' own speed and coverage
    signals), and stop at success or once the settled gate has held for its window.
  - Keep a cap equal to the old fixed wait.
  - The final `settle` already ends at the first success tick, because the episode ends there; its fixed cost applies
    only to a run that never succeeds.
  - Patch 11's 25 s relax before the fold measurement is a fixed wait. In a later iteration it becomes a poll (stop once
    the sheet's max speed has stayed under the gate's limit for its window, cap 25 s), and the final cap returns to 60 s.
    `blanket_hard_c` runs unchanged (25 s relax, 90 s cap).
- Speed rule (lead: one full reference execution at most ~20 % of the 6 h budget, ~72 min, end to end on lab): the
  unpatched blanket hard reference already took 92 min of live oracle execution on lab (3838 steps, ~1.4 s per
  control step), before any extra stage.

## 9. v16 evidence: does merged-v16's replay-tolerant grading turn the zero-margin cases into passes?

- Standard twin hold (lead, 2026-10-05), patch 14 (`oraclefix/patches/14_standard_twin_hold.patch`,
  `topogym/planning/harbor_bridge/runtime.py` `stream_standard`). This is a deliberate deviation from your "no
  implicit holds" for the twin method.
  - After the last reference row the twin keeps sending that row for up to 2 s (80 rows) and stops as soon as the
    service reports done.
  - Reason: the service keeps an episode open until success, failure, the wall clock or the client stops, so an agent
    can hold and poll `done` in exactly this way. The twin then tests what an agent could do. Service and grader are
    unchanged.
  - Re-grade: `harbor_grade_of_v16_blanket_medium_std2` (your harness, `--modes standard --references` the grade-1
    privileged trajectory). It is the only twin on lab that ended as "timeout" at its last reference row.
  - Result: 0. The live session got the 1376 reference rows plus the full 80-row hold (1456 rows) and still did not
    succeed; the plain replay did not either. For blanket medium the gap is the PBD realization (privileged replay 1
    also ended at coverage 0.922), not only the last tick. Patch 14 stays, as the twin method's agent-equivalent end.
- Harness fix found on the way: patch 12 (`oraclefix/patches/12_v16_verification_strict_goal.patch`,
  `topogym/planning/harbor_bridge/verification.py`; applies on d5e71c6ae and v16).
  - The oracle harness's consistency check still assumed the pre-v16 rule "privileged success == all replays
    succeeded". Under v16 a privileged success also needs one strict replay (`strict_goal_reached`), and a deep-contact
    success is held (`success_pending_review`); the standard branch had the same blind spot for review holds.
  - So a correct v16 grade 0 (both replays successful only in the hold) was reported as `evidence_failed`, and the
    queue stopped (lock medium's standard twin never ran).
  - The fix compares the grade with the v16 definition. Graders are untouched.

- Question (lead, 2026-10-04 21:20): the cases above that failed only on GPU replay noise at zero margin (blanket medium,
  lock easy / medium, rope easy / medium / hard, knot medium) were marked "needs v16's replay-tolerant grading". Here
  the same oracles are graded with v16's grader.
- v16 grading (`harbor_templates/topogym/common/rcb_topogym.py`, `GRADING_REVISION` replay_tolerance_2026-10-03b): for
  the GPU families, each grading replay first re-executes the rows with the instance's own thresholds; a success there
  is strict (`strict_success`, `success_row`). If the episode has not ended after the last row, it holds the final
  targets for up to 2 s (`GRADING_HOLD_S`). During the hold only, blanket's coverage / particle speed (0.95 -> 0.92 /
  0.03 -> 0.08 m/s) and knot's rope speed (+0.25 mm/s) are loosened. rope_threading and lock_picking get the hold
  only. Privileged = both replays succeed AND at least one is strict within the rows. Standard = live success AND the
  replay's success. A tolerant replay can only confirm a strict live success.
- Tree `oraclefix/tree_v16` = `align_v16/v16` (= dev/jianwen 7293af9d6: v16 grading + both BUG 7 fixes; rsync copy,
  `diff -rq` clean) + patches 01-08. All eight apply exactly. 07 is redundant there (7293af9d6 has the runtime fix),
  but 01/02/05 import it.
  - Plus the sweep's planning-side FIX 2 and FIX 5 (`oraclefix/patches/sweep_fix2_actions.patch`,
    `sweep_fix5_solvability.patch`), applied at 21:45. 7293af9d6 lacks both, as d5e71c6ae does.
  - Without FIX 2, the first lock lane (`harbor_grade_of_v16_lock_em`) ended easy and medium at step 0 with
    `KeyError: 'mode'` in `lock_picking_medium_planning.initialize`. The cause: `SessionPolicyRunner.run_policy` gives
    `initialize` only `action_spec` / `timing_spec`, while the lock oracle needs `mode`, `observation_spec` and
    `action_spec.grasp_assist`. That is infra, not a v16 verdict; the lock oracle cannot start through the bridge
    until FIX 2 is in.
  - FIX 6 is already inside 06. FIX 4 (blanket `identity_config`) is task-side; v16 builds blanket without it.
  - The release identity (source 936e6ceb..., 325 files) equals the unpatched v16's.
- Image: the v16 pipeline's `labv16/rcb-topogym:0.2.14-dev-cu128` (f204ad420b77, built and kernel-cache warmed by
  align_v16), never rebuilt or retagged.
  - Without `--tasks-root`, your launcher runs the candidate's `build_image.sh` (`docker build -t <tag>`) whenever
    `image.lock.json` is missing. A cache hit there would move that tag back to the un-warmed build.
  - So `oraclefix/bin/v16_lane.sh` first runs the launcher's own candidate steps with the same arguments, but without
    build_image.sh: `topogym_merge_candidate.py`, then `topogym_candidate_pipeline.py --phase build`. The pipeline
    locks the existing tag's id itself and checks the image's runtime source == frozen source. Output goes to
    `tree_v16/runs/test_results/cand_of_<lane>/`.
  - It then grades with your unchanged launcher and `--tasks-root` that candidate's tasks. The lane log prints the
    image id before and after.
- Lanes (GPU 4, non-IPC only so nothing collides with the night's IPC agent trials):
  - `harbor_grade_of_v16_blanket_medium`: blanket_flatten medium. ba01 baseline 0: replay 1 strict at row 1953,
    replay 2 not within the 2088 rows;
  - `harbor_grade_of_v16_lock_em2` (rerun after FIX 2): lock_picking easy (ba01 + 08: 0, neither replay within the
    4743 rows) and medium (ba01 + 08: 0, replay 2 at row 6120, replay 1 not);
  - proposed next on GPU 4: lock_picking hard (ba01 + 08: privileged 1, standard 0 on replay noise).
  - The image id was the same before and after each lane (f204ad420b77).
- Results (`oraclefix/bin/grade_details.py <lane dir>` prints every replay's grading record):

| case | ba01 strict result | v16 privileged | v16 replays (grading record) | v16 standard |
|---|---|---|---|---|
| lock_picking easy | 0: neither replay within the 4743 rows | **1** | both strict within the rows: rows 4732 and 4734 (live 4734), hold 0, tolerance_needed false; the tolerance was not used | **1**: live stream success at row 4733; the grading replay had no success within the 4733 rows (strict_success false, i.e. 0 under the strict grader) and succeeded on the first hold step (hold 1/80, success_in_hold true; lock has no relaxed thresholds) |
| lock_picking medium | 0: replay 2 at 6120, replay 1 not | 0 (v16 rule) | live success at its last row 6111; both replays succeeded only on the first hold step (hold 1, 25 ms), neither strict within the rows (strict_goal_reached 0); v16 requires one strict replay, so 0. The harness labelled it evidence_failed (verification.py, fixed by patch 12) and stopped the lane | blocked_dependency (privileged 0 under v16). The lane was first stopped by the false evidence failure (patch 12); no rerun: re-rolling against replay noise is out of scope |
| blanket_flatten medium | 0: replay 1 at 1953, replay 2 not within 2088 | **1** | replay 2 strict at row 1299 (live 1376); replay 1 no success within the rows, success 21 hold steps (0.53 s) into the hold, tolerance_needed: coverage worst 0.922 (live 0.95, hold 0.92) | 0: the standard live stream ran all 1376 reference rows without success (reason timeout); plain replay no success either |
| lock_picking hard | privileged 1, standard 0 (replay noise) | **1** | both strict within the rows: rows 7476 and 7477 (live 7477), hold 0 | **1**: live stream success at row 7477 (the reference's last row; no twin hold used); the grading replay was not strict and succeeded on hold step 2 (50 ms), so it is 0 under the strict grader |
- **Structural design point (for you, not something we change): zero margin for the strict privileged replay.**
  - In privileged mode v16 credits a success only if one replay meets the strict goal within the rows. But the trajectory
    ends at the live success tick (the Session ends the episode there), so that replay has zero margin.
  - On the GPU families (lock_picking; claws if the same applies), a replay that is one control tick (25 ms) late gets
    0, although it succeeds on the first hold step.
  - This hits agent trials exactly as it hits the oracle.
  - The standard twin's live stream has the same zero margin: the reference ends at the privileged live success tick,
    and the live standard session gets no hold (v16's hold and slack apply only to the grading replay). Example:
    blanket_flatten medium standard on v16, where the live stream ran all 1376 rows without success (reason timeout).
  - lock_picking medium on v16 (`harbor_grade_of_v16_lock_em2`): live success at row 6111; both replays succeed at hold
    step 1; `strict_goal_reached` 0; privileged grade 0.
  - Privileged GPU-family cases seen so far with `replay_hold_steps` >= 1:
    - lock_picking medium: 2 of 2 replays (0);
    - blanket_flatten medium: replay 1 hold 21 with the coverage slack, replay 2 strict at row 1299 (1);
    - lock_picking easy privileged: both strict (hold 0). Its standard twin's replay used hold 1, which the standard
      rule accepts.
    - lock hard and the blanket medium standard twin are still running; this list grows with them.
- **Who the zero margin hits (code reading, d5e71c6ae; no runs).**
  - (b) Privileged side, structural, hits agents as well:
    - `harbor_templates/topogym/common/rcb_topogym.py` `Session.step` sets `episode_end = "success"` on the task's
      first success tick (line 2564, from the Task's `terminated`).
    - Every later step returns `True` at line 2546-2547 (`if self.episode_end is not None: return True`) without
      stepping the scene. Only executed steps are appended to `self._recording` (lines 2566-2567).
    - So every privileged trajectory, an agent's or the oracle's, ends exactly at its live success tick. Nobody can
      append hold rows, and v16's "one strict replay within the rows" always has zero margin.
    - The oracle cannot fix this; a post-success hold in the oracle runner would not be recorded.
  - (a) Standard side, an artifact of the twin method:
    - The service (`harbor_templates/topogym/limited/environment/sim/server.py`) ends the episode only on the task's
      own end, the step guard, the wall clock (`RCB_WALL_CLOCK_S`, default 10800 s), or when the collect hook stops it
      after the client is done. See `ctrl_step` (lines 295-324: `if S.episode_end is not None: finish(...)`) and
      `_end_and_exit` (line 471: `if not E["done"]: finish("timeout")`).
    - It does not know any reference length, so a client can keep submitting hold rows and polling `done` until
      success.
    - Our twin streamer stops at the last reference row by design: `topogym/planning/harbor_bridge/runtime.py`
      `stream_standard`, "Public HTTP only; never append settling actions", and "...ended without native Task
      success; no implicit holds added".
    - The collect hook then ends the episode with reason `timeout`, as in blanket medium's standard twin on v16.
    - An agent driving the service has no such limit. Its remaining zero margin is only on the grading replay, which
      v16's hold covers.
    - Possible oracle-side fix (your call, since the comment states the opposite intent): let `stream_standard` hold
      the last row, up to 2 s, until the service reports `done`.
- **R-now vs R-hold, existing evidence only (privileged GPU-family cases with a strict live success; no new runs).**
  - R-now = v16's rule: every replay succeeds (the 2 s hold allowed) AND at least one replay is strict within the rows.
  - R-hold = every replay succeeds, each allowed the same tolerant hold of at most 2 s that v16 already gives the
    standard mode.
  - ba01 runs had no hold, so where a ba01 replay missed within the rows its hold outcome is unknown (`?`).
  - Live failures are excluded (the sweep's blanket hard, claws easy/hard guard stops).
  - interlocked_claws is not a v16 GPU family (plain, bit-exact replays), so its replays are strict by construction.

| case (lane) | live success row | replay 1 / replay 2 | R-now | R-hold |
|---|---|---|---|---|
| lock easy, v16 (`v16_lock_em2`) | 4734 | strict 4732, hold 0 / strict 4734, hold 0 | 1 | 1 |
| lock hard, v16 (`v16_lock_hard`) | 7477 | strict 7476, hold 0 / strict 7477, hold 0 | 1 | 1 |
| lock medium, v16 (`v16_lock_em2`) | 6111 | hold 1 (25 ms) / hold 1 | **0** | **1** |
| blanket medium, v16 (`v16_blanket_medium`) | 1376 | hold 21, coverage slack used (worst 0.922) / strict 1299 | 1 | 1 |
| lock easy, ba01 + 08 (`lock_easy`) | 4743 | missed / missed | 0 | ? |
| lock medium, ba01 + 08 (`lock_medium`) | 6120 | missed / strict 6120 | ? | ? |
| lock hard, ba01 + 08 (`lock_hard2`); baseline (`base_lock_hard`) | 7485; 7464 | strict / strict | 1 | 1 |
| blanket easy, ba01 (`base_blanket_easy`) | 719 | strict / strict | 1 | 1 |
| blanket medium, ba01 (`base_blanket_medium`) | 2088 | strict 1953 / missed | ? | ? |
| knot easy, 03 (`knot_easy3`) | 907 | strict / strict | 1 | 1 |
| knot medium, 03d (`knot_medium2`) | 1953 | missed / missed | 0 | ? |
| knot hard, 03d (`knot_hard2`) | 2516 | missed / missed | 0 | ? |
| rope easy, 04d (`rope_easy`) | 2101 | strict (19 rows early) / missed | ? | ? |
| rope medium, 04e (`rope_medium`); sweep (`..._rope_threading_medium`) | 2904; 1874 | missed / missed | 0 | ? |
| rope medium, 04f (`rope_medium2`) | 2897 | strict / strict | 1 | 1 |
| rope hard, 04d (`rope_hard2`) | 2917 | missed / strict 2917 | ? | ? |
| rope hard, 04f (`rope_hard3`) | 2916 | missed / missed | 0 | ? |
| claws easy / medium / hard, 06 | 782 / 1364 / 16201 | strict / strict (plain replays) | 1 | 1 |

  - Measured so far: of the 3 v16 cases with hold data, R-hold changes one verdict (lock medium, 0 -> 1); both of its
    replays were one control tick late. The `?` rows are the open cases a hold would decide.
  - Exploitability of R-hold: the live run must still succeed under the instance's own thresholds, and the recorded
    trajectory ends at that tick. R-hold only lets a replay of the same actions confirm up to 2 s later, so it can
    credit nothing the live run did not achieve.
    - For the settle-type goals (blanket, knot, rope: a quiet window), passive motion during the hold can only finish
      the confirmation of a state the live run already reached strictly.
    - The one real difference is the relaxed thresholds (blanket coverage 0.92 / speed 0.08, knot +0.25 mm/s): a
      replay may confirm a state slightly below the live threshold. That is the same trade-off v16 already accepts in
      standard mode.
    - No family was found where the hold could complete a task the live run did not complete.
- Caveat for blanket medium (design point for you, not something we change): Replay 1 ended in a measurably different
  cloth state, coverage 0.922 against the live 0.95. That 0.92 hold threshold is doing real work, which makes it a
  design point for Jianwen, not something we change.
- Pending, IPC (they wait for a GPU free of IPC agent trials): rope_threading easy / medium / hard (04f) and
  knot_untying medium (03e). Knot hard: after the new precision settings are validated, it runs once under v16 grading.

## 10. hedgehog_in_cage very_easy and easier: the below-easy oracle (2026-10-06)

The user reversed the earlier decision to leave hedgehog's below-easy settings out, so we made them work end to end.

**Scenes (William's 10-02 drafts): unchanged.**
- Release: v18, tree `7f0b002cc`.
- Candidate: lab `hhbe/cand_hh`, built with your pipeline on topospeed's v18 image `labv18be` (`01c12854`).
  - build, preflight and harbor-smoke all pass.
  - Exact restore holds for both settings (state_sha very_easy `8fc4502c70aa936e`, easier `ed55f7e11afa2e0b`).
- Rest state: after 10 s at home the ball has settled 0.30 mm onto three cage contacts, with no rotation. Over
  each graded episode, the deepest ball contact with the cage, mount or table is below 0.01 mm.
- Goal: the same goal and instruction as easy (your test checks this).
- Difficulty order very_easy < easier < easy holds. This is an object-level check at the 12 mm test lift: one turn
  of the ball about its centre, then a straight pull, with 1 mm clearance.
  - very_easy (118 mm windows): it leaves by translation alone. Turns of up to -25 deg open pulls across
    178-198 deg.
  - easier (108 mm windows): no translation exit. A single-turn exit needs either your 80-85 deg roll about S10
    or a yaw of exactly -20 deg about the vertical, then a pull at 186-188 deg. A -25 deg yaw is already blocked.
  - easy (CLASSIC): still needs its two-grasp oracle.
  - Design note: easier's smallest exit is that 20 deg yaw, not the documented 80 deg roll. The roll is what
    `below_easy_witness.py` searches; the yaw is a narrower corridor that the witness does not try.

**Oracle:** the easy oracle unchanged (`recipes.run_medium_oracle`, the measured held route), plus one checked
pickup per setting. Changes:
- `harbor_bridge/below_easy.py`, `catalog.py`, `references.py`: hedgehog joins the below-easy dispatcher.
  - Its private input is `reference_data/hedgehog_in_cage/<tier>/pickup.json`, recorded in the manifest.
  - `hedgehog_in_cage/public_session.py` runs both settings through 01's standard-rate runner.
- `hedgehog_in_cage/held_oracle.py`: the below-easy settings skip the historical `reference_routes.json` route,
  because their pickup brings its own object hints.
- `hedgehog_in_cage/below_easy_pickup.py`: builds and checks the pickups on the frozen instance in the task image.
  It runs the oracle's own partial close first, then an offline `plan_held_path` from a constructed measured state.
- Grasp: S10 (the spike that points at the robot), held across the spike near its tip.
  - Hand parameters: theta 90 deg, phi 300 deg, hand turned 180 deg about its axis.
  - Spike axis at 90 mm hand depth, 6 mm from the tip.
  - Why not coaxial: a grasp along the spike, so that easier's roll would be a wrist roll, has no valid IK. The
    cage is 0.43 m from the base, so every solution folds the arm onto itself (q4 at -3.0, self-collision).
  - Why not deeper: at 80 mm depth the closing pads passed through the 10.8 mm spike without a weld
    (`no_bilateral_candidate`). At 86-93 mm, near the fingertips like easy's pickup, the grasp welds every time.
- Routes after the 12 mm test lift:
  - very_easy: pull 0.07 and 0.19 m at 198 deg, then to the goal.
  - easier: yaw -20 deg, pull 0.125 m at 188 deg, then sideways (240 deg) to the goal.
  - Why easier does not use the roll: with every grasp that passes the approach (theta 60-90 deg), the 80 deg
    roll, or a long pull toward the base, drives the elbow to its limit (q4 -3.06). Grasps leaning over the cage
    (theta 105-115 deg) collide at the start. The shorter pull followed by the sideways move keeps q4 at -2.97
    or above.
- Speed: the largest joint step of any row is 0.0047 rad, against the 0.039 rad limit, so the limiter never
  slows a row.

**Grades** (your launcher, `--tasks-root hhbe/cand_hh/tasks`, lab lanes `hh_ve1` and `hh_ea1`):

| setting | privileged | standard | rows | live min (priv / std) | replays |
|---|---|---|---|---|---|
| very_easy | 1 | 1 | 1923 | 3.7 / 3.0 | both strict at 1923, sha `0f706cd9bdf7b8f2`, equal across modes |
| easier | 1 | 1 | 1882 | 3.7 / 2.9 | both strict at 1882, sha `9a2668c6c8beeea3`, equal across modes |

- Penetration, from a fresh-process replay of each graded trajectory:
  - very_easy: deepest contact 0.008 mm ball-cage/mount/table, 0.010 mm robot-ball, 0 robot-fixture.
  - easier: 0.005 / 0.010 / 0.
  - Both episodes: review and forcing 0, review depth 0.0 mm.
- Visual check (verifier videos): the gripper holds S10, the ball leaves through the window without touching a
  bar, and it is held still over the green goal area.
- Trial totals: privileged 10.4 / 10.3 min (verifier 6.4 / 6.3 min for its two replays), standard 7.9 / 7.9 min.
- CI:
  - Updated `test-hedgehog-below-easy` (3 new tests on the oracle inputs), `test-harbor-below-easy` and
    `test-oracle-portability` (the manifest now has 37 files).
  - The full CPU CI in the v18 image gives the same outcome as on `7f0b002cc` for every test. The 10 tests that
    fail there fail the same way.

## 11. v18 below-easy oracle sweep: buzz fixed; rope and knot easier analysed (topospeed, 2026-10-06)

**Sweep.** very_easy and easier of the 8 families your `harbor_bridge/below_easy.py` wired before hedgehog, both modes,
16 tasks / 32 grades, oracle in the agent slot.
- Candidate: lab `align_be/cand_be`, your `topogym_merge_candidate.py --families <8> --tiers very_easy easier` on the
  v18 tree `7f0b002cc`, image `labv18be` (`01c12854`, the v18 release image). Build, preflight (16/16 exact restores)
  and harbor-smoke (32/32) pass. Grades: `test_harbor_oracles.py --candidate` as your launcher runs it, lab lanes
  `align_be/sweep/`.
- Result on `7f0b002cc`: **23 / 32** grade 1, all deterministic. Every non-pass is oracle-side.

| family | very_easy priv / std | easier priv / std | live min (priv) |
|---|---|---|---|
| cast_coil | 1 / 1 | 1 / 1 | 2.6 / 2.9 |
| cast_keyhole | 1 / 1 | 1 / 1 | 5.9 / 7.3 |
| lock_picking | 1 / 1 | 1 / 1 | 5.3 / 7.9 |
| interlocked_claws | 1 / 1 | 1 / 1 | 5.1 / 22.0 |
| fiber_bundling | 1 / 1 | 1 / 1 | 9.8 / 16.0 |
| knot_untying | 1 / 1 | 0 / blocked | 32.7 / 35.9 |
| buzz_wire_3d | 0 / blocked -> **1 / 1** with the fix | 1 / 0 -> **1 / 1** with the fix | 17.3 / 19.9 (fixed) |
| rope_threading | 0 / blocked | 0 / blocked | ~56 to the failure |

With the buzz fix below: **27 / 32**. Open: knot easier (yours, you re-validate it) and rope x2.

**buzz_wire_3d (commit "below-easy buzz_wire_3d: standard-rate rows; very_easy TURN_1 planning margin 1.4 mm").**
- easier standard: the standard service clipped or rejected the reference rows from row 1621. The simplified stages ran
  through a plain `SessionPolicyRunner`, and the regrasp rows asked up to 0.18 rad per step (very_easy has 12 such
  rows). Fix: `rate_limited_runner(session)` (spread), as for buzz easy in O2-2. Largest step afterwards 0.0385 rad.
- very_easy privileged: "No collision-checked terminal turn from the measured grasp". From an exact replay of the
  failed trial (final state_sha `58ef8bbb6fe06cd8`), every planned turn keeps at most **1.4735 mm**: TURN_1's 5
  candidates, 41 yaws 130-170 deg, 210 xy offsets. The 1.5 mm margin admitted none. Fix: very_easy uses 1.4 mm. This is
  the oracle's own planning margin, not a Task rule (the Task fails only on wand-wire contact); easier keeps 1.5 mm.
- Evidence: in-process native success from the failure state with TURN_1 at 1.4 mm (row 10,462); Harbor grades on a
  tree with only these planning files: very_easy 1 / 1 (17.3 / 13.8 min live), easier 1 / 1 (19.9 / 15.6 min).

**knot_untying easier (commit "stop instead of closing when converge() saturated the TCP bias": a safety change,
not a fix).**
- Failure: grasp_ends:converge never reaches the rope ends. The left TCP stays 17 mm off while its bias grows to the
  40 mm cap (16.3, 36.5 mm); the grasp then closed beside the rope, and the lift and spread carried nothing.
- Exact replay with the commanded rows (lab `kdiag`): from grasp_ends:descend the left **waist (joint 1)** falls behind
  its command by 0.10-0.16 rad and the wrist roll by 0.14-0.16 rad, while the other joints track within 0.03 rad. The
  TCP moves a few mm where the commands move about 45 mm. The rigid collider reports no gripper contact.
- Two bounded re-aim attempts did not help, so the stall is not the rope:
  - converge 8 mm above the re-aimed grasp pose in free space: left TCP 49 mm off, waist -0.540 rad against a command of
    -0.382 (other joints within 0.015 rad), jaws open (finger position 27 mm);
  - rise 3 cm with the jaws closed and converge there: still 48.3 mm off, bias saturated.
- Not the cause: a joint limit (the waist range is +-pi). Candidates to check: a left-arm collision with the right arm
  or the scene, or the command path (Session guard rules, the joint-step limiter) altering the waist target; the waist
  torque cap is 12.9 Nm. Every passing knot run on v18 settles once at 1-4 mm with no prior bias.
- The committed guard ends the run where it fails ("TCP bias saturated ...; not closing beside the rope"); runs that
  never saturate are unchanged. Patches of both re-aim attempts: lab `align_be/be_fix_all_v3.patch`.

**rope_threading very_easy and easier (not committed: no native success yet).**
- Failure (both tiers, identical up to here): raise_to_ring, "IK exhausted 4 seeds" after about 56 min. The straight
  raise to ring centre + 10 cm (world z 1.35 m) above the pickup keeps the jaws down; the wrist angle climbs to 2.185 rad
  (range [-1.8675, 2.234]) and the path stops high up.
- IK probe on the v18 instance (`ropeik`): with the jaws down, **no** target 9 cm or more above the ring centre is
  reachable for the right arm (any jaw tangent, dx 0-5 cm), so very_easy's orient_above_open_cradle (ring +
  [0.025, 0, 0.09]) is out of reach as well. Targets 6 cm and 3 cm above it are reachable for most tangents, and every
  easier feed pose (ring + [0.15 / 0.10 / 0.05 / -0.10, 0, 0.025]) is reachable. The left arm reaches none of them.
- Variants from one checkpoint at the raise start (`ropefork`: exact replay of 653 rows, then a rewind per variant):
  - very_easy: one joint-space move to ring + [0.025, 0, 0.06], then your 24-step lowering from 0.06: past the raise,
    then "right lost the physical rope grasp" while lowering onto the cradle.
  - easier: one joint-space move to the entrance feed pose ring + [0.15, 0, 0.025]: past the raise and
    align_ring_entrance, then feed_through_ring stops with "Action would be clipped by the public robot adapter" (the
    feed needs a joint target outside the public action range).
- So the raise target needs to come down (6 cm is reachable), and each tier then has a second issue in its threading
  phase. The variant code is in `topospeed/bin/ropefork_v2.py` (lab).
- **Speed, a decision for you and the user:** below-easy rope runs at about 2.6 s per control step against 0.73 s for
  rope easy on v18, so one execution takes 1.5-2 h, over the 72 min rule. The below-easy candidate path uses the Task
  defaults on purpose (`topogym_merge_candidate.py`: no original-tier overrides for very_easy / easier), so these
  instances do not get merged-v16's rope profile `contact_relaxed_v16`:

| instance setting | rope below-easy | rope easy (contact_relaxed_v16) |
|---|---|---|
| IPC frames per control step | 10 x 2.5 ms (25 ms step) | 1 x 40 ms (40 ms step) |
| rope mesh | default, 33,070 vertices | 5.5 mm spacing, 12 sides, 4,939 vertices |
| Newton / PCG tolerance | 1e-3 / 1e-5 | 3e-3 / 3e-5 |
| robot-rope contact | every link | fingers only |
| rope material | default | E 5e6 |

  Both freeze a settled IPC state. Likely lever: give the below-easy rope tiers that profile, then re-validate the
  simplified oracle on it. Not applied.

**Lab paths.** Sweep `align_be/` (candidate, lanes, `tree_fix` = the planning fixes on `7f0b002cc`). Tools in
`topospeed/bin/`: `bzdiag.py` (buzz replay and turn probe), `kdiag.py` (knot joint tracking), `ropefork_v2.py` and
`ropeik.py` (rope checkpoint variants and reachability).
