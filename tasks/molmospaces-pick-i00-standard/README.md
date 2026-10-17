# molmospaces-pick-i00-standard

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `molmospaces-pick-i00-privileged` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `pick` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-pick-i00-privileged__Y6SSCTZ (run codex-gpt6_1_sol-high, batch molmo-v2-sol, 2026-10-16); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.5` |

## Task
Standard-mode twin of `molmospaces-pick-i00-privileged` (the same frozen MolmoSpaces episode): Pick up the pie. The agent gets only the
`eai-standard/2.2` client (docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`), which owns the episode, serves cameras, proprioception and upstream's kinematic
model, and records every executed row. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, replays the trajectory in two fresh processes and writes `final.json`; the verifier grades those artifacts
in a separate sandbox (`tests/Dockerfile`).

## Difficulty
That of `molmospaces-pick-i00-privileged` (its README), without resets, object poses or a success check: every move is planned from camera
images, depth and the robot's own proprioception, within the benchmark's 20 s of simulated time.

## Reference solution
None is shipped (see `molmospaces-pick-i00-privileged`).

## Verification
`success` = live success ∧ replay success ∧ deterministic. The episode follows upstream's evaluation: one upstream
`Task.step` per executed row; it ends at upstream's `is_done()` (303 control steps), at the agent's `done`,
or when the agent's time is up; then upstream's `judge_success()` on the final state: the object touches the robot and nothing else, and it is at least 1 cm higher than where it started. The two fresh-process
replays of the recorded rows (`rcb_molmospaces.py replay`) must succeed and end in the same state; `replay.mp4` is
rendered after the verdict. `infra_error = 1` (no verdict on the agent): no, an unreadable or an unfinished `final.json`,
a service that gave up after crashes between calls or never ended the episode, a replay process without a result, a
frozen start the image no longer builds. No oracle; human review in PR #276 (PROTOCOL §2.7: per family, this task
and its twin, a positive example and the `nop` result).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 6 GB | 5 GB |
| GPU memory | 3.5 GB | 3.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).
- Measured: GPU 2.7 GB on L40S, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory and CPU author estimate (MuJoCo, CPU physics, EGL rendering)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 18 GiB memory. Limits measured: GPU: 2.7 GiB on a 48 GB card (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)); one trial on a 24 GB card peaked at 18.4 GiB and would exceed: calibrate -> max(1.5 x peak, peak + 4); memory: no samples of the agent's container; floor 8 GiB (at most the 16 GiB cap); whole trial: + the sim service's 10 GiB (from the minimum: no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9, benchmark `molmospaces-bench-v2/20260415`, package `procthor-objaverse/FrankaPickHardBench/FrankaPickHardBench_20260206_json_benchmark` (Pick-v2-classic (MolmoBot benchmarks)), episode 806 |
| World-frame information | none in the texts: object names and the goal only; the robot's own pose and the camera calibration come from the service (docs/benchmarks/molmospaces.md) |
| Generator | `scripts/molmospaces/mk_tasks.py`; docs/benchmarks/molmospaces.md |

### Change Log
- 2026-10-10: how a trial that could not be graded is recorded, and request checks; the frozen episode, upstream's success rule and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: a missing, unreadable or unfinished `final.json` (the collect hook never wrote its verdict) is `infra_error = 1` (was the agent's 0, or no reward at all); a reward is always written. `environment/sim/finalize.sh`: `final.json` is written whole and renamed into place, and a replay is ended at its limit (500 s, never past the hook's deadline; a replay without a result was and is `infra_error`). `environment/sim/server.py`: a null or wrongly typed request field (`dt`, `seconds`, `cameras`, `note`) is a 400 before anything moves (was a 500 that ended the episode); `get_obs(seconds=...)` reports the seconds it ran (whole control steps), not the seconds asked for. A pass before this change is a pass after it; results recorded before it may hold infrastructure failures counted as the agent's 0.
- 2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (no effect on this benchmark, whose service is up within a minute); `cameras="name"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready). Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-16: the frozen episode, the base image and the replay limit. The frozen episode is the one the 2026-10-16 selection rule picks (docs/benchmarks/molmospaces.md, Instances: the target small in the fixed cameras for the pick families, a longer travel for open and close); for every family but navigate-to and open-door that is a different episode, so results recorded on those tasks before this date are of another episode. Base image 0.2.5 (the assets of the new episodes). `environment/sim/finalize.sh`: the two grading replays share the time left before the hook's deadline (1740 s of its 1800 s; the first gets half of it, about 865 s after a prompt end) instead of 500 s each, which ended genuine successes on a loaded host as `replay_failed` + `infra_error`; the verdict, the pass rule and upstream's success rule are unchanged. `instruction.md` now states the pass rule (live success, both replays succeed and end in the same state), which only this README stated.
