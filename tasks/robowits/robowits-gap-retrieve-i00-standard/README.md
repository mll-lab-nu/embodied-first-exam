# RoboWits · gap_retrieve (standard)

| | |
|---|---|
| Task ID | `robowits-gap-retrieve-i00-standard` |
| Benchmark | [RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) (Lin et al., 2026), upstream `UMass-Embodied-AGI/RoboWits@9cc30ae` |
| Robot | Bimanual Marvin: two 7-DoF arms with Pika parallel grippers |
| Mode | standard |
| Instance | `gap_retrieve`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Put the lemon on the green target area.

## Success criteria
The goal: the lemon's bounding-box bottom is within 2 cm of the table top. The footprints of the lemon and of the
green target area lie inside the table area. At least 80 % of the lemon's footprint lies over the target area's
footprint. Neither gripper's end-effector point is inside the lemon's bounding box grown by 3 cm on every side. No
part of the robot touches the lemon. Graded object: the lemon.

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
The frozen scene is entry 0 of RoboWits' `eval_dataset_50/03.json` (RoboWits task
`robowits/03-gap-retrieve-v0`).

## License
RoboWits ([UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ `9cc30ae`) is MIT-licensed,
as declared in its `pyproject.toml`. Genesis 0.4.7 is under the Apache License 2.0, and RoboWits' asset bundle
(`XHRlyb2001/RoboWits_assets`) also under Apache-2.0. Most families also load BlenderKit models. BlenderKit licenses
each model to the account that downloads it, and these models may not be redistributed, so they are not in the image
or the repository. Users fetch them with their own BlenderKit key, or use the encrypted research bundle, whose terms
allow **non-commercial academic research only** (`images/robowits/NOTICE`).
