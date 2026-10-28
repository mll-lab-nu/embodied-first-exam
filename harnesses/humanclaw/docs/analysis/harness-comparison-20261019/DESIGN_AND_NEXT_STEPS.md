# General self-evolving Pi harness: design and validation

## Approved objective

Build a general harness on the Pi SDK that reads public environment documentation and interfaces, autonomously discovers tools, reuses or generates the required bindings, verifies their scope and repairs them from execution evidence. HumanCLAW, RoboCasa365, and RoboDojo are initial validation environments. New benchmarks must not require a human-written Binding, capability manifest or semantic mapping, or a benchmark-specific branch in the core decision loop.

**Autonomous Interface Adaptation was confirmed on 2026-10-26.** A Binding is a versioned runtime artifact produced or reused by the harness. Developers provide generic access, program execution and resource infrastructure once; the user supplies the task/environment entry, authorized access and budgets. The harness discovers the remaining interface and lifecycle semantics from public evidence.

The user approved these choices on 2026-10-25:

- **1A — Progressive discovery:** confirm the capabilities needed for execution first, then discover and verify additional capabilities as the task requires.
- **2A — Incremental skill publication:** automatically validate candidates and publish new versions when checks pass; subsequent tasks may use them.
- **3A — Tool and task-policy repair:** support adaptation of tools, adapters, skills, reasoning, observation, and verification strategies in the first complete version.
- **V-A — Typed validation:** use programmatic and behavioral checks appropriate to the candidate; add a separate-context model review for critical task-policy changes or conflicting evidence.
- **P-A — Scoped publication:** automatically publish candidates only within their validated scope after the type-specific gates pass. Unpublished candidates do not enter a later task's trial pool.
- **R-A — Attributed rollback:** quarantine a confirmed hard defect immediately; also quarantine repeated, attributable behavioral failures within comparable conditions.
- **S-A — Hybrid retrieval:** filter by compatibility, combine lexical and semantic retrieval, and rank using scope fit, goal fit, comparable evidence, and cost.

This document replaces the earlier design and experimental queue. It describes the target architecture; the implemented task-local slice is tracked in [the pilot runbook](../../ADAPTIVE_PILOT.md). The [implementation plan](../pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md) owns detailed contracts, migration tasks, and acceptance gates. Existing code supplies building blocks to integrate into the replacement architecture.

## Architecture

Pi owns model interaction and the session lifecycle. A stable execution authority owns environment mutation and its accounting. Discovery, state estimation, context selection, and task policies operate above that boundary. Generated tools and skills use the same boundary as native tools.

| Module | Responsibility | Outputs and evidence |
|---|---|---|
| Pi Runtime Bridge | Create sessions, connect lifecycle events, deliver decisions, and settle completed sessions | Model requests, session events, decision boundaries, and lifecycle state |
| Environment Discovery | Locate and read permitted schemas, documentation, public clients, examples, resources and dependencies; plan targeted discovery and verification | DiscoveryRecords, versioned capability claims, provenance, unknowns, adapter requirements and constraints; registry lookup alone is insufficient |
| Capability & Tool Registry | Track native, generated, and third-party tools; select the relevant exposure set | Schemas, dependencies, side effects, permission requirements, implementation versions, and validation evidence |
| Execution Broker | Admit and account for discovery probes and environment operations; run validated adapter mappings through generic managed transports | Durable requests, execution receipts, timing, budgets and uncertain-outcome state without per-benchmark dispatch branches |
| Evidence & Task State | Maintain observations, entities, subgoals, hypotheses, and failure evidence | State with source references, uncertainty, freshness, and dependencies |
| Decision Policy | Select reasoning, observation, computation, execution segments, verification, repair, or termination | Expected outcomes, selected actions, verification criteria, and versioned policy changes |
| Context Builder | Assemble relevant evidence, state, tool descriptions, and skills for each request | Complete call/result exchanges, selected artifacts, and explicit retention decisions |
| Workspace & Skill Lifecycle | Reuse public clients or synthesize adapters, manage scientific resources/dependencies, and construct, validate, repair and publish capabilities | AdapterArtifacts, episode programs, immutable candidates, validation reports, scoped releases, retrieval evidence and quarantine history |
| Transport & Audit | Adapt provider requests and record the complete loop | Delivered model settings, usage, errors, source fingerprints, and correlated execution events |

These are logical responsibilities, not a requirement for separate services, processes, or agents. Hooks connect modules; they do not become an additional policy implementation.

Autonomous Interface Adaptation spans Discovery, Workspace/Validation, Registry and Broker within these nine modules. It is part of the normal Pi loop, not a required additional agent or a manually implemented integration stage.

Keep four concepts distinct:

- **ModelCapabilities:** provider/model support for reasoning settings, images, tool formats, and request limits.
- **EnvironmentCapabilities:** public actions, observations, coordinate conventions, constraints, budgets, and lifecycle semantics.
- **ToolRegistry:** actual implementations available to the agent, including native interfaces and constructed capabilities.
- **RuntimePolicy:** stable execution rules, retry ownership, minimum validation requirements, and experiment-mode settings. Replaceable task policies separately select reasoning, context, observation, verification, and recovery within those boundaries.

A model's unsupported setting cannot become valid because an environment description mentions it. A tool's presence does not establish that its semantics, permissions, or behavior have been verified.

## Autonomous Interface Adaptation and progressive discovery

The required path is **Bootstrap → Source / Interface Discovery → Capability Declaration → Client Reuse or Adapter Synthesis → Contract Verification → Tool Registration → Execution Feedback / Repair**.

`BootstrapSpec` supplies the task, environment/public-resource entry, authorized access, generic transport availability, budgets and initial snapshot. It does not require human-provided robot dimensions, action lists, sensor mappings or success interpretation. MCP/HTTP/Python, file/resource access and managed programming are general infrastructure; discovered adapters supply environment-specific semantics.

Discovery actively reads public docs, clients, schemas and examples, follows allowed references and checks available dependencies. `DiscoveryRecord` captures the question, sources/hashes, findings, admitted probes, remaining unknowns and next step. Listing or looking up existing ToolRegistry entries is separate: an empty registry must not prevent discovery. Support both schema/introspection interfaces and public documentation/client-only interfaces.

Before an effectful operation, establish its critical inputs, effects, permission, limits and outcome semantics. Prefer public source inspection, independent fixtures and permitted read queries; a method name or HTTP verb does not prove that a call is read-only. A bounded validation probe is admitted under the normal contract, and only its actual evidence can verify the corresponding capability. Missing critical information blocks dependent work without fabricating support.

The harness reuses an environment-shipped public client when appropriate or generates a missing binding as `AdapterArtifact`: immutable implementation/mapping, source/protocol/schema/dependency identities, codecs, units/frames, effects, budget/lifecycle semantics, validated scope and local/publication eligibility. Register the checked scope at a settled boundary. Feedback can reopen discovery, invalidate dependent claims and trigger a repaired version; uncertain execution is reconciled before changing or retrying physical work.

**Adapter Artifacts** establish how to call an environment. **Task Skills** establish how to achieve an outcome using those interfaces. An adapter's verified transport does not establish successful grasping, planning or task completion. Existing handwritten bindings remain explicit pilot baselines or test fixtures; they cannot serve as hidden fallbacks in autonomous-adaptation trials.

Each capability claim records:

- Source and version: schema, permitted documentation, observed response, inspected code, or inference.
- Origin: environment-native, existing skill, third-party dependency, or generated implementation.
- Verification status: `declared`, `verified`, `inferred`, `unknown`, or `unsupported`; record invalidation and its cause separately when earlier evidence no longer applies.
- Input/output semantics, units, frames, preconditions, dependencies, and side effects.
- Verification evidence, uncertainty, and the conditions under which the claim should be revisited.

Discovery produces a working capability model rather than a one-time declaration. New observations can invalidate a plan, reduce confidence in a tool, or trigger re-verification of a dependent skill. Explicit benchmark constraints remain authoritative; an inferred capability cannot expand permissions or alter success criteria.

Cache discovered identities and local artifacts within a task. Later ordinary tasks retrieve only eligible published adapters from their pinned snapshot, rechecking endpoint/protocol/dependency compatibility and instance-dependent facts. Unpublished adapter caches cannot bypass P-A, and previously evaluated tasks cannot silently warm a cold-start test.

Sensor capabilities are discovered independently. RGB-D, calibration, robot state, and contact information are not universal assumptions. A benchmark that exposes only RGB remains an RGB-only condition unless its public observation protocol explicitly changes. Hidden evaluator labels, target poses, and private success signals must not enter policy inputs.

For EFE, this means the harness reads the public client/protocol and actual service spec, discovers optional kinematics and native action types, and builds only missing mappings. Neither RoboDojo nor RoboCasa365 requires a developer-authored Binding. A new interface outside EFE uses the same source-to-adapter process; a shared EFE protocol alone is insufficient evidence of broad adaptation.

## Execution authority and persistent state

Every operation that changes the environment passes through the broker, including calls made inside generated programs. The broker fixes request identity, relevant observation references, implementation version, and policy version before dispatch.

Distinguish:

- Rejection before execution.
- Accepted or running execution.
- Confirmed completion or confirmed failure.
- An indeterminate outcome in which an effect may already have occurred.

A timeout while waiting does not establish that motion stopped. An uncertain physical execution must not be replayed automatically. Recovery requires a supported status check, observation, confirmed stop, or explicit termination handling appropriate to the environment.

Use independent accounting for model decisions, pure computation, observations, environment submissions, controller steps, simulated time, and wall time. One bounded trajectory submission may contain multiple low-level control steps. A pure computation need not create a fresh robot observation or consume a physical-action count. Some observation operations advance simulation time, so effect classification must be based on semantics rather than names.

Preventing bypass requires an enforced deployment boundary. Generated adapters prepare operation descriptors and decode results; trusted generic transports perform the admitted dispatch under its identity, effect classification and budget. The kernel does not need handwritten endpoint code for each benchmark. Generated processes must lack unrestricted simulator credentials or endpoint access, or be confined by an equivalent mechanism. Working directories, prompt instructions, and wrapper conventions alone do not establish this property. A deployment that cannot enforce the boundary must report that limitation instead of claiming broker-only execution.

Maintain three forms of state separately:

1. **Raw evidence:** observations, images, depth, calibration, robot feedback, tool results, and execution receipts.
2. **Derived task state:** entities, subgoals, current hypotheses, dependencies, uncertainty, failure attempts, and completion evidence.
3. **Program state:** code artifacts, interfaces, dependency versions, validation results, and active tool/policy implementations.

Context projection selects from these stores; it must not erase the underlying evidence when a message or artifact leaves the model context.

## Decision and execution loop

1. **Update evidence and task state.** Incorporate the latest observation or execution result, retaining contradictions and unknown outcomes. Reopen discovery when an interface is missing or an adapter assumption is invalidated.
2. **Select a computation strategy.** Choose reasoning effort, interface discovery/adaptation, additional observation, skill retrieval, numerical analysis, tool construction, or a direct action.
3. **Build the request context.** Include the relevant capability claims, task state, evidence, tools, and skill interfaces.
4. **Form the next operation.** Record its purpose, expected outcome, and how that outcome can be checked.
5. **Admit and execute.** Freeze the relevant versions, enforce the execution contract, and obtain a correlated result or explicit uncertain state.
6. **Compare expectation with evidence.** Separate actual progress, missing information, tool defects, false capability assumptions, and physical execution failures.
7. **Revise the next decision.** Continue, observe, replan, repair, downgrade a capability claim, or terminate according to the evidence.

Completion is task-dependent. Track the agent's completion claim, environment termination, and evaluator success as distinct events. A successful API return does not prove task success, and an occluded target does not by itself disprove completion. Use the available public evidence and the environment's declared lifecycle.

Feedback may change reasoning effort, observation selection, action-segment length, verification, tool choice, or the plan. More reasoning is one response among several. For example, geometric uncertainty may call for another view; a wrong coordinate transform may require program repair; uncertain execution requires reconciliation rather than another action.

Use normal episode budgets. Do not add a high-effort proportion cap or a separate reasoning cutoff. Numerical checks and public robot feedback can trigger policy changes when available; the model's own assessment remains evidence to evaluate, not sensor truth.

## Autonomous construction and repair

When capability is missing, inspect the current environment interface, the skill library, and permitted dependencies or tool sources before constructing a new implementation. Selection considers capability fit, validation cost, remaining budget, and expected reuse.

Episode-local programs can perform geometry, kinematics, trajectory generation, or analysis. Stable execution entry points can run these programs without adding every temporary helper to the model's tool schema. Expose a new callable tool when its reusable interface and evidence justify doing so.

This requires a task-persistent Scientific Workspace with permitted dependency discovery/setup and original public resource access, not only the pilot's stdlib-only snippets. Programs can use NumPy/SciPy or an equivalent available runtime and binary RGB-D handles with calibration, frames, units and time metadata. The Context Builder projects relevant images/summaries; numeric arrays remain available to code. Dependency setup and client execution consume the normal budget and cannot bypass managed environment transport.

The first complete version permits repair of:

- Adapter code and parameter mappings.
- Generated tools and skill implementations.
- Task policies, including reasoning, observation, verification, and recovery rules.

Candidate changes receive versions and appropriate checks before activation. Switch the active reference at a decision boundary with no in-flight environment mutation; ongoing operations retain the versions they started with. Stable hooks should be installed once rather than repeatedly wrapped during updates.

Represent replaceable task policies as versioned structured rules: trigger conditions select reasoning, observation, verification, recovery, or planning actions, and may reference versioned functions for more complex calculations. Store the parent version, rationale, changed rules, affected capabilities, and required checks with every candidate. This makes a policy change inspectable without turning the stable hooks into mutable policy code.

The execution kernel, environment permissions, and benchmark success criteria remain outside task-policy self-modification. Code rollback restores an implementation version; it cannot restore physical state. A tool that ran successfully but produced the wrong geometric meaning still requires repair.

## Automatic validation

The validation lifecycle is `ValidationProtocol → ValidationJob → ValidationReport → ReleaseDecision`. Validation establishes eligibility for a particular scope; it does not establish universal correctness.

| Record | Required content |
|---|---|
| ValidationProtocol | Versioned minimum checks, candidate types, independence requirements, local activation gates, publication gates, and resource limits |
| ValidationJob | Frozen candidate and parent hashes, dependencies, applicability scope, protocol version, test cases, oracle versions, environment/reset permissions, and budget |
| ValidationReport | Every case's `pass`, `fail`, or `inconclusive` result; raw evidence references, actual conditions, costs, regressions, and unresolved observations |
| ReleaseDecision | Separate local-use and publication eligibility, reasons, permitted scope, report references, and the exact version selected for activation or publication |

A job is frozen before execution. A later code, dependency, scope, oracle, or material test change creates another job; reusable evidence must retain its origin and demonstrate that its assumptions still apply. A candidate may propose additional tests but cannot weaken the protocol's minimum requirements or approve its own missing evidence.

Checks depend on the candidate's effect:

| Candidate type | Verification method |
|---|---|
| Pure computation | Known input/output pairs, independent reference calculations where available, mathematical invariants, boundary cases, invalid inputs, and semantic checks for frames and units |
| Interface adapter | Independent schema/codec and semantic-mapping checks against public sources/reference cases, dependencies, lifecycle/effect checks and permitted probes. Effectful paths additionally need the action checks; interface fidelity does not imply task success. |
| Environment action | Interface and effect checks, broker-only dispatch, preconditions, fresh execution in a permitted environment, observable postconditions, and required regression cases |
| Task policy | Decision legality, evidence requirements, termination and recovery behavior, then new execution evidence for changed decisions and their effects |
| Composite skill | Constituent checks plus state transfer between steps, shared preconditions, failure handling, and end-to-end postconditions |

The result oracle must have a basis independent of the candidate's own success claim, such as a public environment check, a known reference result, an invariant, or separately grounded observation evidence. Repeating the candidate's calculation or asking it whether it succeeded is insufficient. If no permitted evidence can resolve the required outcome, report `inconclusive`; model agreement does not turn that result into a pass.

V-A adds a model review only when a policy changes completion evidence, reduces observation or verification, changes recovery execution, or when evidence conflicts or a necessary check remains ambiguous. The reviewer uses a separate context containing the candidate, public contract, and evidence, and may request counterexamples or additional checks. This review supplements the same mandatory checks and behavioral evidence; it cannot waive them. Routine candidates do not require an extra model call.

Saved trajectory replay can verify interface handling, decision legality, and context processing. When a new policy changes an action, the old trajectory's later observations cannot demonstrate its effect; obtain new permitted execution evidence. Local eligibility may permit bounded use in the originating task after the relevant checks, while publication eligibility requires the cross-task gates below. Neither eligibility grants extra environment permissions or attempts.

Initial adapter synthesis and scoped use must not wait for a publication-sized panel or a solved benchmark task. Distinguish passing pre-dispatch checks, permission to run a bounded validation probe and capability verification from the returned evidence. For cross-task release, apply the existing gates by actual effects: conversion-only adapters use the computational gate; non-mutating observation/status/resource adapters also require permitted live read checks for their transport behavior. Action-dispatch adapters, including observations that advance simulation or mutate task state, also meet action gates for their claimed interface/control postconditions. Do not substitute protocol success for a Task Skill's behavioral evidence.

Separate construction examples, publication-validation cases, and final evaluation data. Select publication cases after freezing the candidate and retain the selection record. If validation results inform a revision, create a new candidate and rerun affected checks; do not relabel an exposed validation case as fresh independent evidence. Keep every failure and inconclusive result. Public task evidence may support a declared check, but hidden evaluator information remains inaccessible.

## Skill publication and cross-task learning

A skill is a reusable method with a declared scope, not merely a successful transcript or a script containing task-specific coordinates. Its package includes:

- Required capabilities and input/output interfaces.
- Preconditions, dependencies, and coordinate assumptions.
- Executable implementation or a task strategy.
- Verification procedures and expected outcomes.
- Known failure modes and recovery options.
- Evidence, applicability limits, implementation version, and validation version.

Keep an episode workspace, an unpublished candidate store, and a published skill store separate. A candidate may be used locally after the relevant activation checks or executed by an explicitly permitted validation job. P-A does not expose it to later ordinary tasks as a trial skill. Those tasks retrieve only versions in their published starting snapshot.

The initial publication gates below are engineering defaults, not statistical reliability guarantees. The [implementation plan](../pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md) owns their precise definitions and acceptance fixtures. The protocol must fix the cases, comparison conditions, and mandatory checks before evaluating the candidate; collecting only favorable outcomes is invalid.

| Candidate type | Initial publication gate |
|---|---|
| Pure computation | At least 24 distinct cases covering applicable normal, boundary, and invalid-input families; every mandatory check passes |
| Environment action skill | At least 12 independent validation trials across at least 3 condition groups, success fraction at least 11/12 (11 successes for the minimum panel; round up for larger panels), all mandatory contract and regression checks pass, and no confirmed hard defect |
| Replacement task policy | At least 12 matched trial pairs with the parent version; candidate success count is no lower, no predefined critical condition group regresses, every mandatory check passes, and cost changes are fully reported |

Count independent attempts, not multiple frames or repeated checks from one attempt. An inconclusive attempt is not a success and cannot be silently discarded or replaced to improve the record; unresolved critical execution or oracle ambiguity blocks publication. An ordinary, fully diagnosed task miss can be distinct from a hard implementation defect, which always blocks publication. Where a parent comparison is required, missing matching conditions or unavailable legal trials leave the candidate provisional. A new behavior policy without a parent uses the environment-action gate; a purely computational strategy uses the computational gate. Neither can claim superiority or replace an existing policy without the required comparison, and a replacement cannot discard its parent identity to bypass that requirement.

Publish automatically once all applicable gates pass; no routine human approval is inserted. A release contains an immutable implementation, dependency and validation references, and validated applicability scope. Widening that scope creates a new candidate and requires new evidence. Multiple versions can coexist; the newest release does not automatically become the best choice.

Discovery, construction, and validation within a task consume its episode budget. Library-level validation after the episode ends uses a separately predefined resource budget and contributes to cumulative cost. It may use saved public evidence or an explicitly permitted validation environment; it cannot resume the ended evaluation episode, grant extra benchmark actions, resets, or attempts, or change a fixed evaluation cohort's starting snapshot. Insufficient resources or evidence leaves a candidate provisional.

Episode workspaces and the persistent skill store have separate lifetimes. A task starts from an identified snapshot and may adapt locally. Publication makes a version available to later tasks and does not silently replace a running task's frozen dependencies.

Store code and evidence as content-addressed artifacts. SQLite holds manifests, candidate and release state, validation reports, snapshot membership, usage outcomes, and audit references; FTS5 supplies the lexical index. Commit a release record and its required references in one transaction after checking the referenced artifacts. A semantic index records the artifact hash and embedding configuration, so a changed embedding index cannot silently change a frozen evaluation configuration. The index is derived data; a missing or stale entry does not create a new skill version or bypass compatibility filtering.

## Quarantine, rollback, and recovery

R-A distinguishes execution uncertainty and changing conditions from software defects before modifying trust in a skill.

| Event | Required response |
|---|---|
| Unknown execution outcome | Reconcile receipts and public observations before another conflicting action; preserve all audit evidence, but do not count an unknown result as an attributable failure |
| Changed precondition or capability | Stop using the mismatched scope, update discovery and state, and replan; do not declare an implementation defect solely from a changed environment |
| One confirmed hard defect or contract violation | Immediately block new use and quarantine the affected version or reliably identified scope; create a repair candidate |
| First ordinary behavioral failure | Perform a bounded diagnosis before repeating the attempt; distinguish state/observation errors, environment changes, and implementation or policy errors |
| Two same-class attributable failures among up to the latest five independent, condition-matched, decidable uses | Quarantine the affected scope and trigger repair; two qualifying failures can trigger before five uses accumulate |

The behavioral window is scoped to the version and comparable conditions, with stable attempt identities and recorded attribution evidence. Multiple checks on one attempt count once. Unknown outcomes remain in the audit log and outside this window until resolved; the two-of-five rule is an operational heuristic, not a causal proof. Quarantine conservatively covers the whole version when the affected scope cannot be isolated reliably.

Blocking new use can happen immediately, but changing an active reference requires settled execution and no in-flight environment mutation. Recheck an older version's interface, dependencies, permissions, current preconditions, and validation scope before selecting it. If none is suitable, return to discovery, planning, or construction. Software rollback never restores the world: refresh physical state and choose an environment-supported recovery action independently.

Do not mutate a published manifest to erase failures or shrink its original claim. Append a quarantine or scope restriction, and publish repaired code or a revised scope as a newly validated version. Retain failure evidence alongside successful uses. A task may stop using a bad version locally within a frozen evaluation protocol. A global withdrawal that changes later episodes' starting capability set requires a new cohort or an explicitly reported protocol change; do not silently alter the fixed snapshot.

## Skill retrieval and use

S-A queries the library with the current subgoal, intended effect, available capabilities, state and observation requirements, allowed side effects, remaining budget, and recent failures. Retrieval follows these steps:

1. **Select the permitted snapshot.** Query its released versions and apply the task's local quarantine state. The current task's eligible local tools remain in a separate task registry, not published-snapshot membership; never treat unpublished candidates from other tasks as released skills.
2. **Filter required conditions using three-valued compatibility.** Exclude known mismatches in capabilities, permissions, interfaces, dependency versions, and scope. Place unknown requirements on a discovery queue, not an executable shortlist. A verified adapter chain may satisfy a requirement when its own scope and cost are included.
3. **Retrieve by keywords and semantics.** Search compatible skills with both lexical and semantic indexes, merge and deduplicate by version, and retain provenance for each match. Semantic similarity cannot override a failed compatibility condition.
4. **Rank with visible reasons.** Prefer validated scope fit, then intended-effect fit, evidence from comparable conditions, and expected execution/loading/validation cost. Retain success, failure, and sample counts separately; one successful trial does not outrank stronger matching evidence merely by having a higher raw rate.
5. **Load progressively.** Present at most 8 summary cards, and load at most 3 full skill bodies on demand for the current retrieval round. Pi selects in its normal decision call; an extra model reranking call is not mandatory. Log selected and rejected versions and the material reasons.
6. **Recheck before invocation.** Validate dynamic preconditions and applicable quarantine state, then freeze the selected version with the execution request. If no candidate is suitable, discover missing capability or construct a tool rather than forcing a weak match.

New use outcomes update the condition-specific evidence ledger and can trigger R-A. Retrieval does not rewrite the immutable release or silently change a running task's pinned dependencies. In fixed-snapshot evaluation, evidence from earlier evaluated tasks cannot change the next task's initial ranking state; continual-learning mode may explicitly use that accumulated evidence and must record the sequence and versions.

Cross-task improvement requires measuring negative transfer, retrieval misses, and construction/validation cost, not only the number of accumulated skills.

## Existing code to reuse and responsibilities to replace

| Existing foundation | Reuse | Replace or generalize |
|---|---|---|
| Pi SDK runner and lifecycle hooks | Session creation, event transport, persisted sessions, and request hooks | Benchmark-bound startup, fixed tool assumptions, and logic embedded in hooks |
| Current controller | Useful admission, memory, reasoning, and completion mechanisms | Split execution admission, task state, decision policy, and completion evidence into their owners |
| Context projector | Complete exchange handling, raw-log preservation, budget checks, and retention auditing | Observation-count grouping and assumptions that every result has a HumanCLAW image |
| MCP schema retrieval and registry lookup | One discovery source and the registered-tool exposure mechanism | Add autonomous public-source/client/dependency discovery; registry enumeration cannot stand in for Environment Discovery |
| Environment bridge and LIBERO request journal | Single execution ownership, durable request identity, receipts, and uncertain-outcome handling | Benchmark-specific counters, termination assumptions, and any path that bypasses the common authority |
| Provider transport and experiment recording | Delivered requests, native events, usage, and source/runtime fingerprints | Extend correlation across construction, repair, policy changes, and skill publication |
| Pi programming and extension mechanisms | Workspace inspection, program execution, dependency access, and resource loading | Add autonomous binding synthesis, scientific/binary resources, scoped validation/registration and persistent adapter/skill lifecycle |

Codex's workspace-centered programming, inspection, tool discovery, and repair inform these mechanisms. Pi remains the model/session runtime; adding a second Codex decision loop is not required.

## Future validation route

Validation follows the implementation milestones in the main plan. M1 supplies generic access, workspace and broker foundations; M2a performs autonomous discovery and M2b synthesizes/verifies a binding through the first valid interaction; M3 repairs interfaces and task policies; M4 publishes eligible adapters/skills. Start real-environment minimal interactions during M1–M3, with systematic heterogeneous evaluation in M5. A runnable pilot or an injected manual binding does not satisfy these autonomous gates.

| Validation area | Question | Required evidence |
|---|---|---|
| Execution contract | Does every admitted environment mutation have a durable, accountable lifecycle? | Request identity, effect classification, execution receipts, budget accounting, rejection and indeterminate handling, and enforced access boundary |
| Progressive discovery | Can it acquire new interface knowledge starting from public entries and an empty target-tool registry? | Source/client/spec reading, DiscoveryRecords, new descriptors, unresolved claims, contradictions, invalidation and permitted probes; registry enumeration alone fails |
| Autonomous Interface Adaptation | Can it connect to an unseen interface without a human-authored target binding or semantic map? | Frozen bootstrap, reused/generated AdapterArtifact, independent local checks, registered tools, valid public observation and bounded action/receipt where supported, with no human code edits after reveal |
| Task-local construction | Can a missing capability lead to a validated tool that advances the task? | Generated implementation, declared dependencies, checks, public execution evidence, and construction cost |
| Feedback and repair | Does execution evidence lead to an appropriate observation, reasoning, plan, or implementation change? | Expected-versus-actual outcomes, diagnosis, policy/tool versions, activation boundaries, repair result, and regressions |
| Context and state | Can the next decision recover necessary evidence without retaining every message? | Artifact retrieval, call/result integrity, state provenance, context cost, and successful handling of long tasks |
| Automatic validation | Are activation and publication decisions based on the appropriate independent evidence? | Frozen protocol/jobs, typed checks, fresh behavior where required, all outcomes including inconclusive, conditional model review, and data separation |
| Skill publication | Are only sufficiently validated candidates published, and are versions traceable? | Type-specific thresholds, immutable scope, dependency pinning, atomic release records, and no cross-task exposure of unpublished candidates |
| Quarantine and rollback | Does recovery distinguish uncertain execution from attributable defects? | One-defect and two-of-up-to-five fixtures, compatible fallback, settled activation, physical-state reconciliation, and unchanged fixed-cohort starting snapshots |
| Skill retrieval | Can the harness find relevant skills without selecting incompatible or weakly supported ones? | Three-valued filters, adapter evidence, lexical/semantic recall, ranked reasons, summary/body limits, dynamic checks, and condition-specific outcomes |
| Cross-task learning | Do published skills help later tasks beyond their construction examples? | Logged task order, cumulative experience, held-out performance, negative transfer, and total validation/construction cost |
| Generalization | Can the same discovery-to-adapter mechanism handle different sensors, actions and lifecycle rules? | HumanCLAW, RoboCasa365 and RoboDojo plus an untouched interface family; no handwritten target bindings, manifests, task helpers or core branches added after reveal |

Separate three interventions when interpreting results: changes to the harness core, additional prebuilt tools, and capabilities constructed during the task. Providing a mature IK solver is a tool-capability intervention, even when the solver is packaged inside the harness.

Formal evaluation fixes the initial adapter/skill snapshot, general policy and validation versions, allowed tool sources, and adaptation rules. Task-local changes remain permitted under that fixed protocol and are logged; they do not modify the next evaluation episode's starting snapshot.

Report cold starts without target-specific adapters separately from warm starts using eligible published versions. Freeze the generic runtime before revealing the held-out interface; supply only BootstrapSpec and ordinary public environment materials. Public-client reuse is allowed and recorded, while experimenter-written mapping injected after reveal invalidates the autonomous claim. Measure zero-human-edit adaptation rate, time/cost to first valid observation and action, contract errors, repair outcomes, abstentions and human interventions separately from task success. A new task on a familiar EFE protocol measures reuse; broader generalization requires the distinct held-out interface.

Measure cross-task publication in a separate continual-learning mode. Report task order, skill/policy versions, cumulative experience, construction and validation cost, and performance at frozen checkpoints. Do not combine those results with frozen-snapshot evaluation.

Across both modes, record actual delivered provider settings and complete usage coverage; match environment observations and constraints within comparisons; repeat stochastic conditions; report uncertainty and failure regressions. Distinguish model requests, computation, observation, environment submissions, control steps, simulation time, and wall time. Metrics unavailable from an environment remain unavailable rather than being inferred from a successful tool result.
