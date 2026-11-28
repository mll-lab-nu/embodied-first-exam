# RoboARC · VESKEN shelf unit (privileged)

| | |
|---|---|
| Task ID | `roboarc-ikea-vesken-i00-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Two 7-DoF Franka Panda arms, each with the Panda hand (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `ikea_vesken`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Build the VESKEN shelf unit: snap the four feet into the bottom tray from below, then four columns into the bottom tray,
the second tray onto them, four columns and a tray for each of the two upper levels, and last the four caps into the top
tray. Then let go of everything and move both arms clear.

## Success criteria
Success needs all of these:
- All 23 snap connections are made in the source order (each depends on the previous: feet, columns, tray, columns,
  tray, columns, tray, caps) and, at the end, each connector is within its gates (axial gap 0.6 mm, lateral 0.8 mm,
  outward-axis tilt 2 degrees). Identical parts may take any of their places, one part per place.
- The feet stand on the bench (summed vertical contact force above 0.1 N) and the bottom tray is within 3 degrees of
  its upright, unrotated assembly orientation.
- No arm link touches any furniture part or jaw at the end.

Also required, at the end: no robot link touches any part; every part is at rest (at most 0.01 m/s and 0.05 rad/s);
and the simulation never broke down at any time (no non-finite state, no MuJoCo BADQACC / BADQPOS / BADQVEL warning, no
contact of a part deeper than 10 mm).

The verifier, in a separate sandbox without network, replays `/app/output/trajectory.npz` once, open-loop, in a fresh
process from its own copy of the frozen start.

Every row runs, one per control step (4 physics steps of the scene). The checks above are made on the state after the
last row, and again after the verifier holds the last row for 1.0 s more; both must pass. A replay in which the
simulator crashes, or the scene's code or MuJoCo raises an error, is a breakdown and scores 0.

A missing file scores 0. So does an invalid one:
- not a readable `.npz` archive of at most 64 members;
- no `ctrl` array of shape (N, number of actuators) with numeric, finite values and N at least 1;
- a `substeps` entry other than 4, or a `timestep` entry other than the scene's;
- more than 990,000 rows.

Before the replay the verifier checks the rebuilt scene against the task's runtime binding (its files and its initial
state); a mismatch is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
RoboARC ([mll-lab-nu/RoboARC](https://github.com/mll-lab-nu/RoboARC) @ `153eb8c`) is released under the MIT License
(Copyright (c) 2026 The RoboARC authors). The robot models are MuJoCo Menagerie's: ALOHA 2 (BSD-3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0) and Robotiq 2F-85 (BSD-2-Clause, ROS-Industrial). The furniture part
meshes of the furniture-assembly scenes are CC BY 4.0 (Hugging Face dataset `MLL-Lab/embodied-first-exam-public`,
`ikea-mujoco/`). The simulator is MuJoCo 3.14.0 (Apache License 2.0). RGB images are rendered with Nyx (`gs-nyx`), used
in the images with its owners' permission; the studio lighting is a CC0 HDRI from Poly Haven. Puzzle designs modelled
after Hanayama's Huzzle Cast puzzles and the IKEA product names and designs are used with the owners' permission. No
non-commercial terms apply.
