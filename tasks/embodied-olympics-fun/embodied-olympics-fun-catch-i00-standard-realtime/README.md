# embodied-olympics-fun-catch-i00-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-catch-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `catch` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_catch.py: positive by injection (the real launch and flight; below 3 m the ball is put 0.12 m above the upturned palm at 3 m/s and really gripped); negatives: onto the trunk, touched while rising, dropped after the catch, a fall. The ball comes down 1.25 m from the robot after 3 s at 16.6 m/s: the walk and a palm placed within centimetres are the task; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Catch the fly ball: grip the baseball with a hand before it touches the ground or your body, and keep hold of it. (Embodied Olympics `catch`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball is in the air for three seconds and comes down at about 17 m/s more than a metre away: the body has to walk there at 0.6 m/s and put a palm on the ball's line to within a few centimetres, facing it, with the grip closing in the few milliseconds in which the ball is against the palm. The scene is dynamic (`scripts/task_dynamics.toml`: A launcher 40 m away fires the baseball at t = 1 s (21 m/s).), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-catch-i00-privileged`).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: A baseball (0.073 m across, 0.145 kg, it flies in air with drag) rests on a launcher 40.0 m in front of you, 1.0 m above the ground, and is launched at t = 1.0 s at 21.35 m/s, 45.0 degrees above the horizon, 1.18 degrees to the left of the line from the launcher to you, so that untouched it would come down within 3.0 m of where you stand at the start. A catch is a hand's grip closing on the ball in flight after it has passed the top of its arc: the grip holds a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it. Before the grip the ball may touch only your hands and forearms. You succeed when a hand has gripped the ball and kept it for 1.0 s without a break. You fail if the ball touches the ground, or any part of you other than a hand or a forearm, before it is gripped; if you let go of it after the catch; if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground) before the end; or after 9 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: as the standard twin; the GPU renders the cameras over EGL (2026-10-14): author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | Official Baseball Rules (MLB, 2024 edition): 3.01 (the ball), Definitions of Terms: "catch" (secure possession in the hand before the ball touches the ground, held long enough to show control), "in flight"; deviations: Definitions (catch): no glove; the hand catches by a grip that closes on a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it (the platform's grip). "Held long enough" is 1.0 s without letting go and without falling. A ball that touches the body (any part other than the hands and forearms) before it is gripped is not a catch here (the rule would allow it). · The fly ball is not batted: a launcher 40.0 m away sends it at 21.35 m/s, 45.0 degrees above the horizon, 1.0 s after the start, without spin; where it comes down (within 3.0 m of where you stand) is this instance's draw. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. |
| Stages | catch → hold |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 3.61 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; an RTX 4090 workstation, 4 CPUs, 2026-10-14); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 900 control steps (9 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
