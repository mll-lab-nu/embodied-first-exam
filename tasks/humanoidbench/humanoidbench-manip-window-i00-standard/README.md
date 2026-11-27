# HumanoidBench · window (standard)

| | |
|---|---|
| Task ID | `humanoidbench-manip-window-i00-standard` |
| Benchmark | [HumanoidBench](https://humanoid-bench.github.io/) (Sferrazza et al., 2024), upstream `carlosferrazza/humanoid-bench@cb11890` |
| Robot | Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled actuators (HumanoidBench `h1hand`) |
| Mode | standard |
| Instance | `window`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Take hold of the wiping tool and wipe the window with it, moving it up and down.

## Success criteria
Pass mark: an episode return of at least 650, upstream's success bar, where the return is the sum of
HumanoidBench's per-step `window` reward over the episode. Each control step earns between 0 and 1: half from the
wiping tool's face lying flat against the glass, earned only while the tool touches the pane, and half from the tool
moving up or down at a steady wiping pace, both hands at the tool, and the robot standing upright in front of the
window with little actuator effort. An episode is at most 1,000 control steps (20 s at 50 Hz).

Terminations (each ends the episode at once as a failure):
- the robot falls, its pelvis below 0.58 m;
- the wiping tool drops, its centre below 0.58 m.

Graded: the live episode, judged by the simulator service as it runs; nothing is replayed. The pass mark is judged as
an event: once the episode's return reaches it at some control step, the episode is a success, even if a fall or
another termination above ends it afterwards; a termination before the mark is reached scores 0. Reaching the mark
neither ends the episode nor is shown to the agent. Otherwise the episode ends at the agent's `/finish`, at the end of
its control steps, or when the agent's time (1 h) runs out, and is judged on the return reached by then. The
agent has 50 resets, each starting a new episode from the frozen start; only the last episode (the one after the
last reset) is graded. A simulator error raised by the agent's own call ends the episode with 0. An episode that does
not start from the frozen instance, or a service crash outside the agent's calls, is an infrastructure failure, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 4 GiB | 1024 | 5 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
HumanoidBench (Sferrazza et al., 2024; <https://github.com/carlosferrazza/humanoid-bench>) is released under the MIT
License, copyright (c) 2024 Robot Learning Lab, UC Berkeley. The image's notice is
`images/humanoidbench/LICENSE.humanoid-bench`; this task's `rewards.json` carries upstream's code under that license.
Robot models shipped with upstream: the Unitree H1 model (BSD 3-Clause, copyright Unitree Robotics) and, on the
two-handed H1, the Shadow Hand model from MuJoCo Menagerie (Apache License 2.0). No non-commercial terms apply.
