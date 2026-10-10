# behavior-putting-shoes-on-rack-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-putting-shoes-on-rack-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `putting_shoes_on_rack` / seed 301 |
| Oracle | `partial` — Reference solution solution/oracle_putting_shoes_on_rack.py on the frozen task-level primitives solution/rcb_behavior_ref.py. Recorded Harbor oracle run (laptop, a pre-v1.0 uncommitted tree): 2026-09-24 behavior-putting-shoes-on-rack-i__LkouR9y (job behavior-putting-shoes-on-rack-i00-oracle-0924-234514) scored 1 (6283 control steps, deterministic 1, instance_exact 1), 1 of 1. Model trial behavior-putting-shoes-on-rack-i__KozJnde (behavior-lunaxh-0925-2057, ws) scored 1. The tooling and verifier files changed since; not re-run on this version (static validation only). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Put both pairs of shoes on the hall tree in the corridor.

## Difficulty
The second BEHAVIOR task next to `behavior-picking-up-trash-i00-privileged`: placement with a **pairwise spatial relation** instead of containment. BDDL goal: every gym shoe and sandal touches the hall tree and not the floor, the two gym shoes are `nextto` each other and so are the two sandals. OmniGibson's `nextto` = the gap between the two AABBs is at most one sixth of the mean of their summed extents (6.3 cm for these gym shoes, 5.3 cm for the sandals) and nothing lies between them along a horizontal axis. OmniGibson's own `place_on_top` samples a random spot, so it cannot satisfy `nextto`: the agent has to choose where each shoe lands (the tooling's primitives are thin: joint, base, IK and gripper moves). The four shoes lie on the corridor floor 3-5 m from the hall tree, an open white shoe cabinet (flat top at 0.553 m, two inner shelves) under a back panel with two floating shelves, set in an alcove.

## Reference solution
`solution/oracle_putting_shoes_on_rack.py` (the challenge ships teleop demos, not scripts; written for this instance). It runs on the task-level primitives of the tooling it was written with, frozen in `solution/rcb_behavior_ref.py` (the agent's tooling has only thin ones); `solution/solve.sh` records the trajectory with that copy.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

Oracle `partial`: the reference solution scored 1 on earlier versions of this task (`task.toml` `oracle_evidence`) and was not re-run on this one; the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it.

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_lower`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
| Verifier time | each replay min(4 h, max(3600 s, 1200 s + steps / 2)); `[verifier] timeout_sec` 30600 s (two capped replays + 30 min) |

### Change Log
- 2026-10-08: verifier time limits only. `tests/grade.py` gives each of the two fresh-process replays min(4 h, max(3600 s, 1200 s + steps / 2)) instead of a flat 3600 s, and `[verifier] timeout_sec` is 30600 s (was 5400 s), measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s, so long trajectories hit the old limit as a grader error. The scene, frozen instance and pass rule are unchanged, so the task keeps its name; a trial graded before this date with `grader_error` = 1 can be regraded.
- 2026-10-09: a fall ends the episode as a failure (owner decision): once OmniGibson's own Falling rule (the base tilted more than 41.4° from upright, or more than 3 cm below the floor) has held for 10 s of simulated time, the tooling Session's episode ends (`status()['fallen']`; `s.reset()` starts again), and the verifier's replays end at the same control step (`reward.json` `fallen`). The scene, frozen instance and BDDL goal are unchanged, so the task keeps its name; a trajectory in which the robot falls over and stays down for 10 s scores 0, and results recorded before this change are reported separately.
