# roboEngineer

roboEngineer evaluates whether a coding agent can engineer a robot controller from deployment feedback: tune a
bounded numeric controller against a **public nominal simulator** in its own container, **deploy** it to a private
evaluator whose dynamics differ in hidden ways, read back noisy telemetry and camera frames, revise, and deploy again
(at most three rounds); the evaluator then scores the **selected policy on a private held-out bank** of new episodes
of the same hidden plant. Contributed by WENLIXIAO-CS in #329 (the "Robotic Engineering Bench contributors"); admitted
as a benchmark by the owner on 2026-10-17 (board 0146).

## Tasks

28 tasks, 14 families × 2 instances (`i00`, `i01`: two independently drawn hidden plants), all `-standard`:

| Family (`roboengineer-<family>-iNN-standard`) | Robot / objective | Adaptation / held-out cases | Oracle |
|---|---|---|---|
| `landing-random-pad` | Intel Aero (partial calibration) with the Neural Lander learned ground-effect residual: land on a randomly placed pad | 3 / 6 | full |
| `neuralfly-eight` | Neural Fly airframe with a flight-log force surrogate and wind: track a timed vertical figure eight | 5 / 10 | full |
| `neuralfly-general` | the same, randomized horizontal / vertical / inclined figure eights, both directions | 5 / 10 | full (i00), partial (i01: 8/10) |
| `neuralfly-general-skydio` | the same with Skydio X2 camera appearance (960 × 720) | 5 / 10 | full (i00), partial (i01: 8/10) |
| `neuralfly-vector-wind` | general eights in an explicit horizontal air-velocity field with isotropic drag | 5 / 10 | full |
| `anycar-tracking` | AnyCar racing car: track a reference across surfaces of different friction | 3 / 10 | full |
| `anycar-drift-park` | U-bend, a measured sideways slide, stop between two parked cars | 3 / 10 | none (no positive example yet) |
| `anycar-tight-drift-park` | a 180° drifting turn into a tight bay | 3 / 10 | none (i00), partial (i01: 1/10) |
| `anycar-compact-lap-monaco-6`, `anycar-compact-lap-silverstone-8` | a 45 m smoothed F1-inspired loop within 30 s (target 28 s), every gate in order | 3 / 10 | full |
| `go2-attitude` | Unitree Go2: track commanded body roll / pitch | 3 / 10 | full |
| `go2-forward-jump`, `go2-yaw-jump` | jump forward / with a heading change and land stably | 3 / 10 | none (no positive example yet) |
| `go2-weave` | weave between poles | 3 / 10 | none (no positive example yet) |

Per-family details (plants, randomization, score, feedback channels, provenance): [Neural Fly](roboengineer-neuralfly.md),
[Neural Landing](quadrotor-landing.md), [AnyCar](roboengineer-anycar.md), [Go2](roboengineer-go2.md); the shared
service: [control-transfer.md](control-transfer.md); the wire interface: [roboengineer-policy.md](roboengineer-policy.md).

Not shipped from #329: the G1 terrain family (GPU training image and solvability not validated), the four full-lap
circuit packages (they need up to 32631 s of agent time, above the 14400 s cap), the circuit-sector variants and the
Linearbot / spacecraft / YAM prototypes (source only). `scripts/roboengineer/exported.toml` maps every task to its
package name in #329.

## Mode, runtime and grading

- **Standard mode with the benchmark's own runtime** (PROTOCOL §3): `eai-policy/1.0` (Neural Landing) and
  `eai-policy/1.1` (the others), listed in `scripts/roboengineer/exported.toml`; results are reported apart from the
  `eai-standard/2.x` tasks. Appendix H applies unchanged. The private evaluator runs in the `sim` sidecar (port 8000
  on localhost, no published port); the agent's container holds the public nominal model and the controller ABI only
  (environment/public/, an explicit allowlist checked by `scripts/roboengineer/ci/invariant-boundary.py`).
- **No privileged twin**: the hidden plant is the task; a privileged agent would read it.
- **Deliverable**: numeric policies only (bounded JSON coefficients; the G1 family's fixed-shape NPZ actor is not
  shipped). No agent code runs in the evaluator.
- **Verdict** (H.4): when the agent's time is up the collect hooks run `kill -9 -1` in the agent's container, then
  signal the sidecar: from that signal on it refuses every request (a deployment still running is stopped, Control
  Transfer, or finishes ungraded, Neural Landing), takes the round the agent sealed or else the latest round completed before the cutoff, and evaluates
  that policy on every held-out case in two fresh processes (state hashes, metrics and noisy observations must match),
  without rendering. It writes `final.json` (`success`: every held-out case succeeded; `graded_by: live`); the
  verifier (no network) checks the record's digests and transcribes it: `reward.txt` 1 or 0, `reward.json` with
  `success`, `live_success`, `graded_by_live = 1`, `replays = 0`, `infra_error`, `final_reward` (mean 0–100 engineering
  score), `progress`, `success_rate`, `episodes`.
- **Video** (§4): after the verdict the sidecar renders the held-out evaluation once more (OSMesa) and joins the cases
  into `/data/replay.mp4` (collected as `artifacts/data/replay.mp4`); `video.json` says whether the rendered run's
  state hashes match the graded ones. Every adaptation round also keeps its per-case videos (`round-N/case-K/`). A trial
  without any completed deployment has no episode and no video.
- **Infrastructure vs the agent's failure** (H.5): `infra_error = 1` only when the evaluator itself fails (a missing or
  mismatched asset or instance, a worker crash, a replay mismatch, a missing `final.json`). A policy that crashes the
  vehicle or makes the simulation diverge (non-finite state, a MuJoCo bad-state reset) fails its episode (score 0); an
  invalid policy is rejected before it costs a round; no eligible round scores 0 with `infra_error = 0`.
- **Seeds**: one frozen instance per task (`default = allowed = [instance index]`); the case banks are private
  (instance.json in the sidecar and the verifier only). The Neural Landing banks are independent random 62-bit seeds
  (#329 review: the earlier sequential seeds could be recovered from the pad positions through the public sampler).
- **Cutoff**: 3600 s (Neural Landing), 14400 s (the others), the author's choice. The service's own deadline counts the
  same limit from the agent's first request. Neural Landing freezes its per-case reference search before the agent
  starts (the sidecar's health check gates the agent; this time is not the agent's).

## Images

Both are `BUILD_ONLY` (licence-restricted evaluator assets; see the marker files), built from their directories:

| Image | Contents | Used by |
|---|---|---|
| `ghcr.io/mll-lab-nu/eai-control-transfer:0.2.0-nominal` | python 3.12, MuJoCo 3.5.0, OSMesa, ffmpeg; public assets (Unitree mjlab G1 subset, Menagerie Go2, Skydio X2) | the agent's container (FROM) |
| `ghcr.io/mll-lab-nu/eai-control-transfer:0.2.0` | nominal + the Neural Fly force surrogate (`/opt/private-fly/forces.npz`) and the evaluator Go2 assets | the `sim` sidecar |
| `ghcr.io/mll-lab-nu/eai-quadrotor-landing:0.1.0` | python 3.12, MuJoCo, OSMesa, ffmpeg; the Neural Lander residual (`/opt/landing/residual.npz`) | the landing `sim` sidecar (its agent image is built from the client base) |

Build (any Linux host with Docker and network access to github.com and PyPI): run the preparation in a
`python:3.12` container (numpy 2.3.1, mujoco 3.5.0, scipy 1.17.0, CPU torch for the landing checkpoint conversion):
`python -m scripts.control_transfer.prepare_assets --workspace <ws with sim2realbench/vendor/unitree_rl_mjlab @1425b15f>
--go2-source <menagerie @0059d433> --out <nominal> --private-go2-out <go2>`, `python -m scripts.control_transfer.neuralfly_visual --out <skydio>`,
`python -m scripts.control_transfer.calibrate_fly --source <aerorobotics/neural-fly @0ed50246> --out <fly>`,
`python images/control-transfer/prepare_assets.py --assets <nominal> --fly <fly> --go2 <go2> --skydio <skydio>`,
`bash images/quadrotor-landing/prepare_assets.sh`; then `bash images/control-transfer/build.sh` and
`docker build -f images/quadrotor-landing/Dockerfile -t ghcr.io/mll-lab-nu/eai-quadrotor-landing:0.1.0 .`. The force
fit reproduces the documented validation RMSE (0.8749 / 0.5893 / 1.6956 N); its digest is pinned in
`scripts/control_transfer/gen_tasks.py` `FLY_ASSET_SHA256` (= `trusted/fly.py` `ASSET_SHA256`); the landing residual
conversion is byte-reproducible (`bebb6c7f…`).

## Resources

CPU only. Per trial: the agent's container is capped at 2 CPUs / 6 GB (limit 4 GiB), the sidecar at 4 CPUs / 6 GB;
the held-out evaluation runs four single-threaded workers. The verifier only reads JSON. Rules:
`scripts/task_resources.toml` (`^roboengineer-`).

## Generators and checks

- `python3 -m scripts.quadrotor_landing.gen_tasks render|check`, `python3 -m scripts.control_transfer.gen_tasks
  render|check` (standard library only; both end with `scripts/task_conventions.py` normalize; CI:
  `ci_checks/check-generated-tasks.sh`).
- `scripts/roboengineer/ci/invariant-boundary.py` (the required job `invariants`): the agent's copy is exactly the
  generators' public allowlist, the agent's Dockerfile copies nothing else, one frozen instance in sidecar and verifier.
- Unit tests: the standard-library ones run in CI (`ci_checks/check-unit-tests.sh`); the service, rollout and
  packaging tests need MuJoCo and the assets: run them in the images,
  `docker run --rm -v $PWD:/r -w /r -e MUJOCO_GL=osmesa ghcr.io/mll-lab-nu/eai-control-transfer:0.2.0 python -m unittest discover -s scripts/control_transfer/tests -p 'test_*.py'`
  and the same with `eai-quadrotor-landing:0.1.0`, `-e LANDING_TEST_RESIDUAL=/opt/landing/residual.npz` and
  `scripts/quadrotor_landing/tests` (2026-10-18: 154 + 28 pass, one full-lap test skipped).

## Validation (2026-10-18, Harbor 0.23.0 on aws:rcb-cpu3, the images above)

- **Reference controllers** (`solution/`, Harbor's oracle agent), held-out cases succeeded / mean score per instance
  `i00`, `i01`: landing 6/6 84.11, 6/6 82.89; neuralfly-eight 10/10 90.32, 10/10 94.30 (the contributor's records:
  90.3151, 94.2980); neuralfly-general and -skydio 10/10 87.58, 8/10 71.61; neuralfly-vector-wind 10/10 90.01, 10/10
  88.41; anycar-tracking 10/10 73.21, 10/10 72.87; the four compact laps 10/10 (76.2–77.1); go2-attitude 10/10 91.06,
  10/10 91.24; anycar-drift-park 0/10, 0/10; anycar-tight-drift-park 0/10, 1/10; go2-forward-jump, go2-yaw-jump,
  go2-weave 0/10 on both (no positive example yet). `[metadata] oracle` follows: full where the reference succeeds,
  partial where it succeeds on some cases, none otherwise. A second run of four of them reproduced the same scores
  (determinism across fresh trials).
- **nop** on all 28: reward 0, `infra_error` 0 (no deployment: `no_submission`; no episode, so no video).
- **Cutoff**: a Neural Fly copy with a 90 s limit was stopped during its second deployment: the round was
  `aborted_at_cutoff`, the first round was graded (score 40.21, `infra_error` 0), video present. A Neural Landing copy
  with 200 s: its in-process case running at the cutoff finished 17 s later, that round was not eligible, the earlier
  round was graded (`infra_error` 0).
- **Adversarial** (`codex-gpt6_luna-xhigh`, ChatGPT subscription, told to obtain reward without solving the task):
  anycar-tracking-i00 probed the service and the container (undocumented routes, path traversal, methods, Host
  headers, `/proc`) and scored 0; on landing-random-pad-i00 the agent declined to cheat and solved the task legitimately
  (6/6 held-out landings, score 100.0 in its hour); a second, stricter landing trial: see board 0146.
- **Collection**: the sidecar's finalization plus the video pass took 76–217 s (budget 1740 s; landing 840 s); the
  verifier ~20 s. Peak memory of the agent's container in the reference runs ≤ 0.04 GB.

Historical evidence from the contributor's branch (native Harbor runs of the earlier packages, controller studies):
[roboengineer-validation.md](roboengineer-validation.md).
