# RoboCasa-GR1 · PosttrainPnPNovelFromTrayToCardboardboxSplitA (standard)

| | |
|---|---|
| Task ID | `robocasa-gr1-tray-to-cardboardbox-i00-standard` |
| Benchmark | [RoboCasa-GR1](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) (NVIDIA et al., 2025), upstream `robocasa/robocasa-gr1-tabletop-tasks@4840e67` |
| Robot | Fourier GR1 humanoid (two arms, waist and two six-command dexterous Fourier hands; fixed base) |
| Mode | standard |
| Instance | `robocasa-gr1/PosttrainPnPNovelFromTrayToCardboardboxSplitA`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the squash from the tray in the cardboard box, and move both hands away.

## Success criteria
All of these hold:
- The squash touches the cardboard box, and its origin is less than 70 % of the cardboard box's horizontal radius
  (the radius given by the cardboard box model's horizontal-radius site) from the cardboard box's origin in x and y.
- The squash does not touch the counter (the table, `table_main_group`).
- The cardboard box is upright: its z axis has a world-z component above 0.8 (tilted less than about 37 degrees).
- Each hand's grip site (`gripper0_right_grip_site`, `gripper0_left_grip_site`) is more than 0.25 m from the
  squash's origin and more than 0.25 m from the cardboard box's origin.

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
