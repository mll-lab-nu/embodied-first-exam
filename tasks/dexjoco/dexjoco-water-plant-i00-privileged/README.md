# dexjoco-water-plant-i00-privileged

| | |
|---|---|
| Benchmark | DexJoCo |
| Mode | privileged |
| Twin | `dexjoco-water-plant-i00-standard` |
| Simulator / robot | `dexjoco` / `franka-allegro` |
| Family / instance | `water_plant` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2` |

## Task
DexJoCo `water_plant` (a Franka Panda arm with a 16-DoF Allegro hand): Pick up the spray bottle, point its nozzle at the potted plant and squeeze the trigger. Success: the trigger is held pulled (trigger joint > 0.34 rad; it counts as released again below 0.25 rad) while the nozzle reference point is within 0.20 m of the plant horizontally and within +-0.20 m of the plant's height AND the spray points at the plant, all three for 30 consecutive control steps (0.6 s). The spray leaves the spray head horizontally forward: perpendicular to the bottle's long axis, on the side the trigger faces (the bottle's local +z; its long axis, bottom to head, is local +y). It points at the plant when that direction is within 45 degrees of the line from the nozzle to the plant, e.g. with the bottle held upright and its trigger side facing the plant. Pulling the trigger while the nozzle is outside the zone ends the episode as a failure.
Privileged mode: the agent works in the simulator's container with live object poses, unlimited resets and thin motion
primitives, and hands in one trajectory replayed open-loop from the frozen instance.

## Difficulty
First-pass rating: medium. Dexterous manipulation with a 16-DoF hand on a 7-DoF arm (23 action values per control step);
the primitives only move tcp and hand-joint targets, so grasping, pressing and every other skill is the agent's. The
reference (the human teleoperator's demonstration) takes 307 control steps (6.1 s at 50 Hz).

## Reference solution
`solution/oracle_trajectory.npz` = the human demonstration's own actions, rounded to float32 (the standard client's
precision; the rounded rows still succeed) and replayed from the frozen instance until the episode ends in success
(307 rows). The demonstration is public (DexJoCo-Datasets-Raw on Hugging Face), so agent egress is
limited to the model APIs.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz`, twice in a fresh process in the verifier's own
sandbox (no network); pass iff both episodes end in success and their final-state hashes agree (`tests/grade.py`); plus
`/logs/verifier/replay.mp4`, rendered after the verdict is written. A rebuilt instance that does not match its recorded
hash (the image no longer rebuilds the scene) replays nothing and gives no verdict: `instance_mismatch`, `grader_error`
and `infra_error` = 1, not the agent's 0.
A file that is not a readable trajectory (not an npz, no `task` / `actions`, a wrong shape, NaN) or has more than
50,000 rows scores 0 as `bad_trajectory`: the cap is what two replays of the slowest family fit into the verifier's
3600 s. A verifier that runs fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to it) replays
nothing and gives no verdict: `too_few_cpus`, `grader_error` and `infra_error` = 1, not the agent's 0.
Oracle: success after 307 control steps.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim 1.9 GB, privileged container 2.1 GB, verifier 2.1 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU-only; CPUs: 4, visible to each container that runs the simulator (cpuset / affinity, not a quota): OpenBLAS runs no more threads than that and DexJoCo's result differs below 4 (tasks/dexjoco/README.md, Threads); with fewer there is no verdict (too_few_cpus, infra_error)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: the [environment] cap 8 GiB, which every past trial ran under (docker peak 2.1 GiB over 2 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `water_plant_demo_10_2026-02-05_19-50-27_886249` (DexJoCo-Datasets-Raw), restored with DexJoCo's own state restorer; instance sha `04f14553ced4b0ed` |
| Resources | 4 CPUs, 8 GB, no GPU; `OPENBLAS_NUM_THREADS=4` in the agent's container and the verifier's (the simulation's result depends on the thread count below 4: tasks/dexjoco/README.md). The 4 CPUs must be visible to the container (its cpuset / affinity; a `cpus:` quota does not matter): OpenBLAS runs no more threads than that |

### Tooling notes
DexJoCo's reset samples object poses from the global RNG and its state restorer edits the MuJoCo model (table height,
fixed bodies), so `instance.npz` stores the full physics state (`mjSTATE_INTEGRATION`), the mocap targets, the controls,
every numeric model array a task can change, and the env's Python-side task state. Its per-step camera rendering,
real-time sleep, episode cap and hanoi's wall-clock auto-reset are disabled in the tooling (`rcb_dexjoco.py`).

### Provenance
Generated from the frozen instance (`environment/instance.npz`), restored from DexJoCo's demonstration of the task.

### Change Log
- 2026-10-14 (review, B-M3 and B6-3): `environment/instance.npz` and `tests/instance.npz` no longer name
  the demonstration the scene was restored from: their `meta` entry had `source` (the dataset) and `demo` (the
  demonstration's id), and the reference solution is that demonstration's own actions, so the agent could read at
  `/app/instance.npz` where a solution was (PROTOCOL §2.7). Only `meta` changed: every array of the scene is the same
  (instance sha `04f14553ced4b0ed`), so the scene, the pass rule and the reference are unchanged and the task keeps its
  name. The tooling (`rcb_dexjoco.py`, both copies) refuses to save an instance whose `meta` says where its scene came
  from. `tests/grade.py`: a rebuilt instance that does not match its recorded hash is now no verdict
  (`instance_mismatch`, `grader_error`, `infra_error` = 1, nothing replayed); before, it was the agent's 0 with
  `infra_error` = 0 and `instance_ok` = 0. Past results: the demonstration itself was out of reach under the egress
  allowlist (Hugging Face is not on it); a past 0 with `instance_ok` = 0 was an infrastructure failure.
