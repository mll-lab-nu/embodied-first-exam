# TopoGym tier tasks (protocol v1.0)

39 frozen instances (13 families × easy / medium / hard) in both modes: 78 task dirs
`tasks/topogym-<family>-<tier>-i00-{privileged,standard}`. `scripts/topogym_mk_task.py` (privileged) and
`scripts/topogym_mk_limited.py` (its standard twin) render them from `harbor_templates/topogym/` and the frozen instance;
their last step is `scripts/task_conventions.py`'s `normalize` (protocol v1.0 fields, README layout). Re-rendering needs no
GPU when the instance's `describe.json` is kept (`--reuse-describe`).

## Versions (2026-10-02)
| dirs | families | tooling | standard protocol | image |
|---|---|---|---|---|
| 48 | buzz_wire_3d, cast_coil, cast_keyhole, fiber_bundling, hedgehog_in_cage, horseshoe_ring, interlocked_claws, lock_picking | v5 | `eai-standard/2.3` | `rcb-topogym:0.2.7-cu128` |
| 30 | blanket_flatten, knot_untying, rope_threading, orbits, slotted_post_ring | v4 (frozen) | `eai-standard/2.2` | `rcb-topogym:0.2.5-cu128` |

- v5 / 2.3 = Jianwen's post-merge repairs B04–B13 (`docs/rcb/STANDARD_MODE_2_3.md`,
  `docs/debug_logs/run_trials_post_merge_repair_20261001_zh.md`): invalid submissions graded as such, scores persisted
  before the video, only executed actions recorded with their actual ticks, non-integer `dt` refused, instance mismatch
  never a success, operation ids and request deadlines (a retried request is not executed twice).
- `eai-standard/2.3` is a TopoGym-local extension of robot_coding_bench main's 2.2 (`ci_checks/rcb_vendor.json`
  `local_adaptations`), to be proposed for main.
- The five soft-body families stay on v4: v5 refuses a soft-body instance without complete node references (B08), so they
  move to v5 once their instances are made again with the v5 generator.
- 0.2.7 = Jianwen's 0.2.6 simulator changes + the batched rigid readback (Step time below).

## Budget
Agent wall clock **21600 s** (6 h) for every family (decision of 2026-10-01; before: 6 h, knot_untying 10 h). This is above
protocol v1.0's cap of 14400 s ([agent].timeout_sec ≤ 4 h): a TopoGym exception, so its results form their own budget
group (PROTOCOL D8) and the tasks would need a shorter budget on main. The privileged verifier may take `2 × budget + 1800`
s, the standard collect hook `3600 + budget + 1800` s. The token budget of the 2026-10 sweep is 120M input / 10M output per
trial (the protocol's default is 100M / 10M, D10), applied after the run.

## Tooling
Thin wrappers of the low-level action only (IK and joint moves, gripper, hold) plus state, recording, replay and
rendering; no task-level skills. One source, tooling v4 (`[metadata].tooling_version = "4"`):
`harbor_templates/topogym/common/rcb_topogym.py`, byte-identical in every copy (`ci_checks/check-topogym-tooling.py`, run
by `check-tooling-identity.sh`). v4 (Jianwen, 6a7c755b) folds the two family variants of the previous render into it:
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

## Grading: two passes
- **Privileged.** The verifier (separate sandbox, GPU, no network) replays `/app/output/trajectory.npz` from
  `tests/instance.json` twice in a fresh process and renders `replay.mp4` **during the second replay**. Success: both
  replays meet the task's predicate. The physics runs on the GPU and is not bit-deterministic: `deterministic` is
  reported, not required; v5 requires the rebuilt frozen scene to match (`instance_ok`), v4 only reports it.
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
`eai-standard/2.3` (v5 dirs; the v4 dirs keep 2.2) with crash recovery (`docs/rcb/STANDARD_MODE_2_2.md` §13,
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
- Base images `ghcr.io/luigivamper/rcb-topogym:0.2.7-cu128` (v5 dirs) and `:0.2.5-cu128` (v4 dirs)
  (`images/topogym/VERSION` + the CUDA profile of `scripts/cuda_profiles.py`; outside the `eai-<sim>` registry: a legacy
  warning). Neither is on GHCR: build on the host with `TOPOGYM_CUDA_FLAVOR=cu128 scripts/build_images.sh topogym` (a
  large host may add `--build-arg UIPC_BUILD_JOBS=16`; the default 3 took about 1.5 h on lab).
- blanket_flatten's archived PBD states restore only on the GPU model they were prepared on (RTX PRO 6000): run blanket
  on lab.

## Legacy: the original frozen instances
Jianwen's first frozen instances `tasks/topogym-<family>-i00[-limited]` (seed 0) keep their pre-v1.0 names, layer and
READMEs; the tier dirs supersede them and our sweeps do not run them. CI checks their tooling against its frozen inventory
(`ci_checks/topogym_tooling_versions.json`) and exempts them from the v1.0 naming and README layout
(`ci_checks/check-task-fields.sh`, `check-task-structure.sh`, both adapted). Their agent and verifier containers use the shared client image (a v1.0 MUST for every 2.2 task).
