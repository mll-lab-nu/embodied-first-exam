# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-cabinet-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `n0-hb-standard`, trial `humanoidbench-manip-cabinet-i00__2W79ohj`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 0 (the standard configuration); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 462 s |
| tokens in / out | 1,925,515 / 43,450 (within the budget) |
| cost | $0.05 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 1000, "sim_steps": 1000, "calls": 48, "rows": 1000, "resets": 0, "reset_budget": 0, "sim_startups": 1, "elapsed_s": 369.0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request (after 4 free looks), then 16 chunks of 10–385 rows (hold, dt 0.02 s); its own labels: "stabilize at measured pose", "close fingers around cabinet contact", "recover neutral standing leg targets" (and 13 more). The episode used up its 1000 control steps without reaching the goal (failed).
