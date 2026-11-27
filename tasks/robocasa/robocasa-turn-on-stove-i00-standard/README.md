# RoboCasa · TurnOnStove (standard)

| | |
|---|---|
| Task ID | `robocasa-turn-on-stove-i00-standard` |
| Benchmark | [RoboCasa](https://github.com/robocasa/robocasa) (Nasiriany et al., 2024), upstream `robocasa/robocasa@756598a` |
| Robot | Franka Emika Panda arm with a parallel-jaw gripper on an Omron mobile base with a torso lift (robosuite `PandaMobile`) |
| Mode | standard |
| Instance | `robocasa/TurnOnStove`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Turn on the front left burner of the stove.

## Success criteria
The front left burner is on: its knob's angle, taken modulo 2π, is at least 0.35 rad and at most 2π − 0.35 rad (at
least 0.35 rad, about 20°, away from the off position in either direction). The other knobs are not read.

Graded is the one live episode: no reset, no step limit. It ends when the agent sends `POST /finish`, or when the
agent's session ends (at the latest after 1 h); the environment's own check (`_check_success`) is evaluated on
the state after the last control step the service executed, and nothing is replayed. Meeting the conditions earlier
in the episode does not count, and the service never reports success while the episode runs. A scene already solved
at the start would not count (the frozen start is not solved).

A simulator error raised while executing an agent's call ends the episode with 0, as do repeated service crashes that
all happened while serving the agent's calls. Before the agent is served, the service checks that the scene starts at
the frozen instance (the instance file's hash and the start state's hash); a mismatch, a service crash the episode
cannot be resumed from, or a missing or unfinished verdict is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 6 | 15 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
RoboCasa ([robocasa/robocasa](https://github.com/robocasa/robocasa) @ `756598a`, v0.2) is released under the
[MIT License](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/LICENSE) (Copyright (c)
2024 the RoboCasa Team); paper: Nasiriany et al., 2024, "RoboCasa: Large-Scale Simulation of Everyday Tasks for
Generalist Robots", RSS 2024. robosuite 1.5.1 is MIT-licensed and MuJoCo 3.2.6 is under the Apache License 2.0. The
kitchen assets are downloaded when the image is built and are not in this repository: fixtures and textures from
[robocasa/robocasa-assets](https://huggingface.co/datasets/robocasa/robocasa-assets) (CC-BY-4.0), v0.2 fixtures from a
mirror, [jianzhang96/robocasa-assets](https://huggingface.co/datasets/jianzhang96/robocasa-assets) (Apache-2.0),
RoboCasa's objaverse and AI-generated object archives (CC-BY-4.0), and the lightwheel and sketchfab object sets of
[nvidia/PhysicalAI-DigitalCousin-Assets](https://huggingface.co/datasets/nvidia/PhysicalAI-DigitalCousin-Assets) under
**CC-BY-NC-4.0: non-commercial use only**.
