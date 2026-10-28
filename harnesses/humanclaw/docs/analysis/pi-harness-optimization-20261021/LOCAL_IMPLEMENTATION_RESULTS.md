# Autonomous interface adaptation: local results

Date: 2026-10-26. Branch: `harness-improving`. This implements the local portion
of the [current plan](IMPLEMENTATION_PLAN.md#current-execution-plan--2026-10-26).
The purpose is a reusable entry point for future benchmarks: supply a task,
public documentation and transport handles, then let Pi discover the interface,
reuse or generate a binding, validate it and perform an effective interaction.
Usage and examples are in the [local runbook](../../AUTONOMOUS_INTERFACE_LOCAL.md).

All work and fixture execution were local. Server files, dependencies and the
running HumanCLAW cohort were not changed. No new approval layer or reasoning
quota was introduced.

## Local checks

- Full Python suite: **554 passed, 5 skipped**.
- Pi TypeScript tests: **10 passed**; TypeScript checking passed.
- Integration coverage includes startup with an empty registry and no initial
  image; public schema and client discovery; generated and reused codecs;
  independent validation and scoped registration; source drift and corrected
  children; compatible-parent reuse; and progress from fresh observations.
- Execution checks distinguish a received response with a broken decoder from
  an unknown dispatch outcome. Reconciliation uses a public status operation
  without replaying the physical action.
- Scientific checks cover task-local NumPy, persistent outputs, original depth
  arrays in millimetres/metres, invalid samples, missing depth, calibration and
  RGB previews. MCP checks cover initialization, public resources and tool calls.

Scripted providers and deterministic fixtures establish these mechanics. The
autonomous trials below separately exercise the actual Pi/model decision loop.

## Autonomous model trials

All trials use the pinned Pi 1.3.0 runtime and `gpt-6-astra`. The model receives
only a minimal bootstrap and ordinary public fixture surfaces. No handwritten
binding, argument map or adapter edit is supplied during a trial. Every run saves
its runtime identity before exposing the interface, plus its declared scope,
source contents, adapter artifacts, review records, receipts and provider trace.

| Trial | Public interface | Adaptation | Task | Wall time | Provider tokens | Usage known / attempts |
|---|---|---|---|---:|---:|---:|
| [schema-01](evidence/local-implementation-20261026/schema-01-result.json) | Documentation, schema and client | Pass | Success | 156.2 s | 396,895 | 19 / 19 |
| [client-01](evidence/local-implementation-20261026/client-01-result.json) | Documentation and client, no schema | Pass | Success | 171.7 s | 421,774 | 21 / 21 |
| [rgbd-01](evidence/local-implementation-20261026/rgbd-01-result.json) | Client and RGB-D resources | Pass | Incomplete: provider rate limit | 221.2 s | ≥611,394; total unknown | 27 / 34 |
| [heldout-01](evidence/local-implementation-20261026/heldout-01-result.json) | Distinct POST RPC switchboard | Pass | Success | 155.9 s | ≥310,797; total unknown | 17 / 21 |
| [rgbd-02](evidence/local-implementation-20261026/rgbd-02-result.json) | Client and RGB-D resources, serial follow-up | Pass | Success | 302.7 s | 501,259 | 23 / 23 |

Each of the four interface scenarios has a successful autonomous run. Across all
five recorded attempts, interface adaptation passed five times and task success
was independently confirmed four times. These are development smoke checks,
not a cross-benchmark success-rate estimate or a controlled efficiency comparison.
Runtime snapshots changed during development; exact identities remain in each
trial. Autonomous runs reused public client codecs inside model-authored bindings;
the fully generated codec path has deterministic integration coverage.

The switchboard differs from the instrument in routing, field names, slot order,
reversed valve values and response semantics. It publishes prose and a client,
with no machine schema or JSON test oracle. Its action acknowledgment is not a
sensor observation. Pi adapted from these public sources, applied the requested
configuration and obtained a confirming read. This demonstrates one additional
interface family with no human binding intervention; it does not establish
universal benchmark support.

The first RGB-D attempt completed interface adaptation and instrument movement,
then the provider's token rate limit interrupted its scientific work. Its failure
and usage remain in the records. The serial follow-up also supplied an explicit
public camera rotation and depth convention, then completed the whole task:
read original arrays, load NumPy, reject invalid depth, apply calibration and
write world points `[[1, 0, 1], [2, 0, 2], [3, 2, 4]]` to `world-points.json`.
The external fixture checker confirmed the numerical result and target position.

Token totals include decision and independent-review requests. For failed
requests without provider usage, the table reports only the known lower bound;
unknown usage is never zero. Coverage above is recomputed from the original usage
records. The original development sidecars counted all recorded attempts in
`with_usage`; local reporting now counts only attempts with known token totals.
Original trial records have been retained unchanged.

The linked result files are byte-for-byte copies of the small original trial
summaries, retained in Git for review. Full traces, source snapshots and generated
outputs remain in the ignored local `outputs/autonomous-interface-local-20261026/`
directory; absolute paths inside the records describe that original workspace.

## Internet access

The [live network smoke record](evidence/local-implementation-20261026/internet-result.json)
confirms public Web search and document reading: a Bing RSS query returned
4,742 bytes and 12 references; reading the official Python `urllib.request`
documentation returned 216,510 bytes and 209 references. Discovery stores the
original bytes and source identities alongside readable text and followed links.

## Current scope

The local bootstrap-to-binding-to-interaction path is working. Future benchmarks
can use the same entry point when their public interfaces fit the supported
HTTP JSON or MCP transports. M3 repair mechanics have local fixture coverage;
autonomous drift repair on real targets, Linux deployment, cross-task releases
and systematic cross-benchmark evaluation remain later work. No further paid
trials or server deployment are part of this local verification pass.
