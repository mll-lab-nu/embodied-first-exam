# RoboARC · EKET cabinet (standard)

| | |
|---|---|
| Task ID | `roboarc-ikea-eket-i00-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Two 7-DoF Franka Panda arms, each with the Panda hand (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `ikea_eket`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Build the EKET cabinet frame from the five panels on the table: slide the side panel next to the top panel into the top
panel first, then the other side panel, then the back panel into its grooves, and last the bottom panel onto the sides.
Leave the cabinet standing on the table on its own. Then let go of everything and move both arms clear.

## Success criteria
Success needs all of these:
- The seven operations happen in this order, each measured against the top panel: side A (the side panel that starts
  next to the top panel) entry and slide, side B entry and slide, back slide, bottom entry and slide. Each one must
  reach its goal pose within the scene's gates (goal error 0.25 to 0.8 mm, angle 0.1 to 1 degree, nearly at rest, with
  contact with its counterpart panels).
- The four frame joints (side A and side B to the top, the bottom to both sides) are latched, and the five panels are
  finite.
- At the end the panels are released (no robot contact, no applied force), rest on the table (at least one panel
  touches the table top, none touches the floor) and move slower than 0.01 m/s and 0.05 rad/s.
- At the end every panel, the back included (it has no frame joint), is still in its assembled place: within 10 mm and
  2 degrees of its goal pose relative to the top panel (the benchmark's end-pose rule, `rcb_ikea.END_POSE_RULES`).
- The two side panels are the same part, so either may take side A's place; the other is then side B.

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
