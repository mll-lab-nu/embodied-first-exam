# Pi harness: capability discovery and autonomous adaptation

Implementation and pilot runbook: [ADAPTIVE_PILOT.md](ADAPTIVE_PILOT.md). The earlier embodied prototype has been replaced by `adaptive-v1`; cross-task releases remain a later stage.

Status: architecture approved 2026-10-25; Autonomous Interface Adaptation added
2026-10-26; task-local pilot implemented 2026-10-26.
This document describes the full target, including later cross-task capabilities.
The authoritative implementation sequence and acceptance criteria are
in the [implementation plan](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md).

The harness uses Pi for model interaction, session management and tool execution.
It discovers the environment's public capabilities and constraints, autonomously
reuses or generates Environment Bindings, validates and repairs them, constructs
missing tools, and adjusts its task strategy from execution evidence.
Benchmark-specific knowledge belongs in discovered capability records, validated
Adapter Artifacts and skills, rather than fixed assumptions in the runtime.
Human-authored per-benchmark bindings are not a prerequisite for the full target.
The task-local pilot does not yet establish this autonomous cold-start capability.

The target includes HumanCLAW, RoboCasa365, RoboDojo and future benchmarks. RGB-D,
robot kinematics, a particular action vocabulary and an online success signal
are optional capabilities, not universal requirements.

## Approved design decisions

1. **Progressive discovery.** At startup, verify the contracts and constraints
   required for initial execution. Discover additional capabilities as the task
   requires them, retaining unknowns and evidence of contradictions. Discovery
   actively reads permitted interfaces, documentation, examples, client code
   and dependencies; it is not limited to listing already registered tools.
2. **Automatic incremental skill publication.** A task can build and use
   validated temporary tools. Candidates that pass the library's validation
   gates publish new versions for subsequent tasks.
3. **Tool and task-policy repair.** The first implementation supports repairing
   adapters, tools and skills, and revising task strategy, reasoning, observation
   and verification policies. Checked revisions activate at a decision boundary
   with no physical operation in flight. They cannot rewrite the execution
   kernel, authoritative environment constraints or evaluator criteria.

The approved evolution mechanisms are **V-A** (type-based validation with
selective independent review), **P-A** (automatic publication within the
validated scope), **R-A** (attributed-failure isolation and compatible rollback)
and **S-A** (compatibility filtering followed by hybrid skill retrieval).

Adaptive reasoning has no high-effort quota or additional elapsed-time cutoff.
All reasoning, discovery, tool construction and validation performed within a
task consume the normal episode budget.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| Pi runtime bridge | Own the session and connect model requests, tool results and lifecycle hooks to the other modules. |
| Environment discovery | Locate and read permitted interfaces, schemas, documentation, examples, public clients and dependencies; record new leads, propose capability records and request bounded verification. |
| Capability and tool registry | Track discovered tools and Adapter Artifacts, provenance, availability, effects, dependencies, versions and validation scope; register locally admitted interfaces and select relevant tools for a request. |
| Execution broker | Mediate environment transport and all mutations, including probes and calls inside generated programs; enforce effects, ordering, budgets, request identity and durable execution state. |
| Evidence and task state | Store observations, entities, subgoals, hypotheses, expected outcomes, failures and their supporting evidence. |
| Decision policy | Choose the next observation, computation, execution, repair or completion step and allocate reasoning effort. |
| Context builder | Assemble relevant evidence, state, program interfaces and skills while preserving call/result dependencies and retrievable history. |
| Workspace and skill lifecycle | Reuse public clients or synthesize and repair bindings, tools and skills; provide scientific dependencies and resource access; manage local validation and scoped cross-task publication. |
| Transport and audit | Normalize provider requests, record actual usage and connect decisions, tools, executions and versions without double counting. |

These are logical boundaries, not a requirement for nine agents or services.
The Pi-side runtime can compose them in one process. Environment ownership,
execution receipts and accounting remain explicit boundaries even when modules
share a process.

## Autonomous Interface Adaptation

Autonomous Interface Adaptation is a first-class workflow across these nine
modules. An Environment Binding is a discoverable, reusable and repairable
runtime artifact, not a developer-authored adapter required for each benchmark.

The minimal human bootstrap is a `BootstrapSpec`: the task and environment entry,
permitted public resource locations and access, and applicable budgets. It does
not require a supplied robot dimension, action list, camera mapping or success
mapping. Generic HTTP, MCP, permitted Python, file/resource access and managed
program execution can be implemented once. Protocol and lifecycle semantics are
then discovered from the environment's authoritative public contract.

The adaptation flow is:

**Bootstrap → Interface Discovery → Capability Declaration → Client Reuse or
Adapter Synthesis → Contract Verification → Tool Registration → Execution and
Repair.**

1. Discovery follows permitted entry points to documentation, schemas, public
   clients and resource descriptions. `DiscoveryRecord` entries retain the
   source, version, claim, remaining unknowns and verification evidence. Registry
   listing/lookup is a separate operation, not evidence of automatic discovery.
2. The workspace reuses an appropriate public client when available, or generates
   the required transport, argument, resource and result mappings. It discovers
   initialization, observation effects, action timing, termination and uncertainty
   semantics rather than assuming HumanCLAW's lifecycle. Public availability of
   a client does not establish that every method is supported by this backend.
3. `AdapterArtifact` binds a versioned manifest and implementation to provenance,
   protocol/schema and dependency versions, coordinate/unit mappings, operation
   effects, lifecycle semantics, validation reports and admitted scope. It does
   not embed a task-solving policy or invent an unavailable success signal.
4. Local validation checks the actual interface and effects: schema/codec and
   unit/frame checks, independent fixtures where available, permitted read
   queries, and only the necessary bounded behavioral probes. Unknown effects
   are resolved before invocation; discovery cannot issue untracked exploratory
   requests. The broker mediates environment transport, probes and resource
   access, including calls inside generated clients.
5. A locally admitted artifact can register interfaces and serve its source
   task. Execution evidence can invalidate claims, trigger rediscovery or produce
   a repaired version. Repairs repeat affected validation and activate only at a
   settled decision boundary; they cannot redefine authoritative constraints.

Adapter Artifacts answer how to call an environment correctly. Task Skills
answer how to achieve a task outcome. Their local-use and cross-task publication
gates remain separate. For publication, conversion-only adapters use the
computational gate; non-mutating observation/status/resource adapters additionally
need permitted live read checks. Every action-dispatch adapter, including an
observation that advances simulation or mutates task state, also meets the action
gate for its declared interface/control postconditions. These checks establish
interface fidelity, not manipulation-task success. Source-task activation does
not require publication-sized evidence.

For cross-task reuse, retrieve only eligible published adapters in the task's
pinned snapshot, then recheck the discovered endpoint, protocol, schema,
dependencies and current permissions. An incompatible or absent adapter triggers
autonomous discovery and construction. Unpublished source-task adapters cannot
be silently reused through a cache in ordinary subsequent tasks.

## Execution loop

1. **Discover enough to proceed.** Identify the task, permitted interfaces,
   initial observations, execution effects, budgets and lifecycle semantics.
   Reuse or generate a binding, validate its required scope and register the
   admitted operations. An unclear contract that affects execution is resolved
   before acting; no prewritten per-benchmark binding is assumed.
2. **Update task state.** Ingest available evidence and separate observations
   from model inferences. Preserve conflicting evidence instead of silently
   replacing it.
3. **Select the computation strategy.** Choose reasoning effort, relevant skills
   and tools, and whether more observation or local computation is needed.
4. **Construct the decision context.** Include the task, relevant capabilities,
   current evidence, program interfaces and necessary history.
5. **Propose an operation and its expected outcome.** Keep task-level rationale
   and verification intent in harness records rather than forcing a universal
   assessment schema into every native tool.
6. **Validate and execute.** Freeze the relevant observation and tool/policy
   versions. Pure computation can proceed under its own resource limits;
   environment mutation must pass through the execution broker.
7. **Compare expectation with evidence.** Distinguish command completion from
   task progress, semantic failure, insufficient evidence and uncertain
   execution. Update capability confidence and the next decision accordingly.
8. **Finish or continue.** Completion uses task-specific evidence and the
   environment's lifecycle. Candidate skill extraction and validation follow
   their own publication rules.

A tool repair returns to validation before use. A policy repair changes how
future decisions are made; it does not reinterpret an execution already in
flight. Code rollback does not undo an environment action.

## Capability model

Maintain four separate records:

- **Model capabilities:** provider-supported reasoning, modalities, context
  limits and request formats.
- **Environment capabilities:** available actions and observations, units,
  frames, timing, constraints, permissions and termination semantics.
- **Tool registry:** native tools, generated tools, existing skills and
  third-party dependencies that are currently callable.
- **Runtime policy:** stable execution rules, retry ownership, minimum validation
  requirements and experiment-mode settings. Replaceable task policies separately
  select reasoning, context, observation, verification and recovery within these
  boundaries.

Each capability records its source, version, verification evidence, dependencies
and effects. Documentation-only claims, verified behavior, inferences, unknown
items and contradicted claims remain distinguishable. The harness can revise a
claim when actual behavior disagrees with it.

The presence of depth and calibration can justify constructing a backprojection
tool; it does not mean such a tool already exists or has been verified. A
discovered method name likewise does not establish backend support.

## Evidence, programs and adaptive reasoning

Raw evidence, the current task model and executable program state have separate
lifetimes. Context projection removes material from a model request, not from
the evidence store or workspace. Retained program interfaces identify their
implementation version and validation status.

Public RGB-D and other numeric/binary observations remain available to programs
through resource handles with dtype/shape, timestamps, units, coordinate frames
and associated calibration when supplied. Image previews do not replace raw
depth. The managed workspace supports discovered, permitted scientific
dependencies for array, geometry and numerical work; it is not restricted to
language-model text processing or standard-library-only computations. Missing
depth, calibration or dependencies remain explicit capability gaps.

Expected-versus-observed outcomes drive adaptation. Missing geometry may call
for another observation; inconsistent transforms may require tool repair;
blocked motion may require different waypoints; ambiguity between plausible
explanations may justify more reasoning. Escalating effort is one available
response, not the default response to every failure.

Task state can represent multiple entities and subgoals, uncertain object
relationships and dependency order. Observation freshness depends on the
quantity being used and the environment's dynamics; a new camera view does not
automatically invalidate every world-state estimate.

## Skill and policy lifecycle

The lifecycle is: identify a need, retrieve or construct a candidate, validate
it for local use, observe its results, extract a reusable candidate, and
validate it separately for publication. Local activation and cross-task
publication are independent qualifications. A task does not need to meet the
library's publication sample counts before using a locally checked candidate.

Reusable skills package capability requirements, inputs and outputs, versions,
implementations or strategies, outcome checks, known failure modes and evidence
of applicability. Episode-specific coordinates remain examples. Task policies
use versioned structured trigger/action rules and may reference versioned
functions; policy candidates follow the same activation discipline as tools.

### Automatic validation and scoped publication

V-A uses a versioned `ValidationProtocol`, a frozen `ValidationJob`, an evidence-
linked `ValidationReport` and a separate `ReleaseDecision`. A job freezes the
candidate and parent versions, dependencies, scope, tests and checkers. Results
are `pass`, `fail` or `inconclusive`; failures and unresolved evidence remain
visible. Candidates may add checks but cannot weaken minimum requirements.

Pure computation is checked with independent expected results, invariants and
boundary cases. Effectful tools additionally require permitted behavioral
trials and observable postconditions. Replacing a task policy requires fresh,
comparable execution evidence; replaying an old trajectory cannot establish
what a changed action would have produced. An independent model session reviews
critical policy changes or conflicting evidence. Its approval cannot replace
an independent outcome check or execution evidence.

P-A publishes immutable versions automatically only for their evidenced scope.
The [implementation plan](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md)
owns the approved per-type sample thresholds, hard checks, regression gates and
cost reporting. These defaults are engineering gates, not statistical
reliability guarantees. Publication does not automatically make a new version
the default. Minimum gates cannot be waived by the candidate, and passing them
does not add a routine human approval step.

Unpublished skill, tool and adapter candidates remain usable only in their
source task after local validation or in explicitly permitted validation jobs.
They do not enter a cross-task trial pool or normal later-task retrieval. Later
tasks retrieve from their published skill/adapter snapshot; insufficient publication evidence leaves a
candidate provisional.

### Failure attribution and rollback

R-A immediately isolates a version or affected scope after a confirmed hard
defect. The first ordinary failure triggers bounded diagnosis instead of blind
repetition. Repeated matching failures attributable to that version trigger
scope isolation under the rolling-window rule in the implementation plan.
Unknown execution requires reconciliation first; a timeout alone is not a
software defect. Changed preconditions instead trigger rediscovery or replanning.

Rollback rechecks the older version's capability, dependency and current-state
requirements. Activation waits for a decision boundary with no physical
operation in flight, and admitted operations keep their versions. If no prior
version remains applicable, repair or rediscover instead. Software rollback
never restores physical state.

### Retrieval and persistence

S-A first classifies required capabilities, interfaces, dependencies and
permissions as satisfied, unsatisfied or unknown. Unsatisfied candidates are
excluded; unknown candidates become discovery leads, not executable choices.
Validated adapters may establish compatibility. Dynamic preconditions are
checked again immediately before invocation.

Compatible skills are recalled using both lexical and semantic search, then
ranked by validated scope match, intended effect, matched-condition evidence
and cost. Expose at most eight summary cards and load at most three full skill
bodies on demand. Selection stays in Pi's normal decision step without a
mandatory extra model reranking call. No suitable match leads to discovery or
managed programming. Sparse success records do not outrank substantial evidence
solely because they have a higher raw success fraction.

Store code and evidence as content-addressed artifacts. SQLite holds manifests,
validation reports, lifecycle events and snapshot metadata; publication commits
transactionally. FTS5 supports lexical recall, while the semantic index records
its encoder version and is derived from the same published manifests. Each
activation, publication, isolation and rollback records its scope, evidence and
cost without deleting the failure history.

After an episode ends, library-level validation uses a separate, predefined
resource budget and counts toward cumulative costs. It uses saved public data
or an explicitly permitted validation environment. It cannot resume the ended
episode, grant extra benchmark actions, resets or attempts, or change a fixed
evaluation cohort's starting snapshot. Without sufficient evidence or resources,
the candidate remains provisional.

Stable execution rules and benchmark constraints remain outside the self-repair
surface throughout this lifecycle.

## Evaluation and implementation entry points

Formal evaluation freezes the initial published skill/adapter snapshot and
initial general policy, including the permitted within-task adaptation mechanism.
Task-local adaptation remains enabled, but a publication cannot alter another
episode in that fixed evaluation. Continuous-learning evaluation separately records task
order, accumulated experience, versions and construction/validation costs.
Local evidence may deactivate a bad version or select a compatible version
inside the pinned snapshot. A global revocation that changes later episodes'
starting snapshot must create a separate cohort or an explicitly reported
protocol change; it is not silently applied inside the fixed cohort.

The implementation starts with module contracts, generic brokered transport and
managed-workspace foundations (M0–M1). M2a implements active discovery; M2b closes
autonomous binding synthesis, local validation and tool registration. M3 adds
feedback-driven repair and task-policy adaptation; M4 adds cross-task publication.
Small real interactions in different environments validate these stages before
the systematic M5 evaluation.

Cold-start acceptance supplies a held-out public interface through the minimal
bootstrap and requires a trace of discovery, binding reuse or generation,
validation, brokered execution and observable result checks. No handwritten
benchmark binding, prefilled action/success mapping or hidden fallback may be
injected into that acceptance run. Environment-provided public clients are
allowed and their use is recorded. Existing handwritten bindings serve pilot
baselines or fixtures only. Integration success and task success are measured
separately; automatic adaptation does not establish reliable task solving.

- [Integration and execution contracts](NATIVE_HARNESSES.md)
- [Architecture and evaluation rationale](analysis/harness-comparison-20261019/DESIGN_AND_NEXT_STEPS.md)
- [Implementation stages and acceptance gates](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md)
