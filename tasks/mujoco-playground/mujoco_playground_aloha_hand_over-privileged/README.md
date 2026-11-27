# MuJoCo Playground · ALOHA hand-over (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_aloha_hand_over-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | ALOHA 2 bimanual robot (two ViperX 300 S arms, 6 joints and a gripper each; 14 position actuators) |
| Mode | privileged |
| Instance | `mujoco_playground/AlohaHandOver`, seed 60417 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Pick up the red box with the left arm, pass it to the right arm, and hold it at the see-through target box. Then take
the left arm off the box.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `AlohaHandOver` has only a shaped training reward and no success
test), checked on one state, the one after the episode's last control step: the red box's centre is less than 3 cm from
the centre of the see-through target box; the box touches at least one finger of the right gripper and no part of the
left arm (links, gripper or fingers); and the box's centre is at least 0.05 m high (it rests on the table at about
0.03 m). Meeting the condition at an earlier step does not count.

Graded file: `/app/output/trajectory.npz`, array `actions` of shape (T, 14) with T at most 3,000: one row
of actuator targets per control step, all finite (values outside the actuator ranges are clipped). After the agent's
session the verifier, in a separate sandbox without network, replays it once, open-loop, from its own copy of the
frozen start (`tests/instance.json`), and checks the condition on that replay. Only the trajectory is scored (`gen.py`
is not). A missing file, a file that is not an `.npz` with a numeric `actions` array, or an array of another width, with
more rows or with a NaN or infinite value scores 0. A replay that does not rebuild the frozen start (its state hash
differs) and any other error inside the grader, such as a replay that dies or times out, are reported as a grader
error, not as the agent's score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 5 GiB | 8192 | 6 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 6 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
MuJoCo Playground ([google-deepmind/mujoco_playground](https://github.com/google-deepmind/mujoco_playground) @
`4057c14`) is released under the Apache License 2.0. The robot models come from MuJoCo Menagerie
([google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ `1b86ece`, the commit
Playground pins), each under its own license: Unitree Go1 (BSD 3-Clause, Unitree Robotics), Boston Dynamics Spot
(BSD 3-Clause, Clearpath Robotics), Google Barkour vB (Apache License 2.0, DeepMind), ALOHA 2 (BSD 3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0). The rough-terrain texture is from Poly Haven (CC0). No
non-commercial terms apply. The simulator is MuJoCo 3.3.7 (Apache License 2.0).
