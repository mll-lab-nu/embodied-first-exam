# LIBERO-Pro implementation validation — 2026-10-19

These are framework acceptance checks, not a benchmark success-rate or latency
comparison. Each arm ran one capped episode on `libero_object_task/0`, seed 0,
using Azure `gpt-6-astra` with medium reasoning effort. The GPU was an NVIDIA
RTX 2080 Ti (11 GB), node `z3001`, driver `580.178.04`, Slurm allocation
`42022817` in the `ckpt` partition, account `ckpt-stf`.

## Four real episodes

| Harness | Simulator verdict | Actual control steps | Model HTTP attempts | Usage coverage | Total tokens | Decision seconds |
|---|---|---:|---:|---:|---|---:|
| Bare API | success | 107 | 11 | 100.0% | 28,710 | 330.99 |
| Codex App Server | success | 106 | 17 | 94.1% | unknown; known subtotal 79,768 | 154.63 |
| Pi RPC | success | 107 | 13 | 100.0% | 55,784 | 136.25 |
| RoboRSI Frozen | success | 106 | 23 | 100.0% | 142,410 | 179.72 |

All four ended without an episode infrastructure error, unfinished span or
unfinished controller command. The four runs have identical hashes for the
39-tool catalog, framework source, released knowledge, scene and complete
initial snapshot; all selected actual initial-state index 0. Every recorded
controller command has eight dimensions. Raw native events, RoboRSI workspaces,
HTTP evidence, per-run reports and offline log replay pages were retained.

Codex's first model attempt failed while opening the cluster egress tunnel
(`503 Service Unavailable`). Its native retry recovered. That failed attempt
has no usage: the total stays unknown and the known subtotal remains visible.
It is not silently charged as zero. The other three runs have usage for every
attempt. USD costs remain unknown because no explicit Azure rate card was given.

RoboRSI ran one Planner, one Engineer and one Reviewer round with
`ROBORSI_ROLE_SESSION=0` and frozen mode. The actual Planner request contained
both camera images. Native Codex and Pi both passed the OS isolation probe;
their original model/tool/context flows own the decisions. See the
[adapter change register](LIBERO_ADAPTATIONS.md) for execution-protocol and
image-transport adaptations.

The smoke limits were 12 environment calls, 6,000 control steps and a 900-second
outer harness cap. That cap includes native startup, while the decision column
above excludes it. Separate environment startup was 69.55 / 89.26 / 85.65 /
83.16 seconds in table order; native startup was another 220.86 seconds for
Codex and 70.35 for Pi. Shared PyRoKi startup is recorded in `services.json`.
Cold shared-filesystem imports affected timings, so this table is not a speed
ranking. Nested model/skill/perception/motion times are not added together.

## Replay results and limits

No-API actuator selfchecks passed on both an A40 (`g3046`, job `42022624`) and
the RTX 2080 Ti. Each recorded and replayed 13 episode controls, with maximum
qpos error `4.494484216301743e-18`, qvel error `2.45930318247937e-15`, and matching
final success verdicts.

The production replay now passes for all 107 recorded controls from the
successful Bare API episode: maximum qpos, qvel and act errors are all **0.0**,
the final simulator verdict matches, and no configuration drift was detected.
There are no model requests. This is an observed result on this pinned machine,
not a guarantee of bitwise agreement across machines or dependencies.

The first long replay correctly reported a mismatch at tolerance `1e-6`:
qpos `0.00011894853672525518`, qvel `0.05890689924214457`, act `0.0`, with the
final success verdict still matching. The largest deviations were in the
cream-cheese object's free joint. Identical controls and initially tiny errors
made it possible to isolate the cause: forward/observation refresh after
restoring the snapshot overwrote MuJoCo's saved solver warm-start inputs.
Restoring those integration inputs last fixed the issue. A diagnostic replay
and then a separate run through the installed production replay entry both
returned zero state error. The regression test explicitly exercises that
refresh/restore ordering.

Original commands, state journals, the first difference report, and the
no-API diagnostic probe are retained. No intermediate reference-state resets
or relaxed tolerance were used. `corrected_physics_check.json` is the final
result; `nontrivial_physics_check.json` remains the original mismatch evidence.
Each replay now records its own `framework.json` and source hash. The validated
replay source hash is
`b78ab57452d557a72a5520127e9c92d9c5802005197f0dc455d775c2354ad1d5`.

## Automated checks

- Full local regression run after the replay fix: 339 passed, 4 skipped.
- Focused protocol plus newly added same-configuration rerun checks: 18 passed.
  These cover durable deduplication, uncertain/failed commits, stale/schema
  rejection, owner-thread execution, stream/nonstream/chat/compaction metering,
  real SDK retries, loopback proxy handling and missing usage. The rerun fixture
  verifies snapshot restoration into a new attempt and rejection of source
  drift before model work. Its model and robot are synthetic, with no API cost.
- Server Planner image tests: 2 passed; RoboRSI adapter integration: 1 passed.
- Actual Codex App Server and Pi RPC with a synthetic robot/model both passed
  discovery, roundtrip, retained history and filesystem/credential isolation.

## Evidence and deployment

Full artifacts and large assets remain on Klone. Only this small audit summary
and source/documentation files are retained locally.

```text
/gscratch/stf/hengyil6/libero-bench/outputs/smoke-42022817-r2/
/gscratch/stf/hengyil6/libero-bench/logs/verify-42022817-r2b.log
/gscratch/stf/hengyil6/libero-bench/source-snapshots/acceptance-r2-20261019.tar.gz
```

The result root contains `acceptance_audit_final.json`, `libero_summary.json`,
`corrected_physics_check.json`, the earlier audit/replay reports, and each arm's
independent run directory. Allocation `42022817` was explicitly released after
validation; its Slurm cancellation is cleanup of the paused batch shell and
shared solver, not an episode failure.
A small local copy of the audit is [available here](validation/libero-2026-10-19.json).
The exact source archive has SHA-256
`241f0eec0ddcc3b21d64a087ee74f01f40c5a7394a8142088af6449f0a5e52e5`.
The post-fix replay source is preserved separately as
`source-snapshots/acceptance-replay-fix-20261019.tar.gz`. The original R2 rollout
archive is unchanged. The replay-fix archive SHA-256 is
`89412990ecf08eed055cf8f970789bfbc9d51eb91daf425662f307a439806438`.
Local source also has docstrings for repository checks;
all 12 relevant current Python modules were compared with the installed server
copies and their ASTs match after removing docstrings. Exact files, including
harmless archive metadata entries, remain preserved. Strict reruns of an old
run must use its matching archived framework; the newer replay source identity
is recorded independently.

Earlier attempts and their logs were retained: empty-array snapshot restore,
GPFS journal overhead, loopback proxy routing and a cold native version probe
were repaired before this four-arm cohort. The active journals use `PERSIST`
and `FULL` durability. No original attempts were overwritten.

The common configuration uses the released analytic grasp fallback; optional
SAM3/GraspGen services are disabled for all arms. This validates the framework,
not the published full-perception configuration or the LIBERO-Pro perturbation
suite. A campaign still needs a frozen perception-service choice and paired
multi-task panel. No recurring automation was created.
