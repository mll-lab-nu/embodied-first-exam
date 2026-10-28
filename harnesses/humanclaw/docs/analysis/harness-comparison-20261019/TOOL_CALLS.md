# P3 — Tool calls and the harness execution loop

## Complete executed-action census

These counts cover the final episodes. They include all task types; therefore total Sit counts differ from the interaction-only Sit table in [OUTCOMES.md](OUTCOMES.md).

| Executed tool | PSV r1 | Codex r1 | Pi r1 | Codex r2 | Pi r2 | Codex r3 max | Pi r3 xhigh | Codex Gemini | Pi Gemini |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| walk_forward | 43,993 | 25,008 | 23,903 | 26,060 | 25,579 | 24,201 | 25,645 | 20,998 | 19,811 |
| turn | 20,083 | 12,951 | 12,477 | 13,871 | 14,185 | 16,420 | 17,135 | 16,193 | 15,356 |
| side_walk | 5,607 | 4,330 | 4,098 | 5,602 | 5,103 | 6,458 | 5,971 | 4,982 | 4,075 |
| step_back | 1,075 | 412 | 313 | 1,014 | 984 | 1,217 | 1,351 | 591 | 500 |
| sit | 1,421 | 669 | 675 | 1,671 | 1,734 | 2,202 | 2,284 | 1,362 | 1,289 |
| stand | 842 | 1,218 | 1,218 | 1,217 | 1,218 | 1,217 | 1,218 | 1,180 | 1,165 |
| step_climb_up | 531 | 802 | 843 | 1,285 | 1,343 | 1,646 | 1,916 | 246 | 236 |
| step_climb_down | 90 | 56 | 41 | 69 | 55 | 109 | 66 | 56 | 41 |


Total: **460,783 environment actions**. Each accepted tool executes one action. Stop commits the current pose and ends the episode; it generates no motion. The other actions generally generate a 15-frame, approximately 0.5-second chunk.

## What MCP does here

MCP provides the shared environment-tool interface: discovery of eight schemas, argument delivery, return of a public result and image, and error propagation. It does not select actions, solve the task, run a separate planner, or compute benchmark success.

The public tool result contains `request_id`, incremented `observation_id`, normalized `action`, `done`, and terminal `termination_reason`, plus the next ego image. It does not expose evaluator target distance, contact correctness, privileged scene state, or success reward. `visible_state` is supplied by the model in the request, not independently measured perception.

```mermaid
sequenceDiagram
    participant Model
    participant Native as Codex or Pi
    participant Transport as HumanCLAW provider transport
    participant MCP as HumanCLAW MCP bridge
    participant Env as HumanCLAW environment
    Native->>Transport: Assemble request from system text, tools and history
    Transport->>Model: Apply configured image window; send provider request
    Model-->>Native: Tool name and arguments
    Native->>MCP: Dispatch tool call and wait
    MCP->>MCP: Validate observation ID and request ID
    MCP->>Env: Execute one accepted action on environment owner thread
    Env-->>MCP: New saved observation and environment status
    MCP-->>Native: Public result plus image
    Native->>Native: Append call/result and continue model loop
```

Codex starts a fresh native thread and one outer `turn/start`; many model/tool cycles occur before `turn/completed`. Pi starts a fresh RPC prompt and waits through native retries until `agent_settled`. Pi's per-cycle `turn_start` is not equivalent to Codex's outer turn.

## Responsibilities and observed activity

| Responsibility | Implementer in these runs | Evidence |
|---|---|---|
| Generic agent instructions, native tool catalog, conversation assembly | Native Codex/Pi | Actual request payload summaries |
| Decide the next action and parameters | Astra or Gemini model | Returned function calls and visible-state claims |
| Dispatch MCP calls, wait, append results, continue the loop | Native Codex/Pi | Dispatch spans and raw native events |
| Embodied task text and eight action contracts | HumanCLAW | Pinned `environment.py` and actual tool definitions |
| Keep only first plus recent images | HumanCLAW provider transport | Request-normalization records, shared across native harnesses |
| Validate freshness/idempotency and serialize simulator access | HumanCLAW MCP bridge | Pinned `EnvironmentBridge.call` and owner-thread queue |
| Generate motion, run physics, compute metrics | HumanCLAW | `motion.generate`, environment and metric spans |
| Native Pi transient-request recovery | Pi | `pi.auto_retry` events |
| Gemini empty-response recovery | HumanCLAW provider transport | Saved source and failed `EmptyResponse` request spans |

The native harness is therefore an active **request/history and execution-loop runtime**, even when its file, shell, web, or multi-agent tools are unused. Conversely, image capping and physical action validation should not be credited to native Codex/Pi.

| Condition | Environment dispatches | Executed actions | Argument rejections | Pi auto-retry spans | Failed model requests |
| --- | --- | --- | --- | --- | --- |
| Codex r1 | 45,475 | 45,446 | 29 | — | 88 |
| Pi r1 | 43,568 | 43,568 | 0 | 165 | 170 |
| Codex r2 | 50,831 | 50,789 | 42 | — | 11 |
| Pi r2 | 50,201 | 50,201 | 0 | 46 | 46 |
| Codex r3 max | 53,474 | 53,470 | 4 | — | 352 |
| Pi r3 xhigh | 55,586 | 55,586 | 0 | 308 | 343 |
| Codex Gemini | 45,608 | 45,608 | 0 | — | 1,643 |
| Pi Gemini | 42,473 | 42,473 | 0 | 66 | 3,602 |


Native Pi retry spans completed successfully in the final cohort: r1 **165**, r2 **46**, r3 **308**, Gemini **66**. These are retry episodes at the native-event boundary, not necessarily every underlying failed HTTP request. Codex may recover within its own request loop without a correspondingly instrumented Pi-style retry span. Counts are not comparable retry-policy effectiveness estimates.

For Codex r2, **50,831 dispatches = 50,789 executions + 42 rejected calls**. The raw capability table's requested total is 50,873 because rejection accounting includes an additional request event. It is not evidence for 42 additional physical actions. For PSV, the 4,193 rejected action proposals are verifier overrides, a different mechanism from schema validation.

The model-request totals also reconcile with the loop: Codex r2's **52,060 = 50,789 actions + 1,218 episode-ending requests + 42 rejected-action requests + 11 failed requests**. Pi r2's **51,465 = 50,201 actions + 1,218 episode-ending requests + 46 failed requests**. Across the six native Astra cohorts, the analogous aggregate accounting holds, with Codex r3 additionally including its 12 plan-update requests. This accounts for the native loop's requests without introducing a separate planner/verifier call per action.

## All generic native tools

| Codex native tool | r1 requests | r2 requests | r3 requests | Gemini requests |
| --- | --- | --- | --- | --- |
| create_goal | 0 | 0 | 0 | 0 |
| exec_command | 0 | 0 | 0 | 1 |
| get_goal | 0 | 0 | 0 | 0 |
| list_mcp_resource_templates | 0 | 0 | 0 | 0 |
| list_mcp_resources | 0 | 0 | 0 | 0 |
| multi_agent_v1__close_agent | 0 | 0 | 0 | 0 |
| multi_agent_v1__resume_agent | 0 | 0 | 0 | 0 |
| multi_agent_v1__send_input | 0 | 0 | 0 | 0 |
| multi_agent_v1__spawn_agent | 0 | 0 | 0 | 0 |
| multi_agent_v1__wait_agent | 0 | 0 | 0 | 0 |
| read_mcp_resource | 0 | 0 | 0 | 0 |
| request_user_input | 0 | 0 | 0 | 0 |
| update_goal | 0 | 0 | 0 | 0 |
| update_plan | 0 | 0 | 12 | 0 |
| view_image | 0 | 0 | 0 | 0 |
| web_search | 0 | 0 | 0 | 0 |
| write_stdin | 0 | 0 | 0 | 0 |


Pi exposes `read`, `bash`, `edit`, and `write`; each has **zero requests and executions** across its four final cohorts. Codex r1 and r2 also have zero generic native tool requests.

These catalogs were exposed to the model. The HumanCLAW prompt directs it to use the eight environment tools, and the observation images already arrive in context, so file/shell/image-reading tools have little task relevance. Codex's request uses automatic tool selection, not an eight-tool-only allowlist. The evidence supports prompt-directed tool choice rather than catalog removal. Exposure alone does not prove a tool would execute successfully: the later shell failure is a concrete counterexample.

Two exceptions appear in later Codex conditions:

- **r3: 12 `update_plan` requests across three episodes**, four each in shards 0176, 0713, and 0937. The summary's execution column is zero because these updates lack a generic tool-execution span. A focused raw-event audit confirms **12 `turn/plan/updated` events**. The plans cover locating the target, reaching it, sitting, and submitting the pose. One of the three tasks succeeds; two fail. This tiny self-selected sample does not establish a planning benefit.
- **Gemini: one `exec_command` attempt**, in shard 0295, requesting `ls -la`. Native command execution fails with exit 101 because the Codex sandbox launcher cannot find `bwrap`. The embodied task still succeeds. This historical command was only inspected; it was not executed during this analysis.

Thus “the native tools were never called” is accurate for the audited r1/r2 generic catalogs, but not for all conditions. Actual detailed events override an incomplete summary interpretation.

No native compaction execution is recorded in the final capability census or inspected context traces. This concerns recorded native behavior; provider-internal context management is not observable.

## PSV's distinct call chain

`Current image + bounded text history → percept_mid_low (plan + skill) → conditional verifier → normalized action → environment → history update`.

PSV calls `percept_mid_low` **73,642 times**, once per decision, despite the configuration's plan-horizon terminology. It calls the verifier **49,378 times**, on **67.05%** of decisions. The verifier overrides **4,193 proposals**: 3,343 Walk, 437 Turn, 336 Stop, and 77 Climb-up proposals. That is **8.49% of verifier calls**. The resulting alternative action is executed once, not in addition to the rejected proposal.

This architecture produces **123,047 model calls**, including recorded retries, versus 73,642 decisions. Its gains cannot be attributed to the verifier alone: it also uses a different prompt and explicit sitting-sequence instructions.

## Evidence

- [Full capability ledger](tables/capabilities.csv): registration, exposure, requests, rejection, execution, completion, failure and timing.
- [All action chains](evidence/action_chains.jsonl.gz) and [transition counts](tables/action_transitions.csv).
- [209 context/call-chain audits](evidence/selected_trace_audit.jsonl.gz).
- [Six focused audits](evidence/focused_trace_audit.jsonl.gz): three native-plan episodes, one native-command episode, and the r1/r2 wording example.
