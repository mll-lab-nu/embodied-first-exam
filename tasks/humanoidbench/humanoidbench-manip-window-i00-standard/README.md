# humanoidbench-manip-window-i00-standard

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `humanoidbench-manip-window-i00-privileged` |
| Simulator / robot | `humanoidbench` / `unitree-h1hand` |
| Family / instance | `window` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and published RL reaches 94% of the bar (paper 227, FastTD3 613, bar 650); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `humanoidbench-manip-window-i00-privileged`: the
same frozen instance and the same success rule. HumanoidBench runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar for rendering), which holds the reward, judges the
episode as it runs, records it and, after the verdict, renders its video from the recorded trajectory; the
verifier grades the sidecar's record in a container of its own (`tests/Dockerfile`, no network).

Note: the head cameras see the window. `room_camera` (the recording camera frozen at its starting pose) sees
the window, the wiping tool and the robot.

## Difficulty
See `humanoidbench-manip-window-i00-privileged`'s README; here the agent also has no state, no reward and no
simulator of its own, and 50 resets instead of unlimited ones: every try is a real episode on the one robot.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically removes the
interesting tasks. What replaces it (docs/protocol/README.md §2.7): the floor above (doing nothing cannot
pass), the evidence that the task has a solution (`oracle_evidence` in task.toml), and a human reviewer.

## Verification
`success` = live success: the episode the sim service ran reached the pass mark (HumanoidBench's own rule,
judged on the live simulator; the episode ends there), for the last episode (the one after the last reset;
earlier episodes are in `trajectory_live.f64` and `episode.jsonl`, not graded). Nothing is replayed to grade
it (owner, 2026-10-17). The scene's start is checked against the frozen instance's recorded state
when an episode begins (a mismatch is `instance_mismatch`, infrastructure). `tests/grade.py` reads
`/data/final.json` and copies the evidence to `/logs/verifier/`: `trajectory.npz` (the deliverable,
replayable) and `replay.mp4`, rendered from it in one pass after the verdict (a lost video never changes the
verdict). No oracle; human review in PR #9. `nop` scores 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 3 GB | 3 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 1.1-2.3 GB, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: privileged container median 2.2 GB (p90 11 GB when agents run parallel rollouts), sim 0.7 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 13 GiB memory. Limits measured: GPU: 2.3 GiB (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 2.3 GiB over 10 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.7 GiB, 3 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| mode / sensors | standard: head-camera RGB + joint angles and velocities (HumanoidBench's own `image` and `proprio` sensors), a pelvis IMU and a camera fixed in the room; no root pose, no tool pose, no reward; 50 resets (a new episode from the frozen start each; only the last episode is graded) |
| action space | HumanoidBench's own: 61 normalised position targets, 50 Hz, sent in chunks |
| knobs (compose env) | `RCB_RESET_BUDGET` (50: HumanoidBench's standard configuration, tasks/humanoidbench/README.md), `RCB_OBS_PROPRIO` (1), `RCB_OBS_IMU` (1), `RCB_OBS_ROOM_CAMERA` (1), `RCB_OBS_DEPTH` (0): the defaults are the standard configuration; a run that changes one (`RCB_RESET_BUDGET=0 harbor run ...`: one episode, no reset) is reported separately, and `episode.jsonl` records the `/spec` it ran under |
| agent API | `environment/rcb_client.py` (its docstring is the reference); `instruction.md` lists the endpoints |
| physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (tasks/humanoidbench/README.md, Physics). |

### Change Log
- 2026-10-07: `RCB_RESET_BUDGET`'s default 0 -> 50 (owner decision; PROTOCOL §4.5,
  tasks/humanoidbench/README.md). The scene, instance, pass rule and verifier are unchanged, so the task
  keeps its name; runs recorded before this date had no reset and are reported separately.
- 2026-10-08: base image 0.1.6 -> 0.2.0: MuJoCo 3.3.7 instead of upstream's 3.1.6
  (tasks/humanoidbench/README.md, Physics). The pass rule and verifier are unchanged, so the task keeps its
  name; results recorded on 0.1.6 are other physics and are reported separately.
- 2026-10-10: the sim service marks `final.json` `finalized` the moment the verdict is written, before the
  replay video is rendered (`video_pending` while it renders), and the collect hook's waits run on the clock,
  inside its timeout: a slow, hung or killed video render no longer turns a graded episode into `infra_error`.
  `reward.json` adds `sim_error` and carries `deterministic` in every branch. The scene, instance and pass
  rule are unchanged, so the task keeps its name; every verdict that was reached before is the same now.
- 2026-10-10 (2; second review round): the sim service refuses a negative `Content-Length` unread (400; it
  read until the client hung up), and a simulator that fails inside `POST /reset` ends the episode as `error`
  (`sim_error = 1`), not `reset`. The scene, instance, pass rule and every verdict reached before are
  unchanged, so the task keeps its name.
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
  live rule.
