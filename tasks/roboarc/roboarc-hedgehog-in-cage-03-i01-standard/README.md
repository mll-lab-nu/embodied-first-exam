# RoboARC · hedgehog_in_cage (standard)

| | |
|---|---|
| Task ID | `roboarc-hedgehog-in-cage-03-i01-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Franka Panda 7-DoF arm with a Robotiq 2F-85 parallel gripper (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `hedgehog_in_cage`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Take the hedgehog ball out of the cage and put all of it, every spike included, inside the green dashed goal square.
Leave the cage parts behind, no closer to the goal than they were at the start.

## Success criteria
Success needs all of these:
- Put every part of the whole hedgehog ball, including every spike inside the fixed goal volume, leaving at least 1 mm
  inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may
  remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height.
  It need not touch the table. The goal volume extends 236.877 mm above the tabletop.
- Keep all cage components, and every other remaining puzzle component, entirely on the system side of the fixed
  separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target
  with the gripper is allowed; release is not required.
- Confirmation window: all of these conditions hold together for at least 2 s of simulated time. If one stops holding,
  the window starts again.

How the grader measures it:
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the
  region's border runs along the middle of the line); it encloses a 244.9 mm x 244.9 mm square. Every point counts:
  for a rigid part every vertex of its visual and collision meshes.
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point
  of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30
  mm beyond it. The remaining components here are fixed.
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step).
  "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active
  assisted grasp), the other finger is back at the non-held limits in the same tick. The cage is fixed, so finger
  contact with it is never held (always the non-held limits).
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

The graded episode is the one live episode in the `sim` service; nothing is replayed, and there is no reset. The
episode ends when the agent sends `/finish` or when the agent's session ends (at the latest after 3 h, which the
service counts from the agent's first request), or after 200,000 control steps (holds count).

These ends are judged on the end state. The conditions above must hold when the episode ends and keep holding, with
the last targets held, until they have held for the whole confirmation window; the time they already held before the
end counts. Meeting them earlier in the episode does not count, and the service never reports success while the
episode runs. A task failure (above) ends the episode at once and scores 0, even after a success; so does a simulator
error caused by the agent's actions.

Before the agent is served, the service checks the scene against the frozen instance; a mismatch is an infrastructure
failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 4096 | no GPU | 10 GiB |
| `sim` | 4 | 9 GiB | 1024 | 4 GiB | — |
| verifier (as `main`) | 4 | 16 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
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
