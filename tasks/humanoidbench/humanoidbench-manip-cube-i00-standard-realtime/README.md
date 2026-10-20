# humanoidbench-manip-cube-i00-standard-realtime

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `humanoidbench-manip-cube-i00-privileged` |
| Simulator / robot | `humanoidbench` / `unitree-h1hand` |
| Family / instance | `cube` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and published RL reaches 60% of the bar (paper 135, FastTD3 221, bar 370); human review in PR #83 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 50 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0` |

## Task
Standard-realtime mode (robot as a service on a clock that does not stop, `eai-standard/2.3`, PROTOCOL §4b) of
`humanoidbench-manip-cube-i00-privileged`: the same frozen instance and the same success rule as it and as
`humanoidbench-manip-cube-i00-standard`, but time does not stop. Once an episode's clock starts (its first
`submit`), the robot runs at 50 Hz in real time and holds its last servo targets while the agent thinks, so
the agent drives it with a controller program of its own that streams targets through the client.
HumanoidBench runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for rendering;
`environment/sim/rcb_realtime.py` runs the clock), which holds the reward, judges the episode, records every
control step it ran, judges the episode as it runs and, after the verdict, renders its video from the recorded
trajectory; the verifier grades the sidecar's record in a container of its own (`tests/Dockerfile`, no
network).

Note: the head cameras see the cube above one palm. `room_camera` looks at the hands close up
(`RCB_ROOM_CAMERA_POSE` in the compose file) and sees both hands with their cubes and, floating above them,
the goal orientation (upstream's `target_cube`); the legs are out of frame.

## Difficulty
See `humanoidbench-manip-cube-i00-privileged`'s README; here the agent also has no state, no reward and no
simulator of its own, and 50 resets instead of unlimited ones, as in `humanoidbench-manip-cube-i00-standard`.
On top of that the robot does not wait: a model's turn takes seconds and the H1 falls within a few seconds of
robot time without active balance, so the agent cannot steer it turn by turn. It has to write a controller
that closes the loop at the control rate from proprioception, run it in the background, and improve it between
episodes from what it observed.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically removes the
interesting tasks. What replaces it (docs/protocol/README.md §2.7): the floor above (doing nothing cannot
pass), the evidence that the task has a solution (`oracle_evidence` in task.toml), and a human reviewer.

## Verification
`success` = live success: the episode the sim service ran reached the pass mark (HumanoidBench's own rule,
judged on the live simulator), for the last episode; nothing is replayed to grade it (owner, 2026-10-17, board
0151). The scene's start is checked against the frozen instance's recorded state when an episode begins
(`instance_mismatch`, infrastructure). The trajectory records the servo targets the simulator applied at each
control step (`trajectory_live.f64`, `trajectory.npz`), not the ones the agent submitted, so it reproduces the
live run whatever the timing was (the video is rendered from it after the verdict); `ticks.f64` records each
step's wall time and the call that planned it, `calls.jsonl` and `submitted.f64` every call and every row as
sent, and `final.json` the clock's lag (`max_lag_s`, `stalls`) and the held and late steps. `tests/grade.py`
reads `/data/final.json` and copies the evidence to `/logs/verifier/` (`replay.mp4`). After the agent's first
command, a simulator error raised by a control step and a simulator crash inside a control step (a fatal
signal) are the agent's 0; a kill, a crash outside a control step, anything before the first command, a failed
resume and a reset that does not rebuild the scene are infrastructure (`infra_error = 1`; owner, 2026-10-17,
docs/protocol/standard_mode.md). No oracle; human review in PR #83. `nop` scores 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 3 GB | 3 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 1.1-2.3 GB, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: privileged container median 2.2 GB (p90 11 GB when agents run parallel rollouts), sim 0.7 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 15 GiB memory. Limits measured: GPU: 2.3 GiB (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: no samples of the agent's container; floor 8 GiB (at most the 16 GiB cap); whole trial: + the sim service's 7 GiB (from the minimum: no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| mode / sensors | standard-realtime: head-camera RGB + joint angles and velocities (HumanoidBench's own `image` and `proprio` sensors), a pelvis IMU and a camera fixed in the room; no root pose, no cube poses, no goal orientation, no reward; 50 resets (a new episode from the frozen start each, paused until its first `submit`; only the last episode is graded) |
| time | the episode's clock starts at its first `submit` (or `get_obs(seconds > 0)`) and runs one control step every 0.02 s of wall time until the episode ends; `submit` writes a plan of future targets (from step `at`) and answers at once; the last target is held when the plan runs out |
| action space | HumanoidBench's own: 61 normalised position targets, 50 Hz, streamed one row at a time or in chunks of up to 10 s |
| knobs (compose env) | `RCB_SLOWDOWN` (1: real time, the official configuration; S: one control step every S x 0.02 s, results reported apart from S = 1), `RCB_RESET_BUDGET` (50: HumanoidBench's configuration, an exception to the mode's default of 0, PROTOCOL §4.5), `RCB_OBS_PROPRIO` (1), `RCB_OBS_IMU` (1), `RCB_OBS_ROOM_CAMERA` (1), `RCB_OBS_DEPTH` (0): the defaults are this task's configuration; a run that changes one is reported separately, and `episode.jsonl` records the `/spec` it ran under |
| agent API | `environment/rcb_client.py` (the realtime client; its docstring is the reference); `instruction.md` lists the endpoints |
| physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (tasks/humanoidbench/README.md, Physics). |

### Change Log
- 2026-10-08: base image 0.1.6 -> 0.2.0: MuJoCo 3.3.7 instead of upstream's 3.1.6
  (tasks/humanoidbench/README.md, Physics). The pass rule and verifier are unchanged, so the task keeps its
  name; results recorded on 0.1.6 are other physics and are reported separately.
- 2026-10-09: the service no longer holds waiting requests while it is behind its clock: it serves one after
  each control step it catches up on (before, a request waited until the next stall re-anchored the clock: up
  to MAX_LAG_S, 0.5 s, here, and seconds on a slower simulator such as BiGym 2.0's); final.json adds
  `max_queue_wait_s`. The robot's episode, the pass rule and the verifier are unchanged.
- 2026-10-10: the sim service marks `final.json` `finalized` the moment the verdict is written, before the
  replay video is rendered (`video_pending` while it renders), and the collect hook's waits run on the clock,
  inside its timeout: a slow, hung or killed video render no longer turns a graded episode into `infra_error`.
  `reward.json` adds `sim_error` and carries `deterministic` in every branch. In this mode also: a refused
  `/reset` (budget used up, bad request) no longer answers a pending `get_obs(seconds=...)` early, and
  `final.json`'s realtime counters (`stalls`, `held_steps`, `late_steps`, `max_lag_s`, `max_queue_wait_s`)
  cover the whole trial after a crash-resume. The shared realtime layer no longer combines plan rows of
  different action types (a RoboOlympics bug); this task has one action type, so its plan behaves as before.
  The scene, instance and pass rule are unchanged, so the task keeps its name; every verdict that was reached
  before is the same now.
- 2026-10-10 (2; second review round, M1): the agent's requests can no longer slow the episode's clock.
  Request bodies are read, decoded and checked off the simulator's thread (more than 1 MiB of JSON text by a
  child process), a refused request never reaches it, waiting requests are served once the clock has caught
  up, and the cameras are rendered at most once per control step however many requests ask (before: a flood of
  refused 21 MB bodies left 3 control steps in 6 s instead of 300, and four parallel `/observe` loops slowed
  the robot's time by a fifth). An `/observe` may therefore take longer to answer while the service is behind,
  or after a render that alone took more than 0.5 s; what an accepted `/submit` does, and when, is unchanged.
  `final.json` and `reward.json` add the clock's record (`clock_s`, `stalls`, `stalled_s`, `stalled_share`,
  `max_lag_s`, now the true maximum, `requests_refused`, `request_mb`, `request_busy_s`): evidence, which
  decides no verdict. A negative `Content-Length` is refused unread, and a simulator that fails inside
  `POST /reset` ends the episode as `error` (`infra_error = 1`), not `reset`. The scene, instance and pass
  rule are unchanged, so the task keeps its name.
- 2026-10-10 (3; third review round): the sim service (`environment/sim/rcb_service.py`) renders and returns a
  camera named more than once in `cameras` once (N copies of one name made it build N x N images within the
  frame budget, which could exhaust its memory), and a service that has given up on the episode (it could not
  resume it after its crashes) answers every request with 409 and the reason instead of not listening. The
  scene, instance, pass rule and every verdict reached before are unchanged, so the task keeps its name.
- 2026-10-17 (owner): graded by the live episode: `success` = the episode the sim service ran
  reached the pass mark (the same rule, judged as it ran), and no grading replay runs (no `replay_success` /
  `deterministic` any more; `final.json` has `graded_by = "live"`, `replays = 0`, `reward.json`
  `graded_by_live = 1`). The video is one render pass over the trajectory after the verdict, as before. The
  scene's start is checked when an episode begins: a scene that does not start at the frozen instance's
  recorded state gives up as infrastructure (`instance_mismatch`). The scene, instance, pass rule and the
  agent's interface are unchanged, so the task keeps its name; every archived verdict is the same under the
  live rule. Also (owner, 2026-10-17): after the agent's first command a simulator error raised by a control
  step is the agent's 0 (`sim_error = 1`, no longer `infra_error`), and so are simulator crashes with a fatal
  signal inside a control step (`sim_crashed_on_call`); kills, failed resumes and failures before the first
  command stay infrastructure.
