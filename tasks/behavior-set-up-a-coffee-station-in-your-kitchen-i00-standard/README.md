# behavior-set-up-a-coffee-station-in-your-kitchen-i00-standard

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `behavior-set-up-a-coffee-station-in-your-kitchen-i00-privileged` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `set_up_a_coffee_station_in_your_kitchen` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (209 s on average); demonstration video (209 s): https://player.vimeo.com/video/1114056931 (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-07); human review in PR #71 (protocol §2.7). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Standard-mode twin of `behavior-set-up-a-coffee-station-in-your-kitchen-i00-privileged` on the same frozen instance (2026 BEHAVIOR Challenge public_test instance 301): Set up a coffee station on the kitchen countertop. The coffee maker stays on the countertop; bring the bottle of coffee from the kitchen shelf to stand next to it, put the paper coffee filter on top of the coffee maker, stand the saucer next to the coffee maker with the coffee cup on the saucer, and stand the electric kettle next to the coffee maker.

## Difficulty
Same scene, frozen instance and success rule as `behavior-set-up-a-coffee-station-in-your-kitchen-i00-privileged` (see its Difficulty). In standard mode the agent has no reset, no privileged state and no planning primitives: it sees the robot's cameras (RGB, depth on request) and its proprioception only, acts through the client, and gets one episode.

## Reference solution
None (`oracle = "none"`): no reference solution was written, and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's human teleoperation demonstrations of this activity on the R1Pro (`task.toml` `oracle_evidence`).

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar;
`live_matches_replay` is reported separately, and so are the crash-recovery fields (`sim_startups`, `resumes`,
`resume_state_mismatch`, `infra_error`); `/logs/verifier/replay.mp4`. `infra_error` = 1 (no verdict on the agent) also
when `final.json` is missing, unreadable or not finalized, or a replay did not run to its result (`replay_error`).

No oracle; human review in PR #71 (PROTOCOL §2.7), on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 6 |
| Memory | 16 GB | 15 GB |
| GPU memory | 10.5 GB | 10.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 9 GB with RCB_TEXTURE_BUDGET=0.1 (batch_eval_live vram override; live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + ws-1, 10-10): 8.3-9.0 GB); CPU 6-9 cores per trial (board 0048, ps); author: 13-16 GB of RAM per Isaac process
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 49 GiB memory. Limits measured: GPU: 9.0 GiB with RCB_TEXTURE_BUDGET=0.1, now the tasks' default (live sampler (cgroup anon, 13 AWS hosts + ws-1, 10-10); uncapped trials reached 29.0 GiB on 48 GB cards, batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: agent container docker peak 2.5 GiB over 1 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 24 GiB cap; whole trial: + the sim service's 41 GiB (docker peak 27.0 GiB, 39 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB-D + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (25, streamed at the 30 Hz control rate with the agent's `dt`; base entries are per-step targets) or of `ee_pose` (16, both end effectors, cuRobo IK per row); `observe` frames or a watch window; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service journals every control step (`journal.f64`) and resumes the same episode after a crash (resume class `approx`, docs/STANDARD_MODE.md §13.1); startup watchdog `RCB_STARTUP_TIMEOUT_S` = 1800 s |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition) |
| Budget | the agent's time is the `Agent time budget` row (the number lives in `scripts/task_cutoffs.toml`; docs/benchmarks/behavior.md) |
| Collect hook time | 37800 s: the episode end (up to 2 h through a resume) + two replays of up to 4 h + 30 min |

### Sidecar and grading
The agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`: GPU on the sidecar, the licensed dataset mounted read-only at `/data`, the service's own
record in `/out`), which owns the scene and records the episode as a (T, 25) trajectory. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes
(Isaac: only the first replay in a process is bit-exact, and two simulators do not fit in one container) and writes
`final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

### Change Log
- 2026-10-08: collect-hook time limit only. `[[verifier.collect]] timeout_sec` is 37800 s (was 21600 s): the episode end (up to 2 h through a resume) plus two replays of up to 4 h each (the privileged grader's cap of min(4 h, max(3600 s, 1200 s + steps / 2))) plus 30 min; measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s. The replays still have no limit of their own. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-09: a fall ends the episode as a failure (owner decision): once OmniGibson's own Falling rule (the base tilted more than 41.4° from upright, or more than 3 cm below the floor) has held for 10 s of simulated time, the service ends the episode with reason "failure: the robot fell over"; `/spec` `episode` states the end conditions and `reward.json` adds `task_failure`. The scene, frozen instance and BDDL goal are unchanged, so the task keeps its name; results recorded before this change are reported separately.
- 2026-10-10: infrastructure failures are no longer booked as the agent's 0, and malformed requests no longer end the episode (review of board 0067; the pass rule is unchanged). `tests/grade.py`: a missing, unreadable or unfinalized `final.json` and a fresh-process replay that died, printed no result or ran out of time give `infra_error` = 1 (`replay_error`), and a reward is always written. `environment/sim/finalize.sh`: each replay's exit code is recorded and each replay may run until the hook's own deadline (it was killed with the hook before). `environment/sim/server.py`: every field of `/submit` and `/observe` is checked before anything is executed (a null or wrong-type `dt`, `seconds`, `video_fps`, `cameras` or `note`, `video_fps` outside 1-30, a zero quaternion: 400, they ended the episode as a simulator error before); a `dt` that is not a whole number of control periods is a 400 (it was rounded: 0.25 s ran as 0.267 s); a resume whose replayed episode ends before the logged one no longer crashes every restart; `/spec` states the runaway guard (`max_control_steps` 200,000, in the instruction too). A trial that passed before still passes, so the task keeps its name; a trial scored 0 before this date whose `final.json` was unfinalized or missing was an infrastructure failure.
- 2026-10-10 (review round 2, board 0067): the client only. `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress once a minute: Isaac Sim took 620-715 s to start on the 8-vCPU evaluation hosts (more than 600 s in 38 of 60 archived trials), so the first `Robot()` raised "sim service unavailable" and a script that did not retry ended with 0 control steps. `cameras="name"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged; a trial scored 0 with 0 control steps before this date may have been this wait.
- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
