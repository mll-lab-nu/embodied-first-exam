# KinDER · sweep-into-drawer (privileged)

| | |
|---|---|
| Task ID | `kinder-sweep-into-drawer-i00-privileged` |
| Benchmark | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (Huang et al., 2026), upstream `Princeton-Robot-Planning-and-Learning/kindergarden@5b2dbac` |
| Robot | TidyBot++ mobile manipulator: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper |
| Mode | privileged |
| Instance | `sweep-into-drawer`, seed 0 |
| Time limit | 30 min |
| Reference solution | None |

## Task
Get the five small cubes on top of the kitchen island into the middle drawer of the island's top row. There is a wiper
you can use.

## Success criteria
Goal check (KinDER `SweepIntoDrawer3D-o5`): the centre of every one of the five cubes lies inside the goal region
of the middle drawer of the kitchen island's top row, a box inside the drawer that stops short of its left and right
walls. Nothing else is checked: the drawer may be left in any position, and the wiper anywhere.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: actions for this instance, one row
of 11 values per 10 Hz control step, each inside the action space's bounds. After the agent's session it is replayed
once, open-loop, from the frozen start (`tests/instance.json`) in a fresh process of a separate verifier container
without network. The task is passed if KinDER's goal check holds at any control step of the replay within the first
1,000 rows (100 s). The replay stops at that step; later rows are not run, and rows after the 1,000th never run. Only
the trajectory is scored (`gen.py` and `NOTES.md` are not). A missing file, a file for another instance, a wrong
shape, a non-finite value or a value outside the bounds scores 0. An error inside the grader is reported as
`grader_error` (infrastructure), not as a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 7 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
KinDER ([Princeton-Robot-Planning-and-Learning/kindergarden](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden)
@ `5b2dbac`) is released under the MIT License (copyright (c) 2025 Tom Silver). The lab scenes are MimicLabs
([Gatech-RL2/mimiclabs](https://github.com/Gatech-RL2/mimiclabs), MIT License), fetched by upstream's own download
script when the image is built. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
