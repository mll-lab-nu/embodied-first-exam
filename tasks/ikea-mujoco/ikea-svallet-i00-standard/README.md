# ikea-svallet-i00-standard

| | |
|---|---|
| Benchmark | IKEA MuJoCo |
| Mode | standard (`eai-standard/2.4`) |
| Twin | `ikea-svallet-i00-privileged` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `ikea_svallet` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-sim-0.4.0` |

## Task
IKEA SVALLET work lamp (AA-2140039-1), unpowered steps 1-2 in plain MuJoCo 3.14.0 (CPU, float64) with two 6-DoF ViperX 300 s arms (MuJoCo Menagerie ALOHA), each with its own parallel gripper, through the robot service (eai-standard/2.4; 2.1 / 2.2
requests are served unchanged): RGB from four ALOHA-style cameras (optional depth), proprioception, `joint_position`
chunks, stateless kinematics, every pose in the robot's frame; no reset and no privileged state. Press the lamp shade's key down into the socket on top of the stand column until the spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats.

## Difficulty
The privileged twin's bimanual assembly with physical grasps, from cameras and proprioception only, in one episode
without reset; 14-D actuator action at 400 Hz, joint targets within the robot's joint
velocity limits (3.14159 rad/s on every arm joint). The reference needs 68000 control steps (170.0 s of simulated
time).

## Reference solution
`solution/solve.sh` runs `solution/oracle_replay.py`: it submits the control steps of `solution/oracle_actions.npz` through
the client as `joint_position` chunks of 10 s, `hold`, one control step per row, as float64 (the client's transport;
`Robot.submit` sends float32), so the service executes exactly those rows. The rows are the privileged twin's reference trajectory brought within the joint-speed rule by `scripts/ikea_mujoco/standard/std_reference.py` (`make --method track --lag 0.1`: target glitches of one to a few control steps, which the servos never followed, replaced by the running median (344 rows); then every privileged row in order through a slew-limited tracker: each control step an arm joint target moves toward the current row by at most its limit, and the next row is taken once every joint is within 0.1 rad of it, so time is stretched only where the rows are faster than the limits (65529 privileged rows, 3885 control steps added, 69414 in all)),
so the service's speed limiter never has to act (`n_clipped` 0).

## Verification
The sim service (`environment/sim/server.py`) steps the scene's own runtime (`rcb_ikea.Session.step`: `data.ctrl[:] =
row; S.step(4)`), applies the joint-speed rule, evaluates the grader's terminal rules (`rcb_ikea.Session.status()`:
success.py, released, at rest, no breakdown) after every call and, when they hold, `Session.final_check()` (the same after
a 1.0 s hold of the last row), both on a snapshot restored bit-exactly afterwards, ends the episode at the first settled
success or at a breakdown, and journals every executed control step; at the end it writes
`/data/trajectory.npz` (all executed control steps, float64: the replayable deliverable) and the final state hash; an
episode that ends otherwise (timeout) is judged as it stands by the same two checks. Before the episode the service checks
the scene file by file against `runtime_binding.json` and by its initial-state hash (`instance_mismatch`, infrastructure).
The verifier (`tests/grade.py`, separate sandbox, no network, the shared client base) transcribes `final.json`: pass iff
the live episode succeeded (`graded_by_live` 1, `replays` 0). No grading replay runs (owner, 2026-10-17, board 0151).

Before 2026-10-17 (graded then by the verifier's two replays; history, not re-run since): Harbor checks on ws (ws-1: RTX 4090; shared, loaded) (oracle), ws2 (nop), Harbor 0.23.0, image 0.3.0 sha256:ed950d079b63 / -sim 0.4.0 (Nyx RGB; built per host from one context: ws2 a466a594c463, ws3 53d8800bfa22, ws 3f9218fb9864); the live, replay and settled hashes equal the 0.3.0 (EGL) run's (2026-10-16): `oracle` scored 1 (sim 0.4.0 (Nyx): live settled success at control step 68000 (17 calls), both replays pass final_check() and end in the live state (live_matches_replay 1, deterministic 1), live end hash = the 0.3.0 run's; live service time 397 s, verifier replays 353 s); `nop` scored 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 1 GB | 0 GB |

- GPU: required, any NVIDIA GPU; recommended: RTX 4090 24GB / L4 24GB (an NVIDIA GPU with Vulkan and EGL).
- Measured: Harbor standard oracle of svallet on an RTX 4090 host, 2026-10-17 (docker stats and nvidia-smi per process every 20 s): the sim sidecar peaked at 1.8 GiB of memory and 0.8 GiB of GPU memory (the Nyx render process), the agent's container (the client) below 0.1 GiB; the privileged verifier of the same task (two replays and the video replay) at 1.6 GiB; x 1.5 and rounded up
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 16 GiB memory. Limits measured: the sidecar's measured peaks (1.8 GiB, 0.8 GiB of GPU memory, svallet) with room for the longer scenes and an agent's own client processes; the agent's container runs the client only.

## Details
| | |
|---|---|
| Grasping | physical (finger friction), no assist |
| Success rule | the scene's `success.py` + the terminal rules (released, at rest, no breakdown), on the live episode: after every call and at its end, at the last row and again after a 1.0 s hold of it (on a copy) |
| Frame | every pose the agent gets or gives is in the robot frame: origin at the left arm's base link, +z up (`spec.world`); the scene's own world frame never leaves the sim service |
| Speed rule | targets within the robot's real limits (3.14159 rad/s on every arm joint; the table and its sources: `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S` / `GRIPPER_SPEED_LIMITS`), clamped per control step, as the privileged twin's Session; faster rows take the control steps they need (`meta.clipped`), as RoboARC's rule |
| Cameras | `cam_high`, `cam_low` (static), `cam_left_wrist`, `cam_right_wrist` (on the hands); 848 x 480, fovy 58 deg; added at service start (`environment/sim/ikea_rig.py`, `rig.json`), the model is unchanged; RGB: Nyx, RoboARC's renderer and look (path tracer, 32 spp, denoised; studio HDRI and point lights; `environment/sim/ikea_nyx.py` with RoboARC's `nyx_direct.py`); depth: MuJoCo's raster; on the sidecar's GPU |
| Video | `/data/live.mp4` (cam_high, 10 frames per simulated second, recorded during the live episode), copied to the verifier logs; never affects the verdict |
| Scene | `/opt/ikea/scenes/svallet/` in the images; digest `0ac62b72465133c4…` |
| Initial state | sha256 `22360c69fb8a50ef…` of the mjSTATE_INTEGRATION vector |

### Budget
The wall clock only, the privileged twin's cutoff (PROTOCOL v2.0 H.7): `[agent] timeout_sec` = 10800 s. The service
counts the same limit from the agent's first request (`spec.budget.wall_clock_s`, `meta.time_left_s`) and ends the
episode with reason `timeout` when it runs out; that count never runs out before Harbor's.

### Deviations
- `ee_pose` is not offered (only `joint_position`, the scene's actuator layout); `/kinematics` gives FK / IK.
- Graded by the live episode (the settled check on the live simulator); no grading replay, in the sidecar or the
  verifier (owner, 2026-10-17, board 0150/0151).

### Goal
Press the lamp shade's key down into the socket on top of the stand column until the spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats.

### Success requirements
- Both retention joints are connected (shade on the stand, bulb in the shade) and, at the end, each connector is within its gates (axial gap, lateral offset and axis tilt).
- The stand rests on the bench (vertical contact force above 0.1 N) and is within 3 degrees of its upright start orientation.
- No robot contact with any lamp part at the end.

The benchmark's terminal rules, the same in every IKEA MuJoCo task, come on top of these requirements. When your rows end: (1) the requirements above hold; (2) the parts are released: no robot link touches any part; (3) every part is at rest: at most 0.01 m/s and 0.05 rad/s; (4) the simulation never broke down: no non-finite state, no MuJoCo BADQACC / BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm, at any time. The grader then holds your last row for 1.0 s more and requires (1)-(4) again at its end.

### Mechanism
The shade's barb cams a spring jaw (a slide joint with a spring, 1200 N/m) open and it snaps back over the barb. The bulb thread (11.9 mm x 1.5 mm right-hand, convex thread pieces) advances only by turning and seats on the socket stop. Retention welds switch on with the current relative pose when the seating gates hold. The prewired cable is not built.
