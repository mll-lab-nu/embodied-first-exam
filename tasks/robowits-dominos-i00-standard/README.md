# robowits-dominos-i00-standard

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robowits-dominos-i00-privileged` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `dominos` / seed 0 |
| Oracle | `partial` — Reference solution solution/oracle_replay.py, which streams the privileged oracle's recorded joint rows (solution/oracle_qpos.npy) through the client. It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-dominos-i00-limited-oracle-v2b-0924-2125, trial robowits-dominos-i00-limited__pnfVz4w, 2026-09-25 (laptop, Intel; the protocol's 2.0 service, then named rcb-limited; success=1, live 1, replay 1, deterministic 1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 4f933a76ce2ce34b) and the joint rows (equal to that run's recorded trajectory). Changed since then, so the label is partial: the grader (dev/qineng 82d76c61; this PR: the crash-recovery fields and infra_error), the sim adapter server.py (dev/qineng 6c0b439e: protocol 2.2; this PR: crash recovery), the shared layer rcb_limited.py / rcb_client.py (dev/qineng 42813008; this PR: the eai-standard/2.2 layer with crash recovery), the tooling rcb_robowits.py (as in the privileged twin), the collect hook, the client image and pins, and the oracle player (this PR: it recovers from a crash). Not re-run on this version (static validation only, 2026-10-01). 2026-10-14 (ws, AMD): Harbor -a oracle on this version (run under a temporary -i01 task name; the files differ from it only in that name and in comments) scored 1 (trial robowits-dominos-i01-standard__6MwPrG7: live 1, replay 1, deterministic 1; 187 rows + the 90-step settle window), nop 0 (reason agent_exit). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robowits:0.1.1` |

## Task
Push the red block onto the green target area. The same frozen instance as `robowits-dominos-i00-privileged`, as a
robot service (`eai-standard/2.2`): the simulator runs in the `sim` sidecar, which the agent cannot open; the agent
gets one episode, no reset and no privileged state, only the client (calibrated RGB-D cameras, proprioception,
`joint_position` / `ee_pose` chunks, stateless kinematics). The sidecar records the episode as the trajectory, replays
it and renders the video; the success criterion as graded is in `instruction.md`.

## Difficulty
That of `robowits-dominos-i00-privileged` (its Difficulty), without resets, privileged state or the tooling's
primitives: the agent perceives the scene through calibrated RGB-D cameras and its own proprioception, and every
action it sends is part of the one graded episode.

## Reference solution
`solution/oracle_replay.py` replays the privileged oracle's recorded joint targets (`solution/oracle_qpos.npy`, one
row per control step, `hold`) through the client, with no privileged information at run time; `solution/solve.sh` runs
it. The rows are the trajectory of the privileged reference solution (`robowits-dominos-i00-privileged`, `solution/`).

## Verification
`success` = live success ∧ replay success ∧ deterministic (the in-process replay is bit-exact on Genesis' CPU
backend), computed inside the sidecar, and no infrastructure failure (`tests/grade.py` reads the sidecar's
`final.json`); `/logs/verifier/replay.mp4`. What is checked, in words: `instruction.md`, "Success criterion (as
graded)".

Oracle partial: the reference solution scored 1 on an earlier version of this task and was not re-run on this one
(`oracle_evidence` in `task.toml`); human review in PR #3 (PROTOCOL §2.7), with its privileged twin.

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
| Instance | the privileged twin's frozen instance (`environment/sim/instance.json`): entry 0 of RoboWits' `eval_dataset_50/06.json` |

### Change Log
- 2026-10-10 (review of board 0067; findings RW-1, RW-2, RW-3, RW-4, RW-7, RW-8): the service checks every request field before it executes anything and answers 400 (before: a null or mistyped `dt` / `seconds` / `video_fps`, a `video_fps` outside 1..30 or a non-string `note` ended the episode with a 500, some of them after the chunk had run); a `joint_position` `dt` that is not a whole number of 1/30 s periods is answered 400 (before: rounded silently); `ee_pose` gripper widths outside the limits are listed in `meta["clipped"]`; a frozen instance that the host cannot rebuild (reason `instance_mismatch`) and a grading replay that fails after a normal episode end as `infra_error = 1` with a complete record, at once and without waiting out the collect hook; a service that died while rendering the video keeps its verdict; `/spec` (`max_control_steps`) and the instruction state the cap of 200000 control steps per episode; `reward.json` adds `sim_error`, `instance_mismatch`, `instance_exact`. The pass rule, the frozen instance, the tooling and the predicate are unchanged; validated with synthetic tests of the service and the grader, not re-run in the simulator.
- 2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (no effect on a scene that builds in about a minute); `cameras="name"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): the shared service layer, the client and a per-call image limit in the service (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`, `environment/sim/server.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). One call returns at most 1500 images (`/spec` `max_frames_per_call`: cameras x frames, a frame with per-frame depth counts 4): a request that would exceed it is a 400 before anything runs, and `ee_pose` rows that take longer than planned stop adding frames there (`meta["frames_skipped"]`). Before, a call had no such bound: one long observation at the full frame rate could hold more frames than the sidecar's memory and get the service killed, so a trial that ended `sim_crashed*` or with `resource_service_oom` right after such a request before this date was that. The collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready). Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-14 (in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8; the service's success rule changed). From the failure analysis of the 10-14 results (an object held in the goal region ended the episode as a success; a creeping cup passed one speed sample). (1) The goal is RoboWits' predicate (unchanged) with the graded objects released: no robot contact with them; move_cube's cube must also be on the table. (2) When the goal holds after a call, the service holds the last command for a settle window inside that call (1 s, then 2 s in which the goal must hold and every graded object stay within 2 mm); only then does the episode end as a success, else it goes on (`meta["settle"]` says why). When the agent's phase ends, the same window decides. (3) `final.json` `reason` is "agent_exit" when the agent ended its session with more than 60 s left, "timeout" at the time limit (before: "timeout" in both cases), with `agent_time_s` and `settle`. (4) The instruction says that a client timeout while a call is in flight means the single-threaded service is busy, not crashed. The frozen instance, RoboWits' predicate and the time limit are unchanged; results recorded before this date (the earlier DIGEST) are not comparable with this version.
- 2026-10-17 (in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8; the grading replay changed; instruction audit M5, M6). (1) The service's grading replay (`environment/sim/server.py` `grading_replay`) checks ONE settle window: when the live episode ended on a settle window (reason "success": the window inside the last call; "agent_exit" / "timeout": the window after the agent's last command), that window is part of the recorded rows, and the replay checks the same window again over those rows. Before, the replay ran the recorded rows (the live window included) and then a second window of 90 steps after them, which the instruction did not state and which could fail an episode whose window had passed live (robowits-hold-cup-i00-standard, 2026-10-15: live window passed with 0.13 mm of motion, replay 0). (2) An episode that ends at the step cap (reason "step_guard") is graded without a settle window, as a failure, and the instruction says so (it said "graded as it stands"); before, the replay's window raised past the cap and the trial was recorded as a grading error (`infra_error = 1`). `final.json` adds `final_window` (the window's length in recorded rows) and `replay_settle`. The scene, the frozen instance, the predicate, the live service's success rule and the client are unchanged; recorded trials are re-graded from their trajectories with `scripts/robowits/regrade.py`.
