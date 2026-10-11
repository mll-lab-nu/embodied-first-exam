# robowits-cover-with-lid-i00-standard

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robowits-cover-with-lid-i00-privileged` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `cover_with_lid` / seed 0 |
| Oracle | `none` — No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-cover-with-lid-i00__Jb7Zzve (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robowits:0.1.1` |

## Task
Cover the pot precisely using one lid. The same frozen instance as `robowits-cover-with-lid-i00-privileged`, as a
robot service (`eai-standard/2.2`): the simulator runs in the `sim` sidecar, which the agent cannot open; the agent
gets one episode, no reset and no privileged state, only the client (calibrated RGB-D cameras, proprioception,
`joint_position` / `ee_pose` chunks, stateless kinematics). The sidecar records the episode as the trajectory, replays
it and renders the video; the success criterion as graded is in `instruction.md`.

## Difficulty
That of `robowits-cover-with-lid-i00-privileged` (its Difficulty), without resets, privileged state or the tooling's
primitives: the agent perceives the scene through calibrated RGB-D cameras and its own proprioception, and every
action it sends is part of the one graded episode.

## Reference solution
None: RoboWits ships no expert or planner, and none is written for this family (`oracle = "none"`). Evidence that it
is solvable: `oracle_evidence` in `task.toml` and the positive example cited in the review table of PR #3 (the trial
is published on the results site).

## Verification
`success` = live success ∧ replay success ∧ deterministic (the in-process replay is bit-exact on Genesis' CPU
backend), computed inside the sidecar, and no infrastructure failure (`tests/grade.py` reads the sidecar's
`final.json`); `/logs/verifier/replay.mp4`. What is checked, in words: `instruction.md`, "Success criterion (as
graded)".

No oracle; human review in PR #3 (PROTOCOL §2.7), with its privileged twin: the positive example, the `nop` result and the predicate
summary are in the PR's review table.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 8 GB | 7 GB |
| GPU memory | 2 GB | 2 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.5-1.4 GB (physics on the CPU, GPU renders the cameras), vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 4.5 GB, privileged container p90 4.7 GB, verifier 2.4 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate (single-threaded Genesis CPU backend)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 17 GiB memory. Limits measured: GPU: 1.4 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 2.5 GiB over 4 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 9 GiB (docker peak 4.5 GiB, 8 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2` (docs/STANDARD_MODE.md): `submit` chunks of `joint_position` (16, streamed at the 30 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; stateless `kinematics`; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service replays its journal and resumes the same episode (resume class `exact`, docs/STANDARD_MODE.md §13) |
| Agent and verifier image | `docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` with the shared pins (`environment/client-requirements.txt`) |
| Instance | the privileged twin's frozen instance (`environment/sim/instance.json`): entry 0 of RoboWits' `eval_dataset_50/13.json` |
| BlenderKit models | not redistributable, so not in the image: mounted read-only into the `sim` sidecar from `$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`) |

### Change Log
- 2026-10-10 (review of board 0067; findings RW-1, RW-2, RW-3, RW-4, RW-7, RW-8): the service checks every request field before it executes anything and answers 400 (before: a null or mistyped `dt` / `seconds` / `video_fps`, a `video_fps` outside 1..30 or a non-string `note` ended the episode with a 500, some of them after the chunk had run); a `joint_position` `dt` that is not a whole number of 1/30 s periods is answered 400 (before: rounded silently); `ee_pose` gripper widths outside the limits are listed in `meta["clipped"]`; a frozen instance that the host cannot rebuild (reason `instance_mismatch`) and a grading replay that fails after a normal episode end as `infra_error = 1` with a complete record, at once and without waiting out the collect hook; a service that died while rendering the video keeps its verdict; `/spec` (`max_control_steps`) and the instruction state the cap of 200000 control steps per episode; `reward.json` adds `sim_error`, `instance_mismatch`, `instance_exact`. The pass rule, the frozen instance, the tooling and the predicate are unchanged; validated with synthetic tests of the service and the grader, not re-run in the simulator.
- 2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (no effect on a scene that builds in about a minute); `cameras="name"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): the shared service layer, the client and a per-call image limit in the service (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`, `environment/sim/server.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). One call returns at most 1500 images (`/spec` `max_frames_per_call`: cameras x frames, a frame with per-frame depth counts 4): a request that would exceed it is a 400 before anything runs, and `ee_pose` rows that take longer than planned stop adding frames there (`meta["frames_skipped"]`). Before, a call had no such bound: one long observation at the full frame rate could hold more frames than the sidecar's memory and get the service killed, so a trial that ended `sim_crashed*` or with `resource_service_oom` right after such a request before this date was that. The collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
