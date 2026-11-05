# embodied-olympics-fun-volleyball-set-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-volleyball-set-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_set` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: No reference solution: a CMA-ES search over the walk command, the key times and the arms' key offsets (about 150 generations) finds legal sets (out 7.0-7.5 m/s against 6.6 in, apex 4.3-4.6 m, 0.5-0.8 m from the target's centre) only with the hands 5.7-6.4 cm into each other as they rise above the forehead, which the robot's self-collision rules out; with a penalty for that, no clean set was found in 20 generations. Positive by a declared magic action. The real parts: the ball machine's toss, the walking policy at zero command with the right arm raised straight up (the hands far apart; at most 0.2 mm of self-overlap), the contact with the right hand, the flight and the landing. Injected: (1) once, 0.35 m above the palm, the descending ball is moved sideways, its height and velocity kept, onto a path that meets the palm; (2) at the first contact with the hand, its velocity is set to rise to 4.6 m and come down on the target's centre. It comes in at 6.85 m/s, leaves at 8.13 m/s, peaks at 4.74 m and lands 0.82 m from the centre; the same state hash twice. Negatives: nop (the floor before the set), the same at half speed (not a set), and the referee test's other negatives.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Set the pass: with one overhead contact of your hands, send the volleyball that comes down above you at least a metre above the net and into the outside hitter's target along the net. (Embodied Olympics `volleyball-set`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The hands (rubber fists) have to meet a 7 m/s ball above the head and drive it away faster than it came, up to nearly 4 m and 5 m along the net into a 2 m circle, in a contact of a few hundredths of a second: the angle and the speed both have to be right, and arms that are only held up return the ball too slowly. The scene is dynamic (A ball machine in the back court sends the pass toward the robot at launch_time_s.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-volleyball-set-i00-privileged`).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: You are the setter on an official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high). You stand in your front zone facing along the net: the net is 1.0 m to your right, the attack line 3.0 m from the centre line to your left, the side line of position 2 3.0 m behind you, the side line of position 4 ahead of you. A volleyball (0.21 m across, 0.27 kg, in air) is tossed to you from the back court 3.0 s after the start and comes down above you. The set is the ball's first contact after the toss, before it touches the floor: with your hands (the parts beyond the wrists; one or both), overhead (the ball's centre above the top of your head, which is 0.76 m above your waist joint along the trunk), after the ball has passed its highest point, all contacts within 0.1 s, over when the ball has been clear of you for 0.03 s. It must be a set, not a rebound: the ball leaves your hands moving upward and at least 1.0 times as fast as it was just before they touched it. Then the ball's centre must rise at least 1.0 m above the net's top, and the ball must come down in the outside hitter's target: its first contact with the floor is inside a circle of 1.0 m radius whose centre is 1.0 m from the net on your side and 1.0 m inside the side line ahead of you. That is the success. You fail if you touch the ball machine or the ball waiting in it, if the ball touches the floor before your set, if any part of you other than a hand touches the ball, if the ball's centre is not above the top of your head when your hands first touch it, if you touch it before it has passed its highest point, if the contacts last longer than 0.1 s (the ball held), if the ball leaves your hands downward or slower than that, if you touch the ball again, if it does not rise that high or comes down outside the target, if before your set your pelvis is farther from the net than the attack line (you left the front zone), if you touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 10 s. The ball cannot be gripped. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the front zone between the centre line and the attack line 3 m from it), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: not caught or thrown, one contact), Rule 11 (no contact with the net, the foot not wholly beyond the centre line); deviations: The pass is played by a two-wheel volleyball machine standing in the back court instead of a team-mate, the same in every attempt: its wheels, at equal speeds, drive the ball out 0.9 m above the floor at about 9 m/s without spin, steeply up towards the setter. · Rule 9.2 (the overhead pass with the fingers): the robot has no fingers, so the set is one contact of the hands (the parts beyond the wrists) with the ball's centre above the top of the robot's head (0.76 m above its waist joint along the trunk, about 1.80 m when it stands). 'Not caught or thrown' is a contact of at most 0.1 s (the ball cannot be gripped). · A set is judged by numbers instead of a referee's eye: the ball must leave the hands moving upward and at least 1.0 times as fast as it arrived (hands held still in the ball's path return it at no more than three quarters of its speed: that is a rebound, not a set); it must be played after it has passed its highest point, by a setter who has stayed in the front zone. · Nobody attacks the set: a good set is defined as volleyball coaching grades it, a ball that rises at least 1.0 m above the net and comes down in the outside hitter's target, a circle of 1.0 m radius at position 4, judged where the ball first touches the floor. · Rule 2: the net is a rigid panel 1 m deep and the posts and antennas are rigid (a real net is a mesh under tension that gives); a robot touching any of them commits the Rule 11 fault all the same. · No team-mates or opponents, no wind. |
| Stages | set → above the net → in the target |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.4 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
