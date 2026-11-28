# MuJoCo Playground · BarkourJoystick (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_barkour_joystick-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Google Barkour vB quadruped, 12 joint position actuators |
| Mode | privileged |
| Instance | `mujoco_playground/BarkourJoystick`, seed 2 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Make the robot follow the joystick's commands for the whole schedule without falling over, even when it gets pushed.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `BarkourJoystick` has only a shaped training reward and no success
test): the episode runs all 1,000 control steps of the instance's command schedule (10 s: one control step is 10 ms)
with no termination, and in each of the schedule's 2 command segments the robot tracks the command on
average. Over each segment, leaving out its first 25 control steps (0.25 s), the mean planar velocity error
|(v_x, v_y) − (cmd_vx, cmd_vy)| is at most 0.2 m/s and the mean yaw-rate error |ω_z − cmd_wz| is at most 0.3 rad/s. The
velocity is the IMU's velocimeter and the yaw rate its gyro, both in the torso's IMU frame; the command is the
schedule's (vx, vy, wz) in force at that control step. The torso is pushed 12 times during the episode, at fixed
moments of the frozen instance; the pushes are part of the scene, not of the condition.

Termination (a failure at any step; a live episode ends there): Playground's rule for this environment, any of: the
torso's up axis pointing below the horizon; a leg joint outside its range (abduction −0.7 to 0.52 rad, hip −1.0 to
2.1 rad, knee 0.05 to 2.1 rad); the torso lower than 0.18 m.

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
