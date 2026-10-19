# mujoco_playground_aloha_hand_over-standard

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `mujoco_playground_aloha_hand_over-privileged` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `mujoco_playground/AlohaHandOver` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2` |

## Task
Standard-mode twin of `mujoco_playground_aloha_hand_over-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_aloha`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `mujoco_playground_aloha_hand_over-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the live episode's verdict (`graded_by = "live"`, no grading replay): the task's check of the live final state. The frozen start is checked when the episode begins (instance `state_sha`)

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 1.0-1.3 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container p90 2.6 GB, sim 0.7 GB, mem_guard (docker memory per container, 4090-ws1, 10-02..10); CPU p90 1.9 cores, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + 4090-ws1, 10-10)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 13 GiB memory. Limits measured: GPU: 1.3 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 2.5 GiB over 4 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, 4090-ws1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.7 GiB, 3 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| video | `replay.mp4`: one render pass over the trajectory from the frozen start after the verdict (in the sidecar, EGL on its GPU); it never changes the verdict |

### Change Log
- 2026-10-10 (review 0067): the camera calibration in `meta["cameras"]` now gives the pose of the viewpoint the image is rendered from. Before, `cam2world_gl` held the position of MuJoCo's left-eye camera, 3.4 cm to the side of it, so points back-projected from depth were off by that much. This changes what the agent observes: standard-mode results from before this date are not strictly comparable.
- 2026-10-10 (review 0067): a malformed request (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list of names, actions that are not a numeric array) is answered 400 before any physics; before, some of them (e.g. `dt = Infinity`) were a 500 that ended the episode. `meta["time_left_s"]` counts from the agent's first request, not from the service's start. `final.json` is finalized as soon as the verdict is in it (the video is rendered after it and cannot delay or void it); a missing, unreadable or verdict-less `final.json` is graded `infra_error = 1`, never a plain 0; the collect hook's wait fits inside its timeout.
- 2026-10-10 (review round 2, board 0067): crash recovery only. A service killed inside the call that ended the episode (after the end was logged, before the call's own record) resumed in the state before that call but kept the episode ended, so every later call was a 409 and the rolled-back state was graded (a 0 without `infra_error`); the resume now ignores an end that belongs to the lost call, and the episode continues from the last completed call, as the instruction says. An episode without a crash is unaffected.
- 2026-10-10 (review round 3, board 0067): the sim service's request handling only (`environment/sim/server_mj.py`). A negative or non-numeric `Content-Length` is answered 400 without reading the body (the service read until the client hung up, without a bound, which could exhaust its memory); a camera named more than once in `cameras` is rendered and returned once (N copies of one name made it build N x N images within the frame budget); a port that is still held when the service restarts is waited for, not counted as a crash; a JSON `true` or `false` where `dt` or `seconds` takes a number is a 400 (`true` ran as 1 second). An episode's physics, the grader and the pass rule are unchanged.
- 2026-10-10 (review 0067): the calibration is recomputed for every response. Before, it was computed once at start-up, so the wrist cameras' poses were those of the home pose however the arms had moved; a response with several frames now also carries the wrist cameras' pose for every frame (`cam2world_gl/<cam>`).
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
- 2026-10-13 (board 0086): **the camera intrinsics the agent is given changed** (`environment/sim/server_mj.py`, `meta["cameras"][cam]["intrinsic_cv"]`). `overhead_cam`, `wrist_cam_left` and `wrist_cam_right` are defined by their sensor (3.896 x 2.140 mm, 1.93 mm lens), and MuJoCo renders such a camera with the sensor's own extent in each direction: in the 320 x 240 image fx = 158.52 px and fy = 216.45 px. The service reported fx = fy = 216.45 (from the vertical field of view), 1.37 times too large in x, so points back-projected from depth were off sideways by that factor. It now reports the true fx and fy of every camera (checked against CPU renders: a marker at a known 3-D point lands 0.1 to 0.2 px from its projection on average; 15 to 19 px, up to 35 px, before). `teleoperator_pov`, defined by its field of view, is unchanged. The images, the physics, the grader and the pass rule are unchanged; standard-mode results of this task from before this date were obtained with the wrong fx.
- 2026-10-13 (board 0099): `environment/sim/server_mj.py` gained the optional reset capability (`POST /reset`, `RCB_RESET_BUDGET`, default 0) for DexToolBench, and the client a `reset()` method; `final.json` and `reward.json` record `resets` and `reset_budget`. This task sets no budget: `/reset` is a 404 and `budget.reset` is 0, one episode as before. The physics, the observations, the grader's verdict and the pass rule are unchanged.
- 2026-10-16 (board 0136): the sim collect hook waits for the replay video until 1680 s after the episode ends (`timeout_sec` 900 -> 1710); the verdict keeps its 840 s bound. One 840 s deadline covered the verdict and the video, which replays the episode once more after it, so long episodes lost their video. Video only: the verdict, the physics and the pass rule are unchanged, so results from before this date stay valid.
- 2026-10-17 (owner, boards 0150 and 0151): **graded by the live episode, no grading replay.** `environment/sim/server_mj.py`, `tests/grade.py`, `task.toml` (the collect hook). The verdict is the task's own rule on the episode the service ran (the tooling's check() of the live final state; `graded_by = "live"`, `replays = 0`); the service no longer replays the episode in a fresh simulator (success was that replay's result ∧ the same final state as the live episode, `deterministic`), and renders `replay.mp4` in one pass over the trajectory after the verdict. The rule is the same: the replay ran the same rows through the same per-step tracker and the same check. The frozen start is checked when the episode begins (the built scene's state hash against the instance's `state_sha`, as the tooling's own start check did); a mismatch gets no episode (`instance_mismatch`, infrastructure). A new collect hook on `main` (`kill -9 -1`, before the sim's) stops whatever the agent left running before the episode is ended and judged (PROTOCOL H.4). The collect hook still waits up to 840 s for the verdict (a crashed service resumes the episode first) and until 1680 s for the video. The scene, the instance, the pass rule and what the agent sees are unchanged, so the task keeps its name; `final.json` and `reward.json` no longer have `deterministic`.
