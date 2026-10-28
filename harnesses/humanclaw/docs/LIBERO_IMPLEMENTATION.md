# LIBERO-Pro four-harness implementation

The experiment compares bare API, native Codex App Server, native Pi RPC, and
RoboRSI Frozen with direct-API roles. RoboRSI upstream baseline: 6f0107219d73dcf549b19e585f884f6b3fc3dac6.
No HumanCLAW campaign is resumed by this implementation.

## Implemented contract

- Shared resolved tool catalog, immutable skill/knowledge provenance and hash.
- Owner-thread tool service with durable request journal, payload conflict checks,
  stale-observation rejection and indeterminate-execution handling.
- Private evaluator, complete post-reset state, actual 8-D controller commands and
  per-control-step states. Physics replay never calls an agent or perception model.
- Actual HTTP request metering, streaming/non-streaming Responses and Chat
  Completions, raw usage, unknown usage coverage, explicit pricing.
- Thin native adapters; retain native decision, context and recovery loops.
- RoboRSI Planner image transport patch, recorded separately from orchestration.
- Protocol, retry, isolation, metering and replay checks before live GPU episodes.
- Fixed paired task/initial-state panel; each attempt has fresh output and sessions.

Large assets, environments and rollout outputs belong on the server under
`/gscratch/stf/hengyil6/libero-bench`. Local outputs contain only small validation
reports unless explicitly requested. Slurm submission is one-off; no scheduled
monitor or automation is created.

## Run one episode

On the prepared Klone installation:

```bash
source /gscratch/stf/hengyil6/libero-bench/framework/tools/klone_libero_env.sh
/gscratch/stf/hengyil6/libero-bench/venv/bin/python -m humanclaw_bench.libero.run run \
  --harness bare --task libero_object_task/0 --seed 0 \
  --config /gscratch/stf/hengyil6/libero-bench/framework/configs/libero/klone.json \
  --roborsi-root /gscratch/stf/hengyil6/libero-bench/RoboRSI \
  --env-file /gscratch/stf/hengyil6/HumanCLAW/.env \
  --output /gscratch/stf/hengyil6/libero-bench/outputs/example \
  --max-calls 12 --max-control-steps 6000
```

Run inside a Slurm GPU allocation. Select `bare`, `codex`, `pi`, or `roborsi`.
This single-episode command assumes the shared PyRoKi service is already running
and `ROBORSI_PYROKI_PORT` points to it. The batch entry below starts and stops that
service automatically. The prepared Python environment, pinned model assets,
LIBERO-Pro data and native binaries stay on Klone; this repository does not
vendor those installations.
Use a fresh Python process for every episode; upstream RoboRSI has import-time
home/session caches. The runner always creates a new run directory. Keep model,
reasoning effort, tool catalog, task, actual state index, controller and budgets
paired across arms. The small smoke configuration is not a success-rate study.

`tools/klone_libero_smoke.sbatch` performs a no-API physics check first, starts
the pinned solver, then runs one capped episode per arm. Submit once with an
eligible account/partition. It stops before paid runs if selfcheck fails. The
account, GPU and queue are site-specific, not properties of the harness.

The exact tested native isolation launcher is retained as
`tools/klone_native_isolated.py`. On this installation it is deployed as
`/gscratch/stf/hengyil6/native-harnesses/20261015/bin/native_isolated.py`;
the `bin/codex` and `bin/pi` wrappers invoke it with the corresponding harness
name followed by the original arguments. It requires the pinned native bundle,
bubblewrap and its libraries. Its paths are site-specific. A new machine must
prepare equivalent runtimes, update the paths and pass the synthetic isolation
check before a live native run; the runner refuses an unverified launcher.

## Inspect, replay, or rerun

```bash
python -m humanclaw_bench.libero.run replay /absolute/run_directory --mode log
python -m humanclaw_bench.libero.run replay /absolute/run_directory --mode physics \
  --roborsi-root /absolute/RoboRSI
python -m humanclaw_bench.libero.run rerun /absolute/run_directory \
  --output /absolute/new_output --env-file /absolute/private.env
python -m humanclaw_bench.libero.run report /absolute/results_root
```

Log replay creates a standalone `replay.html`, uses no API or simulator, and
links event/span IDs to raw requests, images and actual controller commands.
Physics replay restores the saved simulator/controller/RNG state and executes
only recorded 8-D controls. It saves per-step qpos/qvel/act errors, configuration
drift and final-success agreement, without claiming bitwise cross-machine
reproducibility. An incomplete actuator journal cannot be certified. Rerun
creates a new billable agent attempt using the original configuration and
snapshot; a changed catalog is rejected. Model output can legitimately differ.
The configured outer wall-clock cap currently includes native client startup;
the reported decision latency excludes that startup. Use the same declared cap
for the smoke checks, and do not use their cold-start timings as a harness
performance ranking.

## Run artifacts and metrics

| File | Contents |
|---|---|
| `run.json` | Run/episode identity, effective parameters, final verdict/reason, infrastructure errors, explicit pricing |
| `events.jsonl`, `artifacts/` | Linked spans, actual HTTP messages/images/replies/raw usage, retries, errors, native events |
| `requests.sqlite` | Durable top-level request deduplication and cached results |
| `initial_state.json`, `scene.xml`, `motion.sqlite` | Actual initialized state/RNG/controller, scene, real control commands and before/after state at every step |
| `capabilities.json`, `framework.json`, `assets.json` | Tool/knowledge hashes, sources, controller, observation contract, dependencies, dataset/model/native-runtime revisions |
| `observability.json` | Observable boundaries and limits |
| `native/`, `roborsi_home/` | Original native sessions and RoboRSI workspaces/traces |
| `report.json`, `replay.html` | Per-run metrics and timeline |
| `libero_summary.json` | Batch results with denominators, unknown usage/cost, mean/median/P95 |

Each actual provider request counts once. Native usage notifications are not
charged again. Cached input is an input subset; reasoning is an output subset.
Failure/retry/compaction requests are retained. Missing usage is unknown and
reduces coverage. Azure prices are not inferred: without an explicit versioned
USD rate card, dollar cost stays unknown. Rate cards must identify model,
provider, date, version, input/cached-input/output prices per million tokens.

The main latency is observation/task delivery to harness completion, including
Reviewer and retries. Native startup and environment startup are reported
separately. Nested skill/perception/motion/model spans overlap and must not be
added as independent wall time. Both failed and successful attempts contribute
to timing/token distributions; infrastructure failures are separated from the
scored-attempt denominator. The batch report does not select best-of-K attempts.

## Validation and adapter boundaries

The protocol tests cover durable replay prevention, stale/conflicting requests,
uncertain execution, worker-thread rejection, shared MCP/JSON dispatch, SDK
retry accounting, stream/nonstream/chat/compaction usage and missing usage.
`python -m humanclaw_bench.libero.smoke` drives the real native processes with a
synthetic model and robot, without paid calls. The server `doctor` additionally
checks real actuation and physics replay. Live acceptance is separate from
these synthetic checks.

See [the adapter register](LIBERO_ADAPTATIONS.md) for every experiment-facing
change, the Planner patch, the initial perception-service configuration, and
which aspects of each native harness remain in control.
