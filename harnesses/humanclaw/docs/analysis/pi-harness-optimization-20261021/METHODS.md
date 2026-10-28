# Methods, coverage and limitations

> **Evidence storage:** full task cards, all CSV tables and the complete native
> transcript census are stored on Klone. See [archive access and checksums](ARCHIVE.md).

[Main report](REPORT.md) · [Full task index](TASK_INDEX.md)

## Scope and read-only execution

This analysis uses the eight previously agreed Codex/Pi conditions: Astra r1, r2, r3, and Gemini. The completed cohort contains **9,742 episodes across 1,218 task identities and 41 scenes**. Both Gemini conditions lack shard-0184; no outcome is imputed. Native r1 combines original and `imgwin50` continuation cohorts, preserving each episode's suite/configuration. PSV remains an earlier reference, not part of this new native-harness census.

Only existing logs, metrics, saved trajectories and source files were read on the server. No model inference, simulator execution, replay, rollout, scheduler submission or experiment-code/configuration edit was performed. New Markdown and derived evidence were written locally. Temporary analysis programs were kept outside the project; no reusable skill was implemented.

## Sources and record selection

The previous [analysis package](../harness-comparison-20261019/REPORT.md) provides the completed-run registry, normalized HTTP usage, latency unions, saved action chains, initial-pose comparison and source manifests. Its final-run selection matches each run's reported metrics to the suite's completed metrics, rather than choosing the newest directory. This package preserves those run IDs and rereads their final `metrics.json` from the server to detect changes.

For each canonical run, the new audit reads the single native session transcript:

- Pi: `native/sessions/*.jsonl`.
- Codex: `native/home/.codex/sessions/*/*/*/*.jsonl`.

Missing or multiple native transcripts are explicit audit issues, not silently resolved by timestamp. Native images are omitted during compact extraction; the original files remain on the server. The compact evidence retains tool-call IDs, arguments, model self-reports, applied results, original file line numbers, system-text hashes and event counts. Pi assistant usage/duration is retained. Codex cumulative/native usage notifications are not added to normalized HTTP usage.

The native system fingerprint uses Codex's recorded base-instruction string and Pi's ordered section values joined by newlines. Pi's fingerprint is an audit representation, not an assertion that it exactly matches the provider's final serialized instruction string. Provider-payload character measurements come from the earlier request audit.

Thirteen non-environment Codex tool outputs were read separately into `generic_tool_results.jsonl` and joined by transcript path/call ID for the derived tables. The main compact extraction deliberately concentrates on MCP results, so its generic-call result fields can remain null; use this supplement for those calls. Seventy-seven Pi call proposals occur in native assistant messages whose stop reason is `error`, with no tool result. They are preserved as unexecuted proposals, not counted as MCP executions or server rejections. [native_call_accounting.csv](ARCHIVE.md#data-tables) reconciles all four categories of proposals.

The audit joins tool calls to results by native call ID, checks the accepted observation sequence against recorded decision count, and compares each applied skill/condition with the previously extracted saved action chain. Float32 saved conditions use an absolute comparison tolerance of 1e-5. Existing terminal Stand rows inferred from metrics/NPZ are independently checked against native execution results. Results and exceptions are in [audit_summary.json](evidence/audit_summary.json).

## What “every task analyzed” means

Every available task/condition receives: endpoint diagnosis, physical-action features, full applied action chain, raw/applied semantic checks, model-call and usage accounting, latency, effective configuration, final self-report, paired first divergence, cross-condition outcome pattern, and candidate source changes. Successful episodes are included as efficiency and regression references, not omitted from failure analysis.

This is **not** a new manual frame-by-frame visual adjudication of all 9,742 episodes. The previous package reviewed 24 pairs using 96 saved images and has 80 paired case cards. Those links are retained. This package adds complete native-call auditing and a fresh C022 contact-record check, while marking visual/semantic root causes as unresolved when the evidence does not isolate them. In particular, a distant stop cannot by itself distinguish target misidentification from an obstruction or an inaccurate visual distance estimate.

## Endpoint facts and physical diagnostics

Success is `interact_sr` for interaction episodes and `nav_sr_20cm` for navigation episodes. Process completion is not task success.

- Navigation success requires active Stop and final body-to-target-AABB distance ≤0.20 m.
- Interaction success requires active Stop, at least one Sit and pelvis/base contact with an exact resolved target mesh on the **final frame of the last motion**.
- `geo_interact_sr` records whether any Sit's **last physics frame** had qualifying contact. False does not mean no transient contact in any intermediate physics frame.
- Body-AABB distance zero does not imply pelvis support. Limb contacts with the correct object do not satisfy the pelvis/base criterion.
- Current `visible_state` is the model's claim about the pre-action image. It is not independent perception ground truth or post-action verification.

Saved horizontal root motion uses axes 0 and 1 in the actual Z-up saved state, following the previous coordinate audit. Path length is not target distance or optimal-path length. A low-displacement Walk means <0.02 m horizontal root displacement. Opposite-sign adjacent turns form a reversal flag. Neither flag is automatically a failure or a wasted action. Ground-truth distances, contact records and root-motion flags are for offline analysis, not assumed available to an embodied policy.

## Explicit action-mismatch definition

For each accepted environment action, compare the raw model argument with the returned applied condition. Count a mismatch only when the raw argument contains an unambiguous explicit speed (`slow`, `normal`, `fast`) or direction (`left`, `right`) that disagrees with the applied value, or when the dispatched skill changes. The main census therefore measures **explicit speed/direction/skill substitutions**, not all possible numeric parsing defects.

Cosmetic canonicalization, missing/ambiguous intent, legal clamping and differences in floating-point formatting are not counted as those substitutions. Absence of a flagged mismatch is not proof that every parameter parser is correct. Every flagged row preserves raw text, applied action, native line and transcript path in [action_contract_mismatches.csv](ARCHIVE.md#data-tables).

## Tokens, terminal requests and time

Normalized leaf HTTP model usage remains the accounting source for totals. Input includes cached input; output includes reasoning where reported. Missing usage remains missing and is shown as coverage/known subtotals. No recorded versioned prices are available, so token reductions are not dollar-cost estimates. Token units differ across model families.

For H8, an episode is eligible only when the native transcript has an accepted terminal environment result, exactly one subsequent assistant response with no later tool call, normal `stop` completion, and native input/output usage matching the normalized final HTTP request. The terminal-reply table excludes unmatched, absent, multiple or abnormal tail responses. Pi's native usage decomposition is normalized as `input + cacheRead + cacheWrite`; `cacheWrite` here is a native accounting bucket, not a claim about a separately billed explicit-cache write API. Uncached input is normalized input minus cached input.

The recorded native assistant `durationMs` quantifies the removed-request exposure. It is not a guaranteed future end-to-end latency reduction: queueing, provider load, cache state and startup costs can change. Existing wall time and non-overlapping per-kind model/environment span unions remain the all-episode latency measures. Nested tool/module/environment durations are never summed as independent elapsed time.

One native final assistant response is not proof of a single underlying HTTP attempt: provider-internal retry/backoff can remain inside that response. Terminal token exposure uses only the matched final successful HTTP request, while native duration can include its internal retry time. Extra invisible retry-token savings are not credited.

For the image-cap boundary analysis, use only Pi episodes with zero failed model requests, native summed input/cached usage reconciled to HTTP totals, and five action decisions on each side of the first image-eviction boundary. At cap K, compare observations K−5…K−1 with K…K+4. These windows are within the same long episode. They do not hold scene state, output or provider load constant, so the observed discontinuity supports a cache mechanism but is not an intervention-based latency effect.

## Pairing, recommendation coverage and causal limits

Pairs retain scene/episode/target, initialization, task/goal/profile hash and seed checks from the earlier package. An exact applied-action common prefix aligns behavior until the first divergence. Once paths diverge, comparing equal step numbers does not compare the same image or physical state.

The per-task H1–H8 tags are **review/implementation eligibility flags**, not estimated recoverable failures. Tags overlap. H5's ≥16-action threshold identifies candidates for a proposed bounded-context design; it is not a measured token-benefit cutoff. H6's r2/r3 outcome-change tag is diagnostic; it must not be used as a hindsight inference-time lookup.

Historical r1→r2 changes support the duration/Stop wording mechanism but are not randomized component ablations. r3 effort labels differ between harnesses. Gemini changes model route and other settings. The 1,218 tasks are not repeated draws under one unchanged policy. Success in one of several conditions demonstrates observed feasibility, not a deployable oracle or a success probability.

The prior package's scene-cluster confidence intervals remain the uncertainty reference for reported aggregate comparisons. This package adds mechanism diagnostics rather than inventing new causal success-gain estimates. No proposed optimization's gain has yet been measured.

## Artifact guide

| Artifact | Purpose |
|---|---|
| `REPORT.md` | Quantified findings and implementation priorities |
| `IMPLEMENTATION_PLAN.md` | H1–H8 exact code locations, before/after behavior and validation gates |
| `SOURCE_MAP.md` | Native/shared responsibility and pinned source anchors |
| `TASK_INDEX.md`, `tasks/shard-XXXX.md` | Every task and all available conditions |
| `tables/task_index.csv` | Filter tasks by outcomes, prior case IDs and candidate changes |
| `tables/episode_diagnostics.csv` | Per-episode endpoint, behavior, cost, native audit and final-reply data |
| `tables/paired_diagnostics.csv` | Paired divergence, endpoints and cost/action deltas |
| `tables/action_contract_mismatches.csv` | Confirmed explicit raw/applied substitutions |
| `tables/first_action_intent_comparison.csv` | Conservative comparison of explicit first Walk/Turn intent versus executed first action |
| `tables/tool_counts.csv` | All accepted environment action counts by condition/tool |
| `tables/native_call_accounting.csv` | Accepted/rejected environment calls, generic calls and unexecuted failed-response proposals |
| `tables/pi_image_cap_boundaries.csv` | Reconciled within-episode pre/post image-cap request costs |
| `tables/recommendation_coverage.csv` | Non-causal recommendation eligibility counts |
| `evidence/native_transcripts.jsonl.gz` | Compact native census with source line/path references |
| `evidence/audit_summary.json` | Counts, reconciliation checks and exceptions |
| `evidence/source_excerpts.md`, `source_provenance.json` | Stable source evidence and hashes |
| `evidence/c022_contact_summary.json`, `c022_contact_records.jsonl.gz` | Fresh saved-physics contact audit for C022 |
| `evidence/c022_request_mechanisms.jsonl.gz` | Previously extracted C022 provider-request/schema details |
| `evidence/generic_tool_results.jsonl` | All 13 non-environment Codex tool outputs, read without re-execution |

The original remote logs remain the source of truth. Derived tables and cards contain no new model answers or simulated physical trajectories.
