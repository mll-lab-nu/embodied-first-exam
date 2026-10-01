# Limited mode v2 (rcb-limited/2.0): Codex + GPT-6 Luna, 22 tasks, 60 min — 2026-09-25

Harbor job `v2-gpt6luna-limited` (one trial per task, ChatGPT subscription, separate verifier). Per-task folders: `tasks/robotwin_2_0_<task>-limited/results/codex-gpt6_luna-medium/prev_rcb_limited_2_0/`.

**Result: 4/22** (move_can_pot, open_microwave, press_stapler, shake_bottle). Same model on the v1 protocol (2026-09-23): 1/21 limited, 11/21 unlimited.

- Agents stop early: median agent time 712 s of 3600; 15/22 stopped within 15 min; 17 of the 18 failures ended with budget left.
- The batch interface is barely used: 1131 submits, 1.09 rows per submit on average, almost all single-row `ee_pose`; only open_microwave used multi-row `joint_position`; 7/22 used `observe(seconds>0)`.
- 148 CuRobo plan failures (planner knows the table, not the objects); planned paths often push objects away.
- Failure stops: knocked over / out of view then quit (7), intact scene but gave up (6), near miss without fine-tuning (3), kept recovering and failed (1), budget exhausted with partial progress (1).

| task | v2 limited | agent s | submits | rows/submit | plan fails |
|---|---|---|---|---|---|
| adjust_bottle | 0 | 397 | 13 | 1.0 | 0 |
| dump_bin_bigbin | 0 | 591 | 59 | 1.0 | 7 |
| handover_mic | 0 | 836 | 57 | 1.0 | 2 |
| hanging_mug | 0 | 1987 | 103 | 1.0 | 7 |
| lift_pot | 0 | 812 | 55 | 1.0 | 5 |
| move_can_pot | 1 | 735 | 45 | 1.0 | 0 |
| open_laptop | 0 | 269 | 19 | 1.0 | 3 |
| open_microwave | 1 | 657 | 27 | 2.0 | 2 |
| pick_dual_bottles | 0 | 114 | 7 | 1.1 | 2 |
| place_a2b_right | 0 | 486 | 54 | 1.0 | 4 |
| place_can_basket | 0 | 343 | 29 | 1.0 | 1 |
| place_dual_shoes | 0 | 571 | 43 | 1.0 | 11 |
| place_fan | 0 | 3065 | 94 | 1.0 | 20 |
| place_object_basket | 0 | 578 | 33 | 1.0 | 3 |
| place_object_stand | 0 | 1366 | 61 | 1.1 | 2 |
| place_phone_stand | 0 | 420 | 32 | 1.0 | 4 |
| press_stapler | 1 | 151 | 4 | 1.5 | 0 |
| put_bottles_dustbin | 0 | 3571 | 96 | 1.0 | 27 |
| rotate_qrcode | 0 | 2571 | 96 | 1.3 | 25 |
| scan_object | 0 | 1572 | 42 | 1.4 | 5 |
| shake_bottle | 1 | 712 | 10 | 2.7 | 1 |
| stack_blocks_two | 0 | 1844 | 152 | 1.0 | 17 |

## Ablation: 'do not stop after a failed attempt' paragraph (job `v2-gpt6luna-limited-persist`, task copies under gitignored `exps/ablation_persist/`)

| task | baseline | s | + persistence | s |
|---|---|---|---|---|
| open_laptop | 0 | 269 | 1 | 2031 |
| place_a2b_right | 0 | 486 | 0 | 3544 |
| place_object_basket | 0 | 578 | 0 | 3600 |
| place_phone_stand | 0 | 420 | 0 | 2198 |
| stack_blocks_two | 0 | 1844 | 0 | 3547 |

1/5 vs 0/5. The hint makes agents use the budget (mean 720 s → 2980 s) but recovery attempts mostly push objects off the table (plan failures 31 → 112). open_laptop succeeded by switching to multi-row `joint_position` chunks. Early stopping is one cause, not the main one: camera-only localisation and object-unaware planning dominate.
