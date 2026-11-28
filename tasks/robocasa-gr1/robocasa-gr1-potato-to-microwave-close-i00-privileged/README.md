# RoboCasa-GR1 · PnPPotatoToMicrowaveClose (privileged)

| | |
|---|---|
| Task ID | `robocasa-gr1-potato-to-microwave-close-i00-privileged` |
| Benchmark | [RoboCasa-GR1](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) (NVIDIA et al., 2025), upstream `robocasa/robocasa-gr1-tabletop-tasks@4840e67` |
| Robot | Fourier GR1 humanoid (two arms, waist and two six-command dexterous Fourier hands; fixed base) |
| Mode | privileged |
| Instance | `robocasa-gr1/PnPPotatoToMicrowaveClose`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the potato in the microwave and close the microwave door.

## Success criteria
Both hold: the potato's origin (the position of its body `obj_main`) lies inside the microwave's interior box, the box
spanned by the microwave's interior sites (`microwave_main_group_int_p0`, `_int_px`, `_int_py`, `_int_pz`) with no
margin; and the microwave door is shut: its hinge is open by at most 0.5 % of 90 degrees (0.45 degrees). The hands,
contacts and the potato's orientation are not checked.

The graded file is `/app/output/trajectory.npz`: an `actions` array of shape (T, 24) with 1 ≤ T ≤ 3000, one row per
control step (1/20 s); values outside the channel limits are clipped. The verifier, in a separate sandbox without
network, replays it once, open-loop, in a fresh process from its own copy of the frozen start, and checks the
conditions above once, with the environment's own `_check_success`, on the state after the last row. Meeting them
earlier in the replay does not count, no step is simulated after the last row, and a scene that already met them at
the start would not count either.

A missing file scores 0, and so does an invalid one: not a plain `.npz` of at most 8 MB holding only arrays (at most
64), no `actions` array, a shape other than (T, 24), a NaN or infinite value, or T outside 1 to 3000. A replay that
does not run to its end (a simulator error, or a frozen instance that fails its hash check) scores 0.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 20 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
The scenes, task definitions and success checks are those of RoboCasa's GR1 tabletop tasks
([robocasa/robocasa-gr1-tabletop-tasks](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) @ `4840e67`, MIT
License, copyright 2025 the NVIDIA GEAR group; paper: NVIDIA et al., 2025, "GR00T N1: An Open Foundation Model for
Generalist Humanoid Robots", arXiv:2503.14734), built on robosuite
([ARISE-Initiative/robosuite](https://github.com/ARISE-Initiative/robosuite) @ `51cc017`, MIT License). Assets are
downloaded when the image is built and are not in this repository: RoboCasa's fixture, texture and object archives
(CC BY 4.0) and NVIDIA's
[PhysicalAI-DigitalCousin-Assets](https://huggingface.co/datasets/nvidia/PhysicalAI-DigitalCousin-Assets)
(`lightwheel` and `sketchfab` object meshes), licensed **CC BY-NC 4.0: non-commercial use only**.
