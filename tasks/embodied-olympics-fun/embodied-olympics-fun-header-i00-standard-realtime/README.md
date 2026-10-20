# embodied-olympics-fun-header-i00-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-header-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `header` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/embodied-olympics/tests/test_header.py: positive by injection (the real cross onto the head, the ball's velocity set at the contact: in at 11.7, out at 14.6 m/s, into the goal); negatives: a still head (the ball leaves slower than it came), the chest, a hand, wide, a second touch, too close, in without a header. An open-loop hip lunge moves the head at 6.2 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Head the cross: meet the football that is crossed to you from the wing with your head and send it into the official goal 5.5 m away, past the goalkeeper dummy. (Embodied Olympics `header`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The head has to be brought about half a metre forward into the path of a 12 m/s ball within a few centimetres and hundredths of a second, and driven into it (a step, a lunge of the trunk or a jump) so that the ball leaves faster than it came, turned through a right angle into the goal and beside the dummy; the shoulders are 25 cm from the head and must not touch. The scene is dynamic (`scripts/task_dynamics.toml`: The cross is launched toward the robot at launch_time_s.), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

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
rules: You stand on the edge of the goal area (the six-yard box), facing the goal; the goal line is 5.5 m ahead of you. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line you face along. A goalkeeper dummy, a board 1.9 m high, 0.6 m wide and 0.3 m thick, stands still on the goal line at the centre of the goal. A size-5 football (0.22 m across, 0.43 kg, in air) waits on the ground on the left wing, 20.0 m from you, and 3.0 s after the start it is crossed: a lofted ball with backspin that passes in front of you at head height. The header is the ball's first contact after the cross: with your head, before the ball has touched the ground. Your trunk and head are one shell; the head is the part of it at or above the neck, 0.53 m above your waist joint measured along the trunk (about 1.56 m above the ground when you stand upright), and the referee judges by the points where the ball touches the shell. Every contact within 0.15 s of the first belongs to the one header, which is over when the ball has been clear of you for 0.03 s; and it must be headed, not merely met: the ball's speed when it leaves your head is at least 1.0 times its speed just before it touched. You succeed at the moment the whole ball is then over the goal line between the posts and under the bar; after the header it may touch the ground, the posts, the bar and the dummy. You fail if the ball touches the ground before your header, if it touches your shell below the neck or any other part of you at any time, if the header's contacts last longer than 0.15 s, if the ball leaves the head slower than that, if you touch the ball again after the header, if the whole ball crosses the goal line outside the goal, if after the header the ball has been slower than 0.1 m/s for 1.0 s, if your pelvis comes within 9.15 m of the waiting ball before it is crossed, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 10 s. The waiting ball cannot be touched. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the goal area 5.5 m deep, the penalty area, the penalty mark), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the bar), Law 12 (handball) and Law 13 (9.15 m from the ball until it is in play); deviations: The cross is a scripted launch: a fixed lofted kick with backspin from a point 20.0 m away on the left wing, the same in every attempt, instead of a team-mate. · The goalkeeper is a dummy, a rigid board 1.9 m high and 0.6 m wide that stands still on the goal line at the centre of the goal: an opponent cannot be simulated. · The head: the Unitree H1-2's trunk and head are one rigid shell, so the head is judged by where the ball touches that shell: at or above its neck, 0.53 m above the waist joint along the trunk (about 1.56 m above the ground when the robot stands upright; the top of the head is 0.76 m above the waist joint). A contact lower on the shell is the shoulders or the chest. · A header is judged by numbers instead of a referee's eye: every contact within 0.15 s of the first is the one header, and a header is a ball that leaves the head at least 1.0 times as fast as it arrived (a ball that only rebounds from a head held in its path leaves slower). · Law 13's distance is applied to the robot itself: until the cross is played it stays 9.15 m from the ball, so that the cross is played, not met at the kicker. · The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one touch, with the head only, before the cross touches the ground (the task is a header, not open play). · Law 1: only the goal end of the field is there; the goal's net is a rigid cage 2.0 m deep; no wind, no other player. |
| Stages | header → goal |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 3.92 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; an RTX 4090 workstation, 4 CPUs, 2026-10-14); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
