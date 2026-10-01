# robowits-hold-cup-i00-privileged

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | privileged |
| Twin | `robowits-hold-cup-i00-standard` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `hold_cup` / seed 0 |
| Oracle | `none` — No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-hold-cup-i00-limited__BiMATyh (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robowits:0.1.1` |

## Task
Put the cup on the green target area on the slope without sliding down. One replayable trajectory from the frozen
instance (evaluation scene 0 of RoboWits task 9), with the privileged tooling (`rcb_robowits.py`: the scene's state,
resets, thin primitives, replay); the success criterion as graded is in `instruction.md`.

## Difficulty
Put a cup on a sloped target area without it sliding down. The cup and slope lack sufficient friction to remain
stationary. The robot must utilize the surface friction of the coaster to stabilize the cup. The coaster acts as a
high-friction interface. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).

## Reference solution
None: RoboWits ships no expert or planner, and none is written for this family (`oracle = "none"`). Evidence that it
is solvable: `oracle_evidence` in `task.toml` and the positive example cited in the review table of PR #3 (the trial
is published on the results site).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff
RoboWits' `_check_success` holds after every replay, the final-state hashes agree and the rebuilt frozen scene matches
the recorded one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. What the predicate checks, in words:
`instruction.md`, "Success criterion (as graded)". The trajectory is the per-control-step JOINT_ABS record (T, 16);
Genesis' CPU backend restores the frozen snapshot exactly, so in-process repeats and fresh processes agree bit for bit
on one CPU vendor (docs/benchmarks/robowits.md).

No oracle; human review in PR #3 (PROTOCOL §2.7): the positive example, the `nop` result and the predicate
summary are in the PR's review table.

## Details
| | |
|---|---|
| RoboWits task | `09-hold-cup-v0` (RoboWits @ 9cc30ae, Genesis 0.4.7: CPU physics backend, EGL rendering on the GPU) |
| Instance | entry 0 of RoboWits' `eval_dataset_50/09.json`; object poses and the expected state hash in `environment/instance.json` (the verifier's copy in `tests/`) |
| Robot | Marvin bimanual: 2 × 7-DoF arms with Pika parallel grippers; JOINT_ABS actions (T, 16) at 30 Hz |
| GPU | EGL camera rendering only (`environment/docker-compose.yaml`, `tests/docker-compose.yaml`) |
| BlenderKit models | not redistributable, so not in the image: mounted read-only from `$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`) |
