# RoboCasa-GR1 · PosttrainPnPNovelFromPlacematToTieredshelfSplitA (standard)

| | |
|---|---|
| Task ID | `robocasa-gr1-placemat-to-tieredshelf-i00-standard` |
| Benchmark | [RoboCasa-GR1](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) (NVIDIA et al., 2025), upstream `robocasa/robocasa-gr1-tabletop-tasks@4840e67` |
| Robot | Fourier GR1 humanoid (two arms, waist and two six-command dexterous Fourier hands; fixed base) |
| Mode | standard |
| Instance | `robocasa-gr1/PosttrainPnPNovelFromPlacematToTieredshelfSplitA`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the tomato from the placemat on the top tier of the tiered shelf, and move both hands away.

## Success criteria
All of these hold:
- At least 2 of 15 key points of the tomato lie in the tiered shelf's top zone (of its spawn zones, one per tier,
  the one whose centre is highest): a box 24.8 cm by 11.4 cm, 4.5 cm high. The key points are the 8 corners of the
  tomato model's bounding box, the centres of its 6 faces and its centre, each moved 20 % of the way toward the
  centre. Contact with the tiered shelf is not required.
- The tomato does not touch the counter (the table, `table_main_group`).
- The tiered shelf is upright: its z axis has a world-z component above 0.8 (tilted less than about 37 degrees).
- Each hand's grip site (`gripper0_right_grip_site`, `gripper0_left_grip_site`) is more than 0.25 m from the
  tomato's origin and more than 0.25 m from the tiered shelf's origin.
- The other item that started on the placemat with the tomato (`distractor_obj_distractor_obj_type_0_num_0`) does
  not meet that same top-zone rule; on a lower tier it does not count against the task.

Graded is the one live episode in the simulator service: no reset, no step limit, nothing replayed. It ends when the
agent sends `POST /finish` or when its session ends (at the latest after 1 h); the conditions above are then
checked once, with the environment's own `_check_success`, on the state after the last executed control step. A
success earlier in the episode neither ends it nor counts, and the service never reports success while the episode
runs. Control steps run by hold chunks belong to the episode like any others.

An episode ended by a simulator error during an agent's call scores 0, as do more than two service crashes that all
happened while serving the agent's calls. Before the agent is served, the scene is checked to start at the frozen
instance (instance and start-state hashes, not already solved). A mismatch there, a crash the episode cannot be
resumed from, or a missing verdict is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 16 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 3 | 14 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

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
