# RoboARC · rope_threading (standard)

| | |
|---|---|
| Task ID | `roboarc-rope-threading-08-i01-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | ALOHA 2: two 6-DoF ViperX 300 s arms with parallel-jaw grippers (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `rope_threading`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Thread the rope, from its end that started farther from the rings, through the cyan grommet in the wall (G1), then the
green ring (A), then the purple grommet in the wall (G2), then the amber ring (T), then the red grommet in the wall
(G3), then the cyan ring (C), in that order, each the way given below.

## Success criteria
Success needs all of these:
- The rope goes through the holes in the order the task gives, counted from its material start, each in this
  direction: cyan grommet in the wall (G1): cross toward the side containing the cyan ring (C); green ring (A): cross
  away from the side containing the cyan ring (C); purple grommet in the wall (G2): cross toward the side containing
  the amber ring (T); amber ring (T): cross away from the side containing the purple grommet in the wall (G2); red
  grommet in the wall (G3): cross toward the side containing the green ring (A); cyan ring (C): cross away from the
  side containing the green ring (A). A crossing in the other direction does not count.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full
  rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each
  ring's thickness, not just its middle plane.
- Keep every rope point at or below 10 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Confirmation window: all of these conditions hold together for at least 0.5 s of simulated time. If one stops
  holding, the window starts again.

How the grader measures it:
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the
  episode ends as an infrastructure error, not the agent's failure, unless an arm was forcing (even for one tick)
  within the 0.25 s before it: then it is the agent's failure (forced_breakdown: what broke and what forced it).
- Sizes (rope radius 4 mm): G1: inner radius 40 mm, tube radius 6 mm, centreline passage radius 36.9 mm on the middle
  plane and 39.2 mm on the two tube-offset planes; A: inner radius 35 mm, tube radius 6 mm, centreline passage radius
  31.9 mm on the middle plane and 34.2 mm on the two tube-offset planes; G2: inner radius 40 mm, tube radius 6 mm,
  centreline passage radius 36.9 mm on the middle plane and 39.2 mm on the two tube-offset planes; T: inner radius 35
  mm, tube radius 6 mm, centreline passage radius 31.9 mm on the middle plane and 34.2 mm on the two tube-offset
  planes; G3: inner radius 40 mm, tube radius 6 mm, centreline passage radius 36.9 mm on the middle plane and 39.2 mm
  on the two tube-offset planes; C: inner radius 35 mm, tube radius 6 mm, centreline passage radius 31.9 mm on the
  middle plane and 34.2 mm on the two tube-offset planes.
- Aperture check: round_ring, compression allowance 1 mm. This allowance changes the geometric passage test; the
  collision geometry stays as declared.
- The material start is the rope end that is farther from the rings at the start.
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

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
| `main` (the agent's) | 4 | 16 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 9 GiB | 1024 | 4 GiB | — |
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
