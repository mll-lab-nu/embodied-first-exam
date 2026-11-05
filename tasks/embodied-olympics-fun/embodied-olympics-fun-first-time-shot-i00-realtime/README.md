# embodied-olympics-fun-first-time-shot-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-first-time-shot-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `first_time_shot` / seed 0 |
| Oracle | `full` — Reference: a scripted standing side-foot kick of the G1 (joint targets, centre-of-mass feedback ankle balance on the left foot, the right hip turned out, the swing start timed within a control step on the rolling ball), then the walking policy recovers: the ball is met at 3.1 m/s and shot at 5.0 m/s, a goal at 9.16 s; 9 of 10 perturbations (gains, release time, ramp height) succeed. In realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Shoot first time: the football rolls down a ramp and across in front of you; with one touch of a foot send it into the official goal 11 m away. (Embodied Olympics `first-time-shot`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball crosses the width of a foot in a few hundredths of a second and at right angles to the goal: the foot has to arrive with a swing or a run of its own at that moment, angled so that the pass's sideways speed is turned towards the goal, faster than the ball came, by a 33 kg robot that has no kicking skill and has to stay on its feet. The scene is dynamic (A gate releases the ball down a ramp across the robot's path at release_time_s.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. Reference: a scripted standing side-foot kick of the G1 (joint targets, centre-of-mass feedback ankle balance on the left foot, the right hip turned out, the swing start timed within a control step on the rolling ball), then the walking policy recovers: the ball is met at 3.1 m/s and shot at 5.0 m/s, a goal at 9.16 s; 9 of 10 perturbations (gains, release time, ramp height) succeed.

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: You stand facing the goal (+x), 0.3 m behind the pass line: the line through the penalty mark parallel to the goal line, which is 11.0 m beyond it. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line you face along; there is no goalkeeper. A size-5 football (0.22 m across, 0.43 kg, in air) rests against a gate on a wooden ball ramp: the ramp's foot is on the pass line 4.0 m to your left, it rises away from you at 20.0 degrees (curving into the grass at its foot) and the ball waits 1.2 m up it. At 2.0 s a servo swings the gate open; the ball rolls down the ramp and along the pass line from your left to your right. The shot is the ball's first contact with you after the release: with a foot or an ankle of yours (the parts below the shin), while the ball's centre is between the lines of the two posts (7.32 m wide, measured across the pass). Every contact within 0.15 s of the first belongs to the one touch, which is over when the ball has been clear of you for 0.03 s; it must be a shot: the ball's speed when it leaves your foot is at least 1.0 times its speed just before the foot touched it, and it is moving towards the goal line. You succeed at the moment the whole ball is then over the goal line between the posts and under the bar; after the shot it may touch the ground, the posts and the bar. You fail if any part of you other than a foot or an ankle touches the ball at any time, if the first touch is outside the lines of the posts, if the touch lasts longer than 0.15 s, if the ball leaves the foot slower than that or not towards the goal line, if you touch the ball again after the shot, if the pass rolls past the line of the far post untouched, if the whole ball crosses the goal line outside the goal, if after the shot the ball has been slower than 0.1 m/s for 1.0 s, if you touch the ramp or its gate, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 15 s.

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
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the penalty mark 11 m from the goal line, the penalty area, the goal area), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the bar), Law 12 (handball) and the glossary (a kick is a contact with the foot or the ankle). The drill itself, a square pass struck first time (one touch) at goal from the penalty mark, is a coaching exercise, not a rule-book event: the pass and the one-touch standard are the benchmark's; deviations: The pass comes from a ball ramp instead of a team-mate: the ball rests against a gate 1.2 m up a 20.0 degree wooden ramp whose foot is 4.0 m to your left on the pass line; at 2.0 s a servo (stall torque 4.1 N m) swings the gate open and gravity rolls the ball down and across, along the line through the penalty mark parallel to the goal line. The same pass in every attempt; the pitch is level and uniform (the official ball's rolling resistance, no bobble), no wind. · Law 3: no goalkeeper and no defender: a finishing drill on an open goal, not a match situation. · The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one touch, with a foot or an ankle only, while the ball is between the lines of the two posts (the shot is taken from in front of the goal). · A shot is judged by numbers instead of a referee's eye: every contact within 0.15 s of the first is the one touch, and a shot is a ball that leaves the foot at least 1.0 times as fast as it arrived (a ball that only rebounds from a foot held in its path leaves slower: it is not a shot). · Law 1: only the goal end of the field is there (the penalty area, the goal area and the mark are painted); the goal's net is a rigid cage 2.0 m deep. |
| Stages | shot → goal |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.62 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
