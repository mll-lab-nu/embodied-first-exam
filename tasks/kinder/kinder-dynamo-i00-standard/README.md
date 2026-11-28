# KinDER · dynamo (standard)

| | |
|---|---|
| Task ID | `kinder-dynamo-i00-standard` |
| Benchmark | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (Huang et al., 2026), upstream `Princeton-Robot-Planning-and-Learning/kindergarden@5b2dbac` |
| Robot | TidyBot++ mobile manipulator: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper |
| Mode | standard |
| Instance | `dynamo`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Drive into the green square marked on the floor, a few metres away ahead and slightly to your right. You may push the
three chairs in the way.

## Success criteria
Goal check (KinDER `Dynamo3D-o3`): the centre of the robot's base lies inside the green square marked on the floor,
0.85 m on a side. Nothing else is checked: the chairs may be pushed anywhere, and the arm and gripper may be in any
pose.

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
