# robowits-ball-into-bottle-i00-privileged

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | privileged |
| Twin | `robowits-ball-into-bottle-i00-standard` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `ball_into_bottle` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `none` — No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-ball-into-bottle-i00__aUXXC4E (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §4). Re-graded with the current grader (two AMD workstations; the earlier positives were graded on the Intel laptop, so a trajectory that fails the earlier grader on AMD too says nothing either way): the cited robowits-ball-into-bottle-i00__aUXXC4E fails the earlier grader on AMD as well (inconclusive). No positive confirmed under the current grader yet. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robowits-0.1.1` |

## Task
Transfer the ball from the blue container into the red bottle. One replayable trajectory from the frozen instance
(evaluation scene 0 of RoboWits task 12), with the privileged tooling (`rcb_robowits.py`: the scene's state, resets,
thin primitives, replay); the success criterion as graded is in `instruction.md`.

## Difficulty
Transfer a ball from a container into a bottle using a funnel. The funnel provides a wide capture entrance. Gravity
guides the ball through the spout into the bottle. The ball container is graspable and can be poured into the funnel
opening. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).

## Reference solution
None: RoboWits ships no expert or planner, and none is written for this family (`oracle = "none"`). Evidence that it
is solvable: `oracle_evidence` in `task.toml` and the positive example cited in the review table of PR #3 (the trial
is published on the results site).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, once; pass iff
RoboWits' `_check_success` holds after the replay and the rebuilt frozen scene matches
the recorded one (`tests/grade.py`; a scene that does not match is the host's failure, `infra_error = 1`, never the
agent's 0), plus `/logs/verifier/replay.mp4`. What the predicate checks, in words:
`instruction.md`, "Success criterion (as graded)". The trajectory is the per-control-step JOINT_ABS record (T, 16);
Genesis' CPU backend restores the frozen snapshot exactly, so in-process repeats and fresh processes agree bit for bit
on one CPU vendor (tasks/robowits/README.md).

No oracle; human review in PR #3 (PROTOCOL §4): the positive example, the `nop` result and the predicate
summary are in the PR's review table.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 13 GiB | 1024 | 5 GiB | 10 GiB |
| `blenderkit` | 1 | 4 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | 5 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| RoboWits task | `12-ball-into-bottle-v0` (RoboWits @ 9cc30ae, Genesis 0.4.7: CPU physics backend, EGL rendering on the GPU) |
| Instance | entry 0 of RoboWits' `eval_dataset_50/12.json`; object poses and the expected state hash in `environment/instance.json` (the verifier's copy in `tests/`) |
| Robot | Marvin bimanual: 2 × 7-DoF arms with Pika parallel grippers; JOINT_ABS actions (T, 16) at 30 Hz |
| GPU | EGL camera rendering only (`environment/docker-compose.yaml`, `tests/docker-compose.yaml`) |
| BlenderKit models | not redistributable, so not in the image: mounted read-only from `$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`) |
