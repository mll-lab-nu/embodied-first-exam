# RoboARC · lock_picking (privileged)

| | |
|---|---|
| Task ID | `roboarc-lock-picking-04-i01-privileged` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Franka Panda 7-DoF arm with a Robotiq 2F-85 parallel gripper (MuJoCo Menagerie) |
| Mode | privileged |
| Instance | `lock_picking`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Pick up the two-tab key from its rest and push it through all three rotor plates and the END plate, passing its tabs
only through the plates' slots.

## Success criteria
Success needs all of these:
- Keep the finite-length shaft passing through the full thickness of all four plates at once, facing the insertion
  direction. Reaching END with only the shaft tip is insufficient.
- The rear edge of the leading tab must clear the outer face of END by at least 1 mm.
- Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all four bores. The
  radial numerical contact tolerance is 0.01 mm; the shaft may not pass through solid plate material.
- Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt,
  not just its rotation about the shaft.
- Keep limited-travel rotor pins within their physical slot bounds (angular tolerance 0.5 degrees).
- The key may stay held. Release and zero velocity are not required; all insertion and clearance conditions must
  remain satisfied throughout confirmation.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Sizes: bore radius 7.5 mm, shaft radius 6.5 mm. At each of the 8 plate faces (three 10 mm rotor plates and END, 120
  mm apart), the shaft axis' distance from the bore axis plus 6.5 mm / cos(tilt) may exceed 7.5 mm by at most 0.01 mm:
  about 1.01 mm of offset when the key is straight, which over the stack allows only about 0.31 degrees of tilt.
- The shaft reaches from 425 mm behind the leading tab to 15 mm in front of it; all 8 plate faces must lie within that
  length.
- Tabs: half-width 4 degrees; the leading tab reaches radius 36 mm and the second tab, 120 mm behind it, 22 mm. Slots:
  half-width 6 degrees, reaching radius 45 mm (deep) or 28 mm (shallow). A tab that overlaps a plate must sit inside
  one of that plate's slots that reaches beyond the tab, with an angular margin of at least asin(axis offset / tab
  radius) + the tilt.
- Rotor stops (from each rotor's start angle, seen from the side the key enters, looking along the key toward END;
  rotor 1 is the first plate the key reaches): rotor 1 38 degrees counterclockwise and 2 degrees clockwise; rotor 2 38
  degrees counterclockwise and 2 degrees clockwise; rotor 3 127 degrees counterclockwise and 7 degrees clockwise.
  Going more than 0.5 degrees beyond a stop ends the episode.
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

Failures:
- A limited-travel rotor exceeding its allowed bounds ends the episode in failure.
- The key falling more than 100 mm below the tabletop ends the episode in failure.

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
- more than 163,000 rows.

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
