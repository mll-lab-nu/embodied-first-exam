# TopoGym tier tasks (protocol v1.0)

39 frozen instances (13 families × easy / medium / hard) in both modes: 78 task packages. The published ones (v14) are
the dirs `tasks/topogym-<family>-<tier>-i00-{privileged,standard}`. Since Jianwen's release mechanism
(`ci_checks/topogym_active_release.json`, `scripts/topogym_versions.py`) the active release's packages are built by
`scripts/topogym_merge_candidate.py` + `scripts/topogym_candidate_pipeline.py` into a frozen candidate tree outside `tasks/`
(source snapshot, its own image, runtime bindings, exact restores and Harbor nop checks, then activation); new experiments
take their tasks from the active release only (`scripts/topogym_versions.py list`). `scripts/topogym_mk_task.py` (privileged) and
`scripts/topogym_mk_limited.py` (its standard twin) render them from `harbor_templates/topogym/` and the frozen instance;
their last step is `scripts/task_conventions.py`'s `normalize` (protocol v1.0 fields, README layout). Re-rendering needs no
GPU when the instance's `describe.json` is kept (`--reuse-describe`).

## Versions (2026-10-04)
Active: **merged-v19** (tooling v19, `eai-standard/2.3`, image `rcb-topogym:0.2.17-dev-cu128`), a source candidate until
its packages are built and qualified. Published: v14 (the 78 dirs under `tasks/`, `rcb-topogym:0.2.12-cu128`).
Jianwen's simpler variants (interlocked_claws easier / very_easy): tooling v10 on 0.2.10.
- v19 (2026-10-06) = merged-v18 with Jianwen's below-easy tiers and oracle fixes up to 2026-10-06 + the blanket settle
  speed: a cloth particle's speed is its end-of-tick displacement over the 2.5 ms tick instead of PBD's last-substep
  velocity, thresholds unchanged (the user's decision, 2026-10-06; Cloth settle speed below). The world's readout
  (`topogym/world/genesis_world.py`) is public source, so the image changes (0.2.17-dev); the physics, the packaged
  cloth states and the other families (no particle entities) are unchanged.
  Environment profile `merged-v19`: the blanket terminal's speed measure changed. As with merged-v18, the blanket re-key
  records differ only in `metadata.identity_rekey.by` (arrays byte-identical) and their record hash enters
  `task.instance_id`, so the blanket instances get new state hashes for the same restored physics; the label also enters
  the slotted oracle's submission fingerprints (computed at run time). The frozen "v18" tooling hashes are those of the
  built merged-v18 packages (cand_v18b; identical to 8d7d16489's and 7571e4194's templates; BOUND_FROZEN 15-18).
- v18 (2026-10-05) = merged-v17 + the deterministic IPC solver (libuipc 292c98c3 with three determinism patches,
  `images/topogym/uipc-patches/`, pyuipc 0.0.25+topogym.det1; knot K2 solo +2 % per control step against the stock build;
  and the robot forward-dynamics recompute after a settled-state restore; the instances with a settled IPC state, knot_untying,
  orbits and slotted_post_ring, are re-made from the deterministic solver, while rope_threading has none, so its instances
  keep their state hashes and only its runtime physics changes) + knot_untying's K2 solve (5 ms IPC frames, a
  semi-implicit Newton solve of at least 3 iterations; `harbor_templates/topogym/common/rcb_topogym.py`) + the exact
  speed-ups below (blanket hard reference 29.1 min) + the agent interaction log restored: `images/topogym/warm_cache.sh`
  had committed an empty `RCB_SESSION_LOG` into the warmed images 0.2.14 / 0.2.15, so their trial Sessions wrote no
  log (agent_sessions / resets / sim_steps 0); it now reaches only the warm-up sessions, and the script fails if a tag
  carries it.
  Environment profile `merged-v18` (`topogym/tasks/release_profile.py`): K2 changes knot's timing and solver and the IPC
  instances are re-settled, so the environment changed. For Jianwen: the label also enters the slotted oracle's
  submission fingerprints (computed at run time) and the blanket re-key records. The three blanket records differ from
  v17's only in `metadata.identity_rekey.by`, and their state arrays are byte-identical; the record hash (the task
  parameter `initial_state_sha256`) enters `task.instance_id` and with it the task state that `Session.state_sha` hashes,
  so the blanket instances get new state hashes for the same restored physics. The frozen "v17" tooling hashes are those
  of the built merged-v17 packages (`ci_checks/topogym_tooling_versions.json`, BOUND_FROZEN 15-17).
  Below-easy tiers (Jianwen's knot_untying very_easy / easier and orbits below_easy, made with `--tooling` the current
  `rcb_topogym.py`): knot inherits K2 from `TASKS["knot_untying"]`, and both families need the v18 image for their
  settled IPC states (the settled-state identity includes the pyuipc version, now 0.0.25+topogym.det1). Their simplified
  oracles were developed under v17's 2.5 ms full Newton solve, so they should be re-validated under K2 when built.
  Proposal for Jianwen (his instruction texts): the step time the task description states comes from steps before the
  first contact; on fiber_bundling the contact phases cost more (lab sweep: medium ~0.23 s per control step against the
  stated 0.16, hard ~0.40 against 0.31). Measuring it over a contact phase would state what an agent pays.
- v17 (2026-10-05) = merged-v16 + the R-hold grading (privileged replays may confirm within the same tolerant hold as
  standard) + fiber_bundling on the CPU (image 0.2.15-dev: Genesis tree patch, exact fast paths; below) + deterministic
  GPU physics (tooling; below).
  Release and environment profile are separate names: the release is merged-v17 (tooling 17, image 0.2.15-dev), while
  its environment profile, `topogym/tasks/release_profile.py` `PROFILE = "merged-v16"`, is merged-v16's, unchanged. The
  profile label names the environment choices (geometry, materials, contact, grasp assistance, timing, terminal), not the
  tooling or the image; it is part of the image's public source, of the slotted oracle's submission fingerprints and of
  the blanket re-key records, so it changes only when the environment does.
  The built merged-v16 packages (7293af9d6's templates) keep their tooling hashes as frozen "v16"
  (`ci_checks/topogym_tooling_versions.json`); v16 trials are graded with their own packages, not mixed with v17 results.
- v16 (2026-10-04) = Jianwen's merged-v15 source candidate (4aac2a4e6: release selection, runtime bindings, the candidate
  pipeline and the environment profile `topogym/tasks/release_profile.py`; ba01d029c: oracle portability, knot_untying
  terminal v5) + our grading rules, developed as the local "tooling v15" below and never published (live-strict,
  replay-tolerant grading; the physical-validity policy) + blanket_flatten's live coverage 0.95 in the environment profile
  + the blanket identity fix found by the lab oracle sweep (BUG 2: the frozen state's absolute path entered the instance
  identity, so no blanket candidate restored exactly). Image 0.2.14-dev: the public source differs from 0.2.13-dev's, and
  a new tag leaves the packages bound to 0.2.13-dev untouched. How the two sides' rules fit: One policy across both sides
  (below).
  - The environment profile (Jianwen's, merged-v16): rope_threading `contact_relaxed_v16` (his name for that profile, not a
    release number): explicit ring geometry, a softer finer rope (E 5e6, 5.5 mm mesh), the fingers as the robot's only
    contact with the rope and rings, a 1 mm aperture compression allowance with a round-ring passage test, a rope still-speed
    of 10 mm/s (was 1), one 40 ms tick per control step (25 Hz), soft-band grasp assistance; blanket_flatten two-hand patch
    assistance and coverage 0.95 (the packaged v14 cloth states re-keyed for it: `rekey_goal_parameters` in
    `scripts/topogym_merge_candidate.py`, as for the local v15 instances); fiber_bundling sheath assistance; horseshoe_ring
    ring-clearance geometry; hedgehog_in_cage hard's s5 post geometry. knot_untying terminal v5 is task code.
  - Every instance is made again by the candidate pipeline (no inherited success). v14 trials can be re-graded with
    `scripts/topogym_regrade_v16.py` only where the v16 instance's state hash equals the trial's (families whose task code,
    profile and terminal revision did not change; known once the candidate is built); the others are rerun.
- v15 (2026-10-04, Jianwen, not published) = the merged-v15 source candidate on image 0.2.13-dev. Its tooling hashes are frozen
  in `ci_checks/topogym_tooling_versions.json` (`v15`); packages built from it (the lab oracle sweep's) keep their own
  runtime binding.
- Local tooling v15 (2026-10-03 / 04, ours, not published; its rules ship in v16) = v14 + live-strict, replay-tolerant grading for the six families whose physics runs on the GPU
  (blanket_flatten, knot_untying, rope_threading, slotted_post_ring, orbits, lock_picking; the user's decision, 2026-10-03)
  and blanket_flatten's live coverage threshold 0.95 (was 0.90: a folded corner passed). Image unchanged (0.2.12). The
  graders' replays run the rows with the instance's thresholds, then hold the final targets for up to 2 s with small replay
  tolerances on continuous thresholds; a tolerant replay only confirms a strict success (standard: the live one; a live
  failure is final; privileged: one replay must reach the strict goal within the trajectory's rows). Details in Grading
  replays below; the live episode and the agent's own Session are unchanged. The texts state all of it.
  - It also replaces v14's contact rule with the user's general physical-validity policy (2026-10-03 ~21:30; details in
    Physical-validity policy below). v14's R1 (a rigid task contact deeper than 3 mm, or deeper than 1 mm for 0.25 s,
    ended the episode) ended a passive impact: standard trial QKSrtdL (interlocked_claws hard) had opened both grippers
    and held every joint target when the released claw landed on the other one, 4.6 mm deep for 3 ticks. Now penetration
    depth is evidence (a success with a deep task contact is held for review, not credited automatically), forcing (an
    arm drive at its torque cap while that arm, or a part it holds, presses on something) is recorded as evidence, and a
    simulator breakdown is an infrastructure error unless the arm was forcing just before it (then the agent's failure).
  - blanket_flatten's 3 instances were made again (`make-instance --task-parameters`: `minimum_coverage_ratio` 0.95). Their
    frozen cloth state is bound to the scene identity, which includes every task parameter, so the archive was re-keyed
    (`identity.parameters.minimum_coverage_ratio` and `identity_sha256` updated, an `identity_rekey` record added,
    `arrays.npz` byte-identical) instead of prepared again (another GPU preparation would give another cloth). Against
    v14: `soft_state`, `objects`, `asset_identity` identical; `effective_task_parameters` and `public_goal` differ only in
    the threshold (95 %); strict fresh-process smokes pass (`instance_matches`; `instance_exact` 0, as for the v14 blanket
    instances). The other 36 instances were v14's. (These local instances are superseded by the v16 candidate's.)
- v14 (2026-10-03) = Jianwen's v13 (e49b116e3) + the rules of the 2026-10-03 rules audit + a PBD cloth-contact fix, on image
  0.2.12 (0.2.11's stack with v13's `topogym/`: the IPC articulation-reference fix and v13's task changes). The 10 instances
  those task changes touch were made again (knot_untying and rope_threading with a stored IPC settled state,
  interlocked_claws' separation goal, buzz_wire_3d medium's F2_terminal_xy40_20 layout; strict smokes instance_exact); the
  other 29 load unchanged on 0.2.12 (their v12 hashes).
  - Rules (tooling-level overrides; every frozen t = 0 state hash kept). A non-held rigid task contact ends the episode when
    it is deeper than 3 mm at once or deeper than 1 mm for 0.25 s; held fingers 4 / 2 mm (v12: 1 / 2 mm at any tick end,
    which ordinary contacts reached and the only v12 success passed at 0.83 mm). A soft body's tet inversion or a stretched
    attachment ends it after 0.25 s; an invalid native IPC state at once. ALOHA arm torque caps 12.9 / 80 / 59 / 12.9 / 35 /
    17.5 N m (waist ... wrist rotate), Panda 50 N m on joints 1-4; grippers unchanged. A fingertip-table guard: no part of a
    gripper is commanded lower than 15 mm below the tabletop (arm motion stops there; gripper commands never). The standard
    service runs joint_position rows at most 0.04 rad per control step and refuses an ee_pose row whose IK solution jumps
    more than 0.5 rad. `Session.safety()` / the service's `meta["safety"]` report contact depth, force and the guard;
    failure reasons are readable. The instruction texts state all of it.
  - blanket_flatten: Genesis 1.2.1's `LegacyCoupler.kernel_pbd_rigid_collide` pushed a cloth particle out of each rigid geom
    in turn by the whole penetration and turned that displacement into velocity. A particle squeezed between two surfaces
    (fingertips pressed onto the table through the cloth) was thrown at up to 1.6e5 m/s ("Cloth fell below the table": all
    three standard failures of the v12 sweep). The tooling replaces that kernel (Genesis' files unchanged, so the frozen
    cloth states restore): a particle's push-outs are summed and bounded by what the contact can physically do in a substep
    (the body's own approach plus 0.05 m/s); one unsqueezed contact runs Genesis' own expressions bit for bit. A guard ends
    an episode whose cloth particle exceeds 20 m/s with `simulator_instability`, an infrastructure error for both graders
    (runs that did not blow up peaked at 9.2 m/s; every recorded blow-up crossed 10 m/s in one jump).
  - The per-step times in the texts come from the v14 describe (Instruction texts).
- v12 = v11 + knot_untying and orbits at one IPC substep like rope_threading / slotted_post_ring (the user's call,
  2026-10-02; their 6 instances made again, settled at one substep): knot 7.4x, orbits 12-15x against substeps 4 in the
  IPC study (knot easy lift / slip / drop within 0.1 mm, frames identical; orbits' clear approach within 0.11 mm).
  Accepted leniency: the larger IPC dt cushions a violent impact, so the reference's noise-robust tet inversion (episode
  end `rope_volume_invalid` / `connection_or_volume_invalid`) on knot medium's closing pinch and on orbits' ~2 m/s
  open-finger sweep does not happen; such impacts no longer end the episode. The families with a final-settling check
  (knot_untying, cast_coil, buzz_wire_3d, blanket_flatten) run it only on ticks where their goal predicate is reached
  (`_settle_only_when_reached`): elsewhere its result cannot change the outcome, so success / failures / episode ends are
  the same and only those ticks' `final_settling` metrics are left out; knot's task cost 1.84 -> 0.04 s per control step.
- v11 = Jianwen's v10 + the IPC families' settled scene frozen with the instance (`export-ipc-state`, then `make-instance
  --ipc-settled-state`; `SimulatorConfig.ipc_settled_state`, `topogym/world/physics/ipc_settled_state.py`): every build
  restores the same bits instead of settling (settling on the GPU started builds ~0.04 um apart, enough for a
  near-threshold squeeze to take another contact branch in a grader's replay; rope_threading hard showed it), so
  `instance_exact` holds again and a build skips 0.8-2.4 min of settling; knot_untying at two IPC substeps + the
  same tolerances / broad phase / settling (4.0x; one substep avoided the reference's near-threshold tet inversion);
  orbits at four substeps with the cheaper tolerances / broad phase and a settled start (~1.3x: only four substeps
  reproduce the reference's violent-impact tet inversion, which is robust to noise; one and two substeps would be
  12-15x but more lenient there).
  0.2.11 = 0.2.10 + that restore + one shared kernel / shader cache for every user (`XDG_CACHE_HOME`,
  `CUDA_CACHE_PATH` = /opt/rcb-cache), filled on a lab GPU by `images/topogym/warm_cache.sh` and committed into the tag:
  a fresh container's first build + first frame 88-239 s + 20-24 s -> 27-62 s + < 1 s (physics unchanged: claws easy
  replays to the same state hash).
- v10 (Jianwen, f0d233115) = v9 + his A01 ZIP/NPZ error classification, A03 evidence export and the owner-only
  `Env.sensor_factory`; new packages only (his simpler variants); notes below.
- New packages use tooling v13: upstream v12 plus the local Fiber Bundling and Lock Picking variant-aware recommended
  grasps. The local IPC articulation-reference initialization repair, task variants, A01/A03 and calibration extensions
  remain in source. Existing packages are not regenerated or relabelled by this merge.
- Both branches also used v11 independently. Upstream v11 and v12 keep image 0.2.11; local `v11_local_grasp` and its earlier Lock-only `v11_local_lock` keep
  their recorded `topogym-local/<family>-variants:20261002-01` images, pinned per package. The checker selects the local
  lineage by the exact tool hash, then checks every shared file and the simulator image references.
  Current v13 uses the image selected by VERSION. Published runtime images do not automatically include local source
  changes, including the local IPC initialization repair; building a new image is a separate release step.
- The upstream v12 one-substep policy retains its documented impact leniency. Skipped final-settling measurements can
  change task-result hashes; this merge does not claim physics-equivalence to older settings or requalify old episodes.
- Both branches independently used tooling v6. The inventory preserves upstream v6 and `v6_local_a01` separately;
  the checker selects the local lineage by its exact tool hash, then validates every shared file. No existing package
  is relabelled. Earlier validation of upstream physics does not qualify the combined code or new task variants.
- v9 = v8 + rope_threading and slotted_post_ring with one IPC solver substep per 2.5 ms tick (was four), Newton / PCG
  tolerances 1e-3 / 1e-5 (`SimulatorConfig.ipc_options`, was 1e-4 / 1e-6), libuipc's linear_bvh broad phase, and a scene
  settled for 300 / 800 ticks before the instance is frozen (`reset_physics_steps`; the v5 instances were not at rest at
  t = 0); their 6 instances made again. knot_untying's predicate uses an exact k-d tree clearance
  (`scripts/check_knot_clearance.py`); its simulator settings and orbits' stay v5 until their study is done (knot medium:
  the larger IPC dt avoids a near-threshold tet inversion the reference shows). interlocked_claws is back on the CPU in
  float64: the branch that made v8 move it is float64 physics (the GPU in float64 takes it for the same noise seeds).
  0.2.10 = 0.2.9 + `ipc_options` (Newton / PCG tolerances, broad phase).
- v8 = v7 with interlocked_claws back on v6's GPU float32 and its v6 instances: on the CPU, 5 of 16 noise runs of
  claws medium lose the teal piece in the friction-held phase after the right hand releases (3 end on the 1 mm
  penetration predicate), GPU 0 of 16 (Fisher p 0.04); claws easy passed. Six rigid families stay on the CPU.
- v7 = v6 + seven rigid families (buzz_wire_3d, cast_coil, cast_keyhole, fiber_bundling, hedgehog_in_cage, horseshoe_ring,
  interlocked_claws until v8) on the CPU in float64 with one global constraint solve (`rigid_options = {use_contact_island: false}`;
  Nyx still renders on the GPU; their 21 instances made again on lab) + frames rendered on demand (`Env.defer_rgb`: the
  per-step observation skips the camera pass; `render_frame` / `render_grid` / `render_depth` / videos render the current
  state when asked). lock_picking keeps v6's GPU float32 (slower on the CPU); the soft-body families keep their instances.
  0.2.9 = 0.2.8 + `SimulatorConfig.rigid_options`, CPU physics with Nyx RGB, `Env.defer_rgb` and exact per-tick fast paths:
  the finiteness check as one iterative walk with a bulk check of the rigid readout (`topogym/world/finite.py`), cached
  readout layouts, cached weld pairs (`grasp_rigid.RigidGraspBackend.pairs`). `topogym/world/state.py` stays byte-identical:
  its hash is part of the blanket frozen states' identity (`ci_checks/check-topogym-tooling.py` checks it).
- v6 = v5 + float32 physics for the 8 rigid families (`TASKS` in `harbor_templates/topogym/common/rcb_topogym.py`; their 24
  instances made again on lab with v6). 0.2.8 = 0.2.7 + blanket's coverage skip + the exact cheaper IPC diagnostics. Evidence:
  robot_coding_bench `jobs/journal/2026-10-02/sim_tradeoff/REPORT.md` (precision / speed study) and the check scripts below.
- v5 / 2.3 = Jianwen's post-merge repairs B04–B13 (`docs/rcb/STANDARD_MODE_2_3.md`,
  `docs/debug_logs/run_trials_post_merge_repair_20261001_zh.md`): invalid submissions graded as such, scores persisted
  before the video, only executed actions recorded with their actual ticks, non-integer `dt` refused, instance mismatch
  never a success, operation ids and request deadlines (a retried request is not executed twice).
- `eai-standard/2.3` is a TopoGym-local extension of robot_coding_bench main's 2.2 (`ci_checks/rcb_vendor.json`
  `local_adaptations`), to be proposed for main.
- 0.2.7 = Jianwen's 0.2.6 simulator changes + the batched rigid readback (Step time below).
- The 15 soft-body instances (blanket_flatten and the four IPC families) were made again with the v5 tooling on lab's
  RTX PRO 6000 (`make-instance --variation <family>_<tier> --scene-seed 0`, image 0.2.7): `instance_contract_version` 2
  with complete soft-body node references, which v5 requires (B08). blanket_flatten's initial states were prepared again in
  0.2.7 (`scripts/prepare_blanket_initial_states.py --tier <tier> --seed 0 --acceptance scene_layout`: the 0.2.3 archives
  are incompatible with the 0.2.7 backend identity) and are packaged in each instance. Every instance passed a strict
  fresh-process smoke (build, 3 hold steps with RGB, replay; `instance_matches`). The rigid instances are unchanged.

## Budget
Current helper preset (2026-10-04): **43200 s (12 h), 150M input / 10M output per trial**, native Codex / GPT-6 Sol xhigh,
10 tasks excluding Knot, Slotted Post Ring and Orbits, three named tiers, both modes, K=3 (180 trials).
See [helper operations](../standard_helper_operations_zh.md). Token limits are applied during post-run scoring;
missing usage blocks complete acceptance. These new packages have not yet been formally published.

Historical packages: agent wall clock **21600 s** (6 h) for every family (decision of 2026-10-01; before: 6 h, knot_untying 10 h). This is above
protocol v1.0's cap of 14400 s ([agent].timeout_sec ≤ 4 h): a TopoGym exception, so its results form their own budget
group (PROTOCOL D8) and the tasks would need a shorter budget on main. The privileged verifier may take `2 × budget + 1800`
s, the standard collect hook `3600 + budget + 1800` s. The token budget of the 2026-10 sweep is 120M input / 10M output per
trial (the protocol's default is 100M / 10M, D10), applied after the run.

## Tooling
Thin wrappers of the low-level action only (IK and joint moves, gripper, hold) plus state, recording, replay and
rendering; no task-level skills. New packages use the active release's tooling (v16, `[metadata].tooling_version = "16"`,
bound to their image by `runtime_binding.json`); v14 (the published `tasks/`, image 0.2.12) and Jianwen's v15 candidate are
frozen in the inventory:
`harbor_templates/topogym/common/rcb_topogym.py`, byte-identical in every copy (`ci_checks/check-topogym-tooling.py`, run
by `check-tooling-identity.sh`). v4 (Jianwen, 6a7c755b) folded the two family variants of the earlier render into it:
- a gripper hold keeps the native target when the commanded width round-trips (the width table drops the closed-end
  plateau): interlocked_claws' contact-weld pre-weld then survives the first step; no other family has an off-table
  gripper target, so their commands are unchanged;
- Genesis 1.2.1's per-substep FEM checkpoint store is bounded to one checkpoint (active FEM solvers only: knot_untying,
  rope_threading, orbits, slotted_post_ring; it leaked ~120 MiB of GPU memory per control step);
- knot's planar-clearance predicate is vectorized (same results).

`common/rcb_topogym_interlocked.py` and `rcb_topogym_ipc.py` are kept for the historical packages
(`ci_checks/topogym_tooling_versions.json`); the generators no longer pick them.

The FEM fix was checked on knot hard (laptop, 14 control steps): free GPU memory −0.9 MiB per step (unpatched −121.7),
the rope's vertex positions within the GPU's run-to-run noise (max 1.2e-7 m vs 9.4e-8 m between two unpatched runs), the
step time unchanged.

## Step time
The speed-up record from v4 (10-01) to v18 (10-06): one fixed benchmark per family plus end-to-end oracle times, in
[`../TOPOGYM_SPEEDUP_RECORD.md`](../TOPOGYM_SPEEDUP_RECORD.md). The profiles below are the 10-01 starting point.

A control step is 10 physics ticks; `Env.step` reads the world state after every tick (the task predicate and the history
need it) and renders every camera once (Nyx). Profiles of one sim alone (2026-10-01, seconds per control step):

| scene | host | step | physics | state readback | render |
|---|---|---|---|---|---|
| buzz_wire_3d easy | lab (RTX PRO 6000 Max-Q, EPYC 9534) | 1.01-1.10 | 0.17 | 0.85 | 0.02 |
| buzz_wire_3d easy | laptop (RTX 4090 Laptop, i9-14900HX) | 0.56-0.62 | 0.11 | 0.43 | 0.03 |
| cast_keyhole hard | lab | 0.56-0.60 | 0.19 | 0.35 | 0.02 |
| cast_keyhole hard | laptop | 0.34-0.38 | 0.14 | 0.18 | 0.03 |

The readback made about 700 separate GPU->CPU copies per tick (four per link, per entity): CPU and driver latency, which is
why lab's server CPU made it twice as slow and the GPU sat mostly idle. NUMA pinning and fewer torch threads changed nothing.
Since 0.2.7 `GenesisWorld.read_state` reads the rigid solver once per field (`_RigidReadout`, six copies per tick);
`scripts/check_read_state_batch.py` compares it with the per-link getters at every tick: bit-identical.
On lab with 0.2.7 (one sim alone, GPU 4): buzz_wire_3d easy 0.26 s per control step (readback 0.055), cast_keyhole hard
0.25 (readback 0.046): 4x and 2.3x faster. At that speed one reference-length solution (Jianwen's solvability proofs: cast_coil
6.5-7.3k control steps, cast_keyhole 18-21k, hedgehog_in_cage 2.3-9.6k) executes in about 0.5 h, 1.4 h and 0.2-0.7 h.

### Precision / speed study (2026-10-02)
Each candidate passed only if both layers passed: metrics (per-substep contact penetration, fresh-process replay, the task
outcome of replayed agent trajectories, deviation against the baseline's own 1e-4 rad sensitivity run) and frames.
- **Rigid families: float32** (tooling v6): 1.4-1.6x faster control steps (hedgehog_in_cage 2.5x); in 7 replays of real agent
  trajectories (interlocked_claws easy / medium, buzz_wire_3d easy, cast_coil easy / hard, cast_keyhole hard,
  hedgehog_in_cage medium) every outcome was kept (interlocked easy success 5/5), the per-substep penetration peak unchanged
  (0.589 vs 0.583 mm), frames identical. Rejected: solver_substeps 2 / 1 (Genesis bounds the contact time constant below by
  2 x the substep, so contacts got 4-16x softer and the tasks' 1 mm penetration predicate fired), 5 ms and 25 ms ticks.
- **Rigid families: CPU float64** (tooling v7, six families since v8; jobs/journal/2026-10-02/rigid_fast/): seven families run their physics on
  the CPU in float64 with one global constraint solve (`use_contact_island` off: the island machinery was most of the CPU
  constraint time); Nyx still renders on the GPU. Lab s/step, CPU vs v6's GPU float32: interlocked_claws easy 0.058-0.072
  vs 0.164, horseshoe_ring 0.092 vs 0.195, cast_coil easy 0.080-0.088 vs 0.146 (laptop GPU), buzz_wire_3d 0.11 vs ~0.17,
  fiber_bundling medium 3.3x; 8 CPU sims on one host run as fast as one (GPU throughput is flat with sims per GPU); cold
  builds halve (63-107 s vs 181-289 s). Accuracy: per-substep contact penetration, trajectory deviation and outcomes of
  replayed agent trajectories inside the GPU float32 noise envelope (interlocked_claws easy: 7 CPU vs 11 GPU runs, MWU p
  0.93 / 0.79 / 0.32; hedgehog_in_cage medium is a 1 mm threshold case on both backends), frames identical. Replays are
  bit-deterministic on one host (fresh processes, in-process rewinds). lock_picking stays GPU float32 (0.151 vs 0.132);
  interlocked_claws went back to it in v8 (claws medium: the CPU loses the teal piece in 5 of 16 noise runs, GPU 0 of 16;
  the same on CPU float32, so the backend, not the precision).
  Rejected on the CPU: GS_ENABLE_NDARRAY=0 (+30-48 s per build for ~13 ms/step), more threads (nothing with islands off),
  fewer substeps with a lower time-constant floor (1.0-1.6 mm penetrations).
- **Exact per-tick fast paths** (0.2.9): `Env.defer_rgb` (1.48x on CPU physics, render 0.043 -> 0.0006 s/step), the finiteness
  check as one iterative walk with a bulk check of the rigid readout, cached readout layouts and weld pairs (claws easy CPU
  0.069 -> 0.058 s/step). Checks: bit-identical replays on the CPU (final state_sha of claws easy, hedgehog medium, cast_coil
  easy equal to the study's runs), `scripts/check_fast_paths.py`, `scripts/check_read_state_batch.py`; on the GPU, which is
  not bit-deterministic, 0.2.9 vs 0.2.8 stays inside 0.2.8's own run-to-run spread (claws 7e-6, blanket 0.44 mm, IPC 1e-9)
  with the same frames up to renderer noise.
- **blanket_flatten: coverage skip** (0.2.8): the footprint union (~88 % of a step) is computed only when every cheap gate
  holds and on each control step's last tick (`Env.step` sets `Task.complete_metrics`); the goal decision is the same at every
  tick (`scripts/check_blanket_coverage_skip.py`).
- **IPC: exact cheaper diagnostics** (0.2.8): cached rest volumes, closed-form determinants, one vertex read per entity
  (`scripts/check_ipc_diagnostics.py`); read_state 0.9 -> 0.19 s per control step.
- **IPC: one solver substep + looser tolerances from a settled scene** (tooling v9 for rope_threading and slotted_post_ring;
  jobs/journal/2026-10-02/ipc_fast/): every
  run starts from the same settled state (a transplant of libuipc's native state, exact to 60 nm), the reference at four
  substeps. Settling: N = first capture after which the 25 ms peak speed stays < 5 mm/s and the 0.25 s drift < 1 mm (knot
  60, rope_threading 30, slotted 80 control steps); the ropes then creep quasi-statically (IPC's smoothed friction), the
  same at every dt (hold-only tests: 0.013-0.13 mm). A closed-loop pinch-lift-release (Jianwen's validated pinch), per
  control step: knot_untying 5.9x (IPC alone 9.5x; lift / slip / drop within 0.1 mm of the reference, centerline 0.44 mm
  at the end, worst 1.47 mm at the release, the same minimum tet volume ratio), rope_threading 8.1x (end 0.81 mm),
  slotted_post_ring 9.2x (end 0.30 mm; the reference inverts a cord tet at step 58 and this setting at step 61 on its own
  instance: a threshold); frames indistinguishable. Rejected: AL-IPC (crashes), MAS (slower). Settled instances are not
  hash-exact in fresh builds (GPU nondeterminism over the settle ticks; positions agree to 0.03-0.26 um), so `instance_exact`
  is 0 and `instance_matches` decides.

### fiber_bundling on the CPU: the articulated bundle (image 0.2.15-dev, 2026-10-05)
Target (the user, 2026-10-04): one full reference execution within about 20 % of the 6 h agent budget, the budget being
for the agent's reasoning; fiber hard may run longer (the user, 2026-10-05). Dual validation as above (metrics and frames;
lab journal topospeed/NOTES.md).
- **Cause.** The bundle is one articulated tree (slack lead, trunk, 8 / 16 strands of 10 links; ball joints): 318 DOFs
  (medium) / 558 (hard). Genesis' CPU branch factors each tree's mass matrix densely (O(n^3) per substep: 94 / 98 % of
  `kernel_step_1`, which was 67 / 80 % of a control step), and its skyline order keeps an entity's DOFs root-first, so every
  strand row of the constraint Hessian's envelope reached the slack lead's root (dense Cholesky again).
- **Engine patch** (`images/topogym/genesis-1.2.1-cpu-tree.patch`, applied by the Dockerfile with sha256 checks):
  1. tree-sparse mass matrix (CPU, no hibernation): structural entries only, and an LDL^T that walks each pivot's
     ancestor DOFs, i.e. the dense loop's nonzero updates in the same order. The physical state is bit-identical; only
     structurally-zero entries of the factor keep their initial +0.0 where the dense loop wrote x - a*0.0 (signed zeros).
     A state with inf / NaN in the mass factor (already broken) could spread differently.
  2. children-first skyline order inside entities with more than 64 DOFs (fill-free for a tree): round-off level. Robots
     (15-16 DOFs) and free bodies (6) keep the previous permutation, so every scene without such an entity is unchanged
     (the skyline envelope exists only on the CPU backend; GPU families are untouched by construction).
- **Exact fast paths** (task code): `body_points_batch` (one batched rotation for all fiber links, link-axis points only,
  so bit-identical) for `_strand_points`, and `advance_passage` skips its per-station loop when no station crossed a
  boundary plane in the tick. `scripts/check_fiber_fast_paths.py`: 0 differences in 3000 random pose sets, 300 strand
  sets, 3000 passage histories (1273 with crossings); task update 0.072 -> 0.020 s per control step on hard.

Bit-exactness of patch 1 per CPU family (one oracle trajectory each, v16 instances; SHA-256 of the rigid solver's arrays
after every control step, patched vs unpatched Genesis; with patch 2 added, every array of these runs is also identical
to patch 1 alone at every step):

| family (trajectory) | rows | physical state identical every step | final state_sha | outcome |
|---|---|---|---|---|
| interlocked_claws medium | 1364 | yes | equal | success / success |
| cast_keyhole easy | 2779 | yes | equal | - / - |
| hedgehog_in_cage medium | 2261 | yes | equal | success / success |
| buzz_wire_3d easy | 5141 | yes | equal | wire_touched / wire_touched |
| horseshoe_ring easy | 7181 | yes | equal | - / - |
| cast_coil easy | 6502 | yes | equal | success / success |
| fiber_bundling medium / hard (patch 1 only) | 200 / 200 | yes (every link pose and joint) | equal | - |

Fiber, per control step on lab (2 cores, hard rows 0-199): 2.10 s unpatched -> 0.64 (patch 1) -> 0.354 (+ patch 2 + fast
paths), solver substeps unchanged (4). Patch 2 against patch 1 on the medium oracle trajectory (13,770 rows + hold, open
loop): bit-identical until the bundle's first constraint solves (row ~550), then round-off grows in the chaotic bundle: the
floppy slack lead drifts by up to 2.2 mm (first > 1 mm at row 5975), the strand tips stay within 0.14 mm, the outcome is
the same (success); per-substep contact depth per role pair unchanged (max: sheath-gripper 0.086 mm both, sheath-ring
0.014 vs 0.014, strand-ring 0.012 vs 0.011, strand-strand 0.002 vs 0.002); rendered frames of both at 12 rows show the
same bundle, strands and ring passage (sheets in the lab journal). The children-first order applied to every
entity (robots included) gave 12 mm on the slack lead with the same tips, hence the 64-DOF threshold.
The built image (labv17 0.2.15-dev) reproduces the tested code: interlocked_claws medium's 1364 rows bit-identical to
unpatched v16 (physical state) and to the tested patch at every step; fiber medium rows 0-399 bit-identical to the tested
patch + fast paths.

| tier | oracle, closed loop (lab, 2 cores) | fresh-process replay of its trajectory | before |
|---|---|---|---|
| medium | success, 13,770 steps, 69.0 min (19.2 % of 6 h) | success, the same final state_sha (bit-exact), 51.5 min | 125.5 min |
| hard | success, 25,554 steps, 205 min (57 % of 6 h; the user accepts a longer fiber hard) | success, the same final state_sha (bit-exact), 152 min | ~15.6 h (2.2 s/step); tree factor alone 5.6 h |

Fiber hard's fresh replay keeps the contact depths of medium (max: sheath-gripper 0.086 mm, sheath-ring 0.021,
strand-ring 0.020, strand-strand 0.006).
Rejected: solver substeps 2 / 1 (the closed-loop hard oracle stalls on its 1 mm sheath-tracking gate: s1 at step 1249,
s2 over comb_01's stage time budget at step 2588, while s4 with every other change passes; open-loop medium replays
still succeed, so only the closed loop separates them), a coarser slack lead (an instance change, not needed), the GPU
backend (fp32: 2.11 s per control step for the 558-DOF tree), more CPU threads (1.5-2.1x slower).

### Deterministic GPU physics (tooling v17, 2026-10-05)
Grading replays re-run an agent's actions in fresh processes; on the GPU families they did not reproduce the live run. Two
fresh replays of one blanket_flatten easy agent trajectory (EtWpiBp, v16) differed by 1.6e-13 m after the first control
step, 1.7 mm by step 99, 37 mm at most, and in the outcome (one success, one not). Stage isolation (each sub-stage of a
tick run three times from identical engine buffers) located the causes, all scheduling-order arithmetic, none in the
model. `harbor_templates/topogym/common/rcb_topogym.py` (`_deterministic_gpu_physics`, installed by every Session right
after genesis.init; no Genesis file, image, frozen state or instance sha changes) removes them:
- **Rigid constraint-solve arm pinned** (every GPU scene): Genesis 1.2.1's `func_solve_body` is a `qd.perf_dispatch`
  wall-clock autotuner that alternates a "monolith" and a "decomposed" arm and re-times them every 5 s, so the arm that
  integrates a substep depended on host load. Pinned to the monolith. Changes the rounding of blanket_flatten,
  lock_picking and of the robots / rigid bodies of the IPC scenes (knot_untying, rope_threading, slotted_post_ring,
  orbits). CPU scenes (interlocked_claws included) are unchanged: the CPU backend only has the monolith arm.
- **IPC families: not yet reproducible.** Their robot (rigid) solve is now deterministic, the libuipc FEM / ABD solve is
  not: float atomics in its PCG dot products, SpMV, gradient and MAS-preconditioner assembly and its contact candidate
  order, plus a stale robot mass matrix read by the first IPC step after a settled-state restore. Both are being fixed
  for the next release (a deterministic libuipc build and a forward-dynamics recompute after the restore); until then the
  tolerant grading replays (R-hold, as in v16) decide for these families.
- **Fixed-point sums** (blanket_flatten, the only PBD scene): the PBD stretch / bending scatter, the particle-collision
  gather (spatial-hash order) and the PBD-rigid coupling forces / torques on robot links (`_bound_pbd_rigid_contacts`)
  are int64 sums of contributions rounded once to 2^-48 m / 2^-32 N (N m); a non-finite or out-of-range contribution
  (16 m, 2^16 N, 2^17 N m) makes the result NaN, so the instability guard ends the episode as before. The constraint
  math, iterations and apply loops are Genesis' expressions. Largest contributions over the whole replay: 1.57 mm
  (collision), 0.96 mm (stretch + bending), 1.9 N, 0.42 N m.
- **Evidence** (lab RTX PRO 6000, image 0.2.14-dev; lab journal topogym_v1/determinism/NOTES.md): five fresh-process
  replays of EtWpiBp (1443 rows + 80-step hold) bit-identical at every control step on every digest (particle positions
  and velocities, rigid links / joints, contacts in canonical order, the grasp-assist record, state_sha; final
  e33f375dac5296de); in-process whole-tick repeats identical; unpatched v16 differs from row 0. The trajectory was
  recorded under v16's nondeterministic physics, so its patched replays agree with each other, not with v16's live run.
- **Speed** (solo, lab GPU 7, image 0.2.14-dev): blanket_flatten easy (EtWpiBp rows 0-199) 0.373 s per control step
  (median 0.356) vs v16's 0.360 (0.342), about +4 %; lock_picking easy (rows 0-299) monolith 0.0770 / 0.0770 vs autotuned
  0.0768 / 0.0782 (no cost; the decomposed arm alone 0.0819), and the two autotuned passes from one state end in different
  digests while the monolith passes are identical. (Measurements on a GPU shared with IPC sims were 4-6x inflated.)

### Exact speed-ups (tooling v18, 2026-10-05)
Target as above (one full reference execution within about 20 % of the 6 h agent budget). Every change below leaves
results identical; each has a check script and a lab replay with both versions compared (lab journal
topogym_v1/topospeed/NOTES.md).
- **blanket_flatten.** Two costs dominated the hard reference: the coverage union in the settle phases, and the PBD grasp
  assist while a closed hand had no hold yet. In those grasp windows `SoftGraspBackend.candidates()` cost 0.5 s per hand
  per tick: trimesh distances of ~450 particles to both finger surfaces, and one 8181-particle `material_patch` per center.
  - The coverage union is skipped inside a control step when an upper bound is 1e-3 below the threshold. The decisions
    are identical at every tick on all three tiers.
  - Finger-surface distances are computed only where they can decide the contact test or the nearest point. A rigorous
    lower bound selects them: the box and the hull planes, less 1 um.
  - A patch is built from its center's cached material neighbourhood.
  - `exposed_patch` scans only the patch's horizontal reach.
  - Checks:
    - `scripts/check_grasp_candidates_exact.py`: 8400 cloth and rope cases identical to the previous code;
    - live calls recorded on lab: 1757 blanket and 13 rope `candidates()` calls identical; 0.51 -> 0.011 s and 0.35 -> 0.022
      s per call.
  - Measured (shipped hard oracle, 4 cores, rgb on, lab GPU 7 next to light CPU sims): **29.1 min** (8 % of 6 h). The run
    is byte-identical to the v17 run without the changes: the same 4075-step trajectory, task result and final state_sha
    c105e712e2af818b. Its close / contact windows now cost 0.5-1.0 s per control step; they were 3.7-5.4 s with the
    previous oracle.
  - Rope acquires within a tick or two, so its episodes gain only seconds.
- **Families with a final release** (buzz_wire_3d, cast_coil, ...). `World.read_state` runs every tick and read the
  release boxes and robot cover planes in a Python loop: 1.1-1.5 ms per read. It also re-read the solver's welds to verify
  the rigid grasp bindings: 0.77 ms.
  - `ReleaseGeometry.read` now evaluates the same products as stacked matmuls over equal shapes.
  - The per-tick binding check (`verify_current_bindings`) reuses the cached weld read; acquire, release and restore
    still refresh it.
  - Shadow replays of the graded easy trajectories were identical at every read: 51,403 (buzz) and 65,019 (coil).
  - Per control step (2 cores, rendering off): buzz 92 -> ~74 ms, coil 65 -> ~53 ms.
  - The rest of buzz's extra cost over coil / keyhole is collision detection over its 1298 wire geoms (22 ms, of which
    broadphase 13). An engine patch would need pair-order identity, so it stays a later option.
- **fiber_bundling** (v17 tree factor + fast paths; 2 cores, rendering off), ms per control step:

  | term | medium | hard |
  |---|---|---|
  | total | 227 | 413 |
  | kernel_step_1 | 71 | 145 |
  | resolve | 54 | 137 |
  | detection | 11 | 16 |
  | task | 15 | 24 |
  | read_state | 15 | 19 |
  | grasp health | 5 | 5 |
  | oracle's per-tick record | 30 | 37 |

  The oracle's references run 69 / 205 min. A fresh-process replay of the same trajectories, which is what an agent
  following the same motion pays, runs 51.5 / 152 min. The difference is the oracle workflow's own work.
  - About 30-37 ms per step is the state record that `QualificationWorkflow` freezes at every physics tick for its
    invariant monitor.
  - That monitor must observe every tick: a tick-level violation latches and fails the stage, and `run()` raises on a
    missing tick. Freezing less often is therefore not equivalent.
  - An exact option, for Jianwen: give that owner monitor an unfrozen or lazily frozen record. The values and decisions
    stay the same, but `Env.tick_record`'s sink contract changes. Estimated medium ~62 min, hard ~189 min. Not done in v18.

## Grading: two passes
- **Privileged.** The verifier (separate sandbox, GPU, no network) replays `/app/output/trajectory.npz` from
  `tests/instance.json` twice in a fresh process and renders `replay.mp4` **during the second replay**. Success: both
  replays meet the task's predicate (grading replays since v16: see Grading replays). The physics runs on the GPU and is not bit-deterministic: `deterministic` is
  reported, not required; the rebuilt frozen scene must match (`instance_ok`, v5).
- **Standard.** Pass 1 is the live episode in the `sim` sidecar. When it ends the service writes `trajectory.npz` and
  `episode.json` (live result, final-state hash, `live_rows`: the rows the live episode executed). The collect hook
  `environment/sim/finalize.sh` sends SIGUSR1, waits until the service has exited (its GPU memory is free), then replays
  the live rows **once** in a fresh process (`environment/sim/replay.py`, a grading replay since v16), rendering
  `replay.mp4` during that replay, and writes `final.json`. The verifier (shared client image, no network) grades `final.json`: success = live ∧ replay; a
  replay without a result is a `grader_error`, not the agent's 0.

## Grading replays (tooling v16)
The physics of six families runs on the GPU, which is not bit-deterministic: blanket_flatten (PBD cloth), knot_untying,
rope_threading, slotted_post_ring, orbits (IPC FEM rope / cord) and lock_picking (GPU float32 rigid bodies). A genuine
live success could miss its own fresh replay: blanket medium standard trial ihy7Nru (v14) succeeded live at row 3089 and
the grader's replay of those rows did not (a speed spike restarted its confirmation at the last row). The user's
decisions (2026-10-03): live-strict, replay-tolerant grading, and a tolerant replay may only confirm a strict success,
never turn a failure into one.
- What the agent sees is unchanged: the live episode (standard) and its own Session (privileged) use the instance's
  thresholds.
- A grading replay (`Session.replay(actions, physics_steps=..., grading=True)`: the standard collect hook's
  `environment/sim/replay.py` after a live success, both replays of the privileged `tests/grade.py`, the `rcb_topogym.py
  replay` CLI) of one of these families (`rcb_topogym.REPLAY_TOLERANCES`)
  1. runs the trajectory's rows with the instance's own thresholds: a success there is a strict success
     (`strict_success`, `success_row`);
  2. if the episode has not ended after the last row, holds the final targets for up to `GRADING_HOLD_S` = 2 s (80
     control steps), stopping at the first success or failure, so a confirmation that starts a few ticks later than live
     can still complete (a confirmation running at the last row carries on); during this hold only, the task's predicate
     uses the replay tolerances below: continuous thresholds, each one of the task's own parameters, loosened for the hold
     and restored after it. Binary / topological conditions, failure predicates and the length of every confirmation
     window are never changed.
- Standard: success = the live success (strict) AND the replay's success AND the existing conditions; a live failure is
  final whatever a replay shows, and the collect hook then replays plainly (instance thresholds, no hold).
- Privileged: success = both replays succeed AND at least one of them is a strict success within the trajectory's own
  rows (the trajectory itself reached the goal at least once): `strict_goal_reached` / `strict_goal_row`, verdict.json
  `evidence.strict_goal` (which replay, which row). A recording stops at the agent's own success, so the texts tell the
  agent it may append copies of the final row for a replay whose confirmation ends a few ticks later.
- Evidence: the replay's status carries a `grading` record (`revision`, `rows`, `strict_success`, `success_row`,
  `hold_steps`, `hold_limit_steps`, `success_in_hold`, per relaxed threshold its `live` and `replay` values and, over the
  confirmation window that ended in success, `window_worst` and `live_held`; `tolerance_needed` = the pass needed a
  slack). Privileged: `verdict.json` `evidence.replays[].grading`; standard: `replay.verdict.json` and `final.json`
  `replay_grading` (+ `replay_grading_policy`: false after a live failure). Both graders add the numeric reward fields
  `replay_hold_steps` (the most hold steps a replay used) and `replay_tolerance_needed` (0/1).
- The CPU families are not in the table: their grading replays are plain replays (bit-exact; the v14 tooling and ours give
  the same verdicts and state hashes), and a plain replay's success is a strict success.
- The hold is 2 s of simulated time at the instance's control rate: 80 control steps at 40 Hz, 50 for merged-v16's
  rope_threading (one 40 ms tick per control step).
- The instruction texts (grader details) and READMEs of the six families state all of it; agents in privileged mode can
  call `s.replay(actions, grading=True)` to check a trajectory the way the verifier will.

### Replay tolerances and their evidence
Rule: a slack only where a continuous threshold's quantity shows a material replay-to-replay spread at the same control
step; slack = 2 x the largest measured spread, rounded up. Spreads below 1 % of a threshold get none; branch-like
divergence (another contact outcome) is not noise a tolerance can absorb, so it gets none either (the hold still applies).
Lab, rcb-topogym:0.2.12-cu128, GPUs 5-7 under the v14 sweep's load, 2026-10-03; probes in
`/DATA2/qineng/rcb/topogym_v1/v15/out/` (`probe_spread.py`: R in-process replays + 80 hold steps, every control step's
metrics, margins against the live thresholds, positions).

| family | threshold (task parameter) | live | grading hold | measured spread (trajectory, replays) |
|---|---|---|---|---|
| blanket_flatten | coverage (`minimum_coverage_ratio`) | 0.95 | 0.92 | the user's numbers (2026-10-03 20:50; first 0.93). Medium trial ihy7Nru (3089 rows), 5 replays: coverage at the last row 0.927 / 0.931 / 0.956 (and one success at row 2868 at 0.943): about 3 points between replays of one long trajectory; short scripted operations (blanket fix notes): at most 0.7 points |
| blanket_flatten | particle speed (`maximum_speed_m_s`: the "settled" gate and the final settling's speed) | 0.03 m/s | 0.08 m/s | the user's numbers (20:50). Through tooling 18 the speed was PBD's last-substep velocity, which on cloth at rest spikes and restarts the confirmation; since tooling 19 it is the end-of-tick displacement over the tick, numbers unchanged (Cloth settle speed below). ihy7Nru replays, control-step samples: replay B 0.0715 (row 3058), then in its hold 0.0633 / 0.0601 / 0.0666 (+10 / +50 / +70: no confirmation within 2 s at coverage 0.958); another replay 0.044 at the last row; a traced v15 replay 69 of its last 400 rows above 0.03 (4 above 0.08, max 0.097, the agent still moving) and 1 of 80 hold steps (0.065) |
| blanket_flatten | displacement from the start of the confirmation 3 mm (`maximum_drift_m`), 0.5 s window, height, stretch | unchanged | unchanged | not relaxed: the displacement limit is what proves the cloth is still |
| knot_untying | rope speed (`terminal.maximum_speed_m_s`: quiet and final settling) | 1 mm/s | 1.25 mm/s | v14 success WWfaVD9 (365 rows), 2 replays, both strict successes at row 365: the window's speeds 0.43-0.90 mm/s, same-step spread up to 0.12 mm/s (just after the release); rope vertices within 11.7 um |
| knot_untying | planar clearance 8 mm, table band (z), drift 1 mm; the release (terminal v5 since v16: 1 mm from every robot part that can move, world-fixed bases may touch, no overlap with any robot part's interior; v14: 5 mm from every part by bounding boxes) | unchanged | unchanged | same replays: 16.4 mm (spread 1.5e-8 m); margins 2.8 / 1.19 mm (< 1e-8 m); 0.7 um; 7e-8 m (measured on v14's release check). The release conditions are geometric: never relaxed |
| rope_threading | merged-v16 profile: rope speed 10 mm/s (was 1), crossing aperture (0.1 mm margin, 1 mm compression allowance, round-ring passage test), thickness planes | unchanged | unchanged | no trajectory on the v14 instances yet (the sweep's rope trials still ran): no slack until a measurement; the profile's live thresholds are not loosened again. The lab oracle sweep's rope hard standard (4aac2a4e6) failed exactly where the hold helps: live success at row 1864, its replay of those rows without one |
| slotted_post_ring | ring speed 1 mm/s / 0.02 rad/s, containment (1 mm boundary, z band), separator | unchanged | unchanged | v12 agent ULq3ATD (92 rows + hold), 3 replays: ring position 3 um, speeds 6e-6 m/s / 6e-5 rad/s (< 1 %); the cord, beads and discs (remainder) diverge by 0.3-8 mm (branch-like) |
| orbits | target speed 1 mm/s / 0.02 rad/s (cord and handle), containment, separator | unchanged | unchanged | v12 agent HHnLEzf (154 rows + 80 hold), 1 replay (the second was stopped by the RAM guard): the cord crept at 1.9-3.3 mm/s through the hold (above the limit, not near it); handle 0.9-2.1e-3 rad/s; separator and z margins constant. No spread measured: no slack |
| lock_picking | shaft-bore excess 10 um, insertion margin 1 mm, slot clearances | unchanged | unchanged | v12 agents oRtMyhk (1178 rows) / JPLHPHT (1285 rows), 3 replays each: bit-identical up to control step 543 / 476, then a contact branch (32-42 um at onset, 1.2 / 5.7 mm key position and 0.27 rad rotor angle at the end); no success trajectory exists to measure at the goal |

### Cloth settle speed: end-of-tick displacement (tooling v19, 2026-10-06)
The user's decision (2026-10-06, "option 1"): a cloth particle's speed is its end-of-tick displacement over the tick,
(x(t) - x(t - dt)) / dt with dt the 2.5 ms physics tick. It is no longer the velocity Genesis' PBD solver stores, which
is the last solver substep's (pos - ipos) / substep_dt (0.625 ms; 4 substeps per tick). The thresholds are unchanged: live
0.03 m/s, grading hold 0.08 m/s, displacement from the start of the confirmation 3 mm (`maximum_drift_m`), window 0.5 s.
- Why. Blanket very_easy (Jianwen's oracle; lab probe 2026-10-06): after the release, particle 7458 sits in a PBD
  self-collision 2-cycle with three neighbours at the 8 mm particle-size threshold. Stretch and bending move it about
  50 um, the self-collision puts it back, so it alternates between two points 20.65 um apart every substep. Its end-of-tick
  position is constant to 1 um, but the stored velocity reads 33.04 mm/s, above the 30 mm/s gate, for as long as the
  episode lasts. With the old definition standard could never pass; privileged passed only through the 0.08 m/s hold.
- Where. `topogym/world/genesis_world.py`:
  - `advance()` keeps every particle entity's positions at the start of the tick;
  - `read_state()` reports `particles[<name>]["velocity_m_s"]` = (x - x_tick_start) / physics_dt once a tick has run;
  - before the first tick of an episode (after `reset_clock`), and on a restored state captured before any tick, it reports
    Genesis' stored velocity as before, so the birth readout, the instance state hashes, `soft_state` and the oracle's
    archive-exact birth check are unchanged;
  - `capture_state` / `restore_state` keep the tick-start positions per captured state, so a rewind reports the speed the
    state had when it was captured.

  Every consumer reads this one field: the Task's settled gate, the final settling's quiet test
  (`topogym/evaluation/terminal/settling.py`), the grading replays' `particle_speed` threshold (through the task's metrics),
  the particle speed guard (`_guard_particle_speeds`; its 20 m/s limit was calibrated on last-substep velocities, see the
  follow-ups), the blanket oracle's quiet wait and its audit, `Session.objects()` and the cloth diagnostics. The frozen PBD state codec's backend identity (`topogym/world/state.py`,
  `pbd_table_friction.py`, Genesis' files) does not include `genesis_world.py`, so the packaged cloth states restore as
  before. The instruction texts are unchanged: they state a linear speed limit, and the agent's Session reads the same field.
- Not changed:
  - `topogym/world/physics/cloth_preparation.py` keeps reading Genesis' velocity: it is the control variable of its
    released-stable acceptance;
  - `topogym/tasks/blanket_flatten/below_easy_preview.py` and `scripts/check_builder_feedback.py` keep their native
    continuity checks;
  - rigid bodies and FEM vertices have their own readers.
- Validation (lab GPU 4, 2026-10-06). Grading replays of graded trajectories under the patched world, compared with their
  v18-sweep / below-easy grades. Per tick, old = Genesis' velocity read by a hook, new = the displacement; the speeds are
  the cloth's maximum over its particles.

  | trajectory | old grade | replay, new speed | at rest (old <= 0.03 m/s): abs(new - old) median / p99, mm/s | moving (old > 0.1 m/s): new / old p10 / median / p90; ticks with new <= 0.03 m/s | settled gate differs: new only / old only (ticks) |
  |---|---|---|---|---|---|
  | easy, 718 rows | strict, row 718 (tick 7176) | strict, row 718 (tick 7176) | 0.95 / 17.4 | 0.16 / 0.68 / 1.04; 807 | 845 / 28 |
  | medium, 1696 rows | strict, row 1696 (tick 16953) | strict, row 1696 (tick 16953) | 1.04 / 21.2 | 0.38 / 0.94 / 1.11; 262 | 2041 / 312 |
  | hard, 4855 rows | strict, row 4855 (tick 48549) | success in the hold's first tick (48550), no tolerance needed | 0.79 / 29.2 | 0.22 / 0.84 / 1.08; 206 | 2800 / 499 |
  | very_easy, 1454 rows | privileged only through the hold (21 hold steps); standard failed | strict, row 637 (window's worst speed 0.69 mm/s, coverage 0.978) | 4.28 / 5.16 | 0.86 / 0.98 / 1.11; 0 | 331 / 6 |
  | easier, 633 rows | oracle failed (lay_half: assisted grasp lost) | no success; the goal is never reached either way | - | - | 129 differ |

  - Old-definition artifacts. At rest the stored velocity has a floor of about 5 mm/s (very_easy: at least 5.27 mm/s
    over 3067 resting ticks), while the displacement reads about 0. It also spikes on cloth that does not move: easy
    particle 3510 read 0.156 m/s against a displacement of about 1 mm/s. Such ticks are the "moving" ticks with a new
    speed <= 0.03 m/s in the table. The ihy7Nru replay spikes of 0.04-0.07 m/s on cloth at rest (Replay tolerances) are
    of the same kind. The very_easy chatter particle: 33.0 mm/s old, about 1e-5 m/s new.
  - Moving cloth stays unsettled. In very_easy's oracle phases the new speed exceeds 0.03 m/s in 1200 / 1200 ticks of
    lay_corner (median 0.162 against 0.170 m/s old), 1098 / 1200 of turn_corner (0.1075 / 0.1076) and 256 / 260 of the
    release.
  - Where the settled gate differs, the new definition is mostly settled where the old one read an artifact. The few
    old-only ticks are slow motion near 0.03 m/s, where the tick's average exceeds the last substep's velocity (a particle
    decelerating within the tick). Goal decisions differ at a few ticks both ways (easy 10 new only / 1 old only, medium
    52 / 24, very_easy 324 / 0); easy's and medium's success rows are unchanged.
  - Hard: one tick later. At tick 48349 a particle decelerating within the tick reads 58 mm/s as displacement and at most
    30 mm/s as last-substep velocity, so the 0.5 s confirmation starts one tick later. The v18 trajectory's last row (9
    ticks) ends at the old success tick 48549, one tick short of a strict success; its replay succeeds in the first tick
    of the hold. The v19 oracle run stops one tick later (tick 48550, the same 4855 rows) and grades strictly in both
    modes (v19 re-grades below).
  - Physics identity. Per-tick SHA-256 of the cloth positions, easy rows 0-300 (3000 ticks): the patched and unpatched
    world, with and without the speed hook, are identical at every tick. On the same packages the patched world gives the
    same instance state hashes (v18 / below-easy instances: easy 34a6293dbb63deb5, medium 437ce3bc96b437f9, hard
    e1631bc691da83c8, very_easy 80c2527aa9f1964c). Only the reported speed changes. (The v19 packages' blanket state
    hashes change anyway, for the same restored physics: the re-key record names the profile merged-v19, as with
    merged-v18.)
  - Visual. very_easy's verifier video around the chatter onset (tick ~6041) and after the release: the sheet lies flat
    and still from the release on; mid-lay frames show the carried corner moving.
- v19 re-grades (lab, 2026-10-06). The five blanket instances of the release (candidate built and preflighted with
  Jianwen's pipeline, exact restores; image `rcb-topogym:0.2.17-dev-cu128` = sha256:06554307), graded with his launcher
  (`scripts/oracle_runners/test_harbor_oracles.py --candidate --no-nop --execute`, both modes) on lab GPUs 4 / 7, at most
  two blanket simulations per GPU. Times in minutes, under lab load: privileged = the oracle's live run (the reference
  execution) and the verifier's two replays; standard = the live episode and the collect hook's replay. No pass needed
  a replay tolerance, and every grading replay succeeded strictly within the trajectory's rows (hold 0). Each tier ends
  in one state hash across both privileged replays and the standard live episode and replay.

  | tier | mode | grade | rows | success tick | strict success | state hash | time |
  |---|---|---|---|---|---|---|---|
  | easy | privileged | 1 | 718 | 7176 (= v18) | row 718, both replays | 71cd36a47dc1538c | oracle 7.5, verifier 14.1 |
  | easy | standard | 1 (live 1, replay 1) | 718 | 7176 | live; replay at row 718 | 71cd36a47dc1538c | live 5.9, replay 6.1 |
  | medium | privileged | 1 | 1696 | 16953 (= v18) | row 1696, both replays | a0ae567c95fb796f | oracle 21.8, verifier 38.9 |
  | medium | standard | 1 (live 1, replay 1) | 1696 | 16953 | live; replay at row 1696 | a0ae567c95fb796f | live 19.6, replay 19.3 |
  | hard | privileged | 1 | 4855 | 48550 (v18: 48549) | row 4855, both replays | a8da7bf066549ba6 | oracle 54.1, verifier 106.5 |
  | hard | standard | 1 (live 1, replay 1) | 4855 | 48550 | live; replay at row 4855 | a8da7bf066549ba6 | live 48.1, replay 51.8 |
  | very_easy | privileged | 1 | 637 | 6363 | row 637, both replays | 51c8d213bf1b7bc8 | oracle 6.4, verifier 12.0 |
  | very_easy | standard | 1 (live 1, replay 1) | 637 | 6363 | live; replay at row 637 | 51c8d213bf1b7bc8 | live 4.9, replay 5.2 |
  | easier | privileged | 0 (score_failed) | 633 | - | none: the oracle stops at lay_half, "assisted grasp lost" (edge ratio 1.3014 > 1.3), then 80 hold steps | 942d21cc4ef26576 | oracle 6.7, verifier 12.9 |
  | easier | standard | not run (blocked_dependency: no grade-1 privileged trajectory) | | | | | |

  Against v18: easy and medium succeed at the same rows and ticks; hard one tick later; very_easy now passes both modes
  strictly (v18 below-easy grades: 1454 rows, privileged only through the hold, standard failed); easier is unchanged,
  an oracle problem left for Jianwen. The reference executions stay under 72 min (hard 54.1). These grades ran on v19 itself
  (89cc32674). The next commit, da47d3a49 (rope below-easy profile), changes the public source hash, so candidates built
  from later heads need a rebuilt image.
- Follow-ups for Jianwen (not done):
  - Rigid bodies: their speeds are the rigid solver's velocities at the end of the tick (the IPC coupling's for
    IPC-coupled bodies). The families that settle rigid bodies could use the same end-of-tick displacement if a similar
    artifact shows up; none has been seen.
  - IPC families: FEM vertex velocities are what the IPC coupling writes back per IPC frame; no change unless a
    measurement shows a similar artifact.
  - `cloth_preparation.py`: its released-stable acceptance still tests Genesis' velocity. Reading the displacement there
    would change which prepared states are accepted, i.e. it would make new instances; worth doing if a preparation ever
    stalls on the same chatter.
  - The particle speed guard's 20 m/s limit was set from last-substep velocities. The displacement averages a tick's
    substeps, so a blow-up's first tick may read lower; the traced blow-ups reached 1e3-1e5 m/s by their third tick, so
    the guard should still end them no later than the tick in which the cloth falls (it runs before the task's
    predicates), but this was not measured. Replaying the press stress tests of the 2026-10-03 blanket fix notes with
    Genesis' original contact kernel under tooling 19 would confirm it.

## Physical-validity policy (tooling v16)
The user's general policy (2026-10-03 ~21:30, its forcing rule settled 2026-10-04 ~01:10) replaces v14's R1 as the
episode-ending contact rule. Penetration depth measures the contact solver, not the agent: a passive impact reaches 4-5 mm
(QKSrtdL: the released claw landing on the other one, 4.6-4.9 mm; a released claw falling, 4.4 mm), the press and push
rams at the capped torques stay at 0.1-2.4 mm, and the deepest readings come from jams and impacts (below). So the policy
separates who caused what, with no per-artifact exceptions (`rcb_topogym.py` "physical-validity policy",
`_install_rules`; every family; the t = 0 states and hashes unchanged):
0. The environment model (the task owner's: the release profile and the task code, frozen in the instance, stated in the
   texts; the same in the live episode and every replay): materials, timing, grasp assistance, which robot links touch a
   soft body. The policy never changes it.
1. Guards (unchanged from v14): arm drive torque caps, the fingertip-table guard, the standard service's joint-speed
   limit and IK-jump refusal.
2. The task's own stated rules (the task owner's): the success predicate, strict live (thresholds, confirmation windows,
   release conditions such as knot_untying's terminal v5, whose overlap check withholds success and never ends the
   episode), and the failures the agent caused, which end the episode (wire / fiber touch, rotor limit, chain link, a body
   or the cloth fallen, and the tooling's R2: a crushed soft volume or a stretched cord attachment persisting 0.25 s).
3. A simulator breakdown ends the episode as an infrastructure error (`simulator_instability`, evidence in
   `status()["instability"]`): a non-finite rigid state, a cloth particle faster than 20 m/s, an invalid native IPC
   state, a rigid task contact deeper than 10 mm (`BREAKDOWN_PENETRATION_M`); unless the forcing condition (4) held on any
   tick of the 0.25 s before it (`FORCING["attribution_s"]`): then it is the agent's
   `forced_breakdown: the simulation broke down (<what>) right after forcing: <which arm, drive, contact, how long ago>`.
4. Evidence only, never an episode end:
   - **forcing** (`FORCING`): an arm drive, not a gripper drive, at 95 % of its torque cap or more while that arm, or a
     movable body it holds (both fingers touching it, or its assisted-grasp binding), presses on anything else with
     20 N or more in total. A run of it on every physics tick for 0.5 s is a forcing event (`status()["forcing"]`: arm,
     drive, % of cap, what pressed on what, the largest force, length; `s.safety()` / `meta["safety"]` report the loads
     and the events). It does not hold a success by itself: the graders record it (`forcing_events`, verdict.json
     `evidence.forcing`, `final.json` `forcing` / `replay_forcing`) and show it, with frames, when a success is held;
   - every tick's deepest non-held and held-finger task contact (`s.safety()`, the service's `meta["safety"]`). A tick
     deeper than 3 mm (held finger: 4 mm), or a contact above 1 mm (held: 2 mm) for 0.25 s, is a review event
     (`status()["review"]`: kind, control step, physics tick, bodies, depth, force, length). A success whose episode or
     replay had one is not credited automatically: success 0 with `success_pending_review` 1 (and `review_events`,
     `review_max_depth_mm`), the review and forcing events in `verdict.json` `evidence` (privileged) or `review.json`
     (standard, from `final.json`), frames around both in `review_frames/` (`Session.render_review_frames`: one more
     replay, after the verdict). A clean success is credited automatically.

Why forcing is evidence and not a stop (the user's decision, 2026-10-04 ~01:10, from the calibration below): as an
episode end it stopped the claws easy standard success oDonuzB (its right waist at the 12.9 N m cap for 2.2 s while the
piece it held pressed the other piece at 80-130 N); the claws easy reference oracle itself forces for 0.33 s; most of the
rulesfix_1003 rams never force for long (the table guard keeps the press rams' drives at 12-85 %, the held-claw ram is
one impact); and the exploit the rules exist for, a 15 cm tug pulling claws hard's interlocked pieces through each other
to a success, forces for 3 ticks only: its 4.8 mm depth is what showed it, and the review rule holds that success.

The forcing memory that attributes a breakdown and the review contacts' persistence are task history
(`task_state["rcb_rules"]`, absent while zero), so a rewind restores them. Standard trials whose live episode v14's R1
ended need a rerun (their agent never got to continue): QKSrtdL (claws hard) and diFXNtw (claws medium). No finished v14
privileged replay was cut by R1 (all ended without an episode end, or in success).

### Calibration and validation (lab 2026-10-03 / 04)
Per physics tick, per arm: the largest arm-drive control force as a fraction of its cap and the contact force between
the arm's own bodies and the rest (`/DATA2/qineng/rcb/topogym_v1/v15/bin/pstop_probe.py`, outputs in `v15/out/pstop/`;
the old tooling with R1's verdicts off for the measurement, then the committed tooling for the outcomes). "Longest" = the
longest run of consecutive ticks with the forcing condition (95 % of cap, 20 N); a forcing event from 200 (0.5 s).

| case | longest run (ticks) | deepest task contact | outcome with the local tooling v15 (the v16 rules) |
|---|---|---|---|
| claws hard privileged success qqiVt2v | 0 | 0.6 mm | success, clean; state hash `0074e6165c952f48` = v14's verifier replays |
| claws easy privileged success UWPrhoN | 0 (wrist wraps at 99 % in free air, 1 N) | 0.2 mm | success, clean; `78159f7d9288c104` = v14's |
| claws easy reference oracle (`claws_easy.npz`) | 131 | 0.5 mm | success at step 881, clean; `057df6735858e33c` = v14's |
| **claws easy standard success oDonuzB** | **890** (2.2 s: the right waist at 100 % of 12.9 N m while piece 1 pressed piece 0 with 80-130 N; later 300+ ticks at 300 N) | 0.5 mm | **success, credited, clean**; its forcing events in the evidence (as an episode end, the stop stopped it at step 984) |
| claws hard standard QKSrtdL (the passive impact), its 50 rows + an 80-step hold | 0 (drives at 2-10 %) | 4.9 mm | no failure in its rows (a review event); in the hold the released claws fall: "A task body fell below the table" at step 75 |
| the same with the breakdown bound lowered to 4 mm | 0 | 4.6 mm | `simulator_instability` at step 50: a breakdown without forcing |
| claws medium standard diFXNtw, its 8313 rows + 80 | 43 | 0.9 mm | no episode end, no review event (its live R1 failure, 1.5 mm, is in no replay: live state != replay state) |
| hedgehog press ram, fast (Panda; rulesfix_1003) | 446 | 0.5 mm | no episode end; a forcing event (joint 3 at 100 % of 50 N m, 124 N on the cage) |
| held-claw ram, 15 cm (claws easy) | 1230 | 0.3 mm | no episode end; a forcing event |
| claws easy push ram | 130 | 0.3 mm | no episode end, no forcing event (0.33 s) |
| press rams, fast (coil / horseshoe / keyhole; rulesfix_1003) | 0 (the table guard stops the press 15 mm below the tabletop: drives at 12-85 %) | 2.4 / 1.1 / 1.3 mm | no episode end |
| held-claw ram, fast, 6 cm (claws hard; rulesfix's `d_claws_hard_heldfast_rules`) | 1 (one impact at 100 %, then the claw slides to its target) | 0.6 mm | no episode end |
| held-claw ram, 15 cm (claws hard) | 0 (the drive follows the ramp at 85 %) | 78.7 mm for 2 ticks (the claw into the other gripper's finger) | `simulator_instability` (not forced) |
| tug-of-war: both arms pull their interlocked pieces 6 cm apart (claws hard) | 5 (intermittent) | 9.4 mm (150 kN contact spikes) | review events; with the bound at 4 mm: `forced_breakdown` (left forearm roll at 100 %, 150 kN) |
| the same, 15 cm | 2 | 4.8 mm (62 kN for 3 ticks: the pieces pass through each other) | **success**, held for review (end to end below) |
| tug-of-war 6 / 15 cm (claws easy) | 0-2 (the physical grips slip) | 0.4-0.7 mm | no episode end |
| blanket easy privileged success Pxz524p (5361 rows); blanket easy standard uYyNBH5 (2087 rows) | 0: the robot touched nothing rigid (the cloth is PBD) | - | Pxz524p succeeds at step 4060 on the local v15 95 % instance (uYyNBH5, a 90 % success, does not reach 95 %); no forcing |
| blanket medium privileged success ccaPmiU (1817 rows) | 0 (the grippers pressed the table with up to 66 N, drives at 73 % at most) | - | success at step 1636 on the local v15 95 % instance, clean |
| knot easy privileged success WWfaVD9 (365 rows) | 0 (the right gripper on the table: 2.8 N at most, drives below 92 %) | - (IPC) | success at row 365, clean |

The claws easy standard success forces longer and harder than every scripted ram: no threshold of drive fraction,
contact force or window separates them (a 0.25 s window would also catch the reference oracle, 131 ticks), so forcing is
evidence only (above). The exploit R1 was made for (bodies forced through each other: the 15 cm tug) takes 3 ticks at
4.8 mm: R1 failed it at once, as it failed QKSrtdL's passive impact; 3 ticks of forcing make no forcing event and the
breakdown bound is 10 mm, so the deep contact is what holds that success for review.

End to end on lab with the committed task dirs (`v15/root_v15c`): the 15 cm tug's trajectory (74 rows, a success)
through the privileged verifier: both replays succeed with the same state hash, `success` 0, `success_pending_review` 1,
`review_events` 1, `review_max_depth_mm` 4.8, verdict.json `evidence.review` (control step 2, physics tick 13, 3 ticks,
claw 1 / claw 0, 22980 N) and `review_frames/` around it. The standard pipeline in one sim container (the sidecar
service, QKSrtdL's 50 rows sent back through the real client plus a 2 s watch, the collect hook, the grader): the live
episode runs past row 49 (`meta["safety"]["review"]`: one deep event, 4.8 mm), the released claws fall at step 75 ("A
task body fell below the table"), the replay matches the live state, `success` 0, `success_pending_review` 0,
`review_events` 1, `review.json` written. A Harbor nop of interlocked_claws easy standard (main + sidecar + the separate
verifier): `finalized` 1, `success` 0, `success_pending_review` 0, no infrastructure or grader error, video rendered.
CPU determinism: the claws hard / easy privileged successes and
the claws easy oracle end with v14's verifier state hashes, and QKSrtdL / diFXNtw (rows + hold) with the hashes of the
v14 tooling's own replays with R1's verdicts off: the policy reads, it never changes the physics.

## One policy across both sides (merged-v16)
Jianwen's merged-v15 candidate and ba01d029c change rules too: knot_untying's release (terminal v5) and the environment
profile, whose rope_threading part he calls `contact_relaxed_v16`. Checked against the layers above, rule by rule, so that
nothing is relaxed twice and no rule contradicts another (2026-10-04):

| rule | layer, owner | live episode | grading replay (rows / hold) |
|---|---|---|---|
| materials, timing, grasp assistance, contact sets (rope: fingers only), geometry | 0, Jianwen (profile, task code) | frozen in the instance | identical |
| torque caps, table guard, standard joint-speed limit and IK-jump refusal | 1, tooling | enforced | the recorded rows (as executed) |
| success thresholds and windows, release checks (knot v5), aperture allowance (rope) | 2, Jianwen | strict | strict on the rows; in the hold only `REPLAY_TOLERANCES` (blanket coverage and cloth speed, knot rope speed) |
| failure predicates; R2 (crushed volume, stretched attachment, 0.25 s) | 2, Jianwen; R2 tooling | end the episode | unchanged |
| breakdowns (non-finite, cloth > 20 m/s, invalid IPC state, rigid contact > 10 mm) | 3, tooling | infrastructure error unless forced | the same |
| forcing; deep rigid task contacts | 4, tooling | evidence; a deep one holds a success for review | the same |

| quantity | Jianwen | ours | merged-v16 |
|---|---|---|---|
| knot release clearance | v5: 1 mm from parts that can move; fixed bases may touch (v4: 5 mm from every part, bounding boxes) | the hold leaves it unchanged | v5, live and replay; one relaxation (his, geometric), never loosened in the hold |
| knot rope inside a robot part | v5: any interior overlap withholds success | penetration depth is evidence (rigid task contacts only; the rope is FEM) | consistent: a certification of the release, not a failure. All robot links collide with the knot rope in IPC, so an overlap means an IPC failure (layer 3) or a mismatch between IPC's collision geometry and the solids the check uses |
| knot rope speed | 1 mm/s | hold 1.25 mm/s | one relaxation (ours, hold) |
| rope still speed | 10 mm/s (was 1) | no slack (hold only) | one relaxation (his, live) |
| rope rim | 1 mm compression allowance, round-ring passage test | none | his; the texts give the passage radii and the allowance |
| rope and robot | fingers only (the IPC contact set, for rope and rings) | not measured (FEM) | his environment model; the texts now say so |
| blanket coverage | task default 0.90 | live 0.95 (the user), hold 0.92 | 0.95 in his profile (re-keyed states), hold 0.92 |
| keyhole standard oracle | his privileged references move a joint up to 0.10 rad per control step; his bridge refuses rows the service slows | the 0.04 rad per step limit exists only in the standard service | open (below) |

Results: a success held for review (`success_pending_review` 1) is `pending_review` in Jianwen's result pipeline
(`scripts/collect_batch_results.py`, the difficulty runner, the HF export, helper assignments): complete, neither solved nor
unsolved, out of the success rate until a reviewer decides; `scripts/write_task_results.py` says so on the result page.

For Jianwen to confirm:
1. knot v5's overlap check: IPC and the release check see the same robot geometry (else a rope resting on a base could read
   as an overlap and withhold success), and `unresolved` geometry is rare (it also withholds success).
2. The rope profile's contact set: only the fingers touch the rope and the rings; now stated in the texts.
3. blanket coverage 0.95 in his profile, with the packaged states re-keyed (arrays unchanged) rather than prepared again.
4. The blanket identity fix (lab BUG 2) in `topogym/tasks/blanket_flatten/common.py`.
5. Release labels: v16 = merged-v16, image 0.2.14-dev; his v15 frozen; the name `contact_relaxed_v16` stays his profile's.
6. `pending_review` as a result status of his pipeline (above).
7. Open: the standard joint-speed limit (0.04 rad per control step) against privileged references that move faster
   (keyhole). Options: references that respect the limit, a bridge that accepts slowed rows, or the same limit in both
   modes.

## Grading GPU
- Privileged: the verifier is its own container; on a host with a spare GPU (lab) the host's copy of
  `tests/docker-compose.yaml` pins it to that grading GPU, so it never runs on the agents' GPUs.
- Standard: the replay runs in the sidecar on its own GPU after the live service has exited: it takes the place of the
  live simulator, adding no load to that GPU. Nyx renders only in a container that sees exactly one GPU (a sidecar given a
  second GPU segfaults in `cuImportExternalMemory`, tested 2026-10-01), so moving this replay to a grading GPU needs a
  replay container of its own (a possible later step).

## Standard mode
`eai-standard/2.3` with crash recovery (`docs/rcb/STANDARD_MODE_2_2.md` §13,
`STANDARD_MODE_2_3.md`), resume class `approx` (GPU nondeterminism), `RCB_STARTUP_TIMEOUT_S` = 1800. The shared layer is
`scripts/eai_standard/` (from robot_coding_bench, with the 2.3 changes as `local_adaptations` in `ci_checks/rcb_vendor.json`);
the TopoGym adapter is `environment/sim/server.py`. Genesis' CUDA context belongs to the
thread that built the scene, so every simulator call (and each call's checkpoint: state hash, proprio row) runs on the
main thread's job queue.

## Instruction texts
The per-step wall times quoted in the texts come from each instance's `describe.json`. Since v14: the unloaded figure is
the v14 describe's own measurement (lab, 3 hold steps, 2026-10-03), the shared figure twice that (the v12 sweep's
standard trials ran at 1.0-2.2x the unloaded figure under its load). Until v12 the texts still quoted the first builds'
times (knot_untying: 37.7 s unloaded / 67 s shared per control step, against about 2 s since v11-v12). The
client-timeout advice derives the chunk sizes from the shared figure with a 2× margin.

## Oracle and review
No reference solutions for the tier instances: `oracle = "none"` with `oracle_evidence`, no `solution/`; human review per
family (PROTOCOL §2.7). Model positives so far: interlocked_claws easy in both modes (sweep topogym-lunamax-assist-1001,
the previous version of these dirs).

## Hosts
- Base image `ghcr.io/luigivamper/rcb-topogym:<images/topogym/VERSION>-cu128` (v16: 0.2.14-dev; the published v14 dirs:
  0.2.12) (`images/topogym/VERSION` + the CUDA profile of `scripts/cuda_profiles.py`; outside the `eai-<sim>` registry: a
  legacy warning). Neither is on GHCR: the candidate pipeline's `build_image.sh` builds the active one; by hand, build on
  the host with `TOPOGYM_CUDA_FLAVOR=cu128 scripts/build_images.sh topogym` (a
  large host may add `--build-arg UIPC_BUILD_JOBS=16`; the default 3 took about 1.5 h on lab), then warm its cache on that
  host's GPU: `images/topogym/warm_cache.sh <built tag> <published tag> <gpu> tasks` (one Session per family; without it
  every container compiles the kernels again).
- blanket_flatten's packaged PBD states restore only on the GPU profile they were prepared on (RTX PRO 6000, sm_120):
  run blanket on lab.
- The IPC families are slow (50-90 s per control step in motion, 15 s holds, one sim per GPU): a precision / speed study
  of the simulator settings is under way (2026-10-02).

## Legacy: the original frozen instances
Jianwen's first frozen instances `tasks/topogym-<family>-i00[-limited]` (seed 0) keep their pre-v1.0 names, layer and
READMEs; the tier dirs supersede them and our sweeps do not run them. CI checks their tooling against its frozen inventory
(`ci_checks/topogym_tooling_versions.json`) and exempts them from the v1.0 naming and README layout
(`ci_checks/check-task-fields.sh`, `check-task-structure.sh`, both adapted). Their agent and verifier containers use the shared client image (a v1.0 MUST for every 2.2 task).
