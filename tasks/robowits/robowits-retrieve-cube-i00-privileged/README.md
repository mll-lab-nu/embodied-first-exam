# RoboWits · retrieve_cube (privileged)

| | |
|---|---|
| Task ID | `robowits-retrieve-cube-i00-privileged` |
| Benchmark | [RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) (Lin et al., 2026), upstream `UMass-Embodied-AGI/RoboWits@9cc30ae` |
| Robot | Bimanual Marvin: two 7-DoF arms with Pika parallel grippers |
| Mode | privileged |
| Instance | `retrieve_cube`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Take the small cube out of the container and put it on the green target area.

## Success criteria
The goal: the cube's bounding-box bottom is between 1 cm below and 3 cm above the table top. The footprints of the
cube and of the green target area lie inside the table area enlarged by 1 cm on every side. Less than 50 % of the
cube's footprint lies over the container's footprint, and at least 50 % of it lies over the target area's. No part of
the robot touches the cube. Graded object: the cube.

The verifier, in a separate sandbox without network, replays `/app/output/trajectory.npz` once in a fresh process
from its own copy of the frozen instance: a reset, then the rows open-loop, one per 1/30 s control step. A settle
window follows the last row. The robot holds the last row's joint targets for 30 control steps (1 s), and nothing is
checked. For 60 more control steps (2 s) the goal must then hold at every 6th step and at the last one. Through those
60 steps the set of graded objects must not change, and no graded object may move more than 2 mm from where it was
when they began. The task scores 1 only if the window passes.

Where the goal names the table area, it is the world-frame rectangle 0.21 ≤ x ≤ 1.00 m, −0.69 ≤ y ≤ 0.69 m;
the table top is at z = 0.76 m.

A missing file scores 0, and so does an invalid one. Invalid means: not a readable `.npz`, no `task` or `actions`
entry, an entry over 256 MB, a `task` other than this family, `actions` that are not finite numbers of shape (T, 16),
or T over 200,000. The rows and the window share the cap of 200,000 control steps; a window cut short by the cap does
not pass. The rebuilt scene must match the frozen instance: the same state hash, or every object within 2 mm and 0.02
(quaternion components) and every joint within 0.002 rad of the recorded pose. A scene that does not match, or does
not build, is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 13 GiB | 1024 | 5 GiB | 10 GiB |
| `blenderkit` | 1 | 4 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | 5 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Others
The frozen scene is entry 0 of RoboWits' `eval_dataset_50/02.json` (RoboWits task
`robowits/02-retrieve-cube-v0`).

## License
RoboWits ([UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ `9cc30ae`) is MIT-licensed,
as declared in its `pyproject.toml`. Genesis 0.4.7 is under the Apache License 2.0, and RoboWits' asset bundle
(`XHRlyb2001/RoboWits_assets`) also under Apache-2.0. Most families also load BlenderKit models. BlenderKit licenses
each model to the account that downloads it, and these models may not be redistributed, so they are not in the image
or the repository. Users fetch them with their own BlenderKit key, or use the encrypted research bundle, whose terms
allow **non-commercial academic research only** (`images/robowits/NOTICE`).
