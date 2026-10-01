# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-powerlift-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-powerlift-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-powerlift-i0__x5eJocW`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 296.87 / pass mark 800) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3496 s |
| tokens in / out | 21,788,244 / 220,622 (within the budget) |
| cost | $0.40 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 1000, "final_reward": 0.29667283599011285, "sim_steps": 1000, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

fixed crouch found at 8.8 min held 1000 steps; IK/contact grip searches only pushed the dumbbell sideways (max z 0.208 m); 296.87
