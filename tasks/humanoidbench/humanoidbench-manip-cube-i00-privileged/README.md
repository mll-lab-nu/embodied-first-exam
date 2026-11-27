# HumanoidBench · cube (privileged)

| | |
|---|---|
| Task ID | `humanoidbench-manip-cube-i00-privileged` |
| Benchmark | [HumanoidBench](https://humanoid-bench.github.io/) (Sferrazza et al., 2024), upstream `carlosferrazza/humanoid-bench@cb11890` |
| Robot | Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled actuators (HumanoidBench `h1hand`) |
| Mode | privileged |
| Instance | `cube`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Turn the two cubes on your palms until each sits the same way round as the see-through cube floating above your hands,
without dropping either.

## Success criteria
Pass mark: an episode return of at least 370, upstream's success bar, where the return is the sum of
HumanoidBench's per-step `cube` reward over the episode. Each control step earns between 0 and 1, mostly from how
closely both cubes match the orientation of the see-through target cube, then from each hand being at its cube, and
the rest from the robot standing upright and still with little actuator effort. An episode is at most 500
control steps (10 s at 50 Hz).

Terminations (each ends the episode at once as a failure):
- the robot falls, its pelvis below 0.58 m;
- either cube drops, its centre below 0.6 m.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name (`cube`) and at
most 500 rows of 61 finite servo targets, one row per control step (values outside [-1, 1] are
clipped). After the agent's session it is replayed once, open-loop, from the frozen start (`tests/instance.npz`) in a
fresh process of a separate verifier container without network, the only place the reward exists. The task is passed
if the replayed episode's return reaches the pass mark. The replay stops at the first of the terminations above; rows
after it are not run. Only the trajectory is scored (`gen.py` and `NOTES.md` are not). A missing file, a file for
another task, or one that is not such an array scores 0; an error inside the grader is reported as `grader_error`
(infrastructure), not as a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 20 GiB | 2048 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
HumanoidBench (Sferrazza et al., 2024; <https://github.com/carlosferrazza/humanoid-bench>) is released under the MIT
License, copyright (c) 2024 Robot Learning Lab, UC Berkeley. The image's notice is
`images/humanoidbench/LICENSE.humanoid-bench`; this task's `rewards.json` carries upstream's code under that license.
Robot models shipped with upstream: the Unitree H1 model (BSD 3-Clause, copyright Unitree Robotics) and, on the
two-handed H1, the Shadow Hand model from MuJoCo Menagerie (Apache License 2.0). No non-commercial terms apply.
