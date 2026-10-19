# ikea-stegesund-i00-privileged

| | |
|---|---|
| Benchmark | IKEA MuJoCo |
| Mode | privileged |
| Twin | `ikea-stegesund-i00-standard` |
| Simulator / robot | `mujoco` / `franka-panda-bimanual` |
| Family / instance | `ikea_stegesund` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-0.3.0` |

## Task
IKEA STEGESUND toilet roll stand (AA-2652783-1), manual steps 1-3 in plain MuJoCo 3.14.0 (CPU, float64) with two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled): produce one replayable trajectory. Build the STEGESUND roll stand: press half B onto half A at the two leg crossings, push the shelf in from the foot end, drive the four bolts through the legs into the shelf's rail ends with the hex key, stand the frame up and drop the top rod into the two crotches.

## Difficulty
Bimanual furniture assembly with physical grasps (no assist), 16-D actuator action at 400 Hz
(4 physics steps of 0.625 ms per row); the reference needs 357221 rows
(893.05 s of simulated time).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `2181d216a5559c98…`) to `/app/output/`: the task's one reference, shared with the standard twin (its `solution/oracle_actions.npz`, the same rows): the author's speed-limited demo (`stegesund_vlim`), unchanged (`scripts/ikea_mujoco/oracles/stegesund/`): every row is within the joint-speed limits (from the keyframe ctrl; the largest step is the limit itself), so the clamp never changes a row, and it passes the terminal rules as sent (it ends released and at rest). It never trips the joint-speed clamp.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the scene's initial state in two fresh processes at the same time
(`tests/grade.py`, `tests/rcb_ikea.py replay`: per row `data.ctrl[:] = row; S.step(4)` with the scene's mechanism, then
`final_check()`: `success.py`, released, at rest and no breakdown at the end of the rows and again after a 1.0 s hold of
the last row). Pass iff both replays pass and end in the same state hashes (`deterministic`). The
scene in the verifier image must match `tests/runtime_binding.json` file by file (`instance_exact`) and build to its
initial-state hash (`instance_ok`). Replay video (evidence only, never the verdict): a third process replays the same rows and renders `/logs/verifier/replay.mp4` (CPU OSMesa, 512 x 288, at most 750 frames over the episode and the 1.0 s hold; `video_rendered`).

Harbor checks (2026-10-16, ws3 (ws-3: Ryzen 9 7950X; shared, loaded), Docker, Harbor 0.23.0, harbor_run_safe.sh (fresh mtime base), image 0.3.0 sha256:ed950d079b63, the replay-video verifier, image `ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-0.3.0` id `ed950d079b63`): `oracle` scored 1 (two replays, 1508.1 s wall); `nop` scored 0. Reference timing against the 10800 s budget: one unobserved replay 3160 s (29.3 %, inside the 40 % bar) on a dedicated Quest Xeon Gold 6230R core (2.1 GHz, a slow trial-class CPU), end and settled hashes equal to the Harbor runs'; 3245-3518 s in earlier Quest runs, 1612 s on vast EPYC 9354.

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
| Scene | `/opt/ikea/scenes/stegesund/` in the image; digest `4e0cbabcd4c7f692…` (scripts/ikea_mujoco/assets.json) |
| Initial state | sha256 `917b2bc63ab1ec62…` of the mjSTATE_INTEGRATION vector |

### Goal
Build the STEGESUND roll stand: press half B onto half A at the two leg crossings, push the shelf in from the foot end, drive the four bolts through the legs into the shelf's rail ends with the hex key, stand the frame up and drop the top rod into the two crotches.

### Success requirements
- Every part except half A and the hex key is at its assembled pose relative to half A (a bolt: relative to the shelf): half B and the shelf within 0.6 mm and 1 degree; the top rod within 3 mm and 1 degree (up to the rod's own symmetry: it may lie end for end, or turned by a facet); each bolt within 0.6 mm along and across its bore axis, its axis within 2 degrees (spin free).
- The stand is upright: half A's z axis within 1 degree of world +z.
- success.py checks only the end state, and the hex key may be anywhere at the end; the terminal rules below add the release, rest and no-breakdown checks.

### Mechanism
Each bolt's coarse right-hand thread (2.5 mm pitch) is a capsule helix against a matching helix in the shelf's rail end: a bolt advances only by being turned, by the hex key in its 4 mm socket. The half-lap crossings are press fits (contact and friction, no weld). A bolt's seat weld is armed at its first thread contact; once its head touches and it has stopped relative to the shelf for 0.05 s, the bolt and the half it clamps are welded to the shelf at their current pose, and the bolt and its rail-end thread stop colliding.

### Provenance
- Scene and demo: the IKEA MuJoCo tree (`scenes/stegesund/`, `demos/stegesund_vlim/actions.npz`), MuJoCo 3.14.0, RoboARC rigid settings
  (timestep 0.625 ms, Newton, 100 iterations, elliptic cones).
- The scene files are not in this repository: the image carries them (`images/ikea-mujoco/README.md`, build context from
  `scripts/ikea_mujoco/stage_context.py`, pinned by `scripts/ikea_mujoco/assets.json`).
