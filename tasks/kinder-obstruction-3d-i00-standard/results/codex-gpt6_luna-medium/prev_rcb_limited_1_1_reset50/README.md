# Codex + GPT-6 Luna, effort medium — kinder-obstruction-3d-i00-standard, 50 resets

Recorded 2026-09-29 before protocol v1.0 (Harbor job `kinder-limited-obstruction-3d-codex-gpt6luna-medium-60min-reset50-depth-ee`, trial `kinder-obstruction-3d-i00-limite__dX8S4Xw`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** |
| mode | standard; reset budget 50 (resets used: 1); sensors: cams+proprio+depth |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.159.2 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 43,979,302 / 353,988 (within the budget) |
| cost | $0.70 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 1004, "sim_steps": 1004, "steps": 1021, "resets": 1, "elapsed_s": 3668.2, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

wrist RGB-D + FK/IK on end_effector, all live in one episode; cleared 2 of 3 pad blocks; purple never released on pad; timeout at step 1004
