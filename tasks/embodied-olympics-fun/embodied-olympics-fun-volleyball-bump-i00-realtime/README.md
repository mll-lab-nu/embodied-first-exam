# embodied-olympics-fun-volleyball-bump-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-volleyball-bump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_bump` / seed 0 |
| Oracle | `full` — Reference, on Unitree's actuator data (H2-class legs, rotor inertia, joint friction): a walk forward and to the left, then a forearm platform held through the contact; the walk, key times and the platform's joint offsets from CMA-ES, with penalties for the arms coming within 5 cm of each other and for any arm passing into the body. The serve comes from the ball machine behind the far end line; the ball meets the right forearm (it also brushes the wrist-pitch link by 2 mm), comes in at 11.3 m/s, leaves at 8.0 m/s, rises to 3.30 m and lands 0.13 m from the target centre; success after 5.85 s. The arms stay at least 2.9 cm apart and no arm passes into the body (at most 0.4 mm). It is open loop on the one serve: 4 of 6 perturbations succeed (servo gains x0.97 / x1.03 and the timing 10 ms earlier / later pass; a machine launch speed 0.5 % lower or higher fails, because the ball misses the platform). In realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Receive the serve: pass the volleyball that is served over the net to you with your forearms, in one contact, above net height and into the setter's target at the net. (Embodied Olympics `volleyball-bump`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The arms have to be made into a platform 0.7 m to the side and in front of where the robot stands, within about four seconds of a walking policy that manages half a metre per second sideways, and angled so that an 11 m/s ball rebounds 2 m up and 5 m forward into a 2 m circle: a few degrees of platform angle are a metre at the target. The scene is dynamic (A ball machine behind the far end line serves toward the robot at launch_time_s.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. Reference, on Unitree's actuator data (H2-class legs, rotor inertia, joint friction): a walk forward and to the left, then a forearm platform held through the contact; the walk, key times and the platform's joint offsets from CMA-ES, with penalties for the arms coming within 5 cm of each other and for any arm passing into the body. The serve comes from the ball machine behind the far end line; the ball meets the right forearm (it also brushes the wrist-pitch link by 2 mm), comes in at 11.3 m/s, leaves at 8.0 m/s, rises to 3.30 m and lands 0.13 m from the target centre; success after 5.85 s. The arms stay at least 2.9 cm apart and no arm passes into the body (at most 0.4 mm). It is open loop on the one serve: 4 of 6 perturbations succeed (servo gains x0.97 / x1.03 and the timing 10 ms earlier / later pass; a machine launch speed 0.5 % lower or higher fails, because the ball misses the platform).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: You stand in your own half of an official volleyball court (9.0 m by 9.0 m on each side of the net), facing the net, 6.0 m from it, midway between the side lines. The net's top is 2.43 m high. A volleyball (0.21 m across, 0.27 kg, in air) is served over the net from behind the far end line 3.0 s after the start: a float serve, without spin, that comes down in your part of the court. The pass is the ball's first contact after the serve, on your side of the net and before it touches the floor: with your forearms or hands (one arm or both; the arm from the elbow down), all contacts within 0.1 s, over when the ball has been clear of you for 0.03 s. After it the ball's centre must rise above the height of the net's top, and the ball must come down in the setter's target: its first contact with the floor is inside a circle of 1.0 m radius whose centre is 1.0 m from the net on your side and 1.5 m to the right of the court's middle (to your right as you face the net). That is the success. You fail if you touch the ball machine or the ball waiting in it, if the ball touches the floor before your pass, if any part of you other than a forearm or a hand touches the ball, if the pass's contacts last longer than 0.1 s (the ball held), if you touch the ball again after the pass, if you touch the ball before it has crossed the net, if the ball comes down outside the target or without having risen above the net's height, if you touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 10 s. The ball cannot be gripped.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 8 GiB | 8192 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## Details
| | |
|---|---|
| Category | football-and-volleyball |
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines 3 m from the centre line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: the ball may touch any part of the body, it must not be caught or thrown), Rule 11 (no contact with the net, the foot not wholly beyond the centre line), Rule 14.5 (the serve may not be blocked); deviations: Rule 12 (the service): the serve is played by a two-wheel volleyball machine on a stand 0.6 m behind the far end line instead of an opponent, the same in every attempt: its wheels, at equal speeds, drive the ball out 2.6 m above the floor at about 14 m/s without spin (a float serve); the ball follows MuJoCo's drag model, without a float serve's sideways wobble. · Rule 9.2 lets a team-mate play the ball next; here nobody does, and a good reception is defined as volleyball coaching grades it: the pass rises above the net's height and comes down in the setter's target, a circle of 1.0 m radius 1.0 m from the net between positions 2 and 3, judged where the ball first touches the floor. · The family asks for the forearm pass: only the forearms and the hands (the arm from the elbow down) may touch the ball, where Rule 9.2.1 allows any part of the body. 'Not caught or thrown' is a contact of at most 0.1 s (the ball cannot be gripped). · Rule 2: the net is a rigid panel 1 m deep and the posts and antennas are rigid (a real net is a mesh under tension that gives); a robot touching any of them commits the Rule 11 fault all the same. · No team-mates or opponents, no wind. |
| Stages | pass → above the net height → in the target |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.44 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
