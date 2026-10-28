# Pi harness integration and execution contracts

Implementation and pilot runbook: [ADAPTIVE_PILOT.md](ADAPTIVE_PILOT.md). The earlier embodied prototype has been replaced by `adaptive-v1`; cross-task releases remain a later stage.

Status: architecture approved 2026-10-25; Autonomous Interface Adaptation added
2026-10-26; the task-local pilot is available. This document defines the full
target integration boundary for the capability-discovering, self-extending Pi
harness. Pilot availability does not mean autonomous unseen-interface adaptation
is already implemented.

The [Pi harness design](PI_EMBODIED.md) describes the modules and adaptive loop.
The [implementation plan](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md)
defines delivery stages and acceptance criteria.

## Runtime ownership and reuse

Pi owns model interaction, session events and the tool-call lifecycle. The
harness supplies discovery, state management, decision policy, managed
programming and context selection. Environment-facing services own actual
execution and receipts; the transport owns provider delivery and usage
accounting.

| Existing component | Reusable mechanism and required extraction |
| --- | --- |
| Pi SDK runner and hooks | Session persistence, provider integration and lifecycle hooks. Hooks become thin dispatch points for explicit modules. |
| Current context projection | Preserve complete call/result dependencies and raw history. Replace environment-specific selection assumptions with evidence and task dependencies. |
| Shared harness runtime and services | Environment ownership, transport, event correlation, budgets and lifecycle handling. Separate generic contracts from benchmark assumptions. |
| Durable LIBERO request protocol | Persistent requests, committed-result reuse and uncertain-execution handling. Extract these guarantees without inheriting a fixed action or observation vocabulary. |
| Codex integration | Reuse applicable tool-registration/exposure separation, workspace execution, event correlation and provider accounting mechanisms. Pi remains the decision runtime; no second Codex decision loop is required. |

Reuse is selective refactoring of mechanisms. It does not commit the new
architecture to retaining existing interface shapes or benchmark-specific
policies.

## Autonomous Interface Adaptation and discovery

The target does not require a human-authored Binding for each benchmark. An
Environment Binding is an Adapter Artifact that the harness can autonomously
discover, reuse, generate, validate, register and repair. Generic MCP, HTTP,
permitted Python, resource/file access and program execution primitives provide
the stable bootstrap infrastructure; they do not encode per-robot action lists
or benchmark success mappings.

`BootstrapSpec` supplies the task/environment entry, allowed public resources
and access, and applicable budgets. From that entry the harness locates schemas,
public documentation, examples, public clients, observation resources and
lifecycle interfaces. A benchmark-specific client shipped by the environment
is valid source material to reuse, with provenance retained; an opaque hidden
fallback to an experimenter-written binding is not autonomous adaptation.

Discovery actively acquires and checks new information. It follows permitted
documentation and resource references, inspects public client/schema information,
discovers available dependencies, and proposes further bounded checks. Listing
the existing registry is a distinct lookup operation and cannot satisfy this
contract. A `DiscoveryRecord` preserves each lead, source/version, capability
claim, evidence, contradictions, unknowns, and the budget spent resolving them.
Tool names or documentation examples alone do not establish backend support.

Discovery remains progressive. Startup establishes only the contract needed for
the first decision; later gaps trigger more discovery or adaptation. Unknown
permissions or effects are resolved from authoritative allowed evidence before
calling the affected operation. No exploratory raw request may evade the broker
because the harness labels it a discovery probe. Discovery and validation have
explicit budget and event records.

A capability record identifies provenance, input/output contracts, units,
coordinate frames, dependencies, effects, supported operations, constraints,
verification state and version. Environment-native tools, agent-generated
tools, library skills and third-party packages retain separate identities.
Unavailable or inferred capability is never presented as verified support.

Authoritative environment constraints cannot be weakened by generated adapters,
skill metadata or policy repairs. An unknown permission or execution effect
must be resolved before the affected operation is admitted.

### Binding artifact, verification and activation

The adaptation sequence is **Bootstrap → Discovery → Capability Declaration →
Public Client Reuse / Adapter Synthesis → Contract Verification → Registration →
Execution Feedback / Repair**. Responsibilities remain within the nine modules
in the architecture, with discovery and the workspace constructing artifacts,
validation admitting their scope, the registry exposing interfaces and the
broker owning actual transport and effects.

`AdapterArtifact` records:

- The immutable implementation and manifest identity, source provenance,
  protocol/schema fingerprints and dependency versions.
- Operation arguments/results, units/frames, resource codecs, declared effects,
  timing, failure modes and required capabilities/permissions.
- Initialization, reset if permitted, observation, action, status, stop and
  termination mappings that actually exist in the discovered environment.
- Validation protocol/report references, local activation status, publication
  status, supported scope and unresolved limits.

Generated mappings may normalize a public lifecycle or success signal only when
the environment actually supplies it. Absence remains explicit; a generated
adapter cannot manufacture completion evidence or add reset/stop guarantees.
Adapter Artifacts implement interface adaptation; Task Skills implement task
behavior and have a distinct identity and validation subject.

Local admission checks schemas and codecs, dimensions, units/frames, effect
classification, broker routing and available independent fixtures. It then uses
permitted read queries and, only where necessary and authorized by the task
contract, bounded behavioral probes with observable outcomes. Probe records
carry ordinary execution identities and resource costs. A task's first use can
be limited to the verified operations and conditions; full protocol coverage
need not precede initial execution.

Unresolved material contracts stay unavailable or inconclusive. Local activation
registers an exact artifact/scope at a decision boundary without physical work
in flight. Contradictory feedback triggers diagnosis, rediscovery and a revised
artifact, followed by affected checks before reactivation. Cross-task reuse
requires separate publication; source-task local eligibility is insufficient.

## Observation contract

An observation is an evidence envelope, not a required RGB image. It may contain
images, depth, calibration, proprioception, text, action outcomes or other
permitted modalities. Each item records a source, observation identity,
timestamp or simulation time when available, frame/units where relevant, and
its association with execution.

Large payloads are retained as addressable resources for generated programs.
Numeric or binary RGB-D access preserves dtype/shape, encoding, timestamps,
units/frames and calibration associations when supplied. The binding discovers
the resource codec and camera convention rather than assuming that a rendered
preview is the underlying depth array. The context builder selects relevant
content without erasing originals. Public evidence and private evaluator state
remain separate; the connector does not expose hidden state to fill a missing
public modality.

Observation freshness is contract-dependent. Merely receiving a new image does
not imply that a physical action occurred. Conversely, a watch or observation
call that advances simulation time is an effectful operation and is accounted
for accordingly.

## Execution broker contract

Environment transport and resource access use generic broker-mediated routes;
every environment-changing operation passes effect admission, including probes
and submissions nested in generated programs. Read-only resource retrieval is
accounted for separately from physical action. A connector or generated client
must not provide an untracked raw transport or credential path around admission
and execution recording. Unknown effects cannot be treated as read-only.

A proposed execution identifies the operation, arguments, applicable evidence,
tool/adapter version, expected outcome and budget allocation. Admission checks
the discovered contract, required preconditions, constraint version and current
execution state. The admitted versions remain fixed for that execution.

Execution states distinguish:

- **Rejected:** no execution was admitted.
- **Accepted:** the request is durably recorded and ready for dispatch.
- **Running:** dispatch has begun and side effects may have occurred.
- **Completed:** a definitive result or receipt is recorded.
- **Failed:** failure and the known extent of execution are recorded.
- **Indeterminate:** execution may have occurred, but its outcome is unresolved.

Environment mutation has a single execution owner. A submitted trajectory may
contain multiple control steps under a declared duration and validation
contract. Pure computation may run independently when dependencies and budgets
permit; it is not counted as a physical action.

An identical request can reuse a committed receipt. Reusing its identity with
different arguments is rejected. An uncertain execution is never blindly
replayed. Local deduplication cannot manufacture backend idempotency; connector
reconciliation must follow the actual backend contract.

Waiting timeout, cancellation request and confirmed stop are different events.
A deadline does not establish that the environment stopped. A recovery decision
uses known execution state and new permitted observations; it cannot assume that
a program rollback reversed a physical action.

## Workspace, extension and activation

Generated programs and bindings execute in a managed task workspace and use
broker clients for environment transport, resources and effects. Their files,
dependencies, interfaces and versions are retained independently of model
context. Discovery can locate permitted scientific packages for array, geometry
and numerical computation; dependency resolution and installation are managed,
versioned and budgeted. Missing or unavailable packages remain explicit gaps.
Stable program/skill execution entry points can expose temporary functions
without rewriting the model's tool schema after every edit.

The first implementation permits repair of adapters, tools, skills and task
policies, including reasoning, observation and verification rules. Candidates
undergo applicable contract, behavior and regression checks. A checked revision
activates at a decision boundary with no physical operation in flight; an
unresolved execution must be reconciled first. Running operations keep their
admitted versions.

The execution kernel, environment constraints and evaluator criteria are not
self-modifiable. A repair changes a method or belief, not the definition of
task success.

A versioned validation protocol fixes the minimum activation and publication
checks. Candidate tools, skills and task policies cannot weaken or remove those
checks; they may add further checks. Insufficient evidence leaves a candidate
provisional without adding a routine human approval step.

Task policies are versioned structured trigger/action rules with optional
versioned function references. The candidate identity covers both rules and
referenced code, so changing either produces a new validation subject.

## Validation and release contracts

The approved V-A workflow separates four records:

| Record | Required integration contract |
| --- | --- |
| `ValidationProtocol` | Versioned minimum checks, independent outcome criteria, permitted data sources and resources, and distinct local-use/publication gates. Candidates cannot edit away these requirements. |
| `ValidationJob` | Frozen candidate and parent versions, dependencies, declared scope, test manifest, checker versions, environment identity and resource allocation. Candidate changes require a new job and reevaluation of affected evidence. |
| `ValidationReport` | Per-check `pass`, `fail` or `inconclusive`, artifact references, all trial outcomes, provenance, resource usage and any independent review. Missing evidence is never a pass. |
| `ReleaseDecision` | Separate `local_eligible` and `publish_eligible` decisions for an exact version/scope, protocol and report references, unresolved restrictions and machine-readable reasons. Local eligibility alone cannot publish a version. |

Validation depends on the candidate's type and actual effects: pure computations
use independent expected results or invariants; environment actions require
permitted execution and observed postconditions; replacement policies require fresh matched trials
against their parent. Old trajectory replay can check interfaces and context
handling but cannot supply counterfactual evidence for changed actions.
Critical policy changes or evidence conflicts add an independent model-session
review. Review does not replace outcome checks or behavioral evidence.

Adapter validation additionally checks transport/schema fidelity, lifecycle
mapping, resource codecs, broker routing and the supported protocol scope.
Conversion-only releases use the computational gate; non-mutating observation,
status and resource adapters additionally need permitted live read checks.
Every action-dispatch adapter, including observations that advance simulation
or mutate task state, also meets the action gate for its declared interface/control
postconditions. These are interface-fidelity claims, not manipulation-task
success. Local interface eligibility does not require publication-sized evidence
and cannot be relabeled as cross-task publication or task competence. The
implementation plan defines the effect-based release mapping and thresholds.

P-A automatically publishes immutable versions within the validated scope. The
[implementation plan](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md)
defines the exact per-type engineering thresholds, hard checks and regression
gates. Those publication thresholds do not gate initial local use or establish
statistical reliability. Success criteria and required checks cannot be supplied
solely by the candidate's own judgment function. Retain failed and unresolved
trials and do not count repeated frames as independent trials.

Unpublished adapter, tool, skill and policy candidates can execute only in their
source task after applicable local checks, or in an explicitly permitted
validation job. There is no cross-task candidate trial pool. Ordinary later tasks
load a published snapshot; new publication does not imply default selection or
change an active snapshot.
Capability requirements, applicability evidence, failure conditions and all
construction/validation costs travel with each published version.

Content-addressed artifacts hold implementations and evidence. SQLite holds
manifests, protocol/job/report/decision records and lifecycle events. An atomic
publication transaction makes a fully validated immutable version selectable;
incomplete or interrupted publication does not expose a partial version. A
semantic index is a derived retrieval aid, never the authority for release
status, snapshot membership or applicability.

Task-local discovery, construction and validation consume episode resources.
Library-level validation after an episode ends has a separately predefined
budget and contributes to cumulative cost. It uses saved public evidence or an
explicitly permitted validation environment; it grants no additional benchmark
actions, resets or attempts and cannot resume an ended evaluation episode or
change a fixed evaluation cohort's starting snapshot. Insufficient resources or
evidence leaves the candidate provisional.

## Isolation and rollback contract

R-A distinguishes execution uncertainty, changed preconditions, confirmed defects
and ordinary outcome failure. An indeterminate request is reconciled before
new conflicting execution; it does not itself increment a defect counter.
Changed preconditions invalidate the current use, not automatically the version.

A confirmed hard defect immediately isolates the affected version or scope.
An ordinary failure first prompts bounded diagnosis. The implementation plan's
rolling-window rule isolates a scope after repeated independent, matched,
judgable failures attributable to that version. Store the attribution evidence,
failure signature and scope; unrelated conditions must not share a failure
counter. Preserve unresolved attribution as unknown.

Isolation stops new affected admissions. It is distinct from switching the
active version or cancelling a running operation. Running operations retain
their admitted identity and follow the backend's actual stop/reconciliation
contract. A replacement activates only at a settled decision boundary after
checking its dependencies, interface and current preconditions. If no compatible
older version exists, return to discovery or repair. No rollback claims to
reverse physical effects.

## Adapter and skill retrieval contract

S-A receives the intended effect, current subgoal, available capabilities,
evidence, resource constraints and recent relevant failures. First apply
three-valued compatibility checks to required capabilities, interfaces,
dependencies and permissions. Exclude known mismatches. Unknown required facts
produce discovery leads; they do not authorize execution. A validated adapter
chain may satisfy a requirement, and dynamic preconditions must be checked again
at invocation.

Adapter retrieval uses the same eligibility and compatibility discipline, with
protocol/schema fingerprints, operation semantics, resource conventions and
dependencies as relevant requirements. A published adapter is reusable only when
it belongs to the pinned snapshot and its supported scope matches newly
discovered endpoint facts. Cached code cannot bypass release status, scope or
task-local checks. A mismatch triggers rediscovery and local adaptation;
unpublished adapters from earlier tasks are excluded from ordinary retrieval.

Run lexical and semantic recall over eligible published versions in the pinned
snapshot, merge and deduplicate, then order by evidenced scope match, intended
effect, matched-condition reliability evidence and cost. FTS5 supports lexical
recall; semantic index entries record the encoder and manifest versions. Return
at most eight summary cards and load at most three full bodies on demand. Pi
selects in its normal decision step without a mandatory extra model reranker.
No suitable skill returns an explicit discovery/construction path. Retrieval
must not treat a sparse perfect success fraction as stronger evidence than a
well-tested candidate, or pool incompatible conditions into one success rate.

Every result identifies the skill version, snapshot, applicability evidence,
remaining precondition checks and ranking reasons. Published status and scope
are rechecked against the selected snapshot and task-local restrictions before
admission, independently of any cached retrieval result. A global revocation that
conflicts with a fixed cohort triggers the protocol-change handling below; it is
not silently imported into the task's starting capabilities.

## Completion and lifecycle

The task policy evaluates task-specific completion evidence. The runtime
separately records a requested stop, environment termination, budget exhaustion,
infrastructure failure and evaluator success when supplied.

A task may finish with its target occluded or without an online success signal.
No universal visible-target rule or assumed success endpoint belongs in the
integration layer. Final text does not supply benchmark success.

Session closure reconciles outstanding requests, records the terminal state and
settles accounting. It must preserve unresolved execution or usage as unknown,
rather than replacing either with a successful empty result.

## Accounting and evaluation identity

Record separate counts and timings for model requests, provider attempts, tool
requests, pure computations, observations, environment submissions, control
steps and simulation time. Retain discovery, construction, validation and repair
costs alongside ordinary task execution.

Provider-reported usage is authoritative. Retries and auxiliary requests remain
visible; cached-input and reasoning subsets must not be added to token totals
again. Nested tool/module durations are not additive end-to-end latency.
Missing completion or usage stays unknown.

Each decision and execution links to the evidence, capability declaration,
tool implementation, policy and skill versions used. Persist raw events and
artifacts alongside projected model requests and derived summaries. These
records support inspection of both successful adaptation and incorrect
capability claims.

Formal evaluation pins the initial general policy and published skill/adapter
snapshot, with its declared within-task adaptation rules. Continuous-learning
evaluation separately records task order, publication history and cumulative experience. Adaptive
reasoning has no high-effort quota or extra elapsed-time cutoff; all task-local
activity remains subject to the ordinary episode budget.

Within a fixed cohort, task-local evidence may isolate a version or select a
compatible version already in the snapshot, or trigger permitted local repair.
Global revocation that changes later episodes' starting state creates a separate
cohort or an explicitly reported protocol change. It cannot silently carry
information from earlier episodes into the fixed evaluation.

Implementation introduces generic transport and managed-workspace foundations
in M1, active discovery in M2a, autonomous binding synthesis/local validation in
M2b, and feedback-driven repair in M3. Early real-environment interactions must
exercise this path rather than defer all integration checks until M5.

Cold-start acceptance provides a held-out environment's entry and permitted
public resources through `BootstrapSpec`, without a handwritten benchmark
binding, prefilled action/success mapping or hidden benchmark fallback. The
harness must produce discovery and adapter evidence, register locally verified
interfaces, perform a brokered interaction and check its observable outcome.
An interface-version change must cause appropriate revalidation or autonomous
repair. An unresolved contract must remain explicitly unresolved rather than
trigger an invented mapping. Environment-provided public clients are allowed
and attributed; existing handwritten bindings are baselines/fixtures only.

Report adaptation success, discovery/validation cost and task-solving success
separately. Demonstrating interface adaptation alone does not establish task
competence or broad cross-benchmark generalization.
