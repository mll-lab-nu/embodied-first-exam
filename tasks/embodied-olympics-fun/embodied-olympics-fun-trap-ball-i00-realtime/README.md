# embodied-olympics-fun-trap-ball-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-trap-ball-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `trap_ball` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the robot teleported at t = 0 to stand in the real pass, which reaches its foot; the ball set to 0.3 m/s as it comes off the foot, under control 1.45 s after the touch); the pass is played by a football machine 15 m away (exit 9.6 m/s, -4 deg, 34 rad/s topspin), skids and hops, and arrives 1.97 s later at 5.9 m/s, 0.5 m to the right; negatives: a planted foot (the ball ends 4.3 m away or in an arm), rolling away, the first touch on the shin, a handball, too close to the machine, touching the machine; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Trap the pass: take the football that is passed along the ground past you with a foot, and bring it to rest within a metre of you inside three seconds. (Embodied Olympics `trap-ball`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A foot has to be in the way of a 6 m/s ball at the right hundredth of a second, half a metre to the side, and it has to take the pace off: a ball that hits a planted foot bounces a few metres away, far outside the metre, and the walking policy cannot catch a ball that is faster than it. The scene is dynamic (A ball machine 15 m away fires a ground pass toward the robot at launch_time_s.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-trap-ball-i00-privileged`).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: A size-5 football (0.22 m across, 0.43 kg) waits in a ball machine 15.0 m ahead of you and 0.5 m to your right; about 3.2 s after the start the machine plays it along the ground at about 9.6 m/s, parallel to the way you face, so that it goes by 0.5 m to the right of where you stand. Your first touch must be with a foot or an ankle (the parts below the shin). After it you may play the ball as often as you like with any part of you except the hands and the arms. You succeed when, within 3.0 s of the first touch, the ball is under control: slower than 0.2 m/s for 0.5 s without a break, its centre all that time within 1.0 m of your pelvis (measured along the ground), you on your feet. You fail if the first part of you that the ball touches is not a foot or an ankle, if a hand or an arm touches the ball at any time (handball), if 3.0 s after the first touch the ball is not under control, if your pelvis comes within 9.15 m of the ball machine before the pass has left it, if you touch the machine or the waiting ball, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 10 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | IFAB Laws of the Game 2025/26: Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 12 (handball: the hand or the arm), Law 13 (9.15 m from the ball until it is in play) and the glossary (a kick is a contact with the foot or the ankle). Receiving a pass is a skill, not a rule-book event: the pass and the control standard (first touch with a foot, the ball at rest within 1 m inside 3 s) are the benchmark's; deviations: The pass is played by a two-wheel football machine standing on the grass 15.0 m away instead of a team-mate, the same in every attempt: its wheels drive the ball out 0.55 m above the grass, nearly level, at about 9.6 m/s with topspin (the two wheels give it at most about 35 rad/s, less than a rolling ball's): it skids and hops low along the grass and reaches the robot at about 6.0 m/s, as the family's former 8 m/s rolling pass did. The pitch is level and uniform (the official ball's rolling resistance, no bobble), no wind. · Law 13's distance is applied to the robot itself: until the pass is played it stays 9.15 m from the ball machine, so that the pass is played, not met at the machine. |
| Stages | first touch → control |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.54 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
