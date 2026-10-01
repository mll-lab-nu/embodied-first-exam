# Codex + GPT-6 Luna, effort medium — kinder-dynamo-i00-standard, 50 resets

Recorded 2026-09-29 before protocol v1.0 (Harbor job `kinder-limited-dynamo-codex-gpt6luna-medium-60min-reset50-depth-ee`, trial `kinder-dynamo-i00-limited__Yvhu3WJ`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** |
| mode | standard; reset budget 50 (resets used: 0); sensors: cams+proprio+depth |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.159.2 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 435 s |
| tokens in / out | 2,261,025 / 29,208 (within the budget) |
| cost | $0.05 |
| verifier | `{"success": 1, "live_success": 1, "replay_success": 1, "deterministic": 1, "finalized": 1, "n_actions": 724, "sim_steps": 724, "steps": 724, "resets": 0, "elapsed_s": 440.2, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the sidecar's record of the graded episode, in KinDER's own frame): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

base camera only; drove the room lane by lane on odometry, saw the green square at step 719; ep0 success at step 724, no reset used
