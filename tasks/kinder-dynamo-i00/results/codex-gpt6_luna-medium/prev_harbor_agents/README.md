# Codex + GPT-6 Luna, effort medium — kinder-dynamo-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `kinder-full-dynamo-codex-gpt6luna-medium-60min`, trial `kinder-dynamo-i00__x3yhmL2`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is an earlier wording of today's; the scene and verifier are the same. |
| agent | Codex 0.158.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 178 s |
| tokens in / out | 330,491 / 7,165 (within the budget) |
| cost | $0.01 |
| verifier | `{"success": 1, "all_success": 1, "deterministic": 1, "n_actions": 135, "missing_trajectory": 0, "invalid_trajectory": 0, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the agent's deliverable): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

smoke test: waypoints around the chairs' north side, 135 steps; the recorded actions replay open loop
