# MuJoCo Playground · Go1Getup (standard)

| | |
|---|---|
| Task ID | `mujoco_playground_go1_getup-standard` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | Unitree Go1 quadruped, 12 joint position actuators |
| Mode | standard |
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

Graded: the live episode, judged by the simulator service when it ends; nothing is replayed. The condition is checked
on the episode's control steps as the service executed them. The service never reports success while the episode
runs, and meeting the condition does not end the episode. The episode ends at the agent's `/finish`, at the `done` action (the same end), after its last control step, or
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
