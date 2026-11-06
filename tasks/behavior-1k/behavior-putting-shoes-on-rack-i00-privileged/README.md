# behavior-putting-shoes-on-rack-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-putting-shoes-on-rack-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `putting_shoes_on_rack` / seed 301 |
| Oracle | `partial` — Reference solution solution/oracle_putting_shoes_on_rack.py on the frozen task-level primitives solution/rcb_behavior_ref.py. Recorded Harbor oracle run (laptop, a pre-v1.0 uncommitted tree): 2026-09-24 behavior-putting-shoes-on-rack-i__LkouR9y (job behavior-putting-shoes-on-rack-i00-oracle-0924-234514) scored 1 (6283 control steps, deterministic 1, instance_exact 1), 1 of 1. Model trial behavior-putting-shoes-on-rack-i__KozJnde (behavior-lunaxh-0925-2057) scored 1. The tooling and verifier files changed since; not re-run on this version (static validation only). Measured 2026-10-10 on main 332bf8080 (an 8-vCPU cloud L40S host, Harbor oracle agent, once): the reference solution's own run ended without success (q_score 0.8, 8921 control steps against the recorded 6283); the frozen scene rebuilt there within tolerance but not bit-exactly (instance_exact 0), so the solution's online planning took another path: this reference solution does not succeed on that host class. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2` |

## Task
Put both pairs of shoes on the hall tree in the corridor.

## Difficulty
The second BEHAVIOR task next to `behavior-picking-up-trash-i00-privileged`: placement with a **pairwise spatial relation** instead of containment. BDDL goal: every gym shoe and sandal touches the hall tree and not the floor, the two gym shoes are `nextto` each other and so are the two sandals. OmniGibson's `nextto` = the gap between the two AABBs is at most one sixth of the mean of their summed extents (6.3 cm for these gym shoes, 5.3 cm for the sandals) and nothing lies between them along a horizontal axis. OmniGibson's own `place_on_top` samples a random spot, so it cannot satisfy `nextto`: the agent has to choose where each shoe lands (the tooling's primitives are thin: joint, base, IK and gripper moves). The four shoes lie on the corridor floor 3-5 m from the hall tree, an open white shoe cabinet (flat top at 0.553 m, two inner shelves) under a back panel with two floating shelves, set in an alcove.

## Reference solution
`solution/oracle_putting_shoes_on_rack.py` (the challenge ships teleop demos, not scripts; written for this instance). It runs on the task-level primitives of the tooling it was written with, frozen in `solution/rcb_behavior_ref.py` (the agent's tooling has only thin ones); `solution/solve.sh` records the trajectory with that copy.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process; pass iff the BDDL goal
holds after the replay and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence a fresh process. A file the
grader cannot read or with the wrong shape is `bad_trajectory`; a replay that dies or runs out of time, and a frozen
instance that does not rebuild in the verifier (`instance_ok` 0), are `grader_error` + `infra_error` (no verdict on the agent).

Oracle `partial`: the reference solution scored 1 on earlier versions of this task (`task.toml` `oracle_evidence`) and was not re-run on this one; the family is reviewed by a maintainer (PROTOCOL §4) in the pull request that adds it.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 8192 | 22 GiB | 32 GiB |
| verifier | no cap | no cap | no cap | 22 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_lower`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2` = `stanfordvl/behavior:3.9.2` + ffmpeg (`images/behavior/`): the task builds it from public sources, or reuses our prebuilt copy when you can pull it |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | the agent's time (the `Agent time budget` row; the number is this task's `[agent] timeout_sec`): every Python process pays ~3 min of Isaac Sim + scene load out of it; ~7-11 control steps/s (tasks/behavior-1k/README.md) |
| Verifier time | at most 40,000 rows accepted; each graded replay min(28000 s, max(3600 s, 1200 s + steps / 1.5)), and the video replay after the verdict the same; `[verifier] timeout_sec` 85800 s (three capped replays + 30 min) |
