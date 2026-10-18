# ikea-svallet-i00-privileged

| | |
|---|---|
| Benchmark | IKEA MuJoCo |
| Mode | privileged |
| Twin | `ikea-svallet-i00-standard` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `ikea_svallet` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-ikea-mujoco:0.3.0` |

## Task
IKEA SVALLET work lamp (AA-2140039-1), unpowered steps 1-2 in plain MuJoCo 3.14.0 (CPU, float64) with two 6-DoF ViperX 300 s arms (MuJoCo Menagerie ALOHA), each with its own parallel gripper: produce one replayable trajectory. Press the lamp shade's key down into the socket on top of the stand column until the spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats.

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), 14-D actuator action at 400 Hz
(4 physics steps of 0.625 ms per row); the reference needs 69414 rows
(173.5 s of simulated time).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `699f86e5075b74eb…`) to `/app/output/`: the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the same rows): the robot demo of the IKEA MuJoCo tree (`demos/svallet/actions.npz`), time-dilated to the robots' real joint-speed limits by `scripts/ikea_mujoco/standard/std_reference.py`, so the joint-speed clamp never changes a row. The demo itself commands faster than the limits and fails under the clamp.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in two fresh processes at the same time
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff both replays pass and end in the same state hashes (`deterministic`). The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): a third process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

Harbor checks (2026-10-16, ws2 (ws-2: Ryzen 9 7950X; shared, loaded), Docker, Harbor 0.23.0, harbor_run_safe.sh (fresh mtime base), image 0.3.0 sha256:ed950d079b63, the replay-video verifier, image `ghcr.io/mll-lab-nu/eai-ikea-mujoco:0.3.0` id `ed950d079b63`): `oracle` scored 1 (two replays, 495.2 s wall); `nop` scored 0. Reference timing against the 10800 s budget: one unobserved replay 478 s (4.4 %, inside the 40 % bar) on a dedicated Quest Xeon Gold 6230R core (2.1 GHz, a slow trial-class CPU), end and settled hashes equal to the Harbor runs'.

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
| Scene | `/opt/ikea/scenes/svallet/` in the image; digest `0ac62b72465133c4…` (scripts/ikea_mujoco/assets.json) |
| Initial state | sha256 `22360c69fb8a50ef…` of the mjSTATE_INTEGRATION vector |

### Goal
Press the lamp shade's key down into the socket on top of the stand column until the spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats.

### Success requirements
- Both retention joints are connected (shade on the stand, bulb in the shade) and, at the end, each connector is within its gates (axial gap, lateral offset and axis tilt).
- The stand rests on the bench (vertical contact force above 0.1 N) and is within 3 degrees of its upright start orientation.
- No robot contact with any lamp part at the end.

### Mechanism
The shade's barb cams a spring jaw (a slide joint with a spring, 1200 N/m) open and it snaps back over the barb. The bulb thread (11.9 mm x 1.5 mm right-hand, convex thread pieces) advances only by turning and seats on the socket stop. Retention welds switch on with the current relative pose when the seating gates hold. The prewired cable is not built.

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/svallet/`, `demos/svallet/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep 0.625 ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `scripts/ikea_mujoco/stage_context.py`, pinned by `scripts/ikea_mujoco/assets.json`).
