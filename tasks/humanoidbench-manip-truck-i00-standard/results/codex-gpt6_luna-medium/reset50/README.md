# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-truck-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-manip-truck-i00-st__25UhTWR`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 20,886,704 / 117,201 (within the budget) |
| cost | $0.29 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 65, "sim_steps": 2955, "calls": 2394, "rows": 2935, "resets": 28, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 3586.9, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request; 2345 chunks in all, 2955 control steps over 29 episodes (28 of its 50 resets used); its own labels include "hold starting stance", "symmetric forward arm reach", "small forward weight shift" (and 125 more). Of the episodes before the last, 1 used all 1000 steps, 27 abandoned by a reset while running. The graded episode 29 was still running at its control step 65 when its 60 min ran out (timeout).
