# roboolympics-fun-catch-realgrasp-i00-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `roboolympics-fun-catch-realgrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `catch_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_catch_realgrasp.py: positive by injection (the real launch and flight; below 3 m the ball is put 0.12 m above the jaw centre of the right Dex1 pointing up: at 3 m/s into the open jaws, which close on it, and at the real 17 m/s into jaws preset to 67.5 mm, where it wedges and is held by pad friction, 120 N). A catch is both pads pressing within 45 deg of the closing axis, within 0.5 s of the first touch, then 1 s between the pads touching nothing else. Measured: at 17 m/s into open jaws the ball bounces out before they close; turned forward, ~51 N holds and ~13 N slips out. Negatives: onto the trunk, touched while rising, let go, slip, ball on the closed tips (core held=yes, no catch), clamped after the window, the other gripper on the held ball, a fall; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Catch the fly ball: close the jaws of one of your grippers on the baseball before it touches the ground or your body, and keep it there. (RoboOlympics `catch-realgrasp`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball is in the air for three seconds and comes down at about 17 m/s more than a metre away: the body has to walk there at 0.6 m/s and bring a gripper whose open jaws leave 8 mm on each side of the ball onto its line, and the jaws need about 40 ms to close on it, while a ball that meets the gripper at that speed bounces off it in a few milliseconds. The scene is dynamic (`scripts/task_dynamics.toml`: A launcher 40 m away fires the baseball at t = 1 s (21 m/s).), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-fun-catch-realgrasp-i00-privileged`).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17, board 0151); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: A baseball (0.073 m across, 0.145 kg, it flies in air with drag) rests on a launcher 40.0 m in front of you, 1.0 m above the ground, and is launched at t = 1.0 s at 21.35 m/s, 45.0 degrees above the horizon, 1.18 degrees to the left of the line from the launcher to you, so that untouched it would come down within 3.0 m of where you stand at the start. Both your hands are two-jaw grippers (90 mm stroke, jaws 80 mm long with rubber pads on their inner faces, at most 120 N of grip) that hold things only by friction; they start open. A catch: the pads of both jaws of one gripper touch the ball at the same time from its two sides, each with a contact whose direction is within 45.0 degrees of the jaws' closing direction (a ball lying on the jaws' tips or edges, or on closed jaws, is not caught), after the ball has passed the top of its arc and at the latest 0.5 s after it first touched you. Before the catch the ball may touch only your grippers and forearms. You succeed when, from the catch, the ball has stayed between the pads of that gripper for 1.0 s (both pads touching it in that way, apart from breaks of at most 0.02 s) touching nothing but that gripper. You fail if the ball touches the ground, or any part of you other than a gripper or a forearm, before the catch; if it is touched before it has passed the top of its arc; if it is not caught within 0.5 s of first touching you; if after the catch it is out of the jaws for longer than 0.02 s (dropped, slipped out or let go: a ball caught again does not count) or touches anything but the gripper that caught it (your other gripper, a forearm, your body, the ground); if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground) before the end; or after 9 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: as the standard twin; the GPU renders the cameras over EGL (board 0112, 2026-10-14): author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | Official Baseball Rules (MLB, 2024 edition): 3.01 (the ball), Definitions of Terms: "catch" (secure possession in the hand before the ball touches the ground, held long enough to show control), "in flight"; deviations: Definitions (catch): no glove; both hands are Unitree's Dex1-1 two-jaw grippers (sold for the G1, the H2 and the R1, not for the H1-2; mounted on the wrist where the H1-2's palm ends): 90 mm stroke, jaws 80 mm long and 34 mm wide with rubber pads, at most 120 N of grip, opening and closing at most 375 mm/s. A catch is the pads of both jaws of one gripper pressing on the ball from its two sides at the same time (each with a contact whose direction is within 45.0 degrees of the jaws' closing direction: the jaws closed on it, not a ball lying on their tips or edges), at the latest 0.5 s after the ball first touched you; "held long enough" is 1.0 s in which the ball stays between the pads of that gripper (breaks of at most 0.02 s) and touches nothing else, without falling. Nothing is welded: the ball is held only by the pads' friction and can slip out. · Definitions (catch): a ball that touches the body (any part other than the grippers and the forearms) before it is caught is not a catch here (the rule would allow trapping it against the body), and neither is a ball held at the end by anything but the jaws of the gripper that caught it (the other hand, a forearm, the body). · The fly ball is not batted: a launcher 40.0 m away sends it at 21.35 m/s, 45.0 degrees above the horizon, 1.0 s after the start, without spin; where it comes down (within 3.0 m of where you stand) is this instance's draw. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. |
| Stages | catch → hold |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 3.88 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; ws-1, 4 CPUs, board 0174, 2026-10-19, measured on the family's Session without the service); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 900 control steps (9 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
