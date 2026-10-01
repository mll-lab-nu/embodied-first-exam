# Claude Code + Claude Opus 5.5, effort medium — humanoidbench-manip-door-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-door-claudecode-opus55-medium-60min-text7`, trial `humanoidbench-manip-door-i00__zRNvQmV`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **1 (success)** (return 676.02 / pass mark 600) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Claude Code 2.1.283 via OpenRouter, `anthropic/claude-opus-5.5`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 2929 s |
| tokens in / out | 5,781,424 / 55,050 (within the budget) |
| cost | $2.71 |
| verifier | `{"success": 1, "all_success": 1, "deterministic": 1, "n_actions": 1000, "final_reward": 0.5178329017957999, "sim_steps": 1000, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

`trajectory.npz` is the graded trajectory (the agent's deliverable): the positive example this task's human review checks (PROTOCOL §2.7).

## What happened

sampling MPC on memory-rebuilt reward proxy, 2 stages: pull door ~1.25 rad backing out of its swing, then walk through; best of seeds; 676.02
