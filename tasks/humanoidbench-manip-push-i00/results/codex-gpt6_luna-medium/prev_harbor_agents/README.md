# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-push-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-push-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-push-i00__tXojwC4`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** (return 997.80 / pass mark 700) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3598 s |
| tokens in / out | 27,828,267 / 156,857 (within the budget) |
| cost | $0.42 |
| verifier | `{"success": 1, "all_success": 1, "deterministic": 1, "n_actions": 8, "final_reward": 999.8605417406861, "sim_steps": 8, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the agent's deliverable): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

right-hand site-Jacobian IK, asymmetric legs + timed torso yaw; random search/CEM cut 108 -> 8 steps; box 3.04 cm from goal, 997.80
