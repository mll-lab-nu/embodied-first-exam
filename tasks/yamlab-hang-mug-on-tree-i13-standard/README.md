# yamlab-hang-mug-on-tree-i13-standard

| | |
|---|---|
| Benchmark | YAMLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `yamlab-hang-mug-on-tree-i13-privileged` |
| Simulator / robot | `yamlab` / `i2rt-yam-bimanual` |
| Family / instance | `hang_mug_on_tree` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-yamlab:0.1.0` |

## Task
Standard-mode twin of `yamlab-hang-mug-on-tree-i13-privileged` (same frozen instance: YAMLab's objects `mug` = `Mug/mug_013` and `mug_tree` = `MugTree/mug_tree_013` as placed in teleoperation
demonstration `hangmug_013.hdf5 demo_1`, both arms at the home pose): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory of YAMLab's own actions. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes and
writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `yamlab-hang-mug-on-tree-i13-privileged` (its README), without resets, object poses or the success signal: every step of a two-arm
manipulation is planned from three cameras (one static, two on the wrists), depth and the robot's own proprioception, and a
missed grasp or a dropped object stays that way.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's actions (`solution/oracle_qpos.npy`: the 1 s ramp from the home
pose and the recorded teleoperation demonstration `hangmug_013.hdf5 demo_1`, one row per control step, `hold`) as one-second
`joint_position` chunks through the client; after a service crash it waits for the resumed episode and continues from the
control step the service reports.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's
collect hook; `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4`. YAMLab's success check (evaluation thresholds) is evaluated after
every control step; the episode ends at the first step where every stage has latched, live and in the replays. Oracle: the
live episode and both replays end in the privileged oracle's final state (hash `321a9d8be0abd35a`). `nop`: the episode ends
on the time-out with no stage reached, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 16 GB | 15 GB |
| GPU memory | 5 GB | 5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 3.8-4.0 GB per trial, anon memory 11.1-11.8 GB, CPU p90 5.8-8.7 cores over 12 trials, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + ws-1, 10-10); vram_profile peaks 5.5-6.5 GB on 24 GB cards; board 0048: about 11 GB RAM and 8 CPUs per simulator; verifier 7.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 27 GiB memory. Limits measured: GPU: 10.4 GiB on a 48 GB card, 6.5 on 24 GB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: agent container docker peak 1.5 GiB over 1 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 24 GiB cap; whole trial: + the sim service's 19 GiB (docker peak 12.4 GiB, 1 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where every stage of YAMLab's success check has latched, when a task object falls off the table, when the agent's time is up, on a simulator error, or at the technical cap of 100,000 control steps (`spec.max_control_steps`, reason `step_guard`; 55.6 min of simulated time); the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (14: YAMLab's own action, streamed at the 30 Hz control rate with the agent's `dt`, a multiple of 1/30 s) or `ee_pose` (16: both tool frames, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK of both arms, stateless); binary RCB1 responses |
| Cameras | `top` (static), `left_wrist`, `right_wrist` (on each arm's link_6), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs eai-yamlab (BUILD_ONLY, `images/yamlab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE.md §13) |
| Generator | `scripts/yamlab/mk_tasks.py` (`scripts/yamlab/instances.json`, `frozen/`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/yamlab.md |

### Change Log
- 2026-10-10: grading robustness and time limits; the scene, the frozen instance and the pass rule
  (live ∧ replay ∧ deterministic) are unchanged, so the task keeps its name. `tests/grade.py`: a missing, unreadable or
  unfinalized `final.json`, or a replay process that ended without a result, is `infra_error` = 1 (it was the agent's 0, or
  no reward at all). `finalize.sh`: `final.json` replaced atomically, each replay time-boxed inside the hook and retried
  once when it dies; `[[verifier.collect]] timeout_sec` 15000 s (was 5400 s). Service: malformed requests (null or
  wrong-type fields, an `ee_pose` position more than 3 m from the origin, a zero quaternion) are answered 400 before anything
  moves (some ended the episode with a simulator error); `/spec` states the 100,000-step cap (`max_control_steps`). The
  replay video of an episode longer than 18,000 control steps is a time lapse (at most 9,000 frames). A trial
  recorded before this date with reward 0 and one of these conditions was an infrastructure failure.
- 2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (629 s measured here on a loaded host: the first `Robot()` could raise "sim service unavailable", and the instruction said to call it again); `cameras="name"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (owner decision, board 0072): the frozen instance file no longer names the recording it was made from
  (`instance.json` had a `source` entry with the dataset, the file and the demonstration index, and the tooling's usage
  text named such a file; the reference solution replays that demonstration). Nothing reads the entry: the scene, its
  state hash, the tooling's behaviour and the pass rule are unchanged, so the task keeps its name.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready). Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
