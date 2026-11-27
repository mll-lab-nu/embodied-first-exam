# MuJoCo Playground · Panda pick cube with orientation (standard)

| | |
|---|---|
| Task ID | `mujoco_playground_panda_pick_cube_orientation-standard` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Franka Emika Panda arm with its two-finger gripper (7 joint and 1 finger position actuators) |
| Mode | standard |
| Instance | `mujoco_playground/PandaPickCubeOrientation`, seed 60417 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Pick up the green box and hold it at the see-through red box, tilted the same way.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `PandaPickCubeOrientation` has only a shaped training reward and no success
test), checked on one state, the one after the episode's last control step: the green box's centre is less than 2 cm
from the centre of the see-through red target box, and the box's orientation is less than 15° from the target's (the
angle of the rotation between them). Meeting the condition at an earlier step does not count.

Graded: the live episode, judged by the simulator service when it ends; nothing is replayed. The condition is checked
on the episode's control steps as the service executed them. The service never reports success while the episode
runs, and meeting the condition does not end the episode. The episode ends at the agent's `/finish`, or
when the agent's session ends (at the latest after 30 min). There is one episode, with no reset and no step limit. An episode ended by a simulator error
(a call that makes the simulation fail) scores 0. Before the agent is served, the service checks that the scene starts
at the frozen instance (its state hash); a mismatch, or a service that cannot record its verdict, is an
infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 7 GiB | 8192 | 6 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
MuJoCo Playground ([google-deepmind/mujoco_playground](https://github.com/google-deepmind/mujoco_playground) @
`4057c14`) is released under the Apache License 2.0. The robot models come from MuJoCo Menagerie
([google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ `1b86ece`, the commit
Playground pins), each under its own license: Unitree Go1 (BSD 3-Clause, Unitree Robotics), Boston Dynamics Spot
(BSD 3-Clause, Clearpath Robotics), Google Barkour vB (Apache License 2.0, DeepMind), ALOHA 2 (BSD 3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0). The rough-terrain texture is from Poly Haven (CC0). No
non-commercial terms apply. The simulator is MuJoCo 3.3.7 (Apache License 2.0).
