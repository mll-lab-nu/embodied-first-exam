# Autonomous interface adaptation: local implementation

The `harness-improving` branch now runs the same pinned Pi 1.3.0 session from a
minimal public bootstrap, with no target binding or initial observation. This is
the local M0–M3 implementation of the
[current plan](analysis/pi-harness-optimization-20261021/IMPLEMENTATION_PLAN.md#current-execution-plan--2026-10-26).
It has not been deployed to the frozen HumanCLAW pilot.

## Entry point

```sh
python -m humanclaw_bench.harnesses.adaptive.run \
  --bootstrap bootstrap.json --output outputs/interface-task
```

For example, a bootstrap can contain only:

```json
{
  "schema": "bootstrap-v1",
  "task": "The user's task",
  "entries": ["https://example.org/instrument/docs"],
  "transports": [{"id": "instrument", "kind": "http", "root": "https://example.org/instrument/api"}]
}
```

The URLs above are placeholders. `source_roots` grants access to local files or
private/local documentation servers; public Internet reading is enabled by
default. `internet: false` confines a local fixture to its declared sources.
Optional `max_actions` and the harness configuration's task timeout are ordinary
task limits. Neither an action map nor sensor dimensions, success semantics or
an initial image belong in this bootstrap. An optional transport `credential_env`
refers to an existing host credential; its value is never sent to Pi or programs.

Existing calls that explicitly supply an `EnvironmentBridge` remain the
HumanCLAW baseline. A bootstrap session cannot inject that binding as a fallback.
Both paths retain the existing provider transport, usage accounting, medium/high
effort mechanism, context projection and completion checks.

## Implemented path

1. `discover` reads public pages, schemas, client source, examples and resources;
   `query` searches the public Web. HTML is projected to readable text and links
   while original bytes, URI, hash, question and read time remain in the source
   store. MCP entries support `mcp://HANDLE/tools`, `/resources`, `/templates`
   and `/resource?uri=...`. `registry` only lists tools and exposes the generic
   artifact contract; an empty target registry does not end discovery.
2. `workspace` keeps sources, resources, scientific packages, programs and
   outputs for the task. Package inspection includes dependency requirements;
   setup copies an installed exact version or downloads a pinned wheel into the
   task directory. NumPy computation and persistence are tested. Original RGB-D
   arrays retain dtype, shape, units, invalid values, frame, timestamp,
   observation association and supplied calibration. Selected RGB previews are
   separate from numerical depth access.
3. `adapter.propose` stores an immutable artifact with source/dependency
   identities, public-client reuse or generated code, operation schemas, codecs,
   effects, timing, native action costs and unresolved semantics. Codec code
   handles `encode`/`decode`; the host dispatches the declared HTTP/MCP operation.
   The kernel contains no instrument/switchboard/benchmark mapping.
4. `adapter.validate` runs syntax/schema checks and independent source examples,
   followed by a separately metered model review of the public contract. Ordinary
   prose/client examples need no manually authored JSON oracle: the independent
   reviewer derives reference cases, which the host executes and records.
   Mandatory failed checks cannot be approved by review. Reports are cached.
5. `adapter.probe` uses the normal durable broker, policy/evidence record and
   native task limits. `adapter.register` exposes only successfully verified
   scopes. An acknowledgment without sensor data clears the current observation;
   subsequent decisions that require an observation must read one. No publication
   panel is required for this first task-local interaction.
6. Changed public sources or failed response codecs invalidate affected bindings.
   Repair creates a checked child; a compatible checked parent can be reused.
   A received response with a broken decoder retains its raw data and completed
   transport receipt. A lost dispatch outcome remains indeterminate; a reviewed
   public status operation can reconcile it without replaying the action.

Source/dependency/validation evidence works before a first observation exists.
After registration, new public execution evidence can justify another interface
scope. Reworded proposals and identical source reads do not create new candidates
or repeat reviews. Pi preserves the pending artifact/report in durable context
and advertises its next legal lifecycle actions. Task-policy candidates keep
their separate observation-based progress rule from the 0515 repair.

Generated code uses the existing OS isolation with task package/source/resource
reads and persistent output writes. Environment access remains a broker callback;
there are no additional approval steps or reasoning quotas. Scientific setup,
validation, probes and execution consume the same task clock.

## Validation and records

`tests/test_adaptive_discovery.py` covers empty bootstrap, schema/client paths,
deduplication, corrected children, compatible-parent reuse, field/unit changes,
received-but-undecodable responses, uncertain dispatch reconciliation, scientific
packages, depth in millimetres/metres, invalid values, missing depth, original
resources, file/network isolation, MCP initialization/resources and a real Pi SDK
run with a scripted provider. Scripted providers test integration, not autonomy.

Actual model trials use only public fixture surfaces:

```sh
python tools/adaptive_local_check.py --family schema --output outputs/interface-schema
python tools/adaptive_local_check.py --family client --output outputs/interface-client
python tools/adaptive_local_check.py --family rgbd --output outputs/interface-rgbd
python tools/adaptive_local_check.py --family heldout --output outputs/interface-heldout
```

Run paid trials sequentially to avoid stacking requests on the shared provider.
The distinct switchboard family uses POST RPC, reversed valve codes, no machine
schema or JSON oracle, and acknowledgments without observations. Each trial saves
the generic runtime identity **before** exposing its interface. No handwritten
binding, semantic map or adapter edit is supplied during an autonomous trial.

`trial-spec.json` fixes scope and the scheduled trial count. `interface-trial.json`
retains source/artifact identities, reports, registered scope, time to first
observation/action, provider usage and coverage, including failed sessions.
The external fixture runner writes `result.json` with independently checked
`adaptation_status` and `task_outcome`. A bare harness session reports task outcome
as unscorable, not evaluator success. Cold development trials are not a controlled
performance comparison; their exact source snapshots remain in the reports.

Current results are recorded in
[LOCAL_IMPLEMENTATION_RESULTS.md](analysis/pi-harness-optimization-20261021/LOCAL_IMPLEMENTATION_RESULTS.md).

## Remaining scope

The implemented transports cover HTTP JSON and Streamable HTTP MCP with JSON or
finite response streams. A public Python client's pure codecs can be reused in
the scientific workspace; clients requiring their own network connections must
use a managed transport wrapper. Arbitrary proprietary/binary transports, browser
authentication flows and all possible third-party SDKs are not claimed supported.

Workspace persistence is within a task; it does not restore a lost physical
environment or resume indeterminate work automatically. Cross-task publication,
retrieval and broad benchmark evaluation are M4/M5 work. M3 repair mechanics have
deterministic fixture coverage; autonomous drift repair on real target environments
and Linux deployment compatibility still require a separately frozen cohort.
The current server pilot must retain its original code, dependencies and jobs.
