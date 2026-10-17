# ikea-gladom-i00-standard

| | |
|---|---|
| Benchmark | IKEA MuJoCo |
| Mode | standard (`eai-standard/2.4`) |
| Twin | `ikea-gladom-i00-privileged` |
| Simulator / robot | `mujoco` / `franka-panda-bimanual` |
| Family / instance | `ikea_gladom` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-ikea-mujoco-sim:0.4.0` |

## Task
IKEA GLADOM tray table (AA-1832218-3), full seven-operation scope in plain MuJoCo 3.14.0 (CPU, float64) with two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled), through the robot service (eai-standard/2.4; 2.1 / 2.2
requests are served unchanged): RGB from four ALOHA-style cameras (optional depth), proprioception, `joint_position`
chunks, stateless kinematics, every pose in the robot's frame; no reset and no privileged state. Build the GLADOM tray table: cross frame B into frame A, drive the long screw and the bottom screw, place the ring and drive its two screws, and set the tray on the ring.

## Difficulty
The privileged twin's bimanual assembly with physical grasps, from cameras and proprioception only, in one episode
without reset; 16-D actuator action at 400 Hz, joint targets within the robot's joint
velocity limits (joints 1-4 2.175 rad/s, joints 5-7 2.61 rad/s). The reference needs 168000 control steps (420.0 s of simulated
time).

## Reference solution
`solution/solve.sh` runs `solution/oracle_replay.py`: it submits the control steps of `solution/oracle_actions.npz` through
the client as `joint_position` chunks of 10 s, `hold`, one control step per row, as float64 (the client's transport;
`Robot.submit` sends float32), so the service executes exactly those rows. The rows are the privileged twin's reference trajectory brought within the joint-speed rule by `scripts/ikea_mujoco/standard/std_reference.py` (`make --method centred`: target glitches of one to a few control steps, which the servos never followed, replaced by the running median (0 rows); then every row keeps its time: per arm joint the mean of a forward and a backward slew-limited pass, so a move faster than the limits starts a little earlier and ends a little later, centred on the original (168628 control steps; largest target deviation 0.505 rad)),
so the service's speed limiter never has to act (`n_clipped` 0).

## Verification
The sim service (`environment/sim/server.py`) steps the scene's own runtime (`rcb_ikea.Session.step`: `data.ctrl[:] =
row; S.step(4)`), applies the joint-speed rule, evaluates the grader's terminal rules (`rcb_ikea.Session.status()`:
success.py, released, at rest, no breakdown) after every call and, when they hold, `Session.final_check()` (the same after
a 1.0 s hold of the last row), both on a snapshot restored bit-exactly afterwards, ends the episode at the first settled
success or at a breakdown, and journals every executed control step; at the end it writes
`/data/trajectory.npz` (all executed control steps, float64) and the final state hash. The verifier (`tests/grade.py`,
separate sandbox, no network, the `ghcr.io/mll-lab-nu/eai-ikea-mujoco:0.3.0` image) replays the trajectory in two fresh processes with the privileged
grader (`tests/replay_grade.py`: `final_check()`, the terminal rules at the end of the rows and after a 1.0 s hold; the
scene checked file by file and by its initial state). Pass iff the live episode succeeded, both replays succeed, and they
end in the live final state (`live_matches_replay`, `deterministic`).

Harbor checks on ws3 (ws-3: Ryzen 9 7950X, RTX 4090; shared, loaded) (oracle), ws2 (nop), Harbor 0.23.0, image 0.3.0 sha256:ed950d079b63 / -sim 0.4.0 (Nyx RGB; built per host from one context: ws2 a466a594c463, ws3 53d8800bfa22, ws 3f9218fb9864); the live, replay and settled hashes equal the 0.3.0 (EGL) run's (2026-10-16): `oracle` scored 1 (sim 0.4.0 (Nyx): live settled success at control step 168000 (42 calls), both replays pass final_check() and end in the live state (live_matches_replay 1, deterministic 1), live end hash = the 0.3.0 run's; live service time 3362 s, verifier replays 3975 s); `nop` scored 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 1 GB | 0 GB |

- GPU: required, any NVIDIA GPU; recommended: RTX 4090 24GB / L4 24GB (an NVIDIA GPU with Vulkan and EGL).
- Measured: Harbor standard oracle of svallet on an RTX 4090 host, 2026-10-17 (docker stats and nvidia-smi per process every 20 s): the sim sidecar peaked at 1.8 GiB of memory and 0.8 GiB of GPU memory (the Nyx render process), the agent's container (the client) below 0.1 GiB; the privileged verifier of the same task (two replays and the video replay) at 1.6 GiB; x 1.5 and rounded up
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 16 GiB memory. Limits measured: the sidecar's measured peaks (1.8 GiB, 0.8 GiB of GPU memory, svallet) with room for the longer scenes and an agent's own client processes; the agent's container runs the client only.

## Details
| | |
|---|---|
| Grasping | physical (finger friction), no assist |
| Success rule | the scene's `success.py` + the terminal rules (released, at rest, no breakdown): live after every call, and on the replays at the end of the rows and after a 1.0 s hold |
| Frame | every pose the agent gets or gives is in the robot frame: origin at the left arm's base link, +z up (`spec.world`); the scene's own world frame never leaves the sim service |
| Speed rule | targets within the robot's real limits (joints 1-4 2.175 rad/s, joints 5-7 2.61 rad/s; the table and its sources: `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S` / `GRIPPER_SPEED_LIMITS`), clamped per control step, as the privileged twin's Session; faster rows take the control steps they need (`meta.clipped`), as RoboARC's rule |
| Cameras | `cam_high`, `cam_low` (static), `cam_left_wrist`, `cam_right_wrist` (on the hands); 848 x 480, fovy 58 deg; added at service start (`environment/sim/ikea_rig.py`, `rig.json`), the model is unchanged; RGB: Nyx, RoboARC's renderer and look (path tracer, 32 spp, denoised; studio HDRI and point lights; `environment/sim/ikea_nyx.py` with RoboARC's `nyx_direct.py`); depth: MuJoCo's raster; on the sidecar's GPU |
| Live video | `/data/live.mp4` (cam_high, 10 frames per simulated second), copied to the verifier logs; never affects the verdict |
| Scene | `/opt/ikea/scenes/gladom/` in the images; digest `8c5f29daaa7e14c2…` |
| Initial state | sha256 `700c53dd5fd9fe2b…` of the mjSTATE_INTEGRATION vector |

### Budget
The wall clock only, the privileged twin's cutoff (PROTOCOL v2.0 H.7): `[agent] timeout_sec` = 10800 s. The service
counts the same limit from the agent's first request (`spec.budget.wall_clock_s`, `meta.time_left_s`) and ends the
episode with reason `timeout` when it runs out; that count never runs out before Harbor's.

### Deviations
- The verifier image is the IKEA MuJoCo image, not the shared client base: it replays the trajectory itself.
- `ee_pose` is not offered (only `joint_position`, the scene's actuator layout); `/kinematics` gives FK / IK.
- No fresh-process replay inside the sidecar (finalize.sh only ends the service): the verifier's replays decide.

### Goal
Build the GLADOM tray table: cross frame B into frame A, drive the long screw and the bottom screw, place the ring and drive its two screws, and set the tray on the ring.

### Success requirements
- The retention joints of frame B, the ring and the four screws are all latched.
- Every part except frame A is at its assembled pose relative to frame A: gap within 0.8 mm along frame A's z axis, lateral within 1 mm, tilt within 2 degrees (screws: axis tilt; frame B and the ring may be rotated 180 degrees, the tray 7.5 degrees), relative speed below 0.025 m/s. The two ring screws may use either ring receiver, but distinct ones.
- The tray is free (never jointed) and supported by the ring (contact above 0.01 N in at least 12 of 36 samples over the last 0.15 s, and above 0.01 N on average over them); no robot contact with any furniture part.
- All of the above hold continuously for 0.15 s.

The benchmark's terminal rules, the same in every IKEA MuJoCo task, come on top of these requirements. When your rows end: (1) the requirements above hold; (2) the parts are released: no robot link touches any part; (3) every part is at rest: at most 0.01 m/s and 0.05 rad/s; (4) the simulation never broke down: no non-finite state, no MuJoCo BADQACC / BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm, at any time. The grader then holds your last row for 1.0 s more and requires (1)-(4) again at its end.

### Mechanism
Screw threads and frame A's four nut sleeves are SDF meshes (0.5 mm pitch, right-hand): a screw advances only by being turned. Retention welds to frame A switch on when the scene's acceptance gates hold. The tray is never jointed.
