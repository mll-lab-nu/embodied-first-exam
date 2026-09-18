# robosuite-cube-stack-i00

| | |
|---|---|
| Simulator / robot | robosuite / franka-panda |
| Family / instance | `cube_stack` / seed 00 |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-robosuite:0.1.0` |
| Agent budget | 3600 s |

## Difficulty
<!-- Why is this instance non-trivial for a coding agent? Which primitive interactions matter? -->

## Reference solution
cap-x's human-written oracle for `cube_stack` (`solution/solve.sh` records it into a trajectory).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz` in a fresh process, twice;
pass iff the task predicate holds after every replay and the final-state hashes agree (`rcb.grade`).
