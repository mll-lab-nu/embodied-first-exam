# TopoGym tier tasks (protocol v1.0)

39 frozen instances (13 families × easy / medium / hard) in both modes: 78 task dirs
`tasks/topogym-<family>-<tier>-i00-{privileged,standard}`. `scripts/topogym_mk_task.py` (privileged) and
`scripts/topogym_mk_limited.py` (its standard twin) render them from `harbor_templates/topogym/` and the frozen instance;
their last step is `scripts/task_conventions.py`'s `normalize` (protocol v1.0 fields, README layout). Re-rendering needs no
GPU when the instance's `describe.json` is kept (`--reuse-describe`).

## Versions (2026-10-02)
All 78 dirs: tooling v9, `eai-standard/2.3`, `rcb-topogym:0.2.10-cu128`.
- New packages use tooling v10: remote v9 performance settings plus the local A01 ZIP/NPZ error classification repair.
  Existing v9 packages keep their bytes and their 0.2.10 image references; v10 is checked against the current templates
  and image version. The local `Env.sensor_factory` extension and A03 evidence collection/export remain in source.
  Published images do not automatically acquire local development extensions.
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
Agent wall clock **21600 s** (6 h) for every family (decision of 2026-10-01; before: 6 h, knot_untying 10 h). This is above
protocol v1.0's cap of 14400 s ([agent].timeout_sec ≤ 4 h): a TopoGym exception, so its results form their own budget
group (PROTOCOL D8) and the tasks would need a shorter budget on main. The privileged verifier may take `2 × budget + 1800`
s, the standard collect hook `3600 + budget + 1800` s. The token budget of the 2026-10 sweep is 120M input / 10M output per
trial (the protocol's default is 100M / 10M, D10), applied after the run.

## Tooling
Thin wrappers of the low-level action only (IK and joint moves, gripper, hold) plus state, recording, replay and
rendering; no task-level skills. New packages use tooling v10 (`[metadata].tooling_version = "10"`): v9 performance
settings plus the local A01 input-classification repair. The checked-in tier packages remain frozen v9:
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

## Grading: two passes
- **Privileged.** The verifier (separate sandbox, GPU, no network) replays `/app/output/trajectory.npz` from
  `tests/instance.json` twice in a fresh process and renders `replay.mp4` **during the second replay**. Success: both
  replays meet the task's predicate. The physics runs on the GPU and is not bit-deterministic: `deterministic` is
  reported, not required; the rebuilt frozen scene must match (`instance_ok`, v5).
- **Standard.** Pass 1 is the live episode in the `sim` sidecar. When it ends the service writes `trajectory.npz` and
  `episode.json` (live result, final-state hash, `live_rows`: the rows the live episode executed). The collect hook
  `environment/sim/finalize.sh` sends SIGUSR1, waits until the service has exited (its GPU memory is free), then replays
  the live rows **once** in a fresh process (`environment/sim/replay.py`), rendering `replay.mp4` during that replay, and
  writes `final.json`. The verifier (shared client image, no network) grades `final.json`: success = live ∧ replay; a
  replay without a result is a `grader_error`, not the agent's 0.

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
The per-step wall times quoted in the texts come from each instance's `describe.json`, measured on lab while it was
loaded (pessimistic); the client-timeout advice derives the chunk sizes from them with a 2× margin.

## Oracle and review
No reference solutions for the tier instances: `oracle = "none"` with `oracle_evidence`, no `solution/`; human review per
family (PROTOCOL §2.7). Model positives so far: interlocked_claws easy in both modes (sweep topogym-lunamax-assist-1001,
the previous version of these dirs).

## Hosts
- Base image `ghcr.io/luigivamper/rcb-topogym:0.2.10-cu128`
  (`images/topogym/VERSION` + the CUDA profile of `scripts/cuda_profiles.py`; outside the `eai-<sim>` registry: a legacy
  warning). Neither is on GHCR: build on the host with `TOPOGYM_CUDA_FLAVOR=cu128 scripts/build_images.sh topogym` (a
  large host may add `--build-arg UIPC_BUILD_JOBS=16`; the default 3 took about 1.5 h on lab).
- blanket_flatten's packaged PBD states restore only on the GPU profile they were prepared on (RTX PRO 6000, sm_120):
  run blanket on lab.
- The IPC families are slow (50-90 s per control step in motion, 15 s holds, one sim per GPU): a precision / speed study
  of the simulator settings is under way (2026-10-02).

## Legacy: the original frozen instances
Jianwen's first frozen instances `tasks/topogym-<family>-i00[-limited]` (seed 0) keep their pre-v1.0 names, layer and
READMEs; the tier dirs supersede them and our sweeps do not run them. CI checks their tooling against its frozen inventory
(`ci_checks/topogym_tooling_versions.json`) and exempts them from the v1.0 naming and README layout
(`ci_checks/check-task-fields.sh`, `check-task-structure.sh`, both adapted). Their agent and verifier containers use the shared client image (a v1.0 MUST for every 2.2 task).
