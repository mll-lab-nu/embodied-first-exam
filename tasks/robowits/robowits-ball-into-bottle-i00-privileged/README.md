# RoboWits · ball_into_bottle (privileged)

| | |
|---|---|
| Task ID | `robowits-ball-into-bottle-i00-privileged` |
| Benchmark | [RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) (Lin et al., 2026), upstream `UMass-Embodied-AGI/RoboWits@9cc30ae` |
| Robot | Bimanual Marvin: two 7-DoF arms with Pika parallel grippers |
| Mode | privileged |
| Instance | `ball_into_bottle`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Move the small ball from the blue container down to the bottom of the red bottle.

## Success criteria
The goal: the small ball's centre, seen from above, lies inside the red bottle's footprint. The top of the ball is more
than 11 cm below the top of the bottle's bounding box. The bottom of the ball is more than 2 mm above the table top
and more than 2 mm above the bottom of the bottle's bounding box. The ball's radius here is half the smallest side of
its bounding box. Neither the ball's nor the bottle's bounding-box bottom is more than 5 cm below the table top. No
part of the robot touches the ball. Graded object: the ball.

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
The frozen scene is entry 0 of RoboWits' `eval_dataset_50/12.json` (RoboWits task
`robowits/12-ball-into-bottle-v0`).

The red bottle's base collides as a thin shell (about 3.5 mm) in the simulator. A ball that falls through it ends on
the table, and the goal then fails.

## License
RoboWits ([UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ `9cc30ae`) is MIT-licensed,
as declared in its `pyproject.toml`. Genesis 0.4.7 is under the Apache License 2.0, and RoboWits' asset bundle
(`XHRlyb2001/RoboWits_assets`) also under Apache-2.0. Most families also load BlenderKit models. BlenderKit licenses
each model to the account that downloads it, and these models may not be redistributed, so they are not in the image
or the repository. Users fetch them with their own BlenderKit key, or use the encrypted research bundle, whose terms
allow **non-commercial academic research only** (`images/robowits/NOTICE`).
