# robosuite-cube-stack-i00-privileged

| | |
|---|---|
| Benchmark | robosuite (example task) |
| Mode | privileged |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `cube_stack` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-robosuite:0.1.1` |

## Task
robosuite cube_stack: produce one replayable trajectory for frozen scene instance 00.

## Difficulty
<!-- Why is this instance non-trivial for a coding agent? Which primitive interactions matter? -->

## Reference solution
cap-x's human-written oracle for `cube_stack` (`solution/solve.sh` records it into a trajectory).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz` in a fresh process, twice;
pass iff the task predicate holds after every replay and the final-state hashes agree (`rcb.grade`).
