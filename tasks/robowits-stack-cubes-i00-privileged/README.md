# robowits-stack-cubes-i00-privileged

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | privileged |
| Twin | `robowits-stack-cubes-i00-standard` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `stack_cubes` / seed 0 |
| Oracle | `partial` — Reference solution solution/oracle_stack_cubes.py with its skills in solution/ref_primitives.py (written for this instance; RoboWits ships no expert). It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-stack-cubes-i00-oracle-thin-0925-000706, trial robowits-stack-cubes-i00__2rVdsVe, 2026-09-25 (laptop, Intel; success=1, deterministic=1, instance_exact=1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 41c4d7e7d7193b0d) and the oracle script (byte-identical to that run's /app/output/gen.py; ref_primitives.py unchanged since f15dbdb7). Changed since then, so the label is partial: the grader tests/grade.py (dev/qineng 82d76c61 added the GPU-backend exception; this PR writes the verdict before the video) and the tooling rcb_robowits.py (dev/qineng 5aa848bd, bddfc520, adce3fef, 8f0ebd55, 82d76c61, 6c0b439e, fe5fb9e6, 1515ea4e). Not re-run on this version (static validation only, 2026-10-01). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robowits:0.1.1` |

## Task
Build a stable two-layer stack so the red cube's center is above the green colored dot. One replayable trajectory from
the frozen instance (evaluation scene 0 of RoboWits task 14), with the privileged tooling (`rcb_robowits.py`: the
scene's state, resets, thin primitives, replay); the success criterion as graded is in `instruction.md`.

## Difficulty
Tabletop bimanual manipulation with a 16-DoF joint-target action space: three 5 cm cubes must be rearranged into a
two-layer stack whose apex sits within 2.5 cm of a marker, and the two base cubes must end up touching. The tooling
gives only thin primitives (IK moves on RoboWits' own pink/pinocchio IK, joint moves, gripper, hold): grasping and
placing are the agent's to build. The wrist joints have ±60° limits (a vertical approach is only reachable for
finger-closing directions within roughly ±60° of world y), the placement tolerances are tight, and the assembled stack
must survive the release and retreat of the gripper. The physics runs at ~700 control steps/s, so iteration is cheap.

## Reference solution
`solution/oracle_stack_cubes.py`: with the left arm, grasp base cube 1 and place it axis-aligned on the marker, grasp
base cube 2 and place it flush against it, grasp the apex cube and place it centred over the marker, then retreat. Its
grasp / place skills live in `solution/ref_primitives.py` (never in the agent image). `solution/solve.sh` records it
into a trajectory.

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
| RoboWits task | `14-stack-cubes-v0` (RoboWits @ 9cc30ae, Genesis 0.4.7: CPU physics backend, EGL rendering on the GPU) |
| Instance | entry 0 of RoboWits' `eval_dataset_50/14.json`; object poses and the expected state hash in `environment/instance.json` (the verifier's copy in `tests/`) |
| Robot | Marvin bimanual: 2 × 7-DoF arms with Pika parallel grippers; JOINT_ABS actions (T, 16) at 30 Hz |
| GPU | EGL camera rendering only (`environment/docker-compose.yaml`, `tests/docker-compose.yaml`) |
