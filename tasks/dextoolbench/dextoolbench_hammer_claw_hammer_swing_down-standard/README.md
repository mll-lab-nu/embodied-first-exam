# dextoolbench_hammer_claw_hammer_swing_down-standard

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `dextoolbench_hammer_claw_hammer_swing_down-privileged` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/hammer/claw_hammer/swing_down` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2` |

## Task
Standard-mode twin of `dextoolbench_hammer_claw_hammer_swing_down-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_dtb`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `dextoolbench_hammer_claw_hammer_swing_down-privileged` (see its Difficulty). In standard mode the agent loses privileged state and planning primitives, and has 20 resets instead of unlimited ones: it sees camera images and proprioception only, acts through the client, and every try is a real episode from the same start, of which only the last is graded.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the live episode's verdict (`graded_by = "live"`, no grading replay): the last episode (every control step since the last reset) passes when the goal tracker, run on every executed control step, has reached every goal (`progress` = goals reached / goals in `reward.json`). The frozen start is checked when the episode begins (`RCB_START_SHA`)

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.3-0.9 GB on 24 GB cards, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: sim p90 0.9 GB, privileged container p90 4.4 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 9 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 14 GiB memory. Limits measured: GPU: 2.1 GiB on a 48 GB card (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 4.4 GiB over 7 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.9 GiB, 7 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| video | `replay.mp4`: one render pass over the trajectory from the frozen start after the verdict (in the sidecar, EGL on its GPU); it never changes the verdict |

### Change Log
- 2026-10-10 (review 0067): the camera calibration in `meta["cameras"]` now gives the pose of the viewpoint the image is rendered from. Before, `cam2world_gl` held the position of MuJoCo's left-eye camera, 3.4 cm to the side of it, so points back-projected from depth were off by that much. This changes what the agent observes: standard-mode results from before this date are not strictly comparable.
- 2026-10-10 (review 0067): a malformed request (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list of names, actions that are not a numeric array) is answered 400 before any physics; before, some of them (e.g. `dt = Infinity`) were a 500 that ended the episode. `meta["time_left_s"]` counts from the agent's first request, not from the service's start. `final.json` is finalized as soon as the verdict is in it (the video is rendered after it and cannot delay or void it); a missing, unreadable or verdict-less `final.json` is graded `infra_error = 1`, never a plain 0; the collect hook's wait fits inside its timeout.
- 2026-10-10 (review round 2): crash recovery only. A service killed inside the call that ended the episode (after the end was logged, before the call's own record) resumed in the state before that call but kept the episode ended, so every later call was a 409 and the rolled-back state was graded (a 0 without `infra_error`); the resume now ignores an end that belongs to the lost call, and the episode continues from the last completed call, as the instruction says. An episode without a crash is unaffected.
- 2026-10-10 (review round 3): the sim service's request handling only (`environment/sim/server_mj.py`). A negative or non-numeric `Content-Length` is answered 400 without reading the body (the service read until the client hung up, without a bound, which could exhaust its memory); a camera named more than once in `cameras` is rendered and returned once (N copies of one name made it build N x N images within the frame budget); a port that is still held when the service restarts is waited for, not counted as a crash; a JSON `true` or `false` where `dt` or `seconds` takes a number is a 400 (`true` ran as 1 second). An episode's physics, the grader and the pass rule are unchanged.
- 2026-10-13: `environment/sim/server_mj.py` reports the intrinsics of a camera that is defined by its sensor size from the sensor (ALOHA's cameras: fx differs from fy). This task's cameras are defined by their field of view: its calibration, and everything else, is unchanged.
- 2026-10-13 (owner decision): **20 resets** (PROTOCOL §4.5). `environment/sim/server_mj.py` gained the optional reset capability: `POST /reset` (the client's `r.reset()`) abandons the running episode and starts a new one from the same frozen start state, at most `RCB_RESET_BUDGET` times; the compose file sets its default to 20 (before: no reset, one episode). Only the last episode is graded (the same fresh replay and pass rule); a success ends the trial, and no reset is accepted once the agent's time is up. `meta` and `/status` add `episode`, `resets_left` and `control_steps_total`; `final.json` and `reward.json` record `resets` and `reset_budget`. Why: with one episode the first grasp decided the trial (all 21 of GPT-6 Astra's standard trials knocked the tool off the table at some point, and a tool on the floor cannot be recovered), so results varied from run to run for unrelated reasons. The scene, instance, physics, pass rule and oracle are unchanged, so the task keeps its name; `RCB_RESET_BUDGET=0` still runs the single-episode configuration. Standard results from before this date ran with no reset and are reported separately, never ranked with these.
- 2026-10-16: the sim collect hook waits for the replay video until 1680 s after the episode ends (`timeout_sec` 900 -> 1710); the verdict keeps its 840 s bound. One 840 s deadline covered the verdict and the video, which replays the episode once more after it, so long episodes lost their video. Video only: the verdict, the physics and the pass rule are unchanged, so results from before this date stay valid.
- 2026-10-17 (owner, boards 0150 and 0151): **graded by the live episode, no grading replay.** `environment/sim/server_mj.py`, `tests/grade.py`, `task.toml` (the collect hook), `environment/docker-compose.yaml` (`RCB_START_SHA`). The verdict is the task's own rule on the episode the service ran (every goal reached: the goal tracker runs on every executed control step; `graded_by = "live"`, `replays = 0`); the service no longer replays the episode in a fresh simulator (success was that replay's result ∧ the same final state as the live episode, `deterministic`), and renders `replay.mp4` in one pass over the trajectory after the verdict. The rule is the same: the replay ran the same rows through the same per-step tracker and the same check. The frozen start is checked when the episode begins (the built scene's state hash against `RCB_START_SHA`, the hash every archived episode of the task started from; before, nothing checked it); a mismatch gets no episode (`instance_mismatch`, infrastructure). A new collect hook on `main` (`kill -9 -1`, before the sim's) stops whatever the agent left running before the episode is ended and judged (PROTOCOL H.4). The collect hook still waits up to 840 s for the verdict (a crashed service resumes the episode first) and until 1680 s for the video. The scene, the instance, the pass rule and what the agent sees are unchanged, so the task keeps its name; `final.json` and `reward.json` no longer have `deterministic`.
