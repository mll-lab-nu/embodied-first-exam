# robotwin_2_0_adjust_bottle-privileged

| | |
|---|---|
| Benchmark | RoboTwin 2.0 |
| Mode | privileged |
| Twin | `robotwin_2_0_adjust_bottle-standard` |
| Simulator / robot | `robotwin` / `aloha-agilex` |
| Family / instance | `adjust_bottle` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robotwin:0.1.1` |

## Task
RoboTwin 2.0 adjust_bottle (ALOHA-AgileX dual arm, SAPIEN): produce one replayable trajectory. Pick up the bottle on the table headup with the correct arm. Frozen scene instance (RoboTwin seed 60417).

## Difficulty
RoboTwin's scripted expert needs 3 planned motions (26 lines); official data-generation success on ALOHA-AgileX 93% (the expert's own pass rate over random layouts); in our image the expert passed on seed 60417 on attempt 1 of 1 with 1857 physics steps. Tags from the code: single-arm, joint-predicate. RoboTwin evaluation budget 400 policy actions. The trajectory is the raw per-step drive-target record, so any plan failure or a grasp that slips during replay scores 0.

## Reference solution
RoboTwin 2.0's expert methods for `adjust_bottle` (play_once; scrubbed from the image), copied verbatim into
`solution/oracle_adjust_bottle.py` and bound onto the env; `solution/solve.sh` records it into a trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice;
pass iff RoboTwin's `check_success` holds after every replay and the final-state hashes agree (`tests/grade.py`),
plus `/logs/verifier/replay.mp4`. The trajectory is the per-physics-step drive-target record (T, 34) captured by
hooking `scene.step()`; the instance is rebuilt from the RoboTwin seed and checked against the stored
initial-state hash on every reset.

## Details
| | |
|---|---|
| RoboTwin eval step limit | 400 (policy-eval budget upstream; indicative of task length) |

### Goal
Pick up the bottle on the table headup with the correct arm.
