# RoboWits · align_blocks (standard)

| | |
|---|---|
| Task ID | `robowits-align-blocks-i00-standard` |
| Benchmark | [RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) (Lin et al., 2026), upstream `UMass-Embodied-AGI/RoboWits@9cc30ae` |
| Robot | Bimanual Marvin: two 7-DoF arms with Pika parallel grippers |
| Mode | standard |
| Instance | `align_blocks`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Line up the three cubes on the table in a perfectly straight line.

## Success criteria
The goal: seen from above, the two centres of the three target cubes that are farthest apart are at least 3 cm apart,
and the third centre is within 1.0 cm of the straight line through them. Each cube's bounding-box bottom is within
2.5 cm of the table top. Every object in the scene except the table and the robot, the ruler included, has its centre
over the table area enlarged by 3 cm on every side. No part of the robot touches any of the three cubes. Graded
objects: the three cubes.

Graded: the live episode the simulator service ran; nothing is replayed. There is one episode and no reset. The
episode ends when the agent sends `/finish` or when its session ends (at the latest after 1 h). Success is never
shown and never ends the episode. The verdict is a settle window on the live simulator, from the state the episode
ends in. The robot holds the last command for 30 control steps (1 s), and nothing is checked. For 60 more control
steps (2 s) the goal must then hold at every 6th step and at the last one. Through those 60 steps the set of graded
objects must not change, and no graded object may move more than 2 mm from where it was when they began. The window's
steps are part of the recorded episode.

Where the goal names the table area, it is a fixed rectangle, 0.79 m deep (away from the robot) and 1.38 m wide,
that the predicates use as the table's extent. Heights are measured from the table top.

The episode also ends on a simulator error, which scores 0. It also ends after 200,000 control steps: the goal is then
judged as it stands, with no window. A window cut short by that cap does not pass. The scene is checked against the
frozen instance before the agent is served; a mismatch is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 8 GiB | 1024 | 4 GiB | — |
| verifier (as `main`) | 4 | 5 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Others
The frozen scene is entry 0 of RoboWits' `eval_dataset_50/01.json` (RoboWits task
`robowits/01-align-blocks-v0`).

## License
RoboWits ([UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ `9cc30ae`) is MIT-licensed,
as declared in its `pyproject.toml`. Genesis 0.4.7 is under the Apache License 2.0, and RoboWits' asset bundle
(`XHRlyb2001/RoboWits_assets`) also under Apache-2.0. Most families also load BlenderKit models. BlenderKit licenses
each model to the account that downloads it, and these models may not be redistributed, so they are not in the image
or the repository. Users fetch them with their own BlenderKit key, or use the encrypted research bundle, whose terms
allow **non-commercial academic research only** (`images/robowits/NOTICE`).
