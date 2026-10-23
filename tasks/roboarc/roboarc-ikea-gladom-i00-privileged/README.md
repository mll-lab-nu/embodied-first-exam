# roboarc-ikea-gladom-i00-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-ikea-gladom-i00-standard` |
| Simulator / robot | `mujoco` / `franka-panda-bimanual` |
| Family / instance | `ikea_gladom` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` |

## Task
IKEA GLADOM tray table (AA-1832218-3), full seven-operation scope in plain MuJoCo 3.14.0 (CPU, float64) with two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled): produce one replayable trajectory. Build the GLADOM tray table: cross frame B into frame A, drive the long screw and the bottom screw, place the ring and drive its two screws, and set the tray on the ring.

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), 16-D actuator action at 400 Hz
(4 physics steps of 0.625 ms per row); the reference needs 168628 rows
(421.6 s of simulated time).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `19fd2916abd1820d…`) to `/app/output/`: the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the same rows): the robot demo of the IKEA MuJoCo tree (`demos/gladom/actions.npz`), time-dilated to the robots' real joint-speed limits, so the joint-speed clamp never changes a row. The demo itself commands faster than the limits and fails under the clamp.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in two fresh processes at the same time
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff both replays pass and end in the same state hashes (`deterministic`). The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): a third process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

Harbor checks (2026-10-16, workstation B (Ryzen 9 7950X; shared, loaded), Docker, Harbor 0.23.0, a fresh mtime base, image 0.3.0 sha256:ed950d079b63, the replay-video verifier, image `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` id `ed950d079b63`): `oracle` scored 1 (two replays, 3168.4 s wall); `nop` scored 0. Reference timing against the 10800 s budget: one unobserved replay 5636 s (52.2 %, OVER the 40 % bar) on a dedicated Xeon Gold 6230R core of a CPU cluster (2.1 GHz, a slow trial-class CPU), end and settled hashes equal to the Harbor runs'; 2882 s (26.7 %) on a quiet i9-14900HX laptop.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 3 |
| Memory | 2 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: peak RSS of one Session 0.27-0.45 GB per scene (3000 reference rows + final_check, laptop, 2026-10-15); the verifier runs two replays and the video replay at once; x 1.2 and rounded up
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: the privileged peaks with room for an agent's own replays (four Sessions at once).

## Details
| | |
|---|---|
| Grasping | physical (finger friction), no assist |
| Success rule | the scene's `success.py` + the terminal rules (released, at rest, no breakdown), at the end of the rows and after a 1.0 s hold |
| Scene | `/opt/ikea/scenes/gladom/` in the image; digest `8c5f29daaa7e14c2…` (images/ikea-mujoco/assets.json) |
| Initial state | sha256 `700c53dd5fd9fe2b…` of the mjSTATE_INTEGRATION vector |

### Goal
Build the GLADOM tray table: cross frame B into frame A, drive the long screw and the bottom screw, place the ring and drive its two screws, and set the tray on the ring.

### Success requirements
- The retention joints of frame B, the ring and the four screws are all latched.
- Every part except frame A is at its assembled pose relative to frame A: gap within 0.8 mm along frame A's z axis, lateral within 1 mm, tilt within 2 degrees (screws: axis tilt; frame B and the ring may be rotated 180 degrees, the tray 7.5 degrees), relative speed below 0.025 m/s. The two ring screws may use either ring receiver, but distinct ones.
- The tray is free (never jointed) and supported by the ring (contact above 0.01 N in at least 12 of 36 samples over the last 0.15 s, and above 0.01 N on average over them); no robot contact with any furniture part.
- All of the above hold continuously for 0.15 s.

### Mechanism
Screw threads and frame A's four nut sleeves are SDF meshes (0.5 mm pitch, right-hand): a screw advances only by being turned. Retention welds to frame A switch on when the scene's acceptance gates hold. The tray is never jointed.

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/gladom/`, `demos/gladom/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep 0.625 ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `images/ikea-mujoco/stage_context.py`, pinned by `images/ikea-mujoco/assets.json`).
