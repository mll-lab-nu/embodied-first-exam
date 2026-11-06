# roboEngineer control transfer

> roboEngineer task names: [README.md](README.md) (the package names of #329 used on this page, `control-transfer-*` / `quadrotor-landing-*`, map to `roboengineer-*` in `ci_checks/benchmarks/roboengineer/exported.toml`).

The shared `eai-policy/1.1` service supports repeated nominal-training → deployment-feedback → revision rounds, followed by private held-out evaluation. See the [collection roadmap](README.md) for task readiness; implementation, successful control, native Harbor isolation and LLM evaluation are separate claims.

## Current families

| Family | Training | Agent feedback | Adaptation / held-out cases per instance |
|---|---|---|---|
| [Neural Fly — fixed and general figure eights](neuralfly.md) | Editable nominal CPU MuJoCo and numeric-controller fitting | Noisy pose/velocity/rate measurements, public timed trajectory, images | 5 / 10 |
| [AnyCar](anycar.md) | Editable nominal contact-wheel MuJoCo model and numeric-controller fitting | 18 noisy sensor/public-command channels and images | 3 / 10 |
| [AnyCar Drift to Park](anycar.md#drift-to-park-drift-park1) | Editable nominal RC model; numeric approach, drift and brake tuning | Public course, 14 noisy/own-action channels and all 161 video frames at 10 Hz | 3 / 10 |
| [Unitree G1 terrain](g1.md) | Blind-terrain PPO in mjlab/MuJoCo Warp; fixed numeric MLP export | 29 noisy joint angles, three public velocity commands and images | 4 / 12 |
| [Unitree Go2](go2.md) | Nominal MuJoCo tuning; bounded numeric controller | 37 noisy proprioceptive/public-command channels and images | 3 / 10 per objective |

The Go2 objectives are weave poles, attitude tracking, forward jump and yaw jump. This service runs 28 of roboEngineer's 30 tasks, 14 families × 2 instances: Neural Fly fixed eight, general eight, its Skydio X2 appearance variant and vector wind; AnyCar tracking, Drift to Park, tight-bay Drift to Park and the compact laps of Monaco and Silverstone; Go2 attitude, forward jump, yaw jump and weave; G1 terrain walk. The other two, Neural Landing (`landing-random-pad`), run on their own service (`eai-policy/1.0`, [quadrotor-landing.md](quadrotor-landing.md)).

## Frozen plant and rounds

Instance schema `control-transfer-instance/2` fixes one hidden plant across all adaptation and held-out cases. Each task has two independently randomized development instances. Episode initial conditions, commands, terrain/surface arrangements and sensor noise vary; those variations are distinct from persistent vehicle/actuator parameters. A bank that changes its plant within a same-plant instance is rejected. Source-visible development seeds must be replaced by operator-frozen undisclosed banks for official model comparisons.

The service allows three `deploy(policy, diagnosis)` calls. Rounds are charged before simulation, survive service restarts and cannot be reset. An interrupted adaptation round is an infrastructure failure. The operator cutoff persists across restarts. Interrupted held-out finalization archives partial evidence and replays the same frozen policy and bank; completed final evidence is never rerun. A completed round returns only its allowed feedback; deployment metrics and held-out feedback are withheld. `seal(round_id, summary)` irreversibly selects a completed round. Otherwise, the latest eligible completed round at cutoff is selected. No eligible submission yields zero reward.

Every held-out case runs in two fresh processes. Full physical-state hashes, numeric metrics and exact noisy observations must match. Binary success requires every held-out case to satisfy its physical task predicates; `final_reward` is the continuous mean engineering score. Infrastructure failures are distinct from bad control.

## Isolation and CPU evaluation

The agent container has editable public nominal code/assets and the client. Public source is copied from explicit file allowlists. Evaluator code, seed banks, force assets, reference fitting code and private policy locations are excluded. The evaluator is a separate container, with no agent-controlled executable code: submissions are finite, bounded JSON coefficients or fixed-shape numeric NPZ arrays. Python, pickle and agent-supplied ONNX graphs are not accepted for deployment.

Every official deployment and held-out rollout uses **native CPU MuJoCo 3.5.0, NumPy CPU inference and OSMesa software rendering**. GPU training is allowed. The simulator service requests no GPU devices, hides CUDA and rejects exposed `/dev/nvidia*`, `/dev/dri/*` or `/dev/kfd` devices. Runtime receipts record actual MuJoCo and OpenGL information; official verification fails if CPU isolation/software-renderer evidence is missing or inconsistent. Local tests on a GPU host explicitly do not prove device isolation.

Only `describe`, `deploy`, `seal` and `result` (a completed round's stored response) are public operations. There is no evaluator filesystem, reset, state or grading API. An operator-only collect hook finalizes and transfers evidence after the agent finishes. The independent verifier runs without network and uses simulator-collected evidence, not agent-written grades. Its Dockerfile checks the frozen instance's digest at build time; tasks are built from content-stamped trees (`scripts/stamp_mtimes.py`). The runtime verifier independently checks the simulator instance digest. Operator-only diagnostics retain the exact input hashes and rejection stage.

## Inspectable records

Each round retains the submitted policy bytes/hash, short observable diagnosis, exact delivered JSON/image bytes, noisy telemetry and full operator MP4s. The client also preserves failed request/response bytes and distinct request indices. These are concise diagnoses and predictions, not private chain of thought. Receipt of an image proves delivery, not that an LLM inspected it. Training code, stdout, configurations, policy exports and checkpoints belong under `/app/output/`; Harbor retains the agent transcript.

Private records include realized parameters, true state, contacts, task metrics, replay hashes and runtime proofs. They never enter adaptation feedback. Held-out videos are available to the operator after submission, not to the coding agent during improvement.

## Reproduction and status

Images: `images/control-transfer/fetch_assets.sh` stages the build inputs from pinned public sources, then
`images/control-transfer/build.sh` builds the `nominal`, `train` and `evaluator` targets (`tasks/roboengineer/README.md`).
Only the evaluator target contains the flight-force artifact (`--fly`, not distributed) and the full prepared Go2
integrity directory; nominal/train stages contain only nominal robot assets.

The task directories are the deliverable; the tooling that built them is kept outside this repository.

```bash
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/roboengineer/roboengineer-anycar-tracking-i00-standard -a oracle -e docker
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/roboengineer/roboengineer-anycar-tracking-i00-standard -a nop -e docker
```

The supplied reference controllers are scripted engineering baselines, not LLM scores. `[metadata] oracle` per task (the reference's held-out results: [README.md](README.md) "Tasks" and "Validation"): `full` for Neural Fly fixed eight and vector wind, AnyCar tracking, the four compact laps, Go2 attitude, and the i00 instances of Neural Fly general eight and its Skydio variant; `partial` (human review) for the i01 instances of those two, tight-bay Drift to Park i01 and both G1 instances; `none` for Drift to Park, tight-bay Drift to Park i00, and Go2 forward jump, yaw jump and weave (no positive example yet). See the [integration validation record](validation.md). Family documents identify source pins, model assumptions, exact score semantics, training initialization and reference failures. Neural Fly uses a heavily clipped flight-data quadratic surrogate rather than the paper's DAIML controller or a calibrated digital twin; AnyCar uses rigid Coulomb contacts rather than deformable soil; G1 and Go2 results are simulation transfer, not hardware tests.

### Optional appearance revision: Skydio X2

`control-transfer-neural-fly-general-skydio-v1-i{00,01}-standard` uses the same
`general-eight/1` plants, cases, commands, numeric ABI and scoring as the existing
general-eight task. Its distinct `neuralfly-skydio/1` observation revision uses
pinned public Skydio meshes in a separate render-only model at 960×720 and 10 fps.
It is not calibrated Skydio physics. Both nominal and deployment environments
explicitly select the profile. The reference scores as on general eight (i00 `full`, i01 `partial`). Asset staging and license
checks are described in the [image guide](../../images/control-transfer/README.md).

Compact 30-second laps use `anycar-circuit-compact-v3-<layout>` / `circuit-compact-lap/3`,
with a separately versioned `compact-30s/1` route. The tasks cover both plants
for Silverstone and Monaco. These public 45 m routes target a 28 s lap within a hard 30 s episode. They are
F1-inspired approximations with recorded smoothing and aspect widening; sharp turns and
crossovers may be removed. The car physics and controller ABI are unchanged. Compact tasks
use the ordinary 14400-second agent cutoff, with all 301 noisy samples and 31 images spanning
0–30 s per deployment.

Drift to Park is a ninth core objective, registered as `control-transfer-anycar-drift-i{00,01}-standard`. It has a 16 s horizon, three adaptation rounds, public course commands and a bounded three-action controller with a physical rear-wheel handbrake. The nominal example succeeds, but the frozen controller fails all 26 randomized development/held-out cases: `oracle = "none"`. This control gap is distinct from package, replay and isolation validation.

The separate tight-bay revision is `control-transfer-anycar-drift-v3-i{00,01}-standard`: a 180-degree drifting turn, 0.69 × 0.43 m nominal bay and 1 m approach. Its observation-driven ABI /3 controller has one nominal positive at 64.70; in the Harbor reference trials it succeeded on 0/10 held-out cases of i00 (`oracle = "none"`) and 1/10 of i01 (`oracle = "partial"`). It also accepts ABI /2.

Native Harbor 0.23.0 validation on CPU Docker completed the reference driver and no-op trial for each Drift instance. Both reference trials evaluated ten held-out episodes with deterministic replay; all four trials reported zero infrastructure errors, enforced resource limits and no observed violations. The reference scores remain zero. This checks the packaged lifecycle and independent verifier, not controller solvability or coding-agent performance.
