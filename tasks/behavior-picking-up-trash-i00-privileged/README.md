# behavior-picking-up-trash-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-picking-up-trash-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `picking_up_trash` / seed 301 |
| Oracle | `partial` — Reference solution solution/oracle_picking_up_trash.py on the frozen task-level primitives solution/rcb_behavior_ref.py. Recorded Harbor oracle runs (laptop, pre-v1.0 uncommitted trees): 2026-09-24 behavior-picking-up-trash-i00__FKLU2nS (job behavior-picking-up-trash-i00-oracle-0924-230430) scored 1 (5115 control steps, deterministic 1, instance_exact 1); the run before it, behavior-picking-up-trash-i00__MjRvy7Y (an older placement routine), scored 0; the 2026-10-01 review counts 1 success in 3 runs of that version. Model trial behavior-picking-up-trash-i00__JRcB9fb (behavior-lunaxh-0925-2057, ws) scored 1. The tooling and verifier files changed since; not re-run on this version (static validation only). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-behavior:0.1.1` |

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
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes.

Oracle `partial`: the reference solution scored 1 on earlier versions of this task (`task.toml` `oracle_evidence`) and was not re-run on this one; the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it.

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_lower`), state hash in `environment/instance.json` |
| Image | `ghcr.io/embodied-agent-interface-v2-internal/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
