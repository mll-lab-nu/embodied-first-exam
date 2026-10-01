# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-cabinet-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-manip-cabinet-i00__9RaNEnj`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 36,082,386 / 140,995 (within the budget) |
| cost | $0.46 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 156, "sim_steps": 2922, "calls": 360, "rows": 2922, "resets": 33, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 3592.4, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move 1 min after its first request; 150 chunks in all, 2922 control steps over 34 episodes (33 of its 50 resets used); its own labels include "brief left arm reach probe", "left hand raised toward upper sliding-door handle", "slider preset, grasp hands" (and 16 more). Of the episodes before the last, 33 abandoned by a reset while running. The graded episode 34 was still running at its control step 156 when its 60 min ran out (timeout).
