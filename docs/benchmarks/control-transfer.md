# roboEngineer control transfer

The shared `eai-policy/1.1` service supports repeated nominal-training → deployment-feedback → revision rounds, followed by private held-out evaluation. See the [collection roadmap](roboengineer.md) for task readiness; implementation, successful control, native Harbor isolation and LLM evaluation are separate claims.

## Current families

| Family | Training | Agent feedback | Adaptation / held-out cases per instance |
|---|---|---|---|
| [Neural Fly — fixed and general figure eights](roboengineer-neuralfly.md) | Editable nominal CPU MuJoCo and numeric-controller fitting | Noisy pose/velocity/rate measurements, public timed trajectory, images | 5 / 10 |
| [AnyCar](roboengineer-anycar.md) | Editable nominal contact-wheel MuJoCo model and numeric-controller fitting | 18 noisy sensor/public-command channels and images | 3 / 10 |
| [Unitree G1 terrain](roboengineer-g1.md) | Blind-terrain PPO in mjlab/MuJoCo Warp; fixed numeric MLP export | 29 noisy joint angles, three public velocity commands and images | 4 / 12 |
| [Unitree Go2](roboengineer-go2.md) | Nominal MuJoCo tuning; bounded numeric controller | 37 noisy proprioceptive/public-command channels and images | 3 / 10 per objective |

The Go2 objectives are weave poles, attitude tracking, forward jump and yaw jump. Some reference controllers remain unsuccessful; those objectives are development tasks, not admission-ready benchmarks. The generator produces two instances of each of eight variants (16 tasks), including separate fixed-eight and general-eight Neural Fly tasks. Neural Landing has its own generator and validated service; this service does not replace it.

Earlier imported Linearbot, spacecraft and YAM modules remain prototype source. They are not generated members of the original eight-objective collection. Their old twelve-instance release must not be confused with the current task bank.

## Frozen plant and rounds

Instance schema `control-transfer-instance/2` fixes one hidden plant across all adaptation and held-out cases. Each task has two independently randomized development instances. Episode initial conditions, commands, terrain/surface arrangements and sensor noise vary; those variations are distinct from persistent vehicle/actuator parameters. A bank that changes its plant within a same-plant instance is rejected. Source-visible development seeds must be replaced by operator-frozen undisclosed banks for official model comparisons.

The service allows three `deploy(policy, diagnosis)` calls. Rounds are charged before simulation, survive service restarts and cannot be reset. An interrupted adaptation round is an infrastructure failure. The operator cutoff persists across restarts. Interrupted held-out finalization archives partial evidence and replays the same frozen policy and bank; completed final evidence is never rerun. A completed round returns only its allowed feedback; deployment metrics and held-out feedback are withheld. `seal(round_id, summary)` irreversibly selects a completed round. Otherwise, the latest eligible completed round at cutoff is selected. No eligible submission yields zero reward.

Every held-out case runs in two fresh processes. Full physical-state hashes, numeric metrics and exact noisy observations must match. Binary success requires every held-out case to satisfy its physical task predicates; `final_reward` is the continuous mean engineering score. Infrastructure failures are distinct from bad control.

## Isolation and CPU evaluation

The agent container has editable public nominal code/assets and the client. Public source is copied from explicit file allowlists. Evaluator code, seed banks, force assets, reference fitting code and private policy locations are excluded. The evaluator is a separate container, with no agent-controlled executable code: submissions are finite, bounded JSON coefficients or fixed-shape numeric NPZ arrays. Python, pickle and agent-supplied ONNX graphs are not accepted for deployment.

Every official deployment and held-out rollout uses **native CPU MuJoCo 3.5.0, NumPy CPU inference and OSMesa software rendering**. GPU training is allowed. The simulator service requests no GPU devices, hides CUDA and rejects exposed `/dev/nvidia*`, `/dev/dri/*` or `/dev/kfd` devices. Runtime receipts record actual MuJoCo and OpenGL information; official verification fails if CPU isolation/software-renderer evidence is missing or inconsistent. Local tests on a GPU host explicitly do not prove device isolation.

Only `describe`, `deploy` and `seal` are public operations. There is no evaluator filesystem, reset, state or grading API. An operator-only collect hook finalizes and transfers evidence after the agent finishes. The independent verifier runs without network and uses simulator-collected evidence, not agent-written grades. Its Dockerfile includes deterministic hashes of the frozen instance and all copied verifier inputs before any COPY, and checks every copied file at build time. This prevents reuse of a stale same-size instance file in the staged Docker build cache; the runtime verifier independently checks the simulator instance digest. Operator-only diagnostics retain the exact input hashes and rejection stage.

## Inspectable records

Each round retains the submitted policy bytes/hash, short observable diagnosis, exact delivered JSON/image bytes, noisy telemetry and full operator MP4s. The client also preserves failed request/response bytes and distinct request indices. These are concise diagnoses and predictions, not private chain of thought. Receipt of an image proves delivery, not that an LLM inspected it. Training code, stdout, configurations, policy exports and checkpoints belong under `/app/output/`; Harbor retains the agent transcript.

Private records include realized parameters, true state, contacts, task metrics, replay hashes and runtime proofs. They never enter adaptation feedback. Held-out videos are available to the operator after submission, not to the coding agent during improvement.

## Reproduction and status

Prepare nominal robot assets with `python -m scripts.control_transfer.prepare_assets --workspace /path/to/workspace --go2-source /path/to/pinned-menagerie --out /operator/assets --private-go2-out /operator/private-go2`; this requires the pinned Unitree checkout and excludes reference policies and unrelated robot archives. Stage them with `python images/control-transfer/prepare_assets.py --assets /operator/assets --fly /operator/fly-calibration --go2 /operator/private-go2`, then build the `nominal`, `train` and `evaluator` targets with `images/control-transfer/build.sh`. Only the evaluator target contains the flight-force artifact and the full prepared Go2 integrity directory; nominal/train stages contain only nominal robot assets. Images are `BUILD_ONLY`; neither restricted flight-derived assets nor user-provided robot archives are published by these scripts.

```bash
python -m scripts.control_transfer.gen_tasks render
python -S -m scripts.control_transfer.gen_tasks check
# Refresh task digests from tasks/ with: harbor add --scan .
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/control-transfer-anycar-i00-standard -a oracle -e docker
RCB_LIMITS_ENFORCE=1 harbor run -p tasks/control-transfer-anycar-i00-standard -a nop -e docker
```

The supplied reference candidates are scripted engineering baselines, not LLM scores. Fixed-eight Neural Fly, ellipse AnyCar and Go2 attitude declare full scripted references after both native instance banks and no-submission controls passed. General-eight Neural Fly, G1 and the other Go2 objectives remain `oracle=none` and require human review. See the [integration validation record](roboengineer-validation.md). Family documents identify source pins, model assumptions, exact score semantics, training initialization and reference failures. Neural Fly uses a heavily clipped flight-data quadratic surrogate rather than the paper's DAIML controller or a calibrated digital twin; AnyCar uses rigid Coulomb contacts rather than deformable soil; G1 and Go2 results are simulation transfer, not hardware tests.
