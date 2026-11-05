# mujoco_playground_barkour_joystick-realtime

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `mujoco_playground_barkour_joystick-privileged` |
| Simulator / robot | `mujoco` / `google-barkour-vb` |
| Family / instance | `mujoco_playground/BarkourJoystick` / seed 2 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` |

## Task
MuJoCo Playground `BarkourJoystick` (Google Barkour vB) on the same frozen instance as `mujoco_playground_barkour_joystick-privileged`: Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, through random pushes, without falling over.
For 10 s the robot gets a joystick command schedule (2 segments: planar velocity and yaw rate in its own frame) and must track it without falling over. Its torso is pushed 12 times. Realtime mode (eai-standard/2.3, slowdown S = 1): once an episode's clock starts the
robot runs at 100 Hz whatever the agent does; it drives the robot through the realtime client from a program
of its own, with 10 resets (only the last episode is graded), the robot's own sensors and the cameras that
follow it.

## Difficulty
Same instance and success check as `mujoco_playground_barkour_joystick-standard`. The scene is dynamic (scripted pushes (kicks) apply an external force to the torso at moments the agent is not told),
and here time does not stop: the robot falls within a second without active balance and the pushes come at moments
the agent is not told, so nothing can be steered call by call. The agent has to write a feedback controller that runs
at the control rate in its own container, and learn the robot from 11 real attempts.

## Reference solution
`solution/oracle_plan.py` plans the privileged reference's rows (`solution/oracle.npy`, 1000 rows) into the episode
from its first control step (`submit(..., at=0)`); it uses no privileged information at run time. On the clock the rows
run at the same control steps as in the privileged replay, and the episode ends after the 1000 steps of the schedule, with success.

## Verification
The sim service (`environment/sim/rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with
`environment/sim/server.py`, this benchmark's adapter) judges the episode live and records every control step it ran
(`trajectory_live.f64`); after the agent's time the collect hook stops the agent's programs and signals the service,
which writes the live episode's verdict into `final.json` (`graded_by = "live"`, `replays = 0`: the task's check on the
episode it ran; nothing is replayed to grade it), then renders `replay.mp4` from the trajectory in one pass; the service
refuses an episode whose start does not hash to the instance's `state_sha` (`instance_mismatch`, infrastructure).
`tests/grade.py` (separate sandbox, no network) passes iff the live episode passed the check. The
clock's record (`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. Oracle: success, worst segment errors 0.033 m/s and 0.028 rad/s. `nop`: the
episode never starts (its clock starts at the first submit), reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | 4 GiB | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## Details
| | |
|---|---|
| Upstream | MuJoCo Playground @ 4057c14 (Apache-2.0): `menagerie/google_barkour_vb/scene_mjx.xml`; MuJoCo Menagerie @ 1b86ece (`google_barkour_vb`); MuJoCo 3.3.7 on the CPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): measured RTF 31.6 (2026-10-14, an RTX 4090 workstation at load 44, the service capped at 4 CPUs: the reference's 1000 rows planned from step 0 with the clock flat out, RCB_SLOWDOWN = 0.01), far above 3, so S = 1. At S = 1 the reference succeeds live and in the fresh replay with no stall, also streamed one row per call with a camera image every 0.25 s (7.7 ms each over EGL) |
| Service | the realtime layer of HumanoidBench, BiGym 2.0 and MyoSuite (`rcb_realtime.py`, `rcb_service.py`, unchanged) with `server.py`, which implements `rcb_service.Sim` on `rcb_quadruped.Session` (the standard twin's scene, schedule, pushes, termination rule and check); cameras `track` (follows the robot) and `realsense/rgb` (on its head) (320 x 240, EGL on the GPU) |
| Resources | 4 CPUs and a GPU for rendering (the physics is on the CPU) |
