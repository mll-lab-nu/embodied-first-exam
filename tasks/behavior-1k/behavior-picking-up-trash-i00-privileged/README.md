# behavior-picking-up-trash-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-picking-up-trash-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `picking_up_trash` / seed 301 |
| Oracle | `partial` — Reference solution solution/oracle_picking_up_trash.py on the frozen task-level primitives solution/rcb_behavior_ref.py. Recorded Harbor oracle runs (laptop, pre-v1.0 uncommitted trees): 2026-09-24 behavior-picking-up-trash-i00__FKLU2nS (job behavior-picking-up-trash-i00-oracle-0924-230430) scored 1 (5115 control steps, deterministic 1, instance_exact 1); the run before it, behavior-picking-up-trash-i00__MjRvy7Y (an older placement routine), scored 0; the 2026-10-01 review counts 1 success in 3 runs of that version. Model trial behavior-picking-up-trash-i00__JRcB9fb (behavior-lunaxh-0925-2057) scored 1. The tooling and verifier files changed since; not re-run on this version (static validation only). Measured 2026-10-10 on main 332bf8080 (an 8-vCPU cloud L40S host, Harbor oracle agent, twice): the reference solution's own run put 2 of the 3 cans in (the third grasp closed on nothing; q_score 0.667, 4390 control steps), the verifier replayed it faithfully (deterministic 1) and scored 0; both runs were bit-identical. The frozen scene rebuilt there within tolerance but not bit-exactly (instance_exact 0), so the solution's online planning took another path than on the recording host: this reference solution does not succeed on that host class. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2` |

## Task
Put the three cans of soda from the living room inside the trash can in the kitchen (BDDL: every `can__of__soda.n.01`
`inside` `ashcan.n.01_1`).

## Difficulty
Long-horizon mobile manipulation: three floor-level soda cans in the living room must be carried to a trash can in the
kitchen (~2.5 m navigation legs between rooms). The tooling gives only thin primitives (joint moves, a straight-line base
drive, cuRobo IK moves, gripper commands): navigation, grasping and placing are the agent's to build. What that takes,
from building the reference solution: the traversability map does not contain movable furniture (a 0.41 m cabinet blocks
the route between the rooms), the robot is a floating-base articulation that gets shoved around by any contact, IK near
the can in hand treats it as an obstacle unless told otherwise, the open fingers hang ~9 cm below the end-effector frame
and hook the rim when backing away, and the trash can is narrow at the bottom (fillable radius ~6.5 cm for 7.5 cm wide
cans) while the `inside` predicate tests each can's centre against a fillable volume that ends at z = 0.239 m, 4 cm below
the rim: a third upright can stacked on two others sticks out of it.

## Reference solution
`solution/oracle_picking_up_trash.py`: nearest can first; grasp (navigate → top-down pregrasp → descend → assisted
grasp), lift 0.6 m to carry above furniture, place it inside the trash can lying down (the pile stays low), reusing the
base pose of the first successful delivery. It runs on the task-level primitives of the tooling it was written with,
frozen in `solution/rcb_behavior_ref.py` (navigation on a map with the furniture painted in, grasp, `place_inside`);
`solution/solve.sh` records the trajectory with that copy (5115 control steps).

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
