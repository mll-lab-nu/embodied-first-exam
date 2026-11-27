# RoboCasa-GR1 · PnPMilkToMicrowaveClose (standard)

| | |
|---|---|
| Task ID | `robocasa-gr1-milk-to-microwave-close-i00-standard` |
| Benchmark | [RoboCasa-GR1](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) (NVIDIA et al., 2025), upstream `robocasa/robocasa-gr1-tabletop-tasks@4840e67` |
| Robot | Fourier GR1 humanoid (two arms, waist and two six-command dexterous Fourier hands; fixed base) |
| Mode | standard |
| Instance | `robocasa-gr1/PnPMilkToMicrowaveClose`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the milk in the microwave and close the microwave door.

## Success criteria
Both hold: the milk's origin (the position of its body `obj_main`) lies inside the microwave's interior box, the box
spanned by the microwave's interior sites (`microwave_main_group_int_p0`, `_int_px`, `_int_py`, `_int_pz`) with no
margin; and the microwave door is shut: its hinge is open by at most 0.5 % of 90 degrees (0.45 degrees). The hands,
contacts and the milk's orientation are not checked.

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
