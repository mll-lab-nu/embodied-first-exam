# robosuite-cube-stack-i00-privileged

| | |
|---|---|
| Benchmark | robosuite (example task) |
| Mode | privileged |
| Twin | — (privileged only) |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `cube_stack` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robosuite:0.1.1` |

## Task
robosuite cube_stack: produce one replayable trajectory for frozen scene instance 00.

## Difficulty
The example task of the benchmark: stack the red cube on the green one with a Franka arm through cap-x primitives (`get_object_pose`, `goto_pose`, grippers) and leave it stacked. It is easy on purpose: it shows the task layout, the trajectory deliverable and the fresh-process replay verifier, and runs on CPU.

## Reference solution
cap-x's human-written oracle for `cube_stack` (`solution/solve.sh` records it into a trajectory).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz` in a fresh process, twice;
pass iff the task predicate holds after every replay and the final-state hashes agree (`rcb.grade`).
