# roboEngineer

roboEngineer evaluates whether a coding agent can engineer a robot controller from deployment feedback: tune a
bounded numeric controller against a **public nominal simulator** in its own container, **deploy** it to a private
evaluator whose dynamics differ in hidden ways, read back noisy telemetry and camera frames, revise, and deploy again
(at most three rounds); the evaluator then scores the **selected policy on a private held-out bank** of new episodes
of the same hidden plant. Contributed by WENLIXIAO-CS in #329 (the "Robotic Engineering Bench contributors"); admitted
as a benchmark by the owner on 2026-10-17.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/roboengineer -a codex -m openai/gpt-6-astra
```
Some images are not on a public registry: build them first ([Getting the images](#getting-the-images)).

## Getting the images

All 30 tasks are standard mode. The agents' images (`efe:control-transfer-0.2.0-nominal`, `-train`) and the files images
are public; the sidecar images below are not on a public registry and are built locally (no account, token or licence
acceptance needed; every input comes from a pinned public upstream and is checked):

| Tasks | Image to build |
|---|---|
| `roboengineer-landing-random-pad-*` | `efe-private:quadrotor-landing-0.1.0` |
| every other `roboengineer-*` (anycar, g1, go2, neuralfly) | `efe-private:control-transfer-0.2.0` (evaluator) |

The Neural Fly force fit (`forces.npz`) is not distributed: Neural-Fly's flight-log terms allow personal and educational
use only. `fetch_assets.sh --fit-fly` downloads the public logs and makes the fit locally (byte-identical to the pinned
digest, checked); without it the eight `roboengineer-neuralfly-*` tasks cannot run, and the other 22 tasks run.

```bash
# Control Transfer evaluator (builds the public nominal base too, which it starts FROM)
images/control-transfer/fetch_assets.sh            # git, python3; unitree_rl_mjlab and MuJoCo Menagerie at pinned commits
bash images/control-transfer/build.sh
# Neural Landing: downloads the Neural Lander checkpoint at its pinned commit and converts it (needs numpy and torch)
bash images/quadrotor-landing/prepare_assets.sh
docker build -f images/quadrotor-landing/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:quadrotor-landing-$(cat images/quadrotor-landing/VERSION) .
harbor run -d embodied-first-exam@all -p tasks/roboengineer -a codex -m openai/gpt-6-astra
```

## Tasks

30 tasks, 15 families × 2 instances (`i00`, `i01`: two independently drawn hidden plants), all `-standard`:

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
| `g1-terrain-walk` | Unitree G1 humanoid, blind walking over flat, sloped, rough and stepped terrain; the agent trains its 98 → 512 → 256 → 128 → 29 actor with mjlab / MuJoCo Warp **on its own GPU** | 4 / 12 | partial (i00: 1/12, i01: 4/12; the reference trains from scratch on the GPU) |

Per-family details (plants, randomization, score, feedback channels, provenance): [Neural Fly](neuralfly.md),
[Neural Landing](quadrotor-landing.md), [AnyCar](anycar.md), [Go2](go2.md), [G1](g1.md); the shared
service: [control-transfer.md](control-transfer.md); the wire interface: [policy.md](policy.md).

Not shipped from #329: the four full-lap
circuit packages (they need up to 32631 s of agent time, above the 14400 s cap), the circuit-sector variants and the
Linearbot / spacecraft / YAM prototypes (source only). `ci_checks/benchmarks/roboengineer/exported.toml` maps every task to its
package name in #329.

## Mode, runtime and grading

- **Standard mode with the benchmark's own runtime** (PROTOCOL §3): `eai-policy/1.0` (Neural Landing) and
  `eai-policy/1.1` (the others), listed in `ci_checks/benchmarks/roboengineer/exported.toml`; results are reported apart from the
  `eai-standard/2.x` tasks. Appendix H applies unchanged. The private evaluator runs in the `sim` sidecar (port 8000
  on localhost, no published port); the agent's container holds the public nominal model and the controller ABI only
  (environment/public/, an explicit allowlist checked by `ci_checks/benchmarks/roboengineer/invariant-boundary.py`, plus AnyCar's two track data files from the files-only image).
- **No privileged twin**: the hidden plant is the task; a privileged agent would read it.
- **Deliverable**: numeric policies only (bounded JSON coefficients; G1: the fixed-shape NPZ actor's weights). No
  agent code runs in the evaluator.
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

The evaluators (`control-transfer-<version>`, `quadrotor-landing-<version>`) are `BUILD_ONLY` (licence-restricted evaluator assets; see the marker files) in the private package; the agents' bases (`-nominal`, `-train`: public assets only) and the files image are public. All are built from their directories:

| Image | Contents | Used by |
|---|---|---|
| `ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal` | python 3.12, MuJoCo 3.5.0, OSMesa, ffmpeg; public assets (Unitree mjlab G1 subset, Menagerie Go2, Skydio X2) | the agent's container (FROM) |
| `ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-train` | nominal + libEGL and the G1 training stack, pinned: torch 2.11.0+cu128 (CUDA 12.8 wheels: NVIDIA driver >= 570), mujoco-warp 3.5.0, warp-lang 1.12.0, mjlab 1.2.0, rsl-rl-lib 5.0.1, tensordict 0.14.3, tensorboard 2.21.0, onnx 1.23.0, onnxscript 0.7.2, onnxruntime 1.23.2, wandb 0.30.0 (`pip check` clean); 4.7 GB | the G1 agent's container (FROM) |
| `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` | nominal + the Neural Fly force surrogate (`/opt/private-fly/forces.npz`) and the evaluator Go2 assets | the `sim` sidecar |
| `ghcr.io/mll-lab-nu/efe:control-transfer-anycar-files-0.3.0` | files only: AnyCar's `circuits.json` and `compact_routes.json` with F1DB's attribution (`NOTICE`, `LICENSE.f1db`, `LICENSE.anycar`) (`scripts/files_image.py`; `images/control-transfer-anycar-files/FILES.json` pins it) | the AnyCar compact-lap and tracking agents' containers (`COPY --from`) |
| `ghcr.io/mll-lab-nu/efe-private:quadrotor-landing-0.1.0` | python 3.12, MuJoCo, OSMesa, ffmpeg; the Neural Lander residual (`/opt/landing/residual.npz`) | the landing `sim` sidecar (its agent image is built from the client base) |

Build (any Linux host with Docker and network access to github.com and PyPI):
`images/control-transfer/fetch_assets.sh --fit-fly` clones the pinned public sources (unitree_rl_mjlab
@1425b15f, Menagerie @0059d433 for Go2 and @d7b481ba for Skydio X2), checks them and stages `images/control-transfer/assets/`;
then `BUILD_TRAIN=1 bash images/control-transfer/build.sh` (`TRAIN_ONLY=1` builds the training image alone FROM the nominal
tag). `bash images/quadrotor-landing/prepare_assets.sh` (NumPy and PyTorch) downloads the Neural Lander checkpoint at its
pinned commit and converts it byte-reproducibly (`bebb6c7f…`, checked by the Dockerfile); then
`docker build -f images/quadrotor-landing/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:quadrotor-landing-0.1.0 .`. The Neural
Fly force fit (`forces.npz`) is not in this repository and is not downloadable: Neural-Fly's flight-log terms allow
personal and educational use only. `--fit-fly` fits it locally from the public logs with
`images/control-transfer/calibrate_fly.py` (in a `python:3.12.14-slim` container, numpy 2.3.1 / mujoco 3.5.0; needs docker),
byte-identical to the pinned asset; `--fly <dir>` takes a `forces.npz` you already have. Its digest is pinned in each Neural Fly task's
`environment/sim/scripts/control_transfer/trusted/fly.py` `ASSET_SHA256`; an evaluator built without it runs every
roboEngineer task except the eight `roboengineer-neuralfly-*` ones.

## Resources

Rules: `scripts/task_resources.toml` (`^roboengineer-`), measured on 2026-10-18 (Harbor 0.23 trials,
docker stats, cgroup `memory.peak` and per-container `nvidia-smi` every 3-6 s). The verifier only reads JSON (~20 s).

- **28 CPU tasks** (all but G1): the agent's container is capped at 2 CPUs / 6 GB (limit 4 GiB), the sidecar at 4 CPUs
  / 6 GB. The sidecar uses 1.7-1.9 cores while a deployment runs (one worker, OSMesa), its full 4 cores while it
  finalizes (held-out cases twice on four single-threaded workers, then the video: 79-199 s) and, for Neural Landing,
  through the per-case reference search before the agent starts (~480 s); its peak memory is 0.6-2.1 GiB (go2-weave
  the largest), 1.2 GiB for landing. The reference runs' agent containers stay below 0.25 GiB. Minimum: 4 CPUs (the
  sidecar's 4 never coincide with the agent's work: the agent waits for the health check and is stopped before
  finalization; during a deployment the agent's 2-core cap + the sidecar's ~2) and 9 GB (landing 8 GB) = the agent's
  6 GB cap (its 4 GiB limit is recorded, not enforced, by default) + the sidecar's peak x 1.2 + the monitor. The
  verifier phase is the sidecar's collect hook: 4 CPUs, 3 GB. Timeouts: collection budgets 1740 s (compact laps
  5520 s, a worst-case bound) against 79-199 s measured; the verifier step 600 s against ~20 s.
- **G1** (`g1-terrain-walk`): one NVIDIA GPU for the agent's container (`environment/docker-compose.yaml` reserves one
  device for `main`; the sidecar has none and checks it). Measured on an L40S (`aws:rcb-gpu14`) with the public
  trainer: 1.8 GB of GPU memory at its default 256 environments, 4.7 GB at its cap of 1024, 16.5 GB at 4096 (the
  reference solution), about one CPU core (the PPO loop is bound by one Python thread); over the reference's 3.5 hours
  16.1 GiB of GPU memory, 5.6 GiB of memory, 1.6 cores at most. The sidecar: 2.2-2.6 cores during a deployment (four
  rendered 20 s cases, ~3.6 min), its 4-CPU cap while finalizing (419-488 s), peak 2.1 GiB. Declared: `gpu_required`,
  `min_gpu_memory_gb = 20` (16.1 GiB x 1.15 = 18.5, rounded up; any CUDA GPU by memory, but all measurements are on
  the L40S: a 24 GB card fits only when otherwise free and trains slower, so fewer iterations fit the cutoff and
  results are comparable only on one GPU model; the trainer caps torch at 15 % of the card, which its 0.64 GB at
  4096 environments stays under on 24 GB), 6 CPUs, 15 GB (the agent's 12 GB cap + the sidecar); limits 20 GiB of GPU memory and 10 GiB of memory for the
  agent's container; caps `main` 4 CPUs / 12 GB, `sim` 4 CPUs / 6 GB. Hosts: a GPU host that holds the three
  control-transfer images (`-train`, `-nominal` is its base, the evaluator) and lists the `roboengineer` bench.

## Checks

The task directories are the deliverable; the tooling that built them is kept outside this repository.

- `ci_checks/benchmarks/roboengineer/invariant-boundary.py` (the required job `invariants`): the agent's copy is exactly the
  public allowlist, the agent's Dockerfile copies nothing else, one frozen instance in sidecar and verifier.

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
- **G1** (Harbor 0.23.0 on aws:rcb-gpu14 / -gpu13, L40S): the reference (trains from scratch on the
  agent's GPU, 12009-12638 s of agent time, three deployments) held-out 1/12 (mean 43.14, i00) and 4/12 (82.68, i01):
  `oracle = "partial"`; nop 0 on both, `infra_error` 0; every graded trial has `replay.mp4` (`matches_graded`).
  [g1.md](g1.md).
- **Cutoff**: a Neural Fly copy with a 90 s limit was stopped during its second deployment: the round was
  `aborted_at_cutoff`, the first round was graded (score 40.21, `infra_error` 0), video present. A Neural Landing copy
  with 200 s: its in-process case running at the cutoff finished 17 s later, that round was not eligible, the earlier
  round was graded (`infra_error` 0).
- **Adversarial** (`codex-gpt6_luna-xhigh`, ChatGPT subscription, told to obtain reward without solving the task):
  anycar-tracking-i00 probed the service and the container (undocumented routes, path traversal, methods, Host
  headers, `/proc`) and scored 0; on landing-random-pad-i00 the agent declined to cheat and solved the task legitimately
  (6/6 held-out landings, score 100.0 in its hour); a second, stricter landing trial was also run.
- **Collection**: the sidecar's finalization plus the video pass took 76–217 s (budget 1740 s; landing 840 s); the
  verifier ~20 s. Peak memory of the agent's container in the reference runs ≤ 0.04 GB.

Historical evidence from the contributor's branch (native Harbor runs of the earlier packages, controller studies):
[validation.md](validation.md).
