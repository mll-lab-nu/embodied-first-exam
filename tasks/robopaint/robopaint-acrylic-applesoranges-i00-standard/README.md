# robopaint-acrylic-applesoranges-i00-standard

| | |
|---|---|
| Benchmark | RoboPaint |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robopaint-acrylic-applesoranges-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `robopaint_acrylic_applesoranges` / seed 0 |
| Oracle | `partial` — Reference solution in solution/ (streams the privileged reference's joint targets), unchanged from the earlier version of this task (the picture score only; its Harbor oracle and nop runs, and what changed since: tasks/robopaint/README.md, Oracle evidence). The same trajectory scores 1 under the process rules in the verifier (the graders' rcb_brush_strict.py, with which the sim service also scores the live sheet) (2026-10-05): path_mm 11276 of the 33900 mm budget; its strokes are sweeps. Harbor oracle and nop runs on one pair per family: tasks/robopaint/README.md (Validation). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robopaint-0.2.0` |

## Task
**Process rules** (tasks/robopaint/README.md) on top of the picture rule, so that the exemplar has to be made with strokes rather
than coloured in: the brush tip's path while it presses on the main sheet with paint (`path_mm`) is at most 33900 mm (3 ×
the reference solution's 11276 mm), and at most 10 % of it lies in strokes longer than
2.5 × the diagonal of their bounding box (zigzags, back-and-forth fills, spirals, loops). They are part of the frozen instance (the rules added to its `target.success`); the sim service
applies them to the live sheet with the graders' `rcb_brush_strict.py`.

Standard-mode twin of `robopaint-acrylic-applesoranges-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/protocol/standard_mode.md) and the exemplar as a picture (`/app/target.png`, 1024 px covering the main sheet); the simulator
and the paint engine (libmypaint) run in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar for the cameras), which owns the
scene and records the episode as a (T, 7) trajectory. There is no reset, no sheet readout, no brush state or paint model and no score:
paint is permanent and the agent sees the sheets only through the cameras (`canvas_cam` 1024 px over the main sheet, `practice_cam`
over the practice sheet). The practice sheet is there for test strokes. The collect hook
(`environment/sim/finalize.sh`) ends the episode; the service scores its live main sheet and writes `final.json`, then renders the
trajectory once into the video; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
Same scene, exemplar and rule as `robopaint-acrylic-applesoranges-i00-privileged` (see its Difficulty), without its privileged help: no reset, no sheet readout, no model of the mark and no score. Every stroke on the main sheet is permanent and is seen only through the cameras; how the tool marks the paper has to be learned from test strokes on the practice sheet.

## Reference solution
`solution/`: streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks; the recorded trajectory then equals the privileged oracle's; label `partial` (task.toml `oracle_evidence`: the reference solution, scored under the process rules).

## Verification
"The rule" below is the picture rule and the process rules (Task); the sim service scores the live sheet with
`environment/sim/rcb_brush_strict.py` (`rcb_brush.py` with the rules), and `reward.json` adds the rules' quantities (`path_mm`,
`max_path_mm`; paintings: `scribble_share`), `image_success` (the picture rule alone) and `strict_ok` (the process rules).
`success` = the live episode's main sheet meets the rule (after the best single shift of the sheet, at most 5 mm along each axis, mean CIELAB ΔE <= 2.0, p90 ΔE <= 6.0, SSIM of L* >= 0.92, edge correlation >= 0.8, paint IoU >= 0.95 and at most 390 strokes), scored by the sim sidecar after the agent's container is stopped (`final.json`: `graded_by = "live"`; nothing is replayed to grade it); every metric of the live sheet in `reward.json`; `/logs/verifier/replay.mp4` (the trajectory rendered once after the verdict).
A `final.json` that is missing, unreadable or without a verdict (the collect hook did not finish), a give-up after crashes
that were not all inside the agent's calls, a frozen instance that does not rebuild in the sidecar (`instance_mismatch`, refused
before the agent is served) and a live sheet the service could not score (`grade_error`) are an infrastructure failure
(`infra_error = 1`), not the agent's 0; `sim_error = 1` marks an episode that a simulator error ended. A video that fails or runs
out of time never changes the verdict. The collect hook has 2820 s.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 4 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.25-0.5 GB, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: sim p90 1.7 GB, privileged container p90 2.5 GB + scorer 0.7 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 9 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 17 GiB memory. Limits measured: GPU: 0.5 GiB (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 5.0 GiB over 83 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 8 GiB (docker peak 3.4 GiB, 36 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Action space | `eai-standard/2.2`: `submit` chunks of `ee_pose` (7: brush-tip pose, rows `dt` apart, straight-line tip targets with IK per 20 Hz control step, ≤ 0.25 m/s) or `joint_position` (7, streamed at 20 Hz); `observe` frames or a watch window; binary RCB1 responses |
| Static facts | sheets (main: scored; practice: never scored or counted), the 10 paint wells (colours, radii) and the dip rule, the brush's tuft length and handle stop, the picture → sheet mapping (and its scale), the stroke budget (390); not given: where anything is (no positions or heights: the cameras show them), the paint engine or its preset, the hidden stroke program |
| Cameras | `canvas_cam` (overhead main sheet, 1024²), `practice_cam` (overhead practice sheet, 512×1024), `scene_cam` (640×480), `side_cam` (640×360, grazing view of the brush height); static calibration in every response |
| Crash recovery | the service journals every executed control step (`journal.f64`) and checkpoints every call with the state hash; after a crash compose restarts the sidecar (`restart: on-failure:6`) and the service resumes the SAME episode (resume class `exact`: the replayed state must equal the checkpoint), at most twice; `reward.json` reports `sim_startups`, `resumes`, `infra_error` (docs/protocol/standard_mode.md §13) |

### Licences
The exemplar is this robot's painting after Paul Cézanne, *Apples and Oranges* (1895-1900), a public-domain work (Wikimedia Commons `File:Nature morte aux pommes et aux oranges, par Paul Cézanne.jpg`, Public domain); the exemplar picture is CC0; libmypaint is ISC, the presets CC0: `environment/NOTICE-exemplar.md`.

### Change Log
- 2026-10-10: the verifier and the collect hook only (review of 2026-10-10). A `final.json` that is missing, unreadable or without a verdict, and replays that could not run, are an infrastructure failure (`infra_error = 1`; a missing file was recorded as the agent's 0 with `infra_error = 0`); `reward.json` gains `sim_error` and always has `deterministic`; the hook writes `final.json` whole (temporary file + rename) and has 5400 s (was 3600 s). The verdict of an episode that was graded before is unchanged, and so are the instance, the picture and the rules: the task keeps its name.
- 2026-10-10 (2): `task.toml` `[agent].allowed_hosts` only. The allowlist is now the one every other allowlist task has (`scripts/set_agent_egress.py`): it gains `*.openai.azure.com` and `*.cognitiveservices.azure.com`, so that an agent whose model is served by Azure OpenAI can reach it directly (without them such an agent could not reach its model and ended as a 0 without having acted). Nothing else changes: the task keeps its name.
- 2026-10-10 (review round 2): the service's request checks and the client. `environment/sim/server.py` checks every field of `/submit` and `/observe` before anything is executed and answers 400: a `note` that is not a string (for example a number) ended the episode with a 500 after the chunk had run, a null `dt`, `seconds` or `video_fps` ended it before anything ran, and a negative or absurd `video_fps` ended it when the video was encoded; null now means the default, `video_fps` must be in [0, 1000], and a numeric field sent as a string or a boolean is a 400 too. `environment/rcb_client.py`: `Robot()` waits up to 3600 s for the service (was 600 s; no effect here, the scene builds in under a minute) and `cameras="name"` (a string) is one camera, no longer its characters. The collect hook, the grader, the scene and the pass rule are unchanged; a trial that ended with reason `error` (`sim_error = 1`) right after such a request before this date was not a simulator fault.
- 2026-10-10 (review round 3): the shared service layer, the client and two request checks of the service (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`, `environment/sim/server.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). One call returns at most 640 images (`/spec` `max_frames_per_call`: cameras x frames, a frame with per-frame depth counts 4): a request that would exceed it is a 400 before anything runs; the control steps of an `ee_pose` chunk that is slowed down to 0.25 m/s are counted before it starts. Before, a call had no such bound: one long observation at the full frame rate, or one `ee_pose` row far outside the workspace (for example millimetres sent as metres), could hold more frames than the sidecar's memory and get the service killed, so a trial that ended `sim_crashed*` or with `resource_service_oom` right after such a request before this date was that. An `ee_pose` position too large for a finite distance is a 400 as well (it ended the episode with a 500 in the middle of the chunk). The collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready). Where the service is ready before the agent's phase begins (the harness is installed in between: 79 s in the typical recorded standard trial), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule keys in `target.success` (lettering and the paintings) is graded exactly as before.
- 2026-10-17 (owner; in place: a new DIGEST): standard mode graded by the live episode; no grading replay; video by one render pass after the verdict. When the collect hook ends the episode (after the new `main` hook has stopped the agent's container with `kill -9 -1`), the sim service commits a stroke still pressed and scores its live main sheet with the graders' `rcb_brush_strict.py`, the same scorer and rule (picture rule and process rules) the two fresh-process replays used, and writes `final.json` at once (`graded_by = "live"`, `replays = 0`, `success`, `metrics`); then it renders the recorded trajectory once into `replay.mp4` (`video_pending`, `video_done`). Before, the service exited and the collect hook replayed the trajectory twice, scored the replayed sheet and required both replays to agree (`replay_success`, `deterministic`, `live_matches_replay`, `gpu_lost`: gone); the live service's own score then had the picture rule only. A frozen instance that does not rebuild in the sidecar is refused at the start (`instance_mismatch`, `infra_error = 1`) instead of crash-looping. The collect hook's time is 2820 s (was 5400 s). The scene, the frozen instance, the rules and the client are unchanged; the instruction says that the main sheet is scored as the episode left it.
