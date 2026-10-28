# P2 — Token, action, and latency efficiency

## Final-cohort resource accounting

All token totals below are **known subtotals**, covering every selected completed episode, whether or not it succeeds. Input already includes cached input; output already includes the recorded reasoning subset. Do not add cached or reasoning columns again. Missing usage is not imputed as zero. There is no versioned pricing record, so these are not dollar costs.

| Condition | Model calls | Input (M) | Cached input (M) | Uncached input (M) | Output (M) | Reasoning subset (M) | Calls missing input usage | Mean wall time (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PSV r1 | 123,047 | 319.652 | 1.155 | 318.497 | 29.986 | 6.118 | 28 | 1,444.6 |
| Codex r1 | 46,781 | 1,025.749 | 795.530 | 230.220 | 4.113 | 0.254 | 88 | 664.2 |
| Pi r1 | 44,956 | 568.098 | 376.068 | 192.030 | 3.904 | 0.310 | 170 | 600.3 |
| Codex r2 | 52,060 | 1,196.753 | 896.362 | 300.391 | 4.704 | 0.384 | 11 | 636.8 |
| Pi r2 | 51,465 | 704.432 | 454.322 | 250.110 | 4.591 | 0.459 | 46 | 583.1 |
| Codex r3 max | 55,056 | 1,478.553 | 1,045.056 | 433.497 | 12.264 | 6.844 | 352 | 1,143.0 |
| Pi r3 xhigh | 57,147 | 857.085 | 503.194 | 353.891 | 10.427 | 4.951 | 343 | 967.3 |
| Codex Gemini | 48,468 | 1,451.459 | 746.107 | 705.353 | 4.319 | 0.000 | 83 | 749.8 |
| Pi Gemini | 47,286 | 897.353 | 373.740 | 523.613 | 4.113 | 0.000 | 75 | 719.2 |


The full final cohort contains 526,266 model calls. Failed request usage is included where supplied. Native calls are observed at the HTTP boundary; PSV adapter calls do not expose all provider-internal attempts. Token units also differ across model families.

Pi's total input volume is lower in all four native comparisons. In r2, it is **704.43M versus 1,196.75M**, a **41.14%** reduction. Uncached input is **250.11M versus 300.39M**, a smaller **16.74%** reduction. Much of the gross input gap concerns cached prefix/history exposure. This distinction materially changes the interpretation of “cheaper.”

## Both-success paired efficiency

Only tasks where both harnesses succeed enter this table. Action and wall-time columns use every such pair; token columns exclude pairs with incomplete usage on either side. Percentages are changes in paired-subset means, **Pi relative to Codex**, not averages of per-episode percentage ratios.

| Pair | Both-success pairs | Codex mean actions | Pi mean actions | Complete token pairs | Input change | Uncached-input change | Output change | Wall-time change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r1 | 402 | 27.80 | 26.52 | 361 | -50.58% | -17.68% | -6.22% | -9.89% |
| r2 | 527 | 32.75 | 31.83 | 511 | -46.02% | -17.73% | -4.49% | -9.39% |
| r3 | 637 | 35.26 | 36.85 | 560 | -45.04% | -7.97% | -21.09% | -16.03% |
| gemini | 561 | 28.58 | 27.53 | 548 | -38.44% | -22.73% | -1.69% | -2.29% |


Median paired action differences are −1, −1, −1, and 0 for r1, r2, r3, and Gemini. The positive r3 **mean** difference, +1.59 actions, shows why both location summaries matter: Pi's tail outweighs its small median advantage.

Scene-cluster 95% intervals, 10,000 resamples:

| Pair | Action-count delta CI | Input-token change CI | Uncached-input change CI |
| --- | --- | --- | --- |
| r1 | [-2.02, -0.56] actions | [-54.19, -47.03]% | [-41.76, 6.42]% |
| r2 | [-2.03, 0.13] actions | [-49.52, -42.60]% | [-33.68, 0.02]% |
| r3 | [0.24, 2.98] actions | [-49.38, -40.57]% | [-28.16, 17.61]% |
| gemini | [-1.96, -0.13] actions | [-41.45, -35.40]% | [-27.01, -18.26]% |


The total-input reduction is stable across the observed scenes. The Astra uncached-input intervals include zero, including the narrow r2 upper bound near zero. Therefore the point-estimate uncached savings should not be described as a proven universal cost improvement. Gemini's observed uncached reduction is clearer in this subset, while Codex still has higher overall Gemini success.

Common-success selection favors episodes both systems can solve. It does not replace the all-episode table or establish equal quality. Wall time also reflects provider load, queueing, cache behavior, and environment execution; this historical comparison does not isolate harness CPU overhead.

## How much can be attributed to prompt size?

Full-census first-request input medians:

| Condition | First-request input median |
| --- | --- |
| PSV r1 | 1,996 |
| Codex r1 | 11,271 |
| Pi r1 | 2,743 |
| Codex r2 | 11,344 |
| Pi r2 | 2,801 |
| Codex r3 max | 11,351 |
| Pi r3 xhigh | 2,803 |
| Codex Gemini | 14,483 |
| Pi Gemini | 4,330 |


For Astra r2, Codex starts around **8,543 tokens above Pi** before any action history. The raw request audit independently shows much longer system/developer text and more generic tool text. This is strong evidence for a baseline request-size burden, but not a causal decomposition: schema format, native wrappers, tokenizer behavior, and other request fields also differ.

Identical complete action chains are rare: **2 r1, 3 r2, 2 r3, and 2 Gemini pairs**. Their initial saved poses and final outcomes agree. On those nine pairs, average input is consistently lower for Pi; r2 means are **119,263 versus 41,804 tokens**. The sample is far too small to estimate a general effect, but it illustrates the request burden with action count held fixed. See [identical_action_chains.csv](tables/identical_action_chains.csv).

## Higher effort changes the resource profile

Codex r2→r3 gains 9.28 success points while mean wall time rises **636.8→1,143.0 seconds** and recorded reasoning tokens **0.384M→6.844M**. Pi gains 10.02 points while wall time rises **583.1→967.3 seconds** and reasoning tokens **0.459M→4.951M**.

The two r3 effort labels are different. These observations motivate a controlled effort/latency frontier rather than assuming “max” and “xhigh” provide equal inference computation. They also suggest that the remaining interaction problem benefits from more deliberation under these recorded settings, without proving a particular internal reasoning mechanism.

## PSV changes both request count and request content

PSV has fewer input tokens than the native Astra cohorts, but **29.99M output tokens**, compared with **4.70M Codex r2** and **4.59M Pi r2**, and mean wall time **1,444.6 seconds**. Its task-specific planner and conditional verifier generate far more text and approximately 1.67 calls per decision. Smaller input does not imply lower total cost or better latency.

The verifier runs on 67.05% of decisions but overrides 8.49% of its calls. This is useful evidence for investigating selective checks, not proof that the remaining calls are unnecessary: a no-change decision could still be useful. No verifier ablation was performed.

## Saved-motion efficiency

Horizontal path summaries and physical seconds are in [trajectory_summary.csv](tables/trajectory_summary.csv) and [trajectory_features.csv](tables/trajectory_features.csv). These are realized motion measures, not shortest-path efficiency or successful contact. Low-displacement Walk and turn-reversal counts are descriptive flags, not automatically “stuck” or “looping” failures.

## Supporting tables

- [Per-episode costs](tables/episode_costs.csv), including usage coverage and timing boundaries.
- [Both-success statistics](tables/both_success_efficiency.csv), including medians and within-harness phase comparisons.
- [Scene-cluster efficiency intervals](tables/efficiency_intervals.csv).
- [All recorded-attempt costs](tables/attempt_summary.csv), separate from canonical outcomes.
