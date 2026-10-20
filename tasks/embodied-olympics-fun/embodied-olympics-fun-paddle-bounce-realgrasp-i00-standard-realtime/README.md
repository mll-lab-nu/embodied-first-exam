# embodied-olympics-fun-paddle-bounce-realgrasp-i00-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-paddle-bounce-realgrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `paddle_bounce_realgrasp` / seed 0 |
| Oracle | `full` — paddle-bounce's solution ported to the free paddle in the Dex1-1 (IK reads the paddle's pose in the jaws): 20 bounces at 15.4 s, 17/18 perturbations; two-jaw breaks ≤2 ms; 0.6 N clamp slides 54 mm, 0.3 N drops In standard-realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Keep the table tennis ball that is dropped in front of you bouncing on the paddle held in your right hand's gripper: 20 bounces in a row, each back up to the height the ball was dropped from, without letting go of the paddle. (Embodied Olympics `paddle-bounce-realgrasp`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Every bounce needs an upward hit of the right strength at the right instant, with the blade level and under a 40 mm ball: a tilt of a degree sends the ball off the 15 cm blade within a few bounces, and the arm that holds the blade gives way a little at every hit. The paddle sits in a two-finger gripper, so the blade is where the jaws hold it, not where the arm was told to put it, and it has to go right twenty times in a row. The scene is dynamic (`scripts/task_dynamics.toml`: The venue releases the ball at drop_time_s (a clock-timed release; gravity then does the work).), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. paddle-bounce's solution ported to the free paddle in the Dex1-1 (IK reads the paddle's pose in the jaws): 20 bounces at 15.4 s, 17/18 perturbations; two-jaw breaks ≤2 ms; 0.6 N clamp slides 54 mm, 0.3 N drops

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: A table tennis racket (a rigid square blade 0.15 m wide and 0.015 m thick on a straight handle 0.1 m long, 0.032 m wide and 0.025 m thick; 0.14 kg; the blade's centre 0.175 m from the butt) is a separate body; at the start its handle is closed in your right hand's two-finger gripper, which holds it by friction only: it can slip, turn in the gripper and fall. The paddle is in your hand while its handle touches both of the gripper's jaws; it has left your hand when for more than 0.05 s the handle has not touched both jaws. The paddle may touch nothing of you but your right hand (the gripper's jaws and body). The official ball (40 mm, 2.7 g; it flies in air, with drag) hangs at rest, its centre 1.2 m above the floor, until 2.0 s after the start, and then falls. You succeed after 20 bounces in a row on the blade (either face; the faces need not alternate). A bounce is a touch of the blade after which, before the ball touches the blade again, the ball's centre rises at least 0.15 m above the height at which it left the blade and reaches at least the height it was dropped from, 1.2 m above the floor, and which the ball leaves with at least 0.98 of the speed it reached the blade with (both speeds taken at the height where the touch began). On a still blade every bounce is lower than the one before (the ball keeps about nine tenths of its height, 0.95 of its speed), so each bounce needs a hit of the blade; a rebound that rises enough but was not hit is not counted, and is not a fault. A touch is all contact of the ball with the blade from the first contact on, with breaks shorter than 0.02 s; a bounce's own contact lasts about a millisecond. You fail if the paddle leaves your hand at any time (dropped, thrown or slipped out of the gripper); if the paddle touches any part of you other than your right hand; if the ball comes back to the blade after a touch without having risen that much; if a touch lasts longer than 0.02 s from its first contact to its last (the ball rests, rolls or is carried on the blade); if the ball touches the floor or anything other than the blade (the paddle's handle, the gripper, your arm or body included); if you or the paddle touch the ball before it is dropped; if you fall; or after 20 s. A fall is your pelvis lower than 0.35 m above the floor, or any part of you other than your feet touching the floor; the paddle touching the floor is a fall too.

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
| Category | basketball-and-rackets |
| Rule book | ITTF Handbook 2024, The Laws of Table Tennis, for the equipment: 2.3 (the ball), 2.4 (the racket), 2.5.5 (the racket hand: the hand carrying the racket). Bouncing the ball on the racket is a ball-control drill, not an event with a rule book: the number of consecutive bounces asked for is this benchmark's line; deviations: 2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, on a straight handle 0.1 m long, 0.032 m wide and 0.025 m thick, 0.14 kg in all (legal: the Laws set no size, shape or weight); its covering is one contact law on both faces (Embodied Olympics' ball-paddle pair, hand-picked, not identified) · 2.5.5 (the hand carrying the racket): the hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm jaws, at most 120 N); the handle lies along its jaws and the paddle is held by their friction alone, as a hand holds it; "in the hand" is defined by contact: the handle touches both of the gripper's jaws, and a break of up to 0.05 s is not a release · the start: nobody hands the robot a ball; it hangs at rest in front of the robot and is let go at 2.0 s · a bounce is a hit: so that the rebounds of one strong hit off a still blade are not counted, the ball must leave a counted bounce with at least 0.98 of the speed it reached the blade with (both taken at the height of the touch; a still blade returns about 0.95); a bounce that does not is not counted, and is not a fault |
| Stages | bounce 1 → bounce 2 → bounce 3 → bounce 4 → bounce 5 → bounce 6 → bounce 7 → bounce 8 → bounce 9 → bounce 10 → bounce 11 → bounce 12 → bounce 13 → bounce 14 → bounce 15 → bounce 16 → bounce 17 → bounce 18 → bounce 19 → bounce 20 |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 2.86 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; an RTX 4090 workstation, 4 CPUs, 2026-10-19, measured on the family's Session without the service); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
