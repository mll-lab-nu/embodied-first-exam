# RoboARC · fiber_bundling (privileged)

| | |
|---|---|
| Task ID | `roboarc-fiber-bundling-04-i01-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Franka Panda 7-DoF arm with a Robotiq 2F-85 parallel gripper (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `fiber_bundling`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Feed every fine fiber, tip first, and the front of the sheath through the fixed copper ring, touching only the thick
sheath with the gripper. Leave the rear terminal anchored where it is.

## Success criteria
Success needs all of these:
- Pass every fiber tip first, then successive material points through to its root. The actual crossing history must be
  observed; placing fibers on the far side or passing only the tips is not completion.
- All fiber points must finish beyond the exit side of the ring tube, allowing for fiber thickness. The branching face
  of the front sheath must also pass through and clear the tube with its full thickness. The fixed rear terminal must
  remain anchored and does not pass through.
- Keep the angle between every pair of adjacent fiber segments at most 60 degrees in the final configuration.
- Touch and grasp only the thick sheath with the gripper. Keep the completed passage valid through confirmation;
  holding is allowed, with no separate release or speed threshold.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Sizes: ring inner radius 13.5 mm, ring tube radius 4 mm; 8 fibers of radius 1.2 mm; sheath radius 12 mm.
- Each fiber is tracked at 11 points from tip to root. A point counts when it crosses the ring's plane less than 17.48
  mm from the ring's axis, in tip-to-root order; a crossing out of order or outside that radius resets that point and
  every point behind it, and crossing back loses the credit.
- At the end every fiber point must be more than 5.2 mm past the ring's plane (tube + fiber radius) and the centre of
  the sheath's front face more than 16 mm past it (tube + sheath radius). The exit side is the side opposite to where
  the fibers start.
- The failure counts contact between a fine fiber and the gripper (fingers and hand, housing included); arm links
  touching a fiber do not count. Contact is sampled at all 4 solver substeps of every tick; if any tick since the
  start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

Failures:
- Any gripper touch of a fine fiber at any time ends the episode in failure, including a brief or zero-force touch.
- A fiber link falling more than 100 mm below the tabletop ends the episode in failure.

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
- more than 90,000 rows.

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
