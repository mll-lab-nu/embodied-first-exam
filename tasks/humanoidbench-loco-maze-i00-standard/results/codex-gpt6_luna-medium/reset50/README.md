# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-maze-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-loco-maze-i00-stan__KkujT8x`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 2683 s |
| tokens in / out | 20,761,902 / 133,841 (within the budget) |
| cost | $0.31 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 1000, "sim_steps": 21296, "calls": 2004, "rows": 21296, "resets": 50, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 2637.8, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move 1 min after its first request; 1844 chunks in all, 21296 control steps over 51 episodes (50 of its 50 resets used); its own labels include "alternating gait calibration", "IMU corrected alternating gait", "camera and IMU corrected alternating gait". Of the episodes before the last, 11 ended by the task's own termination, 11 used all 1000 steps, 28 abandoned by a reset while running. The graded episode 51 used up its 1000 control steps without reaching the goal (failed).
