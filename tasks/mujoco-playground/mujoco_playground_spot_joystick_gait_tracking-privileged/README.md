# MuJoCo Playground · SpotJoystickGaitTracking (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_spot_joystick_gait_tracking-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Boston Dynamics Spot quadruped, 12 joint position actuators |
| Mode | privileged |
| Instance | `mujoco_playground/SpotJoystickGaitTracking`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Make the robot follow the joystick's commands for the whole schedule without falling over, moving its feet in the
commanded gait: the same stepping pattern, rhythm and foot height.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `SpotJoystickGaitTracking` has only a shaped training reward and no success
test): the episode runs all 1,000 control steps of the instance's command schedule (20 s at 50 Hz) with no
termination, and in each of the schedule's 5 command segments the robot tracks both the command and the
gait on average. Over each segment, leaving out its first 25 control steps (0.5 s):

- the mean planar velocity error |(v_x, v_y) − (cmd_vx, cmd_vy)| is at most 0.2 m/s and the mean yaw-rate error
  |ω_z − cmd_wz| is at most 0.3 rad/s (the IMU's velocimeter and gyro, in the body's IMU frame; the command is the
  schedule's (vx, vy, wz) in force at that control step);
- the mean foot-height error is at most 0.05 m. At each control step this error is the root mean square, over the four
  feet, of the foot's height above the floor minus its target height. The target follows Playground's gait curve
  (`gait.get_rz`) over each foot's phase, for this instance's gait: `pace` at 3.66 Hz with a swing height of 0.129 m.

Termination (a failure at any step; a live episode ends there): Playground's fall rule for this environment, the body
tilted by more than about 32° (the IMU frame's z axis has a world z component below 0.85).

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
