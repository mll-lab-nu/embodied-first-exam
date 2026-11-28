# RoboARC · GLADOM tray table (standard)

| | |
|---|---|
| Task ID | `roboarc-ikea-gladom-i00-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Two 7-DoF Franka Panda arms, each with the Panda hand (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `ikea_gladom`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Build the GLADOM tray table: fit frame B crosswise into frame A, drive in the long screw and the bottom screw, put on
the ring and drive its two screws, and set the tray on the ring. Then let go of everything and move both arms clear.

## Success criteria
Success needs all of these:
- The retention joints of frame B, the ring and the four screws are all latched.
- Every part except frame A is at its assembled pose relative to frame A: gap within 0.8 mm along frame A's z axis,
  lateral within 1 mm, tilt within 2 degrees (screws: axis tilt; frame B and the ring may be rotated 180 degrees, the
  tray 7.5 degrees), relative speed below 0.025 m/s. The three short screws are the same part: any of them may take
  the bottom nut or either ring receiver, one screw per place.
- The tray is free (never jointed) and supported by the ring (contact above 0.01 N in at least 12 of 36 samples over the
  last 0.15 s, and above 0.01 N on average over them); no robot contact with any furniture part.
- All of the above hold continuously for 0.15 s.

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
