# embodied-olympics-fun-header-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-header-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `header` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the robot teleported 0.40 m forward and the ball's velocity set at the head contact, in 11.6, out 12.5 m/s, then into the goal); the cross comes from a football machine on the left wing 20 m away (exit 15.3 m/s with backspin, apex 4.4 m) and passes 0.45 m in front of the head, at 1.65 m, at 11.7 m/s; the keeper is a physical 80 kg board on a rail, servo-held; negatives: a still head (at most 0.85 of the speed back), chest, hand, carry, wide, headed at the keeper (saved), a second touch, too close to the machine, touching the machine, a goal without a header, a fall; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Head the cross: meet the football that is crossed to you from the wing with your head and send it into the official goal 5.5 m away, past the goalkeeper dummy. (Embodied Olympics `header`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The head has to be brought about half a metre forward into the path of a 12 m/s ball within a few centimetres and hundredths of a second, and driven into it (a step, a lunge of the trunk or a jump) so that the ball leaves faster than it came, turned through a right angle into the goal and beside the dummy; the shoulders are 25 cm from the head and must not touch. The scene is dynamic (A ball machine on the wing fires the cross toward the robot at launch_time_s.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-header-i00-privileged`).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: You stand on the edge of the goal area (the six-yard box), facing the goal; the goal line is 5.5 m ahead of you. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line you face along. A goalkeeper dummy, a board 1.9 m high, 0.6 m wide and 0.3 m thick (80.0 kg), stands on the goal line at the centre of the goal: it runs on a rail and a motor holds it there (a ball that hits it pushes it aside a little). A size-5 football (0.22 m across, 0.43 kg, in air) waits in a ball machine on the left wing, 20.0 m from you, and about 2.9 s after the start the machine crosses it: a lofted ball with backspin that passes in front of you at head height. The header is the ball's first contact after the cross: with your head, before the ball has touched the ground. Your trunk and head are one shell; the head is the part of it at or above the neck, 0.53 m above your waist joint measured along the trunk (about 1.56 m above the ground when you stand upright), and the referee judges by the points where the ball touches the shell. Every contact within 0.15 s of the first belongs to the one header, which is over when the ball has been clear of you for 0.03 s; and it must be headed, not merely met: the ball's speed when it leaves your head is at least 1.0 times its speed just before it touched. You succeed at the moment the whole ball is then over the goal line between the posts and under the bar; after the header it may touch the ground, the posts, the bar and the dummy. You fail if the ball touches the ground before your header, if it touches your shell below the neck or any other part of you at any time, if the header's contacts last longer than 0.15 s, if the ball leaves the head slower than that, if you touch the ball again after the header, if the whole ball crosses the goal line outside the goal, if after the header the ball has been slower than 0.1 m/s for 1.0 s, if your pelvis comes within 9.15 m of the ball machine before the cross has left it, if you touch the machine or the waiting ball, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 10 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the goal area 5.5 m deep, the penalty area, the penalty mark), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the bar), Law 12 (handball) and Law 13 (9.15 m from the ball until it is in play); deviations: The cross is played by a two-wheel football machine standing on the left wing 20.0 m away instead of a team-mate, the same in every attempt: its wheels drive the ball out 0.5 m above the grass at about 15 m/s with backspin (a lofted cross). Until the ball has left it, neither the ball nor the machine may be touched. · The goalkeeper is a dummy: a rigid 80.0 kg board 1.9 m high and 0.6 m wide on a carriage that runs on a rail along the goal line, held at the centre of the goal by a force-limited linear servo (at most 800.0 N): a ball that hits it pushes it aside a little and the servo brings it back. It does not dive or step towards the ball, where a goalkeeper would: an opponent's decisions cannot be simulated. · The head: the Unitree H1-2's trunk and head are one rigid shell, so the head is judged by where the ball touches that shell: at or above its neck, 0.53 m above the waist joint along the trunk (about 1.56 m above the ground when the robot stands upright; the top of the head is 0.76 m above the waist joint). A contact lower on the shell is the shoulders or the chest. · A header is judged by numbers instead of a referee's eye: every contact within 0.15 s of the first is the one header, and a header is a ball that leaves the head at least 1.0 times as fast as it arrived (a ball that only rebounds from a head held in its path leaves slower). · Law 13's distance is applied to the robot itself: until the cross is played it stays 9.15 m from the ball machine, so that the cross is played, not met at the machine. · The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one touch, with the head only, before the cross touches the ground (the task is a header, not open play). · Law 1: only the goal end of the field is there; the goal's net is a rigid cage 2.0 m deep; no wind, no other player. |
| Stages | header → goal |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.4 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
