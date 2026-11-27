# RoboARC · cast_coil (standard)

| | |
|---|---|
| Task ID | `roboarc-cast-coil-05-i01-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | ALOHA 2: two 6-DoF ViperX 300 s arms with parallel-jaw grippers (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `cast_coil`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Fit the gold and silver pieces fully together, interlocked the way they are made to fit, resting on the table. Then let
go of them and move both arms clear of them.

## Success criteria
Success needs all of these:
- Align the pieces' matching assembly frames with relative position error below 1 mm and relative angular error below
  0.02 rad.
- The bottom of at least one piece must be within 3 mm of the tabletop. Neither piece may extend more than 1 mm below
  it, and each piece must overlap the tabletop horizontally.
- Keep both pieces' linear speeds below 1 mm/s and angular speeds below 0.02 rad/s. Merely touching or gripping them
  is not completion.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of
  verified clearance from every target part; opening the fingers while still touching or surrounding the target is
  insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement
  from the start of confirmation at most 1 mm. Each target rigid body's angular speed must be at most 0.02 rad/s and
  angular drift at most 0.02 rad.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step).
  "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active
  assisted grasp), the other finger is back at the non-held limits in the same tick.
- Simulator breakdown (a non-finite state or a task contact deeper than 10 mm): the episode ends as an infrastructure
  error, not the agent's failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it
  is the agent's failure (forced_breakdown: what broke and what forced it).
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the
  whole robot (every link of both arms) and one around each collision geometry of the pieces, so the true gap usually
  has to be larger than 5 mm.
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
