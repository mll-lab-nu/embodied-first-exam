# roboEngineer integration validation

> Historical development evidence. Paths under `tasks/control-transfer-*` and `tasks/quadrotor-landing-*` below refer to the pre-migration checkout. Current packages live under `experimental/roboengineer/tasks/`; use its explicit checks. Earlier branch-local CI success does not establish compliance with main. See [the compatibility assessment](roboengineer-main-compatibility.md).

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

Each task's verifier Dockerfile carries a deterministic literal label **before COPY** with the instance file hash (`roboengineer.instance_sha256`). Build-time checks verify every copied file. Source transfers preserve mtimes. No random nonce, host path or relaxed verifier predicate is used. Corrected Docker builds distinguish both instances, and supported Harbor regrades retain the original simulator evidence. Full affected-instance reruns are recorded separately from regrades.

Private verifier diagnostics identify the rejection stage, exact bytes read, expected and actual digests, and file-read errors. The public score schema is unchanged. Original infrastructure failures remain in the archive rather than being presented as control failures or silently overwritten.

## Reproduction and review

Prepare the pinned nominal and private assets using `images/control-transfer/stage_nominal_assets.py` and `images/control-transfer/prepare_assets.py`; the public G1 source subset must contain only the G1 dependency closure. The training image declares EGL and pins the tested W&B version, but its full CUDA wheel/driver combination still requires a GPU-container test. Private weights, model manifests, policies and held-out banks must not enter the nominal image.

```bash
bash ci_checks/run_all.sh tasks/control-transfer-*/
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/control-transfer-anycar-i00-standard -a oracle -e docker
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/control-transfer-anycar-i00-standard -a nop -e docker
```

Repeat native oracle/no-op checks for both instances of each admitted family. An infrastructure verdict must be resolved separately from a controller failure. Changes to task inputs require updated task copies and Harbor manifest digests. Benchmarks with incomplete references require the repository's human review; successful integration does not remove that gate. All new tasks still need actual coding-agent evaluations before model comparisons are reported.


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
The prior native archive and videos remain unchanged. See the [AnyCar task guide](roboengineer-anycar.md#historical-circuits-and-zigzag-circuit-sector1)
for the historical layouts.


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


## AnyCar F1TENTH-style appearance update

The procedural GT-style RC shell, glazing, rear wing, lamps and spoke wheels are
visual-only. The existing AnyCar dynamics and collision primitives are retained;
this is not a newly calibrated F1TENTH chassis. Public nominal and private deployment
packages use identical model source, with refreshed task digests identifying the
appearance change. Existing recordings remain associated with their original digests.

Integration compares the old and new models on both plants, for ellipse and Silverstone
commands: mass, inertia, joint, actuator and active collision arrays match, as do all
500 driven control steps per pair (5,000 physics steps each). A fresh generated-package
24-second ellipse recording and independent non-rendered replay match physical state,
noisy feedback and metrics exactly; the rendered record also equals the archived
pre-change record, including its runtime metadata. Rendering metadata correctly differs
for the non-rendered replay. The new 1280×480 video decodes into 241 frames and the
adapter delivers 25 hash-verified JPEGs with all 241 noisy rows. Both preview panels
were inspected. All 125 existing AnyCar MP4 hashes remain unchanged.

Thirty existing vehicle, circuit, lap-runtime and packaging tests pass. Repository CI
passes all 20 Control Transfer task checks and 113 mutation checks; its system-Python
optional NumPy/requests tier is skipped, with affected tests run separately in the
pinned numerical environment above. The separate
operator evidence is `anycar/integration-f1tenth-visual-v1`; the worker preview is
`anycar/f1tenth-visual-v1`. This is a visual integration smoke test, not a new full-lap,
multi-round, native Harbor or coding-agent campaign.


## Explicit Skydio appearance revision

`neural-fly-general-skydio-v1` adds two tasks with observation revision
`neuralfly-skydio/1`. All 1,512 files in the preceding 20 Control Transfer task
directories remain byte-identical, including their primitive renderer and image
references. The new tasks use 0.1.1 image tags and explicitly enable the same
Skydio profile in nominal training and private deployment. Pinned Apache-2.0 mesh,
texture and attribution assets are staged outside Git, checked before copying, and
verified again by Docker's build instructions. The agent's helper omits operator
download code; runtime requires local matching assets and has no fallback.

Generated private packages reproduced a successful i00/case1 flight and the retained
i01/case6 crash in separate rendered/non-rendered processes. All four entire records
match the pre-visual general-eight records, including state, telemetry, metrics and
private scenario/dynamics. The success retains score 87.6987 and the crash remains
zero at 1.72 seconds. These are frozen-controller compatibility checks, not new
agent scores. The two 960×720 videos decode into 378 and 18 frames; all 40 delivered
JPEG hashes and 396 noisy rows verify, with the existing +0.02-second timestamp
origin preserved. A public-only reverse-horizontal nominal rollout at rate 0.8
produces a decoded 472-frame video and the prior RMSE 0.0815133 m without trusted
imports. The evaluation preview was visually inspected.

All 79 pre-existing Neural Fly video hashes remain unchanged. Thirty distinct
family/spec/visual/packaging tests pass, including separation of render and physics
models and rejection of corrupt assets. Repository CI passes all 22 task contracts
and 115 mutation checks; the optional system-Python NumPy/requests tier is skipped,
with the affected numerical/visual suites executed separately in the pinned runtime.
The operator receipts are under
`neuralfly/integration-skydio-v1`. The 0.1.1 Docker build, container isolation and
native Harbor/LLM campaign have not been run; this appearance does not constitute
a calibrated Skydio dynamics model or establish full-bank solvability.

## Compact 30-second circuit laps

`circuit-compact-lap/3` uses separate public `compact-30s/1` geometry. All 160 runnable
routes are precomputed at 45 m, with recorded smoothing and aspect widening. They are
F1-inspired approximations, not preserved historical outlines. The target lap is 28 s;
the CPU deployment always runs to the hard 30 s horizon. The car dynamics, numeric ABI,
scoring thresholds and persistent-plant randomization are unchanged. The four default
compact tasks cover Silverstone and Monaco on plants 10100 and 11100; all other routes are
in the compact route catalog. The ordinary four-hour agent budget
applies; the older long-lap track retains its separate budget and geometry.

Worker commit `319ecc464299e752548fdcc7562aed3f694340f9` reports 160/160 adaptation-only
nominal-controller laps, alternating the two plants, with actual finish times
28.0147–28.1447 s. All four traction surfaces are contacted. This is broad geometry and
controller smoke coverage, not all-layout held-out or coding-agent acceptance. Its source
and artifact hashes were checked during integration.

Integration independently ran the exact generated private packages on Silverstone i00
and Monaco i01, using the unchanged default policy on the first held-out case. Both pass,
with finish times 28.0483 and 28.1290 s and scores 60.0126 and 37.6700. Each physical state,
noisy trajectory and metric matches a fresh-process non-rendered replay exactly; expected
render-backend metadata differs. Both no-op controls score zero. These two probes are not
complete held-out bank results. Both public-only nominal CLI runs finish with finite
1501×19 trajectories and no trusted imports.

The two real CPU OSMesa/llvmpipe recordings decode fully at 1280×480, 301 frames each.
The generated feedback adapter delivers 31 images at exactly 0–30 s per case and preserves
all 301 noisy rows. All 62 delivered JPEG byte hashes and 602 noisy rows are audited;
the Silverstone frame at 7 s was visually inspected. Measured render wall times are
25.22 and 33.09 s on this host, not universal hardware bounds.

All 22 pre-existing canonical task specifications remain unchanged. Generated ellipse and
long-lap replay probes match their earlier physical records and feedback exactly. All 129
prior AnyCar MP4 hashes remain intact. Shared source copies and task digests are refreshed;
this is not a claim that old task package bytes are unchanged. The subsequent optional
reference-line and cone appearance commits are not included in this revision.

Thirty-six focused numerical/runtime/packaging tests pass, including all 320 compact
route/plant specifications, rejection of mismatched private route revisions, and separation
from the long-lap budget. Optional zigzag and Valencia generation/check runs pass without
site packages. Root evidence is `anycar/integration-compact-v3`; worker evidence is
`anycar/compact-30s-v1`. The initial integration driver's final spec comparison exposed
Python tuple-versus-JSON-list representation differences; canonical JSON comparison and
an independent artifact audit pass. No rollout, controller or success predicate was
changed to address that audit-only issue.

Compact tasks remain `oracle="none"`. Native Harbor, local GPU-device isolation, full
multi-round held-out acceptance and LLM evaluation have not been established for this
revision. No cloud resources or published site were changed by this integration.

Repository CI passes all 26 Control Transfer task contracts and all 117 deliberate
mutation checks, including compact revision/cutoff violations. The optional global
NumPy/requests service-test tier is skipped by system Python; the affected numerical and
runtime checks were run separately in the pinned MuJoCo 3.5 environment above.

## Public reference-line observation revision

Worker commit `be58433a0cec3af93c838952bd39425bdcbbbaeb` replaces the target dot with a
continuous cyan commanded centerline in both AnyCar camera panels. All generated AnyCar
packages explicitly declare `anycar-reference-line/1`. The overlay depends only on public
route geometry, not robot state. Numeric feedback, physical trajectories, task geometry,
policies and scoring are unchanged; image observations intentionally change.

The generated compact Silverstone i00 first held-out spot-check retains byte-identical
physical record and noisy-feedback files relative to the preceding target-dot run.
A fresh-process non-rendered replay matches physical state, feedback and metrics. The full
1280×480, 301-frame CPU OSMesa/llvmpipe clip decodes; all 31 delivered JPEGs span 0–30 s
and all 301 noisy rows are retained. The actual finish is 28.0483 s, score 60.0126.
This is one scripted-controller spot-check, not an LLM run or complete held-out bank.
The largest legacy route, Valencia-1, renders with 3378 of 10000 scene geoms, including the
257-point line. All 131 earlier AnyCar video hashes remain unchanged.

Thirty-six focused tests and repository CI pass, including all 117 existing mutation
checks and 26 task contracts. System Python skips the optional NumPy/requests global tier;
the affected numerical/runtime checks run separately in the pinned environment. Operator
evidence is `anycar/integration-reference-line-v1`. The benchmark site adds the exact MP4,
feedback JSON/JPEGs, public task specification and nominal policy. Browser playback uses
a separately identified 960×360, 10 fps VP9 WebM preview because the installed
Chromium lacks H.264 support; original artifact bytes remain unchanged. Private case banks,
dynamics and true-state records are excluded from the website export.

Earlier native reference evidence predates this image revision. Native/model acceptance
of `anycar-reference-line/1` remains pending; no new isolation or coding-agent score is claimed.

## Dashed centerline and traffic-cone observation revision

Worker commit `04ed39a5df64acacb67f8a03db1e6c6373c384f3` changes only the public
route overlay and cosmetic scenery. Both views show fixed spatial dashes and
tapered orange-and-white traffic cones with black bases. The visible cone geoms
have zero mass and disabled collision masks; the original collision cylinders
remain unchanged and invisible. No hidden state is used to draw the route.
Generated AnyCar packages explicitly declare `anycar-dashed-cones/1`.

The generated compact Silverstone i00 first held-out spot-check produces a
byte-identical physical record and noisy trajectory relative to the preceding
continuous-line run. A fresh process exactly reproduces physical state, metrics
and feedback. The 30-second CPU OSMesa/llvmpipe video decodes all 301 frames; all
31 delivered JPEGs and 301 noisy rows are retained. Finish time remains 28.0483 s
and the scripted-controller score remains 60.0126. All 133 previous local AnyCar
MP4 hashes are preserved. The largest legacy route, Valencia-1, renders 20807
scene geoms within its 25204-geom capacity, including 2700 dash segments.

Operator evidence is `anycar/integration-dashed-cones-v1`. Website exports include
the exact MP4, exact image payloads, noisy measurements, public specification and
nominal controller; private case banks and true-state records are excluded. This
is a local visual integration check, not an LLM evaluation, a full held-out bank
or new native Harbor acceptance. Earlier native scores predate this image revision.

Thirty-two focused physics, controller, circuit, packaging and runtime-budget
tests pass. Repository CI passes all 26 Control Transfer task contracts and 117
mutation checks. All 26 generated instance banks and nonvisual specifications
match the preceding revision. The optional global NumPy/requests tier remains
unavailable in system Python; affected numerical tests ran in pinned MuJoCo 3.5.

## Experimental vector wind (2026-10-14)

The new `neural-fly-vector-wind-v1` i00/i01 tasks declare `general-eight-wind/1` and
`vector-wind/1`, preserving earlier scalar-wind dispatch. The extension uses synthetic
isotropic air-relative drag; its heading and coefficient are not calibrated to
measured directional aerodynamics. Agent feedback remains the existing camera
frames and noisy trajectories. `wind.npz` and the wind-arrow renderer are private
operator artifacts; public-package, field-injection and HTTP-route tests enforce
that distinction at the tested interfaces.

Generated-package local checks: the frozen earlier scripted controller passes all
20 held-out cases, mean score 89.2110 (plants 90.0123 / 88.4098), with 20 exact
fresh-process record/state/wind replays. Four videos decode; 159 delivered JPEG
hashes and 1,576 noisy rows match. Both no-submission checks score zero without
infrastructure errors. A legacy scalar-wind whole record is unchanged, as are 83
previous recordings. Both isolated public nominal packages execute without trusted
imports. The operator demo uses 436 timestamp-matched samples from the saved private
wind trace; its arrows are not part of coding-agent feedback. Renderer: MuJoCo 3.5.0
and llvmpipe. Focused physics, packaging and privacy tests: 58 passed.

The bank driver's shell returned signal exit 143 after writing its completed receipt;
a separate artifact audit subsequently exited zero and verified every case pair,
source hash, private wind schedule, feedback artifact and prior recording. Do not
report the original shell as a clean exit. Local evidence is retained outside the
repository under `evidence/neuralfly/integration-vector-wind-v1/` in the orchestration
workspace. Native Harbor, multi-round adaptation and model evaluations of this
revision remain unperformed; both tasks retain `oracle=none` and require human review.
