# Limited v2: GPT-6 Luna reasoning effort xhigh vs medium (Codex, 22 tasks, 60 min) — 2026-09-27

Same tasks, instructions and budget as `limited_v2_gpt6luna_2026-09-25.md` (medium). Jobs `v2-gpt6luna-xhigh-limited` + `v2-gpt6luna-xhigh-limited-rerun` (three trials whose sim sidecar crashed at start were rerun). Per task: `results/codex-gpt6_luna-xhigh/`.

**xhigh 8/22 vs medium 4/22.** Both: press_stapler, shake_bottle. xhigh only: dump_bin_bigbin, open_laptop, place_can_basket, place_object_stand, place_phone_stand, stack_blocks_two. medium only: move_can_pot, open_microwave.

- xhigh stops much later: median agent time 3070 s vs 685 s; 5 trials hit the 60 min limit (medium: 0).
- It uses the batch interface: 1.83 rows per submit vs 1.09; multi-row `joint_position` in 9 tasks vs 1.
- Fewer plan failures (107 vs 148) despite longer episodes.
- New failure mode: declaring success early (move_can_pot, place_fan, place_a2b_right).
- Cost: ≥200M input / 1.36M output tokens vs 103M / 0.68M (timed-out trials left no token counts).

| task | medium | xhigh | xhigh s | rows/submit |
|---|---|---|---|---|
| adjust_bottle | 0 | 0 | 3106 | 1.0 |
| dump_bin_bigbin | 0 | 1 | 2407 | 1.0 |
| handover_mic | 0 | 0 | 2150 | 2.4 |
| hanging_mug | 0 | 0 | 3600 | 1.0 |
| lift_pot | 0 | 0 | 3600 | 1.0 |
| move_can_pot | 1 | 0 | 691 | 1.0 |
| open_laptop | 0 | 1 | 2453 | 2.5 |
| open_microwave | 1 | 0 | 3588 | 2.3 |
| pick_dual_bottles | 0 | 0 | 657 | 3.2 |
| place_a2b_right | 0 | 0 | 3415 | 1.1 |
| place_can_basket | 0 | 1 | 2668 | 4.9 |
| place_dual_shoes | 0 | 0 | 3475 | 1.6 |
| place_fan | 0 | 0 | 696 | 1.0 |
| place_object_basket | 0 | 0 | 3600 | 1.5 |
| place_object_stand | 0 | 1 | 3033 | 1.0 |
| place_phone_stand | 0 | 1 | 1401 | 1.0 |
| press_stapler | 1 | 1 | 660 | 1.8 |
| put_bottles_dustbin | 0 | 0 | 3600 | 1.9 |
| rotate_qrcode | 0 | 0 | 3600 | 1.0 |
| scan_object | 0 | 0 | 3198 | 4.8 |
| shake_bottle | 1 | 1 | 1035 | 1.0 |
| stack_blocks_two | 0 | 1 | 3158 | 2.4 |
