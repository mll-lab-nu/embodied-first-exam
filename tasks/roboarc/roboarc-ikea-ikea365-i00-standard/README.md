# RoboARC · IKEA 365+ serving stand (standard)

| | |
|---|---|
| Task ID | `roboarc-ikea-ikea365-i00-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Two 7-DoF Franka Panda arms, each with the Panda hand (MuJoCo Menagerie) |
| Mode | standard |
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

The graded episode is the one live episode in the `sim` service; nothing is replayed, and there is no reset. The
episode ends when the agent sends `/finish` or when the agent's session ends (at the latest after 3 h, which the
service counts from the agent's first request).

An end at `/finish` or at the session's end is judged on the end state, by the checks above: on the live state, then
again on a copy with the last row held for 1.0 s more; both must pass. Ordered steps count as they happened during the
episode; everything else must hold at the end. The service never reports success while the episode runs. A simulator
breakdown or a simulator error ends the episode at once and scores 0, even after a success.

Before the agent is served, the service checks the scene against the frozen instance; a mismatch is an infrastructure
failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 7 GiB | 1024 | 4 GiB | — |
| verifier | 2 | 2 GiB | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: RTX 4090 24GB / L4 24GB (an NVIDIA GPU with Vulkan and EGL).

## License
RoboARC ([mll-lab-nu/RoboARC](https://github.com/mll-lab-nu/RoboARC) @ `153eb8c`) is released under the MIT License
(Copyright (c) 2026 The RoboARC authors). The robot models are MuJoCo Menagerie's: ALOHA 2 (BSD-3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0) and Robotiq 2F-85 (BSD-2-Clause, ROS-Industrial). The furniture part
meshes of the furniture-assembly scenes are CC BY 4.0 (Hugging Face dataset `MLL-Lab/embodied-first-exam-public`,
`ikea-mujoco/`). The simulator is MuJoCo 3.14.0 (Apache License 2.0). RGB images are rendered with Nyx (`gs-nyx`), used
in the images with its owners' permission; the studio lighting is a CC0 HDRI from Poly Haven. Puzzle designs modelled
after Hanayama's Huzzle Cast puzzles and the IKEA product names and designs are used with the owners' permission. No
non-commercial terms apply.
