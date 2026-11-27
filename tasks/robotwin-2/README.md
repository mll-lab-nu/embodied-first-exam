# RoboTwin 2.0

## Overview

RoboTwin 2.0 dual-arm manipulation on the ALOHA-AgileX robot (SAPIEN 3 / PhysX, CuRobo motion planning): 47 of
RoboTwin's 50 tasks, each in two modes, 94 task directories (`robotwin_2_0_<task>-privileged`,
`robotwin_2_0_<task>-standard`). Both modes of a task use the same frozen scene instance (one RoboTwin seed per task,
with its expected initial-state hash) and the same success rule, RoboTwin's `check_success`.

- **privileged**: the agent has the full simulator (`rcb_traj.Session`: the RoboTwin task env, its planning
  primitives, unlimited resets) and hands in one replayable trajectory of per-physics-step drive targets, which the
  verifier replays open-loop.
- **standard**: RoboTwin 2.0's standard tasks serve the standard protocol
  (docs/protocol/standard_mode.md Part 1), the service the base protocol was written from. The simulator runs in a
  `sim` sidecar the agent cannot open; the agent gets only the client (and the same service as MCP tools): camera
  images, camera calibration and proprioception, `joint_position` or `ee_pose` action chunks, one episode, no reset, no
  object poses, no success signal. It has to estimate the scene from images and recover from its own mistakes without
  starting over; comparing it with the privileged mode measures the cost of losing resets, privileged state and
  planning primitives.

The task directories are the deliverable; the tooling that built them is kept outside this repository.

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/robotwin-2 -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it. Base image: `ghcr.io/mll-lab-nu/efe:robotwin-<images/robotwin/VERSION>`
(`robotwin-0.1.2`).

## Upstream and license

- Upstream: RoboTwin 2.0, [RoboTwin-Platform/RoboTwin](https://github.com/RoboTwin-Platform/RoboTwin), pinned at
  `6dde571` (the submodule `third_party/RoboTwin`, copied to `/opt/RoboTwin` in the image). MIT License (copyright 2025
  Tianxing Chen). Citation: Chen et al., 2025, "RoboTwin 2.0: A Scalable Data Generator and Benchmark with Strong Domain
  Randomization for Robust Bimanual Robotic Manipulation", arXiv:2506.18088.
- Assets: RoboTwin's asset dataset on Hugging Face,
  [TianxingChen/RoboTwin2.0](https://huggingface.co/datasets/TianxingChen/RoboTwin2.0) at revision
  `981c92aa34d8f94d4cff47e0d5bc2f7d4e0af042` (`embodiments.zip`, `objects.zip`), downloaded when the image is built
  (`images/robotwin/Dockerfile`); nothing of it is committed here.
- Other components in the image: CuRobo v0.7.8 (NVlabs/curobo), SAPIEN 3.0.0b1, mplib 0.2.1.

## Changes from upstream

- **Reference solutions scrubbed** (`images/robotwin/scrub_oracles.py`): every task class keeps only `setup_demo`,
  `load_actors`, `check_success`, `__init__` and what they call; every other method body (the expert `play_once` and its
  helpers) raises `NotImplementedError("scrubbed")`. Attributes the kept methods set that only the expert reads (target,
  hand-over and placing poses, `dump_bin_bigbin`'s pouring action list: `LEAKS`, 18 tasks) are removed with the values
  that only feed them; a removed statement that draws from numpy's random stream is replaced by the same number of
  bare draws, so the scene (and its hash) is unchanged. None of them is read by `check_success`. `code_gen/` (LLM
  prompts with worked solutions), `description/` and `XPolicyLab/` are deleted.
- **Assets**: only embodiments and objects; `background_texture` (10 GB) is used only by domain randomisation and is
  left out. Scenes are clean: RoboTwin's `demo_clean` task config without data collection or domain randomisation (no
  random background, clutter, lighting, camera distance or table height).
- **Image patches** that RoboTwin's own install script applies: utf-8 URDF reads (sapien `urdf_loader.py`) and the
  mplib screw-plan collision check.
- **Seeded object draw made host-independent**: `place_a2b_left`, `place_a2b_right`, `place_object_scale` and
  `place_object_stand` list an object's model files with `glob.glob` and draw one with the seeded `np.random.choice`;
  glob returns the file system's directory order, so one seed built a different object on another host. While a scene
  is built, `rcb_traj.Session` sorts glob's matches (`_SortedGlob`).
- **Gripper state in the success check, privileged mode**: RoboTwin's `is_{left,right}_gripper_{open,close}()` read the
  value `Robot.set_gripper()` stores next to the finger drive targets (open > 0.8, half open > 0.45, closed < 0.2). A
  recorded row carries both (the finger targets in the joint columns, the stored value in the last two columns), so
  the two can disagree; the privileged tooling and verifier read the **fingers** instead (`Session.gripper_opening`:
  open needs the least open finger's target above 0.8, closed the most open finger's below 0.2; targets, not measured
  positions, so a gripper closed on an object still reads closed). The standard service drives the fingers only
  through `set_gripper`, so it keeps RoboTwin's own rule (`gripper_state="command"`).
- **Latched success cleared**: a task class may latch its success in `stage_success_tag` (`press_stapler` sets it at
  the first touch and never clears it). The standard service clears it before every judgement, so the verdict is the
  end state's, as in the privileged verifier's one check after the replay.
- **Recording hook**: every `scene.step()` RoboTwin's primitives take goes through a hook that applies gravity /
  Coriolis compensation (as RoboTwin does before every joint command) and records the row; replaying the rows
  open-loop from the same instance reproduces the outcome (PhysX CPU is deterministic on the same build).
- **Episode ends**: upstream evaluation stops at the first success; here a success never ends an episode (standard:
  agent-ended, below), and no upstream policy-evaluation step limit applies.

## Interface

World frame (both modes): the table centre at the origin, +z up, the robot at y = −0.65 facing +y (+x is the robot's
right), the table top at z ≈ 0.74 m; quaternions are wxyz.

### Privileged

- `/opt/tools/rcb_traj.py` (`from rcb_traj import Session`): `Session(<task>, instance="/app/instance.json")` rebuilds
  the frozen instance and loads the CuRobo planner; `s.reset()` (unlimited, a few seconds), `s.env` (the RoboTwin task
  env: objects, `env.robot`, the planning primitives of `envs/_base_task.py`), `record_start()` / `record_stop()`,
  `status()`, `replay(actions)`, `save_trajectory(actions, path)`, `step(row)` for low-level control,
  `gripper_opening(side)`; optional rendering (`enable_render=True`, `render_frame(camera)`). When a plan fails,
  `env.plan_success` turns False and later moves are skipped.
- A trajectory is the per-physics-step control record (T, 34): for the 16 driven joints of the articulation (arms and
  gripper fingers; wheels and casters are never commanded), drive position targets (16), drive velocity targets (16),
  then the left and right gripper commands. One row per physics step (1/250 s); at most 200,000 rows (`MAX_T`, 800 s of
  physics) are graded, and `save_trajectory()` / `replay()` refuse a longer one.
- The instance (`instance.json`): task, RoboTwin seed, embodiment, expected initial-state hash (`state_sha`: SHA-1 of
  every actor pose and articulation qpos / qvel), number of driven joints. RoboTwin seeds numpy before `load_actors`,
  then settles the scene for 2500 physics steps; every reset rebuilds the scene and checks the hash.
- Self-reported cost: every Session appends one line per start / reset / record / replay / exit to
  `/app/output/rcb_session_log.jsonl`, and every rollout's drive targets are dumped to `/app/output/rcb_trace/`.

### Standard

The robot is a service in the `sim` sidecar (wire protocol `eai-standard/3.0`).

**Actions.**
- `joint_position` (14 = 6 joints + gripper per arm; rad; gripper 0 closed..1 open): rows are `dt` seconds apart
  (`1/250 ≤ dt ≤ 0.5`, a multiple of the 1/250 s physics step: 0.004, 0.008, 0.02, …); the service streams drive
  targets at 250 Hz with linear interpolation. A chunk may cover at most `max_chunk_s` (10 s). Rows may carry 14 extra
  columns (28 in all) = joint velocity feed-forward in rad/s, held over the row; without them the service uses the
  central difference of the streamed targets. (An expert record replayed at `dt = 1/250` with its velocities is
  exact.) Out-of-limit values are clipped and listed in `meta["clipped"]`.
- `ee_pose` (16 = xyz + wxyz + gripper per arm, world frame): each row is planned by CuRobo against the table only and
  executed; `dt` is ignored (the planner sets the duration); a failed plan holds that arm for 50 physics steps and is
  reported in `plan`. The pose is RoboTwin's end-effector frame, **0.12 m behind the gripper centre** along the approach
  axis (same as the `proprio` end-effector poses). At most 50 rows per submit.
- Video is captured every `250/video_fps` physics steps; the chunk is appended to the recorded `(T, 34)` trajectory.
- `/observe` only reads (`last_s`); a hold chunk (`/submit` with `interpolate: "hold"`, `seconds`, no rows) holds the
  last command for at most a chunk's length.
- The same endpoints are MCP tools (`efe-robot`: `spec`, `observe`, `submit`, `finish`).

**Cameras.** `head_camera` (static, above the table), `front_camera` (static, facing the robot), `left_camera` /
`right_camera` (wrists), `observer_camera` and `world_camera1` (free third-person views); 320×240 RGB. Depth
(`include_depth`) is available on the head, front and wrist cameras. **`meta.cameras`** carries RoboTwin's per-camera
`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`; the wrist cameras move with the arms (`cam2world_gl/<cam>` per returned
frame). `/spec` states the agent's clock in `budget.wall_clock_note`.

**Proprioception (82 columns)**, grouped in `spec.proprio_groups`:

| columns | group | source |
|---|---|---|
| 0–13 | `joint_cmd` | commanded drive targets + gripper command |
| 14–27 | `ee_pose` | measured end-effector link pose (RoboTwin ee frame, 0.12 m behind the TCP) |
| 28–29 | `gripper_cmd` | commanded gripper value |
| 30–43 | `joint_pos` | measured joint positions (articulation qpos) + measured gripper opening, from the finger joint mapped to the command's [0,1] units (clipped to [-0.2, 1.2]) |
| 44–55 | `joint_vel` | measured arm joint velocities |
| 56–69 | `tcp_pose` | measured gripper-centre pose (RoboTwin `get_*_tcp_pose`) |
| 70–81 | `joint_effort` | stiffness·(target−q) + damping·(v_target−q̇) per arm joint: the PD drive's effort |

Not given: object poses, the scene layout, the success signal, resets.

## Grading

### Privileged (replay)

`tests/test.sh` runs `tests/grade.py` on `/app/output/trajectory.npz`: ONE open-loop replay of the trajectory from
`tests/instance.json`, in a fresh process; pass iff RoboTwin's `check_success` holds after the replay. The instance is
rebuilt from the RoboTwin seed and checked against the stored initial-state hash. With one replay there is no second
end state to compare: `deterministic` = 1, `determinism_checked` = 0, `replays` = 1 (`--repeat N`, N ≥ 2, kept for a
determinism measurement by hand: success = every replay succeeds and all final-state hashes agree).

- Agent failures (0): `missing_trajectory`, `bad_trajectory` (not an npz, a missing key, a wrong shape, NaN, more than
  200,000 rows), `wrong_family` (the file's `task` is another task's), a simulator error during the replay
  (`grader_error`).
- Infrastructure (`infra_error = 1`): a host that cannot rebuild the frozen instance (`instance_mismatch`: the
  initial-state hash differs, seen for four tasks on L40S cards), whether or not a trajectory was handed in; with no
  trajectory the grader first rebuilds the instance once in a child process (`instance_probe_error` if that fails or
  hangs).
- `reward.json` (numeric only): `success`, `all_success`, `deterministic`, `determinism_checked`, `replays`,
  `n_actions`, `sim_steps`, `grader_error`, `video_rendered`, the failure flags above, and self-reported cost
  (`agent_sessions`, `agent_resets`, `agent_sim_steps`, `agent_records`, `agent_replays`, `agent_cost_self_reported = 1`)
  from the session log.
- Video, after the verdict (it never changes it): `/logs/verifier/replay.mp4` (3×2 grid: world, observer, head / front,
  left wrist, right wrist) and `replay.last.png`, plus videos of the agent's last rollouts reconstructed from its
  traces (`agent_sessions/`); everything after the verdict stops at 1500 s so that the verifier ends inside its timeout.

### Standard (live)

**Grading** (the live episode, PROTOCOL H.4; no grading replay). `success` is RoboTwin's `check_success` on the
episode the sidecar ran: it is checked after every call that ran physics and only recorded (a success never ends the
episode: "Agent-ended episodes" below); the episode ends at the agent's `POST /finish` or when
the agent's time is up (the collect hook's SIGUSR1, after the monitor is sealed and the agent's container is stopped
with `kill -9 -1`) the final state is checked once more. `final.json` gets the verdict at once (`graded_by = "live"`, `replays = 0`, `finalized`,
the end state's hash `live_sha`, `video_pending: true`); `trajectory.npz` is saved as the deliverable. The frozen
instance is checked when the scene is built, before the agent is served: `rcb_traj.Session` compares the initial-state
hash with `instance.json`'s `state_sha` (a mismatch: one retry, then `instance_mismatch`, `infra_error = 1`). The
grader (`tests/grade.py`, in a separate sandbox over the sidecar's artifacts) transcribes it; `infra_error = 1` only
for a missing / unreadable final.json, no live verdict (`graded_by` absent: the hook gave up first, or
`finalize_error`), `sim_crashed`, `resume_failed`, `instance_mismatch`; `sim_crashed_on_call`, a simulator error from
the agent's call (`reason = "error"`), a timeout are the agent's 0. `reward.json` (numeric only): `success`,
`live_success`, `graded_by_live`, `replays`, `finalized`, `missing_log`, `n_actions`, `sim_steps`, `steps`,
`elapsed_s`, `video_rendered`, `video_pending`, `live_video`, `live_frames`, `infra_error`, `sim_error`,
`sim_crashed_on_call`, `instance_mismatch`, `sim_startups`, `grader_error`, and the agent-ended fields
(`ended_finish`, `ended_step_limit`, `ended_session_end`, `hidden_success_seen`).

#### Agent-ended episodes

Every standard task sets `RCB_AGENT_END "1"` in its sim service (PROTOCOL §3). `server.py` no longer ends the episode at
the first success: RoboTwin's `check_success` is still run after every call and only recorded
(`hidden_success_first_step`). The agent ends the episode with `POST /finish` (reason `finished`); the end of its
session (`timeout`) ends it too, and both are judged by `check_success` on the state they leave (end judgement `state`;
no settle window, the check is one state's). A simulator error still ends the episode with 0. The service has no step
cap, so `RCB_STEP_LIMIT` is refused. `final.json` adds the shared fields (`success_signal`, `ended_by`, `end_judgement`,
`hidden_success_seen`, `hidden_success_first_step`, `trial_hidden_success_seen`, `finish_time_s`). Without
`RCB_AGENT_END` the service behaves as described above.

#### Crash recovery

Every executed physics step is journaled (`trajectory_live.f64`) and every completed call logs a
checkpoint in `episode.jsonl`; compose restarts the service (`restart: on-failure:6`) and it resumes the same episode.
More than 2 crashes end the episode: `sim_crashed_on_call` if every crash happened while serving a call, else
`sim_crashed` (`infra_error = 1`). A scene build that hangs is killed by the service's startup watchdog
(`RCB_STARTUP_TIMEOUT_S`, 300 s). A host on which the frozen instance does not rebuild gets one retry and then
`reason = instance_mismatch` with `infra_error = 1`.

#### Video

After the verdict one pass over the trajectory (`rcb_live.LiveRecorder.render_videos`) rebuilds the frozen
instance, steps the rows once and writes both `replay.mp4` (six views, 320×240 tiles, a frame every
max(10, rows/600) steps) and `live.mp4` (below); `video_pending` is false when it is done or failed (`video_error`). The
collect hook waits for it until 2200 s (an episode whose physics filled the whole 1800 s cutoff, plus at most ~2100
rendered frames); a video not ready by then is lost, the verdict is not.

**Live recording** (sidecar only; the agent sees none of it):
- `live.mp4`: the episode as six views (world / observer / head · front / left wrist / right wrist, 213×160 tiles), each
  frame stamped `wall mm:ss  sim s  #call what-the-agent-sent`. Frames are sampled every `250 / RCB_LIVE_FPS` physics
  steps (default 10 per simulated second) only inside calls that ran physics, so the agent's thinking time takes no
  frames; with `RCB_LIVE_FILTER=moving` (default) frames are also skipped while nothing moves (max change of all poses /
  joint states below `RCB_LIVE_MOVE_EPS`, 1e-3).
- Capture (`RCB_LIVE`): **`replay`** (default) logs only call boundaries during the episode (no cost to the agent) and
  renders `live.mp4` after the verdict from the recorded trajectory, in the same pass as `replay.mp4`; `realtime` renders while the episode runs (the video
  survives a crash, but each frame costs ~150 ms of the agent's wall clock: a 10 s chunk took 20.6 s instead of 5.1 s);
  `off` disables it.
- `live_segments.jsonl` (per call) and `live_timeline.jsonl` (per frame) map every frame back to `episode.jsonl`;
  `calls/NNNNNN/actions.npy` is the exact action array of every `/submit`; `trajectory_live.f64` with
  `live_segments.jsonl` is enough to render the video offline; `startups.jsonl` has one line per service start.
- The verifier copies `live.mp4` and `live_timeline.jsonl` next to `replay.mp4` (which stays the authoritative video)
  and reports `live_video`, `live_frames`, `sim_startups`, `infra_error`.

## Tasks

47 of RoboTwin's 50 tasks, each as `robotwin_2_0_<task>-privileged` and `robotwin_2_0_<task>-standard` on the same
instance: adjust_bottle, beat_block_hammer, blocks_ranking_rgb, blocks_ranking_size, dump_bin_bigbin, grab_roller,
handover_block, handover_mic, hanging_mug, lift_pot, move_can_pot, move_pillbottle_pad, move_playingcard_away,
move_stapler_pad, open_laptop, open_microwave, pick_diverse_bottles, pick_dual_bottles, place_a2b_left,
place_a2b_right, place_bread_basket, place_bread_skillet, place_burger_fries, place_can_basket, place_cans_plasticbox,
place_container_plate, place_dual_shoes, place_empty_cup, place_fan, place_mouse_pad, place_object_basket,
place_object_scale, place_object_stand, place_phone_stand, place_shoe, press_stapler, put_bottles_dustbin,
rotate_qrcode, scan_object, shake_bottle, shake_bottle_horizontally, stack_blocks_three, stack_blocks_two,
stack_bowls_three, stack_bowls_two, stamp_seal, turn_switch. Instance seeds: 60417 for most; 28831, 77321 or 91573 for
the others (each task's `[metadata] instance_seed`). Each task's README states its exact success condition (from
`envs/<task>.py` `check_success`) with its thresholds.

Excluded: `click_bell` is left out because its success is a transient contact that a replay does not reproduce;
`click_alarmclock` and `put_object_cabinet` because the upstream expert failed on every seed we swept.

## Others

- **Reference solutions** (`solution/`, never in the image): privileged, RoboTwin 2.0's expert methods for the task
  (`play_once` and its helpers, scrubbed from the image) copied into `solution/oracle_<task>.py` and bound onto the env
  (for `stack_blocks_two`, rewritten), recorded into a trajectory by `solution/solve.sh`; the oracles restore the
  scrubbed attributes by rebuilding the scene with upstream's `load_actors`. Standard, the privileged expert's joint
  targets streamed as `joint_position` chunks (every K physics steps, dt = K/250 s, linear interpolation).
- **Resources** (caps per container, PROTOCOL §6): privileged `main` 4 CPUs, 10 GiB, 13 GiB of GPU memory (the GPU is
  held by `main`; the verifier gets 13 GiB of GPU memory); standard `main` 3 CPUs, 4 GiB, no GPU, `sim` 2 CPUs, 7 GiB,
  13 GiB of GPU memory. Any NVIDIA GPU; recommended RTX 4090 24GB / L4 24GB. The GPU is passed through with
  `environment/docker-compose.yaml` (nvidia device reservation).
- **Egress**: the agent reaches its model's API and the package registries only (`[agent] network_mode = "allowlist"`);
  the verifiers run with no network.
