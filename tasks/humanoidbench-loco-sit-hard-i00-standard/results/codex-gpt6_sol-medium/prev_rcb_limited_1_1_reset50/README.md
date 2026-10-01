# Codex + GPT-6 Sol, effort medium — humanoidbench-loco-sit-hard-i00-standard, 50 resets

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-limited-sit-hard-codex-gpt6sol-medium-60min-reset50-imu-roomcam-text7`, trial `humanoidbench-loco-sit-hard-i00__XFr67eM`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 383.12 / pass mark 750) |
| mode | standard; reset budget 50 (resets used: 50); sensors: head+joints+imu+room |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-sol`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 576 s |
| tokens in / out | 1,643,301 / 18,363 (within the budget) |
| cost | $0.62 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 788, "sim_steps": 23908, "steps": 23908, "resets": 50, "elapsed_s": 521.4, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

hold start pose then timed crouch; 7 eps sat 1000 steps (516-610) on seat front edge; resets gone at 7 min; graded ep tipped at step 788
