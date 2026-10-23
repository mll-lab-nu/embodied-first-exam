# roboarc-ikea-eket-i00-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-ikea-eket-i00-standard` |
| Simulator / robot | `mujoco` / `franka-panda-bimanual` |
| Family / instance | `ikea_eket` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` |

## Task
IKEA EKET cabinet (AA-1914763-5), manual steps 1-4 in plain MuJoCo 3.14.0 (CPU, float64) with two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled): produce one replayable trajectory. Build the EKET cabinet frame: slide the two side panels into the top panel, then the back panel into its grooves, then the bottom panel onto the sides, and leave the cabinet standing on the table on its own.

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), 16-D actuator action at 400 Hz
(4 physics steps of 0.625 ms per row); the reference needs 70210 rows
(175.5 s of simulated time).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `a55a377945679794…`) to `/app/output/`: the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the same rows): a closed-loop reference built on the final physics: the demo as the phase guide, each held panel servoed onto the unclamped demo's recorded relative-pose track (damped-least-squares Jacobian IK on the TCP) and paused at each slide until its gate accepts; the rows are the targets executed after the joint-speed clamp. It never trips the joint-speed clamp.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in two fresh processes at the same time
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff both replays pass and end in the same state hashes (`deterministic`). The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): a third process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

Harbor checks (2026-10-16, workstation B (Ryzen 9 7950X; shared, loaded), Docker, Harbor 0.23.0, a fresh mtime base, image 0.3.0 sha256:ed950d079b63, the replay-video verifier, image `ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0` id `ed950d079b63`): `oracle` scored 1 (two replays, 294.9 s wall); `nop` scored 0. Reference timing against the 10800 s budget: one unobserved replay 472 s (4.4 %, inside the 40 % bar) on a dedicated Xeon Gold 6230R core of a CPU cluster (2.1 GHz, a slow trial-class CPU), end and settled hashes equal to the Harbor runs'.

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
| Scene | `/opt/ikea/scenes/eket/` in the image; digest `22795734d50cdce9…` (images/ikea-mujoco/assets.json) |
| Initial state | sha256 `9815e6dc4b4a9856…` of the mjSTATE_INTEGRATION vector |

### Goal
Build the EKET cabinet frame: slide the two side panels into the top panel, then the back panel into its grooves, then the bottom panel onto the sides, and leave the cabinet standing on the table on its own.

### Success requirements
- The seven operations happen in this order, each measured against the top panel: side A entry and slide, side B entry and slide, back slide, bottom entry and slide. Each one must reach its goal pose within the scene's gates (goal error 0.25 to 0.8 mm, angle 0.1 to 1 degree, nearly at rest, with contact with its counterpart panels).
- The four frame joints (side A and side B to the top, the bottom to both sides) are latched, and the five panels are finite.
- At the end the panels are released (no robot contact, no applied force), rest on the table (at least one panel touches the table top, none touches the floor) and move slower than 0.01 m/s and 0.05 rad/s.
- At the end every panel, the back included (it has no frame joint), is still in its assembled place: within 10 mm and 2 degrees of its goal pose relative to the top panel (the benchmark's end-pose rule, rcb_ikea.END_POSE_RULES).

### Mechanism
Mitres, keyholes, dowels and back grooves are contact. The four frame joints (welds) latch with the measured relative pose when the side A slide, the side B slide and the bottom slide pass their gates.

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/eket/`, `demos/eket_vlim/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep 0.625 ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `images/ikea-mujoco/stage_context.py`, pinned by `images/ikea-mujoco/assets.json`).
