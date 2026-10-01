# robowits-dominos-i00-privileged

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | privileged |
| Twin | `robowits-dominos-i00-standard` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `dominos` / seed 0 |
| Oracle | `partial` — Reference solution solution/oracle_dominos.py (written for this instance; RoboWits ships no expert). It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-dominos-i00-oracle-thin-0925-000706, trial robowits-dominos-i00__qL9Rvsb, 2026-09-25 (laptop, Intel; success=1, deterministic=1, instance_exact=1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 4f933a76ce2ce34b) and the oracle script (byte-identical to that run's /app/output/gen.py). Changed since then, so the label is partial: the grader tests/grade.py (dev/qineng 82d76c61 added the GPU-backend exception; this PR writes the verdict before the video) and the tooling rcb_robowits.py (dev/qineng 5aa848bd, bddfc520, adce3fef, 8f0ebd55, 82d76c61, 6c0b439e, fe5fb9e6, 1515ea4e). Not re-run on this version (static validation only, 2026-10-01). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robowits:0.1.1` |

## Task
Push the red block onto the green target area. One replayable trajectory from the frozen instance (evaluation scene 0
of RoboWits task 6), with the privileged tooling (`rcb_robowits.py`: the scene's state, resets, thin primitives,
replay); the success criterion as graded is in `instruction.md`.

## Difficulty
Physical reasoning rather than pick-and-place: the red block ends on the target only through a chain of collisions.
White block 3 has to be toppled along the chain direction (about 26 deg off the table's x axis in this scene) hard
enough to carry through blocks 2 and 1, and gently enough that the red block falls onto the 6 x 10 cm patch instead of
past it. Nothing can be undone within one attempt, but the agent may reset and rehearse as often as it likes before
committing a trajectory.

## Reference solution
`solution/oracle_dominos.py` (RoboWits ships no expert; written for this instance): it pushes white block 3 near its
top along the chain direction with the closed right gripper, then retreats and lets the chain fall.
`solution/solve.sh` records it into a trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff
RoboWits' `_check_success` holds after every replay, the final-state hashes agree and the rebuilt frozen scene matches
the recorded one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. What the predicate checks, in words:
`instruction.md`, "Success criterion (as graded)". The trajectory is the per-control-step JOINT_ABS record (T, 16);
Genesis' CPU backend restores the frozen snapshot exactly, so in-process repeats and fresh processes agree bit for bit
on one CPU vendor (docs/benchmarks/robowits.md).

Oracle partial: the reference solution scored 1 on an earlier version of this task and was not re-run on this one
(`oracle_evidence` in `task.toml`); human review in PR #3 (PROTOCOL §2.7).

## Details
| | |
|---|---|
| RoboWits task | `06-dominos-v0` (RoboWits @ 9cc30ae, Genesis 0.4.7: CPU physics backend, EGL rendering on the GPU) |
| Instance | entry 0 of RoboWits' `eval_dataset_50/06.json`; object poses and the expected state hash in `environment/instance.json` (the verifier's copy in `tests/`) |
| Robot | Marvin bimanual: 2 × 7-DoF arms with Pika parallel grippers; JOINT_ABS actions (T, 16) at 30 Hz |
| GPU | EGL camera rendering only (`environment/docker-compose.yaml`, `tests/docker-compose.yaml`) |
