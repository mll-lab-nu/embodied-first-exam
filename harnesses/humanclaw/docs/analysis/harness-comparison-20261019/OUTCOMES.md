# Recorded outcomes and paired comparisons

All figures below describe the selected completed-task population. They are not first-attempt reliability estimates. See [Methods](METHODS.md) for run selection, uncertainty, and causal limits.

## Outcomes by condition

| Condition | Completed tasks | Overall success | Navigation success | Interaction success | Mean actions | At least 100 actions |
|---|---:|---:|---:|---:|---:|---:|
| PSV Astra r1 | 1218 | 579 (47.54%) | 313/621 (50.40%) | 266/597 (44.56%) | 60.46 | 378 |
| Codex Astra r1 | 1218 | 460 (37.77%) | 435/621 (70.05%) | 25/597 (4.19%) | 37.31 | 56 |
| Pi Astra r1 | 1218 | 465 (38.18%) | 455/621 (73.27%) | 10/597 (1.68%) | 35.77 | 50 |
| Codex Astra r2 | 1218 | 669 (54.93%) | 450/621 (72.46%) | 219/597 (36.68%) | 41.70 | 63 |
| Pi Astra r2 | 1218 | 676 (55.50%) | 471/621 (75.85%) | 205/597 (34.34%) | 41.22 | 52 |
| Codex Astra r3 (max) | 1218 | 782 (64.20%) | 466/621 (75.04%) | 316/597 (52.93%) | 43.90 | 100 |
| Pi Astra r3 (xhigh) | 1218 | 798 (65.52%) | 472/621 (76.01%) | 326/597 (54.61%) | 45.64 | 94 |
| Codex Gemini | 1217 | 726 (59.65%) | 461/620 (74.35%) | 265/597 (44.39%) | 37.48 | 79 |
| Pi Gemini | 1217 | 667 (54.81%) | 448/620 (72.26%) | 219/597 (36.68%) | 34.90 | 52 |

Gemini has 1,217 common completed tasks, including 620 navigation and 597 interaction tasks. The other conditions have 1,218 tasks, including 621 navigation and 597 interaction tasks. The missing Gemini task is not silently assigned a success/failure outcome.

## Within-condition Codex–Pi pairing

Differences and confidence intervals below are Pi minus Codex, in percentage points. The intervals resample scenes, preserving pairing.

| Pair | Both succeed | Codex only | Pi only | Both fail | Difference | 95% scene-cluster interval | Exploratory exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|
| r1 | 402 | 58 | 63 | 695 | +0.41 pp | [-1.71, 2.47] | 0.716294 |
| r2 | 527 | 142 | 149 | 400 | +0.57 pp | [-2.54, 3.85] | 0.72511 |
| r3 | 637 | 145 | 161 | 275 | +1.31 pp | [-1.55, 4.11] | 0.391207 |
| gemini | 561 | 165 | 106 | 385 | -4.85 pp | [-7.20, -2.62] | 0.000406508 |

The three Astra intervals include zero. This does not prove equivalence, but these observations do not establish a consistent Pi success-rate advantage. Gemini favors Codex in this recorded configuration. The effort labels, image policies, provider route, and source changes limit causal cross-condition interpretation.

### Navigation and interaction explain different parts of the aggregate

| Pair | Pi minus Codex: navigation successes | Pi minus Codex: interaction successes | Net successes |
|---|---:|---:|---:|
| r1 | +20 | -15 | +5 |
| r2 | +21 | -14 | +7 |
| r3 | +6 | +10 | +16 |
| gemini | -13 | -46 | -59 |

In r2, Pi gains 21 navigation successes but loses 14 interaction successes, leaving only seven net additional successes. In Gemini, 46 of the 59 net Codex successes come from interaction tasks. Overall scores conceal these different behavior profiles.

## Action semantics and sitting behavior

The native r1 protocol lacks the explicit fact that one Sit call advances only about 0.5 seconds. The r2 protocol adds that fact and clarifies that Stop submits the current pose and terminates the episode. PSV v4 already instructs a 3–4-chunk sitting sequence. The actual request definitions confirm that only Sit and Stop wording changes among the eight tools. Source comparison identifies this as the principal task-facing r1-to-r2 change; the other audited changes mainly concern provenance and higher effort mapping, which leaves medium unchanged. The original r1 cohort's different image policy remains a comparison caveat.

| Condition | Interaction tasks with no Sit | Exactly one Sit | At least two Sit calls | Total Sit calls in interaction tasks | Interaction successes |
|---|---:|---:|---:|---:|---:|
| PSV Astra r1 | 149 | 1 | 447 | 1421 | 266 |
| Codex Astra r1 | 45 | 487 | 65 | 637 | 25 |
| Pi Astra r1 | 50 | 468 | 79 | 655 | 10 |
| Codex Astra r2 | 39 | 15 | 543 | 1548 | 219 |
| Pi Astra r2 | 44 | 14 | 539 | 1695 | 205 |
| Codex Astra r3 (max) | 51 | 3 | 543 | 1919 | 316 |
| Pi Astra r3 (xhigh) | 39 | 9 | 549 | 1969 | 326 |
| Codex Gemini | 32 | 7 | 558 | 1361 | 265 |
| Pi Gemini | 36 | 3 | 558 | 1289 | 219 |

Codex r1-to-r2 adds 209 overall successes: 194 interaction and 15 navigation. Pi adds 211: 195 interaction and 16 navigation. Thus 92.82% and 92.42% of their respective net gains are interaction gains. This is strong prioritization evidence for action-duration and completion semantics, not a randomized estimate of a prompt component effect.

## Higher delivered reasoning effort

| Comparison | Earlier only | Later only | Net gain | 95% scene-cluster interval |
|---|---:|---:|---:|---:|
| Codex Astra r2 → Codex Astra r3 (max) | 109 | 222 | +9.28 pp | [6.14, 12.52] |
| Pi Astra r2 → Pi Astra r3 (xhigh) | 107 | 229 | +10.02 pp | [6.97, 12.93] |

Codex adds 97 interaction and 16 navigation successes; Pi adds 121 interaction and one navigation success. The r3 gains are therefore concentrated in interaction again. Actual request effort is `max` for Codex and `xhigh` for Pi; these values are not assumed to represent equal provider computation. There are no repeated identical-configuration trials here to separate sampling variability from stable changes.

## Terminal failure facts

[terminal_outcomes.csv](tables/terminal_outcomes.csv) partitions every selected task into a success or a terminal condition supported by metrics. These are endpoint diagnoses, not complete causal explanations. In particular, “no valid sit contact recorded” does not by itself distinguish wrong seat alignment, incomplete lowering, wrong object, or a misleading image interpretation.

Navigation success requires an active stop within the distance threshold. Interaction success requires active stop, at least one Sit, and appropriate final pelvis/target contact. A historical successful Sit contact does not guarantee that the final committed pose still satisfies the criterion.

## Tables

- [All 10,960 episode outcomes](tables/episode_outcomes.csv) with remote metrics paths.
- [Paired success and uncertainty](tables/paired_success.csv).
- [Outcomes by task type, object category, and scene](tables/stratified_outcomes.csv).
- [Sitting behavior](tables/sit_behavior.csv).
- [Terminal outcome partition](tables/terminal_outcomes.csv).
