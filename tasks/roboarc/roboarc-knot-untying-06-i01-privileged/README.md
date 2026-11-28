# RoboARC · knot_untying (privileged)

| | |
|---|---|
| Task ID | `roboarc-knot-untying-06-i01-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | ALOHA 2: two 6-DoF ViperX 300 s arms with parallel-jaw grippers (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `knot_untying`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Untie the rope and lay it out flat on the table so that, seen from above, it nowhere crosses or overlaps itself. One end
is clamped to the table under a staple and stays clamped. Then let go of it and move both arms clear of it.

## Success criteria
Success needs all of these:
- Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must
  be separated by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.
- Keep the entire rope close to the tabletop: no point more than 1 mm below it, and no point higher than one rope
  diameter plus 3 mm above it.
- Release all target parts and disengage any assisted grasp. Keep at least 1 mm of verified clearance between the rope
  and grippers or other robot links that can move. World-fixed bases may touch the rope normally. Interior overlap
  with any robot part is forbidden; ambiguous bounding-volume overlaps require a native-solid geometry check.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement
  from the start of confirmation at most 1 mm.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the
  episode ends as an infrastructure error, not the agent's failure, unless an arm was forcing (even for one tick)
  within the 0.25 s before it: then it is the agent's failure (forced_breakdown: what broke and what forced it).
- The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.
- "Nonlocal" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least 8 mm
  apart in the top view. Closer parts are exempt, but an actual crossing always counts.
- The release check bounds the rope's volume mesh (carried rigidly by its capsule links), element by element, against
  the robot's collision geometries and decides the close ones with the exact solids: every robot part that can move
  (grippers, arm links) needs at least 1 mm of clearance from the rope; a world-fixed base may touch it. An overlap
  with the interior of any robot part means the release is not certified: no success while it lasts, never a failure.
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

The verifier, in a separate sandbox without network, replays `/app/output/trajectory.npz` once, open-loop, in a fresh
process from its own copy of the frozen start.

The rows run in order, one per control step, with the instance's own thresholds. The replay stops at the first success
or failure: a success is the conditions above holding for the whole confirmation window, and the rows after it are not
run. If the rows end first, the trajectory scores 0. A success that the verifier's 2 s hold of the last targets after
the rows reaches is not credited either.

A missing file scores 0. So does an invalid one:
- not a readable `.npz` file;
- no `actions` array of shape (T, action dimension) with numeric, finite values and T at least 1;
- a `task` entry other than the task's family key;
- an `action_layout` entry other than the frozen instance's;
- more than 31,000 rows.

Before the replay the verifier checks the rebuilt scene against the task's runtime binding (its files and its initial
state); a mismatch is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 7 | 23 GiB | 1024 | 4 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 4 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).

## License
RoboARC ([mll-lab-nu/RoboARC](https://github.com/mll-lab-nu/RoboARC) @ `153eb8c`) is released under the MIT License
(Copyright (c) 2026 The RoboARC authors). The robot models are MuJoCo Menagerie's: ALOHA 2 (BSD-3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0) and Robotiq 2F-85 (BSD-2-Clause, ROS-Industrial). The furniture part
meshes of the furniture-assembly scenes are CC BY 4.0 (Hugging Face dataset `MLL-Lab/embodied-first-exam-public`,
`ikea-mujoco/`). The simulator is MuJoCo 3.14.0 (Apache License 2.0). RGB images are rendered with Nyx (`gs-nyx`), used
in the images with its owners' permission; the studio lighting is a CC0 HDRI from Poly Haven. Puzzle designs modelled
after Hanayama's Huzzle Cast puzzles and the IKEA product names and designs are used with the owners' permission. No
non-commercial terms apply.
