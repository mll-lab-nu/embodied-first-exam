# iSpatialGym · make the scene look like a picture (privileged)

| | |
|---|---|
| Task ID | `ispatialgym-configuration-matching-block-design-i00-privileged` |
| Benchmark | [iSpatialGym](https://github.com/kmy17518/iSpatialGym) (iSpatialGym Authors, 2026), upstream `kmy17518/iSpatialGym@fddcf75` |
| Robot | Galaxea R1 Pro mobile bimanual manipulator (holonomic wheeled base, 4-joint trunk, two 7-joint arms with parallel-jaw grippers) |
| Mode | privileged |
| Instance | `configuration_matching_block_design`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Make the scene look like the goal image /app/goal.png, the head camera's view once the task is done; the robot itself
does not have to match it.

## Success criteria
Each of the four toy dice is on the tray (`ontop`), and no gripper holds a die or the tray. The dice are
interchangeable: upstream matches each die to one die place of the goal, the matching that fits the layout best, and the
tray has its own place. Each die and the tray is within 9 cm of its place's target position and within 0.30 rad of
that place's target orientation. For every pair among the five (10 pairs), the pose of one relative to the other is within 3 cm and
0.15 rad of the target relative pose. The robot, the four dice and the tray are the objects that must be at rest.

Success is iSpatialGym's own geometric success with settle-eval on, as its evaluation judges a policy run. On some
control step the conditions above have held on that step and on each of the 44 steps before it (45 consecutive control
steps, 1.5 s at 30 Hz). On that step the robot and every object named above are also at rest: over the last 45 steps
the object's root pose stayed within 2 mm and 5 mrad of where it was at the first of them, and each of its joints within
5 mrad (5 mm for a sliding joint). For the robot this covers its base pose and all its joints.

The graded file is `/app/output/trajectory.npz`: an array `actions` of shape (T, 23), at most 8,298 rows, one
row per 30 Hz control step. The verifier replays it once, open-loop, in a fresh process from the frozen start. The task
succeeds if the success above is reached at some control step of that replay; the replay stops there. Nothing runs after
the last row, so a trajectory whose rows end before the success is reached scores 0. There is no fall rule: a robot
that has tipped over does not end the replay.

A missing file, a file without `actions`, another shape, a non-numeric array or more than 8,298 rows scores 0.
A row that is not 23 finite numbers stops the replay and scores 0. A replay that gives no result or runs out of its
time limit, or a frozen start that does not rebuild as recorded, is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 12 | 38 GiB | 4096 | 22 GiB | 10 GiB |
| verifier (as `main`) | 12 | 38 GiB | no cap | 22 GiB | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
iSpatialGym ([kmy17518/iSpatialGym](https://github.com/kmy17518/iSpatialGym) @ `fddcf75`) and its evaluation data
(Hugging Face `kmy17518/ispatialgym-eval-data`, revision `v1.0`, which holds the goal images) are released under the MIT
License. Its BEHAVIOR-1K fork (OmniGibson and bddl) is MIT. The scenes, objects and robot assets are the BEHAVIOR Data
Bundle, under its End User License Agreement: **non-commercial academic research use only (NC)**, no redistribution;
the dataset is mounted at run time and never copied into an image or this repository. NVIDIA Isaac Sim 5.1 and
Omniverse Kit are proprietary; building the simulator image accepts NVIDIA's licence terms.
