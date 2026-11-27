# HumanoidBench · bookshelf_simple (privileged)

| | |
|---|---|
| Task ID | `humanoidbench-manip-bookshelf-simple-i00-privileged` |
| Benchmark | [HumanoidBench](https://humanoid-bench.github.io/) (Sferrazza et al., 2024), upstream `carlosferrazza/humanoid-bench@cb11890` |
| Robot | Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled actuators (HumanoidBench `h1hand`) |
| Mode | privileged |
| Instance | `bookshelf_simple`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Put the five red objects on the bookshelf one at a time, palest first and darkest last, each on the see-through copy of
itself.

## Success criteria
Pass mark: an episode return of at least 2000, upstream's success bar, where the return is the sum of
HumanoidBench's per-step `bookshelf_simple` reward over the episode. The five objects are to be placed in a fixed order,
palest first, each on its own place on the shelves (its see-through copy). Each control step earns up to 1 from the
current object's closeness to its place, a hand's closeness to that object, and the robot standing upright with little
actuator effort. An object counts as placed once its centre comes within 15 cm of its place; the next object then
becomes the current one, and each placement adds a one-time bonus that grows with the number of objects placed. An
episode is at most 1,000 control steps (20 s at 50 Hz); placing the fifth object also ends it, as
the end of its steps would, not as a failure.

Terminations (each ends the episode at once as a failure):
- the robot falls, its pelvis below 0.58 m;
- the object being moved drops, its centre below 0.5 m.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name (`bookshelf_simple`) and at
most 1,000 rows of 61 finite servo targets, one row per control step (values outside [-1, 1] are
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
