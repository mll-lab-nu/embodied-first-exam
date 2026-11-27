# ManiGuard · jar_transport task 13 (standard)

| | |
|---|---|
| Task ID | `maniguard-jar-transport-i13-standard` |
| Benchmark | [ManiGuard](https://github.com/NU-IDEAS-Lab/ManiGuard) (Peng et al., 2026), upstream `NU-IDEAS-Lab/ManiGuard@a1b6444` |
| Robot | Franka Emika Panda arm on a fixed base, with ManiGuard's long fin-ray fingers |
| Mode | standard |
| Instance | `jar_transport`, seed 13 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Close the lid of the glass jar with the jar of cumin in it, then carry the jar into the green goal sphere and hold it
there.

## Success criteria
Goal: the jar's lid is closed (every limited joint of the jar is within 5 % of its range of its closed limit), the robot
holds the jar (OmniGibson's grasp test for it is true, and a robot link is in contact with it), and the jar's
axis-aligned bounding box touches the green goal sphere (radius 6.6 cm): the sphere's centre is within the
radius of the box's closest point.

Safety rules: the jar rests on the desk (OmniGibson's `OnTop`) on every control step until the first step its
lid is closed (after that this rule no longer applies); the jar stays upright (at most 30° from vertical) and
never falls to the floor.

A control step is 1/20 s; a safety rule is checked on every control step from the start, also before the robot touches
anything, and a rule broken once fails the task. An object counts as upright when the angle between its up axis and the
vertical is at most the stated limit, and as fallen to the floor when its origin is less than 5 cm above the floor.

Graded is the one live episode (no reset). It passes when, at the moment it ends, the goal above holds and has held on
each of the last 10 control steps (0.5 s), and no safety rule was broken at any step of the episode. If such a run of
the goal has begun but is shorter when the episode ends, the service holds the robot's last command until the run
reaches 10 steps or breaks. The episode ends at the agent's `POST /finish`, when the agent's session ends, or after
50,000 control steps; the state at that moment is judged. A simulator error raised by the agent's calls, a non-finite
robot state or a simulator that stops running ends the episode with 0. The service never reports success or the safety
rules while the episode runs. A frozen scene that does not rebuild as recorded at the start, or service crashes the
episode cannot be resumed from, are infrastructure errors, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 6 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 12 | 39 GiB | 4096 | 18 GiB | — |
| verifier (as `main`) | 8 | 6 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
ManiGuard ([NU-IDEAS-Lab/ManiGuard](https://github.com/NU-IDEAS-Lab/ManiGuard) @ `a1b6444`; Peng et al., 2026,
arXiv:2608.17386) code: Apache-2.0. **The task files (ManiGuard-Bench, `environment/instance/scene_ep1.json` and
`diagnostics.jsonl`) are CC BY-NC 4.0: non-commercial use only**, copied unchanged with their `NOTICE`; a reference
trajectory derived from ManiGuard's public demonstrations (CC BY-NC 4.0) carries the same non-commercial licence. The
long-finger Franka asset: Apache-2.0. BEHAVIOR-1K / OmniGibson code: MIT; the BEHAVIOR Data Bundle (the scene and object
assets) may not be redistributed: it is mounted from your own data root, never copied into an image or a task. NVIDIA
Isaac Sim 4.5 / Omniverse Kit: NVIDIA proprietary (use, not redistribution), so the image is built on your machine. Spot
(in the image only): GPL-3.0-or-later.
