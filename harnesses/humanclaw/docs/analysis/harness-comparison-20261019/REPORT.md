# HumanCLAW harness comparison: evidence for an embodied harness

**Historical rollout analysis, October 19–20, 2026.** Scope: PSV Astra r1; Codex and Pi Astra r1/r2/r3; Codex and Pi Gemini. Codex r3 uses `max`; Pi r3 uses `xhigh`.

The analysis covers **10,960 final episodes**, **12,997 recorded attempts**, **460,783 executed environment actions**, and **526,266 model calls in the final episodes**. It uses existing server results and writes derived reports locally. No experiment code, configuration, or original data was modified; no rollout, inference, simulation, or new scene rendering was run. The reusable skill is deferred.

## Main findings

**1. r1→r2 is principally an action-description change, and the behavior supports that explanation.** Actual requests change only the Sit and Stop descriptions among the eight tools. Sit now explicitly says one call advances about 0.5 seconds and may not complete sitting; Stop explicitly commits the final pose and terminates the episode. Other audited source changes mainly improve runtime provenance and higher-effort mapping; medium remains unchanged.

Codex gains **209 successes**, including **194 interaction successes**; Pi gains **211**, including **195 interactions**. Thus roughly **93% of each net gain comes from interaction**. Exactly-one-Sit interaction episodes fall **487→15** for Codex and **468→14** for Pi. Adjacent Sit→Sit transitions rise **0→859** and **0→804**. The gain persists among tasks whose r1 and r2 image windows are both 50: interaction success rises **8/191→68/191** for Codex and **5/187→54/187** for Pi.

This is strong mechanism-consistent evidence for the tool-description hypothesis. It is not a randomized separation of Sit wording, Stop wording, or all historical execution differences. [Details and source comparison](PROMPTS_AND_CONTEXT.md).

**2. The data do not show a consistent Pi success advantage across models.** The three Astra Codex–Pi success differences are small and their scene-cluster intervals include zero. Gemini favors Codex by **4.85 percentage points**. Choosing Pi as a base is better supported by its compact request footprint than by a claim of universal task superiority.

**3. Pi's clearest measured advantage is input-token efficiency.** On r2 tasks both harnesses solve, Pi uses **46.02% fewer input tokens**, **17.73% fewer uncached input tokens**, and **4.49% fewer output tokens**, on pairs with complete usage. It uses only **0.92 fewer actions on average** across all common-success pairs. The first-request input median is **11,344 tokens for Codex versus 2,801 for Pi**, before trajectory length can explain the gap. Astra uncached-input uncertainty intervals include zero, so the gross-input advantage should not be equated with a proven dollar-cost advantage. [Efficiency analysis](EFFICIENCY.md).

**4. The native harness actively manages the model/tool loop even when generic tools are unused.** It assembles requests, maintains conversation history, dispatches MCP calls, waits for results, continues the loop, and handles native lifecycle/retry events. HumanCLAW supplies the action contract, image-window policy, validation, physical environment, and metrics. These roles should be attributed separately.

Generic native tools are unused in Codex r1/r2 and all Pi cohorts. Later Codex exceptions are **12 confirmed native plan updates in three r3 episodes** and **one failed shell-tool attempt in Gemini**. No native compaction execution is recorded. [Full tool counts and call chains](TOOL_CALLS.md).

**5. Better action descriptions do not finish the interaction problem.** Both Astra r3 harnesses still have **209 stopped interaction episodes with no valid sitting contact recorded**. Reviewed cases show seated-looking images and repeated Sit calls on both sides of a success/failure pair. The remaining candidates include target grounding, support alignment, height, recovery, and premature commitment. They require evidence-sensitive progress and completion logic, not merely more tool calls. [Trajectory findings](TRAJECTORY_FINDINGS.md).

## Outcomes at a glance

| Condition | Final tasks | Overall success | Navigation success | Interaction success | Mean actions |
|---|---:|---:|---:|---:|---:|
| PSV Astra r1 | 1,218 | 47.54% | 50.40% | 44.56% | 60.46 |
| Codex Astra r1 | 1,218 | 37.77% | 70.05% | 4.19% | 37.31 |
| Pi Astra r1 | 1,218 | 38.18% | 73.27% | 1.68% | 35.77 |
| Codex Astra r2 | 1,218 | 54.93% | 72.46% | 36.68% | 41.70 |
| Pi Astra r2 | 1,218 | 55.50% | 75.85% | 34.34% | 41.22 |
| Codex Astra r3, max | 1,218 | 64.20% | 75.04% | 52.93% | 43.90 |
| Pi Astra r3, xhigh | 1,218 | 65.52% | 76.01% | 54.61% | 45.64 |
| Codex Gemini | 1,217 | 59.65% | 74.35% | 44.39% | 37.48 |
| Pi Gemini | 1,217 | 54.81% | 72.26% | 36.68% | 34.90 |

Gemini excludes the same missing completed task in both harnesses: shard-0184, scene `102816600`, episode 6, chair navigation. Native r1 combines complementary original and `imgwin50` continuation cohorts.

| Comparison | Both succeed | Codex only | Pi only | Both fail | Pi − Codex success | 95% scene-cluster interval |
|---|---:|---:|---:|---:|---:|---|
| Astra r1 | 402 | 58 | 63 | 695 | +0.41 pp | [−1.71, 2.47] |
| Astra r2 | 527 | 142 | 149 | 400 | +0.57 pp | [−2.54, 3.85] |
| Astra r3 | 637 | 145 | 161 | 275 | +1.31 pp | [−1.55, 4.11] |
| Gemini | 561 | 165 | 106 | 385 | −4.85 pp | [−7.20, −2.62] |

Intervals use 10,000 scene-cluster bootstrap resamples with paired tasks preserved. They describe uncertainty over the observed scenes, not repeated-run variability at identical model settings. An interval containing zero is not evidence of equivalence.

## What to build and test next

Use a compact native loop as the implementation baseline, with explicit components for:

1. **Action semantics:** duration, partial completion, legal parameters, and terminal Stop.
2. **Observation and progress state:** current image, selected history, observed target identity, task stage, and failed approaches.
3. **Completion checks:** uncertainty-aware target/contact/support assessment using only permitted observations.
4. **Provider adaptation and recovery:** effective effort/tool/image capabilities, bounded retries, and idempotent physical actions.
5. **Auditable accounting:** actual delivered requests, usage coverage, lifecycle events, and pinned source/runtime identities.

The first controlled experiments should separate Sit/Stop wording, then separate system-prompt/tool-catalog overhead from the remaining native loop, then test interaction progress and selective completion checks. Memory policy, target grounding, provider compatibility, and optional verification follow as explicit factors. The full ranked queue, controls, metrics, and research to-do list are in [DESIGN_AND_NEXT_STEPS.md](DESIGN_AND_NEXT_STEPS.md).

## Completed analysis packages

| Package | Deliverable | Coverage |
|---|---|---|
| P0 | [Cohort and provenance audit](REGISTRY.md) | All final episodes and recorded attempts; actual configuration and source fingerprints |
| P1 | [Outcomes and paired comparisons](OUTCOMES.md) | Task/scene/category tables, outcome quadrants, uncertainty, Sit behavior |
| P2 | [Efficiency](EFFICIENCY.md) | All-episode and common-success actions, input/output/cache/reasoning, latency |
| P3 | [Tool calls](TOOL_CALLS.md), [prompts and context](PROMPTS_AND_CONTEXT.md) | Full capability census; 209 primary raw-trace audits plus six focused audits |
| P4 | [Trajectory findings](TRAJECTORY_FINDINGS.md) | All saved action chains; 80 paired case cards; 24 image-reviewed pairs |
| P5 | [Design and next steps](DESIGN_AND_NEXT_STEPS.md) | Evidence-ranked components and controlled ablation plan |

Read [METHODS.md](METHODS.md) for definitions and interpretation limits.

## Evidence index

The primary tables remain directly readable as CSV:

- [Episode outcomes](tables/episode_outcomes.csv), [costs](tables/episode_costs.csv), and [trajectory features](tables/trajectory_features.csv).
- [Recorded attempts](tables/attempts.csv), [suite registry](tables/suite_registry.csv), and [configuration variants](tables/configuration_variants.csv).
- [Paired success](tables/paired_success.csv), [common-success efficiency](tables/both_success_efficiency.csv), and [efficiency intervals](tables/efficiency_intervals.csv).
- [Task/scene/category outcomes](tables/stratified_outcomes.csv), [endpoint failure classes](tables/terminal_outcomes.csv), and [r1→r2 cohort sensitivity](tables/r1_r2_cohort_sensitivity.csv).
- [Capabilities](tables/capabilities.csv), [action transitions](tables/action_transitions.csv), and [per-request context audit](tables/context_requests.csv).
- [Case index](tables/case_index.csv) and case cards for [r1](cases/r1.md), [r2](cases/r2.md), [r3](cases/r3.md), and [Gemini](cases/gemini.md).

Compressed JSONL evidence preserves the [selected episode registry](evidence/episode_registry.jsonl.gz), [all action chains](evidence/action_chains.jsonl.gz), [primary trace audit](evidence/selected_trace_audit.jsonl.gz), and [focused trace audit](evidence/focused_trace_audit.jsonl.gz). These are derived summaries, not copies of the full remote event streams. Every episode/case retains a remote source path.

Pinned [source excerpts](evidence/source_evidence.json), [r1/r2 source differences](evidence/r1_r2_source_diff.json), [source-hash checks](evidence/source_hash_verification.json), [data audit](evidence/data_audit.json), and [trajectory reconciliation](evidence/trajectory_audit.json) support the component analysis.

## Material interpretation limits

- Historical conditions do not isolate every component. r1 has mixed image-window cohorts and weaker native-binary provenance; r3 effort labels differ; Gemini changes provider route and recovery/context settings.
- A completed rollout is not the same as task success. Canonical results and historical attempts are counted separately.
- Cached input is part of input; reasoning is part of recorded output. Missing usage stays unknown; provider-internal reasoning and pricing are not inferred.
- Full-population endpoints and action counts are exhaustive for the selected cohort. Detailed context/image interpretation uses a documented diagnostic sample and cannot supply population causal failure frequencies.
- The saved motion archives omit zero-motion terminal Stop; the analysis reconstructs and flags it. Saved coordinate labels are inconsistent with the implementation; path calculations follow the verified coordinate conversion.
- Target-annotation ambiguity remains a possible explanation for some confident object-contact claims that disagree with evaluator distance.

The present evidence identifies a strong shared action-contract improvement and a substantial Pi request-size advantage. Establishing which Pi-specific component causally improves embodied performance requires the controlled comparisons in the next-step plan.
