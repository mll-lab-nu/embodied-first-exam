# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-package-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-manip-package-i00__uLJSM8Y`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 1536 s |
| tokens in / out | 10,355,181 / 87,479 (within the budget) |
| cost | $0.16 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 1000, "sim_steps": 6291, "calls": 3611, "rows": 5921, "resets": 50, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 1508.1, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request; 1920 chunks in all, 6291 control steps over 51 episodes (50 of its 50 resets used); its own labels include "turn and reach toward package", "short alternating approach steps". Of the episodes before the last, 50 abandoned by a reset while running. The graded episode 51 used up its 1000 control steps without reaching the goal (failed).
