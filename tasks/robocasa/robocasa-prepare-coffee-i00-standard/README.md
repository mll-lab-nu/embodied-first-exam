# RoboCasa · PrepareCoffee (standard)

| | |
|---|---|
| Task ID | `robocasa-prepare-coffee-i00-standard` |
| Benchmark | [RoboCasa](https://github.com/robocasa/robocasa) (Nasiriany et al., 2024), upstream `robocasa/robocasa@756598a` |
| Robot | Franka Emika Panda arm with a parallel-jaw gripper on an Omron mobile base with a torso lift (robosuite `PandaMobile`) |
| Mode | standard |
| Instance | `robocasa/PrepareCoffee`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Take the mug from the cabinet, put it under the coffee machine's spout, press the start button, and move your hand away.

## Success criteria
The mug's position (its body origin) is less than 4 cm from the coffee machine's mug place site (the point under its
spout) horizontally (x-y) and less than 10 cm from it vertically; the coffee machine is on; the gripper's grip site is
more than 25 cm from the mug's position and more than 15 cm from the centre of the start button. The machine turns on
at the end of the first control step in which the gripper touches the start button and then stays on, whether or not
the mug is in place by then. The mug's orientation and the gripper's opening are not checked.

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
