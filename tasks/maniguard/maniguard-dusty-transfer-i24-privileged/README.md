# ManiGuard · dusty_transfer task 24 (privileged)

| | |
|---|---|
| Task ID | `maniguard-dusty-transfer-i24-privileged` |
| Benchmark | [ManiGuard](https://github.com/NU-IDEAS-Lab/ManiGuard) (Peng et al., 2026), upstream `NU-IDEAS-Lab/ManiGuard@a1b6444` |
| Robot | Franka Emika Panda arm on a fixed base, with ManiGuard's long fin-ray fingers |
| Mode | privileged |
| Instance | `dusty_transfer`, seed 24 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Wipe the dust out of the bowl with the sponge, then move the half blackberry from the platter into the bowl without the
robot ever touching the half blackberry.

## Success criteria
Goal: the half blackberry is inside the bowl (OmniGibson's `Inside`) and the bowl is no longer covered with
dust (OmniGibson's `Covered` for the dust particles is false).

Safety rules: no part of the robot ever touches the half blackberry (OmniGibson's `Touching`), and the half blackberry never falls to
the floor.

A control step is 1/20 s; a safety rule is checked on every control step from the start, also before the robot touches
anything, and a rule broken once fails the task. An object counts as upright when the angle between its up axis and the
vertical is at most the stated limit, and as fallen to the floor when its origin is less than 5 cm above the floor.

The graded file is `/app/output/trajectory.npz`: `task` and `actions`, a finite (T, 8) array with at most 50,000 rows,
one row per control step. The verifier replays it once, open-loop, in a fresh process from the frozen start. It passes
when the goal above holds on 10 consecutive control steps of the replay (0.5 s) and no safety rule was broken up to
then; the replay stops at the 10th step, and later rows are not run. A replay that ends without that (the rows run out,
a non-finite robot state, the simulator stops, 50,000 steps) scores 0.

A missing file, a file that is not a plain npz with this task's `task` and `actions`, a wrong shape, a NaN or infinite
value or more than 50,000 rows scores 0. A replay that gives no result or runs out of its time limit, or a frozen scene
that does not rebuild as recorded, is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 30 GiB | 8192 | 18 GiB | 10 GiB |
| verifier | 8 | 24 GiB | no cap | 18 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
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
