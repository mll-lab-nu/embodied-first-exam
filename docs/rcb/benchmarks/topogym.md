# TopoGym tier tasks (protocol v1.0)

39 frozen instances (13 families × easy / medium / hard) in both modes: 78 task dirs
`tasks/topogym-<family>-<tier>-i00-{privileged,standard}`. `scripts/topogym_mk_task.py` (privileged) and
`scripts/topogym_mk_limited.py` (its standard twin) render them from `harbor_templates/topogym/` and the frozen instance;
their last step is `scripts/task_conventions.py`'s `normalize` (protocol v1.0 fields, README layout). Re-rendering needs no
GPU when the instance's `describe.json` is kept (`--reuse-describe`).

## Budget
Agent wall clock **21600 s** (6 h) for every family (decision of 2026-10-01; before: 6 h, knot_untying 10 h). This is above
protocol v1.0's cap of 14400 s ([agent].timeout_sec ≤ 4 h): a TopoGym exception, so its results form their own budget
group (PROTOCOL D8) and the tasks would need a shorter budget on main. The privileged verifier may take `2 × budget + 1800`
s, the standard collect hook `3600 + budget + 1800` s. The token budget of the 2026-10 sweep is 120M input / 10M output per
trial (the protocol's default is 100M / 10M, D10), applied after the run.

## Tooling
Thin wrappers of the low-level action only (IK and joint moves, gripper, hold) plus state, recording, replay and
rendering; no task-level skills. One source per variant, byte-identical in every copy (`ci_checks/check-tooling-identity.sh`):

| variant | families | difference from `common/rcb_topogym.py` |
|---|---|---|
| `common/rcb_topogym.py` | the rigid and PBD families | — |
| `common/rcb_topogym_interlocked.py` | interlocked_claws | the contact-weld pre-weld survives the first step (the gripper width table drops the closed end) |
| `common/rcb_topogym_ipc.py` | knot_untying, rope_threading, orbits, slotted_post_ring | Genesis 1.2.1's per-substep FEM checkpoint store is bounded to one checkpoint (it leaked ~120 MiB of GPU memory per control step); knot's planar-clearance predicate vectorized (same results) |

The FEM fix was checked on knot hard (laptop, 14 control steps): free GPU memory −0.9 MiB per step (unpatched −121.7),
the rope's vertex positions within the GPU's run-to-run noise (max 1.2e-7 m vs 9.4e-8 m between two unpatched runs), the
step time unchanged.

## Grading: two passes
- **Privileged.** The verifier (separate sandbox, GPU, no network) replays `/app/output/trajectory.npz` from
  `tests/instance.json` twice in a fresh process and renders `replay.mp4` **during the second replay**. Success: both
  replays meet the task's predicate. The physics runs on the GPU and is not bit-deterministic: `deterministic` and
  `instance_ok` are reported, not required.
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
`eai-standard/2.2` with crash recovery (`docs/rcb/STANDARD_MODE_2_2.md` §13), resume class `approx` (GPU nondeterminism),
`RCB_STARTUP_TIMEOUT_S` = 1800. The shared layer is `scripts/eai_standard/` (vendored from robot_coding_bench,
`ci_checks/rcb_vendor.json`); the TopoGym adapter is `environment/sim/server.py`. Genesis' CUDA context belongs to the
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
- Base image `ghcr.io/luigivamper/rcb-topogym:0.2.3-cu128` (outside the `eai-<sim>` registry: a legacy warning).
- blanket_flatten's archived PBD states restore only on the GPU model they were prepared on (RTX PRO 6000): run blanket
  on lab.

## Legacy: the original frozen instances
Jianwen's first frozen instances `tasks/topogym-<family>-i00[-limited]` (seed 0) keep their pre-v1.0 names, layer and
READMEs; the tier dirs supersede them and our sweeps do not run them. CI checks them against their 76583213 template and
exempts them from the v1.0 naming and README layout (`ci_checks/check-task-fields.sh`, `check-task-structure.sh`, both
adapted). Their agent and verifier containers use the shared client image (a v1.0 MUST for every 2.2 task).
