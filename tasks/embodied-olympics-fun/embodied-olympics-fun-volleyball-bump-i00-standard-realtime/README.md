# embodied-olympics-fun-volleyball-bump-i00-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-volleyball-bump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_bump` / seed 0 |
| Oracle | `full` — Reference: a walk to where the serve comes down, then a forearm platform on the walking policy, from a technique found offline by CMA-ES (Embodied Olympics' method): 11.4 m/s in, 7.3 m/s out, up to 3.08 m, down 0.13 m from the target's centre. Open loop on the frozen start, not robust. Referee test negatives: the passive rebound, below net height, the body, a second touch, held, under the net, a net touch, over the centre line In standard-realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Receive the serve: pass the volleyball that is served over the net to you with your forearms, in one contact, above net height and into the setter's target at the net. (Embodied Olympics `volleyball-bump`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The arms have to be made into a platform 0.7 m to the side and in front of where the robot stands, within about four seconds of a walking policy that manages half a metre per second sideways, and angled so that an 11 m/s ball rebounds 2 m up and 5 m forward into a 2 m circle: a few degrees of platform angle are a metre at the target. The scene is dynamic (The ball is launched toward the robot at launch_time_s.), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. Reference: a walk to where the serve comes down, then a forearm platform on the walking policy, from a technique found offline by CMA-ES (Embodied Olympics' method): 11.4 m/s in, 7.3 m/s out, up to 3.08 m, down 0.13 m from the target's centre. Open loop on the frozen start, not robust. Referee test negatives: the passive rebound, below net height, the body, a second touch, held, under the net, a net touch, over the centre line

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: You stand in your own half of an official volleyball court (9.0 m by 9.0 m on each side of the net), facing the net, 6.0 m from it, midway between the side lines. The net's top is 2.43 m high. A volleyball (0.21 m across, 0.27 kg, in air) is served over the net from behind the far end line 3.0 s after the start: a float serve, without spin, that comes down in your part of the court. The pass is the ball's first contact after the serve, on your side of the net and before it touches the floor: with your forearms or hands (one arm or both; the arm from the elbow down), all contacts within 0.1 s, over when the ball has been clear of you for 0.03 s. After it the ball's centre must rise above the height of the net's top, and the ball must come down in the setter's target: its first contact with the floor is inside a circle of 1.0 m radius whose centre is 1.0 m from the net on your side and 1.5 m to the right of the court's middle (to your right as you face the net). That is the success. You fail if the ball touches the floor before your pass, if any part of you other than a forearm or a hand touches the ball, if the pass's contacts last longer than 0.1 s (the ball held), if you touch the ball again after the pass, if you touch the ball before it has crossed the net, if the ball comes down outside the target or without having risen above the net's height, if you touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 10 s. The ball cannot be gripped, and it cannot be touched while it waits to be served.

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
| Category | football-and-volleyball |
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines 3 m from the centre line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: the ball may touch any part of the body, it must not be caught or thrown), Rule 11 (no contact with the net, the foot not wholly beyond the centre line), Rule 14.5 (the serve may not be blocked); deviations: Rule 12 (the service): the serve is a scripted launch, a float serve (no spin) of about 14 m/s from 0.6 m behind the far end line, the same in every attempt, instead of an opponent; the ball follows MuJoCo's drag model, without a float serve's sideways wobble. · Rule 9.2 lets a team-mate play the ball next; here nobody does, and a good reception is defined as volleyball coaching grades it: the pass rises above the net's height and comes down in the setter's target, a circle of 1.0 m radius 1.0 m from the net between positions 2 and 3, judged where the ball first touches the floor. · The family asks for the forearm pass: only the forearms and the hands (the arm from the elbow down) may touch the ball, where Rule 9.2.1 allows any part of the body. 'Not caught or thrown' is a contact of at most 0.1 s (the ball cannot be gripped). · No team-mates or opponents, no wind. |
| Stages | pass → above the net height → in the target |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 2.69 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; an RTX 4090 workstation, 4 CPUs, 2026-10-14); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
