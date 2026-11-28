# KinDER · constrained-cupboard (standard)

| | |
|---|---|
| Task ID | `kinder-constrained-cupboard-i00-standard` |
| Benchmark | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (Huang et al., 2026), upstream `Princeton-Robot-Planning-and-Learning/kindergarden@5b2dbac` |
| Robot | TidyBot++ mobile manipulator: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper |
| Mode | standard |
| Instance | `constrained-cupboard`, seed 0 |
| Time limit | 30 min |
| Reference solution | None |

## Task
Put the six brown rods lying on the floor into the row of narrow cupboards ahead of you, one rod in the tall compartment
of each of six cupboards. Taking the rods in order of distance from where you start, nearest first, they go into the
11th, 5th, 2nd, 8th, 4th and 1st cupboard of the row, counted from the left as you face it.

## Success criteria
Goal check (KinDER `ConstrainedCupboard3D-o6`): each of the six rods has its own cupboard, as the task names them,
and the centre of every rod lies inside the goal region of the tall compartment of its own cupboard. A rod in another
rod's cupboard does not count. Nothing else is checked.

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
