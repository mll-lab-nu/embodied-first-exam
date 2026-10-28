# Codex/Pi rollout census and a concrete Pi optimization plan

> **Evidence storage:** full task cards, all CSV tables and the complete native
> transcript census are stored on Klone. See [archive access and checksums](ARCHIVE.md).

**Analysis date: 2026-10-21.** Read-only analysis of existing experiments; documentation and derived evidence only.

The source audit below describes the frozen experiment implementations. The current shared-parser correction is documented separately in [ACTION_PARSER_FIX.md](../../ACTION_PARSER_FIX.md); it does not retroactively correct these historical outcomes.

**Recommended direction:** use Pi's runtime as the base, add a small embodied controller, and evaluate changes separately. Start with removing post-terminal model requests and coding-only prompt/tool overhead; fix the shared action contract; then focus success improvements on target/phase memory, alignment and evidence-sensitive completion. Context projection and selective reasoning are the next resource-control layers. Increasing reasoning everywhere or repeatedly calling Sit is not a sufficient design.

This package analyzes **every one of the 1,218 task identities and 9,742 completed Codex/Pi episodes** in the agreed eight conditions. It adds a full native-transcript census to the earlier aggregate analysis. It does not claim a new visual root-cause adjudication of every frame: all task cards state which explanations are measured facts and which still need visual review or an intervention.

**Read next:** [exact files/functions and proposed behavior](IMPLEMENTATION_PLAN.md), [all task cards](TASK_INDEX.md), [source-to-behavior map](SOURCE_MAP.md), [methods](METHODS.md). The filterable [task index](ARCHIVE.md#data-tables) (`tables/task_index.csv`) and [episode diagnostics](ARCHIVE.md#data-tables) (`tables/episode_diagnostics.csv`) expose every result.

## 1. The main findings for optimization

1. **A deterministic action-interface defect is now quantified over the full cohort.** 1,937 accepted Codex actions and 0 accepted Pi actions contain an explicit speed/direction/skill substitution under the audit's conservative definition. Codex r2 alone has **547 affected actions in 543 episodes**. This is a shared HumanCLAW parser problem interacting with the harness/model's output format; it is not a native Codex planning module failing to run. Fix it for correctness and fair comparisons; do not infer a Pi success gain from Codex-only defects.
2. **There is a concrete low-risk token/delay target after physical execution is finished.** 4,821 Pi episodes have a verified extra final-reply request after `done=true`. H8 ends the Pi loop on the successful terminal tool result while preserving persistence/settlement. The quantified exposure is below; no new saving has been experimentally measured.
3. **Remaining Pi r2 failures are concentrated in task completion and interaction.** 334 episodes attempt Sit without any qualifying Sit-end contact, 44 execute no Sit, 14 have earlier qualifying contact but fail at termination, and 150 navigation episodes stop outside 0.20 m. These are disjoint endpoint categories, not assumed preventable failure counts. H3/H4 target the decision process behind them.
4. **Higher-effort runs improve net success, with substantial task-level reversals.** Pi r2→r3 rescues **229** tasks but loses **107**, net **+122** successes. Mean wall time rises **583.1→967.3 s**. Use those 336 changed-outcome tasks to inspect uncertainty/phase triggers, and protect the 107 regressions; do not set xhigh globally by default.
5. **Context eviction has a large measured uncached-token discontinuity.** Across 274 reconciled long Pi r2 episodes, mean uncached input per action request rises **410→20,909 tokens** across the 50-image boundary, while mean native request duration changes **12.63→13.12 s**. This is an observational boundary comparison, not a controlled causal effect or a proportional latency claim. The cap keeps old text; H5 should preserve current/landmark evidence while bounding repeated history and cache churn.

## 2. Cohort results and the practical baseline

| Condition | Success | Input M¹ | Uncached input M¹ | Wall mean / p95 s | Failed model requests |
|---|---|---|---|---|---|
| Codex r1 | 460/1218 (37.77%) | 1025.75 | 230.22 | 664.2 / 1818.1 | 88 |
| Pi r1 | 465/1218 (38.18%) | 568.10 | 192.03 | 600.3 / 1677.3 | 170 |
| Codex r2 | 669/1218 (54.93%) | 1196.75 | 300.39 | 636.8 / 1708.8 | 11 |
| Pi r2 | 676/1218 (55.50%) | 704.43 | 250.11 | 583.1 / 1524.6 | 46 |
| Codex r3 max | 782/1218 (64.20%) | 1478.55 | 433.50 | 1143.0 / 3278.5 | 352 |
| Pi r3 xhigh | 798/1218 (65.52%) | 857.09 | 353.89 | 967.3 / 2728.1 | 343 |
| Codex Gemini | 726/1217 (59.65%) | 1451.46 | 705.35 | 749.8 / 1914.9 | 1,643 |
| Pi Gemini | 667/1217 (54.81%) | 897.35 | 523.61 | 719.2 / 1883.7 | 3,602 |

Token totals are known subtotals; input includes cached input. Failed requests can have reported usage or missing usage. Wall time is seconds, mean / p95, and includes provider and environment behavior; it is not pure harness CPU time. Both Gemini conditions have 1,217 completed tasks; the Astra conditions have 1,218. Native r1 combines the original and image-window continuation cohorts.

| Condition | Navigation success | Interaction success |
|---|---|---|
| Codex r1 | 435/621 (70.05%) | 25/597 (4.19%) |
| Pi r1 | 455/621 (73.27%) | 10/597 (1.68%) |
| Codex r2 | 450/621 (72.46%) | 219/597 (36.68%) |
| Pi r2 | 471/621 (75.85%) | 205/597 (34.34%) |
| Codex r3 max | 466/621 (75.04%) | 316/597 (52.93%) |
| Pi r3 xhigh | 472/621 (76.01%) | 326/597 (54.61%) |
| Codex Gemini | 461/620 (74.35%) | 265/597 (44.39%) |
| Pi Gemini | 448/620 (72.26%) | 219/597 (36.68%) |

On Astra r2, Pi's overall advantage is only 7 successes: it has **21 more navigation successes but 14 fewer interaction successes**. The overall rate hides this trade-off. Pi r3 is 16 successes above Codex, while Gemini is 59 below. A compact Pi-based runtime is a promising engineering base, not a demonstrated universally superior policy across models.

For r2 **common-success pairs**, the earlier complete-usage subset shows Pi input down **46.02%**, uncached input down **17.73%**, and wall time down **9.39%**. Across **all r2 final episodes**, the respective point estimates are **41.14%**, **16.74%**, and **8.44%**. The approximately 46% figure is not a universal cost reduction. Much of the gross-input difference is repeated cached prompt/history exposure; reported pricing is unavailable.

The median first r2 request already costs **11,344 Codex versus 2,801 Pi input tokens**, before action history can explain the gap. Sampled payloads show approximately **25.4k / 2.9k system/developer characters** and **20.3k / 2.8k generic-tool characters**, respectively. This supports a baseline serialization burden, but does not isolate system prompt, schema representation and image detail as independent effects.

Use Pi r2/medium as the low-cost Astra reference, Pi r3/xhigh as the observed higher-success/higher-delay point, and Gemini as a separate compatibility/robustness condition. The earlier [scene-cluster uncertainty and paired efficiency analysis](../harness-comparison-20261019/EFFICIENCY.md) remains the statistical reference.

## 3. New full-census finding: raw intent can differ from the applied action

| Condition | Accepted actions | Changed actions | Affected episodes | At first action | Substitutions in successful episodes |
|---|---|---|---|---|---|
| Codex r1 | 45,446 | 922 | 920 | 552 | 370 |
| Pi r1 | 43,568 | 0 | 0 | 0 | 0 |
| Codex r2 | 50,789 | 547 | 543 | 340 | 305 |
| Pi r2 | 50,201 | 0 | 0 | 0 | 0 |
| Codex r3 max | 53,470 | 468 | 468 | 266 | 309 |
| Pi r3 xhigh | 55,586 | 0 | 0 | 0 | 0 |
| Codex Gemini | 45,608 | 0 | 0 | 0 | 0 |
| Pi Gemini | 42,473 | 0 | 0 | 0 | 0 |

“Changed actions” counts distinct accepted calls with explicit substitutions; “at first action” counts flagged substitutions at decision 1. The table is not a count of rejected tool calls. Formatting-only changes, ambiguous/omitted intent and legal clamping are excluded. [Every raw/applied row](ARCHIVE.md#data-tables) (`tables/action_contract_mismatches.csv`) includes the source transcript and line number.

The source explains the mechanism: `normalize_action` looks for `<...>` tokens. Walk speed defaults to slow if the second bracket token is missing; Turn direction defaults to left unless the first bracket token is exactly `right`. Consequently:

```text
requested: action_name = "Walk forward normal"
applied:   Walk<forward><slow>       # 0.2 m, not the explicit normal 0.4 m

requested: action_name = "Turn right 90"
applied:   Turn<left><90>            # opposite direction
```

The shared bridge accepts the nonempty string, constructs a normalized SkillCall and executes it. Pi's generic schema validation cannot validate semantics hidden inside that string. Merely restoring `minLength` or enabling stricter JSON shape checks does not solve this. H1 replaces the mini-language with explicit enums/numbers and server-side semantic validation. [Source and patch specification](IMPLEMENTATION_PLAN.md#h1).

### Reinterpreting some “first-action divergence” cases

| Pair | All tasks | Both first intents explicitly comparable | Same requested intent, different first execution |
|---|---|---|---|
| r1 | 1218 | 1204 | 325 |
| r2 | 1218 | 1201 | 203 |
| r3 | 1218 | 1147 | 130 |
| gemini | 1217 | 1189 | 0 |

This comparison conservatively parses only explicit, single-valued, valid Walk/Turn intent on both sides. The last column counts pairs where those requested parameters agree but the actual first actions differ. These particular divergences have a direct execution-contract explanation; they must not be reported as the models freely choosing different first actions. Other first-action divergences remain compatible with prompt/schema/image packaging differences and sampling. No conclusion here identifies the final outcome's counterfactual cause.

In r2, these **203 pairs account for 32.3% of the 629 pairs with different applied first actions**. Also, **491 of the 547 r2 substitutions** occur on the first executed use of the affected tool family. This prioritizes an unambiguous initial action contract, while the 56 later substitutions show that a first-call-only workaround is insufficient. [First-use accounting](evidence/mismatch_first_use.json).

## 4. New efficiency target: stop the model loop when the environment is terminal

| Pi condition | Verified final replies | Input M | Uncached M | Mean reply s | Share of cohort input | Native reply time / cohort wall |
|---|---|---|---|---|---|---|
| Pi r1 | 1213 | 19.603 | 6.249 | 11.02 | 3.45% | 1.83% |
| Pi r2 | 1217 | 21.886 | 9.510 | 8.76 | 3.11% | 1.50% |
| Pi r3 xhigh | 1207 | 24.018 | 11.820 | 11.98 | 2.80% | 1.23% |
| Pi Gemini | 1184 | 26.405 | 22.539 | 8.76 | 2.94% | 1.18% |

Eligibility requires a terminal environment result, exactly one subsequent non-action assistant response, normal completion, and matching native/HTTP input/output usage. Native duration is the measured request exposure; the last column divides it by total cohort wall time. These are accounting opportunities, not a promise that future end-to-end latency falls by the same percentage.

The existing task prompt explicitly requests a final answer after `done=true`, and Pi continues after a tool call by default. In an embodied benchmark, that reply cannot change an already final physical state. Use Pi's `finishTurn` decision to end after the recorded terminal result and emit a deterministic completion record. Preserve `agent_settled`, which HumanCLAW waits for. Do not confuse `done` with `task_success`, and do not return a nonexistent `terminate` field from a Pi `tool_result` extension. [Exact H8 change](IMPLEMENTATION_PLAN.md#h8).

This is useful but modest: one final reply is only part of the per-episode cost. Larger gains require fewer unnecessary decisions, less uncached history, or lower reasoning cost while maintaining task quality.

## 5. What the remaining failed tasks actually establish

| Pi condition | Sit, no qualifying Sit-end contact | No Sit | Historical contact, terminal fail | Navigation stopped too far | No Stop |
|---|---|---|---|---|---|
| Pi r1 | 536 | 50 | 1 | 166 | 0 |
| Pi r2 | 334 | 44 | 14 | 150 | 0 |
| Pi r3 xhigh | 209 | 39 | 23 | 149 | 0 |
| Pi Gemini | 335 | 10 | 1 | 152 | 52 |

The five columns are disjoint terminal classifications. “No qualifying Sit-end contact” refers to the last frame of each Sit, not every intermediate physics frame. “No Stop” combines interaction and navigation cases with no committed stop. Full criteria are in [METHODS](METHODS.md).

Of the **392 failed Pi r2 interaction episodes**, **272** finish within **1 mm** of the target AABB/body distance measure. Merely moving closer is therefore not a sufficient general repair. That distance is compatible with limb contact, penetration/overlap or an unsupported pelvis. The controller needs target consistency, support alignment, duration-aware lowering and calibrated completion evidence.

For navigation, only **19 of the 150 Pi r2 stopped-too-far failures** are within 0.30 m. A universal tiny forward nudge is not supported as the solution to most failures. Some involve wrong target interpretation, obstructions, routes or premature stopping. The task cards expose final distance, action history and model claims; visual evidence is linked where available.

### C022: a concrete source-to-outcome chain, with a clear causal limit

[Full eight-condition task card: shard-0317](ARCHIVE.md#task-cards). Astra r2 Codex succeeds after 63 actions; Pi fails after 75. Both perform two final Sit calls, after right-turn alignment and a 0.20 m backward step. Codex requests height 0.50; Pi 0.45. Each Sit is a 15-frame, approximately 0.5-second chunk.

The saved contact records were reread for this report:

| Observation | Codex r2 | Pi r2 |
|---|---|---|
| Final body-target AABB distance | 0.000 m | 0.000 m |
| Qualifying pelvis contact in first Sit | None | None |
| Qualifying pelvis contact in second Sit | Final 4 of 15 frames | None in all 15 frames |
| Final contacts with target object 209 | Includes 2 pelvis contacts | 3 right-hip, 1 left-knee, 1 left-ankle contacts; no pelvis/base |
| Completion | Active Stop | Active Stop |

Pi did contact the correct target object; “no contact at all” would be wrong. The evaluator requires pelvis/base contact, not arbitrary hip/limb contact. The exact saved [contact summary](evidence/c022_contact_summary.json) and [source criteria](evidence/source_excerpts.md#hc5) explain the metric difference.

Separately, Codex's first raw call is `Walk forward normal`, which the parser changes to slow. This corrects a simplistic earlier interpretation that Codex voluntarily chose a slow first step. It explains an early execution discrepancy, not why Codex eventually wins. The observed height/bearing/path choices and final contact cannot be assigned to one system-prompt clause or history wrapper without an intervention. H1 fixes the demonstrated contract problem; H3/H4 address the unsupported completion decision and alignment uncertainty.

### Other concrete task entry points

| Task | Target | Codex / Pi result | Codex / Pi actions | Mechanism to inspect |
|---|---|---|---|---|
| [C021 / r2](ARCHIVE.md#task-cards) (`tasks/shard-0368.md`) | tv | PASS / FAIL | 76 / 72 | TV fills view, but Pi ends 0.338 m away; obstacle/finish evidence (H3/H4) |
| [C022 / r2](ARCHIVE.md#task-cards) (`tasks/shard-0317.md`) | couch | PASS / FAIL | 63 / 75 | Same two-Sit tail; different pelvis contact; raw speed parsing also differs (H1/H4) |
| [C026 / r2](ARCHIVE.md#task-cards) (`tasks/shard-1136.md`) | chair | FAIL / PASS | 22 / 18 | Different chair interpretations; inspect grounding before optimizing approach (H3) |
| [C027 / r2](ARCHIVE.md#task-cards) (`tasks/shard-0375.md`) | bed | FAIL / PASS | 38 / 44 | Repeated sitting plus repositioning; align/verify/recover, not a fixed repeat count (H4) |
| [C031 / r2](ARCHIVE.md#task-cards) (`tasks/shard-1045.md`) | potted_plant | PASS / PASS | 35 / 38 | Both succeed; preserve finish while removing request overhead (H2/H5/H8) |
| [C036 / r2](ARCHIVE.md#task-cards) (`tasks/shard-0730.md`) | tv | FAIL / FAIL | 100 / 100 | Both reach action limit far from TV; route/progress recovery (H3) |
| [C041 / r3](ARCHIVE.md#task-cards) (`tasks/shard-0795.md`) | tv | PASS / FAIL | 100 / 99 | Pi ends in another room; target/route memory (H3) |
| [C047 / r3](ARCHIVE.md#task-cards) (`tasks/shard-0436.md`) | bed | FAIL / PASS | 26 / 27 | Both use three Sit calls; alignment/height/contact differ (H4) |
| [C067 / gemini](ARCHIVE.md#task-cards) (`tasks/shard-0225.md`) | bed | FAIL / PASS | 32 / 30 | Both use two Sit calls; backward adjustment/endpoint differ (H4) |

All 1,218 task cards contain this style of metric/trace comparison, including complete chains and raw first-divergence arguments. The cases above additionally link the earlier saved-image review. The cards do not claim image-grounded causal certainty for unreviewed tasks.

## 6. Context and cache: a resource mechanism worth testing

The shared transport preserves the initial image plus the latest images up to the cap, but keeps old text. Once eviction starts, replacing earlier image blocks can invalidate part of the cached prefix. The new native Pi audit compares five decisions immediately before/after that boundary within the same long episode, using only episodes whose native input/cache accounting reconciles with HTTP totals and has no failed model calls:

| Pi condition | Long episodes | Uncached/request before → after | Cached/request before → after | Native duration s before → after |
|---|---|---|---|---|
| Pi r1 | 143 | 547 → 20,986 | 21,364 → 2,317 | 14.51 → 14.29 |
| Pi r2 | 274 | 410 → 20,909 | 21,578 → 2,475 | 12.63 → 13.12 |
| Pi r3 xhigh | 290 | 470 → 21,776 | 22,248 → 2,425 | 17.21 → 18.11 |
| Pi Gemini | 309 | 3,178 → 12,083 | 10,630 → 5,118 | 11.30 → 12.46 |

Values are means over matched episode windows. Before/after differs in physical state and provider timing; it is not an isolated intervention. Native durations include the request's observed execution time. The purpose is to identify whether a cache-aware context design has a plausible measured target, not to claim every delay increase is caused by eviction.

The r1 row uses only the capped continuation subset. In r2, the uncached-input jump is approximately **51×**, whereas the native-duration change is approximately **3.9%**; token and latency effects should not be conflated.

H5 proposes a stable task/tool prefix, bounded target/phase state, the current image, recent observations and a small keyframe set. Compare chunked eviction with a per-step sliding window. Log retained IDs and cached/uncached tokens; preserve tool-call/result pairing and provider-required reasoning signatures. A smaller context that loses the target and adds more actions may cost more overall.

In the previous **8,035 sampled native provider requests**, the current image was present in every request. That sample result is not expanded into a full provider-payload census here. Native compaction events in the new session census: **0**. Image eviction and semantic compaction remain different operations.

## 7. Which code should change first?

| Order | Change | Specific location | Main objective | Main risk to measure |
|---|---|---|---|---|
| 1 | [H8 terminal completion](IMPLEMENTATION_PLAN.md#h8) | Owned runner wraps `session.agent.finishTurn`; new-profile prompt completion wording | Remove measured final-reply exposure | Settlement/persistence regression |
| 1 | [H2 embodied prompt + tools](IMPLEMENTATION_PLAN.md#h2) | `runtime.py` / Pi SDK tool allowlist and system prompt | Lower baseline input and unrelated instruction burden | Losing useful action semantics |
| 2 | [H1 typed contract](IMPLEMENTATION_PLAN.md#h1) | `environment.py::tool_definitions/call`, direct SkillCall construction | Eliminate silent semantic substitutions; fair comparisons | Accidental primitive/benchmark change |
| 3 | [H3 target/phase memory](IMPLEMENTATION_PLAN.md#h3) | Owned `controller.ts`, Pi tool-result / next-request hooks | Target/route progress and fewer repeated actions | Stale or incorrect memory |
| 3 | [H4 completion/alignment](IMPLEMENTATION_PLAN.md#h4) | Pi `beforeToolCall` and bounded recovery state | Recover unsupported finishes | Extra calls, false Stop blocks, hidden-state leakage |
| 4 | [H5 context projection](IMPLEMENTATION_PLAN.md#h5) | Pi `transformContext`; coordinate `services.py::cap_images` | Lower repeated/uncached input | Lost visual landmarks, cache churn |
| 4 | [H6 selective effort](IMPLEMENTATION_PLAN.md#h6) | Pi request/next-turn hooks and capability profile | Trade reasoning cost for difficult decisions only | Misclassified hard cases or unsupported effort |
| Foundation / separate reliability variant | [H7 admission/retries](IMPLEMENTATION_PLAN.md#h7) | Explicit sequential execution, observation snapshots, one retry owner | Avoid stale/duplicate actions and long retry tails | Abandoning recoverable requests too early |

The [implementation plan](IMPLEMENTATION_PLAN.md) specifies parameter schemas, state fields, candidate thresholds, hook composition, source locations and acceptance criteria for each change. New-file names are proposed design locations; no implementation files were created.

Do **not** begin with a universal verifier on every step, fixed minimum Sit count, unobserved “support sensor,” blind action batching, or global maximum effort. Those either add cost indiscriminately, change the benchmark information/action space, or have counterexamples in the recorded tasks.

## 8. Native harness contribution versus embodied policy

Codex and Pi did perform the native runtime work: construct requests, provide default instructions/tool representations, preserve history, parse model output, dispatch MCP tools, await results and continue/finish the loop. They did not automatically supply a task-specific target tracker, alignment state machine, support-contact verifier or calibrated Stop policy. In the integration, `verifier={}` and the environment's terminal decision is largely driven by `stand`/budget/termination.

Full-census non-environment native tool calls recovered: **Codex r3 max: update_plan=12; Codex Gemini: exec_command=1**. The 12 `update_plan` calls occur in three r3 episodes and return “Plan updated”; the single Gemini `exec_command` fails in the sandbox launcher because bubblewrap is unavailable. These recorded outputs were reread, not re-executed. [Generic-tool result evidence](evidence/generic_tool_results.jsonl).

The full accounting distinguishes **387,141 accepted environment actions**, **75 rejected environment calls**, **13 generic native-tool calls**, and **77 Pi tool-call proposals inside failed assistant responses that were never executed**. Their sum is **387,306 raw function/tool proposals**. A proposal in a failed response is not an MCP dispatch. [Per-condition accounting](ARCHIVE.md#data-tables) (`tables/native_call_accounting.csv`).

Sparse or absent generic-tool use does not mean the harness was unused; its conversation/execution loop still mediated the environment calls. Conversely, merely using that loop does not establish that it contributed an embodied recovery strategy. [Detailed source attribution](SOURCE_MAP.md).

The observed distinctions fall into three evidence levels:

| Level | Supported claim | What remains unproven |
|---|---|---|
| Deterministic local mechanism | Parser changed an explicit parameter; loop issued a request after terminal tool success | Final success change after fixing the mechanism; future wall-time saving |
| Measured task fact | Distance, Stop/Sit, contact endpoint, action count, tokens and timing | Whether grounding, alignment, occlusion or another model decision caused the fact |
| Proposed policy intervention | Target memory, bounded completion guard, cache projection and adaptive effort are implementable at identified Pi hooks | Their causal success/token/delay gains and model generality |

## 9. Coverage, checks and the next decision

| Check | Result |
|---|---|
| episodes | 9742 |
| tasks | 1218 |
| all_metrics_unchanged | True |
| all_status_ok | True |
| native_actions_equal_metric_steps | True |
| physical_chain_equals_native_applied | True |
| all_call_proposals_accounted_for | True |

The audit reads approximately **165.76 GB** of native session files on the server and saves compact evidence locally. The original source files, configurations, rollout records and physical state were not changed. C022 uses an additional read of saved contact records; no replay was used.

Choose the first implementation bundle from the H1–H8 specifications, then run separate controlled variants only when new experimentation is authorized. Track rescued **and lost** tasks, all-episode success, uncached input, model requests, actions and mean/p95 delay. Keep successful task cards as regression references. Because all current validation tasks informed this analysis, use a fresh held-out evaluation for a final generalization claim.

The main deliverable is this decision document plus [1,218 task cards](TASK_INDEX.md); [METHODS](METHODS.md) and the evidence tables make each aggregate and limitation inspectable.
