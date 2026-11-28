# RoboARC · IKEA 365+ serving stand (privileged)

| | |
|---|---|
| Task ID | `roboarc-ikea-ikea365-i00-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Two 7-DoF Franka Panda arms, each with the Panda hand (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `ikea_ikea365`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Rebuild the IKEA 365+ serving stand: take the screw out of member A and set it down by itself, away from both members,
lay member B across member A, and screw the screw back in through both members until it seats. After that, lift the
stand about a hand's width off the bench, turn it upside down in the air, set it down and put the bowl on it. Then let
go of everything and move both arms clear.

## Success criteria
Success needs all of these:
- The seven operations are accepted in this order: remove the screw, park the screw, cross the members, return the
  screw, reinstall the screw, turn the stand, place the bowl.
- At the end the screw is retained in member A and aligned with its seated pose relative to both members, and member B
  is retained and aligned with member A (gates: axial 0.1 mm, lateral 0.6 mm, axis 1.5 degrees; member B may be rotated
  180 degrees).
- Released and settled: no robot contact with any part, every part slower than 0.025 m/s, the bench carries the parts;
  the bowl touches the members (more than 0.1 N) and member A is turned over (its z axis pointing down).
- A support probe on a copy of the final state: the bench must carry the whole weight, and the weight plus a 2 N
  downward test load on member A (the grader applies it; it never acts during the episode), with the arms holding their
  last commands.

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
- more than 495,000 rows.

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
