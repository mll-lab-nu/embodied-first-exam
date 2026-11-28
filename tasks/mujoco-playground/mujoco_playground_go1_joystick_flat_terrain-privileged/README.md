# MuJoCo Playground · Go1JoystickFlatTerrain (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_go1_joystick_flat_terrain-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Unitree Go1 quadruped, 12 joint position actuators |
| Mode | privileged |
| Instance | `mujoco_playground/Go1JoystickFlatTerrain`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Make the robot follow the joystick's commands for the whole schedule without falling over.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `Go1JoystickFlatTerrain` has only a shaped training reward and no success
test): the episode runs all 1,000 control steps of the instance's command schedule (20 s at 50 Hz) with no
termination, and in each of the schedule's 4 command segments the robot tracks the command on average. Over
each segment, leaving out its first 25 control steps (0.5 s), the mean planar velocity error |(v_x, v_y) − (cmd_vx,
cmd_vy)| is at most 0.2 m/s and the mean yaw-rate error |ω_z − cmd_wz| is at most 0.3 rad/s. The velocity is the IMU's
velocimeter and the yaw rate its gyro, both in the trunk's IMU frame; the command is the schedule's (vx, vy, wz) in
force at that control step.

Termination (a failure at any step; a live episode ends there): Playground's fall rule for this environment, the
trunk's up axis pointing below the horizon (the IMU frame's z axis has a negative world z component).

Graded file: `/app/output/trajectory.npz`, array `actions` of shape (T, 12) with T at most 1,000: one row
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
