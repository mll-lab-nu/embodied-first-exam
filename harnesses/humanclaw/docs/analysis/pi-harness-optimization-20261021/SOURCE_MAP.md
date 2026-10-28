# From source code to model requests, actions and outcomes

> **Evidence storage:** full task cards, all CSV tables and the complete native
> transcript census are stored on Klone. See [archive access and checksums](ARCHIVE.md).

[Main report](REPORT.md) · [Concrete changes](IMPLEMENTATION_PLAN.md) · [Pinned excerpts](evidence/source_excerpts.md)

## Version and evidence boundary

The recorded r2/r3/Gemini native identities point to **Codex 0.145.0** and **Pi 1.3.0**. The matching release source snapshots reviewed here are Codex `1635de866c61d1b76e50b31928ee6d61482435a8` and Pi `71023aec1546d6d677a65669c5665c0927ce0dd0`. Source mechanisms are corroborated with delivered requests/native transcripts; a release tag alone is not proof of a reproducibly identical binary. r1 provenance is weaker and original/continuation membership is retained.

The frozen HumanCLAW r2 source is `d18b41dd0df221409a72b8a554b0341fa64743d5`, under `/gscratch/scrubbed/linjli/humanclaw/fixes/r2-d18b41d`. The prior [source hash audit](../harness-comparison-20261019/evidence/source_hash_verification.json) matches recorded source files to historical commits. New [source_provenance.json](evidence/source_provenance.json) records full-file hashes for the excerpts used below. The local Pi checkout was 1.2.0, so the plan deliberately names the attested 1.3.0 APIs rather than treating local HEAD as the runtime used in the experiments.

## Mechanisms that actually matter

| Layer | Actual source mechanism | What the rollout evidence supports | Consequence / proposed change |
|---|---|---|---|
| Initial task | HumanCLAW `EnvironmentBridge.initial_prompt` sends task, observation 0, initial ego image and action budget | Same paired instruction/init/goal/profile hashes in the previous input audit | Task semantics belong to HumanCLAW; retain them in H2 |
| Action descriptions | HumanCLAW `tool_definitions` supplies 8 MCP actions; r2 adds Sit duration and explicit terminal Stop wording | r1→r2 repeated-Sit behavior and interaction success change together | Strong reason to preserve duration/completion semantics; not a randomized wording effect |
| Codex system prompt | `models-manager::model_info_from_slug` falls back for unknown model slugs; default coding instructions are used unless overridden | C022 logs the missing metadata warning; delivered 20,751-character base instructions match the release prompt hash | Large initial request burden, not evidence of an embodied controller |
| Pi system prompt | `buildSystemPromptSections` defaults to a coding assistant; adapter passes no custom replacement | About 2.9k system/developer characters in sampled r2 requests; 4 generic tools | H2 can target remaining generic prompt/tool overhead |
| Tool schema conversion | Codex's `JsonSchema.properties` is a `BTreeMap`; supported schema fields omit `minimum` and `minLength`; Responses tool `strict=false` | C022 shows reordered properties, dropped constraints, namespaced short tool names | Schema representation differs before any history; server validation remains necessary |
| Pi schema conversion | `toParameters` preserves the received schema; flat MCP tool names; provider-specific strict handling | C022 preserves constraints/order and uses `mcp__humanclaw__sit` | Smaller/different serialization is real; its contribution to decision quality is not isolated |
| Local tool validation | Pi validates/coerces tool arguments before execution; shared server validates IDs/field shape | Well-formed strings can still encode invalid mini-language semantics | H1 must validate semantic action fields; generic JSON validation is insufficient |
| Action parsing | Shared `normalize_action` extracts bracket tokens and defaults missing speed/direction | Full raw/applied mismatch census; C022 `normal → slow` | Confirmed deterministic interface defect; fix the shared contract |
| History | Native runtimes append assistant calls, tool results, images and reasoning items where returned | Previous 8,035-request native sample and this full session-transcript census | A general conversation loop, without explicit target/phase memory |
| Images | Shared `cap_images` preserves first + latest cap-minus-one images; older image blocks become text notices | Caps 50 for continuation/r2/r3, 10 Gemini; no cap for original r1 | H5 should bound text and images together while preserving current evidence |
| Image detail | Codex delivered `high`; Pi Responses conversion uses `auto` in inspected requests | Packaging differs even with the same source image | Candidate contributor to perception/token differences, not an isolated explanation |
| Tool result wrappers | Codex adds wall-time/output framing; Pi converts MCP content and normalizes images | Delivered histories differ in formatting and text burden | H2/H5 can simplify the owned interface; preserve public meaning |
| Physical execution | MCP bridge queues actions on the simulator's owning thread; freshness/idempotency checks precede execution | Native dispatch → accepted environment action → next observation is traceable | Keep one owner; do not parallelize physical actions to reduce delay |
| Interaction policy | Bridge builds `PlannerResult(..., verifier={})`; no native target/support verifier is wired in | Stop self-reports can disagree with evaluator distance/contact | H3/H4 must add task-aware state/guards explicitly |
| Completion | `done` is set on environment termination, `stand`, or max steps; prompt requests a final model answer | Verified Pi post-terminal reply requests in the new census | H8 can terminate after tool success with a deterministic acknowledgement |
| Metrics | `record_motion` uses the last physics frame of a Sit for historical contact; `finalize` requires active Stop, ≥1 Sit and contact on the last motion frame | C022 contact audit and all endpoint diagnostics | Never substitute body-AABB distance, limb contact or a visual claim for InteractSR |

## Exact anchors for implementation review

The current HumanCLAW repository links are navigation aids; use the frozen excerpts to resolve historical line/version differences. Pi and Codex links below point into the saved source-evidence document, so the report does not depend on temporary source checkouts surviving.

| ID | File / function / release line | Review purpose |
|---|---|---|
| [HC1](evidence/source_excerpts.md#hc1) | `environment.py`: `tool_definitions` 46, `initial_prompt` 104, `call` 157–224 | Typed contract, freshness, empty verifier, terminal condition; current [repository file](../../../src/humanclaw_bench/harnesses/environment.py) |
| [HC2](evidence/source_excerpts.md#hc2) | `runtime.py`: config allowlist 69, Pi invocation 413, `_pi_config` 468, `_pi` 542 | Profile plumbing, native settings, settlement; current [repository file](../../../src/humanclaw_bench/harnesses/runtime.py) |
| [HC3](evidence/source_excerpts.md#hc3) | `services.py`: `cap_images` 49, payload normalization 234–245 | Image budget and effective request fields; current [repository file](../../../src/humanclaw_bench/harnesses/services.py) |
| [HC4](evidence/source_excerpts.md#hc4) | `agent/skills.py`: bracket parser 89, Walk 90, Turn 104, Sit 124 | Silent semantic substitution; current [repository file](../../../src/humanclaw_bench/agent/skills.py) |
| [HC5](evidence/source_excerpts.md#hc5) | `evaluation/metrics/episode.py`: `record_motion` 145, `finalize` 198 | Historical versus terminal contact; current [repository file](../../../src/humanclaw_bench/evaluation/metrics/episode.py) |
| [HC6](evidence/source_excerpts.md#hc6) | `envs/find_nav_interact_env.py`: `is_pelvis_target_contact` 393 | Pelvis/base and exact goal-mesh requirement; current [repository file](../../../src/humanclaw_bench/envs/find_nav_interact_env.py) |
| [PI1](evidence/source_excerpts.md#pi1) | `packages/coding-agent/src/core/system-prompt.ts`: `buildSystemPromptSections`, `buildSystemPromptState` | Replace generic prompt without losing required sections |
| [PI2](evidence/source_excerpts.md#pi2) | `packages/coding-agent/src/core/sdk.ts`: tool allowlist 65, provider payload hook 373, Agent construction 413 | Tool filtering, context interception and provider boundary |
| [PI3](evidence/source_excerpts.md#pi3) | `packages/agent/src/agent.ts`: AgentOptions 113; default execution 253 | `beforeToolCall`, `afterToolCall`, `finishTurn`, context/effort hooks; explicit sequential execution |
| [PI4](evidence/source_excerpts.md#pi4) | `packages/agent/src/agent-loop.ts`: finish decision 286, context 381, execution mode 508, preparation 708, after hook 859 | Exact control points; no invented hook semantics |
| [PI5](evidence/source_excerpts.md#pi5) | `packages/coding-agent/src/core/agent-session.ts`: public `agent` 380; hook installation 649; boundary composition 887 | Compose installed hooks and preserve persistence/settlement |
| [PI6](evidence/source_excerpts.md#pi6) | `packages/coding-agent/src/core/extensions/types.ts`: ToolCallEventResult 1454, ToolResultEventResult 1483 | Blocking is supported; tool-result termination is not exposed by this extension result type |
| [PI7](evidence/source_excerpts.md#pi7) | `packages/coding-agent/src/extensions/mcp/tools.ts`: schema 291, `createMcpToolDefinition` 311 | MCP tools remain a standard extension/tool interface |
| [PI8](evidence/source_excerpts.md#pi8) | `packages/ai/src/api/openai-responses-shared.ts`: image detail 82, message conversion 156, tool conversion 385 | Provider-specific history and tool serialization |
| [PI9](evidence/source_excerpts.md#pi9) | `packages/ai/src/utils/validation.ts`: argument validation 317 | Type/schema validation does not validate the free-form action mini-language |
| [C1](evidence/source_excerpts.md#c1) | `codex-rs/models-manager/src/model_info.rs`: overrides 49, fallback 124 | Coding prompt and fallback metadata |
| [C2/C3](evidence/source_excerpts.md#c2) | `codex-rs/tools/src/json_schema.rs` 41 and `responses_api.rs` 127 | Schema subset/order and `strict=false` |
| [C4/C5](evidence/source_excerpts.md#c4) | `core/src/tools/context.rs` 117 and `core/src/mcp_tool_call.rs` 128 | Result formatting and MCP dispatch |

## What can and cannot be attributed

The chain **raw action → parser → applied action** permits a deterministic local explanation of semantic substitutions. Likewise, **terminal tool result → loop continuation → final model reply** identifies avoidable request exposure. The source and logs jointly support those mechanisms.

The chain **system prompt/schema/history packaging → model-selected target/height/bearing → physical success** does not isolate one component from historical trajectories. Many paired episodes diverge on their first action, before accumulated history can explain the difference; stochastic generation, prompt, tool serialization and image packaging all remain candidates. Later steps no longer share the same physical state. Calling the entire difference “the original harness design” is too coarse to guide a reliable edit.

The actionable strategy is to fix provable contract/control-flow problems, then separately evaluate target/phase memory, completion, context and effort policies with the per-task regression evidence. None of the existing logs demonstrates that Pi intrinsically understands support contact or that changing a system prompt alone will repair a particular failure.
