# Codex + GPT-6 Luna, effort medium — kinder-packing-3d-i00-standard, 50 resets

Recorded 2026-09-29 before protocol v1.0 (Harbor job `kinder-limited-packing-3d-codex-gpt6luna-medium-60min-reset50-depth-ee`, trial `kinder-packing-3d-i00-limited__AjQfrNF`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** |
| mode | standard; reset budget 50 (resets used: 0); sensors: cams+proprio+depth |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.159.2 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3589 s |
| tokens in / out | 46,528,920 / 363,859 (within the budget) |
| cost | $0.76 |
| verifier | `{"success": 1, "live_success": 1, "replay_success": 1, "deterministic": 1, "finalized": 1, "n_actions": 1657, "sim_steps": 1657, "steps": 1657, "resets": 0, "elapsed_s": 3702.3, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the sidecar's record of the graded episode, in KinDER's own frame): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

FK on spec end_effector + wrist depth; one live episode, 0/50 resets; repacked tray after blocked moves; ep0 success at step 1657
