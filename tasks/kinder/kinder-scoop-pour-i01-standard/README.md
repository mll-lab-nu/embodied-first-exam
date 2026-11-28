# KinDER · scoop-pour (standard)

| | |
|---|---|
| Task ID | `kinder-scoop-pour-i01-standard` |
| Benchmark | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (Huang et al., 2026), upstream `Princeton-Robot-Planning-and-Learning/kindergarden@5b2dbac` |
| Robot | TidyBot++ mobile manipulator: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper |
| Mode | standard |
| Instance | `scoop-pour`, seed 0 |
| Time limit | 30 min |
| Reference solution | None |

## Task
Move all 50 small cubes from the yellow bin into the green bin. There is a scoop you can use.

## Success criteria
Goal check (KinDER `ScoopPour3D-o50`): the centre of every one of the 50 cubes lies inside the green bin's goal
region, a box 0.37 m by 0.22 m centred in the bin, from 3 cm to 5.5 cm above the bin's base frame, so a cube resting
on the rim or stacked high does not count. Nothing else is checked: the scoop and the yellow bin may be anywhere.

Graded: the live episode, judged by the simulator service; nothing is replayed. Reaching the goal does not end the
episode and is not shown to the agent. The episode ends at the agent's `/finish`, after 1,000 control steps (100 s
of robot time), or when the agent's time (30 min) runs out. It is passed if KinDER's goal check holds in the state
the episode ends in. Resets granted: 0. A reset starts a new episode from the frozen start; only the episode
after the last reset is graded. A simulator error raised by the agent's own call ends the episode with 0. An episode that does not
start from the frozen instance, or a service crash outside the agent's calls, is an infrastructure failure, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
KinDER ([Princeton-Robot-Planning-and-Learning/kindergarden](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden)
@ `5b2dbac`) is released under the MIT License (copyright (c) 2025 Tom Silver). The lab scenes are MimicLabs
([Gatech-RL2/mimiclabs](https://github.com/Gatech-RL2/mimiclabs), MIT License), fetched by upstream's own download
script when the image is built. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
