# roboarc-ikea-ikea365-i00-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-ikea-ikea365-i00-standard` |
| Simulator / robot | `mujoco` / `franka-panda-bimanual` |
| Family / instance | `ikea_ikea365` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` |

## Task
IKEA 365+ serving stand (AA-2568481-2) in plain MuJoCo 3.14.0 (CPU, float64) with two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled): produce one replayable trajectory. Rebuild the IKEA 365+ serving stand: take the screw out of member A and park it, lay member B across member A, bring the screw back and screw it in through both members until it seats, turn the stand over, and place the bowl on it.

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), 16-D actuator action at 400 Hz
(4 physics steps of 0.625 ms per row); the reference needs 89126 rows
(222.8 s of simulated time).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `d32ff622ac43e114…`) to `/app/output/`: the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the same rows): a closed-loop reference built on the final physics: the demo through the clamp as the phase guide; the right hand threads the returned screw itself before releasing it; the screwdriver is centred on the true screw axis, spins with a 5-15 N axial push and goes torque-free at the seat so the welds engage on an unloaded screw; guide tracks (damped-least-squares IK) steer the hands onto member B, the turned stand and the bowl; the rows are the targets executed after the joint-speed clamp. It never trips the joint-speed clamp.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in one fresh process
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff the replay passes. The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): another process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

Harbor checks (2026-10-16, workstation B (Ryzen 9 7950X; shared, loaded), Docker, Harbor 0.23.0, a fresh mtime base, image 0.3.0 sha256:ed950d079b63, the replay-video verifier, image `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` id `ed950d079b63`): `oracle` scored 1 (two replays, 359.5 s wall); `nop` scored 0. Reference timing against the 10800 s budget: one unobserved replay 604 s (5.6 %, inside the 40 % bar) on a dedicated Xeon Gold 6230R core of a CPU cluster (2.1 GHz, a slow trial-class CPU), end and settled hashes equal to the Harbor runs'.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Grasping | physical (finger friction), no assist |
| Success rule | the scene's `success.py` + the terminal rules (released, at rest, no breakdown), at the end of the rows and after a 1.0 s hold |
| Scene | `/opt/ikea/scenes/ikea365/` in the image; digest `25535efa33fd5d80…` (images/ikea-mujoco/assets.json) |
| Initial state | sha256 `4e9e040022202b3e…` of the mjSTATE_INTEGRATION vector |

### Goal
Rebuild the IKEA 365+ serving stand: take the screw out of member A and park it, lay member B across member A, bring the screw back and screw it in through both members until it seats, turn the stand over, and place the bowl on it.

### Success requirements
- The seven operations are accepted in this order: remove the screw, park the screw, cross the members, return the screw, reinstall the screw, turn the stand, place the bowl.
- At the end the screw is retained in member A and aligned with its seated pose relative to both members, and member B is retained and aligned with member A (gates: axial 0.1 mm, lateral 0.6 mm, axis 1.5 degrees; member B may be rotated 180 degrees).
- Released and settled: no robot contact with any part, every part slower than 0.025 m/s, the bench carries the parts; the bowl touches the members and member A is turned over (its z axis pointing down).
- A support probe on a copy of the final state: the bench must carry the whole weight, and the weight plus a 2 N downward test load on member A (the grader applies it; it never acts during your episode), with the arms holding their last commands.

### Mechanism
The M4 x 0.5 thread is exact convex pieces: the screw advances only by being turned. Two retention welds (screw to member A, member B to member A) switch on with the current relative pose once the reinstalled screw is seated.

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/ikea365/`, `demos/ikea365/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep 0.625 ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `images/ikea-mujoco/stage_context.py`, pinned by `images/ikea-mujoco/assets.json`).
