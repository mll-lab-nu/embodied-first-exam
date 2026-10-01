# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-package-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-package-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-package-i00__VYZwaGN`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 805.63 / pass mark 1500) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3513 s |
| tokens in / out | 25,930,228 / 114,564 (within the budget) |
| cost | $0.34 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 145, "final_reward": 999.7927124106341, "sim_steps": 145, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

DE-tuned 3-phase pose sequence: robot falls toward box, arm sweep lands it 0.09 m from target at step 145 (robot prone); 805.63
