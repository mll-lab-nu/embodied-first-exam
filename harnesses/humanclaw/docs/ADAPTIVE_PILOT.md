# Adaptive harness pilot

The `harness-improving` branch replaces the earlier embodied prototype with
`pi_profile: adaptive-v1`. There is no parallel `embodied-v1` implementation.
Native Pi and Codex remain benchmark reference harnesses.

## Implemented task-local slice

- The pinned Pi 1.3.0 session discovers a managed MCP interface. Public native
  schemas, effects and versions come from a binding. HumanCLAW's eight actions,
  RGB, Sit duration and Stop semantics are confined to `adaptive/bindings.py`.
- A SQLite journal commits intent before dispatch and receipts before delivery.
  Identical retries recover a receipt; conflicting IDs are rejected. A dispatch
  interrupted before a reliable receipt becomes indeterminate and prevents new
  execution and version activation. This pilot does not restore a lost simulator.
- A model turn may attempt one environment execution. Identical retries and
  receipt recovery remain allowed; subsequent work waits for a fresh model
  request so it cannot cite a future frame it has not seen. Explicit reviewed
  programs receive public child receipts and use the separate child-call contract.
- Model-reported claims and task-derived subgoals retain evidence references and
  provenance. Initial and subsequent public observations persist separately from
  chat; `evidence` retrieves original observations and memory can pin two anchors.
- Context projection keeps complete tool exchanges, current evidence, the task,
  system instructions and schemas. It uses a chunked 16-to-8 exchange window,
  includes schema/text costs and declared image reserves, preserves signatures,
  and explicitly fails if mandatory context cannot fit. Non-image bindings work.
- Reasoning changes between medium and high from prediction feedback and
  uncertainty. There is no high-effort proportion cap or separate reasoning
  deadline. Retry identities retain their selected effort.
- Completion is supported, contradicted or unknown in public evidence. The model
  can stop with explicit uncertainty or inability; it cannot turn its assessment
  into an evaluator success signal. No fixed sitting-phase classifier is used.
- Immutable Python tools and structured policy revisions have parent hashes,
  diagnoses, fixed validation protocols, reports and separate release decisions.
  The initial numerical protocols cover shortest-angle deltas and signed turn
  adapters. Other numerical contracts require an additional host-owned oracle;
  model-supplied examples alone cannot authorize them.
- Policy changes require fresh interpreter checks and a separate model review
  through the same metered provider. Failed deterministic checks cannot be
  overridden by review. Activation requires settled execution. Confirmed tool
  defects are quarantined, with rollback to an eligible compatible parent.
- Adaptation keeps one pending candidate in host-owned state, including its
  implementation, validation result and next transition, in every context
  projection. Validate then activate, repair a failed parent, or explicitly
  discard it. Reworded diagnoses with identical implementation/evidence reuse
  the candidate; repeated validation reuses its report. New proposals require
  current observation evidence; after activation/discard that protocol requires
  a new environment observation. Pi exposes the legal lifecycle tools for the
  next turn, avoiding repeated discovery/proposals while validation is pending.
  The latest discovery exchange stays in context while a candidate is pending;
  unread or changed environment contracts still make discovery available.
  Execution and receipt recovery remain available. These are progress/evidence
  requirements, not reasoning quotas or additional elapsed-time limits.
- Independent review connects directly to the authenticated loopback gateway;
  upstream model traffic retains the cluster proxy. Transient HTTP and streamed
  provider errors share a cooldown, honoring Retry-After or using a 60-second
  token-rate fallback with exponential backoff and jitter. SDK turn retries and
  reviewer retries retain their original request; each actual provider attempt
  remains metered. Episode closure interrupts waiting and prevents new admission.
- Review infrastructure failure is inconclusive, not a defective candidate. After
  bounded transient retries, it stops the attempt and fails the framework gate.
  Content filtering remains a non-retryable provider failure; filters are not
  bypassed. A previous rate-limit error cannot authorize retry of a later filter
  rejection, host deadline, or unrelated runtime failure.
- Temporary `runtime.program` executions use standard-library Python in macOS
  Seatbelt or Linux bubblewrap. Private files and network access are excluded.
  Syntax/scope checks and independent review precede execution. Child operations
  use the same broker, frozen parent IDs, evidence, versions and native budgets.
  Validation candidates cannot modify the checker. Unsupported isolation fails
  closed. CPU, process, output and wall limits apply to these programs.

All candidates remain task-local. Cross-task publication, hybrid retrieval,
RoboCasa365/RoboDojo bindings and leaderboard submission are later stages of the
design, outside this 24-task pilot. Untriggered mechanisms are reported as such.

The [current execution plan](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md#current-execution-plan--2026-10-26)
now has a [local autonomous interface implementation](AUTONOMOUS_INTERFACE_LOCAL.md):
minimal bootstrap, Internet/public-source/client/schema discovery, a Scientific
Workspace with numerical RGB-D resources, M2a Discovery, M2b Binding Synthesis and
M3 repair mechanics. Bootstrap sessions have no injected target binding. The
stdlib-only numerical protocols and the explicit HumanCLAW baseline above remain
separate from this workspace path. Interface adaptation and independently scored
task success are recorded separately. This local work is not deployed to the
current pilot; later server validation requires a new frozen cohort.

## Local validation

Install the pinned SDK with `npm ci --ignore-scripts` in `harnesses/pi-adaptive`;
install the Python `adaptive` and `test` extras in an isolated environment.

```sh
python -m pytest -q
cd harnesses/pi-adaptive
npm run check
npm test
```

`tests/test_pi_adaptive.py` exercises durable receipts, conflicts, uncertain
execution, deadlines, contract changes, non-image counters, evidence provenance,
OS file/network/credential isolation, generated children, repair, review and the
real Pi SDK against an explicitly scripted provider. Scripted tests do not prove
autonomous adaptation.

```sh
python tools/adaptive_validation.py --output outputs/adaptive-validation --case all
```

This command uses the configured Azure model in three controlled public text
fixtures: construct a missing tool, repair a faulty adapter, and revise a policy
after a failed prediction. Host oracles inspect the fresh results, candidate
ancestry and execution after activation. All attempts and provider usage remain
in their trace directories. These fixtures do not establish HumanCLAW success.

## Frozen HumanCLAW cohort

`configs/experiments/adaptive_pilot24.json` fixes 24 different scenes, 16 historical
failures and eight historical successes, with 12 navigation and 12 interaction
tasks. Selection seed is 20261025; execution seed is 0. The first two tasks are
shard-0362 and shard-1056. Run full `paper_fullval_v1` episodes with 100 actions,
instruction v1, trace, metrics and video; each native session has 7200 seconds
including discovery, construction, validation and review.

After local validation, deploy the same Git revision on `harness-improving`.
`tools/adaptive_pilot.py prepare` archives committed sources and freezes their
hashes. GPU tasks verify the snapshot before and after each attempt. The scripts
use an isolated additional Python dependency directory and pinned SDK packages,
restored from a hashed archive onto each node's temporary disk. The existing GPU
Python environment supplies the unchanged simulator dependencies.

`submit` launches the two gate tasks and a dependent array for the other 22.
Each array has concurrency two; the second starts only after both gate tasks
complete their framework audit. The audit checks trace/metrics, settled execution,
discovery, matching saved historical initial poses and review infrastructure.
Benchmark task failure
does not fail this framework gate. A framework change requires a new cohort.

Normal task failures are not retried. Recognized transient provider failures may
receive one infrastructure retry; all attempt costs remain in reports. Unknown
physical execution is never retried automatically. Slurm preemption/requeue is
disabled. Interrupted allocations require explicit reconciliation.
`STOPPED.json` closes a cohort to both submission and new task admission. Repairs
must use a new frozen cohort; interrupted simulator state is never resumed.

The cohort contains `freeze.json`, `jobs.json`, per-task states, original attempts,
`adaptation-events.json`, `report.json` and `report.csv`. Reports separate benchmark
outcomes from framework validity. Historical runs used Copilot/Magpie; this pilot
uses Azure, so differences cannot be attributed exclusively to the harness.

Completed attempts are compressed individually. Every archived file is compared
with its original SHA-256 before removing raw episode directories; audit summaries
remain directly readable and point to the verified complete archive. This bounds
storage while retaining failures, native sessions, observations, videos and usage.
