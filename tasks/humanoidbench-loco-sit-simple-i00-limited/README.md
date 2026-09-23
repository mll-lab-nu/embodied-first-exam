# humanoidbench-loco-sit-simple-i00-limited

Limited-mode twin of `humanoidbench-loco-sit-simple-i00` (same frozen instance, same success rule): the agent
gets only the `rcb-limited/1.1` client; HumanoidBench runs in the `sim` sidecar (`environment/docker-compose.yaml`,
GPU on the sidecar for rendering), which holds the reward, judges the episode, records it as a trajectory,
replays it from the frozen instance for success + determinism, and renders the replay video. The verifier runs
in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the unlimited task to
measure the cost of losing resets, privileged state and the ability to search.

| | |
|---|---|
| tier / mode | perception / limited: head-camera RGB + joint angles/velocities (HumanoidBench's own `image` + `proprio` sensors); no root pose, no chair pose, no reward; no reset by default |
| action space | HumanoidBench's own: 19 normalised position targets, 50 Hz; one per request or a batch of K |
| knobs (compose env) | `RCB_RESET_BUDGET` (0), `RCB_OBS_PROPRIO` (1; 0 = images only), `RCB_OBS_IMU` (0), `RCB_OBS_ROOM_CAMERA` (0), `RCB_WALL_CLOCK_S` (3600). Per run from the shell: `RCB_RESET_BUDGET=3 RCB_OBS_IMU=1 harbor run ...`; the start line of `episode.jsonl` records the resulting `/spec` |
| agent API | `environment/rcb_client.py`: its docstring is the full reference; `instruction.md` points to it and keeps only task facts |
| reference solution | none, on purpose; the nop agent scores 0 |
| verification | `success` = live success ∧ replay success ∧ deterministic, computed inside the sidecar; `/logs/verifier/replay.mp4` |
| code | copied from `robotwin_2_0_stack_blocks_two-limited` (dev/kangrui) and split: `sim/rcb_service.py` is simulator-agnostic, `sim/server.py` is the HumanoidBench adapter. See `docs/LIMITED_MODE_1_1.md` |

Note: the chair is behind the robot and never enters the head cameras' view (floor and horizon only);
`room_camera` (the recording camera frozen at its starting pose) sees both.

Hand-maintained: not rendered by `scripts/humanoidbench/gen_tasks.py` (yet).

## Runs so far (2026-09-22, 30-minute budget, through OpenRouter)

| agent | resets | result |
|---|---|---|
| Codex + DeepSeek V4.1 Flash, web search on (the Codex default) | 0 | fell at step 394 while probing one joint at a time. OpenRouter ran searches server-side, after which the agent's reasoning quoted the hidden reward constants |
| Codex + DeepSeek V4.1 Flash, web search off | 3 | spent all three resets calibrating; the last episode fell at step 66 (a sign error in its own action mapping) |
| Claude Code + Opus 5.5, web tools off | 1 | **success** at step 771, one minute, $0.40, from recalled HumanoidBench facts: the exact actuator ranges, the chair behind the robot, the seat-height band |

All three used the instruction from before the API moved into the client's docstring.
