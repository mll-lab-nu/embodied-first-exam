# RoboCasa · MicrowaveThawing (privileged)

| | |
|---|---|
| Task ID | `robocasa-microwave-thawing-i00-privileged` |
| Benchmark | [RoboCasa](https://github.com/robocasa/robocasa) (Nasiriany et al., 2024), upstream `robocasa/robocasa@756598a` |
| Robot | Franka Emika Panda arm with a parallel-jaw gripper on an Omron mobile base with a torso lift (robosuite `PandaMobile`) |
| Mode | privileged |
| Instance | `robocasa/MicrowaveThawing`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the squash from the counter in the microwave, close the door and turn the microwave on, and move your hand away.

## Success criteria
The squash is inside the microwave: each of the 8 corners of its bounding box (the box of its model, at its current
pose) lies within the microwave's interior box, which is widened at both ends of each of its three edges by 0.05 m²
divided by that edge's length (10 cm for an edge 0.5 m long). The microwave is on, and the gripper's grip site is
more than 25 cm from the squash's position (its body origin). Whether the squash is on the plate is not checked.

The microwave's on/off state is updated at the end of every control step: if the door is open more than 0.5% of 90°
(0.45°) the microwave is off; otherwise it turns off if it was on and the gripper touches the stop button, and turns
on if it was off and the gripper touches the start button. So it is on only with the door closed to within 0.45°.

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
