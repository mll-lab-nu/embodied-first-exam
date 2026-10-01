# Claude Code + Claude Opus 5.5, effort medium — humanoidbench-loco-sit-hard-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-sit-hard-claudecode-opus55-medium-60min-text7`, trial `humanoidbench-loco-sit-hard-i00__f2jwHhM`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** (return 951.04 / pass mark 750) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Claude Code 2.1.283 via OpenRouter, `anthropic/claude-opus-5.5`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 308 s |
| tokens in / out | 829,072 / 13,598 (within the budget) |
| cost | $0.59 |
| verifier | `{"success": 1, "all_success": 1, "deterministic": 1, "n_actions": 1000, "final_reward": 0.9713269938000126, "sim_steps": 1000, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the agent's deliverable): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

reward rebuilt from memory + own ES over 3 keyframes; backward squat seated by step ~35; est 977.9, replay 951.04 passes in 5.1 min
