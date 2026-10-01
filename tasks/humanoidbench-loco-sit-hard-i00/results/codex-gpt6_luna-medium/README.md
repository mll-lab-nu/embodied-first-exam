# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-sit-hard-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-sit-hard-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-loco-sit-hard-i00__cHqn5LH`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** (return 946.31 / pass mark 750) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3501 s |
| tokens in / out | 16,879,490 / 77,977 (within the budget) |
| cost | $0.23 |
| verifier | `{"success": 1, "all_success": 1, "deterministic": 1, "n_actions": 1000, "final_reward": 0.9751891348954511, "sim_steps": 1000, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the agent's deliverable): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

chair pose from state; 55-step fast crouch then low-force seated target, no turn; own proxy 827.5; replay 946.31 passes; used 58 min
