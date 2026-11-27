# KinDER · scoop-pour (privileged)

| | |
|---|---|
| Task ID | `kinder-scoop-pour-i01-privileged` |
| Benchmark | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (Huang et al., 2026), upstream `Princeton-Robot-Planning-and-Learning/kindergarden@5b2dbac` |
| Robot | TidyBot++ mobile manipulator: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper |
| Mode | privileged |
| Instance | `scoop-pour`, seed 0 |
| Time limit | 30 min |
| Reference solution | None |

## Task
Move all 50 small cubes from the yellow bin into the green bin. There is a scoop you can use.

## Success criteria
Goal check (KinDER `ScoopPour3D-o50`): the centre of every one of the 50 cubes lies inside the green bin's goal
region, a box 0.37 m by 0.22 m centred in the bin, from 3 cm to 5.5 cm above the bin's base frame, so a cube resting
on the rim or stacked high does not count. Nothing else is checked: the scoop and the yellow bin may be anywhere.

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
