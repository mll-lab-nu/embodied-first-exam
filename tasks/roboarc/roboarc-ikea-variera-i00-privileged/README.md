# roboarc-ikea-variera-i00-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-ikea-variera-i00-standard` |
| Simulator / robot | `mujoco` / `franka-panda-bimanual` |
| Family / instance | `ikea_variera` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` |

## Task
IKEA VARIERA shelf insert (AA-741461-4), step 1 in plain MuJoCo 3.14.0 (CPU, float64) with two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled): produce one replayable trajectory. Assemble the VARIERA shelf insert: place the two side frames, lower the shelf onto them, and drive the four screws through the shelf holes into the frames' receivers until they seat.

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), 16-D actuator action at 400 Hz
(4 physics steps of 0.625 ms per row); the reference needs 231903 rows
(579.8 s of simulated time).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `a2653e570ce4be2c…`) to `/app/output/`: the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the same rows): the robot demo of the IKEA MuJoCo tree (`demos/variera/actions.npz`), then a release tail of our own appended: both grippers open and the arms hold for 0.6 s (240 rows): the demo ended with the left hand still closed on the screwdriver, which the terminal rules' release check refuses, time-dilated to the robots' real joint-speed limits, so the joint-speed clamp never changes a row. The demo itself commands faster than the limits and fails under the clamp.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in one fresh process
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff the replay passes. The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): another process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

Harbor checks (2026-10-16, workstation B (Ryzen 9 7950X; shared, loaded), Docker, Harbor 0.23.0, a fresh mtime base, image 0.3.0 sha256:ed950d079b63, the replay-video verifier, image `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` id `ed950d079b63`): `oracle` scored 1 (two replays, 3842.0 s wall); `nop` scored 0. Reference timing against the 10800 s budget: one unobserved replay 6839 s (63.3 %, OVER the 40 % bar) on a dedicated Xeon Gold 6230R core of a CPU cluster (2.1 GHz, a slow trial-class CPU), end and settled hashes equal to the Harbor runs'; 3413 s (31.6 %) on a quiet i9-14900HX laptop.

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
| Scene | `/opt/ikea/scenes/variera/` in the image; digest `869e1978078a13ae…` (images/ikea-mujoco/assets.json) |
| Initial state | sha256 `067105ad8f8329ec…` of the mjSTATE_INTEGRATION vector |

### Goal
Assemble the VARIERA shelf insert: place the two side frames, lower the shelf onto them, and drive the four screws through the shelf holes into the frames' receivers until they seat.

### Success requirements
- Four distinct receivers each hold a screw that was turned relative to that receiver (at least 0.4 measured turns, with a descent matching turns x pitch), its head seated at the shelf hole (axial 0.2 mm, lateral 0.6 mm, axis 1.5 degrees).
- The frames are aligned under the shelf, parts are slower than 0.02 m/s, the assembly stands on the bench on its own, and no robot touches any furniture part.
- All of the above hold for 0.5 s.

### Mechanism
Screw threads and receivers are non-convex SDF meshes (0.5 mm pitch, right-hand): a screw advances only by being turned. There are no welds or other non-contact mechanisms.

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/variera/`, `demos/variera/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep 0.625 ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `images/ikea-mujoco/stage_context.py`, pinned by `images/ikea-mujoco/assets.json`).
