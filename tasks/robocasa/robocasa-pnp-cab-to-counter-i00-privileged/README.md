# RoboCasa · PnPCabToCounter (privileged)

| | |
|---|---|
| Task ID | `robocasa-pnp-cab-to-counter-i00-privileged` |
| Benchmark | [RoboCasa](https://github.com/robocasa/robocasa) (Nasiriany et al., 2024), upstream `robocasa/robocasa@756598a` |
| Robot | Franka Emika Panda arm with a parallel-jaw gripper on an Omron mobile base with a torso lift (robosuite `PandaMobile`) |
| Mode | privileged |
| Instance | `robocasa/PnPCabToCounter`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Take the hot dog out of the cabinet and put it on the counter below it, and move your hand away.

## Success criteria
The hot dog touches the counter below the cabinet (`counter_1_left_group`), and the gripper's grip site is more than 25
cm from the hot dog's position (its body origin). Only the contact is checked, not where on the counter it lies or
whether the gripper is open.

The graded file is `/app/output/trajectory.npz`: a plain `.npz` (at most 8 MB, at most 64 members, arrays only) with an
array `actions` of shape (T, 12), finite numbers, 1 ≤ T ≤ 3000, one row per control step (1/20 s); each value is
clipped to its channel's limits ([-1, 1]). The verifier, in a separate sandbox without network, replays it once,
open-loop, in a fresh process from its own copy of the frozen start, and evaluates the environment's own check
(`_check_success`) on the state after the last row; meeting the conditions at an earlier step does not count. A scene
already solved at the start would not count either (the frozen start is not solved).

A missing file scores 0, and so does an invalid one: not a readable `.npz` of that kind, no `actions`, a shape other
than (T, 12), a NaN or infinite value, or T outside 1 to 3000. A replay that fails (a simulator error) scores 0.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 15 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

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
