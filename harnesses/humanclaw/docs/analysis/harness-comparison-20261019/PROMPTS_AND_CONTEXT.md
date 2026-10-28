# P3 — Prompts, per-request context, and r1→r2 semantics

## What is fed to each model request

**Codex, first request:** native coding-agent instructions; permission/environment instructions; native tool definitions; the HumanCLAW task and action protocol; and the initial ego image. In the sampled Astra r2 payloads, system/developer content is about 25.4k characters and the generic tool catalog another 20.3k characters.

**Pi, first request:** its shorter coding-assistant system/developer prompt; four generic tools; the same HumanCLAW task/action protocol; eight directly exposed environment tools; and the initial ego image. System/developer content is about 2.9k characters and generic tools 2.8k characters.

**Subsequent native requests:** system instructions and tool definitions remain present. The harness carries prior assistant/function-call items, corresponding tool results, images, and recorded reasoning items where returned. The newest image accompanies the most recent tool result. This is the native harness's conversation-management work; the model supplies the decisions.

**PSV requests:** a task-specific plan-and-skill prompt, current image, and a bounded textual history (configured maximum 10). Conditional verifier requests use a separate prompt. PSV explicitly asks for a visible-state description, mid-level progress/goal, low-level action reasoning, and structured action choice. Its last request can be a verifier call, so first-to-last prompt-size changes are not directly comparable to the native conversation.

## Quantified request audit

The primary diagnostic sample contains **209 runs and 10,259 model requests**: **8,035 native HTTP-boundary requests** and 2,224 PSV adapter calls. Six additional focused runs are retained separately and are not added to the table below.

| Condition | Audited runs | Model requests | Median first input tokens | Median system characters | Native-tool characters | Max sent images | Requests with image eviction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PSV r1 | 24 | 2,224 | 1,996 | 1 | 0 | 1 | 0 |
| Codex r1 | 23 | 900 | 11,283 | 25,475 | 20,328 | 50 | 173 |
| Pi r1 | 23 | 942 | 2,743 | 2,890 | 2,784 | 50 | 223 |
| Codex r2 | 24 | 1,062 | 11,344 | 25,448 | 20,328 | 50 | 253 |
| Pi r2 | 23 | 1,015 | 2,802 | 2,891 | 2,784 | 50 | 224 |
| Codex r3 max | 23 | 1,291 | 11,351 | 25,469 | 20,328 | 50 | 471 |
| Pi r3 xhigh | 23 | 1,130 | 2,802 | 2,896 | 2,784 | 50 | 358 |
| Codex Gemini | 23 | 798 | 14,513 | 25,487 | 20,328 | 10 | 557 |
| Pi Gemini | 23 | 897 | 4,329 | 2,897 | 2,784 | 10 | 609 |


Characters are not token estimates. Serialized tool schemas differ between harnesses, so their character counts are descriptive component-size measurements. Full-census first-request token medians corroborate the gap: Astra r2 **11,344 Codex versus 2,801 Pi**, approximately 4.05×. This occurs before trajectory length can explain the difference, but it includes every request-format difference, not an isolated system-prompt intervention.

At every one of the **8,035 sampled native request boundaries**, the current observation's image hash is present. No stale-current-image exception was found in this audit. Repeated identical images can make temporal hash identity ambiguous; this is not a proof about every request in the full population.

## Image eviction is not native context compaction

The shared HumanCLAW transport keeps the **first image plus the most recent cap-minus-one images**. Older image blocks are replaced with short textual notices; earlier text, actions, and results remain. The configured cap is 50 for the continuation/r2/r3 cohorts and 10 for Gemini. Original r1 has no configured cap.

In sampled long episodes, native histories reach **101 images** before normalization, while delivered requests remain within the cap. The counts of “image blocks dropped” in the CSV sum repeated block exposures across requests; they are not counts of unique deleted observations. There is no observed native summary/compaction event explaining this behavior.

Examples of retained text growth: median first/last request text in Codex r2 is **28,324 / 47,585.5 characters**; Pi r2 **3,670 / 22,234**. These include different episode lengths and should not be interpreted as equal-step growth slopes. [context_requests.csv](tables/context_requests.csv) retains every audited request's observation, image list, item types, roles, text size, and normalization.

## r1→r2: the user's tool-description hypothesis is supported

The actual definitions sent to both native harnesses change in exactly two of the eight tools:

| Tool | r1 action description | r2 action description |
|---|---|---|
| Sit | `Sit down<height> (height clamped to 0.15–0.85 metres)` | Adds: `one call moves for only about 0.5 s and may not complete sitting down` |
| Stop | `finish at the current pose; no generated motion` | `submits the current pose as the final pose and ends the episode; no further motion is generated` |

Each change appears in both the tool description and its `action_name` parameter description. The other six definitions are unchanged within each harness. The HumanCLAW initial task-prompt template is unchanged. Exact text and hashes are in [tool_definitions.json](evidence/tool_definitions.json) and [tool_description_changes.csv](tables/tool_description_changes.csv).

The pinned source difference supports a narrow interpretation:

| Source difference | Practical role in r2 |
|---|---|
| Sit/Stop wording and protocol digest | Changes the model-visible action contract; logs its identity |
| Real binary/package hashes and version source | Improves provenance; does not add an embodied reasoning policy |
| Pi `thinkingLevelMap` for xhigh/max | Relevant to higher-effort runs; medium is sent unchanged |
| Effort validation | Checks route-supported settings; no changed medium value in r2 |
| Services-file change relative to r1 image-cap source | Docstring only; same image-cap algorithm |
| Gemini model configuration | Also differs in the full source manifest, but is not selected by the Astra r1/r2 runs |

The original r1 cohort still differs in image-cap policy. A sensitivity check compares only r1 continuation tasks, where both r1 and r2 already use cap 50:

| Harness | Matched continuation interaction tasks | r1 interaction successes | r2 interaction successes | Gain |
| --- | --- | --- | --- | --- |
| Codex | 191 | 8 | 68 | 31.41 pp |
| Pi | 187 | 5 | 54 | 26.20 pp |


The gain persists within that matched-image-policy subset. It is a selected historical cohort, not a randomized sample, but image-cap introduction alone cannot explain the observed r1→r2 improvement.

Behavior changes line up with the added duration fact:

- Exactly one Sit in interaction tasks falls from **487 to 15** for Codex and **468 to 14** for Pi.
- Across all action chains, adjacent **Sit→Sit transitions rise from 0 to 859** for Codex and **0 to 804** for Pi.
- Interaction tasks account for **92.82%** of Codex's and **92.42%** of Pi's net additional successes.

This makes **action semantics the strongest supported explanation to prioritize**, while retaining uncertainty about unrandomized runs and weaker r1 binary provenance.

## A concrete same-task r1/r2 example

Codex shard **0738**, scene `106366410_174226806`, episode 24, bed:

The first **10 actions are identical**. r1 then executes **Sit(0.55) → Stop**, ending after 12 decisions: target distance 0.023 m, but no valid sitting contact and interaction failure. r2 instead executes **Turn right 120° → Turn right 60° → Step back 0.20 m → Sit(0.55) → Sit(0.55) → Stop**, ending after 16 decisions with valid sitting contact and success.

This demonstrates changed alignment and repeated sitting after an identical approach. It does not isolate an extra Sit call as the sole cause. Both trajectories are short enough that a 50-image cap never binds, further limiting that alternative explanation for this example. Raw call and visible-state evidence is in [focused_trace_audit.jsonl.gz](evidence/focused_trace_audit.jsonl.gz).

## Provider and recovery details

Actual native efforts are medium for r1/r2, max for Codex r3, xhigh for Pi r3, and medium for Gemini. No explicit temperature/output-token limit is sent in the audited native requests. Codex sends `tool_choice=auto` and `parallel_tool_calls=false`; Pi omits these fields. The common task protocol nevertheless requests sequential actions and waits for each result.

Both Gemini configurations use the shared HumanCLAW empty-response retry budget of five. A response with neither text nor a tool call is retried at the provider transport layer. The diagnostic sample records **18 Codex and 63 Pi EmptyResponse failures**; these are sample counts, not the full-population empty-response total. Full failed-model-request counts are 1,643 and 3,602, respectively, and include other errors. Many Gemini failed requests still contain usage: failure count and missing-usage count are different quantities.

Gemini reasoning-token fields are reported as zero at this boundary. That is not proof that the provider performed no internal reasoning. Goal-management code exists in the later source, but the inspected Gemini configurations do not enable the goal feature; it is not credited as an active component.
