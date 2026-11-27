# MuJoCo Playground · Go1Handstand (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_go1_handstand-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Unitree Go1 quadruped, 12 joint position actuators |
| Mode | privileged |
| Instance | `mujoco_playground/Go1Handstand`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Make the robot do a handstand: balance on its front legs, nose down and hind legs in the air, for 2 s.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `Go1Handstand` has only a shaped training reward and no success
test): no termination at any step, and the last 100 control steps (2 s) of the episode all have the trunk's forward
axis (the IMU frame's x axis) within 30° of straight down, the IMU at least 0.40 m above the floor, and neither hind
foot touching the floor. An episode is at most 500 control steps (10 s at 50 Hz).

Termination (a failure at any step; a live episode ends there): Playground's rule for this environment, either the
trunk tipped over, its up axis more than about 15° below the horizon (the IMU frame's z axis has a world z component
below −0.25), or a thigh, calf or hip of a front leg touching the floor.

Graded file: `/app/output/trajectory.npz`, array `actions` of shape (T, 12) with T at most 500: one row
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
