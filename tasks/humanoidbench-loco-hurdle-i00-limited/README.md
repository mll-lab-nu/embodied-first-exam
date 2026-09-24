# humanoidbench-loco-hurdle-i00-limited

Limited-mode twin of `humanoidbench-loco-hurdle-i00` (same frozen instance, same success rule): the agent
gets only the `rcb-limited/1.1` client; HumanoidBench runs in the `sim` sidecar (`environment/docker-compose.yaml`,
GPU on the sidecar for rendering), which holds the reward, judges the episode, records it as a trajectory,
replays it from the frozen instance for success + determinism, and renders the replay video. The verifier runs
in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the unlimited task to
measure the cost of losing resets, privileged state and the ability to search.

| | |
|---|---|
| tier / mode | perception / limited: head-camera RGB + joint angles/velocities (HumanoidBench's own `image` + `proprio` sensors); no root pose, no hurdle or wall positions, no reward; no reset by default |
| action space | HumanoidBench's own: 19 normalised position targets, 50 Hz; one per request or a batch of K |
| knobs (compose env) | `RCB_RESET_BUDGET` (0), `RCB_OBS_PROPRIO` (1; 0 = images only), `RCB_OBS_IMU` (0), `RCB_OBS_ROOM_CAMERA` (0), `RCB_WALL_CLOCK_S` (3600). Per run from the shell: `RCB_RESET_BUDGET=3 RCB_OBS_IMU=1 harbor run ...`; the start line of `episode.jsonl` records the resulting `/spec` |
| agent API | `environment/rcb_client.py`: its docstring is the full reference; `instruction.md` points to it and keeps only task facts |
| reference solution | none, on purpose; the nop agent scores 0 |
| verification | `success` = live success ∧ replay success ∧ deterministic, computed inside the sidecar; `/logs/verifier/replay.mp4` |
| code | copied from `robotwin_2_0_stack_blocks_two-limited` (dev/kangrui) and split: `sim/rcb_service.py` is simulator-agnostic, `sim/server.py` is the HumanoidBench adapter. See `docs/LIMITED_MODE_1_1.md` |

Note: the head cameras see the walled track and the line of hurdles ahead. `room_camera` (off by default) stands
behind and above the start and looks down the course (`RCB_ROOM_CAMERA_POSE` in the compose file): the robot
stays in frame from x = 0 to 20 m.

Hand-maintained: not rendered by `scripts/humanoidbench/gen_tasks.py` (yet).

## Runs so far (2026-09-23, 60-minute budget, through OpenRouter)

| agent | resets | result |
|---|---|---|
| Codex + GPT-6 Luna, web search off | 3 | 0 (return 14.9 / 700, below the all-zero 17.9). 8.1 min, $0.05: the only run that steered from the cameras (23 looks in the graded episode). The robot was on the ground from about step 250, but upstream ends the episode only when the pelvis is below 0.2 m, which came at step 416; the agent read the tilted view as "leaning" and kept tuning the gait |
