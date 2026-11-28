# MuJoCo Playground · ALOHA single peg insertion (standard)

| | |
|---|---|
| Task ID | `mujoco_playground_aloha_single_peg_insertion-standard` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | ALOHA 2 bimanual robot (two ViperX 300 S arms, 6 joints and a gripper each; 14 position actuators) |
| Mode | standard |
| Instance | `mujoco_playground/AlohaSinglePegInsertion`, seed 60417 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Push the red peg well into the open end of the blue socket.

## Success criteria
Pass condition, defined by this benchmark (MuJoCo Playground's `AlohaSinglePegInsertion` has only a shaped training reward and no success
test), checked on one state, the one after the episode's last control step: the peg's tip (site `peg_end2`) is less
than 5 mm from the socket's axis, the line through sites `socket_rear` and `socket_entrance`, and lies inside the
cavity. Inside means the tip's position t along the axis is from −0.875 to 0.75, where t = 0 at `socket_rear` (the
tube's centre), t = 1 at `socket_entrance` (the open end) and one unit is 48 mm: at least 12 mm in from the open end,
and at most 2 mm past the inner face of the rear wall (t = −0.833). Both the peg and the socket can move; the sites
are taken where they are in that state. Meeting the condition at an earlier step does not count.

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
