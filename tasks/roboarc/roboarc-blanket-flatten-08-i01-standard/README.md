# RoboARC · blanket_flatten (standard)

| | |
|---|---|
| Task ID | `roboarc-blanket-flatten-08-i01-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | ALOHA 2: two 6-DoF ViperX 300 s arms with parallel-jaw grippers (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `blanket_flatten`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Unfold the blanket and spread it flat on the table, with no part folded over another and without stretching it. Then let
go of it and move both arms clear of it.

## Success criteria
Success needs all of these:
- Cover at least 95% of the blanket's unfolded material area in top-down projection. Overlapping layers count only
  once, holes do not count, and a large outer bounding box is insufficient.
- The sheet must lie flat on the tabletop, fully in contact with the table surface: keep every cloth point at most 30
  mm above the tabletop and no more than 8 mm below it.
- No material edge may stretch beyond 1.15 times its original length. Raised corners or pulling the blanket taut in
  the air do not count.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of
  verified clearance from every target part; opening the fingers while still touching or surrounding the target is
  insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 30 mm/s and its displacement
  from the start of confirmation at most 3 mm.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Simulator breakdown (a cloth particle faster than 20 m/s): the episode ends as an infrastructure error, not the
  agent's failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is the agent's
  failure (forced_breakdown: what broke and what forced it).
- The blanket is 0.6 m x 0.48 m (0.288 m^2), so the coverage needs at least 0.2736 m^2 of its area in the top view.
  Heights are measured at the cloth particles' centres.
- The release clearance is measured from one box around all cloth particles, grown by 8 mm: every robot collision box
  must stay at least 5 mm from it, i.e. at least 13 mm outside the cloth's bounding box, above its highest point too.
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

Failures:
- Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.

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
| `main` (the agent's) | 3 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 9 GiB | 1024 | 4 GiB | — |
| verifier (as `main`) | 3 | 4 GiB | no cap | no GPU | 10 GiB |

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
