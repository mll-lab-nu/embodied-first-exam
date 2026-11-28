# RoboWits · hold_cup (privileged)

| | |
|---|---|
| Task ID | `robowits-hold-cup-i00-privileged` |
| Benchmark | [RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) (Lin et al., 2026), upstream `UMass-Embodied-AGI/RoboWits@9cc30ae` |
| Robot | Bimanual Marvin: two 7-DoF arms with Pika parallel grippers |
| Mode | privileged |
| Instance | `hold_cup`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Stand the cup upright on the green target area on the slope, so that it stays there without sliding down.

## Success criteria
The goal: at least 50 % of the cup's footprint lies over the green target area's footprint. The cup moves no faster
than 5 mm/s. Its roll and pitch angles are each within 20° of zero. Its footprint lies inside the table area. Neither
gripper's end-effector point is inside the cup's bounding box grown by 3 cm on every side. No part of the robot touches
the cup. Graded object: the cup.

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
or T over 200,000. The window runs past the cap of 200,000 control steps, so a trajectory of up to 200,000 rows gets
its full window. The rebuilt scene must match the frozen instance: the same state hash, or every object within 2 mm
and 0.02 (quaternion components) and every joint within 0.002 rad of the recorded pose. A scene that does not match,
or does not build, is an infrastructure error, not a score.

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
The frozen scene is entry 0 of RoboWits' `eval_dataset_50/09.json` (RoboWits task
`robowits/09-hold-cup-v0`).

## License
RoboWits ([UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ `9cc30ae`) is MIT-licensed,
as declared in its `pyproject.toml`. Genesis 0.4.7 is under the Apache License 2.0, and RoboWits' asset bundle
(`XHRlyb2001/RoboWits_assets`) also under Apache-2.0. Most families also load BlenderKit models. BlenderKit licenses
each model to the account that downloads it, and these models may not be redistributed, so they are not in the image
or the repository. Users fetch them with their own BlenderKit key, or use the encrypted research bundle, whose terms
allow **non-commercial academic research only** (`images/robowits/NOTICE`).
