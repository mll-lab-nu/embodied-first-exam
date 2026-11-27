# MuJoCo Playground · Go1Getup (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_go1_getup-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Unitree Go1 quadruped, 12 joint position actuators |
| Mode | privileged |
| Instance | `mujoco_playground/Go1Getup`, seed 5 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
The robot has fallen over. Get it back up, standing upright at its normal height.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `Go1Getup` has only a shaped training reward and no success
test): the last 25 control steps (0.5 s) of the episode all have the trunk upright, its up axis (the IMU frame's z
axis) within 10° of vertical, and the IMU at least 0.22 m above the floor. An episode is at most 300 control steps (6 s
at 50 Hz); an episode of fewer than 25 control steps fails. There is no termination: no pose ends the episode early, and
only its last 25 steps are judged.

Graded file: `/app/output/trajectory.npz`, array `actions` of shape (T, 12) with T at most 300: one row
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
| `main` (the agent's) | 4 | 10 GiB | 2048 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
MuJoCo Playground ([google-deepmind/mujoco_playground](https://github.com/google-deepmind/mujoco_playground) @
`4057c14`) is released under the Apache License 2.0. The robot models come from MuJoCo Menagerie
([google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ `1b86ece`, the commit
Playground pins), each under its own license: Unitree Go1 (BSD 3-Clause, Unitree Robotics), Boston Dynamics Spot
(BSD 3-Clause, Clearpath Robotics), Google Barkour vB (Apache License 2.0, DeepMind), ALOHA 2 (BSD 3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0). The rough-terrain texture is from Poly Haven (CC0). No
non-commercial terms apply. The simulator is MuJoCo 3.3.7 (Apache License 2.0).
