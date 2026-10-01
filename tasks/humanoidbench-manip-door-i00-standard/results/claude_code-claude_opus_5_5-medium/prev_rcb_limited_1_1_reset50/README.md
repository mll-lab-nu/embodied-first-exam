# Claude Code + Claude Opus 5.5, effort medium — humanoidbench-manip-door-i00-standard, 50 resets

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-limited-door-claudecode-opus55-medium-60min-reset50-imu-roomcam-text7`, trial `humanoidbench-manip-door-i00-lim__4qvYP8i`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 132.77 / pass mark 600) |
| mode | standard; reset budget 50 (resets used: 34); sensors: head+joints+imu+room |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Claude Code 2.1.283 via OpenRouter, `anthropic/claude-opus-5.5`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 861 s |
| tokens in / out | 4,362,403 / 54,873 (within the budget) |
| cost | $2.40 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 1000, "sim_steps": 9999, "steps": 9999, "resets": 34, "elapsed_s": 855.0, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

COM-over-feet ankle balancer from spec masses; FK tip = left_hand com_m (0.31 m off), judged arms pass through door; quit 14.3 min, 16 resets left
