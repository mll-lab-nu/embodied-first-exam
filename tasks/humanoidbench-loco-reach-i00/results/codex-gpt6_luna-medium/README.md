# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-reach-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-reach-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-loco-reach-i00__qGroVq8`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** (return 19184.07 / pass mark 12000) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3532 s |
| tokens in / out | 26,539,635 / 151,082 (within the budget) |
| cost | $0.37 |
| verifier | `{"success": 1, "all_success": 1, "deterministic": 1, "n_actions": 1000, "final_reward": 19.5526952301051, "sim_steps": 1000, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the agent's deliverable): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

searched a constant-target crouch that stands 1000 steps + damped-Jacobian left-arm correction; hand <5 cm 96.6% of steps; 19184.07 pass
