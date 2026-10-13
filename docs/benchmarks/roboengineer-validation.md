# roboEngineer integration validation

This record covers the October 13, 2026 development integration of the eight-objective collection. The runs use scripted engineering references and Harbor's `nop` agent. They are **not LLM model scores**. Raw trial outputs, video, feedback, policies and operator diagnostics are retained outside Git; task directories contain only reproducible inputs.

## Validation layers

| Layer | What was checked | Limits |
|---|---|---|
| Family physics and control | Randomized fixed-plant banks, fresh-process replay, controller admission, contact-based predicates, negative controls and video decoding | Local success alone does not establish container isolation or complete reference solvability |
| Generated packages | Explicit public allowlists; separate private simulator and no-network verifier; matching instance copies; numeric-only deployed policies; Python `-S` generation | Nominal geometry and training code are intentionally public |
| Shared service | Three adaptation rounds, artifact and feedback history, frozen selection, deadline persistence, interrupted-finalization recovery and verifier diagnostics | Reference scripts do not assess a model's visual reasoning |
| Native Harbor | Docker execution with `RCB_LIMITS_ENFORCE=1`, separate verifier, exact CPU replay and actual software-renderer receipts | G1's full GPU-training container run remains unperformed |
| Trace audit | Match delivered JSON and JPEG bytes to private service records; verify policy hashes, replay state, feedback and metric equality; fully decode recorded video | Stored public diagnoses describe intended changes; private model reasoning is not collected |

The new evaluators require MuJoCo **3.5.0**, NumPy CPU inference and OSMesa software rendering. Their runtime records verify that no GPU devices are exposed and identify the actual software renderer. Each development instance preserves one plant across adaptation and held-out cases; the second instance uses a different plant. These are reproducible development banks, not a claim that public repository seeds remain secret from a future competition participant.

## Native reference outcomes

The final selection contains **24 native Harbor trials**: one scripted reference and one no-submission control for each of 12 CPU instances. Every selected verifier accepted its evidence with `infra_error=0`, resource enforcement enabled, no observed limit violation, and no monitor or emergency-kill failure. All 12 no-submission controls score zero.

| Task | i00 success / score | i01 success / score | Reference status |
|---|---|---|---|
| Neural Fly fixed eight | 10/10 · 90.32 | 10/10 · 94.30 | Full scripted reference |
| AnyCar multi-surface | 10/10 · 73.21 | 10/10 · 72.87 | Full scripted reference |
| Go2 attitude | 10/10 · 91.06 | 10/10 · 91.24 | Full scripted reference |
| Go2 weave | 0/10 · 0.00 | 0/10 · 0.00 | Development-only |
| Go2 forward jump | 0/10 · 0.00 | 0/10 · 24.50 | Development-only |
| Go2 yaw jump | 0/10 · 9.80 | 0/10 · 14.70 | Development-only |

The selected references include **120 held-out cases**, each with an exact fresh-process replay, **36 adaptation rounds**, **2,346 delivered JPEGs**, **30,768 noisy telemetry rows**, and **240 fully decoded videos**. The audit matches delivered JSON/JPEG bytes to simulator records, checks every policy hash, compares replay states/metrics/feedback, verifies frame dimensions and sampling timestamps, and checks actual CPU/software-renderer receipts. A local HTML index connects every iteration, submitted diagnosis, policy change, delivered frame and held-out video. The reference scripts use numeric feedback; these runs do not measure an LLM's visual reasoning.

Historical diagnostics and superseded runs remain in the operator archive: 37 native jobs including diagnostic campaigns, plus separate regrades and G1 deployment-only evidence. All 20,115 archived files passed SHA-256/size verification. All 522 MP4 file copies represent 196 unique payloads, every one decoded successfully. The archive `native-validation.tar.gz` has SHA-256 `b53517150e6a5542a2d7b4acbc792477d29fe2096ba061e64db6dd728c0c69bb`. `acceptance.json` defines the selected trials; `independent-audit.json`, `media-completeness.json` and `artifact-manifest.json` retain the audit details. Counts from historical runs are not additional independent benchmark cases.

These runs used Harbor 0.23.0 on an AWS c7i.2xlarge CPU host. The run-scoped instance, security group, IAM profile/role and encrypted transfer bucket were removed after local evidence verification. No cloud GPU instance was created.

## Current acceptance boundaries

Neural Landing has its own completed native validation described in [its specification](quadrotor-landing.md#native-harbor-packaging-and-validation). The Control Transfer acceptance receipt selects a single final native run per task and per reference/no-op agent; earlier diagnostic runs are retained separately, including failed verifiers.

G1's schema-v2 banks have local trained-reference success **17/24** (6/12 and 11/12) versus released-reference **16/24** (6/12 and 10/12). Both plants remain incompletely solved. Real local PPO training and numeric export were exercised. The final CPU image and minimal public asset subset were also built on AWS. Four deployment-only adaptation cases (flat, slope, rough, steps) ran twice in separate Docker containers with networking disabled and no GPU devices: all state/feedback/metric pairs matched exactly, and all four videos decoded. Flat and steps passed; slope and rough fell. This is deployment packaging evidence, not a full Harbor training trial or a new held-out score. The AWS account's G/VT quota is zero, so no cloud GPU training or native GPU-device isolation result is claimed.

Go2 weave, forward jump and yaw jump remain **development-only** until successful references are established. A bounded search of 60 candidates over 180 adaptation episodes found no passing candidate; it used no held-out feedback and did not change success predicates. This result does not prove that the tasks are impossible. The current fixed-phase, 17-knot and linear attitude/rate controller interface may constrain future reference development.

## Isolation checks and fixes

The agent and private simulator occupy separate containers. Agent-container probes checked private model/instance/grade paths, evaluator imports, GPU devices, the Docker socket and AWS credential environment variables. Private HTTP routes return 404. During active adaptation, a package-registry request succeeds while non-allowlisted AWS and instance-metadata requests fail. Harbor temporarily uses its setup network policy before `agent.run()`; a startup probe is therefore retained separately from the active-agent probe. These bounded tests support the intended boundary; they are not a proof against every possible container exploit.

The shared review found and fixed:

- Signed integer minimum values could overflow `abs` during NPZ magnitude validation. Direct comparisons now enforce the same inclusive numeric bounds without overflow.
- An interrupted held-out finalization could fail on an existing output directory. Recovery preserves the interrupted directory and repeats the same frozen bank and artifact; a completed final result remains idempotent.
- Early termination could be lost when the runtime restarted. The service now persists its cutoff and rejects subsequent adaptation calls.
- A public AnyCar alias import failed outside the checkout. Both the top-level and qualified public entry points now pass an isolated nominal rollout.

## Verifier build incident

Native diagnostics found a second-instance verifier reading the first instance's baked JSON, even though the simulator and host source were correct. A plain Docker reproduction using separate build contexts showed the same stale copy. The transferred equal-size files had identical zero mtimes. Harbor 0.23.0 hashes all environment file paths and bytes; its local context-hash algorithm was not itself a Dockerfile-only cache key.

The generator now adds deterministic literal labels **before COPY**, containing the instance file hash and a hash of all copied verifier inputs (`grade.py`, normalized `test.sh`, `instance.json`, `rcb_limits.py`, `rcb_limits.json`). Build-time checks verify every copied file. Source transfers preserve mtimes. No random nonce, host path or relaxed verifier predicate is used. Corrected Docker builds distinguish both instances, and supported Harbor regrades retain the original simulator evidence. Full affected-instance reruns are recorded separately from regrades.

Private verifier diagnostics identify the rejection stage, exact bytes read, expected and actual digests, and file-read errors. The public score schema is unchanged. Original infrastructure failures remain in the archive rather than being presented as control failures or silently overwritten.

## Reproduction and review

Prepare the pinned nominal and private assets using `scripts/control_transfer/prepare_assets.py` and `images/control-transfer/prepare_assets.py`; the public G1 source subset must contain only the G1 dependency closure. The training image declares EGL and pins the tested W&B version, but its full CUDA wheel/driver combination still requires a GPU-container test. Private weights, model manifests, policies and held-out banks must not enter the nominal image.

```bash
python3 -S -m scripts.control_transfer.gen_tasks check
bash ci_checks/run_all.sh tasks/control-transfer-*/
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/control-transfer-anycar-i00-standard -a oracle -e docker
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/control-transfer-anycar-i00-standard -a nop -e docker
```

Repeat native oracle/no-op checks for both instances of each admitted family. An infrastructure verdict must be resolved separately from a controller failure. Changes to task inputs require regenerated task copies and Harbor manifest digests. Benchmarks with incomplete references require the repository's human review; successful integration does not remove that gate. All new tasks still need actual coding-agent evaluations before model comparisons are reported.


## Subsequent optional circuit extension

The AnyCar historical-circuit extension is separate from the native ellipse results above.
Pinned F1DB geometry covers 78 World Championship venues, 160 recorded layout versions
(159 runnable; one malformed Buenos Aires outline is explicitly unavailable), and a synthetic
zigzag. The registered variant is `circuit-sector/1`, with 24-second prescribed-time sectors,
three adaptation rounds and ten held-out cases per plant. Optional circuit tasks have
`oracle="none"`; these are not additional native Harbor successes or LLM evaluations.

The worker's frozen-source validation passed one bend-focused CPU sector per venue plus
zigzag (79/79), with four decoded dual-view videos and exact rendered/non-rendered replays.
All 159 historical interpolants and zigzag pass geometry checks; this does not establish
full-lap or all-layout physical acceptance. The synthetic zigzag separately completed one
169.3-second nominal lap. Track outlines are scaled planar schematics, not surveyed 3D tracks.

Integration checks pass 16 AnyCar numerical/geometry tests and three standard-library
packaging tests, including 320 distinct layout/plant specifications and rejection of misplaced
private files. Actual generated public-only nominal training and private CPU deployment
were exercised on zigzag/i00 and Monaco/i01. Both deployment cases succeed and reproduce
state, noisy feedback and metrics exactly in fresh processes; both 1280×480 videos decode,
and the adapter returns 50 frames and 482 noisy rows total. One original held-out ellipse
case per plant also reproduces the archived state, metrics and noisy feedback exactly.
These local checks do not establish container/device isolation for circuit tasks.

Evidence is in the separate `anycar/historical-circuits-v3` and
`anycar/integration-circuits-v1` operator directories, with source manifests and receipts.
The prior native archive and videos remain unchanged. See the [AnyCar task guide](roboengineer-anycar.md#generating-optional-circuit-tasks)
for listing or generating any historical layout, or the full optional 320-task suite.


## General-eight Neural Fly extension

`control-transfer-neural-fly-general-v1-i{00,01}-standard` is a separate revision from
fixed-eight native acceptance above. Commands vary yaw, plane (vertical, horizontal,
inclined), traversal sense, amplitudes, rate, phase and center. Both held-out banks
include all three plane classes and both senses for each wind stratum; ten cases do
not cover the full 30-combination plane/sense/wind product. Plant draws, controller
ABI, feedback fields, score thresholds and the private clipped force surrogate are unchanged.

The frozen earlier scripted controller succeeds in **18/20** new cases, with mean
score **79.5960**. Instance i01 retains a tracking failure (case 3, RMSE 0.27468 m)
and a crash (case 6, 1.72 s); there was no reference retuning. The generated private
packages independently reproduce all 20 whole records exactly, including both
failures. One legacy case per plant also matches its archived record exactly.
Four new generated-package videos decode; their delivered feedback contains 130
hash-verified images and 1,287 noisy rows with the physical timestamp offset preserved.
Both generated public-only nominal packages complete a reverse horizontal six-lap
rollout at rate 0.8, without importing trusted code (472 rows, RMSE 0.08151 m).

The new task metadata is `oracle="none"`. These are local CPU integration checks,
not a new three-round adaptation campaign, native Harbor/device-isolation acceptance,
or LLM model scores. Source compatibility tests retain exact old specification
fingerprints and require explicit revision tags on new cases. The operator evidence
is under `neuralfly/general-eight-v1`, `neuralfly/revision-dispatch-v1` and
`neuralfly/integration-general-v1`; old fixed-eight evidence remains separately archived.


## Historical-circuit full laps

The new `circuit-lap/2` variant requires every ordered gate (spacing at most 0.5 m)
and an actual interpolated finish crossing. It retains the complete route and traction
patches, with a route-length-dependent horizon. Existing ellipse and 24-second sector
banks remain separate. The 159 runnable historical layouts plus zigzag have frozen
public duration metadata; no claim is made that every layout has been physically
validated for a full lap.

The worker's frozen nominal-controller examples completed Silverstone, Monaco and
Suzuka in 395.5598, 596.7122 and 474.8703 simulated seconds. These are scaled,
prescribed-speed tracking times, not competitive F1 lap times. Its full Silverstone
video replay is exact and its no-op scores zero. Integration independently executed
the generated Silverstone/i00 and Monaco/i01 held-out case 0 twice each: both pairs
match complete records exactly and pass every gate and all four traction surfaces.
Their lap times are 395.5598 and 596.7986 seconds; Monaco/i01 is a different plant
from the worker's earlier example and its score is kept separate.

The new adapter was run on the complete frozen Silverstone recording: all 3,976 noisy
rows are preserved, 128 JPEG byte hashes verify, image timestamps span 0 through 397.5 s,
and the full 397.6-second video decodes with unchanged bytes. This is an imported,
previously recorded full video used to validate the new feedback path, not a new
native Harbor recording. Public feedback contains only permitted noisy measurements,
commands and images. The private record is not delivered.

Full-lap tasks declare a separate 129600-second agent cap to accommodate long
CPU-rendered episodes over three rounds; it is not an estimated cloud bill or a claim
that every run takes 36 hours. Worker, replay, extraction, HTTP and collection deadlines
are bounded from the frozen public route duration. Legacy task cutoffs and frame
schedules are preserved. The new tasks remain `oracle="none"`; native Harbor,
all-layout physical acceptance, complete multi-round campaigns and LLM evaluation
remain unperformed. Operator receipts and exact generated-source/artifact hashes are
under `anycar/integration-full-laps-v1`.
