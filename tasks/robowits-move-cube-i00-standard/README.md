# robowits-move-cube-i00-standard

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robowits-move-cube-i00-privileged` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `move_cube` / seed 0 |
| Oracle | `none` — No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-move-cube-i00-limited__9Vd2dpc (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robowits:0.1.1` |

## Task
Move any of the three cubes to the left of the goal line. The same frozen instance as
`robowits-move-cube-i00-privileged`, as a robot service (`eai-standard/2.2`): the simulator runs in the `sim` sidecar,
which the agent cannot open; the agent gets one episode, no reset and no privileged state, only the client (calibrated
RGB-D cameras, proprioception, `joint_position` / `ee_pose` chunks, stateless kinematics). The sidecar records the
episode as the trajectory, replays it and renders the video; the success criterion as graded is in `instruction.md`.

## Difficulty
That of `robowits-move-cube-i00-privileged` (its Difficulty), without resets, privileged state or the tooling's
primitives: the agent perceives the scene through calibrated RGB-D cameras and its own proprioception, and every
action it sends is part of the one graded episode.

## Reference solution
None: RoboWits ships no expert or planner, and none is written for this family (`oracle = "none"`). Evidence that it
is solvable: `oracle_evidence` in `task.toml` and the positive example cited in the review table of PR #3 (the trial
is published on the results site).

## Verification
`success` = live success ∧ replay success ∧ deterministic (the in-process replay is bit-exact on Genesis' CPU
backend), computed inside the sidecar, and no infrastructure failure (`tests/grade.py` reads the sidecar's
`final.json`); `/logs/verifier/replay.mp4`. What is checked, in words: `instruction.md`, "Success criterion (as
graded)".

No oracle; human review in PR #3 (PROTOCOL §2.7), with its privileged twin: the positive example, the `nop` result and the predicate
summary are in the PR's review table.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2` (docs/STANDARD_MODE_2_2.md): `submit` chunks of `joint_position` (16, streamed at the 30 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; stateless `kinematics`; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service replays its journal and resumes the same episode (resume class `exact`, docs/STANDARD_MODE_2_2.md §13) |
| Agent and verifier image | `docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` with the shared pins (`environment/client-requirements.txt`) |
| Instance | the privileged twin's frozen instance (`environment/sim/instance.json`): entry 0 of RoboWits' `eval_dataset_50/28.json` |
| BlenderKit models | not redistributable, so not in the image: mounted read-only into the `sim` sidecar from `$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`) |
