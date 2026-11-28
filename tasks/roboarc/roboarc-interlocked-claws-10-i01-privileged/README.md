# RoboARC · interlocked_claws (privileged)

| | |
|---|---|
| Task ID | `roboarc-interlocked-claws-10-i01-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | ALOHA 2: two 6-DoF ViperX 300 s arms with parallel-jaw grippers (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `interlocked_claws`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Take the brown key out of the teal lock and put all of it inside the green dashed goal square. Leave the teal lock
behind, no closer to the goal than it was at the start.

## Success criteria
Success needs all of these:
- Put every part of the entire brown claw piece inside the fixed goal volume, leaving at least 1 mm inside its
  horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height.
  It need not touch the table. The goal volume extends 351.74 mm above the tabletop.
- Keep the other claw piece, and every other remaining puzzle component, entirely on the system side of the fixed
  separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target
  with the gripper is allowed; release is not required.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the
  region's border runs along the middle of the line); it encloses a 359.7 mm x 359.7 mm square. Every point counts:
  for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point
  of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30
  mm beyond it. The other claw piece is free to move (its speed is not checked), but no point of it may cross that
  plane.
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step).
  "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active
  assisted grasp), the other finger is back at the non-held limits in the same tick.
- Simulator breakdown (a non-finite state or a task contact deeper than 10 mm): the episode ends as an infrastructure
  error, not the agent's failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it
  is the agent's failure (forced_breakdown: what broke and what forced it).
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

Failures:
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Contact penetration never ends
  the episode by itself: a success with a task contact deeper than 3 mm, or deeper than 2 mm for at least 0.25 s (100
  consecutive physics ticks), is not credited automatically: it scores 0, is flagged for human review, and the
  evidence and frames are kept for a reviewer (for a finger contact with a held movable piece: 4 mm, or 2 mm for 0.25
  s; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that
  hand); a clean success is credited automatically. A task contact deeper than 10 mm is a simulator breakdown.

The verifier, in a separate sandbox without network, replays `/app/output/trajectory.npz` once, open-loop, in a fresh
process from its own copy of the frozen start.

The rows run in order, one per control step, with the instance's own thresholds. The replay stops at the first success
or failure: a success is the conditions above holding for the whole confirmation window, and the rows after it are not
run. If the rows end first, the trajectory scores 0.

A missing file scores 0. So does an invalid one:
- not a readable `.npz` file;
- no `actions` array of shape (T, action dimension) with numeric, finite values and T at least 1;
- a `task` entry other than the task's family key;
- an `action_layout` entry other than the frozen instance's;
- more than 173,000 rows.

Before the replay the verifier checks the rebuilt scene against the task's runtime binding (its files and its initial
state); a mismatch is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 30 GiB | 8192 | 12 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 12 GiB | no cap |

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
