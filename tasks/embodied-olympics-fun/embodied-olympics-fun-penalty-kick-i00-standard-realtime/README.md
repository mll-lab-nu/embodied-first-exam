# embodied-olympics-fun-penalty-kick-i00-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-penalty-kick-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `penalty_kick` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_penalty_kick.py: positive by injection (a real walk-up and foot contact, the ball's velocity set at the contact to 20 m/s into the corner; also a chip over the keeper); negatives: an 8 m/s shot saved by the keeper, a weak kick, wide, over the bar, a second touch, in without a kick, a body contact. Beating the keeper takes about 12 m/s to a corner; a G1 foot running into the ball at 4 m/s gives 3 to 5 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Take a penalty kick: with one kick of a foot, send the ball that lies on the penalty mark into the official goal 11 m away, past the goalkeeper dummy. (Embodied Olympics `penalty-kick`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The dummy reaches any ball that needs more than about 1.3 s for the 11 m: the kick has to send a 0.43 kg ball off at about 12 m/s or more and into a corner (or over the dummy and under the bar). The robot weighs 33 kg and has no kicking skill; a foot that merely runs into the ball at the running policy's 4 m/s sends it off at 3 to 5 m/s. The scene is dynamic (`scripts/task_dynamics.toml`: A goalkeeper dummy on a slide is driven by the referee toward the ball after the kick.), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-penalty-kick-i00-privileged`).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: A size-5 football (0.22 m across, 0.43 kg, in air) lies at rest on the penalty mark, 3.0 m straight ahead of you; the goal line is 11.0 m beyond the mark. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line through you and the mark. A goalkeeper dummy, a board 1.9 m high, 0.6 m wide and 0.3 m thick, stands on the goal line at the centre of the goal; from 0.25 s after your kick it slides along the goal line at up to 3.0 m/s towards the point where the ball, going on as it moves at that moment, would cross the line, and it blocks the ball. The kick is a contact of a foot or an ankle of yours with the ball (the parts below the shin); every such contact within 0.15 s of the first belongs to the one kick. You succeed at the moment the whole ball is over the goal line between the posts and under the bar; it may touch the posts, the bar, the dummy and the ground on the way. You fail if any other part of you touches the ball at any time, if a foot touches the ball again later than 0.15 s after the first contact (a second touch), if the ball is not moving towards the goal line at the end of the kick, if the whole ball crosses the goal line outside the goal, if after the kick the ball has been slower than 0.1 m/s for 1.0 s, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the penalty mark 11 m from the goal line, the penalty area, the goal area and the penalty arc), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 14 (the penalty kick: the ball at rest on the mark, kicked forward, the goalkeeper on the goal line between the posts until the kick), Law 10 (kicks from the penalty mark: one kick, which is over when the ball stops moving or goes out of play; the kicker may not play the ball a second time) and the glossary (a kick is a contact with the foot or the ankle); deviations: Law 14 (the goalkeeper): the goalkeeper is a dummy, a rigid board 1.9 m high and 0.6 m wide standing on the goal line. It starts at the centre and, from 0.25 s after the kick, slides along the line at up to 3.0 m/s towards the point where the ball's velocity of that moment would take it over the goal line; it stays between the posts and neither dives, jumps nor uses hands. An opponent cannot be simulated otherwise. · Law 14 (the kick): the referee takes every contact of a foot with the ball within 0.15 s of the first as the one kick; any later contact is a second touch. A referee's eye is replaced by this number. · Law 14 says the ball is kicked; the Laws do not name the part of the leg. Here the kick is made with a foot or an ankle (the parts below the shin): a contact of the ball with a shin or any other part is a failure. · Law 1: only the goal end of the field is there (the penalty area, the goal area, the mark and the arc are painted); the goal's net is a rigid cage 2.0 m deep; there is no wind and no other player. |
| Stages | kick → goal |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 3.89 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; an RTX 4090 workstation, 4 CPUs, 2026-10-14); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
