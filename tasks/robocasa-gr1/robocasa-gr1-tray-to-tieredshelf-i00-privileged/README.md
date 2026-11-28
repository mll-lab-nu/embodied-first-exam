# RoboCasa-GR1 · PosttrainPnPNovelFromTrayToTieredshelfSplitA (privileged)

| | |
|---|---|
| Task ID | `robocasa-gr1-tray-to-tieredshelf-i00-privileged` |
| Benchmark | [RoboCasa-GR1](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) (NVIDIA et al., 2025), upstream `robocasa/robocasa-gr1-tabletop-tasks@4840e67` |
| Robot | Fourier GR1 humanoid (two arms, waist and two six-command dexterous Fourier hands; fixed base) |
| Mode | privileged |
| Instance | `robocasa-gr1/PosttrainPnPNovelFromTrayToTieredshelfSplitA`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the bell pepper from the tray on the top tier of the tiered shelf, and move both hands away.

## Success criteria
All of these hold:
- At least 2 of 15 key points of the bell pepper lie in the tiered shelf's top zone (of its spawn zones, one per
  tier, the one whose centre is highest): a box 32.9 cm by 9.0 cm, 1.8 cm high. The key points are the 8 corners of
  the bell pepper model's bounding box, the centres of its 6 faces and its centre, each moved 20 % of the way toward
  the centre. Contact with the tiered shelf is not required.
- The bell pepper does not touch the counter (the table, `table_main_group`).
- The tiered shelf is upright: its z axis has a world-z component above 0.8 (tilted less than about 37 degrees).
- Each hand's grip site (`gripper0_right_grip_site`, `gripper0_left_grip_site`) is more than 0.25 m from the bell
  pepper's origin and more than 0.25 m from the tiered shelf's origin.
- The other item that started on the tray with the bell pepper (`distractor_obj_distractor_obj_type_0_num_0`) does
  not meet that same top-zone rule; on a lower tier it does not count against the task.

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
