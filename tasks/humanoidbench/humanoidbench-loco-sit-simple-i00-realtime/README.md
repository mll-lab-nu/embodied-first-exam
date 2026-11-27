# HumanoidBench · sit_simple (realtime)

| | |
|---|---|
| Task ID | `humanoidbench-loco-sit-simple-i00-realtime` |
| Benchmark | [HumanoidBench](https://humanoid-bench.github.io/) (Sferrazza et al., 2024), upstream `carlosferrazza/humanoid-bench@cb11890` |
| Robot | Unitree H1 humanoid, 19 position-controlled actuators (HumanoidBench `h1`) |
| Mode | realtime, slowdown 1 |
| Instance | `sit_simple`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Sit down on the chair right behind you and stay seated, upright and still.

## Success criteria
Pass mark: an episode return of at least 750, upstream's success bar, where the return is the sum of
HumanoidBench's per-step `sit_simple` reward over the episode. Each control step earns between 0 and 1, more the closer
the robot is to sitting on the chair behind it: pelvis at seat height above the seat, a seated upright posture, no
horizontal motion and little actuator effort. An episode is at most 1,000 control steps (20 s at
50 Hz).

Termination (the episode ends at once as a failure): the robot falls, its pelvis below 0.5 m (lower than when seated).

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
