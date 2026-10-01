# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-maze-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `n0-hb-standard`, trial `humanoidbench-loco-maze-i00-stan__UZ5QADK`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 0 (the standard configuration); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 429 s |
| tokens in / out | 1,258,864 / 27,582 (within the budget) |
| cost | $0.03 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 432, "sim_steps": 432, "calls": 14, "rows": 392, "resets": 0, "reset_budget": 0, "sim_startups": 1, "elapsed_s": 364.8, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request (after 1 free look), then 8 chunks of 24–80 rows (linear, dt 0.02 s) and 2 timed watches. The task's own termination ended the episode at control step 432 of 1000 (failed; this task ends when the robot falls (its pelvis drops near the ground)).
