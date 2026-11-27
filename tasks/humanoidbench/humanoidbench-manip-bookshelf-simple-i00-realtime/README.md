# HumanoidBench · bookshelf_simple (realtime)

| | |
|---|---|
| Task ID | `humanoidbench-manip-bookshelf-simple-i00-realtime` |
| Benchmark | [HumanoidBench](https://humanoid-bench.github.io/) (Sferrazza et al., 2024), upstream `carlosferrazza/humanoid-bench@cb11890` |
| Robot | Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled actuators (HumanoidBench `h1hand`) |
| Mode | realtime, slowdown 1 |
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

Graded: the live episode, judged by the simulator service as it runs; nothing is replayed. The clock does not stop:
an episode starts paused at the frozen start, and from the agent's first `submit` one control step runs every 20 ms
× S of wall time (slowdown S = 1) whether or not the agent sends anything; when the planned targets run out
the last ones are held. The pass mark is judged as an event: once the episode's return reaches it at some control step, the episode
is a success, even if a fall or another termination above ends it afterwards; a termination before the mark is
reached scores 0. Reaching the mark neither ends the episode nor is shown to the agent. Otherwise the episode ends at
the agent's `/finish`, at the end of its control steps, or when the agent's time (1 h) runs out, and is judged on
the return reached by then. The agent has 50 resets, each starting a new, paused episode from the frozen start;
only the last episode (the one after the last reset) is graded. After the agent's first command, a simulator error or
a simulator crash inside a control step is the agent's 0; anything before the first command, a killed service, a
failed resume or a reset that does not rebuild the scene is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | 5 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
HumanoidBench (Sferrazza et al., 2024; <https://github.com/carlosferrazza/humanoid-bench>) is released under the MIT
License, copyright (c) 2024 Robot Learning Lab, UC Berkeley. The image's notice is
`images/humanoidbench/LICENSE.humanoid-bench`; this task's `rewards.json` carries upstream's code under that license.
Robot models shipped with upstream: the Unitree H1 model (BSD 3-Clause, copyright Unitree Robotics) and, on the
two-handed H1, the Shadow Hand model from MuJoCo Menagerie (Apache License 2.0). No non-commercial terms apply.
