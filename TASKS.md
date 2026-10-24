# Task list

Generated from `main` at `6847111cea2163fc2826b535745a928e1fa35e9c` by `scripts/dataset_manifest.py list` (`.github/workflows/task-list.yml`); do not edit: every number is the task's own (`task.toml`), the core set's from `docs/core_set.toml`. 2224 task directories. Modes: P = privileged, S = standard, RT = standard-realtime.

## Per benchmark

| Benchmark | Tasks (P / S / RT) | Cutoff (P / S / RT) | Oracle (full / partial / none) | Validated | Core set (tasks) | Network (allowlist / open) |
|---|---|---|---|---|---|---|
| ABC Sim | 29 / 29 / 2 | 3600 s · 3600 s · 3600 s | 60 / 0 / 0 | 60 of 60 | — | 60 / 0 |
| AM-Bench | 8 / 9 / — | 3600 s · 3600 s · — | 17 / 0 / 0 | 17 of 17 | 4 | 17 / 0 |
| AutoBio | 9 / 9 / — | 3600 s · 3600 s · — | 18 / 0 / 0 | 18 of 18 | — | 18 / 0 |
| BEHAVIOR-1K | 100 / 100 / — | 7200 s · 7200 s · — | 0 / 4 / 196 | 0 of 200 | 142 | 200 / 0 |
| BiGym 2.0 | 13 / 13 / 13 | 3600 s · 3600 s · 3600 s | 0 / 0 / 39 | 0 of 39 | 30 | 39 / 0 |
| DexHand | 30 / 30 / — | 3600 s · 3600 s · — | 60 / 0 / 0 | 60 of 60 | 46 | 60 / 0 |
| DexJoCo | 11 / 11 / — | 3600 s · 3600 s · — | 22 / 0 / 0 | 22 of 22 | 4 | 22 / 0 |
| DexToolBench | 21 / 21 / — | 3600 s · 3600 s · — | 12 / 30 / 0 | 12 of 42 | 40 | 42 / 0 |
| Embodied Olympics - Fun | 79 / 79 / 21 | 7200 s · 7200 s · 7200 s | 52 / 0 / 127 | 52 of 179 | 123 | 0 / 179 |
| Embodied Olympics - Match | 6 / 2 / 17 | 7200 s / 14400 s (mixed) · 7200 s · 7200 s / 14400 s (mixed) | 2 / 23 / 0 | 2 of 25 | 24 | 25 / 0 |
| Embodied Safety Exam | — / 71 / 5 | — · 3600 s · 3600 s | 76 / 0 / 0 | 76 of 76 | 54 | 76 / 0 |
| HumanoidBench | 10 / 10 / 10 | 3600 s · 3600 s · 3600 s | 3 / 0 / 27 | 3 of 30 | 24 | 30 / 0 |
| iSpatialGym | 12 / 12 / — | 3600 s · 3600 s · — | 0 / 0 / 24 | 0 of 24 | 16 | 24 / 0 |
| KinDER | 5 / 5 / — | 1800 s · 1800 s · — | 2 / 0 / 8 | 2 of 10 | 8 | 10 / 0 |
| LabUtopia | 9 / 9 / — | 3600 s · 3600 s · — | 18 / 0 / 0 | 18 of 18 | — | 18 / 0 |
| LIBERO-MAX | 64 / 64 / — | 1800 s · 1800 s · — | 128 / 0 / 0 | 128 of 128 | 4 | 128 / 0 |
| ManiGuard | 30 / 30 / — | 3600 s · 3600 s · — | 28 / 0 / 32 | 28 of 60 | 14 | 60 / 0 |
| MetaWorld+ | 50 / 50 / — | 1800 s · 1800 s · — | 100 / 0 / 0 | 100 of 100 | 4 | 100 / 0 |
| MolmoSpaces | 8 / 8 / — | 3600 s · 3600 s · — | 0 / 0 / 16 | 0 of 16 | 4 | 16 / 0 |
| MuJoCo Playground | 13 / 13 / 1 | 1800 s · 1800 s · 1800 s | 27 / 0 / 0 | 27 of 27 | 15 | 27 / 0 |
| MyoSuite | 22 / 22 / 1 | 3600 s · 3600 s · 3600 s | 6 / 0 / 39 | 6 of 45 | 26 | 45 / 0 |
| Panda Dynamic Scenes | 25 / 25 / 19 | 3600 s · 3600 s · 3600 s | 69 / 0 / 0 | 69 of 69 | 28 | 69 / 0 |
| RoboARC | 106 / 106 / — | 10800 s · 10800 s · — | 208 / 0 / 4 | 208 of 212 | 116 | 212 / 0 |
| RoboCasa | 29 / 29 / — | 3600 s · 3600 s · — | 58 / 0 / 0 | 58 of 58 | 4 | 58 / 0 |
| RoboCasa-GR1 | 24 / 24 / — | 3600 s · 3600 s · — | 48 / 0 / 0 | 48 of 48 | 2 | 48 / 0 |
| RoboCasa365 | 50 / 50 / 1 | 3600 s · 3600 s · 3600 s | 100 / 0 / 1 | 100 of 101 | 10 | 101 / 0 |
| RoboDojo | 48 / 54 / — | 3600 s · 3600 s · — | 0 / 0 / 102 | 0 of 102 | 24 | 102 / 0 |
| roboEngineer | — / 30 / — | — · 3600 s / 14400 s (mixed) · — | 16 / 5 / 9 | 16 of 30 | 15 | 30 / 0 |
| RoboLab | 53 / 53 / — | 3600 s · 3600 s · — | 4 / 0 / 102 | 4 of 106 | 12 | 106 / 0 |
| RoboPaint | 43 / 43 / — | 3600 s · 3600 s · — | 0 / 86 / 0 | 0 of 86 | 44 | 86 / 0 |
| RoboTwin 2.0 | 47 / 47 / — | 1800 s · 1800 s · — | 94 / 0 / 0 | 94 of 94 | 6 | 94 / 0 |
| RoboWits | 15 / 15 / — | 3600 s · 3600 s · — | 0 / 4 / 26 | 0 of 30 | 12 | 30 / 0 |
| VLABench | 36 / 36 / — | 1800 s · 1800 s · — | 72 / 0 / 0 | 72 of 72 | 4 | 72 / 0 |
| YAMLab | 10 / 10 / — | 3600 s · 3600 s · — | 20 / 0 / 0 | 20 of 20 | 4 | 20 / 0 |

## Comparable configurations

Results are ranked only within one configuration: protocol version, mode, cutoff, reset budget, slowdown S and network (`scripts/task_conventions.py` `config_key`; docs/protocol/running.md "Results"). Validated and unvalidated tasks (no `oracle = "full"` and no `[metadata] validated = true`) are ranked together; the columns below count them for reference. Each task's settings are in `tasks.json`.

| Mode | Cutoff | Resets | S | Network | Validated tasks | Unvalidated tasks |
|---|---|---|---|---|---|---|
| privileged | 1800 s | — | — | allowlist | 211 | 4 |
| privileged | 3600 s | — | — | allowlist | 260 | 249 |
| privileged | 7200 s | — | — | allowlist | 0 | 103 |
| privileged | 7200 s | — | — | open | 23 | 56 |
| privileged | 10800 s | — | — | allowlist | 104 | 2 |
| privileged | 14400 s | — | — | allowlist | 0 | 3 |
| standard | 1800 s | 0 | — | allowlist | 202 | 4 |
| standard | 1800 s | 10 | — | allowlist | 9 | 0 |
| standard | 3600 s | 0 | — | allowlist | 269 | 212 |
| standard | 3600 s | 3 | — | allowlist | 25 | 0 |
| standard | 3600 s | 10 | — | allowlist | 3 | 19 |
| standard | 3600 s | 20 | — | allowlist | 36 | 15 |
| standard | 3600 s | 50 | — | allowlist | 1 | 9 |
| standard | 7200 s | 0 | — | allowlist | 2 | 100 |
| standard | 7200 s | 50 | — | open | 23 | 56 |
| standard | 10800 s | 0 | — | allowlist | 104 | 2 |
| standard | 14400 s | 0 | — | allowlist | 14 | 14 |
| standard-realtime | 1800 s | 10 | 1 | allowlist | 1 | 0 |
| standard-realtime | 3600 s | 0 | 1 | allowlist | 5 | 13 |
| standard-realtime | 3600 s | 3 | 2 | allowlist | 7 | 0 |
| standard-realtime | 3600 s | 3 | 3 | allowlist | 8 | 0 |
| standard-realtime | 3600 s | 3 | 4 | allowlist | 2 | 0 |
| standard-realtime | 3600 s | 3 | 6 | allowlist | 2 | 0 |
| standard-realtime | 3600 s | 10 | 1 | allowlist | 2 | 1 |
| standard-realtime | 3600 s | 10 | 2 | allowlist | 0 | 1 |
| standard-realtime | 3600 s | 50 | 1 | allowlist | 1 | 9 |
| standard-realtime | 7200 s | 0 | 5 | allowlist | 0 | 1 |
| standard-realtime | 7200 s | 0 | 10 | allowlist | 0 | 6 |
| standard-realtime | 7200 s | 10 | 1 | open | 6 | 15 |
| standard-realtime | 14400 s | 0 | 10 | allowlist | 0 | 4 |
| standard-realtime | 14400 s | 0 | 20 | allowlist | 0 | 6 |

## Tasks

### ABC Sim

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `abc-sim-ball-tray-i00-privileged` | privileged | ball_tray | 3600 s | full | yes | excluded | allowlist | dynamic |
| `abc-sim-ball-tray-i00-standard` | standard | ball_tray | 3600 s | full | yes | excluded | allowlist | dynamic |
| `abc-sim-ball-tray-i00-standard-realtime` | standard-realtime | ball_tray | 3600 s | full | yes | excluded | allowlist | dynamic |
| `abc-sim-chess-i00-privileged` | privileged | chess | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-chess-i00-standard` | standard | chess | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-conveyor-pick-i00-privileged` | privileged | conveyor_pick | 3600 s | full | yes | excluded | allowlist | dynamic |
| `abc-sim-conveyor-pick-i00-standard` | standard | conveyor_pick | 3600 s | full | yes | excluded | allowlist | dynamic |
| `abc-sim-conveyor-pick-i00-standard-realtime` | standard-realtime | conveyor_pick | 3600 s | full | yes | excluded | allowlist | dynamic |
| `abc-sim-count-four-i00-privileged` | privileged | count_four | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-four-i00-standard` | standard | count_four | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-i00-privileged` | privileged | count | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-i00-standard` | standard | count | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-one-i00-privileged` | privileged | count_one | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-one-i00-standard` | standard | count_one | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-three-i00-privileged` | privileged | count_three | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-three-i00-standard` | standard | count_three | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-two-i00-privileged` | privileged | count_two | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-count-two-i00-standard` | standard | count_two | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-dish-rack-i00-privileged` | privileged | dish_rack | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-dish-rack-i00-standard` | standard | dish_rack | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-drawer-search-i00-privileged` | privileged | drawer_search | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-drawer-search-i00-standard` | standard | drawer_search | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-grab-clutter-i00-privileged` | privileged | grab_clutter | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-grab-clutter-i00-standard` | standard | grab_clutter | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-hang-mug-i00-privileged` | privileged | hang_mug | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-hang-mug-i00-standard` | standard | hang_mug | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-inhand-transfer-i00-privileged` | privileged | inhand_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-inhand-transfer-i00-standard` | standard | inhand_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-lego-i00-privileged` | privileged | lego | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-lego-i00-standard` | standard | lego | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-nuts-bolts-i00-privileged` | privileged | nuts_bolts | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-nuts-bolts-i00-standard` | standard | nuts_bolts | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-pouring-i00-privileged` | privileged | pouring | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-pouring-i00-standard` | standard | pouring | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-put-bottles-i00-privileged` | privileged | put_bottles | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-put-bottles-i00-standard` | standard | put_bottles | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-put-relative-i00-privileged` | privileged | put_relative | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-put-relative-i00-standard` | standard | put_relative | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-abc-i00-privileged` | privileged | spell_abc | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-abc-i00-standard` | standard | spell_abc | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-agi-i00-privileged` | privileged | spell_agi | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-agi-i00-standard` | standard | spell_agi | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-bair-i00-privileged` | privileged | spell_bair | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-bair-i00-standard` | standard | spell_bair | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-cat-i00-privileged` | privileged | spell_cat | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-cat-i00-standard` | standard | spell_cat | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-dog-i00-privileged` | privileged | spell_dog | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-dog-i00-standard` | standard | spell_dog | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-fish-i00-privileged` | privileged | spell_fish | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-fish-i00-standard` | standard | spell_fish | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-xdof-i00-privileged` | privileged | spell_xdof | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-xdof-i00-standard` | standard | spell_xdof | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-yam-i00-privileged` | privileged | spell_yam | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-spell-yam-i00-standard` | standard | spell_yam | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-sweep-i00-privileged` | privileged | sweep | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-sweep-i00-standard` | standard | sweep | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-throw-bottles-i00-privileged` | privileged | throw_bottles | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-throw-bottles-i00-standard` | standard | throw_bottles | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-turn-mug-i00-privileged` | privileged | turn_mug | 3600 s | full | yes | excluded | allowlist | static |
| `abc-sim-turn-mug-i00-standard` | standard | turn_mug | 3600 s | full | yes | excluded | allowlist | static |

### AM-Bench

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `ambench-cabinet-pick-place-fahexa-i00-privileged` | privileged | cabinet_pick_place_fahexa | 3600 s | full | yes | core | allowlist | static |
| `ambench-cabinet-pick-place-fahexa-i00-standard` | standard | cabinet_pick_place_fahexa | 3600 s | full | yes | core | allowlist | static |
| `ambench-lemon-harvesting-fahexa-i00-privileged` | privileged | lemon_harvesting_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-lemon-harvesting-fahexa-i00-standard` | standard | lemon_harvesting_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-ndt-fahexa-i00-privileged` | privileged | ndt_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-ndt-fahexa-i00-standard` | standard | ndt_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-open-door-fahexa-i00-privileged` | privileged | open_door_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-open-door-fahexa-i00-standard` | standard | open_door_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-peg-in-hole-fahexa-i00-privileged` | privileged | peg_in_hole_fahexa | 3600 s | full | yes | core | allowlist | static |
| `ambench-peg-in-hole-fahexa-i00-standard` | standard | peg_in_hole_fahexa | 3600 s | full | yes | core | allowlist | static |
| `ambench-press-button-fahexa-i00-privileged` | privileged | press_button_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-press-button-fahexa-i00-standard` | standard | press_button_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-pull-lever-fahexa-i00-standard` | standard | pull_lever_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-push-slider-fahexa-i00-privileged` | privileged | push_slider_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-push-slider-fahexa-i00-standard` | standard | push_slider_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-rotate-valve-fahexa-i00-privileged` | privileged | rotate_valve_fahexa | 3600 s | full | yes | excluded | allowlist | static |
| `ambench-rotate-valve-fahexa-i00-standard` | standard | rotate_valve_fahexa | 3600 s | full | yes | excluded | allowlist | static |

### AutoBio

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `autobio-insert-centrifuge-5430-i00-privileged` | privileged | insert_centrifuge_5430 | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-insert-centrifuge-5430-i00-standard` | standard | insert_centrifuge_5430 | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-insert-i00-privileged` | privileged | insert | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-insert-i00-standard` | standard | insert | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-pickup-i00-privileged` | privileged | pickup | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-pickup-i00-standard` | standard | pickup | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-pipette-i00-privileged` | privileged | pipette | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-pipette-i00-standard` | standard | pipette | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-screw-loose-i00-privileged` | privileged | screw_loose | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-screw-loose-i00-standard` | standard | screw_loose | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-screw-tighten-i00-privileged` | privileged | screw_tighten | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-screw-tighten-i00-standard` | standard | screw_tighten | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-thermal-cycler-close-i00-privileged` | privileged | thermal_cycler_close | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-thermal-cycler-close-i00-standard` | standard | thermal_cycler_close | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-thermal-cycler-open-i00-privileged` | privileged | thermal_cycler_open | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-thermal-cycler-open-i00-standard` | standard | thermal_cycler_open | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-thermal-mixer-i00-privileged` | privileged | thermal_mixer | 3600 s | full | yes | excluded | allowlist | static |
| `autobio-thermal-mixer-i00-standard` | standard | thermal_mixer | 3600 s | full | yes | excluded | allowlist | static |

### BEHAVIOR-1K

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `behavior-assembling-gift-baskets-i00-privileged` | privileged | assembling_gift_baskets | 7200 s | none | no | core | allowlist | static |
| `behavior-assembling-gift-baskets-i00-standard` | standard | assembling_gift_baskets | 7200 s | none | no | core | allowlist | static |
| `behavior-attach-a-camera-to-a-tripod-i00-privileged` | privileged | attach_a_camera_to_a_tripod | 7200 s | none | no | excluded | allowlist | static |
| `behavior-attach-a-camera-to-a-tripod-i00-standard` | standard | attach_a_camera_to_a_tripod | 7200 s | none | no | excluded | allowlist | static |
| `behavior-boxing-books-up-for-storage-i00-privileged` | privileged | boxing_books_up_for_storage | 7200 s | none | no | core | allowlist | static |
| `behavior-boxing-books-up-for-storage-i00-standard` | standard | boxing_books_up_for_storage | 7200 s | none | no | core | allowlist | static |
| `behavior-boxing-food-after-dinner-i00-privileged` | privileged | boxing_food_after_dinner | 7200 s | none | no | core | allowlist | static |
| `behavior-boxing-food-after-dinner-i00-standard` | standard | boxing_food_after_dinner | 7200 s | none | no | core | allowlist | static |
| `behavior-bringing-in-wood-i00-privileged` | privileged | bringing_in_wood | 7200 s | none | no | core | allowlist | static |
| `behavior-bringing-in-wood-i00-standard` | standard | bringing_in_wood | 7200 s | none | no | core | allowlist | static |
| `behavior-bringing-paper-to-recycling-i00-privileged` | privileged | bringing_paper_to_recycling | 7200 s | none | no | core | allowlist | static |
| `behavior-bringing-paper-to-recycling-i00-standard` | standard | bringing_paper_to_recycling | 7200 s | none | no | core | allowlist | static |
| `behavior-bringing-water-i00-privileged` | privileged | bringing_water | 7200 s | none | no | core | allowlist | static |
| `behavior-bringing-water-i00-standard` | standard | bringing_water | 7200 s | none | no | core | allowlist | static |
| `behavior-can-meat-i00-privileged` | privileged | can_meat | 7200 s | none | no | core | allowlist | static |
| `behavior-can-meat-i00-standard` | standard | can_meat | 7200 s | none | no | core | allowlist | static |
| `behavior-canning-food-i00-privileged` | privileged | canning_food | 7200 s | none | no | core | allowlist | static |
| `behavior-canning-food-i00-standard` | standard | canning_food | 7200 s | none | no | core | allowlist | static |
| `behavior-carrying-in-groceries-i00-privileged` | privileged | carrying_in_groceries | 7200 s | none | no | core | allowlist | static |
| `behavior-carrying-in-groceries-i00-standard` | standard | carrying_in_groceries | 7200 s | none | no | core | allowlist | static |
| `behavior-carrying-out-garden-furniture-i00-privileged` | privileged | carrying_out_garden_furniture | 7200 s | none | no | core | allowlist | static |
| `behavior-carrying-out-garden-furniture-i00-standard` | standard | carrying_out_garden_furniture | 7200 s | none | no | core | allowlist | static |
| `behavior-chop-an-onion-i00-privileged` | privileged | chop_an_onion | 7200 s | none | no | excluded | allowlist | static |
| `behavior-chop-an-onion-i00-standard` | standard | chop_an_onion | 7200 s | none | no | excluded | allowlist | static |
| `behavior-chopping-wood-i00-privileged` | privileged | chopping_wood | 7200 s | none | no | core | allowlist | static |
| `behavior-chopping-wood-i00-standard` | standard | chopping_wood | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-a-keyboard-i00-privileged` | privileged | clean_a_keyboard | 7200 s | none | no | excluded | allowlist | static |
| `behavior-clean-a-keyboard-i00-standard` | standard | clean_a_keyboard | 7200 s | none | no | excluded | allowlist | static |
| `behavior-clean-a-patio-i00-privileged` | privileged | clean_a_patio | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-a-patio-i00-standard` | standard | clean_a_patio | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-a-trumpet-i00-privileged` | privileged | clean_a_trumpet | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-a-trumpet-i00-standard` | standard | clean_a_trumpet | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-boxing-gloves-i00-privileged` | privileged | clean_boxing_gloves | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-boxing-gloves-i00-standard` | standard | clean_boxing_gloves | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-up-broken-glass-i00-privileged` | privileged | clean_up_broken_glass | 7200 s | none | no | excluded | allowlist | static |
| `behavior-clean-up-broken-glass-i00-standard` | standard | clean_up_broken_glass | 7200 s | none | no | excluded | allowlist | static |
| `behavior-clean-up-your-desk-i00-privileged` | privileged | clean_up_your_desk | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-up-your-desk-i00-standard` | standard | clean_up_your_desk | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-your-rusty-garden-tools-i00-privileged` | privileged | clean_your_rusty_garden_tools | 7200 s | none | no | core | allowlist | static |
| `behavior-clean-your-rusty-garden-tools-i00-standard` | standard | clean_your_rusty_garden_tools | 7200 s | none | no | core | allowlist | static |
| `behavior-cleaning-up-branches-and-twigs-i00-privileged` | privileged | cleaning_up_branches_and_twigs | 7200 s | none | no | core | allowlist | static |
| `behavior-cleaning-up-branches-and-twigs-i00-standard` | standard | cleaning_up_branches_and_twigs | 7200 s | none | no | core | allowlist | static |
| `behavior-cleaning-up-plates-and-food-i00-privileged` | privileged | cleaning_up_plates_and_food | 7200 s | none | no | core | allowlist | static |
| `behavior-cleaning-up-plates-and-food-i00-standard` | standard | cleaning_up_plates_and_food | 7200 s | none | no | core | allowlist | static |
| `behavior-clearing-food-from-table-into-fridge-i00-privileged` | privileged | clearing_food_from_table_into_fridge | 7200 s | none | no | core | allowlist | static |
| `behavior-clearing-food-from-table-into-fridge-i00-standard` | standard | clearing_food_from_table_into_fridge | 7200 s | none | no | core | allowlist | static |
| `behavior-collecting-aluminum-cans-i00-privileged` | privileged | collecting_aluminum_cans | 7200 s | none | no | core | allowlist | static |
| `behavior-collecting-aluminum-cans-i00-standard` | standard | collecting_aluminum_cans | 7200 s | none | no | core | allowlist | static |
| `behavior-collecting-childrens-toys-i00-privileged` | privileged | collecting_childrens_toys | 7200 s | none | no | core | allowlist | static |
| `behavior-collecting-childrens-toys-i00-standard` | standard | collecting_childrens_toys | 7200 s | none | no | core | allowlist | static |
| `behavior-composting-waste-i00-privileged` | privileged | composting_waste | 7200 s | none | no | excluded | allowlist | static |
| `behavior-composting-waste-i00-standard` | standard | composting_waste | 7200 s | none | no | excluded | allowlist | static |
| `behavior-cook-a-brisket-i00-privileged` | privileged | cook_a_brisket | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-a-brisket-i00-standard` | standard | cook_a_brisket | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-a-frozen-pie-i00-privileged` | privileged | cook_a_frozen_pie | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-a-frozen-pie-i00-standard` | standard | cook_a_frozen_pie | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-bacon-i00-privileged` | privileged | cook_bacon | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-bacon-i00-standard` | standard | cook_bacon | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-broccolini-i00-privileged` | privileged | cook_broccolini | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-broccolini-i00-standard` | standard | cook_broccolini | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-brussels-sprouts-i00-privileged` | privileged | cook_brussels_sprouts | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-brussels-sprouts-i00-standard` | standard | cook_brussels_sprouts | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-cabbage-i00-privileged` | privileged | cook_cabbage | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-cabbage-i00-standard` | standard | cook_cabbage | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-hot-dogs-i00-privileged` | privileged | cook_hot_dogs | 7200 s | none | no | core | allowlist | static |
| `behavior-cook-hot-dogs-i00-standard` | standard | cook_hot_dogs | 7200 s | none | no | core | allowlist | static |
| `behavior-dispose-of-batteries-i00-privileged` | privileged | dispose_of_batteries | 7200 s | none | no | core | allowlist | static |
| `behavior-dispose-of-batteries-i00-standard` | standard | dispose_of_batteries | 7200 s | none | no | core | allowlist | static |
| `behavior-dispose-of-glass-i00-privileged` | privileged | dispose_of_glass | 7200 s | none | no | excluded | allowlist | static |
| `behavior-dispose-of-glass-i00-standard` | standard | dispose_of_glass | 7200 s | none | no | excluded | allowlist | static |
| `behavior-freeze-fruit-i00-privileged` | privileged | freeze_fruit | 7200 s | none | no | core | allowlist | static |
| `behavior-freeze-fruit-i00-standard` | standard | freeze_fruit | 7200 s | none | no | core | allowlist | static |
| `behavior-freeze-pies-i00-privileged` | privileged | freeze_pies | 7200 s | none | no | core | allowlist | static |
| `behavior-freeze-pies-i00-standard` | standard | freeze_pies | 7200 s | none | no | core | allowlist | static |
| `behavior-getting-organized-for-work-i00-privileged` | privileged | getting_organized_for_work | 7200 s | none | no | excluded | allowlist | static |
| `behavior-getting-organized-for-work-i00-standard` | standard | getting_organized_for_work | 7200 s | none | no | excluded | allowlist | static |
| `behavior-halve-an-egg-i00-privileged` | privileged | halve_an_egg | 7200 s | none | no | core | allowlist | static |
| `behavior-halve-an-egg-i00-standard` | standard | halve_an_egg | 7200 s | none | no | core | allowlist | static |
| `behavior-hanging-pictures-i00-privileged` | privileged | hanging_pictures | 7200 s | none | no | excluded | allowlist | static |
| `behavior-hanging-pictures-i00-standard` | standard | hanging_pictures | 7200 s | none | no | excluded | allowlist | static |
| `behavior-hiding-Easter-eggs-i00-privileged` | privileged | hiding_Easter_eggs | 7200 s | none | no | excluded | allowlist | static |
| `behavior-hiding-Easter-eggs-i00-standard` | standard | hiding_Easter_eggs | 7200 s | none | no | excluded | allowlist | static |
| `behavior-installing-a-fax-machine-i00-privileged` | privileged | installing_a_fax_machine | 7200 s | none | no | core | allowlist | static |
| `behavior-installing-a-fax-machine-i00-standard` | standard | installing_a_fax_machine | 7200 s | none | no | core | allowlist | static |
| `behavior-installing-a-modem-i00-privileged` | privileged | installing_a_modem | 7200 s | none | no | excluded | allowlist | static |
| `behavior-installing-a-modem-i00-standard` | standard | installing_a_modem | 7200 s | none | no | excluded | allowlist | static |
| `behavior-installing-a-scanner-i00-privileged` | privileged | installing_a_scanner | 7200 s | none | no | excluded | allowlist | static |
| `behavior-installing-a-scanner-i00-standard` | standard | installing_a_scanner | 7200 s | none | no | excluded | allowlist | static |
| `behavior-installing-smoke-detectors-i00-privileged` | privileged | installing_smoke_detectors | 7200 s | none | no | excluded | allowlist | static |
| `behavior-installing-smoke-detectors-i00-standard` | standard | installing_smoke_detectors | 7200 s | none | no | excluded | allowlist | static |
| `behavior-laying-tile-floors-i00-privileged` | privileged | laying_tile_floors | 7200 s | none | no | core | allowlist | static |
| `behavior-laying-tile-floors-i00-standard` | standard | laying_tile_floors | 7200 s | none | no | core | allowlist | static |
| `behavior-loading-the-car-i00-privileged` | privileged | loading_the_car | 7200 s | none | no | core | allowlist | static |
| `behavior-loading-the-car-i00-standard` | standard | loading_the_car | 7200 s | none | no | core | allowlist | static |
| `behavior-make-cabinet-doors-i00-privileged` | privileged | make_cabinet_doors | 7200 s | none | no | excluded | allowlist | static |
| `behavior-make-cabinet-doors-i00-standard` | standard | make_cabinet_doors | 7200 s | none | no | excluded | allowlist | static |
| `behavior-make-gift-bags-for-baby-showers-i00-privileged` | privileged | make_gift_bags_for_baby_showers | 7200 s | none | no | core | allowlist | static |
| `behavior-make-gift-bags-for-baby-showers-i00-standard` | standard | make_gift_bags_for_baby_showers | 7200 s | none | no | core | allowlist | static |
| `behavior-make-microwave-popcorn-i00-privileged` | privileged | make_microwave_popcorn | 7200 s | none | no | excluded | allowlist | static |
| `behavior-make-microwave-popcorn-i00-standard` | standard | make_microwave_popcorn | 7200 s | none | no | excluded | allowlist | static |
| `behavior-make-pizza-i00-privileged` | privileged | make_pizza | 7200 s | none | no | core | allowlist | static |
| `behavior-make-pizza-i00-standard` | standard | make_pizza | 7200 s | none | no | core | allowlist | static |
| `behavior-make-rose-centerpieces-i00-privileged` | privileged | make_rose_centerpieces | 7200 s | none | no | core | allowlist | static |
| `behavior-make-rose-centerpieces-i00-standard` | standard | make_rose_centerpieces | 7200 s | none | no | core | allowlist | static |
| `behavior-moving-boxes-to-storage-i00-privileged` | privileged | moving_boxes_to_storage | 7200 s | none | no | excluded | allowlist | static |
| `behavior-moving-boxes-to-storage-i00-standard` | standard | moving_boxes_to_storage | 7200 s | none | no | excluded | allowlist | static |
| `behavior-organizing-art-supplies-i00-privileged` | privileged | organizing_art_supplies | 7200 s | none | no | core | allowlist | static |
| `behavior-organizing-art-supplies-i00-standard` | standard | organizing_art_supplies | 7200 s | none | no | core | allowlist | static |
| `behavior-organizing-school-stuff-i00-privileged` | privileged | organizing_school_stuff | 7200 s | none | no | core | allowlist | static |
| `behavior-organizing-school-stuff-i00-standard` | standard | organizing_school_stuff | 7200 s | none | no | core | allowlist | static |
| `behavior-outfit-a-basic-toolbox-i00-privileged` | privileged | outfit_a_basic_toolbox | 7200 s | none | no | core | allowlist | static |
| `behavior-outfit-a-basic-toolbox-i00-standard` | standard | outfit_a_basic_toolbox | 7200 s | none | no | core | allowlist | static |
| `behavior-packing-meal-for-delivery-i00-privileged` | privileged | packing_meal_for_delivery | 7200 s | none | no | core | allowlist | static |
| `behavior-packing-meal-for-delivery-i00-standard` | standard | packing_meal_for_delivery | 7200 s | none | no | core | allowlist | static |
| `behavior-picking-up-toys-i00-privileged` | privileged | picking_up_toys | 7200 s | none | no | excluded | allowlist | static |
| `behavior-picking-up-toys-i00-standard` | standard | picking_up_toys | 7200 s | none | no | excluded | allowlist | static |
| `behavior-picking-up-trash-i00-privileged` | privileged | picking_up_trash | 7200 s | partial | no | excluded | allowlist | static |
| `behavior-picking-up-trash-i00-standard` | standard | picking_up_trash | 7200 s | partial | no | excluded | allowlist | static |
| `behavior-polishing-shoes-i00-privileged` | privileged | polishing_shoes | 7200 s | none | no | core | allowlist | static |
| `behavior-polishing-shoes-i00-standard` | standard | polishing_shoes | 7200 s | none | no | core | allowlist | static |
| `behavior-preparing-lunch-box-i00-privileged` | privileged | preparing_lunch_box | 7200 s | none | no | core | allowlist | static |
| `behavior-preparing-lunch-box-i00-standard` | standard | preparing_lunch_box | 7200 s | none | no | core | allowlist | static |
| `behavior-put-together-a-basic-pruning-kit-i00-privileged` | privileged | put_together_a_basic_pruning_kit | 7200 s | none | no | core | allowlist | static |
| `behavior-put-together-a-basic-pruning-kit-i00-standard` | standard | put_together_a_basic_pruning_kit | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-away-Halloween-decorations-i00-privileged` | privileged | putting_away_Halloween_decorations | 7200 s | none | no | excluded | allowlist | static |
| `behavior-putting-away-Halloween-decorations-i00-standard` | standard | putting_away_Halloween_decorations | 7200 s | none | no | excluded | allowlist | static |
| `behavior-putting-away-toys-i00-privileged` | privileged | putting_away_toys | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-away-toys-i00-standard` | standard | putting_away_toys | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-dirty-dishes-in-sink-i00-privileged` | privileged | putting_dirty_dishes_in_sink | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-dirty-dishes-in-sink-i00-standard` | standard | putting_dirty_dishes_in_sink | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-dishes-away-after-cleaning-i00-privileged` | privileged | putting_dishes_away_after_cleaning | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-dishes-away-after-cleaning-i00-standard` | standard | putting_dishes_away_after_cleaning | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-shoes-on-rack-i00-privileged` | privileged | putting_shoes_on_rack | 7200 s | partial | no | excluded | allowlist | static |
| `behavior-putting-shoes-on-rack-i00-standard` | standard | putting_shoes_on_rack | 7200 s | partial | no | excluded | allowlist | static |
| `behavior-putting-up-Christmas-decorations-inside-i00-privileged` | privileged | putting_up_Christmas_decorations_inside | 7200 s | none | no | core | allowlist | static |
| `behavior-putting-up-Christmas-decorations-inside-i00-standard` | standard | putting_up_Christmas_decorations_inside | 7200 s | none | no | core | allowlist | static |
| `behavior-re-shelving-library-books-i00-privileged` | privileged | re_shelving_library_books | 7200 s | none | no | core | allowlist | static |
| `behavior-re-shelving-library-books-i00-standard` | standard | re_shelving_library_books | 7200 s | none | no | core | allowlist | static |
| `behavior-rearrange-your-room-i00-privileged` | privileged | rearrange_your_room | 7200 s | none | no | core | allowlist | static |
| `behavior-rearrange-your-room-i00-standard` | standard | rearrange_your_room | 7200 s | none | no | core | allowlist | static |
| `behavior-rearranging-kitchen-furniture-i00-privileged` | privileged | rearranging_kitchen_furniture | 7200 s | none | no | core | allowlist | static |
| `behavior-rearranging-kitchen-furniture-i00-standard` | standard | rearranging_kitchen_furniture | 7200 s | none | no | core | allowlist | static |
| `behavior-scrubbing-bathroom-floor-i00-privileged` | privileged | scrubbing_bathroom_floor | 7200 s | none | no | excluded | allowlist | static |
| `behavior-scrubbing-bathroom-floor-i00-standard` | standard | scrubbing_bathroom_floor | 7200 s | none | no | excluded | allowlist | static |
| `behavior-set-up-a-coffee-station-in-your-kitchen-i00-privileged` | privileged | set_up_a_coffee_station_in_your_kitchen | 7200 s | none | no | excluded | allowlist | static |
| `behavior-set-up-a-coffee-station-in-your-kitchen-i00-standard` | standard | set_up_a_coffee_station_in_your_kitchen | 7200 s | none | no | excluded | allowlist | static |
| `behavior-setting-mousetraps-i00-privileged` | privileged | setting_mousetraps | 7200 s | none | no | excluded | allowlist | static |
| `behavior-setting-mousetraps-i00-standard` | standard | setting_mousetraps | 7200 s | none | no | excluded | allowlist | static |
| `behavior-setting-the-fire-i00-privileged` | privileged | setting_the_fire | 7200 s | none | no | core | allowlist | static |
| `behavior-setting-the-fire-i00-standard` | standard | setting_the_fire | 7200 s | none | no | core | allowlist | static |
| `behavior-setting-the-table-i00-privileged` | privileged | setting_the_table | 7200 s | none | no | core | allowlist | static |
| `behavior-setting-the-table-i00-standard` | standard | setting_the_table | 7200 s | none | no | core | allowlist | static |
| `behavior-setup-a-bar-for-a-cocktail-party-i00-privileged` | privileged | setup_a_bar_for_a_cocktail_party | 7200 s | none | no | core | allowlist | static |
| `behavior-setup-a-bar-for-a-cocktail-party-i00-standard` | standard | setup_a_bar_for_a_cocktail_party | 7200 s | none | no | core | allowlist | static |
| `behavior-slicing-vegetables-i00-privileged` | privileged | slicing_vegetables | 7200 s | none | no | core | allowlist | static |
| `behavior-slicing-vegetables-i00-standard` | standard | slicing_vegetables | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-books-on-shelf-i00-privileged` | privileged | sorting_books_on_shelf | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-books-on-shelf-i00-standard` | standard | sorting_books_on_shelf | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-bottles-cans-and-paper-i00-privileged` | privileged | sorting_bottles_cans_and_paper | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-bottles-cans-and-paper-i00-standard` | standard | sorting_bottles_cans_and_paper | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-household-items-i00-privileged` | privileged | sorting_household_items | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-household-items-i00-standard` | standard | sorting_household_items | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-vegetables-i00-privileged` | privileged | sorting_vegetables | 7200 s | none | no | core | allowlist | static |
| `behavior-sorting-vegetables-i00-standard` | standard | sorting_vegetables | 7200 s | none | no | core | allowlist | static |
| `behavior-spraying-for-bugs-i00-privileged` | privileged | spraying_for_bugs | 7200 s | none | no | excluded | allowlist | static |
| `behavior-spraying-for-bugs-i00-standard` | standard | spraying_for_bugs | 7200 s | none | no | excluded | allowlist | static |
| `behavior-spraying-fruit-trees-i00-privileged` | privileged | spraying_fruit_trees | 7200 s | none | no | excluded | allowlist | static |
| `behavior-spraying-fruit-trees-i00-standard` | standard | spraying_fruit_trees | 7200 s | none | no | excluded | allowlist | static |
| `behavior-stacking-wood-i00-privileged` | privileged | stacking_wood | 7200 s | none | no | excluded | allowlist | static |
| `behavior-stacking-wood-i00-standard` | standard | stacking_wood | 7200 s | none | no | excluded | allowlist | static |
| `behavior-store-batteries-i00-privileged` | privileged | store_batteries | 7200 s | none | no | core | allowlist | static |
| `behavior-store-batteries-i00-standard` | standard | store_batteries | 7200 s | none | no | core | allowlist | static |
| `behavior-store-honey-i00-privileged` | privileged | store_honey | 7200 s | none | no | excluded | allowlist | static |
| `behavior-store-honey-i00-standard` | standard | store_honey | 7200 s | none | no | excluded | allowlist | static |
| `behavior-store-produce-i00-privileged` | privileged | store_produce | 7200 s | none | no | core | allowlist | static |
| `behavior-store-produce-i00-standard` | standard | store_produce | 7200 s | none | no | core | allowlist | static |
| `behavior-storing-food-i00-privileged` | privileged | storing_food | 7200 s | none | no | core | allowlist | static |
| `behavior-storing-food-i00-standard` | standard | storing_food | 7200 s | none | no | core | allowlist | static |
| `behavior-sweeping-garage-i00-privileged` | privileged | sweeping_garage | 7200 s | none | no | core | allowlist | static |
| `behavior-sweeping-garage-i00-standard` | standard | sweeping_garage | 7200 s | none | no | core | allowlist | static |
| `behavior-thawing-frozen-food-i00-privileged` | privileged | thawing_frozen_food | 7200 s | none | no | core | allowlist | static |
| `behavior-thawing-frozen-food-i00-standard` | standard | thawing_frozen_food | 7200 s | none | no | core | allowlist | static |
| `behavior-tidying-bathroom-i00-privileged` | privileged | tidying_bathroom | 7200 s | none | no | excluded | allowlist | static |
| `behavior-tidying-bathroom-i00-standard` | standard | tidying_bathroom | 7200 s | none | no | excluded | allowlist | static |
| `behavior-tidying-bedroom-i00-privileged` | privileged | tidying_bedroom | 7200 s | none | no | excluded | allowlist | static |
| `behavior-tidying-bedroom-i00-standard` | standard | tidying_bedroom | 7200 s | none | no | excluded | allowlist | static |
| `behavior-tidying-living-room-i00-privileged` | privileged | tidying_living_room | 7200 s | none | no | core | allowlist | static |
| `behavior-tidying-living-room-i00-standard` | standard | tidying_living_room | 7200 s | none | no | core | allowlist | static |
| `behavior-turning-on-radio-i00-privileged` | privileged | turning_on_radio | 7200 s | none | no | excluded | allowlist | static |
| `behavior-turning-on-radio-i00-standard` | standard | turning_on_radio | 7200 s | none | no | excluded | allowlist | static |
| `behavior-turning-out-all-lights-before-sleep-i00-privileged` | privileged | turning_out_all_lights_before_sleep | 7200 s | none | no | core | allowlist | static |
| `behavior-turning-out-all-lights-before-sleep-i00-standard` | standard | turning_out_all_lights_before_sleep | 7200 s | none | no | core | allowlist | static |
| `behavior-unloading-the-car-i00-privileged` | privileged | unloading_the_car | 7200 s | none | no | core | allowlist | static |
| `behavior-unloading-the-car-i00-standard` | standard | unloading_the_car | 7200 s | none | no | core | allowlist | static |
| `behavior-vacuuming-floors-i00-privileged` | privileged | vacuuming_floors | 7200 s | none | no | core | allowlist | static |
| `behavior-vacuuming-floors-i00-standard` | standard | vacuuming_floors | 7200 s | none | no | core | allowlist | static |
| `behavior-wash-a-baseball-cap-i00-privileged` | privileged | wash_a_baseball_cap | 7200 s | none | no | core | allowlist | static |
| `behavior-wash-a-baseball-cap-i00-standard` | standard | wash_a_baseball_cap | 7200 s | none | no | core | allowlist | static |
| `behavior-wash-dog-toys-i00-privileged` | privileged | wash_dog_toys | 7200 s | none | no | core | allowlist | static |
| `behavior-wash-dog-toys-i00-standard` | standard | wash_dog_toys | 7200 s | none | no | core | allowlist | static |

### BiGym 2.0

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `bigym2-dishwasher-close-i00-privileged` | privileged | dishwasher-close | 3600 s | none | no | core | allowlist | static |
| `bigym2-dishwasher-close-i00-standard` | standard | dishwasher-close | 3600 s | none | no | core | allowlist | static |
| `bigym2-dishwasher-close-i00-standard-realtime` | standard-realtime | dishwasher-close | 3600 s | none | no | core | allowlist | static |
| `bigym2-dishwasher-load-plates-i00-privileged` | privileged | dishwasher-load-plates | 3600 s | none | no | core | allowlist | static |
| `bigym2-dishwasher-load-plates-i00-standard` | standard | dishwasher-load-plates | 3600 s | none | no | core | allowlist | static |
| `bigym2-dishwasher-load-plates-i00-standard-realtime` | standard-realtime | dishwasher-load-plates | 3600 s | none | no | core | allowlist | static |
| `bigym2-drawer-top-open-i00-privileged` | privileged | drawer-top-open | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-drawer-top-open-i00-standard` | standard | drawer-top-open | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-drawer-top-open-i00-standard-realtime` | standard-realtime | drawer-top-open | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-flip-cup-i00-privileged` | privileged | flip-cup | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-flip-cup-i00-standard` | standard | flip-cup | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-flip-cup-i00-standard-realtime` | standard-realtime | flip-cup | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-flip-cutlery-i00-privileged` | privileged | flip-cutlery | 3600 s | none | no | core | allowlist | static |
| `bigym2-flip-cutlery-i00-standard` | standard | flip-cutlery | 3600 s | none | no | core | allowlist | static |
| `bigym2-flip-cutlery-i00-standard-realtime` | standard-realtime | flip-cutlery | 3600 s | none | no | core | allowlist | static |
| `bigym2-move-two-plates-i00-privileged` | privileged | move-two-plates | 3600 s | none | no | core | allowlist | static |
| `bigym2-move-two-plates-i00-standard` | standard | move-two-plates | 3600 s | none | no | core | allowlist | static |
| `bigym2-move-two-plates-i00-standard-realtime` | standard-realtime | move-two-plates | 3600 s | none | no | core | allowlist | static |
| `bigym2-pick-box-i00-privileged` | privileged | pick-box | 3600 s | none | no | core | allowlist | static |
| `bigym2-pick-box-i00-standard` | standard | pick-box | 3600 s | none | no | core | allowlist | static |
| `bigym2-pick-box-i00-standard-realtime` | standard-realtime | pick-box | 3600 s | none | no | core | allowlist | static |
| `bigym2-put-cups-i00-privileged` | privileged | put-cups | 3600 s | none | no | core | allowlist | static |
| `bigym2-put-cups-i00-standard` | standard | put-cups | 3600 s | none | no | core | allowlist | static |
| `bigym2-put-cups-i00-standard-realtime` | standard-realtime | put-cups | 3600 s | none | no | core | allowlist | static |
| `bigym2-reach-target-dual-i00-privileged` | privileged | reach-target-dual | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-reach-target-dual-i00-standard` | standard | reach-target-dual | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-reach-target-dual-i00-standard-realtime` | standard-realtime | reach-target-dual | 3600 s | none | no | excluded | allowlist | static |
| `bigym2-sandwich-remove-i00-privileged` | privileged | sandwich-remove | 3600 s | none | no | core | allowlist | static |
| `bigym2-sandwich-remove-i00-standard` | standard | sandwich-remove | 3600 s | none | no | core | allowlist | static |
| `bigym2-sandwich-remove-i00-standard-realtime` | standard-realtime | sandwich-remove | 3600 s | none | no | core | allowlist | static |
| `bigym2-saucepan-to-hob-i00-privileged` | privileged | saucepan-to-hob | 3600 s | none | no | core | allowlist | static |
| `bigym2-saucepan-to-hob-i00-standard` | standard | saucepan-to-hob | 3600 s | none | no | core | allowlist | static |
| `bigym2-saucepan-to-hob-i00-standard-realtime` | standard-realtime | saucepan-to-hob | 3600 s | none | no | core | allowlist | static |
| `bigym2-stack-blocks-i00-privileged` | privileged | stack-blocks | 3600 s | none | no | core | allowlist | static |
| `bigym2-stack-blocks-i00-standard` | standard | stack-blocks | 3600 s | none | no | core | allowlist | static |
| `bigym2-stack-blocks-i00-standard-realtime` | standard-realtime | stack-blocks | 3600 s | none | no | core | allowlist | static |
| `bigym2-wall-cupboard-open-i00-privileged` | privileged | wall-cupboard-open | 3600 s | none | no | core | allowlist | static |
| `bigym2-wall-cupboard-open-i00-standard` | standard | wall-cupboard-open | 3600 s | none | no | core | allowlist | static |
| `bigym2-wall-cupboard-open-i00-standard-realtime` | standard-realtime | wall-cupboard-open | 3600 s | none | no | core | allowlist | static |

### DexHand

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `dexhand-assemble-hamburger-i00-privileged` | privileged | assemble_hamburger | 3600 s | full | yes | core | allowlist | static |
| `dexhand-assemble-hamburger-i00-standard` | standard | assemble_hamburger | 3600 s | full | yes | core | allowlist | static |
| `dexhand-batter-whisk-i00-privileged` | privileged | batter_whisk | 3600 s | full | yes | core | allowlist | static |
| `dexhand-batter-whisk-i00-standard` | standard | batter_whisk | 3600 s | full | yes | core | allowlist | static |
| `dexhand-bicycle-pump-stroke-i00-privileged` | privileged | bicycle_pump_stroke | 3600 s | full | yes | core | allowlist | static |
| `dexhand-bicycle-pump-stroke-i00-standard` | standard | bicycle_pump_stroke | 3600 s | full | yes | core | allowlist | static |
| `dexhand-binder-page-load-i00-privileged` | privileged | binder_page_load | 3600 s | full | yes | core | allowlist | static |
| `dexhand-binder-page-load-i00-standard` | standard | binder_page_load | 3600 s | full | yes | core | allowlist | static |
| `dexhand-book-page-turn-i00-privileged` | privileged | book_page_turn | 3600 s | full | yes | core | allowlist | static |
| `dexhand-book-page-turn-i00-standard` | standard | book_page_turn | 3600 s | full | yes | core | allowlist | static |
| `dexhand-boot-sole-brush-i00-privileged` | privileged | boot_sole_brush | 3600 s | full | yes | core | allowlist | static |
| `dexhand-boot-sole-brush-i00-standard` | standard | boot_sole_brush | 3600 s | full | yes | core | allowlist | static |
| `dexhand-coffee-stir-i00-privileged` | privileged | coffee_stir | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-coffee-stir-i00-standard` | standard | coffee_stir | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-drying-rack-unfold-i00-privileged` | privileged | drying_rack_unfold | 3600 s | full | yes | core | allowlist | static |
| `dexhand-drying-rack-unfold-i00-standard` | standard | drying_rack_unfold | 3600 s | full | yes | core | allowlist | static |
| `dexhand-envelope-letter-insert-i00-privileged` | privileged | envelope_letter_insert | 3600 s | full | yes | core | allowlist | static |
| `dexhand-envelope-letter-insert-i00-standard` | standard | envelope_letter_insert | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-cube-layer-i00-privileged` | privileged | essential_cube_layer | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-essential-cube-layer-i00-standard` | standard | essential_cube_layer | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-essential-cube-reorient-i00-privileged` | privileged | essential_cube_reorient | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-cube-reorient-i00-standard` | standard | essential_cube_reorient | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-held-joystick-i00-privileged` | privileged | essential_held_joystick | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-essential-held-joystick-i00-standard` | standard | essential_held_joystick | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-essential-pen-regrasp-i00-privileged` | privileged | essential_pen_regrasp | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-pen-regrasp-i00-standard` | standard | essential_pen_regrasp | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-rotary-gait-i00-privileged` | privileged | essential_rotary_gait | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-rotary-gait-i00-standard` | standard | essential_rotary_gait | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-two-object-i00-privileged` | privileged | essential_two_object | 3600 s | full | yes | core | allowlist | static |
| `dexhand-essential-two-object-i00-standard` | standard | essential_two_object | 3600 s | full | yes | core | allowlist | static |
| `dexhand-fan-guard-install-i00-privileged` | privileged | fan_guard_install | 3600 s | full | yes | core | allowlist | static |
| `dexhand-fan-guard-install-i00-standard` | standard | fan_guard_install | 3600 s | full | yes | core | allowlist | static |
| `dexhand-grinder-crank-i00-privileged` | privileged | grinder_crank | 3600 s | full | yes | core | allowlist | static |
| `dexhand-grinder-crank-i00-standard` | standard | grinder_crank | 3600 s | full | yes | core | allowlist | static |
| `dexhand-jar-lid-open-i00-privileged` | privileged | jar_lid_open | 3600 s | full | yes | core | allowlist | static |
| `dexhand-jar-lid-open-i00-standard` | standard | jar_lid_open | 3600 s | full | yes | core | allowlist | static |
| `dexhand-pancake-serve-i00-privileged` | privileged | pancake_serve | 3600 s | full | yes | core | allowlist | static |
| `dexhand-pancake-serve-i00-standard` | standard | pancake_serve | 3600 s | full | yes | core | allowlist | static |
| `dexhand-paper-half-fold-i00-privileged` | privileged | paper_half_fold | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-paper-half-fold-i00-standard` | standard | paper_half_fold | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-paper-staple-i00-privileged` | privileged | paper_staple | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-paper-staple-i00-standard` | standard | paper_staple | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-picture-hang-i00-privileged` | privileged | picture_hang | 3600 s | full | yes | core | allowlist | static |
| `dexhand-picture-hang-i00-standard` | standard | picture_hang | 3600 s | full | yes | core | allowlist | static |
| `dexhand-pot-shelf-transfer-i00-privileged` | privileged | pot_shelf_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-pot-shelf-transfer-i00-standard` | standard | pot_shelf_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-ram-module-install-i00-privileged` | privileged | ram_module_install | 3600 s | full | yes | core | allowlist | static |
| `dexhand-ram-module-install-i00-standard` | standard | ram_module_install | 3600 s | full | yes | core | allowlist | static |
| `dexhand-remote-battery-swap-i00-privileged` | privileged | remote_battery_swap | 3600 s | full | yes | core | allowlist | static |
| `dexhand-remote-battery-swap-i00-standard` | standard | remote_battery_swap | 3600 s | full | yes | core | allowlist | static |
| `dexhand-stool-brace-insert-i00-privileged` | privileged | stool_brace_insert | 3600 s | full | yes | core | allowlist | static |
| `dexhand-stool-brace-insert-i00-standard` | standard | stool_brace_insert | 3600 s | full | yes | core | allowlist | static |
| `dexhand-sweep-dustpan-i00-privileged` | privileged | sweep_dustpan | 3600 s | full | yes | core | allowlist | static |
| `dexhand-sweep-dustpan-i00-standard` | standard | sweep_dustpan | 3600 s | full | yes | core | allowlist | static |
| `dexhand-tray-glass-carry-i00-privileged` | privileged | tray_glass_carry | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-tray-glass-carry-i00-standard` | standard | tray_glass_carry | 3600 s | full | yes | excluded | allowlist | static |
| `dexhand-usb-plug-insert-i00-privileged` | privileged | usb_plug_insert | 3600 s | full | yes | core | allowlist | static |
| `dexhand-usb-plug-insert-i00-standard` | standard | usb_plug_insert | 3600 s | full | yes | core | allowlist | static |
| `dexhand-vacuum-bin-reseat-i00-privileged` | privileged | vacuum_bin_reseat | 3600 s | full | yes | core | allowlist | static |
| `dexhand-vacuum-bin-reseat-i00-standard` | standard | vacuum_bin_reseat | 3600 s | full | yes | core | allowlist | static |

### DexJoCo

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `dexjoco-bimanual-assembly-i00-privileged` | privileged | bimanual_assembly | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-assembly-i00-standard` | standard | bimanual_assembly | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-hanoi-i00-privileged` | privileged | bimanual_hanoi | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-hanoi-i00-standard` | standard | bimanual_hanoi | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-microwave-cook-i00-privileged` | privileged | bimanual_microwave_cook | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-microwave-cook-i00-standard` | standard | bimanual_microwave_cook | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-photograph-i00-privileged` | privileged | bimanual_photograph | 3600 s | full | yes | core | allowlist | static |
| `dexjoco-bimanual-photograph-i00-standard` | standard | bimanual_photograph | 3600 s | full | yes | core | allowlist | static |
| `dexjoco-bimanual-unlock-ipad-i00-privileged` | privileged | bimanual_unlock_ipad | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-bimanual-unlock-ipad-i00-standard` | standard | bimanual_unlock_ipad | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-click-mouse-i00-privileged` | privileged | click_mouse | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-click-mouse-i00-standard` | standard | click_mouse | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-fold-glasses-i00-privileged` | privileged | fold_glasses | 3600 s | full | yes | core | allowlist | static |
| `dexjoco-fold-glasses-i00-standard` | standard | fold_glasses | 3600 s | full | yes | core | allowlist | static |
| `dexjoco-hammer-nail-i00-privileged` | privileged | hammer_nail | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-hammer-nail-i00-standard` | standard | hammer_nail | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-pick-bucket-i00-privileged` | privileged | pick_bucket | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-pick-bucket-i00-standard` | standard | pick_bucket | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-pinch-tongs-i00-privileged` | privileged | pinch_tongs | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-pinch-tongs-i00-standard` | standard | pinch_tongs | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-water-plant-i00-privileged` | privileged | water_plant | 3600 s | full | yes | excluded | allowlist | static |
| `dexjoco-water-plant-i00-standard` | standard | water_plant | 3600 s | full | yes | excluded | allowlist | static |

### DexToolBench

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `dextoolbench_brush_blue_brush_sweep_forward-privileged` | privileged | dextoolbench/brush/blue_brush/sweep_forward | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_brush_blue_brush_sweep_forward-standard` | standard | dextoolbench/brush/blue_brush/sweep_forward | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_brush_red_brush_sweep_forward-privileged` | privileged | dextoolbench/brush/red_brush/sweep_forward | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_brush_red_brush_sweep_forward-standard` | standard | dextoolbench/brush/red_brush/sweep_forward | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_brush_red_brush_sweep_right-privileged` | privileged | dextoolbench/brush/red_brush/sweep_right | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_brush_red_brush_sweep_right-standard` | standard | dextoolbench/brush/red_brush/sweep_right | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_eraser_handle_eraser_wipe_c-privileged` | privileged | dextoolbench/eraser/handle_eraser/wipe_c | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_eraser_handle_eraser_wipe_c-standard` | standard | dextoolbench/eraser/handle_eraser/wipe_c | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_eraser_handle_eraser_wipe_smile-privileged` | privileged | dextoolbench/eraser/handle_eraser/wipe_smile | 3600 s | full | yes | excluded | allowlist | static |
| `dextoolbench_eraser_handle_eraser_wipe_smile-standard` | standard | dextoolbench/eraser/handle_eraser/wipe_smile | 3600 s | full | yes | excluded | allowlist | static |
| `dextoolbench_hammer_claw_hammer_swing_down-privileged` | privileged | dextoolbench/hammer/claw_hammer/swing_down | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_hammer_claw_hammer_swing_down-standard` | standard | dextoolbench/hammer/claw_hammer/swing_down | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_hammer_claw_hammer_swing_side-privileged` | privileged | dextoolbench/hammer/claw_hammer/swing_side | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_hammer_claw_hammer_swing_side-standard` | standard | dextoolbench/hammer/claw_hammer/swing_side | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_hammer_mallet_hammer_swing_down-privileged` | privileged | dextoolbench/hammer/mallet_hammer/swing_down | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_hammer_mallet_hammer_swing_down-standard` | standard | dextoolbench/hammer/mallet_hammer/swing_down | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_hammer_mallet_hammer_swing_side-privileged` | privileged | dextoolbench/hammer/mallet_hammer/swing_side | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_hammer_mallet_hammer_swing_side-standard` | standard | dextoolbench/hammer/mallet_hammer/swing_side | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_marker_sharpie_marker_draw_smile-privileged` | privileged | dextoolbench/marker/sharpie_marker/draw_smile | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_marker_sharpie_marker_draw_smile-standard` | standard | dextoolbench/marker/sharpie_marker/draw_smile | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_marker_sharpie_marker_write_c-privileged` | privileged | dextoolbench/marker/sharpie_marker/write_c | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_marker_sharpie_marker_write_c-standard` | standard | dextoolbench/marker/sharpie_marker/write_c | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_marker_staples_marker_draw_smile-privileged` | privileged | dextoolbench/marker/staples_marker/draw_smile | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_marker_staples_marker_draw_smile-standard` | standard | dextoolbench/marker/staples_marker/draw_smile | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_marker_staples_marker_write_c-privileged` | privileged | dextoolbench/marker/staples_marker/write_c | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_marker_staples_marker_write_c-standard` | standard | dextoolbench/marker/staples_marker/write_c | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_screwdriver_long_screwdriver_spin_horizontal-privileged` | privileged | dextoolbench/screwdriver/long_screwdriver/spin_horizontal | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_screwdriver_long_screwdriver_spin_horizontal-standard` | standard | dextoolbench/screwdriver/long_screwdriver/spin_horizontal | 3600 s | full | yes | core | allowlist | static |
| `dextoolbench_screwdriver_long_screwdriver_spin_vertical-privileged` | privileged | dextoolbench/screwdriver/long_screwdriver/spin_vertical | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_screwdriver_long_screwdriver_spin_vertical-standard` | standard | dextoolbench/screwdriver/long_screwdriver/spin_vertical | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_screwdriver_short_screwdriver_spin_horizontal-privileged` | privileged | dextoolbench/screwdriver/short_screwdriver/spin_horizontal | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_screwdriver_short_screwdriver_spin_horizontal-standard` | standard | dextoolbench/screwdriver/short_screwdriver/spin_horizontal | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_screwdriver_short_screwdriver_spin_vertical-privileged` | privileged | dextoolbench/screwdriver/short_screwdriver/spin_vertical | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_screwdriver_short_screwdriver_spin_vertical-standard` | standard | dextoolbench/screwdriver/short_screwdriver/spin_vertical | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_flat_spatula_flip_over-privileged` | privileged | dextoolbench/spatula/flat_spatula/flip_over | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_flat_spatula_flip_over-standard` | standard | dextoolbench/spatula/flat_spatula/flip_over | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_flat_spatula_serve_plate-privileged` | privileged | dextoolbench/spatula/flat_spatula/serve_plate | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_flat_spatula_serve_plate-standard` | standard | dextoolbench/spatula/flat_spatula/serve_plate | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_spoon_spatula_flip_over-privileged` | privileged | dextoolbench/spatula/spoon_spatula/flip_over | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_spoon_spatula_flip_over-standard` | standard | dextoolbench/spatula/spoon_spatula/flip_over | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_spoon_spatula_serve_plate-privileged` | privileged | dextoolbench/spatula/spoon_spatula/serve_plate | 3600 s | partial | no | core | allowlist | static |
| `dextoolbench_spatula_spoon_spatula_serve_plate-standard` | standard | dextoolbench/spatula/spoon_spatula/serve_plate | 3600 s | partial | no | core | allowlist | static |

### Embodied Olympics - Fun

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `embodied-olympics-fun-backflip-i00-privileged` | privileged | backflip | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-backflip-i00-standard` | standard | backflip | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-badminton-serve-i00-privileged` | privileged | badminton_serve | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-badminton-serve-i00-standard` | standard | badminton_serve | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-balance-beam-i00-privileged` | privileged | balance_beam | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-balance-beam-i00-standard` | standard | balance_beam | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-balance-board-i00-privileged` | privileged | balance_board | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-balance-board-i00-standard` | standard | balance_board | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-basketball-dribble-i00-privileged` | privileged | basketball_dribble | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-basketball-dribble-i00-standard` | standard | basketball_dribble | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-basketball-dribble-realgrasp-i00-privileged` | privileged | basketball_dribble_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-basketball-dribble-realgrasp-i00-standard` | standard | basketball_dribble_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-bowling-i00-privileged` | privileged | bowling | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-bowling-i00-standard` | standard | bowling | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-bowling-realgrasp-i00-privileged` | privileged | bowling_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-bowling-realgrasp-i00-standard` | standard | bowling_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-box-jump-i00-privileged` | privileged | box_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-box-jump-i00-standard` | standard | box_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-boxing-i00-privileged` | privileged | boxing | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-boxing-i00-standard` | standard | boxing | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-catch-and-shoot-i00-privileged` | privileged | catch_and_shoot | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-and-shoot-i00-standard` | standard | catch_and_shoot | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-and-shoot-i00-standard-realtime` | standard-realtime | catch_and_shoot | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-and-shoot-realgrasp-i00-privileged` | privileged | catch_and_shoot_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-and-shoot-realgrasp-i00-standard` | standard | catch_and_shoot_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-and-shoot-realgrasp-i00-standard-realtime` | standard-realtime | catch_and_shoot_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-i00-privileged` | privileged | catch | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-catch-i00-standard` | standard | catch | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-catch-i00-standard-realtime` | standard-realtime | catch | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-catch-realgrasp-i00-privileged` | privileged | catch_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-realgrasp-i00-standard` | standard | catch_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-catch-realgrasp-i00-standard-realtime` | standard-realtime | catch_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-clean-and-jerk-i00-privileged` | privileged | clean_and_jerk | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-clean-and-jerk-i00-standard` | standard | clean_and_jerk | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-crawl-i00-privileged` | privileged | crawl | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-crawl-i00-standard` | standard | crawl | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-discus-i00-privileged` | privileged | discus | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-discus-i00-standard` | standard | discus | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-discus-realgrasp-i00-privileged` | privileged | discus_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-discus-realgrasp-i00-standard` | standard | discus_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-dribble-slalom-i00-privileged` | privileged | dribble_slalom | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-dribble-slalom-i00-standard` | standard | dribble_slalom | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-dunk-between-legs-i00-privileged` | privileged | dunk_between_legs | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-dunk-between-legs-i00-standard` | standard | dunk_between_legs | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-dunk-i00-privileged` | privileged | dunk | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-dunk-i00-standard` | standard | dunk | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-dunk-realgrasp-i00-privileged` | privileged | dunk_realgrasp | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-dunk-realgrasp-i00-standard` | standard | dunk_realgrasp | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-free-throw-i00-privileged` | privileged | free_throw | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-free-throw-i00-standard` | standard | free_throw | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-free-throw-realgrasp-i00-privileged` | privileged | free_throw_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-free-throw-realgrasp-i00-standard` | standard | free_throw_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-golf-putt-i00-privileged` | privileged | golf_putt | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-golf-putt-i00-standard` | standard | golf_putt | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-golf-putt-realgrasp-i00-privileged` | privileged | golf_putt_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-golf-putt-realgrasp-i00-standard` | standard | golf_putt_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-header-i00-privileged` | privileged | header | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-header-i00-standard` | standard | header | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-header-i00-standard-realtime` | standard-realtime | header | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-high-bar-swing-i00-privileged` | privileged | high_bar_swing | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-high-bar-swing-i00-standard` | standard | high_bar_swing | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-high-jump-i00-privileged` | privileged | high_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-high-jump-i00-standard` | standard | high_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-hurdles-freestanding-i00-privileged` | privileged | hurdles_freestanding | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-hurdles-freestanding-i00-standard` | standard | hurdles_freestanding | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-hurdles-i00-privileged` | privileged | hurdles | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-hurdles-i00-standard` | standard | hurdles | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-javelin-i00-privileged` | privileged | javelin | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-javelin-i00-standard` | standard | javelin | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-javelin-realgrasp-i00-privileged` | privileged | javelin_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-javelin-realgrasp-i00-standard` | standard | javelin_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-juggle-three-i00-privileged` | privileged | juggle_three | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-juggle-three-i00-standard` | standard | juggle_three | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-juggle-three-i00-standard-realtime` | standard-realtime | juggle_three | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-juggle-three-realgrasp-i00-privileged` | privileged | juggle_three_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-juggle-three-realgrasp-i00-standard` | standard | juggle_three_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-juggle-three-realgrasp-i00-standard-realtime` | standard-realtime | juggle_three_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-juggling-feet-i00-privileged` | privileged | juggling_feet | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-juggling-feet-i00-standard` | standard | juggling_feet | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-juggling-feet-realgrasp-i00-privileged` | privileged | juggling_feet_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-juggling-feet-realgrasp-i00-standard` | standard | juggling_feet_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-juggling-head-i00-privileged` | privileged | juggling_head | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-juggling-head-i00-standard` | standard | juggling_head | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-juggling-head-i00-standard-realtime` | standard-realtime | juggling_head | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-juggling-i00-privileged` | privileged | juggling | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-juggling-i00-standard` | standard | juggling | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-juggling-realgrasp-i00-privileged` | privileged | juggling_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-juggling-realgrasp-i00-standard` | standard | juggling_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-jump-rope-i00-privileged` | privileged | jump_rope | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-jump-rope-i00-standard` | standard | jump_rope | 7200 s | none | no | core | open | — |
| `embodied-olympics-fun-kick-target-i00-privileged` | privileged | kick_target | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-kick-target-i00-standard` | standard | kick_target | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-layup-i00-privileged` | privileged | layup | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-layup-i00-standard` | standard | layup | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-layup-realgrasp-i00-privileged` | privileged | layup_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-layup-realgrasp-i00-standard` | standard | layup_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-long-jump-i00-privileged` | privileged | long_jump | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-long-jump-i00-standard` | standard | long_jump | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-long-rope-i00-privileged` | privileged | long_rope | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-long-rope-i00-standard` | standard | long_rope | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-long-rope-i00-standard-realtime` | standard-realtime | long_rope | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-paddle-bounce-i00-privileged` | privileged | paddle_bounce | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-paddle-bounce-i00-standard` | standard | paddle_bounce | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-paddle-bounce-i00-standard-realtime` | standard-realtime | paddle_bounce | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-paddle-bounce-realgrasp-i00-privileged` | privileged | paddle_bounce_realgrasp | 7200 s | full | yes | core | open | dynamic |
| `embodied-olympics-fun-paddle-bounce-realgrasp-i00-standard` | standard | paddle_bounce_realgrasp | 7200 s | full | yes | core | open | dynamic |
| `embodied-olympics-fun-paddle-bounce-realgrasp-i00-standard-realtime` | standard-realtime | paddle_bounce_realgrasp | 7200 s | full | yes | core | open | dynamic |
| `embodied-olympics-fun-penalty-kick-i00-privileged` | privileged | penalty_kick | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-penalty-kick-i00-standard` | standard | penalty_kick | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-penalty-kick-i00-standard-realtime` | standard-realtime | penalty_kick | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-pitch-target-i00-privileged` | privileged | pitch_target | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-pitch-target-i00-standard` | standard | pitch_target | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-pitch-target-realgrasp-i00-privileged` | privileged | pitch_target_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-pitch-target-realgrasp-i00-standard` | standard | pitch_target_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-pole-vault-i00-privileged` | privileged | pole_vault | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-pole-vault-i00-standard` | standard | pole_vault | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-shot-put-i00-privileged` | privileged | shot_put | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-shot-put-i00-standard` | standard | shot_put | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-shot-put-realgrasp-i00-privileged` | privileged | shot_put_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-shot-put-realgrasp-i00-standard` | standard | shot_put_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-shuttle-run-i00-privileged` | privileged | shuttle_run | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-shuttle-run-i00-standard` | standard | shuttle_run | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-slalom-i00-privileged` | privileged | slalom | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-slalom-i00-standard` | standard | slalom | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-sprint-i00-privileged` | privileged | sprint | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-sprint-i00-standard` | standard | sprint | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-standing-long-jump-i00-privileged` | privileged | standing_long_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-standing-long-jump-i00-standard` | standard | standing_long_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-steeplechase-i00-privileged` | privileged | steeplechase | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-steeplechase-i00-standard` | standard | steeplechase | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-table-tennis-return-i00-privileged` | privileged | table_tennis_return | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-table-tennis-return-i00-standard` | standard | table_tennis_return | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-table-tennis-return-i00-standard-realtime` | standard-realtime | table_tennis_return | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-table-tennis-return-realgrasp-i00-privileged` | privileged | table_tennis_return_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-table-tennis-return-realgrasp-i00-standard` | standard | table_tennis_return_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-table-tennis-return-realgrasp-i00-standard-realtime` | standard-realtime | table_tennis_return_realgrasp | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-tennis-return-i00-privileged` | privileged | tennis_return | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-tennis-return-i00-standard` | standard | tennis_return | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-tennis-return-i00-standard-realtime` | standard-realtime | tennis_return | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-tennis-return-realgrasp-i00-privileged` | privileged | tennis_return_realgrasp | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-tennis-return-realgrasp-i00-standard` | standard | tennis_return_realgrasp | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-tennis-return-realgrasp-i00-standard-realtime` | standard-realtime | tennis_return_realgrasp | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-tennis-serve-i00-privileged` | privileged | tennis_serve | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-tennis-serve-i00-standard` | standard | tennis_serve | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-tennis-serve-realgrasp-i00-privileged` | privileged | tennis_serve_realgrasp | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-tennis-serve-realgrasp-i00-standard` | standard | tennis_serve_realgrasp | 7200 s | full | yes | core | open | — |
| `embodied-olympics-fun-toes-to-bar-i00-privileged` | privileged | toes_to_bar | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-toes-to-bar-i00-standard` | standard | toes_to_bar | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-toes-to-bar-realgrasp-i00-privileged` | privileged | toes_to_bar_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-toes-to-bar-realgrasp-i00-standard` | standard | toes_to_bar_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-trap-ball-i00-privileged` | privileged | trap_ball | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-trap-ball-i00-standard` | standard | trap_ball | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-trap-ball-i00-standard-realtime` | standard-realtime | trap_ball | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-triple-jump-i00-privileged` | privileged | triple_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-triple-jump-i00-standard` | standard | triple_jump | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-vault-i00-privileged` | privileged | vault | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-vault-i00-standard` | standard | vault | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-vertical-jump-i00-privileged` | privileged | vertical_jump | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-vertical-jump-i00-standard` | standard | vertical_jump | 7200 s | none | no | excluded | open | static |
| `embodied-olympics-fun-volley-shot-i00-privileged` | privileged | volley_shot | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-volley-shot-i00-standard` | standard | volley_shot | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-volley-shot-i00-standard-realtime` | standard-realtime | volley_shot | 7200 s | none | no | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-bump-i00-privileged` | privileged | volleyball_bump | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-bump-i00-standard` | standard | volleyball_bump | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-bump-i00-standard-realtime` | standard-realtime | volleyball_bump | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-serve-i00-privileged` | privileged | volleyball_serve | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-volleyball-serve-i00-standard` | standard | volleyball_serve | 7200 s | full | yes | excluded | open | static |
| `embodied-olympics-fun-volleyball-serve-realgrasp-i00-privileged` | privileged | volleyball_serve_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-volleyball-serve-realgrasp-i00-standard` | standard | volleyball_serve_realgrasp | 7200 s | full | yes | core | open | static |
| `embodied-olympics-fun-volleyball-set-i00-privileged` | privileged | volleyball_set | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-set-i00-standard` | standard | volleyball_set | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-set-i00-standard-realtime` | standard-realtime | volleyball_set | 7200 s | full | yes | excluded | open | dynamic |
| `embodied-olympics-fun-volleyball-spike-i00-privileged` | privileged | volleyball_spike | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-volleyball-spike-i00-standard` | standard | volleyball_spike | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-volleyball-spike-i00-standard-realtime` | standard-realtime | volleyball_spike | 7200 s | none | no | core | open | dynamic |
| `embodied-olympics-fun-wall-ball-i00-privileged` | privileged | wall_ball | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-wall-ball-i00-standard` | standard | wall_ball | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-wall-ball-realgrasp-i00-privileged` | privileged | wall_ball_realgrasp | 7200 s | none | no | core | open | static |
| `embodied-olympics-fun-wall-ball-realgrasp-i00-standard` | standard | wall_ball_realgrasp | 7200 s | none | no | core | open | static |

### Embodied Olympics - Match

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `embodied-olympics-match-badminton-duelrl-i01-standard-realtime` | standard-realtime | badminton_duel | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-badminton-match-i01-privileged` | privileged | badminton_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-badminton-match-i01-standard-realtime` | standard-realtime | badminton_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-badminton-match-i02-privileged` | privileged | badminton_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-badminton-match-i02-standard-realtime` | standard-realtime | badminton_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-badminton-match-i04-standard-realtime` | standard-realtime | badminton_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-badminton-matchlow-i01-standard-realtime` | standard-realtime | badminton_matchlow | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-fencing-bout-i01-standard` | standard | fencing_bout | 7200 s | full | yes | core | allowlist | dynamic |
| `embodied-olympics-match-fencing-bout-i02-standard` | standard | fencing_bout | 7200 s | full | yes | excluded | allowlist | dynamic |
| `embodied-olympics-match-foosball-match-i01-standard-realtime` | standard-realtime | foosball_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccer-jointcpu-i01-standard-realtime` | standard-realtime | soccer_jointmatch | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccer-jointgpu-i01-standard-realtime` | standard-realtime | soccer_jointmatch | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccer-match-i00-privileged` | privileged | soccer_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccer-match-i00-standard-realtime` | standard-realtime | soccer_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccerssl-match-i00-privileged` | privileged | soccer_ssl_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccerssl-match-i00-standard-realtime` | standard-realtime | soccer_ssl_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-soccerssl-match-i01-standard-realtime` | standard-realtime | soccer_ssl_match | 14400 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-duelrl-i01-standard-realtime` | standard-realtime | tabletennis_duel | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-match-i01-privileged` | privileged | tabletennis_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-match-i01-standard-realtime` | standard-realtime | tabletennis_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-match-i02-privileged` | privileged | tabletennis_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-match-i02-standard-realtime` | standard-realtime | tabletennis_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-match-i03-standard-realtime` | standard-realtime | tabletennis_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-match-i04-standard-realtime` | standard-realtime | tabletennis_match | 7200 s | partial | no | core | allowlist | dynamic |
| `embodied-olympics-match-tabletennis-matchlow-i01-standard-realtime` | standard-realtime | tabletennis_matchlow | 7200 s | partial | no | core | allowlist | dynamic |

### Embodied Safety Exam

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `ese-a01-i01-standard` | standard | a01 | 3600 s | full | yes | core | allowlist | static |
| `ese-a01-i02-standard` | standard | a01 | 3600 s | full | yes | core | allowlist | static |
| `ese-a01-i04-standard` | standard | a01 | 3600 s | full | yes | core | allowlist | static |
| `ese-a01-i08-standard` | standard | a01 | 3600 s | full | yes | core | allowlist | static |
| `ese-a01-i09-standard` | standard | a01 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-a02-i03-standard` | standard | a02 | 3600 s | full | yes | core | allowlist | static |
| `ese-a04-i00-standard` | standard | a04 | 3600 s | full | yes | core | allowlist | static |
| `ese-a04-i03-standard` | standard | a04 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-a06-i01-standard` | standard | a06 | 3600 s | full | yes | core | allowlist | static |
| `ese-a06-i03-standard` | standard | a06 | 3600 s | full | yes | core | allowlist | static |
| `ese-a07-i02-standard` | standard | a07 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-a08-i01-standard` | standard | a08 | 3600 s | full | yes | core | allowlist | static |
| `ese-a09-i05-standard` | standard | a09 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-a17-i00-standard` | standard | a17 | 3600 s | full | yes | core | allowlist | static |
| `ese-a17-i01-standard` | standard | a17 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-a26-i02-standard` | standard | a26 | 3600 s | full | yes | core | allowlist | static |
| `ese-a27-i06-standard` | standard | a27 | 3600 s | full | yes | core | allowlist | static |
| `ese-a28-i00-standard` | standard | a28 | 3600 s | full | yes | core | allowlist | static |
| `ese-a28-i01-standard` | standard | a28 | 3600 s | full | yes | core | allowlist | static |
| `ese-a28-i03-standard` | standard | a28 | 3600 s | full | yes | core | allowlist | static |
| `ese-a29-i00-standard` | standard | a29 | 3600 s | full | yes | core | allowlist | static |
| `ese-a29-i01-standard` | standard | a29 | 3600 s | full | yes | core | allowlist | static |
| `ese-a29-i03-standard` | standard | a29 | 3600 s | full | yes | core | allowlist | static |
| `ese-a30-i05-standard` | standard | a30 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-a33-i01-standard` | standard | a33 | 3600 s | full | yes | core | allowlist | static |
| `ese-a33-i04-standard` | standard | a33 | 3600 s | full | yes | core | allowlist | static |
| `ese-a34-i07-standard` | standard | a34 | 3600 s | full | yes | core | allowlist | static |
| `ese-a34-i09-standard` | standard | a34 | 3600 s | full | yes | core | allowlist | static |
| `ese-a34-i11-standard` | standard | a34 | 3600 s | full | yes | core | allowlist | static |
| `ese-b06-i00-standard` | standard | b06 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-b06-i01-standard` | standard | b06 | 3600 s | full | yes | core | allowlist | static |
| `ese-b06-i02-standard` | standard | b06 | 3600 s | full | yes | core | allowlist | static |
| `ese-b08-i01-standard` | standard | b08 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-b08-i02-standard` | standard | b08 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-b11-i00-standard` | standard | b11 | 3600 s | full | yes | core | allowlist | static |
| `ese-b11-i01-standard` | standard | b11 | 3600 s | full | yes | core | allowlist | static |
| `ese-b11-i03-standard` | standard | b11 | 3600 s | full | yes | core | allowlist | static |
| `ese-b12-i04-standard` | standard | b12 | 3600 s | full | yes | core | allowlist | static |
| `ese-b12-i06-standard` | standard | b12 | 3600 s | full | yes | core | allowlist | static |
| `ese-b12-i07-standard` | standard | b12 | 3600 s | full | yes | core | allowlist | static |
| `ese-c02-i00-standard` | standard | c02 | 3600 s | full | yes | core | allowlist | static |
| `ese-c02-i00-standard-realtime` | standard-realtime | c02 | 3600 s | full | yes | core | allowlist | static |
| `ese-c02-i01-standard` | standard | c02 | 3600 s | full | yes | core | allowlist | static |
| `ese-c02-i01-standard-realtime` | standard-realtime | c02 | 3600 s | full | yes | core | allowlist | static |
| `ese-c04-i00-standard-realtime` | standard-realtime | c04 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-c04-i01-standard` | standard | c04 | 3600 s | full | yes | core | allowlist | static |
| `ese-c04-i01-standard-realtime` | standard-realtime | c04 | 3600 s | full | yes | core | allowlist | static |
| `ese-c05-i01-standard` | standard | c05 | 3600 s | full | yes | core | allowlist | dynamic |
| `ese-c05-i01-standard-realtime` | standard-realtime | c05 | 3600 s | full | yes | core | allowlist | dynamic |
| `ese-c05-i02-standard` | standard | c05 | 3600 s | full | yes | core | allowlist | dynamic |
| `ese-c16-i00-standard` | standard | c16 | 3600 s | full | yes | core | allowlist | dynamic |
| `ese-c16-i01-standard` | standard | c16 | 3600 s | full | yes | excluded | allowlist | dynamic |
| `ese-d05-i04-standard` | standard | d05 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-d05-i07-standard` | standard | d05 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-d08-i01-standard` | standard | d08 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-d12-i02-standard` | standard | d12 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-d12-i04-standard` | standard | d12 | 3600 s | full | yes | core | allowlist | static |
| `ese-e06-i00-standard` | standard | e06 | 3600 s | full | yes | core | allowlist | static |
| `ese-e06-i03-standard` | standard | e06 | 3600 s | full | yes | core | allowlist | static |
| `ese-f01-i00-standard` | standard | f01 | 3600 s | full | yes | core | allowlist | static |
| `ese-f02-i00-standard` | standard | f02 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f02-i01-standard` | standard | f02 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f03-i00-standard` | standard | f03 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f03-i01-standard` | standard | f03 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f03-i02-standard` | standard | f03 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f04-i01-standard` | standard | f04 | 3600 s | full | yes | core | allowlist | static |
| `ese-f04-i02-standard` | standard | f04 | 3600 s | full | yes | core | allowlist | static |
| `ese-f05-i00-standard` | standard | f05 | 3600 s | full | yes | core | allowlist | static |
| `ese-f05-i01-standard` | standard | f05 | 3600 s | full | yes | core | allowlist | static |
| `ese-f06-i00-standard` | standard | f06 | 3600 s | full | yes | core | allowlist | static |
| `ese-f06-i01-standard` | standard | f06 | 3600 s | full | yes | core | allowlist | static |
| `ese-f07-i00-standard` | standard | f07 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f08-i00-standard` | standard | f08 | 3600 s | full | yes | core | allowlist | static |
| `ese-f09-i00-standard` | standard | f09 | 3600 s | full | yes | core | allowlist | static |
| `ese-f10-i00-standard` | standard | f10 | 3600 s | full | yes | excluded | allowlist | static |
| `ese-f11-i00-standard` | standard | f11 | 3600 s | full | yes | core | allowlist | static |

### HumanoidBench

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `humanoidbench-loco-balance-hard-i00-privileged` | privileged | balance_hard | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-loco-balance-hard-i00-standard` | standard | balance_hard | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-loco-balance-hard-i00-standard-realtime` | standard-realtime | balance_hard | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-loco-hurdle-i00-privileged` | privileged | hurdle | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-loco-hurdle-i00-standard` | standard | hurdle | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-loco-hurdle-i00-standard-realtime` | standard-realtime | hurdle | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-loco-sit-simple-i00-privileged` | privileged | sit_simple | 3600 s | full | yes | excluded | allowlist | static |
| `humanoidbench-loco-sit-simple-i00-standard` | standard | sit_simple | 3600 s | full | yes | excluded | allowlist | static |
| `humanoidbench-loco-sit-simple-i00-standard-realtime` | standard-realtime | sit_simple | 3600 s | full | yes | excluded | allowlist | static |
| `humanoidbench-loco-walk-i00-privileged` | privileged | walk | 3600 s | none | no | excluded | allowlist | static |
| `humanoidbench-loco-walk-i00-standard` | standard | walk | 3600 s | none | no | excluded | allowlist | static |
| `humanoidbench-loco-walk-i00-standard-realtime` | standard-realtime | walk | 3600 s | none | no | excluded | allowlist | static |
| `humanoidbench-manip-bookshelf-simple-i00-privileged` | privileged | bookshelf_simple | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-bookshelf-simple-i00-standard` | standard | bookshelf_simple | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-bookshelf-simple-i00-standard-realtime` | standard-realtime | bookshelf_simple | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-cube-i00-privileged` | privileged | cube | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-cube-i00-standard` | standard | cube | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-cube-i00-standard-realtime` | standard-realtime | cube | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-door-i00-privileged` | privileged | door | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-door-i00-standard` | standard | door | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-door-i00-standard-realtime` | standard-realtime | door | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-powerlift-i00-privileged` | privileged | powerlift | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-powerlift-i00-standard` | standard | powerlift | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-powerlift-i00-standard-realtime` | standard-realtime | powerlift | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-room-i00-privileged` | privileged | room | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-room-i00-standard` | standard | room | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-room-i00-standard-realtime` | standard-realtime | room | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-window-i00-privileged` | privileged | window | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-window-i00-standard` | standard | window | 3600 s | none | no | core | allowlist | static |
| `humanoidbench-manip-window-i00-standard-realtime` | standard-realtime | window | 3600 s | none | no | core | allowlist | static |

### iSpatialGym

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `ispatialgym-alignment-axial-i00-privileged` | privileged | alignment_axial | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-alignment-axial-i00-standard` | standard | alignment_axial | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-alignment-vertical-i00-privileged` | privileged | alignment_vertical | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-alignment-vertical-i00-standard` | standard | alignment_vertical | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-camera-relocalization-obstructed-i00-privileged` | privileged | camera_relocalization_obstructed | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-camera-relocalization-obstructed-i00-standard` | standard | camera_relocalization_obstructed | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-configuration-matching-articulation-open-small-scale-i00-privileged` | privileged | configuration_matching_articulation_open_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-configuration-matching-articulation-open-small-scale-i00-standard` | standard | configuration_matching_articulation_open_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-configuration-matching-block-design-i00-privileged` | privileged | configuration_matching_block_design | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-configuration-matching-block-design-i00-standard` | standard | configuration_matching_block_design | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-inside-small-scale-i00-privileged` | privileged | inter_object_relation_satisfaction_inside_small_scale | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-inside-small-scale-i00-standard` | standard | inter_object_relation_satisfaction_inside_small_scale | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-nextto-small-scale-i00-privileged` | privileged | inter_object_relation_satisfaction_nextto_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-nextto-small-scale-i00-standard` | standard | inter_object_relation_satisfaction_nextto_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-ontop-small-scale-i00-privileged` | privileged | inter_object_relation_satisfaction_ontop_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-ontop-small-scale-i00-standard` | standard | inter_object_relation_satisfaction_ontop_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-touching-small-scale-i00-privileged` | privileged | inter_object_relation_satisfaction_touching_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-touching-small-scale-i00-standard` | standard | inter_object_relation_satisfaction_touching_small_scale | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-under-small-scale-i00-privileged` | privileged | inter_object_relation_satisfaction_under_small_scale | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-inter-object-relation-satisfaction-under-small-scale-i00-standard` | standard | inter_object_relation_satisfaction_under_small_scale | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-mental-rotation-i00-privileged` | privileged | mental_rotation | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-mental-rotation-i00-standard` | standard | mental_rotation | 3600 s | none | no | core | allowlist | static |
| `ispatialgym-object-scaling-i00-privileged` | privileged | object_scaling | 3600 s | none | no | excluded | allowlist | static |
| `ispatialgym-object-scaling-i00-standard` | standard | object_scaling | 3600 s | none | no | excluded | allowlist | static |

### KinDER

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `kinder-constrained-cupboard-i00-privileged` | privileged | constrained-cupboard | 1800 s | none | no | core | allowlist | static |
| `kinder-constrained-cupboard-i00-standard` | standard | constrained-cupboard | 1800 s | none | no | core | allowlist | static |
| `kinder-dynamo-i00-privileged` | privileged | dynamo | 1800 s | full | yes | excluded | allowlist | static |
| `kinder-dynamo-i00-standard` | standard | dynamo | 1800 s | full | yes | excluded | allowlist | static |
| `kinder-scoop-pour-i01-privileged` | privileged | scoop-pour | 1800 s | none | no | core | allowlist | static |
| `kinder-scoop-pour-i01-standard` | standard | scoop-pour | 1800 s | none | no | core | allowlist | static |
| `kinder-sweep-into-drawer-i00-privileged` | privileged | sweep-into-drawer | 1800 s | none | no | core | allowlist | static |
| `kinder-sweep-into-drawer-i00-standard` | standard | sweep-into-drawer | 1800 s | none | no | core | allowlist | static |
| `kinder-sweep-simple-i01-privileged` | privileged | sweep-simple | 1800 s | none | no | core | allowlist | static |
| `kinder-sweep-simple-i01-standard` | standard | sweep-simple | 1800 s | none | no | core | allowlist | static |

### LabUtopia

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `labutopia-heat-liquid-i00-privileged` | privileged | heat_liquid | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-heat-liquid-i00-standard` | standard | heat_liquid | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-open-close-i00-privileged` | privileged | open_close | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-open-close-i00-standard` | standard | open_close | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-open-door-i00-privileged` | privileged | open_door | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-open-door-i00-standard` | standard | open_door | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-open-drawer-i00-privileged` | privileged | open_drawer | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-open-drawer-i00-standard` | standard | open_drawer | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-pick-i00-privileged` | privileged | pick | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-pick-i00-standard` | standard | pick | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-place-i00-privileged` | privileged | place | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-place-i00-standard` | standard | place | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-pour-i00-privileged` | privileged | pour | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-pour-i00-standard` | standard | pour | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-press-i00-privileged` | privileged | press | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-press-i00-standard` | standard | press | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-shake-i00-privileged` | privileged | shake | 3600 s | full | yes | excluded | allowlist | static |
| `labutopia-shake-i00-standard` | standard | shake | 3600 s | full | yes | excluded | allowlist | static |

### LIBERO-MAX

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `libero-max-goal-akita-black-bowl-in-wooden-cabinet-top-target-relocation-i00-privileged` | privileged | libero-max/libero_goal/target_relocation | 1800 s | full | yes | core | allowlist | static |
| `libero-max-goal-akita-black-bowl-in-wooden-cabinet-top-target-relocation-i00-standard` | standard | libero-max/libero_goal/target_relocation | 1800 s | full | yes | core | allowlist | static |
| `libero-max-goal-akita-black-bowl-on-flat-stove-cook-target-relocation-i00-privileged` | privileged | libero-max/libero_goal/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-akita-black-bowl-on-flat-stove-cook-target-relocation-i00-standard` | standard | libero-max/libero_goal/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-akita-black-bowl-on-plate-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_goal/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-akita-black-bowl-on-plate-receptacle-relocation-i00-standard` | standard | libero-max/libero_goal/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-akita-black-bowl-on-wooden-cabinet-top-obstacle-insertion-i00-privileged` | privileged | libero-max/libero_goal/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-akita-black-bowl-on-wooden-cabinet-top-obstacle-insertion-i00-standard` | standard | libero-max/libero_goal/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-cream-cheese-on-akita-black-bowl-obstacle-insertion-i00-privileged` | privileged | libero-max/libero_goal/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-cream-cheese-on-akita-black-bowl-obstacle-insertion-i00-standard` | standard | libero-max/libero_goal/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-off-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_goal/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-off-visual-theme-switch-i00-standard` | standard | libero-max/libero_goal/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-on-illumination-switch-i00-privileged` | privileged | libero-max/libero_goal/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-on-illumination-switch-i00-standard` | standard | libero-max/libero_goal/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-on-illumination-switch-i01-privileged` | privileged | libero-max/libero_goal/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-on-illumination-switch-i01-standard` | standard | libero-max/libero_goal/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-on-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_goal/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-flat-stove-on-sensor-noise-onset-i00-standard` | standard | libero-max/libero_goal/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-plate-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_goal/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-plate-receptacle-relocation-i00-standard` | standard | libero-max/libero_goal/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-wine-rack-top-camera-shift-i00-privileged` | privileged | libero-max/libero_goal/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-wine-rack-top-camera-shift-i00-standard` | standard | libero-max/libero_goal/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-wine-rack-top-obstacle-insertion-i00-privileged` | privileged | libero-max/libero_goal/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-wine-rack-top-obstacle-insertion-i00-standard` | standard | libero-max/libero_goal/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-wine-rack-top-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_goal/visual_theme_switch | 1800 s | full | yes | core | allowlist | static |
| `libero-max-goal-wine-bottle-on-wine-rack-top-visual-theme-switch-i00-standard` | standard | libero-max/libero_goal/visual_theme_switch | 1800 s | full | yes | core | allowlist | static |
| `libero-max-goal-wine-bottle-on-wooden-cabinet-top-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_goal/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-wine-bottle-on-wooden-cabinet-top-sensor-noise-onset-i00-standard` | standard | libero-max/libero_goal/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-yellow-stove-on-camera-shift-i00-privileged` | privileged | libero-max/libero_goal/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-goal-yellow-stove-on-camera-shift-i00-standard` | standard | libero-max/libero_goal/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-cream-cheese-in-basket-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_10/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-cream-cheese-in-basket-receptacle-relocation-i00-standard` | standard | libero-max/libero_10/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-cream-cheese-in-basket-target-relocation-i00-privileged` | privileged | libero-max/libero_10/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-cream-cheese-in-basket-target-relocation-i00-standard` | standard | libero-max/libero_10/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_10/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-distractor-burst-i00-standard` | standard | libero-max/libero_10/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_10/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-receptacle-relocation-i00-standard` | standard | libero-max/libero_10/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_10/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-sensor-noise-onset-i00-standard` | standard | libero-max/libero_10/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i00-privileged` | privileged | libero-max/libero_10/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i00-standard` | standard | libero-max/libero_10/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i01-privileged` | privileged | libero-max/libero_10/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i01-standard` | standard | libero-max/libero_10/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-camera-shift-i00-privileged` | privileged | libero-max/libero_10/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-camera-shift-i00-standard` | standard | libero-max/libero_10/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-illumination-switch-i00-privileged` | privileged | libero-max/libero_10/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-illumination-switch-i00-standard` | standard | libero-max/libero_10/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_10/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-visual-theme-switch-i00-standard` | standard | libero-max/libero_10/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-visual-theme-switch-i01-privileged` | privileged | libero-max/libero_10/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-visual-theme-switch-i01-standard` | standard | libero-max/libero_10/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-white-yellow-mug-and-green-chocolate-pudding-on-yellow-plate-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_10/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-white-yellow-mug-and-green-chocolate-pudding-on-yellow-plate-sensor-noise-onset-i00-standard` | standard | libero-max/libero_10/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-white-yellow-mug-in-desk-caddy-back-camera-shift-i00-privileged` | privileged | libero-max/libero_10/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-white-yellow-mug-in-desk-caddy-back-camera-shift-i00-standard` | standard | libero-max/libero_10/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-white-yellow-mug-in-desk-caddy-back-illumination-switch-i00-privileged` | privileged | libero-max/libero_10/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-long-white-yellow-mug-in-desk-caddy-back-illumination-switch-i00-standard` | standard | libero-max/libero_10/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-alphabet-soup-in-basket-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_object/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-alphabet-soup-in-basket-receptacle-relocation-i00-standard` | standard | libero-max/libero_object/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-alphabet-soup-in-basket-target-relocation-i00-privileged` | privileged | libero-max/libero_object/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-alphabet-soup-in-basket-target-relocation-i00-standard` | standard | libero-max/libero_object/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-alphabet-soup-in-basket-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_object/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-alphabet-soup-in-basket-visual-theme-switch-i00-standard` | standard | libero-max/libero_object/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-butter-in-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-butter-in-basket-distractor-burst-i00-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-butter-in-basket-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_object/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-butter-in-basket-receptacle-relocation-i00-standard` | standard | libero-max/libero_object/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i00-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i01-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i01-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-chocolate-pudding-in-basket-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_object/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-chocolate-pudding-in-basket-sensor-noise-onset-i00-standard` | standard | libero-max/libero_object/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-cream-cheese-in-basket-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_object/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-cream-cheese-in-basket-visual-theme-switch-i00-standard` | standard | libero-max/libero_object/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-green-bbq-sauce-in-red-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-green-bbq-sauce-in-red-basket-distractor-burst-i00-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-green-chocolate-pudding-in-red-basket-camera-shift-i00-privileged` | privileged | libero-max/libero_object/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-green-chocolate-pudding-in-red-basket-camera-shift-i00-standard` | standard | libero-max/libero_object/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-ketchup-in-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-ketchup-in-basket-distractor-burst-i00-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-camera-shift-i00-privileged` | privileged | libero-max/libero_object/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-camera-shift-i00-standard` | standard | libero-max/libero_object/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-distractor-burst-i00-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-illumination-switch-i00-privileged` | privileged | libero-max/libero_object/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-illumination-switch-i00-standard` | standard | libero-max/libero_object/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-target-relocation-i00-privileged` | privileged | libero-max/libero_object/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-milk-in-basket-target-relocation-i00-standard` | standard | libero-max/libero_object/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-orange-juice-in-basket-distractor-burst-i00-privileged` | privileged | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-orange-juice-in-basket-distractor-burst-i00-standard` | standard | libero-max/libero_object/distractor_burst | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-orange-juice-in-basket-illumination-switch-i00-privileged` | privileged | libero-max/libero_object/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-orange-juice-in-basket-illumination-switch-i00-standard` | standard | libero-max/libero_object/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-salad-dressing-in-basket-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_object/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-object-salad-dressing-in-basket-sensor-noise-onset-i00-standard` | standard | libero-max/libero_object/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i00-privileged` | privileged | libero-max/libero_spatial/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i00-standard` | standard | libero-max/libero_spatial/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-privileged` | privileged | libero-max/libero_spatial/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01-standard` | standard | libero-max/libero_spatial/camera_shift | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-illumination-switch-i00-privileged` | privileged | libero-max/libero_spatial/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-illumination-switch-i00-standard` | standard | libero-max/libero_spatial/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-illumination-switch-i01-privileged` | privileged | libero-max/libero_spatial/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-illumination-switch-i01-standard` | standard | libero-max/libero_spatial/illumination_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-obstacle-insertion-i00-privileged` | privileged | libero-max/libero_spatial/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-obstacle-insertion-i00-standard` | standard | libero-max/libero_spatial/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-obstacle-insertion-i01-privileged` | privileged | libero-max/libero_spatial/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-obstacle-insertion-i01-standard` | standard | libero-max/libero_spatial/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i00-privileged` | privileged | libero-max/libero_spatial/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i00-standard` | standard | libero-max/libero_spatial/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i01-privileged` | privileged | libero-max/libero_spatial/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i01-standard` | standard | libero-max/libero_spatial/receptacle_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-sensor-noise-onset-i00-privileged` | privileged | libero-max/libero_spatial/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-sensor-noise-onset-i00-standard` | standard | libero-max/libero_spatial/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-sensor-noise-onset-i01-privileged` | privileged | libero-max/libero_spatial/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-sensor-noise-onset-i01-standard` | standard | libero-max/libero_spatial/sensor_noise_onset | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-target-relocation-i00-privileged` | privileged | libero-max/libero_spatial/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-target-relocation-i00-standard` | standard | libero-max/libero_spatial/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-target-relocation-i01-privileged` | privileged | libero-max/libero_spatial/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-target-relocation-i01-standard` | standard | libero-max/libero_spatial/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_spatial/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-akita-black-bowl-on-plate-visual-theme-switch-i00-standard` | standard | libero-max/libero_spatial/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-black-bowl-on-yellow-plate-obstacle-insertion-i00-privileged` | privileged | libero-max/libero_spatial/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-black-bowl-on-yellow-plate-obstacle-insertion-i00-standard` | standard | libero-max/libero_spatial/obstacle_insertion | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-black-bowl-on-yellow-plate-target-relocation-i00-privileged` | privileged | libero-max/libero_spatial/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-black-bowl-on-yellow-plate-target-relocation-i00-standard` | standard | libero-max/libero_spatial/target_relocation | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-black-bowl-on-yellow-plate-visual-theme-switch-i00-privileged` | privileged | libero-max/libero_spatial/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |
| `libero-max-spatial-black-bowl-on-yellow-plate-visual-theme-switch-i00-standard` | standard | libero-max/libero_spatial/visual_theme_switch | 1800 s | full | yes | excluded | allowlist | static |

### ManiGuard

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `maniguard-cabinet-pickup-i19-privileged` | privileged | cabinet_pickup | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-cabinet-pickup-i19-standard` | standard | cabinet_pickup | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-cabinet-pickup-i20-privileged` | privileged | cabinet_pickup | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-cabinet-pickup-i20-standard` | standard | cabinet_pickup | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-cabinet-pickup-i22-privileged` | privileged | cabinet_pickup | 3600 s | full | yes | core | allowlist | static |
| `maniguard-cabinet-pickup-i22-standard` | standard | cabinet_pickup | 3600 s | full | yes | core | allowlist | static |
| `maniguard-cabinet-pickup-i26-privileged` | privileged | cabinet_pickup | 3600 s | none | no | core | allowlist | static |
| `maniguard-cabinet-pickup-i26-standard` | standard | cabinet_pickup | 3600 s | none | no | core | allowlist | static |
| `maniguard-cabinet-pickup-i29-privileged` | privileged | cabinet_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-cabinet-pickup-i29-standard` | standard | cabinet_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i09-privileged` | privileged | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i09-standard` | standard | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i15-privileged` | privileged | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i15-standard` | standard | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i23-privileged` | privileged | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i23-standard` | standard | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i25-privileged` | privileged | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i25-standard` | standard | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i28-privileged` | privileged | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-clutter-pickup-i28-standard` | standard | clutter_pickup | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-dusty-transfer-i03-privileged` | privileged | dusty_transfer | 3600 s | full | yes | core | allowlist | static |
| `maniguard-dusty-transfer-i03-standard` | standard | dusty_transfer | 3600 s | full | yes | core | allowlist | static |
| `maniguard-dusty-transfer-i16-privileged` | privileged | dusty_transfer | 3600 s | none | no | core | allowlist | static |
| `maniguard-dusty-transfer-i16-standard` | standard | dusty_transfer | 3600 s | none | no | core | allowlist | static |
| `maniguard-dusty-transfer-i20-privileged` | privileged | dusty_transfer | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-dusty-transfer-i20-standard` | standard | dusty_transfer | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-dusty-transfer-i24-privileged` | privileged | dusty_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-dusty-transfer-i24-standard` | standard | dusty_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-dusty-transfer-i25-privileged` | privileged | dusty_transfer | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-dusty-transfer-i25-standard` | standard | dusty_transfer | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-jar-transport-i02-privileged` | privileged | jar_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-jar-transport-i02-standard` | standard | jar_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-jar-transport-i09-privileged` | privileged | jar_transport | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-jar-transport-i09-standard` | standard | jar_transport | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-jar-transport-i13-privileged` | privileged | jar_transport | 3600 s | full | yes | core | allowlist | static |
| `maniguard-jar-transport-i13-standard` | standard | jar_transport | 3600 s | full | yes | core | allowlist | static |
| `maniguard-jar-transport-i14-privileged` | privileged | jar_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-jar-transport-i14-standard` | standard | jar_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-jar-transport-i25-privileged` | privileged | jar_transport | 3600 s | none | no | core | allowlist | static |
| `maniguard-jar-transport-i25-standard` | standard | jar_transport | 3600 s | none | no | core | allowlist | static |
| `maniguard-lid-transport-i06-privileged` | privileged | lid_transport | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-lid-transport-i06-standard` | standard | lid_transport | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-lid-transport-i07-privileged` | privileged | lid_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-lid-transport-i07-standard` | standard | lid_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-lid-transport-i12-privileged` | privileged | lid_transport | 3600 s | full | yes | core | allowlist | static |
| `maniguard-lid-transport-i12-standard` | standard | lid_transport | 3600 s | full | yes | core | allowlist | static |
| `maniguard-lid-transport-i15-privileged` | privileged | lid_transport | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-lid-transport-i15-standard` | standard | lid_transport | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-lid-transport-i16-privileged` | privileged | lid_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-lid-transport-i16-standard` | standard | lid_transport | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-stack-retrieve-i08-privileged` | privileged | stack_retrieve | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-stack-retrieve-i08-standard` | standard | stack_retrieve | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-stack-retrieve-i10-privileged` | privileged | stack_retrieve | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-stack-retrieve-i10-standard` | standard | stack_retrieve | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-stack-retrieve-i12-privileged` | privileged | stack_retrieve | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-stack-retrieve-i12-standard` | standard | stack_retrieve | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-stack-retrieve-i13-privileged` | privileged | stack_retrieve | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-stack-retrieve-i13-standard` | standard | stack_retrieve | 3600 s | none | no | excluded | allowlist | static |
| `maniguard-stack-retrieve-i21-privileged` | privileged | stack_retrieve | 3600 s | full | yes | excluded | allowlist | static |
| `maniguard-stack-retrieve-i21-standard` | standard | stack_retrieve | 3600 s | full | yes | excluded | allowlist | static |

### MetaWorld+

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `metaworldplus-assembly-i00-privileged` | privileged | metaworld/assembly | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-assembly-i00-standard` | standard | metaworld/assembly | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-basketball-i00-privileged` | privileged | metaworld/basketball | 1800 s | full | yes | core | allowlist | static |
| `metaworldplus-basketball-i00-standard` | standard | metaworld/basketball | 1800 s | full | yes | core | allowlist | static |
| `metaworldplus-bin-picking-i00-privileged` | privileged | metaworld/bin-picking | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-bin-picking-i00-standard` | standard | metaworld/bin-picking | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-box-close-i00-privileged` | privileged | metaworld/box-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-box-close-i00-standard` | standard | metaworld/box-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-button-press-i00-privileged` | privileged | metaworld/button-press | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-button-press-i00-standard` | standard | metaworld/button-press | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-button-press-topdown-i00-privileged` | privileged | metaworld/button-press-topdown | 1800 s | full | yes | core | allowlist | static |
| `metaworldplus-button-press-topdown-i00-standard` | standard | metaworld/button-press-topdown | 1800 s | full | yes | core | allowlist | static |
| `metaworldplus-button-press-topdown-wall-i00-privileged` | privileged | metaworld/button-press-topdown-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-button-press-topdown-wall-i00-standard` | standard | metaworld/button-press-topdown-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-button-press-wall-i00-privileged` | privileged | metaworld/button-press-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-button-press-wall-i00-standard` | standard | metaworld/button-press-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-coffee-button-i00-privileged` | privileged | metaworld/coffee-button | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-coffee-button-i00-standard` | standard | metaworld/coffee-button | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-coffee-pull-i00-privileged` | privileged | metaworld/coffee-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-coffee-pull-i00-standard` | standard | metaworld/coffee-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-coffee-push-i00-privileged` | privileged | metaworld/coffee-push | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-coffee-push-i00-standard` | standard | metaworld/coffee-push | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-dial-turn-i00-privileged` | privileged | metaworld/dial-turn | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-dial-turn-i00-standard` | standard | metaworld/dial-turn | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-disassemble-i00-privileged` | privileged | metaworld/disassemble | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-disassemble-i00-standard` | standard | metaworld/disassemble | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-close-i00-privileged` | privileged | metaworld/door-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-close-i00-standard` | standard | metaworld/door-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-lock-i00-privileged` | privileged | metaworld/door-lock | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-lock-i00-standard` | standard | metaworld/door-lock | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-open-i00-privileged` | privileged | metaworld/door-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-open-i00-standard` | standard | metaworld/door-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-unlock-i00-privileged` | privileged | metaworld/door-unlock | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-door-unlock-i00-standard` | standard | metaworld/door-unlock | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-drawer-close-i00-privileged` | privileged | metaworld/drawer-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-drawer-close-i00-standard` | standard | metaworld/drawer-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-drawer-open-i00-privileged` | privileged | metaworld/drawer-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-drawer-open-i00-standard` | standard | metaworld/drawer-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-faucet-close-i00-privileged` | privileged | metaworld/faucet-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-faucet-close-i00-standard` | standard | metaworld/faucet-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-faucet-open-i00-privileged` | privileged | metaworld/faucet-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-faucet-open-i00-standard` | standard | metaworld/faucet-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-hammer-i00-privileged` | privileged | metaworld/hammer | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-hammer-i00-standard` | standard | metaworld/hammer | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-hand-insert-i00-privileged` | privileged | metaworld/hand-insert | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-hand-insert-i00-standard` | standard | metaworld/hand-insert | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-press-i00-privileged` | privileged | metaworld/handle-press | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-press-i00-standard` | standard | metaworld/handle-press | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-press-side-i00-privileged` | privileged | metaworld/handle-press-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-press-side-i00-standard` | standard | metaworld/handle-press-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-pull-i00-privileged` | privileged | metaworld/handle-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-pull-i00-standard` | standard | metaworld/handle-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-pull-side-i00-privileged` | privileged | metaworld/handle-pull-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-handle-pull-side-i00-standard` | standard | metaworld/handle-pull-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-lever-pull-i00-privileged` | privileged | metaworld/lever-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-lever-pull-i00-standard` | standard | metaworld/lever-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-peg-insert-side-i00-privileged` | privileged | metaworld/peg-insert-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-peg-insert-side-i00-standard` | standard | metaworld/peg-insert-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-peg-unplug-side-i00-privileged` | privileged | metaworld/peg-unplug-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-peg-unplug-side-i00-standard` | standard | metaworld/peg-unplug-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-pick-out-of-hole-i00-privileged` | privileged | metaworld/pick-out-of-hole | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-pick-out-of-hole-i00-standard` | standard | metaworld/pick-out-of-hole | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-pick-place-i00-privileged` | privileged | metaworld/pick-place | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-pick-place-i00-standard` | standard | metaworld/pick-place | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-pick-place-wall-i00-privileged` | privileged | metaworld/pick-place-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-pick-place-wall-i00-standard` | standard | metaworld/pick-place-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-back-i00-privileged` | privileged | metaworld/plate-slide-back | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-back-i00-standard` | standard | metaworld/plate-slide-back | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-back-side-i00-privileged` | privileged | metaworld/plate-slide-back-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-back-side-i00-standard` | standard | metaworld/plate-slide-back-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-i00-privileged` | privileged | metaworld/plate-slide | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-i00-standard` | standard | metaworld/plate-slide | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-side-i00-privileged` | privileged | metaworld/plate-slide-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-plate-slide-side-i00-standard` | standard | metaworld/plate-slide-side | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-push-back-i00-privileged` | privileged | metaworld/push-back | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-push-back-i00-standard` | standard | metaworld/push-back | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-push-i00-privileged` | privileged | metaworld/push | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-push-i00-standard` | standard | metaworld/push | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-push-wall-i00-privileged` | privileged | metaworld/push-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-push-wall-i00-standard` | standard | metaworld/push-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-reach-i00-privileged` | privileged | metaworld/reach | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-reach-i00-standard` | standard | metaworld/reach | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-reach-wall-i00-privileged` | privileged | metaworld/reach-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-reach-wall-i00-standard` | standard | metaworld/reach-wall | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-shelf-place-i00-privileged` | privileged | metaworld/shelf-place | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-shelf-place-i00-standard` | standard | metaworld/shelf-place | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-soccer-i00-privileged` | privileged | metaworld/soccer | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-soccer-i00-standard` | standard | metaworld/soccer | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-stick-pull-i00-privileged` | privileged | metaworld/stick-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-stick-pull-i00-standard` | standard | metaworld/stick-pull | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-stick-push-i00-privileged` | privileged | metaworld/stick-push | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-stick-push-i00-standard` | standard | metaworld/stick-push | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-sweep-i00-privileged` | privileged | metaworld/sweep | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-sweep-i00-standard` | standard | metaworld/sweep | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-sweep-into-i00-privileged` | privileged | metaworld/sweep-into | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-sweep-into-i00-standard` | standard | metaworld/sweep-into | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-window-close-i00-privileged` | privileged | metaworld/window-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-window-close-i00-standard` | standard | metaworld/window-close | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-window-open-i00-privileged` | privileged | metaworld/window-open | 1800 s | full | yes | excluded | allowlist | static |
| `metaworldplus-window-open-i00-standard` | standard | metaworld/window-open | 1800 s | full | yes | excluded | allowlist | static |

### MolmoSpaces

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `molmospaces-close-i00-privileged` | privileged | close | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-close-i00-standard` | standard | close | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-navigate-to-i00-privileged` | privileged | navigate-to | 3600 s | none | no | core | allowlist | static |
| `molmospaces-navigate-to-i00-standard` | standard | navigate-to | 3600 s | none | no | core | allowlist | static |
| `molmospaces-open-door-i00-privileged` | privileged | open-door | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-open-door-i00-standard` | standard | open-door | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-open-i00-privileged` | privileged | open | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-open-i00-standard` | standard | open | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-and-place-color-i00-privileged` | privileged | pick-and-place-color | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-and-place-color-i00-standard` | standard | pick-and-place-color | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-and-place-i00-privileged` | privileged | pick-and-place | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-and-place-i00-standard` | standard | pick-and-place | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-and-place-next-to-i00-privileged` | privileged | pick-and-place-next-to | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-and-place-next-to-i00-standard` | standard | pick-and-place-next-to | 3600 s | none | no | excluded | allowlist | static |
| `molmospaces-pick-i00-privileged` | privileged | pick | 3600 s | none | no | core | allowlist | static |
| `molmospaces-pick-i00-standard` | standard | pick | 3600 s | none | no | core | allowlist | static |

### MuJoCo Playground

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `mujoco_playground_aloha_hand_over-privileged` | privileged | mujoco_playground/AlohaHandOver | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_aloha_hand_over-standard` | standard | mujoco_playground/AlohaHandOver | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_aloha_single_peg_insertion-privileged` | privileged | mujoco_playground/AlohaSinglePegInsertion | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_aloha_single_peg_insertion-standard` | standard | mujoco_playground/AlohaSinglePegInsertion | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_barkour_joystick-privileged` | privileged | mujoco_playground/BarkourJoystick | 1800 s | full | yes | core | allowlist | dynamic |
| `mujoco_playground_barkour_joystick-standard` | standard | mujoco_playground/BarkourJoystick | 1800 s | full | yes | core | allowlist | dynamic |
| `mujoco_playground_barkour_joystick-standard-realtime` | standard-realtime | mujoco_playground/BarkourJoystick | 1800 s | full | yes | core | allowlist | dynamic |
| `mujoco_playground_go1_footstand-privileged` | privileged | mujoco_playground/Go1Footstand | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_go1_footstand-standard` | standard | mujoco_playground/Go1Footstand | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_go1_getup-privileged` | privileged | mujoco_playground/Go1Getup | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_go1_getup-standard` | standard | mujoco_playground/Go1Getup | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_go1_handstand-privileged` | privileged | mujoco_playground/Go1Handstand | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_go1_handstand-standard` | standard | mujoco_playground/Go1Handstand | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_go1_joystick_flat_terrain-privileged` | privileged | mujoco_playground/Go1JoystickFlatTerrain | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_go1_joystick_flat_terrain-standard` | standard | mujoco_playground/Go1JoystickFlatTerrain | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_go1_joystick_rough_terrain-privileged` | privileged | mujoco_playground/Go1JoystickRoughTerrain | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_go1_joystick_rough_terrain-standard` | standard | mujoco_playground/Go1JoystickRoughTerrain | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_panda_open_cabinet-privileged` | privileged | mujoco_playground/PandaOpenCabinet | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_panda_open_cabinet-standard` | standard | mujoco_playground/PandaOpenCabinet | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_panda_pick_cube_orientation-privileged` | privileged | mujoco_playground/PandaPickCubeOrientation | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_panda_pick_cube_orientation-standard` | standard | mujoco_playground/PandaPickCubeOrientation | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_spot_flat_terrain_joystick-privileged` | privileged | mujoco_playground/SpotFlatTerrainJoystick | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_spot_flat_terrain_joystick-standard` | standard | mujoco_playground/SpotFlatTerrainJoystick | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_spot_getup-privileged` | privileged | mujoco_playground/SpotGetup | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_spot_getup-standard` | standard | mujoco_playground/SpotGetup | 1800 s | full | yes | excluded | allowlist | static |
| `mujoco_playground_spot_joystick_gait_tracking-privileged` | privileged | mujoco_playground/SpotJoystickGaitTracking | 1800 s | full | yes | core | allowlist | static |
| `mujoco_playground_spot_joystick_gait_tracking-standard` | standard | mujoco_playground/SpotJoystickGaitTracking | 1800 s | full | yes | core | allowlist | static |

### MyoSuite

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `myosuite-arm-reach-i00-privileged` | privileged | arm_reach | 3600 s | full | yes | excluded | allowlist | static |
| `myosuite-arm-reach-i00-standard` | standard | arm_reach | 3600 s | full | yes | excluded | allowlist | static |
| `myosuite-baoding-i00-privileged` | privileged | baoding | 3600 s | none | no | core | allowlist | static |
| `myosuite-baoding-i00-standard` | standard | baoding | 3600 s | none | no | core | allowlist | static |
| `myosuite-bimanual-i00-privileged` | privileged | bimanual | 3600 s | none | no | core | allowlist | static |
| `myosuite-bimanual-i00-standard` | standard | bimanual | 3600 s | none | no | core | allowlist | static |
| `myosuite-chase-tag-i00-privileged` | privileged | chase_tag | 3600 s | none | no | core | allowlist | static |
| `myosuite-chase-tag-i00-standard` | standard | chase_tag | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-airplane-fly-i00-privileged` | privileged | dex_airplane_fly | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-airplane-fly-i00-standard` | standard | dex_airplane_fly | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-apple-lift-i00-privileged` | privileged | dex_apple_lift | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-apple-lift-i00-standard` | standard | dex_apple_lift | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-bunny-inspect-i00-privileged` | privileged | dex_bunny_inspect | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-bunny-inspect-i00-standard` | standard | dex_bunny_inspect | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-cup-pour-i00-privileged` | privileged | dex_cup_pour | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-cup-pour-i00-standard` | standard | dex_cup_pour | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-cylinder-pass-i00-privileged` | privileged | dex_cylinder_pass | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-cylinder-pass-i00-standard` | standard | dex_cylinder_pass | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-hammer-use-i00-privileged` | privileged | dex_hammer_use | 3600 s | none | no | core | allowlist | static |
| `myosuite-dex-hammer-use-i00-standard` | standard | dex_hammer_use | 3600 s | none | no | core | allowlist | static |
| `myosuite-die-reorient-i00-privileged` | privileged | die_reorient | 3600 s | none | no | core | allowlist | static |
| `myosuite-die-reorient-i00-standard` | standard | die_reorient | 3600 s | none | no | core | allowlist | static |
| `myosuite-hand-pose-i00-privileged` | privileged | hand_pose | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-hand-pose-i00-standard` | standard | hand_pose | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-hand-reach-i00-privileged` | privileged | hand_reach | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-hand-reach-i00-standard` | standard | hand_reach | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-key-turn-i00-privileged` | privileged | key_turn | 3600 s | full | yes | excluded | allowlist | static |
| `myosuite-key-turn-i00-standard` | standard | key_turn | 3600 s | full | yes | excluded | allowlist | static |
| `myosuite-obj-hold-i00-privileged` | privileged | obj_hold | 3600 s | full | yes | excluded | allowlist | static |
| `myosuite-obj-hold-i00-standard` | standard | obj_hold | 3600 s | full | yes | excluded | allowlist | static |
| `myosuite-obj-reorient-i00-privileged` | privileged | obj_reorient | 3600 s | none | no | core | allowlist | static |
| `myosuite-obj-reorient-i00-standard` | standard | obj_reorient | 3600 s | none | no | core | allowlist | static |
| `myosuite-osl-run-i00-privileged` | privileged | osl_run | 3600 s | none | no | core | allowlist | static |
| `myosuite-osl-run-i00-standard` | standard | osl_run | 3600 s | none | no | core | allowlist | static |
| `myosuite-pen-twirl-i00-privileged` | privileged | pen_twirl | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-pen-twirl-i00-standard` | standard | pen_twirl | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-relocate-i00-privileged` | privileged | relocate | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-relocate-i00-standard` | standard | relocate | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-sarc-key-turn-i00-privileged` | privileged | sarc_key_turn | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-sarc-key-turn-i00-standard` | standard | sarc_key_turn | 3600 s | none | no | excluded | allowlist | static |
| `myosuite-soccer-i00-privileged` | privileged | soccer | 3600 s | none | no | core | allowlist | static |
| `myosuite-soccer-i00-standard` | standard | soccer | 3600 s | none | no | core | allowlist | static |
| `myosuite-table-tennis-i00-privileged` | privileged | table_tennis | 3600 s | none | no | excluded | allowlist | dynamic |
| `myosuite-table-tennis-i00-standard` | standard | table_tennis | 3600 s | none | no | excluded | allowlist | dynamic |
| `myosuite-table-tennis-i00-standard-realtime` | standard-realtime | table_tennis | 3600 s | none | no | excluded | allowlist | dynamic |

### Panda Dynamic Scenes

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `pandadyn-d01-reciprocal-cup-relay-i00-privileged` | privileged | d01_reciprocal_cup_relay | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d01-reciprocal-cup-relay-i00-standard` | standard | d01_reciprocal_cup_relay | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d01-reciprocal-cup-relay-i00-standard-realtime` | standard-realtime | d01_reciprocal_cup_relay | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d02-strike-catch-merge-i00-privileged` | privileged | d02_strike_catch_merge | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d02-strike-catch-merge-i00-standard` | standard | d02_strike_catch_merge | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d02-strike-catch-merge-i00-standard-realtime` | standard-realtime | d02_strike_catch_merge | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d03-cooperative-puck-course-i00-privileged` | privileged | d03_cooperative_puck_course | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d03-cooperative-puck-course-i00-standard` | standard | d03_cooperative_puck_course | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d03-cooperative-puck-course-i00-standard-realtime` | standard-realtime | d03_cooperative_puck_course | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d04-shared-tray-transport-discharge-i00-privileged` | privileged | d04_shared_tray_transport_discharge | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d04-shared-tray-transport-discharge-i00-standard` | standard | d04_shared_tray_transport_discharge | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d04-shared-tray-transport-discharge-i00-standard-realtime` | standard-realtime | d04_shared_tray_transport_discharge | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d05-moving-ramp-relay-i00-privileged` | privileged | d05_moving_ramp_relay | 3600 s | full | yes | core | allowlist | static |
| `pandadyn-d05-moving-ramp-relay-i00-standard` | standard | d05_moving_ramp_relay | 3600 s | full | yes | core | allowlist | static |
| `pandadyn-d06-moving-bank-relay-i00-privileged` | privileged | d06_moving_bank_relay | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d06-moving-bank-relay-i00-standard` | standard | d06_moving_bank_relay | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d06-moving-bank-relay-i00-standard-realtime` | standard-realtime | d06_moving_bank_relay | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d07-spring-gate-switchyard-i00-privileged` | privileged | d07_spring_gate_switchyard | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d07-spring-gate-switchyard-i00-standard` | standard | d07_spring_gate_switchyard | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d07-spring-gate-switchyard-i00-standard-realtime` | standard-realtime | d07_spring_gate_switchyard | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d08-pendulum-energy-relay-i00-privileged` | privileged | d08_pendulum_energy_relay | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d08-pendulum-energy-relay-i00-standard` | standard | d08_pendulum_energy_relay | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d09-lever-launch-catch-reload-i00-privileged` | privileged | d09_lever_launch_catch_reload | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d09-lever-launch-catch-reload-i00-standard` | standard | d09_lever_launch_catch_reload | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d09-lever-launch-catch-reload-i00-standard-realtime` | standard-realtime | d09_lever_launch_catch_reload | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-d10-moving-grasp-handover-i00-privileged` | privileged | d10_moving_grasp_handover | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d10-moving-grasp-handover-i00-standard` | standard | d10_moving_grasp_handover | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d10-moving-grasp-handover-i00-standard-realtime` | standard-realtime | d10_moving_grasp_handover | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-d11-moving-fixture-unlock-i00-privileged` | privileged | d11_moving_fixture_unlock | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d11-moving-fixture-unlock-i00-standard` | standard | d11_moving_fixture_unlock | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d12-reciprocal-sliding-transfer-i00-privileged` | privileged | d12_reciprocal_sliding_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d12-reciprocal-sliding-transfer-i00-standard` | standard | d12_reciprocal_sliding_transfer | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d13-supported-cube-flip-relay-i00-privileged` | privileged | d13_supported_cube_flip_relay | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-d13-supported-cube-flip-relay-i00-standard` | standard | d13_supported_cube_flip_relay | 3600 s | full | yes | excluded | allowlist | static |
| `pandadyn-s01-cup-route-delivery-i00-privileged` | privileged | s01_cup_route_delivery | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s01-cup-route-delivery-i00-standard` | standard | s01_cup_route_delivery | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s01-cup-route-delivery-i00-standard-realtime` | standard-realtime | s01_cup_route_delivery | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s02-plate-catch-transport-release-i00-privileged` | privileged | s02_plate_catch_transport_release | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s02-plate-catch-transport-release-i00-standard` | standard | s02_plate_catch_transport_release | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s02-plate-catch-transport-release-i00-standard-realtime` | standard-realtime | s02_plate_catch_transport_release | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s03-clear-gate-hockey-i00-privileged` | privileged | s03_clear_gate_hockey | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s03-clear-gate-hockey-i00-standard` | standard | s03_clear_gate_hockey | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s03-clear-gate-hockey-i00-standard-realtime` | standard-realtime | s03_clear_gate_hockey | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s04-impact-release-relay-i00-privileged` | privileged | s04_impact_release_relay | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s04-impact-release-relay-i00-standard` | standard | s04_impact_release_relay | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s04-impact-release-relay-i00-standard-realtime` | standard-realtime | s04_impact_release_relay | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s05-sliding-receive-align-deliver-i00-privileged` | privileged | s05_sliding_receive_align_deliver | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s05-sliding-receive-align-deliver-i00-standard` | standard | s05_sliding_receive_align_deliver | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s05-sliding-receive-align-deliver-i00-standard-realtime` | standard-realtime | s05_sliding_receive_align_deliver | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s06-cube-flip-route-recover-i00-privileged` | privileged | s06_cube_flip_route_recover | 3600 s | full | yes | core | allowlist | static |
| `pandadyn-s06-cube-flip-route-recover-i00-standard` | standard | s06_cube_flip_route_recover | 3600 s | full | yes | core | allowlist | static |
| `pandadyn-s07-conveyor-load-brake-unload-i00-privileged` | privileged | s07_conveyor_load_brake_unload | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s07-conveyor-load-brake-unload-i00-standard` | standard | s07_conveyor_load_brake_unload | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s07-conveyor-load-brake-unload-i00-standard-realtime` | standard-realtime | s07_conveyor_load_brake_unload | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s08-load-switch-recover-i00-privileged` | privileged | s08_load_switch_recover | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s08-load-switch-recover-i00-standard` | standard | s08_load_switch_recover | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s08-load-switch-recover-i00-standard-realtime` | standard-realtime | s08_load_switch_recover | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s09-toss-recatch-delivery-i00-privileged` | privileged | s09_toss_recatch_delivery | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s09-toss-recatch-delivery-i00-standard` | standard | s09_toss_recatch_delivery | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s09-toss-recatch-delivery-i00-standard-realtime` | standard-realtime | s09_toss_recatch_delivery | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s10-swinging-load-transit-dock-i00-privileged` | privileged | s10_swinging_load_transit_dock | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s10-swinging-load-transit-dock-i00-standard` | standard | s10_swinging_load_transit_dock | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s10-swinging-load-transit-dock-i00-standard-realtime` | standard-realtime | s10_swinging_load_transit_dock | 3600 s | full | yes | excluded | allowlist | dynamic |
| `pandadyn-s11-cylinder-rescue-route-deliver-i00-privileged` | privileged | s11_cylinder_rescue_route_deliver | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s11-cylinder-rescue-route-deliver-i00-standard` | standard | s11_cylinder_rescue_route_deliver | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s11-cylinder-rescue-route-deliver-i00-standard-realtime` | standard-realtime | s11_cylinder_rescue_route_deliver | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s12-moving-bridge-puck-relay-i00-privileged` | privileged | s12_moving_bridge_puck_relay | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s12-moving-bridge-puck-relay-i00-standard` | standard | s12_moving_bridge_puck_relay | 3600 s | full | yes | core | allowlist | dynamic |
| `pandadyn-s12-moving-bridge-puck-relay-i00-standard-realtime` | standard-realtime | s12_moving_bridge_puck_relay | 3600 s | full | yes | core | allowlist | dynamic |

### RoboARC

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `roboarc-blanket-flatten-01-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-flatten-01-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-flatten-02-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-02-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-03-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-03-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-04-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-04-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-05-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-flatten-05-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-flatten-06-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-flatten-06-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-flatten-07-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-07-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-08-i01-privileged` | privileged | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-flatten-08-i01-standard` | standard | blanket_flatten | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-01-i01-privileged` | privileged | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-01-i01-standard` | standard | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-02-i01-privileged` | privileged | blanket_fold | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-fold-02-i01-standard` | standard | blanket_fold | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-blanket-fold-03-i01-privileged` | privileged | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-03-i01-standard` | standard | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-04-i01-privileged` | privileged | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-04-i01-standard` | standard | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-05-i01-privileged` | privileged | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-blanket-fold-05-i01-standard` | standard | blanket_fold | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-01-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-01-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-02-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-02-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-03-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-buzz-wire-3d-03-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-buzz-wire-3d-04-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-04-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-05-i01-privileged` | privileged | buzz_wire_3d | 10800 s | none | no | excluded | allowlist | static |
| `roboarc-buzz-wire-3d-05-i01-standard` | standard | buzz_wire_3d | 10800 s | none | no | excluded | allowlist | static |
| `roboarc-buzz-wire-3d-06-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-06-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-07-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-07-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-08-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-buzz-wire-3d-08-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-buzz-wire-3d-09-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-09-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-10-i01-privileged` | privileged | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-buzz-wire-3d-10-i01-standard` | standard | buzz_wire_3d | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-01-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-01-i01-standard` | standard | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-02-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-02-i01-standard` | standard | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-03-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-03-i01-standard` | standard | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-04-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-04-i01-standard` | standard | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-05-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-05-i01-standard` | standard | cast_coil | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-coil-06-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-06-i01-standard` | standard | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-07-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-07-i01-standard` | standard | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-08-i01-privileged` | privileged | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-coil-08-i01-standard` | standard | cast_coil | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-01-i01-privileged` | privileged | cast_keyhole | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-keyhole-01-i01-standard` | standard | cast_keyhole | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-keyhole-02-i01-privileged` | privileged | cast_keyhole | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-keyhole-02-i01-standard` | standard | cast_keyhole | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-keyhole-03-i01-privileged` | privileged | cast_keyhole | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-03-i01-standard` | standard | cast_keyhole | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-04-i01-privileged` | privileged | cast_keyhole | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-04-i01-standard` | standard | cast_keyhole | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-05-i01-privileged` | privileged | cast_keyhole | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-05-i01-standard` | standard | cast_keyhole | 10800 s | full | yes | core | allowlist | static |
| `roboarc-cast-keyhole-06-i01-privileged` | privileged | cast_keyhole | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-cast-keyhole-06-i01-standard` | standard | cast_keyhole | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-01-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-01-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-02-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-02-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-03-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-03-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-04-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-04-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-05-i01-privileged` | privileged | fiber_bundling | 10800 s | none | no | excluded | allowlist | static |
| `roboarc-fiber-bundling-05-i01-standard` | standard | fiber_bundling | 10800 s | none | no | excluded | allowlist | static |
| `roboarc-fiber-bundling-06-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-06-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-07-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-07-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-08-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-08-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-fiber-bundling-09-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-09-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-10-i01-privileged` | privileged | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-fiber-bundling-10-i01-standard` | standard | fiber_bundling | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-01-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-01-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-02-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-02-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-03-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-03-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-04-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-04-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-05-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-05-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-06-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-06-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-07-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-07-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | core | allowlist | static |
| `roboarc-hedgehog-in-cage-08-i01-privileged` | privileged | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-hedgehog-in-cage-08-i01-standard` | standard | hedgehog_in_cage | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-horseshoe-ring-01-i01-privileged` | privileged | horseshoe_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-horseshoe-ring-01-i01-standard` | standard | horseshoe_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-horseshoe-ring-02-i01-privileged` | privileged | horseshoe_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-horseshoe-ring-02-i01-standard` | standard | horseshoe_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-horseshoe-ring-03-i01-privileged` | privileged | horseshoe_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-horseshoe-ring-03-i01-standard` | standard | horseshoe_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-horseshoe-ring-04-i01-privileged` | privileged | horseshoe_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-horseshoe-ring-04-i01-standard` | standard | horseshoe_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-horseshoe-ring-05-i01-privileged` | privileged | horseshoe_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-horseshoe-ring-05-i01-standard` | standard | horseshoe_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-ikea-eket-i00-privileged` | privileged | ikea_eket | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-eket-i00-standard` | standard | ikea_eket | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-gladom-i00-privileged` | privileged | ikea_gladom | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-gladom-i00-standard` | standard | ikea_gladom | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-ikea365-i00-privileged` | privileged | ikea_ikea365 | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-ikea365-i00-standard` | standard | ikea_ikea365 | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-lack-i00-privileged` | privileged | ikea_lack | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-lack-i00-standard` | standard | ikea_lack | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-stegesund-i00-privileged` | privileged | ikea_stegesund | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-stegesund-i00-standard` | standard | ikea_stegesund | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-svallet-i00-privileged` | privileged | ikea_svallet | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-svallet-i00-standard` | standard | ikea_svallet | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-variera-i00-privileged` | privileged | ikea_variera | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-variera-i00-standard` | standard | ikea_variera | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-vesken-i00-privileged` | privileged | ikea_vesken | 10800 s | full | yes | core | allowlist | static |
| `roboarc-ikea-vesken-i00-standard` | standard | ikea_vesken | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-01-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-01-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-02-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-02-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-03-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-03-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-04-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-04-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-05-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-05-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-06-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-06-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-07-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-07-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-08-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-08-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-09-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-09-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-10-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-10-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-interlocked-claws-11-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-11-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-12-i01-privileged` | privileged | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-interlocked-claws-12-i01-standard` | standard | interlocked_claws | 10800 s | full | yes | core | allowlist | static |
| `roboarc-knot-untying-01-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-01-i01-standard` | standard | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-02-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-02-i01-standard` | standard | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-03-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-03-i01-standard` | standard | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-04-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-04-i01-standard` | standard | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-05-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-05-i01-standard` | standard | knot_untying | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-knot-untying-06-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | core | allowlist | static |
| `roboarc-knot-untying-06-i01-standard` | standard | knot_untying | 10800 s | full | yes | core | allowlist | static |
| `roboarc-knot-untying-09-i01-privileged` | privileged | knot_untying | 10800 s | full | yes | core | allowlist | static |
| `roboarc-knot-untying-09-i01-standard` | standard | knot_untying | 10800 s | full | yes | core | allowlist | static |
| `roboarc-lock-picking-01-i01-privileged` | privileged | lock_picking | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-lock-picking-01-i01-standard` | standard | lock_picking | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-lock-picking-02-i01-privileged` | privileged | lock_picking | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-lock-picking-02-i01-standard` | standard | lock_picking | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-lock-picking-03-i01-privileged` | privileged | lock_picking | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-lock-picking-03-i01-standard` | standard | lock_picking | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-lock-picking-04-i01-privileged` | privileged | lock_picking | 10800 s | full | yes | core | allowlist | static |
| `roboarc-lock-picking-04-i01-standard` | standard | lock_picking | 10800 s | full | yes | core | allowlist | static |
| `roboarc-lock-picking-05-i01-privileged` | privileged | lock_picking | 10800 s | full | yes | core | allowlist | static |
| `roboarc-lock-picking-05-i01-standard` | standard | lock_picking | 10800 s | full | yes | core | allowlist | static |
| `roboarc-orbits-01-i01-privileged` | privileged | orbits | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-orbits-01-i01-standard` | standard | orbits | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-rope-threading-01-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-rope-threading-01-i01-standard` | standard | rope_threading | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-rope-threading-02-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-rope-threading-02-i01-standard` | standard | rope_threading | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-rope-threading-03-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-03-i01-standard` | standard | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-04-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-04-i01-standard` | standard | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-05-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-05-i01-standard` | standard | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-06-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-06-i01-standard` | standard | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-07-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-07-i01-standard` | standard | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-08-i01-privileged` | privileged | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-rope-threading-08-i01-standard` | standard | rope_threading | 10800 s | full | yes | core | allowlist | static |
| `roboarc-slotted-post-ring-01-i01-privileged` | privileged | slotted_post_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-slotted-post-ring-01-i01-standard` | standard | slotted_post_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-slotted-post-ring-02-i01-privileged` | privileged | slotted_post_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-slotted-post-ring-02-i01-standard` | standard | slotted_post_ring | 10800 s | full | yes | excluded | allowlist | static |
| `roboarc-slotted-post-ring-03-i01-privileged` | privileged | slotted_post_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-slotted-post-ring-03-i01-standard` | standard | slotted_post_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-slotted-post-ring-04-i01-privileged` | privileged | slotted_post_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-slotted-post-ring-04-i01-standard` | standard | slotted_post_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-slotted-post-ring-05-i01-privileged` | privileged | slotted_post_ring | 10800 s | full | yes | core | allowlist | static |
| `roboarc-slotted-post-ring-05-i01-standard` | standard | slotted_post_ring | 10800 s | full | yes | core | allowlist | static |

### RoboCasa

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robocasa-arrange-vegetables-i00-privileged` | privileged | robocasa/ArrangeVegetables | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-arrange-vegetables-i00-standard` | standard | robocasa/ArrangeVegetables | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-close-double-door-i00-privileged` | privileged | robocasa/CloseDoubleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-close-double-door-i00-standard` | standard | robocasa/CloseDoubleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-close-drawer-i00-privileged` | privileged | robocasa/CloseDrawer | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-close-drawer-i00-standard` | standard | robocasa/CloseDrawer | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-close-single-door-i00-privileged` | privileged | robocasa/CloseSingleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-close-single-door-i00-standard` | standard | robocasa/CloseSingleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-coffee-press-button-i00-privileged` | privileged | robocasa/CoffeePressButton | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-coffee-press-button-i00-standard` | standard | robocasa/CoffeePressButton | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-coffee-serve-mug-i00-privileged` | privileged | robocasa/CoffeeServeMug | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-coffee-serve-mug-i00-standard` | standard | robocasa/CoffeeServeMug | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-coffee-setup-mug-i00-privileged` | privileged | robocasa/CoffeeSetupMug | 3600 s | full | yes | core | allowlist | static |
| `robocasa-coffee-setup-mug-i00-standard` | standard | robocasa/CoffeeSetupMug | 3600 s | full | yes | core | allowlist | static |
| `robocasa-microwave-thawing-i00-privileged` | privileged | robocasa/MicrowaveThawing | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-microwave-thawing-i00-standard` | standard | robocasa/MicrowaveThawing | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-open-double-door-i00-privileged` | privileged | robocasa/OpenDoubleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-open-double-door-i00-standard` | standard | robocasa/OpenDoubleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-open-drawer-i00-privileged` | privileged | robocasa/OpenDrawer | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-open-drawer-i00-standard` | standard | robocasa/OpenDrawer | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-open-single-door-i00-privileged` | privileged | robocasa/OpenSingleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-open-single-door-i00-standard` | standard | robocasa/OpenSingleDoor | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-cab-to-counter-i00-privileged` | privileged | robocasa/PnPCabToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-cab-to-counter-i00-standard` | standard | robocasa/PnPCabToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-cab-i00-privileged` | privileged | robocasa/PnPCounterToCab | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-cab-i00-standard` | standard | robocasa/PnPCounterToCab | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-microwave-i00-privileged` | privileged | robocasa/PnPCounterToMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-microwave-i00-standard` | standard | robocasa/PnPCounterToMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-sink-i00-privileged` | privileged | robocasa/PnPCounterToSink | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-sink-i00-standard` | standard | robocasa/PnPCounterToSink | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-stove-i00-privileged` | privileged | robocasa/PnPCounterToStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-counter-to-stove-i00-standard` | standard | robocasa/PnPCounterToStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-microwave-to-counter-i00-privileged` | privileged | robocasa/PnPMicrowaveToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-microwave-to-counter-i00-standard` | standard | robocasa/PnPMicrowaveToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-sink-to-counter-i00-privileged` | privileged | robocasa/PnPSinkToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-sink-to-counter-i00-standard` | standard | robocasa/PnPSinkToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-stove-to-counter-i00-privileged` | privileged | robocasa/PnPStoveToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pnp-stove-to-counter-i00-standard` | standard | robocasa/PnPStoveToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pre-soak-pan-i00-privileged` | privileged | robocasa/PreSoakPan | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-pre-soak-pan-i00-standard` | standard | robocasa/PreSoakPan | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-prepare-coffee-i00-privileged` | privileged | robocasa/PrepareCoffee | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-prepare-coffee-i00-standard` | standard | robocasa/PrepareCoffee | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-restock-pantry-i00-privileged` | privileged | robocasa/RestockPantry | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-restock-pantry-i00-standard` | standard | robocasa/RestockPantry | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-off-microwave-i00-privileged` | privileged | robocasa/TurnOffMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-off-microwave-i00-standard` | standard | robocasa/TurnOffMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-off-sink-faucet-i00-privileged` | privileged | robocasa/TurnOffSinkFaucet | 3600 s | full | yes | core | allowlist | static |
| `robocasa-turn-off-sink-faucet-i00-standard` | standard | robocasa/TurnOffSinkFaucet | 3600 s | full | yes | core | allowlist | static |
| `robocasa-turn-off-stove-i00-privileged` | privileged | robocasa/TurnOffStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-off-stove-i00-standard` | standard | robocasa/TurnOffStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-on-microwave-i00-privileged` | privileged | robocasa/TurnOnMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-on-microwave-i00-standard` | standard | robocasa/TurnOnMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-on-sink-faucet-i00-privileged` | privileged | robocasa/TurnOnSinkFaucet | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-on-sink-faucet-i00-standard` | standard | robocasa/TurnOnSinkFaucet | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-on-stove-i00-privileged` | privileged | robocasa/TurnOnStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-on-stove-i00-standard` | standard | robocasa/TurnOnStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-sink-spout-i00-privileged` | privileged | robocasa/TurnSinkSpout | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-turn-sink-spout-i00-standard` | standard | robocasa/TurnSinkSpout | 3600 s | full | yes | excluded | allowlist | static |

### RoboCasa-GR1

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robocasa-gr1-bottle-to-cabinet-close-i00-privileged` | privileged | robocasa-gr1/PnPBottleToCabinetClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-bottle-to-cabinet-close-i00-standard` | standard | robocasa-gr1/PnPBottleToCabinetClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-can-to-drawer-close-i00-privileged` | privileged | robocasa-gr1/PnPCanToDrawerClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-can-to-drawer-close-i00-standard` | standard | robocasa-gr1/PnPCanToDrawerClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cup-to-drawer-close-i00-privileged` | privileged | robocasa-gr1/PnPCupToDrawerClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cup-to-drawer-close-i00-standard` | standard | robocasa-gr1/PnPCupToDrawerClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-basket-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToBasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-basket-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToBasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-cardboardbox-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToCardboardboxSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-cardboardbox-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToCardboardboxSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-pan-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToPanSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-pan-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToPanSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-pot-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToPotSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-pot-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToPotSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-tieredbasket-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToTieredbasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-cuttingboard-to-tieredbasket-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromCuttingboardToTieredbasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-milk-to-microwave-close-i00-privileged` | privileged | robocasa-gr1/PnPMilkToMicrowaveClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-milk-to-microwave-close-i00-standard` | standard | robocasa-gr1/PnPMilkToMicrowaveClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-basket-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlacematToBasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-basket-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlacematToBasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-bowl-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlacematToBowlSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-bowl-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlacematToBowlSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-plate-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlacematToPlateSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-plate-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlacematToPlateSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-tieredshelf-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlacematToTieredshelfSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-placemat-to-tieredshelf-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlacematToTieredshelfSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-bowl-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlateToBowlSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-bowl-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlateToBowlSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-cardboardbox-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlateToCardboardboxSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-cardboardbox-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlateToCardboardboxSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-pan-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlateToPanSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-pan-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlateToPanSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-plate-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromPlateToPlateSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-plate-to-plate-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromPlateToPlateSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-potato-to-microwave-close-i00-privileged` | privileged | robocasa-gr1/PnPPotatoToMicrowaveClose | 3600 s | full | yes | core | allowlist | static |
| `robocasa-gr1-potato-to-microwave-close-i00-standard` | standard | robocasa-gr1/PnPPotatoToMicrowaveClose | 3600 s | full | yes | core | allowlist | static |
| `robocasa-gr1-tray-to-cardboardbox-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromTrayToCardboardboxSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-cardboardbox-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromTrayToCardboardboxSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-plate-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromTrayToPlateSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-plate-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromTrayToPlateSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-pot-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromTrayToPotSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-pot-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromTrayToPotSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-tieredbasket-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromTrayToTieredbasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-tieredbasket-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromTrayToTieredbasketSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-tieredshelf-i00-privileged` | privileged | robocasa-gr1/PosttrainPnPNovelFromTrayToTieredshelfSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-tray-to-tieredshelf-i00-standard` | standard | robocasa-gr1/PosttrainPnPNovelFromTrayToTieredshelfSplitA | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-wine-to-cabinet-close-i00-privileged` | privileged | robocasa-gr1/PnPWineToCabinetClose | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa-gr1-wine-to-cabinet-close-i00-standard` | standard | robocasa-gr1/PnPWineToCabinetClose | 3600 s | full | yes | excluded | allowlist | static |

### RoboCasa365

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robocasa365-add-lemon-to-fish-i00-privileged` | privileged | robocasa365/AddLemonToFish | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-add-lemon-to-fish-i00-standard` | standard | robocasa365/AddLemonToFish | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-assemble-cooking-array-i00-privileged` | privileged | robocasa365/AssembleCookingArray | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-assemble-cooking-array-i00-standard` | standard | robocasa365/AssembleCookingArray | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-beverage-sorting-i00-privileged` | privileged | robocasa365/BeverageSorting | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-beverage-sorting-i00-standard` | standard | robocasa365/BeverageSorting | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-bread-and-cheese-i00-privileged` | privileged | robocasa365/BreadAndCheese | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-bread-and-cheese-i00-standard` | standard | robocasa365/BreadAndCheese | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-candle-cleanup-i00-privileged` | privileged | robocasa365/CandleCleanup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-candle-cleanup-i00-standard` | standard | robocasa365/CandleCleanup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-cereal-and-bowl-i00-privileged` | privileged | robocasa365/CerealAndBowl | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-cereal-and-bowl-i00-standard` | standard | robocasa365/CerealAndBowl | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-choose-measuring-cup-i00-privileged` | privileged | robocasa365/ChooseMeasuringCup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-choose-measuring-cup-i00-standard` | standard | robocasa365/ChooseMeasuringCup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-clear-food-waste-i00-privileged` | privileged | robocasa365/ClearFoodWaste | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-clear-food-waste-i00-standard` | standard | robocasa365/ClearFoodWaste | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-clear-sink-i00-privileged` | privileged | robocasa365/ClearSink | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-clear-sink-i00-standard` | standard | robocasa365/ClearSink | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-close-drawer-i00-privileged` | privileged | robocasa365/CloseDrawer | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-close-drawer-i00-standard` | standard | robocasa365/CloseDrawer | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-close-oven-i00-privileged` | privileged | robocasa365/CloseOven | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-close-oven-i00-standard` | standard | robocasa365/CloseOven | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-close-stand-mixer-head-i00-privileged` | privileged | robocasa365/CloseStandMixerHead | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-close-stand-mixer-head-i00-standard` | standard | robocasa365/CloseStandMixerHead | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-cookie-dough-prep-i00-privileged` | privileged | robocasa365/CookieDoughPrep | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-cookie-dough-prep-i00-standard` | standard | robocasa365/CookieDoughPrep | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-deliver-brewed-coffee-i00-privileged` | privileged | robocasa365/DeliverBrewedCoffee | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-deliver-brewed-coffee-i00-standard` | standard | robocasa365/DeliverBrewedCoffee | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-dessert-upgrade-i00-privileged` | privileged | robocasa365/DessertUpgrade | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-dessert-upgrade-i00-standard` | standard | robocasa365/DessertUpgrade | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-display-meat-variety-i00-privileged` | privileged | robocasa365/DisplayMeatVariety | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-display-meat-variety-i00-standard` | standard | robocasa365/DisplayMeatVariety | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-divide-basins-i00-privileged` | privileged | robocasa365/DivideBasins | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-divide-basins-i00-standard` | standard | robocasa365/DivideBasins | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-drain-veggies-i00-privileged` | privileged | robocasa365/DrainVeggies | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-drain-veggies-i00-standard` | standard | robocasa365/DrainVeggies | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-drinkware-consolidation-i00-privileged` | privileged | robocasa365/DrinkwareConsolidation | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-drinkware-consolidation-i00-standard` | standard | robocasa365/DrinkwareConsolidation | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-make-ice-lemonade-i00-privileged` | privileged | robocasa365/MakeIceLemonade | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-make-ice-lemonade-i00-standard` | standard | robocasa365/MakeIceLemonade | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-make-loaded-potato-i00-privileged` | privileged | robocasa365/MakeLoadedPotato | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-make-loaded-potato-i00-standard` | standard | robocasa365/MakeLoadedPotato | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-meal-prep-staging-i00-privileged` | privileged | robocasa365/MealPrepStaging | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-meal-prep-staging-i00-standard` | standard | robocasa365/MealPrepStaging | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-microwave-defrost-meat-i00-privileged` | privileged | robocasa365/MicrowaveDefrostMeat | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-microwave-defrost-meat-i00-standard` | standard | robocasa365/MicrowaveDefrostMeat | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-open-dishwasher-i00-privileged` | privileged | robocasa365/OpenDishwasher | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-open-dishwasher-i00-standard` | standard | robocasa365/OpenDishwasher | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-organize-coffee-condiments-i00-privileged` | privileged | robocasa365/OrganizeCoffeeCondiments | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-organize-coffee-condiments-i00-standard` | standard | robocasa365/OrganizeCoffeeCondiments | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-oven-broil-fish-i00-privileged` | privileged | robocasa365/OvenBroilFish | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-oven-broil-fish-i00-standard` | standard | robocasa365/OvenBroilFish | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pack-dessert-i00-privileged` | privileged | robocasa365/PackDessert | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pack-dessert-i00-standard` | standard | robocasa365/PackDessert | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pick-place-cabinet-to-counter-i00-privileged` | privileged | robocasa365/PickPlaceCabinetToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pick-place-cabinet-to-counter-i00-standard` | standard | robocasa365/PickPlaceCabinetToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pick-place-sink-to-counter-i00-privileged` | privileged | robocasa365/PickPlaceSinkToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pick-place-sink-to-counter-i00-standard` | standard | robocasa365/PickPlaceSinkToCounter | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-plate-steak-meal-i00-privileged` | privileged | robocasa365/PlateSteakMeal | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-plate-steak-meal-i00-standard` | standard | robocasa365/PlateSteakMeal | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-portion-in-tupperware-i00-privileged` | privileged | robocasa365/PortionInTupperware | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-portion-in-tupperware-i00-standard` | standard | robocasa365/PortionInTupperware | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pre-rinse-station-i00-privileged` | privileged | robocasa365/PreRinseStation | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-pre-rinse-station-i00-standard` | standard | robocasa365/PreRinseStation | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-prep-for-sanitizing-i00-privileged` | privileged | robocasa365/PrepForSanitizing | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-prep-for-sanitizing-i00-standard` | standard | robocasa365/PrepForSanitizing | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-prep-marinating-meat-i00-privileged` | privileged | robocasa365/PrepMarinatingMeat | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-prep-marinating-meat-i00-standard` | standard | robocasa365/PrepMarinatingMeat | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-reheat-meal-i00-privileged` | privileged | robocasa365/ReheatMeal | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-reheat-meal-i00-standard` | standard | robocasa365/ReheatMeal | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-retrieve-meat-i00-privileged` | privileged | robocasa365/RetrieveMeat | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-retrieve-meat-i00-standard` | standard | robocasa365/RetrieveMeat | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-sanitize-prep-cutting-board-i00-privileged` | privileged | robocasa365/SanitizePrepCuttingBoard | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-sanitize-prep-cutting-board-i00-standard` | standard | robocasa365/SanitizePrepCuttingBoard | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-scrub-bowl-i00-privileged` | privileged | robocasa365/ScrubBowl | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-scrub-bowl-i00-standard` | standard | robocasa365/ScrubBowl | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-searing-meat-i00-privileged` | privileged | robocasa365/SearingMeat | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-searing-meat-i00-standard` | standard | robocasa365/SearingMeat | 3600 s | full | yes | core | allowlist | static |
| `robocasa365-seasoning-spice-setup-i00-privileged` | privileged | robocasa365/SeasoningSpiceSetup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-seasoning-spice-setup-i00-standard` | standard | robocasa365/SeasoningSpiceSetup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-set-up-cutting-station-i00-privileged` | privileged | robocasa365/SetUpCuttingStation | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-set-up-cutting-station-i00-standard` | standard | robocasa365/SetUpCuttingStation | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-stocking-breakfast-foods-i00-privileged` | privileged | robocasa365/StockingBreakfastFoods | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-stocking-breakfast-foods-i00-standard` | standard | robocasa365/StockingBreakfastFoods | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-sweeten-coffee-i00-privileged` | privileged | robocasa365/SweetenCoffee | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-sweeten-coffee-i00-standard` | standard | robocasa365/SweetenCoffee | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-thaw-in-sink-i00-privileged` | privileged | robocasa365/ThawInSink | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-thaw-in-sink-i00-standard` | standard | robocasa365/ThawInSink | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-tong-buffet-setup-i00-privileged` | privileged | robocasa365/TongBuffetSetup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-tong-buffet-setup-i00-standard` | standard | robocasa365/TongBuffetSetup | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-off-microwave-i00-privileged` | privileged | robocasa365/TurnOffMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-off-microwave-i00-standard` | standard | robocasa365/TurnOffMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-microwave-i00-privileged` | privileged | robocasa365/TurnOnMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-microwave-i00-standard` | standard | robocasa365/TurnOnMicrowave | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-sink-faucet-i00-privileged` | privileged | robocasa365/TurnOnSinkFaucet | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-sink-faucet-i00-standard` | standard | robocasa365/TurnOnSinkFaucet | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-stove-i00-privileged` | privileged | robocasa365/TurnOnStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-stove-i00-standard` | standard | robocasa365/TurnOnStove | 3600 s | full | yes | excluded | allowlist | static |
| `robocasa365-turn-on-toaster-oven-i00-privileged` | privileged | robocasa365/TurnOnToasterOven | 3600 s | full | yes | excluded | allowlist | dynamic |
| `robocasa365-turn-on-toaster-oven-i00-standard` | standard | robocasa365/TurnOnToasterOven | 3600 s | full | yes | excluded | allowlist | dynamic |
| `robocasa365-turn-on-toaster-oven-i00-standard-realtime` | standard-realtime | robocasa365/TurnOnToasterOven | 3600 s | none | no | excluded | allowlist | dynamic |

### RoboDojo

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robodojo-align-blocks-i00-privileged` | privileged | align_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-align-blocks-i00-standard` | standard | align_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-arrange-largest-number-i00-privileged` | privileged | arrange_largest_number | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-arrange-largest-number-i00-standard` | standard | arrange_largest_number | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-arrange-largest-number-random-i00-privileged` | privileged | arrange_largest_number_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-arrange-largest-number-random-i00-standard` | standard | arrange_largest_number_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-build-tower-i00-privileged` | privileged | build_tower | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-build-tower-i00-standard` | standard | build_tower | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-classify-objects-by-language-i00-privileged` | privileged | classify_objects_by_language | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-classify-objects-by-language-i00-standard` | standard | classify_objects_by_language | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-classify-objects-i00-privileged` | privileged | classify_objects | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-classify-objects-i00-standard` | standard | classify_objects | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-cover-blocks-i00-privileged` | privileged | cover_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-cover-blocks-i00-standard` | standard | cover_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-deposit-coin-i00-privileged` | privileged | deposit_coin | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-deposit-coin-i00-standard` | standard | deposit_coin | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-fasten-screws-i00-privileged` | privileged | fasten_screws | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-fasten-screws-i00-standard` | standard | fasten_screws | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-fill-egg-holder-i00-privileged` | privileged | fill_egg_holder | 3600 s | none | no | core | allowlist | static |
| `robodojo-fill-egg-holder-i00-standard` | standard | fill_egg_holder | 3600 s | none | no | core | allowlist | static |
| `robodojo-fill-pen-holder-i00-privileged` | privileged | fill_pen_holder | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-fill-pen-holder-i00-standard` | standard | fill_pen_holder | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-fold-clothes-i00-standard` | standard | fold_clothes | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-fold-clothes-random-i00-standard` | standard | fold_clothes_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-general-pickup-i00-privileged` | privileged | general_pickup | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-general-pickup-i00-standard` | standard | general_pickup | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-hang-mugs-i00-privileged` | privileged | hang_mugs | 3600 s | none | no | core | allowlist | static |
| `robodojo-hang-mugs-i00-standard` | standard | hang_mugs | 3600 s | none | no | core | allowlist | static |
| `robodojo-hang-mugs-random-i00-privileged` | privileged | hang_mugs_random | 3600 s | none | no | core | allowlist | static |
| `robodojo-hang-mugs-random-i00-standard` | standard | hang_mugs_random | 3600 s | none | no | core | allowlist | static |
| `robodojo-imitate-sorting-sequence-i00-privileged` | privileged | imitate_sorting_sequence | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-imitate-sorting-sequence-i00-standard` | standard | imitate_sorting_sequence | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-insert-key-i00-privileged` | privileged | insert_key | 3600 s | none | no | core | allowlist | static |
| `robodojo-insert-key-i00-standard` | standard | insert_key | 3600 s | none | no | core | allowlist | static |
| `robodojo-insert-tubes-i00-privileged` | privileged | insert_tubes | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-insert-tubes-i00-standard` | standard | insert_tubes | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-make-kong-i00-privileged` | privileged | make_kong | 3600 s | none | no | core | allowlist | dynamic |
| `robodojo-make-kong-i00-standard` | standard | make_kong | 3600 s | none | no | core | allowlist | dynamic |
| `robodojo-make-toast-i00-privileged` | privileged | make_toast | 3600 s | none | no | core | allowlist | static |
| `robodojo-make-toast-i00-standard` | standard | make_toast | 3600 s | none | no | core | allowlist | static |
| `robodojo-make-toast-random-i00-standard` | standard | make_toast_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-match-and-pick-from-conveyor-i00-privileged` | privileged | match_and_pick_from_conveyor | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-match-and-pick-from-conveyor-i00-standard` | standard | match_and_pick_from_conveyor | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-organize-table-i00-privileged` | privileged | organize_table | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-organize-table-i00-standard` | standard | organize_table | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pack-objects-into-box-i00-privileged` | privileged | pack_objects_into_box | 3600 s | none | no | core | allowlist | static |
| `robodojo-pack-objects-into-box-i00-standard` | standard | pack_objects_into_box | 3600 s | none | no | core | allowlist | static |
| `robodojo-pack-objects-into-box-random-i00-privileged` | privileged | pack_objects_into_box_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pack-objects-into-box-random-i00-standard` | standard | pack_objects_into_box_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pick-from-conveyor-by-image-i00-privileged` | privileged | pick_from_conveyor_by_image | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-pick-from-conveyor-by-image-i00-standard` | standard | pick_from_conveyor_by_image | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-play-stacking-toy-i00-privileged` | privileged | play_stacking_toy | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-play-stacking-toy-i00-standard` | standard | play_stacking_toy | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-play-tic-tac-toe-i00-privileged` | privileged | play_tic_tac_toe | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-play-tic-tac-toe-i00-standard` | standard | play_tic_tac_toe | 3600 s | none | no | excluded | allowlist | dynamic |
| `robodojo-play-xylophone-i00-privileged` | privileged | play_Xylophone | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-play-xylophone-i00-standard` | standard | play_Xylophone | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-plug-in-charger-i00-privileged` | privileged | plug_in_charger | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-plug-in-charger-i00-standard` | standard | plug_in_charger | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pour-balls-into-vase-i00-privileged` | privileged | pour_balls_into_vase | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pour-balls-into-vase-i00-standard` | standard | pour_balls_into_vase | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pour-by-language-i00-standard` | standard | pour_by_language | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pour-liquid-into-cup-i00-standard` | standard | pour_liquid_into_cup | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-pour-liquid-into-cup-random-i00-standard` | standard | pour_liquid_into_cup_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-press-by-number-i00-privileged` | privileged | press_by_number | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-press-by-number-i00-standard` | standard | press_by_number | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-push-t-i00-privileged` | privileged | push_T | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-push-t-i00-standard` | standard | push_T | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-push-t-random-i00-privileged` | privileged | push_T_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-push-t-random-i00-standard` | standard | push_T_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-put-bottles-into-dustbin-i00-privileged` | privileged | put_bottles_into_dustbin | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-put-bottles-into-dustbin-i00-standard` | standard | put_bottles_into_dustbin | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-solve-equation-i00-privileged` | privileged | solve_equation | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-solve-equation-i00-standard` | standard | solve_equation | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sort-nesting-dolls-by-size-i00-privileged` | privileged | sort_nesting_dolls_by_size | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sort-nesting-dolls-by-size-i00-standard` | standard | sort_nesting_dolls_by_size | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sort-nesting-dolls-by-size-random-i00-privileged` | privileged | sort_nesting_dolls_by_size_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sort-nesting-dolls-by-size-random-i00-standard` | standard | sort_nesting_dolls_by_size_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-blocks-by-language-i00-privileged` | privileged | stack_blocks_by_language | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-blocks-by-language-i00-standard` | standard | stack_blocks_by_language | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-blocks-i00-privileged` | privileged | stack_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-blocks-i00-standard` | standard | stack_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-blocks-random-i00-privileged` | privileged | stack_blocks_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-blocks-random-i00-standard` | standard | stack_blocks_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-bowls-i00-privileged` | privileged | stack_bowls | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-bowls-i00-standard` | standard | stack_bowls | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-bowls-random-i00-privileged` | privileged | stack_bowls_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-stack-bowls-random-i00-standard` | standard | stack_bowls_random | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-store-laptop-and-headphones-i00-privileged` | privileged | store_laptop_and_headphones | 3600 s | none | no | core | allowlist | static |
| `robodojo-store-laptop-and-headphones-i00-standard` | standard | store_laptop_and_headphones | 3600 s | none | no | core | allowlist | static |
| `robodojo-store-laptop-and-headphones-random-i00-privileged` | privileged | store_laptop_and_headphones_random | 3600 s | none | no | core | allowlist | static |
| `robodojo-store-laptop-and-headphones-random-i00-standard` | standard | store_laptop_and_headphones_random | 3600 s | none | no | core | allowlist | static |
| `robodojo-store-tools-in-toolbox-i00-privileged` | privileged | store_tools_in_toolbox | 3600 s | none | no | core | allowlist | static |
| `robodojo-store-tools-in-toolbox-i00-standard` | standard | store_tools_in_toolbox | 3600 s | none | no | core | allowlist | static |
| `robodojo-swap-blocks-i00-privileged` | privileged | swap_blocks | 3600 s | none | no | core | allowlist | static |
| `robodojo-swap-blocks-i00-standard` | standard | swap_blocks | 3600 s | none | no | core | allowlist | static |
| `robodojo-swap-t-i00-privileged` | privileged | swap_T | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-swap-t-i00-standard` | standard | swap_T | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sweep-blocks-i00-privileged` | privileged | sweep_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sweep-blocks-i00-standard` | standard | sweep_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robodojo-sweep-blocks-random-i00-privileged` | privileged | sweep_blocks_random | 3600 s | none | no | core | allowlist | static |
| `robodojo-sweep-blocks-random-i00-standard` | standard | sweep_blocks_random | 3600 s | none | no | core | allowlist | static |

### roboEngineer

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `roboengineer-anycar-compact-lap-monaco-6-i00-standard` | standard | roboengineer/anycar-compact-lap-monaco-6 | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-anycar-compact-lap-monaco-6-i01-standard` | standard | roboengineer/anycar-compact-lap-monaco-6 | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-anycar-compact-lap-silverstone-8-i00-standard` | standard | roboengineer/anycar-compact-lap-silverstone-8 | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-anycar-compact-lap-silverstone-8-i01-standard` | standard | roboengineer/anycar-compact-lap-silverstone-8 | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-anycar-drift-park-i00-standard` | standard | roboengineer/anycar-drift-park | 14400 s | none | no | core | allowlist | static |
| `roboengineer-anycar-drift-park-i01-standard` | standard | roboengineer/anycar-drift-park | 14400 s | none | no | core | allowlist | static |
| `roboengineer-anycar-tight-drift-park-i00-standard` | standard | roboengineer/anycar-tight-drift-park | 14400 s | none | no | core | allowlist | static |
| `roboengineer-anycar-tight-drift-park-i01-standard` | standard | roboengineer/anycar-tight-drift-park | 14400 s | partial | no | core | allowlist | static |
| `roboengineer-anycar-tracking-i00-standard` | standard | roboengineer/anycar-tracking | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-anycar-tracking-i01-standard` | standard | roboengineer/anycar-tracking | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-g1-terrain-walk-i00-standard` | standard | roboengineer/g1-terrain-walk | 14400 s | partial | no | core | allowlist | static |
| `roboengineer-g1-terrain-walk-i01-standard` | standard | roboengineer/g1-terrain-walk | 14400 s | partial | no | core | allowlist | static |
| `roboengineer-go2-attitude-i00-standard` | standard | roboengineer/go2-attitude | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-go2-attitude-i01-standard` | standard | roboengineer/go2-attitude | 14400 s | full | yes | excluded | allowlist | static |
| `roboengineer-go2-forward-jump-i00-standard` | standard | roboengineer/go2-forward-jump | 14400 s | none | no | core | allowlist | static |
| `roboengineer-go2-forward-jump-i01-standard` | standard | roboengineer/go2-forward-jump | 14400 s | none | no | core | allowlist | static |
| `roboengineer-go2-weave-i00-standard` | standard | roboengineer/go2-weave | 14400 s | none | no | core | allowlist | static |
| `roboengineer-go2-weave-i01-standard` | standard | roboengineer/go2-weave | 14400 s | none | no | core | allowlist | static |
| `roboengineer-go2-yaw-jump-i00-standard` | standard | roboengineer/go2-yaw-jump | 14400 s | none | no | core | allowlist | static |
| `roboengineer-go2-yaw-jump-i01-standard` | standard | roboengineer/go2-yaw-jump | 14400 s | none | no | core | allowlist | static |
| `roboengineer-landing-random-pad-i00-standard` | standard | roboengineer/landing-random-pad | 3600 s | full | yes | core | allowlist | static |
| `roboengineer-landing-random-pad-i01-standard` | standard | roboengineer/landing-random-pad | 3600 s | full | yes | excluded | allowlist | static |
| `roboengineer-neuralfly-eight-i00-standard` | standard | roboengineer/neuralfly-eight | 14400 s | full | yes | excluded | allowlist | dynamic |
| `roboengineer-neuralfly-eight-i01-standard` | standard | roboengineer/neuralfly-eight | 14400 s | full | yes | excluded | allowlist | dynamic |
| `roboengineer-neuralfly-general-i00-standard` | standard | roboengineer/neuralfly-general | 14400 s | full | yes | excluded | allowlist | dynamic |
| `roboengineer-neuralfly-general-i01-standard` | standard | roboengineer/neuralfly-general | 14400 s | partial | no | core | allowlist | dynamic |
| `roboengineer-neuralfly-general-skydio-i00-standard` | standard | roboengineer/neuralfly-general-skydio | 14400 s | full | yes | excluded | allowlist | dynamic |
| `roboengineer-neuralfly-general-skydio-i01-standard` | standard | roboengineer/neuralfly-general-skydio | 14400 s | partial | no | core | allowlist | dynamic |
| `roboengineer-neuralfly-vector-wind-i00-standard` | standard | roboengineer/neuralfly-vector-wind | 14400 s | full | yes | excluded | allowlist | dynamic |
| `roboengineer-neuralfly-vector-wind-i01-standard` | standard | roboengineer/neuralfly-vector-wind | 14400 s | full | yes | excluded | allowlist | dynamic |

### RoboLab

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robolab-apple-and-yogurt-in-bowl-i00-privileged` | privileged | apple_and_yogurt_in_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-apple-and-yogurt-in-bowl-i00-standard` | standard | apple_and_yogurt_in_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-banana-in-bowl-i00-privileged` | privileged | banana_in_bowl | 3600 s | full | yes | excluded | allowlist | static |
| `robolab-banana-in-bowl-i00-standard` | standard | banana_in_bowl | 3600 s | full | yes | excluded | allowlist | static |
| `robolab-banana-then-rubiks-cube-i00-privileged` | privileged | banana_then_rubiks_cube | 3600 s | none | no | excluded | allowlist | static |
| `robolab-banana-then-rubiks-cube-i00-standard` | standard | banana_then_rubiks_cube | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bananas-in-bin-one-more-i00-privileged` | privileged | bananas_in_bin_one_more | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bananas-in-bin-one-more-i00-standard` | standard | bananas_in_bin_one_more | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bananas-in-bin-three-total-i00-privileged` | privileged | bananas_in_bin_three_total | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bananas-in-bin-three-total-i00-standard` | standard | bananas_in_bin_three_total | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bananas-out-of-bin-i00-privileged` | privileged | bananas_out_of_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bananas-out-of-bin-i00-standard` | standard | bananas_out_of_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-bbq-sauce-in-bin-i00-privileged` | privileged | bbq_sauce_in_bin | 3600 s | none | no | core | allowlist | static |
| `robolab-bbq-sauce-in-bin-i00-standard` | standard | bbq_sauce_in_bin | 3600 s | none | no | core | allowlist | static |
| `robolab-block-stacking-order-agnostic-i00-privileged` | privileged | block_stacking_order_agnostic | 3600 s | none | no | excluded | allowlist | static |
| `robolab-block-stacking-order-agnostic-i00-standard` | standard | block_stacking_order_agnostic | 3600 s | none | no | excluded | allowlist | static |
| `robolab-block-stacking-specified-order-i00-privileged` | privileged | block_stacking_specified_order | 3600 s | none | no | excluded | allowlist | static |
| `robolab-block-stacking-specified-order-i00-standard` | standard | block_stacking_specified_order | 3600 s | none | no | excluded | allowlist | static |
| `robolab-blocks-in-bin-i00-privileged` | privileged | blocks_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-blocks-in-bin-i00-standard` | standard | blocks_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-butter-above-raisin-i00-privileged` | privileged | butter_above_raisin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-butter-above-raisin-i00-standard` | standard | butter_above_raisin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-clutter-plastic-i00-privileged` | privileged | clutter_plastic | 3600 s | none | no | excluded | allowlist | static |
| `robolab-clutter-plastic-i00-standard` | standard | clutter_plastic | 3600 s | none | no | excluded | allowlist | static |
| `robolab-clutter-pumpkin-i00-privileged` | privileged | clutter_pumpkin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-clutter-pumpkin-i00-standard` | standard | clutter_pumpkin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-condiments-in-bin-i00-privileged` | privileged | condiments_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-condiments-in-bin-i00-standard` | standard | condiments_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-cooking-clear-plate-i00-privileged` | privileged | cooking_clear_plate | 3600 s | none | no | excluded | allowlist | static |
| `robolab-cooking-clear-plate-i00-standard` | standard | cooking_clear_plate | 3600 s | none | no | excluded | allowlist | static |
| `robolab-cubes-and-blocks-in-bin-i00-privileged` | privileged | cubes_and_blocks_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-cubes-and-blocks-in-bin-i00-standard` | standard | cubes_and_blocks_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-food-packing2-cans-i00-privileged` | privileged | food_packing2_cans | 3600 s | none | no | excluded | allowlist | static |
| `robolab-food-packing2-cans-i00-standard` | standard | food_packing2_cans | 3600 s | none | no | excluded | allowlist | static |
| `robolab-food-packing3-cans-i00-privileged` | privileged | food_packing3_cans | 3600 s | none | no | core | allowlist | static |
| `robolab-food-packing3-cans-i00-standard` | standard | food_packing3_cans | 3600 s | none | no | core | allowlist | static |
| `robolab-fruits-green-limes-on-plate-i00-privileged` | privileged | fruits_green_limes_on_plate | 3600 s | none | no | excluded | allowlist | static |
| `robolab-fruits-green-limes-on-plate-i00-standard` | standard | fruits_green_limes_on_plate | 3600 s | none | no | excluded | allowlist | static |
| `robolab-fruits-on-plate3-i00-privileged` | privileged | fruits_on_plate3 | 3600 s | none | no | excluded | allowlist | static |
| `robolab-fruits-on-plate3-i00-standard` | standard | fruits_on_plate3 | 3600 s | none | no | excluded | allowlist | static |
| `robolab-keyboard-out-of-bin-i00-privileged` | privileged | keyboard_out_of_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-keyboard-out-of-bin-i00-standard` | standard | keyboard_out_of_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-larger-object-raisin-box-in-bin-i00-privileged` | privileged | larger_object_raisin_box_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-larger-object-raisin-box-in-bin-i00-standard` | standard | larger_object_raisin_box_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-marker-in-mug-i00-privileged` | privileged | marker_in_mug | 3600 s | none | no | excluded | allowlist | static |
| `robolab-marker-in-mug-i00-standard` | standard | marker_in_mug | 3600 s | none | no | excluded | allowlist | static |
| `robolab-mustard-above-raisin-i00-privileged` | privileged | mustard_above_raisin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-mustard-above-raisin-i00-standard` | standard | mustard_above_raisin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-mustard-in-left-bin-i00-privileged` | privileged | mustard_in_left_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-mustard-in-left-bin-i00-standard` | standard | mustard_in_left_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-mustard-in-right-bin-i00-privileged` | privileged | mustard_in_right_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-mustard-in-right-bin-i00-standard` | standard | mustard_in_right_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-pick-glasses-i00-privileged` | privileged | pick_glasses | 3600 s | none | no | excluded | allowlist | static |
| `robolab-pick-glasses-i00-standard` | standard | pick_glasses | 3600 s | none | no | excluded | allowlist | static |
| `robolab-pick-orange-object-i00-privileged` | privileged | pick_orange_object | 3600 s | none | no | excluded | allowlist | static |
| `robolab-pick-orange-object-i00-standard` | standard | pick_orange_object | 3600 s | none | no | excluded | allowlist | static |
| `robolab-pick-up-blue-pitcher-i00-privileged` | privileged | pick_up_blue_pitcher | 3600 s | none | no | excluded | allowlist | static |
| `robolab-pick-up-blue-pitcher-i00-standard` | standard | pick_up_blue_pitcher | 3600 s | none | no | excluded | allowlist | static |
| `robolab-plastic-bottles-in-square-pail-i00-privileged` | privileged | plastic_bottles_in_square_pail | 3600 s | none | no | excluded | allowlist | static |
| `robolab-plastic-bottles-in-square-pail-i00-standard` | standard | plastic_bottles_in_square_pail | 3600 s | none | no | excluded | allowlist | static |
| `robolab-put-two-mugs-on-shelf-i00-privileged` | privileged | put_two_mugs_on_shelf | 3600 s | none | no | core | allowlist | static |
| `robolab-put-two-mugs-on-shelf-i00-standard` | standard | put_two_mugs_on_shelf | 3600 s | none | no | core | allowlist | static |
| `robolab-recycle-carton-i00-privileged` | privileged | recycle_carton | 3600 s | none | no | excluded | allowlist | static |
| `robolab-recycle-carton-i00-standard` | standard | recycle_carton | 3600 s | none | no | excluded | allowlist | static |
| `robolab-recycle-cartons-vertical-crate-i00-privileged` | privileged | recycle_cartons_vertical_crate | 3600 s | none | no | excluded | allowlist | static |
| `robolab-recycle-cartons-vertical-crate-i00-standard` | standard | recycle_cartons_vertical_crate | 3600 s | none | no | excluded | allowlist | static |
| `robolab-red-dishes-in-bin-i00-privileged` | privileged | red_dishes_in_bin | 3600 s | none | no | core | allowlist | static |
| `robolab-red-dishes-in-bin-i00-standard` | standard | red_dishes_in_bin | 3600 s | none | no | core | allowlist | static |
| `robolab-reorient-red-mug-i00-privileged` | privileged | reorient_red_mug | 3600 s | none | no | excluded | allowlist | static |
| `robolab-reorient-red-mug-i00-standard` | standard | reorient_red_mug | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-and-banana-i00-privileged` | privileged | rubiks_cube_and_banana | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-and-banana-i00-standard` | standard | rubiks_cube_and_banana | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-behind-bowl-i00-privileged` | privileged | rubiks_cube_behind_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-behind-bowl-i00-standard` | standard | rubiks_cube_behind_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-in-front-of-bowl-i00-privileged` | privileged | rubiks_cube_in_front_of_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-in-front-of-bowl-i00-standard` | standard | rubiks_cube_in_front_of_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-left-of-bowl-i00-privileged` | privileged | rubiks_cube_left_of_bowl | 3600 s | full | yes | excluded | allowlist | static |
| `robolab-rubiks-cube-left-of-bowl-i00-standard` | standard | rubiks_cube_left_of_bowl | 3600 s | full | yes | excluded | allowlist | static |
| `robolab-rubiks-cube-right-of-bowl-i00-privileged` | privileged | rubiks_cube_right_of_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-right-of-bowl-i00-standard` | standard | rubiks_cube_right_of_bowl | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-then-banana-i00-privileged` | privileged | rubiks_cube_then_banana | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cube-then-banana-i00-standard` | standard | rubiks_cube_then_banana | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cubes-in-bin-i00-privileged` | privileged | rubiks_cubes_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-rubiks-cubes-in-bin-i00-standard` | standard | rubiks_cubes_in_bin | 3600 s | none | no | excluded | allowlist | static |
| `robolab-spoon-in-mug-i00-privileged` | privileged | spoon_in_mug | 3600 s | none | no | excluded | allowlist | static |
| `robolab-spoon-in-mug-i00-standard` | standard | spoon_in_mug | 3600 s | none | no | excluded | allowlist | static |
| `robolab-stack-yellow-on-red-i00-privileged` | privileged | stack_yellow_on_red | 3600 s | none | no | excluded | allowlist | static |
| `robolab-stack-yellow-on-red-i00-standard` | standard | stack_yellow_on_red | 3600 s | none | no | excluded | allowlist | static |
| `robolab-stack3-rubiks-cube-i00-privileged` | privileged | stack3_rubiks_cube | 3600 s | none | no | excluded | allowlist | static |
| `robolab-stack3-rubiks-cube-i00-standard` | standard | stack3_rubiks_cube | 3600 s | none | no | excluded | allowlist | static |
| `robolab-take-measuring-spoon-out-i00-privileged` | privileged | take_measuring_spoon_out | 3600 s | none | no | excluded | allowlist | static |
| `robolab-take-measuring-spoon-out-i00-standard` | standard | take_measuring_spoon_out | 3600 s | none | no | excluded | allowlist | static |
| `robolab-take-mugs-off-of-shelf-i00-privileged` | privileged | take_mugs_off_of_shelf | 3600 s | none | no | excluded | allowlist | static |
| `robolab-take-mugs-off-of-shelf-i00-standard` | standard | take_mugs_off_of_shelf | 3600 s | none | no | excluded | allowlist | static |
| `robolab-take-spatula-off-shelf-i00-privileged` | privileged | take_spatula_off_shelf | 3600 s | none | no | excluded | allowlist | static |
| `robolab-take-spatula-off-shelf-i00-standard` | standard | take_spatula_off_shelf | 3600 s | none | no | excluded | allowlist | static |
| `robolab-throw-away-snacks-i00-privileged` | privileged | throw_away_snacks | 3600 s | none | no | excluded | allowlist | static |
| `robolab-throw-away-snacks-i00-standard` | standard | throw_away_snacks | 3600 s | none | no | excluded | allowlist | static |
| `robolab-tools-picking-drill-i00-privileged` | privileged | tools_picking_drill | 3600 s | none | no | excluded | allowlist | static |
| `robolab-tools-picking-drill-i00-standard` | standard | tools_picking_drill | 3600 s | none | no | excluded | allowlist | static |
| `robolab-unstack-rubiks-cube-i00-privileged` | privileged | unstack_rubiks_cube | 3600 s | none | no | excluded | allowlist | static |
| `robolab-unstack-rubiks-cube-i00-standard` | standard | unstack_rubiks_cube | 3600 s | none | no | excluded | allowlist | static |
| `robolab-utensils-in-mug-i00-privileged` | privileged | utensils_in_mug | 3600 s | none | no | core | allowlist | static |
| `robolab-utensils-in-mug-i00-standard` | standard | utensils_in_mug | 3600 s | none | no | core | allowlist | static |
| `robolab-white-mug-in-center-of-table-i00-privileged` | privileged | white_mug_in_center_of_table | 3600 s | none | no | core | allowlist | static |
| `robolab-white-mug-in-center-of-table-i00-standard` | standard | white_mug_in_center_of_table | 3600 s | none | no | core | allowlist | static |

### RoboPaint

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robopaint-acrylic-applesoranges-i00-privileged` | privileged | robopaint_acrylic_applesoranges | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-applesoranges-i00-standard` | standard | robopaint_acrylic_applesoranges | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-bedroom-i00-privileged` | privileged | robopaint_acrylic_bedroom | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-bedroom-i00-standard` | standard | robopaint_acrylic_bedroom | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-bluehorses-i00-privileged` | privileged | robopaint_acrylic_bluehorses | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-bluehorses-i00-standard` | standard | robopaint_acrylic_bluehorses | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-greatwave-i00-privileged` | privileged | robopaint_acrylic_greatwave | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-greatwave-i00-standard` | standard | robopaint_acrylic_greatwave | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-kajikazawa-i00-privileged` | privileged | robopaint_acrylic_kajikazawa | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-kajikazawa-i00-standard` | standard | robopaint_acrylic_kajikazawa | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-plumpark-i00-privileged` | privileged | robopaint_acrylic_plumpark | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-plumpark-i00-standard` | standard | robopaint_acrylic_plumpark | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-redfuji-i00-privileged` | privileged | robopaint_acrylic_redfuji | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-redfuji-i00-standard` | standard | robopaint_acrylic_redfuji | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-suddenshower-i00-privileged` | privileged | robopaint_acrylic_suddenshower | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-suddenshower-i00-standard` | standard | robopaint_acrylic_suddenshower | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-sunflowers-i00-privileged` | privileged | robopaint_acrylic_sunflowers | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-sunflowers-i00-standard` | standard | robopaint_acrylic_sunflowers | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-vision-i00-privileged` | privileged | robopaint_acrylic_vision | 3600 s | partial | no | core | allowlist | static |
| `robopaint-acrylic-vision-i00-standard` | standard | robopaint_acrylic_vision | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-beiquelindanshui-i00-privileged` | privileged | robopaint_caoshu_beiquelindanshui | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-beiquelindanshui-i00-standard` | standard | robopaint_caoshu_beiquelindanshui | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-nangong-i00-privileged` | privileged | robopaint_caoshu_nangong | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-caoshu-nangong-i00-standard` | standard | robopaint_caoshu_nangong | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-caoshu-siwushaonian-i00-privileged` | privileged | robopaint_caoshu_siwushaonian | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-siwushaonian-i00-standard` | standard | robopaint_caoshu_siwushaonian | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-wen-i00-privileged` | privileged | robopaint_caoshu_wen | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-caoshu-wen-i00-standard` | standard | robopaint_caoshu_wen | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-caoshu-zhen-i00-privileged` | privileged | robopaint_caoshu_zhen | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-zhen-i00-standard` | standard | robopaint_caoshu_zhen | 3600 s | partial | no | core | allowlist | static |
| `robopaint-caoshu-zhongtiangechuifen-i00-privileged` | privileged | robopaint_caoshu_zhongtiangechuifen | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-caoshu-zhongtiangechuifen-i00-standard` | standard | robopaint_caoshu_zhongtiangechuifen | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-kaishu-linfengguilong-i00-privileged` | privileged | robopaint_kaishu_linfengguilong | 3600 s | partial | no | core | allowlist | static |
| `robopaint-kaishu-linfengguilong-i00-standard` | standard | robopaint_kaishu_linfengguilong | 3600 s | partial | no | core | allowlist | static |
| `robopaint-kaishu-yongzibafa-i00-privileged` | privileged | robopaint_kaishu_yongzibafa | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-kaishu-yongzibafa-i00-standard` | standard | robopaint_kaishu_yongzibafa | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-aim-i00-privileged` | privileged | robopaint_lettering_aim | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-aim-i00-standard` | standard | robopaint_lettering_aim | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-business-i00-privileged` | privileged | robopaint_lettering_business | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-business-i00-standard` | standard | robopaint_lettering_business | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-commendation-i00-privileged` | privileged | robopaint_lettering_commendation | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-commendation-i00-standard` | standard | robopaint_lettering_commendation | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-diligence-i00-privileged` | privileged | robopaint_lettering_diligence | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-diligence-i00-standard` | standard | robopaint_lettering_diligence | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-liberty-i00-privileged` | privileged | robopaint_lettering_liberty | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-liberty-i00-standard` | standard | robopaint_lettering_liberty | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-virtue-i00-privileged` | privileged | robopaint_lettering_virtue | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-lettering-virtue-i00-standard` | standard | robopaint_lettering_virtue | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-bathers-i01-privileged` | privileged | robopaint_oil_bathers | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-bathers-i01-standard` | standard | robopaint_oil_bathers | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-cafeterrace-i01-privileged` | privileged | robopaint_oil_cafeterrace | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-cafeterrace-i01-standard` | standard | robopaint_oil_cafeterrace | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-cypresses-i01-privileged` | privileged | robopaint_oil_cypresses | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-cypresses-i01-standard` | standard | robopaint_oil_cypresses | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-irises-i01-privileged` | privileged | robopaint_oil_irises | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-irises-i01-standard` | standard | robopaint_oil_irises | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-milkmaid-i01-privileged` | privileged | robopaint_oil_milkmaid | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-milkmaid-i01-standard` | standard | robopaint_oil_milkmaid | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-monalisa-i01-privileged` | privileged | robopaint_oil_monalisa | 3600 s | partial | no | core | allowlist | static |
| `robopaint-oil-monalisa-i01-standard` | standard | robopaint_oil_monalisa | 3600 s | partial | no | core | allowlist | static |
| `robopaint-oil-pearlearring-i01-privileged` | privileged | robopaint_oil_pearlearring | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-pearlearring-i01-standard` | standard | robopaint_oil_pearlearring | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-saintevictoire-i01-privileged` | privileged | robopaint_oil_saintevictoire | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-saintevictoire-i01-standard` | standard | robopaint_oil_saintevictoire | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-starrynight-i01-privileged` | privileged | robopaint_oil_starrynight | 3600 s | partial | no | core | allowlist | static |
| `robopaint-oil-starrynight-i01-standard` | standard | robopaint_oil_starrynight | 3600 s | partial | no | core | allowlist | static |
| `robopaint-oil-temeraire-i01-privileged` | privileged | robopaint_oil_temeraire | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-temeraire-i01-standard` | standard | robopaint_oil_temeraire | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-wanderer-i01-privileged` | privileged | robopaint_oil_wanderer | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-oil-wanderer-i01-standard` | standard | robopaint_oil_wanderer | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-xingshu-feng-i00-privileged` | privileged | robopaint_xingshu_feng | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-feng-i00-standard` | standard | robopaint_xingshu_feng | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-he-i00-privileged` | privileged | robopaint_xingshu_he | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-he-i00-standard` | standard | robopaint_xingshu_he | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-huifenghechang-i00-privileged` | privileged | robopaint_xingshu_huifenghechang | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-huifenghechang-i00-standard` | standard | robopaint_xingshu_huifenghechang | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-maolinxiuzhu-i00-privileged` | privileged | robopaint_xingshu_maolinxiuzhu | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-maolinxiuzhu-i00-standard` | standard | robopaint_xingshu_maolinxiuzhu | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-nian-i00-privileged` | privileged | robopaint_xingshu_nian | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-xingshu-nian-i00-standard` | standard | robopaint_xingshu_nian | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-xingshu-shan-i00-privileged` | privileged | robopaint_xingshu_shan | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-xingshu-shan-i00-standard` | standard | robopaint_xingshu_shan | 3600 s | partial | no | excluded | allowlist | static |
| `robopaint-xingshu-xian-i00-privileged` | privileged | robopaint_xingshu_xian | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-xian-i00-standard` | standard | robopaint_xingshu_xian | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-yong-i00-privileged` | privileged | robopaint_xingshu_yong | 3600 s | partial | no | core | allowlist | static |
| `robopaint-xingshu-yong-i00-standard` | standard | robopaint_xingshu_yong | 3600 s | partial | no | core | allowlist | static |

### RoboTwin 2.0

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robotwin_2_0_adjust_bottle-privileged` | privileged | adjust_bottle | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_adjust_bottle-standard` | standard | adjust_bottle | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_beat_block_hammer-privileged` | privileged | beat_block_hammer | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_beat_block_hammer-standard` | standard | beat_block_hammer | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_blocks_ranking_rgb-privileged` | privileged | blocks_ranking_rgb | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_blocks_ranking_rgb-standard` | standard | blocks_ranking_rgb | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_blocks_ranking_size-privileged` | privileged | blocks_ranking_size | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_blocks_ranking_size-standard` | standard | blocks_ranking_size | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_dump_bin_bigbin-privileged` | privileged | dump_bin_bigbin | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_dump_bin_bigbin-standard` | standard | dump_bin_bigbin | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_grab_roller-privileged` | privileged | grab_roller | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_grab_roller-standard` | standard | grab_roller | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_handover_block-privileged` | privileged | handover_block | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_handover_block-standard` | standard | handover_block | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_handover_mic-privileged` | privileged | handover_mic | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_handover_mic-standard` | standard | handover_mic | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_hanging_mug-privileged` | privileged | hanging_mug | 1800 s | full | yes | core | allowlist | static |
| `robotwin_2_0_hanging_mug-standard` | standard | hanging_mug | 1800 s | full | yes | core | allowlist | static |
| `robotwin_2_0_lift_pot-privileged` | privileged | lift_pot | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_lift_pot-standard` | standard | lift_pot | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_can_pot-privileged` | privileged | move_can_pot | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_can_pot-standard` | standard | move_can_pot | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_pillbottle_pad-privileged` | privileged | move_pillbottle_pad | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_pillbottle_pad-standard` | standard | move_pillbottle_pad | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_playingcard_away-privileged` | privileged | move_playingcard_away | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_playingcard_away-standard` | standard | move_playingcard_away | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_stapler_pad-privileged` | privileged | move_stapler_pad | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_move_stapler_pad-standard` | standard | move_stapler_pad | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_open_laptop-privileged` | privileged | open_laptop | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_open_laptop-standard` | standard | open_laptop | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_open_microwave-privileged` | privileged | open_microwave | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_open_microwave-standard` | standard | open_microwave | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_pick_diverse_bottles-privileged` | privileged | pick_diverse_bottles | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_pick_diverse_bottles-standard` | standard | pick_diverse_bottles | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_pick_dual_bottles-privileged` | privileged | pick_dual_bottles | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_pick_dual_bottles-standard` | standard | pick_dual_bottles | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_a2b_left-privileged` | privileged | place_a2b_left | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_a2b_left-standard` | standard | place_a2b_left | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_a2b_right-privileged` | privileged | place_a2b_right | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_a2b_right-standard` | standard | place_a2b_right | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_bread_basket-privileged` | privileged | place_bread_basket | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_bread_basket-standard` | standard | place_bread_basket | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_bread_skillet-privileged` | privileged | place_bread_skillet | 1800 s | full | yes | core | allowlist | static |
| `robotwin_2_0_place_bread_skillet-standard` | standard | place_bread_skillet | 1800 s | full | yes | core | allowlist | static |
| `robotwin_2_0_place_burger_fries-privileged` | privileged | place_burger_fries | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_burger_fries-standard` | standard | place_burger_fries | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_can_basket-privileged` | privileged | place_can_basket | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_can_basket-standard` | standard | place_can_basket | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_cans_plasticbox-privileged` | privileged | place_cans_plasticbox | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_cans_plasticbox-standard` | standard | place_cans_plasticbox | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_container_plate-privileged` | privileged | place_container_plate | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_container_plate-standard` | standard | place_container_plate | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_dual_shoes-privileged` | privileged | place_dual_shoes | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_dual_shoes-standard` | standard | place_dual_shoes | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_empty_cup-privileged` | privileged | place_empty_cup | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_empty_cup-standard` | standard | place_empty_cup | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_fan-privileged` | privileged | place_fan | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_fan-standard` | standard | place_fan | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_mouse_pad-privileged` | privileged | place_mouse_pad | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_mouse_pad-standard` | standard | place_mouse_pad | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_object_basket-privileged` | privileged | place_object_basket | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_object_basket-standard` | standard | place_object_basket | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_object_scale-privileged` | privileged | place_object_scale | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_object_scale-standard` | standard | place_object_scale | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_object_stand-privileged` | privileged | place_object_stand | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_object_stand-standard` | standard | place_object_stand | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_phone_stand-privileged` | privileged | place_phone_stand | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_phone_stand-standard` | standard | place_phone_stand | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_shoe-privileged` | privileged | place_shoe | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_place_shoe-standard` | standard | place_shoe | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_press_stapler-privileged` | privileged | press_stapler | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_press_stapler-standard` | standard | press_stapler | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_put_bottles_dustbin-privileged` | privileged | put_bottles_dustbin | 1800 s | full | yes | core | allowlist | static |
| `robotwin_2_0_put_bottles_dustbin-standard` | standard | put_bottles_dustbin | 1800 s | full | yes | core | allowlist | static |
| `robotwin_2_0_rotate_qrcode-privileged` | privileged | rotate_qrcode | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_rotate_qrcode-standard` | standard | rotate_qrcode | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_scan_object-privileged` | privileged | scan_object | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_scan_object-standard` | standard | scan_object | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_shake_bottle-privileged` | privileged | shake_bottle | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_shake_bottle-standard` | standard | shake_bottle | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_shake_bottle_horizontally-privileged` | privileged | shake_bottle_horizontally | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_shake_bottle_horizontally-standard` | standard | shake_bottle_horizontally | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_blocks_three-privileged` | privileged | stack_blocks_three | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_blocks_three-standard` | standard | stack_blocks_three | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_blocks_two-privileged` | privileged | stack_blocks_two | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_blocks_two-standard` | standard | stack_blocks_two | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_bowls_three-privileged` | privileged | stack_bowls_three | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_bowls_three-standard` | standard | stack_bowls_three | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_bowls_two-privileged` | privileged | stack_bowls_two | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stack_bowls_two-standard` | standard | stack_bowls_two | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stamp_seal-privileged` | privileged | stamp_seal | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_stamp_seal-standard` | standard | stamp_seal | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_turn_switch-privileged` | privileged | turn_switch | 1800 s | full | yes | excluded | allowlist | static |
| `robotwin_2_0_turn_switch-standard` | standard | turn_switch | 1800 s | full | yes | excluded | allowlist | static |

### RoboWits

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `robowits-align-blocks-i00-privileged` | privileged | align_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robowits-align-blocks-i00-standard` | standard | align_blocks | 3600 s | none | no | excluded | allowlist | static |
| `robowits-ball-into-bottle-i00-privileged` | privileged | ball_into_bottle | 3600 s | none | no | core | allowlist | static |
| `robowits-ball-into-bottle-i00-standard` | standard | ball_into_bottle | 3600 s | none | no | core | allowlist | static |
| `robowits-ball-onto-tower-i00-privileged` | privileged | ball_onto_tower | 3600 s | none | no | excluded | allowlist | static |
| `robowits-ball-onto-tower-i00-standard` | standard | ball_onto_tower | 3600 s | none | no | excluded | allowlist | static |
| `robowits-collect-screws-i00-privileged` | privileged | collect_screws | 3600 s | none | no | excluded | allowlist | static |
| `robowits-collect-screws-i00-standard` | standard | collect_screws | 3600 s | none | no | excluded | allowlist | static |
| `robowits-cover-with-lid-i00-privileged` | privileged | cover_with_lid | 3600 s | none | no | core | allowlist | static |
| `robowits-cover-with-lid-i00-standard` | standard | cover_with_lid | 3600 s | none | no | core | allowlist | static |
| `robowits-dominos-i00-privileged` | privileged | dominos | 3600 s | partial | no | excluded | allowlist | static |
| `robowits-dominos-i00-standard` | standard | dominos | 3600 s | partial | no | excluded | allowlist | static |
| `robowits-gap-retrieve-i00-privileged` | privileged | gap_retrieve | 3600 s | none | no | excluded | allowlist | static |
| `robowits-gap-retrieve-i00-standard` | standard | gap_retrieve | 3600 s | none | no | excluded | allowlist | static |
| `robowits-hold-cup-i00-privileged` | privileged | hold_cup | 3600 s | none | no | excluded | allowlist | static |
| `robowits-hold-cup-i00-standard` | standard | hold_cup | 3600 s | none | no | excluded | allowlist | static |
| `robowits-move-cube-i00-privileged` | privileged | move_cube | 3600 s | none | no | excluded | allowlist | static |
| `robowits-move-cube-i00-standard` | standard | move_cube | 3600 s | none | no | excluded | allowlist | static |
| `robowits-raise-platform-i00-privileged` | privileged | raise_platform | 3600 s | none | no | excluded | allowlist | static |
| `robowits-raise-platform-i00-standard` | standard | raise_platform | 3600 s | none | no | excluded | allowlist | static |
| `robowits-retrieve-cube-i00-privileged` | privileged | retrieve_cube | 3600 s | none | no | core | allowlist | static |
| `robowits-retrieve-cube-i00-standard` | standard | retrieve_cube | 3600 s | none | no | core | allowlist | static |
| `robowits-stack-bowls-i00-privileged` | privileged | stack_bowls | 3600 s | none | no | core | allowlist | static |
| `robowits-stack-bowls-i00-standard` | standard | stack_bowls | 3600 s | none | no | core | allowlist | static |
| `robowits-stack-cubes-i00-privileged` | privileged | stack_cubes | 3600 s | partial | no | excluded | allowlist | static |
| `robowits-stack-cubes-i00-standard` | standard | stack_cubes | 3600 s | partial | no | excluded | allowlist | static |
| `robowits-stand-bulb-i00-privileged` | privileged | stand_bulb | 3600 s | none | no | core | allowlist | static |
| `robowits-stand-bulb-i00-standard` | standard | stand_bulb | 3600 s | none | no | core | allowlist | static |
| `robowits-stand-pages-i00-privileged` | privileged | stand_pages | 3600 s | none | no | core | allowlist | static |
| `robowits-stand-pages-i00-standard` | standard | stand_pages | 3600 s | none | no | core | allowlist | static |

### VLABench

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `vlabench-add-condiment-i00-privileged` | privileged | vlabench/add_condiment | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-add-condiment-i00-standard` | standard | vlabench/add_condiment | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-book-rearrange-i00-privileged` | privileged | vlabench/book_rearrange | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-book-rearrange-i00-standard` | standard | vlabench/book_rearrange | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-find-unseen-object-i00-privileged` | privileged | vlabench/find_unseen_object | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-find-unseen-object-i00-standard` | standard | vlabench/find_unseen_object | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-friction-qa-i00-privileged` | privileged | vlabench/friction_qa | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-friction-qa-i00-standard` | standard | vlabench/friction_qa | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-hammer-nail-and-hang-picture-i00-privileged` | privileged | vlabench/hammer_nail_and_hang_picture | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-hammer-nail-and-hang-picture-i00-standard` | standard | vlabench/hammer_nail_and_hang_picture | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-heat-food-i00-privileged` | privileged | vlabench/heat_food | 1800 s | full | yes | core | allowlist | static |
| `vlabench-heat-food-i00-standard` | standard | vlabench/heat_food | 1800 s | full | yes | core | allowlist | static |
| `vlabench-insert-bloom-flower-i00-privileged` | privileged | vlabench/insert_bloom_flower | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-insert-bloom-flower-i00-standard` | standard | vlabench/insert_bloom_flower | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-insert-flower-i00-privileged` | privileged | vlabench/insert_flower | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-insert-flower-i00-standard` | standard | vlabench/insert_flower | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-magnetism-qa-i00-privileged` | privileged | vlabench/magnetism_qa | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-magnetism-qa-i00-standard` | standard | vlabench/magnetism_qa | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-play-math-game-i00-privileged` | privileged | vlabench/play_math_game | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-play-math-game-i00-standard` | standard | vlabench/play_math_game | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-put-box-on-painting-i00-privileged` | privileged | vlabench/put_box_on_painting | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-put-box-on-painting-i00-standard` | standard | vlabench/put_box_on_painting | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-reflection-qa-i00-privileged` | privileged | vlabench/reflection_qa | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-reflection-qa-i00-standard` | standard | vlabench/reflection_qa | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-billiards-common-sense-i00-privileged` | privileged | vlabench/select_billiards_common_sense | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-billiards-common-sense-i00-standard` | standard | vlabench/select_billiards_common_sense | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-billiards-i00-privileged` | privileged | vlabench/select_billiards | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-billiards-i00-standard` | standard | vlabench/select_billiards | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-billiards-spatial-i00-privileged` | privileged | vlabench/select_billiards_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-billiards-spatial-i00-standard` | standard | vlabench/select_billiards_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-book-spatial-i00-privileged` | privileged | vlabench/select_book_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-book-spatial-i00-standard` | standard | vlabench/select_book_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-common-sense-i00-privileged` | privileged | vlabench/select_chemistry_tube_common_sense | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-common-sense-i00-standard` | standard | vlabench/select_chemistry_tube_common_sense | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-i00-privileged` | privileged | vlabench/select_chemistry_tube | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-i00-standard` | standard | vlabench/select_chemistry_tube | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-semantic-i00-privileged` | privileged | vlabench/select_chemistry_tube_semantic | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-semantic-i00-standard` | standard | vlabench/select_chemistry_tube_semantic | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-spatial-i00-privileged` | privileged | vlabench/select_chemistry_tube_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-chemistry-tube-spatial-i00-standard` | standard | vlabench/select_chemistry_tube_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-drink-i00-privileged` | privileged | vlabench/select_drink | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-drink-i00-standard` | standard | vlabench/select_drink | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-fruit-common-sense-i00-privileged` | privileged | vlabench/select_fruit_common_sense | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-fruit-common-sense-i00-standard` | standard | vlabench/select_fruit_common_sense | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-fruit-i00-privileged` | privileged | vlabench/select_fruit | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-fruit-i00-standard` | standard | vlabench/select_fruit | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-mahjong-i00-privileged` | privileged | vlabench/select_mahjong | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-mahjong-i00-standard` | standard | vlabench/select_mahjong | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-mahjong-semantic-i00-privileged` | privileged | vlabench/select_mahjong_semantic | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-mahjong-semantic-i00-standard` | standard | vlabench/select_mahjong_semantic | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-mahjong-spatial-i00-privileged` | privileged | vlabench/select_mahjong_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-mahjong-spatial-i00-standard` | standard | vlabench/select_mahjong_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-nth-largest-poker-i00-privileged` | privileged | vlabench/select_nth_largest_poker | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-nth-largest-poker-i00-standard` | standard | vlabench/select_nth_largest_poker | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-painting-i00-privileged` | privileged | vlabench/select_painting | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-painting-i00-standard` | standard | vlabench/select_painting | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-poker-i00-privileged` | privileged | vlabench/select_poker | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-poker-i00-standard` | standard | vlabench/select_poker | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-poker-semantic-i00-privileged` | privileged | vlabench/select_poker_semantic | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-poker-semantic-i00-standard` | standard | vlabench/select_poker_semantic | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-poker-spatial-i00-privileged` | privileged | vlabench/select_poker_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-poker-spatial-i00-standard` | standard | vlabench/select_poker_spatial | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-specific-type-book-i00-privileged` | privileged | vlabench/select_specific_type_book | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-specific-type-book-i00-standard` | standard | vlabench/select_specific_type_book | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-toy-i00-privileged` | privileged | vlabench/select_toy | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-toy-i00-standard` | standard | vlabench/select_toy | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-unique-type-mahjong-i00-privileged` | privileged | vlabench/select_unique_type_mahjong | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-select-unique-type-mahjong-i00-standard` | standard | vlabench/select_unique_type_mahjong | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-take-out-cool-drink-i00-privileged` | privileged | vlabench/take_out_cool_drink | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-take-out-cool-drink-i00-standard` | standard | vlabench/take_out_cool_drink | 1800 s | full | yes | excluded | allowlist | static |
| `vlabench-texas-holdem-i00-privileged` | privileged | vlabench/texas_holdem | 1800 s | full | yes | core | allowlist | static |
| `vlabench-texas-holdem-i00-standard` | standard | vlabench/texas_holdem | 1800 s | full | yes | core | allowlist | static |

### YAMLab

| Task | Mode | Family | Cutoff | Oracle | Validated | Set | Network | Dynamics |
|---|---|---|---|---|---|---|---|---|
| `yamlab-hang-mug-on-tree-i10-privileged` | privileged | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i10-standard` | standard | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i13-privileged` | privileged | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i13-standard` | standard | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i15-privileged` | privileged | hang_mug_on_tree | 3600 s | full | yes | core | allowlist | static |
| `yamlab-hang-mug-on-tree-i15-standard` | standard | hang_mug_on_tree | 3600 s | full | yes | core | allowlist | static |
| `yamlab-hang-mug-on-tree-i20-privileged` | privileged | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i20-standard` | standard | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i21-privileged` | privileged | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-hang-mug-on-tree-i21-standard` | standard | hang_mug_on_tree | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i00-privileged` | privileged | put_pot_on_cooktop | 3600 s | full | yes | core | allowlist | static |
| `yamlab-put-pot-on-cooktop-i00-standard` | standard | put_pot_on_cooktop | 3600 s | full | yes | core | allowlist | static |
| `yamlab-put-pot-on-cooktop-i03-privileged` | privileged | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i03-standard` | standard | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i04-privileged` | privileged | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i04-standard` | standard | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i07-privileged` | privileged | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i07-standard` | standard | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i08-privileged` | privileged | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
| `yamlab-put-pot-on-cooktop-i08-standard` | standard | put_pot_on_cooktop | 3600 s | full | yes | excluded | allowlist | static |
