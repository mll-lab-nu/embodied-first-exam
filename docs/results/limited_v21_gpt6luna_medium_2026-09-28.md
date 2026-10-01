# Limited v2.1 (measured proprioception) vs v2.0: GPT-6 Luna medium, 22 tasks, 60 min — 2026-09-28

Job `v21-gpt6luna-medium-limited`. Per task: `results/codex-gpt6_luna-medium/`.

**2.1 medium 3/22** (open_laptop, open_microwave, place_object_stand) vs 2.0 medium 4/22 vs 2.0 xhigh 8/22. The measured proprioception did not help at medium effort; the difference is within single-trial noise.

| | 2.0 medium | 2.1 medium | 2.0 xhigh |
|---|---|---|---|
| success | 4 | 3 | 8 |
| median agent s | 684 | 660 | 3070 |
| stopped within 15 min | 15 | 13 | 4 |
| rows per submit | 1.09 | 2.58 | 1.83 |
| tasks with multi-row joint_position | 1 | 6 | 9 |
| plan failures | 148 | 185 | 107 |
| input tokens (M) | 103 | 94 | 200 |

- Early stopping is unchanged at medium; reasoning effort (how long the agent persists) matters far more than the extra sensing.
- Agents did read the new fields (measured gripper opening, TCP pose, depth in every task; drive effort in a few) without turning them into successes.
- open_microwave: live success, verification replay success and deterministic per the service log, but final.json was never finalized because rendering replay.mp4 + live.mp4 for a 40k-step episode outlasted the collect hook; Harbor scored 0. Re-verified offline (two fresh replays, success + deterministic) and counted as 1 here. Fixed: the verdict is written before any video is rendered, live.mp4 rendering is capped (RCB_LIVE_BUDGET_S, live_truncated), the collect hook waits up to 800 s.
