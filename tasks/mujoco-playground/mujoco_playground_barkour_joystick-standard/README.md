# MuJoCo Playground · BarkourJoystick (standard)

| | |
|---|---|
| Task ID | `mujoco_playground_barkour_joystick-standard` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Google Barkour vB quadruped, 12 joint position actuators |
| Mode | standard |
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

Graded: the live episode, judged by the simulator service when it ends; nothing is replayed. The condition is checked
on the episode's control steps as the service executed them. The service never reports success while the episode
runs, and meeting the condition does not end the episode. The episode ends at the agent's `/finish`, at the `done` action (the same end), after its last control step, at a termination, or
when the agent's session ends (at the latest after 30 min). The agent has 10 resets (`POST /reset`), each starting a new episode from the frozen start; only the last episode (the one after the last reset) is graded, and no reset is possible after `/finish`. An episode ended by a simulator error
(a call that makes the simulation fail) scores 0. Before the agent is served, the service checks that the scene starts
at the frozen instance (its state hash); a mismatch, or a service that cannot record its verdict, is an
infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## License
MuJoCo Playground ([google-deepmind/mujoco_playground](https://github.com/google-deepmind/mujoco_playground) @
`4057c14`) is released under the Apache License 2.0. The robot models come from MuJoCo Menagerie
([google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ `1b86ece`, the commit
Playground pins), each under its own license: Unitree Go1 (BSD 3-Clause, Unitree Robotics), Boston Dynamics Spot
(BSD 3-Clause, Clearpath Robotics), Google Barkour vB (Apache License 2.0, DeepMind), ALOHA 2 (BSD 3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0). The rough-terrain texture is from Poly Haven (CC0). No
non-commercial terms apply. The simulator is MuJoCo 3.3.7 (Apache License 2.0).
