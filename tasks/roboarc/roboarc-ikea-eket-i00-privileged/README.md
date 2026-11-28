# RoboARC · EKET cabinet (privileged)

| | |
|---|---|
| Task ID | `roboarc-ikea-eket-i00-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Two 7-DoF Franka Panda arms, each with the Panda hand (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `ikea_eket`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Build the EKET cabinet frame from the five panels on the table: slide the side panel next to the top panel into the top
panel first, then the other side panel, then the back panel into its grooves, and last the bottom panel onto the sides.
Leave the cabinet standing on the table on its own. Then let go of everything and move both arms clear.

## Success criteria
Success needs all of these:
- The seven operations happen in this order, each measured against the top panel: side A (the side panel that starts
  next to the top panel) entry and slide, side B entry and slide, back slide, bottom entry and slide. Each one must
  reach its goal pose within the scene's gates (goal error 0.25 to 0.8 mm, angle 0.1 to 1 degree, nearly at rest, with
  contact with its counterpart panels).
- The four frame joints (side A and side B to the top, the bottom to both sides) are latched, and the five panels are
  finite.
- At the end the panels are released (no robot contact, no applied force), rest on the table (at least one panel
  touches the table top, none touches the floor) and move slower than 0.01 m/s and 0.05 rad/s.
- At the end every panel, the back included (it has no frame joint), is still in its assembled place: within 10 mm and
  2 degrees of its goal pose relative to the top panel (the benchmark's end-pose rule, `rcb_ikea.END_POSE_RULES`).
- The two side panels are the same part, so either may take side A's place; the other is then side B.

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
- more than 476,000 rows.

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
