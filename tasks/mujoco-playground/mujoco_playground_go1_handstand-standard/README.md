# MuJoCo Playground · Go1Handstand (standard)

| | |
|---|---|
| Task ID | `mujoco_playground_go1_handstand-standard` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Unitree Go1 quadruped, 12 joint position actuators |
| Mode | standard |
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
