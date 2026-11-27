# MuJoCo Playground · ALOHA single peg insertion (privileged)

| | |
|---|---|
| Task ID | `mujoco_playground_aloha_single_peg_insertion-privileged` |
| Benchmark | [MuJoCo Playground](https://playground.mujoco.org/) (Zakka et al., 2025), upstream `google-deepmind/mujoco_playground@4057c14` |
| Robot | ALOHA 2 bimanual robot (two ViperX 300 S arms, 6 joints and a gripper each; 14 position actuators) |
| Mode | privileged |
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
