# roboEngineer

## Overview

roboEngineer tests whether a coding agent can engineer a robot controller from deployment feedback. The agent tunes a
bounded numeric controller against a **public nominal simulator** in its own container. It then **deploys** the
controller to a private evaluator whose dynamics differ in hidden ways, reads back noisy telemetry and camera frames,
revises, and deploys again (at most three rounds). The evaluator then scores the **selected policy on a private held-out
bank** of new episodes of the same hidden plant.

All 30 tasks are standard mode: 15 families × 2 instances (`i00`, `i01`: two independently drawn hidden plants). There
is no privileged mode: the hidden plant is the task, and a privileged agent would read it.

```bash
harbor run -d embodied-first-exam@all -p tasks/roboengineer -a <agent> -m <model>
```
Some images are not on a public registry: build them first (Getting the images, below).

### Getting the images

The agents' images (`efe:control-transfer-0.2.0-nominal`, `-train`) and the files image are public. The sidecar images
below are not on a public registry and are built locally. No account, token or licence acceptance is needed; every
input comes from a pinned public upstream and is checked.

| Tasks | Image to build |
|---|---|
| `roboengineer-landing-random-pad-*` | `efe-private:quadrotor-landing-0.1.0` |
| every other `roboengineer-*` (anycar, g1, go2, neuralfly) | `efe-private:control-transfer-0.2.0` (evaluator) |

The Neural Fly force fit (`forces.npz`) is not distributed: Neural-Fly's flight-log terms allow personal and educational
use only. `fetch_assets.sh --fit-fly` downloads the public logs and makes the fit locally (byte-identical to the pinned
digest, checked). Without it the eight `roboengineer-neuralfly-*` tasks cannot run; the other 22 tasks run.

```bash
# Control Transfer evaluator (builds the public nominal base too, which it starts FROM)
images/control-transfer/fetch_assets.sh            # git, python3; unitree_rl_mjlab and MuJoCo Menagerie at pinned commits
bash images/control-transfer/build.sh
# Neural Landing: downloads the Neural Lander checkpoint at its pinned commit and converts it (needs numpy and torch)
bash images/quadrotor-landing/prepare_assets.sh
docker build -f images/quadrotor-landing/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:quadrotor-landing-$(cat images/quadrotor-landing/VERSION) .
```

| Image | Contents | Used by |
|---|---|---|
| `ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-nominal` | python 3.12, MuJoCo 3.5.0, OSMesa, ffmpeg; public assets (Unitree mjlab G1 subset, Menagerie Go2, Skydio X2) | the agent's container (FROM) |
| `ghcr.io/mll-lab-nu/efe:control-transfer-0.2.0-train` | nominal + libEGL and the G1 training stack, pinned: torch 2.11.0+cu128 (CUDA 12.8 wheels: NVIDIA driver >= 570), mujoco-warp 3.5.0, warp-lang 1.12.0, mjlab 1.2.0, rsl-rl-lib 5.0.1; 4.7 GB | the G1 agent's container (FROM) |
| `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` | nominal + the Neural Fly force surrogate (`/opt/private-fly/forces.npz`) and the evaluator Go2 assets | the `sim` sidecar |
| `ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1` | files only (`images/roboengineer-files/FILES.json`): the public client code and graders under `standard/`, the sidecars' shared service files, and AnyCar's `circuits.json` and `compact_routes.json` with F1DB's attribution | the agents' and verifiers' containers and the `sim` sidecars (`COPY --from`) |
| `ghcr.io/mll-lab-nu/efe-private:quadrotor-landing-0.1.0` | python 3.12, MuJoCo, OSMesa, ffmpeg; the Neural Lander residual (`/opt/landing/residual.npz`) | the landing `sim` sidecar |

`BUILD_TRAIN=1 bash images/control-transfer/build.sh` also builds the training image (`TRAIN_ONLY=1` builds it alone
FROM the nominal tag). The Neural Fly fit's digest is pinned in each Neural Fly task's
`environment/sim/scripts/control_transfer/trusted/fly.py` `ASSET_SHA256`.

## Upstream and license

roboEngineer is an original suite of Embodied First Exam. Its plants and assets come from pinned public sources:

| Family | Source | Licence |
|---|---|---|
| Neural Fly (`neuralfly-*`) | [aerorobotics/neural-fly](https://github.com/aerorobotics/neural-fly) @ `0ed50246`: figure-eight reference, airframe mass and thrust, flight logs for the force fit | the logs are **for personal and educational use only**; written permission from the authors is needed for further use. The fit is made locally and never distributed. Skydio X2 visual model: MuJoCo Menagerie @ `d7b481ba`, Apache License 2.0 |
| Neural Landing (`landing-random-pad`) | [GuanyaShi/neural_lander_sim_1d](https://github.com/GuanyaShi/neural_lander_sim_1d) @ `30ab04cb`: Intel Aero calibration and the Neural Lander checkpoint, converted to NumPy (SHA-256 `bebb6c7f…`) | the repository states no licence |
| AnyCar (`anycar-*`) | [LeCAR-Lab/anycar](https://github.com/LeCAR-Lab/anycar) @ `20fc50a6`: wheel, suspension, steering and actuator mechanism; circuit outlines from [f1db/f1db](https://github.com/f1db/f1db) @ `7cf634e8` | AnyCar: Apache License 2.0 (declared in its README; `anycarbench/LICENSE.anycar`, `NOTICE`); F1DB: CC BY 4.0 (`LICENSE.f1db`) |
| Go2 (`go2-*`) | MuJoCo Menagerie @ `0059d433`, `unitree_go2` | BSD 3-Clause (Unitree Robotics) |
| G1 (`g1-terrain-walk`) | [unitreerobotics/unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab) @ `1425b15f`: robot model, actuator interface, base PPO task | Apache License 2.0 |

The simulator is MuJoCo 3.5.0 (Apache License 2.0). Per-family provenance and model assumptions:
[neuralfly.md](neuralfly.md), [quadrotor-landing.md](quadrotor-landing.md), [anycar.md](anycar.md), [go2.md](go2.md),
[g1.md](g1.md).

## Changes from upstream

- **Simulation ports, not reproductions.** Every family is a MuJoCo CPU simulation built for this suite. Neural Fly uses
  an 18-feature quadratic ridge fit to the baseline flight logs (each force axis clipped to ±12 N), not the paper's
  DAIML controller; the airframe is approximated as a symmetric X quadrotor. The fit includes strong-wind logs, so the
  paper's unseen-wind experiment is not replicated, and there is no excluded warm-up lap. Neural Landing uses a
  partial Intel Aero calibration with the learned ground-effect residual. AnyCar keeps the car mechanism but replaces
  the omitted meshes with a procedural chassis and adds new tracks, rigid Coulomb contacts, surface layouts and
  barriers. The compact laps are 45 m loops shaped after F1 circuits (smoothed and widened), not scaled outlines. Go2
  and G1 are simulated quadruped and humanoid tasks, not hardware calibrations.
- **Hidden plants.** Each instance fixes one hidden plant (mass, inertia, motor and steering gains, delays, friction,
  sensor bias) for its adaptation and held-out cases. Commands, initial conditions, terrain or surfaces and sensor
  noise vary per case.
- **Success predicates.** The binary success of every family is defined by this suite (Grading). Upstream defines none
  for these settings.
- **Not included:** four full-lap circuit packages (they need up to 32631 s of agent time, above the 14400 s cap), the
  circuit-sector variants, and the Linearbot, spacecraft and YAM prototypes.

## Interface

- **Its own runtime.** roboEngineer keeps its own multi-round runtime, not the `eai-standard/3.0` robot service: there is no
  live robot to call and no MCP tools. Its protocols are listed in `ci_checks/benchmarks/roboengineer/exported.toml`;
  results are reported apart from the other standard-mode tasks. The wire interface is in [policy.md](policy.md).
- **The agent's container** holds the public nominal model, the training helpers and the client only
  (`environment/public/`, an explicit allowlist checked by `ci_checks/benchmarks/roboengineer/invariant-boundary.py`).
  The private evaluator runs in the `sim` sidecar (port 8000 on localhost, no published port).
- **Operations.** `describe()` (public defaults, bounds, rounds left), `deploy(policy, diagnosis)` (one round on the
  fixed development cases; returns noisy telemetry and camera frames), `result(round_id)` (a completed round's stored
  response again; Control Transfer only) and `seal(round_id, summary)` (selects a round and ends adaptation). There is
  no reset and no state or grading endpoint; every other path is 404.
- **Deliverable.** Numeric policies only: bounded JSON coefficients, and for G1 the fixed-shape NPZ actor's weights. No
  agent code runs in the evaluator.
- **Time.** 3600 s for Neural Landing, 14400 s for the others. The service's own deadline counts the same limit from the
  agent's first request. Neural Landing freezes its per-case reference search before the agent starts.
- **Seeds.** One frozen instance per task (`default = allowed = [instance index]`). The case banks are private: they
  are in `instance.json` in the sidecar and the verifier only. The Neural Landing banks are independent random 62-bit
  seeds.

## Grading

- **Selection.** When the agent's time is up, the collect hooks run `kill -9 -1` in the agent's container and then
  signal the sidecar. From that signal on the sidecar refuses every request. A deployment still running is stopped
  (Control Transfer) or finishes ungraded (Neural Landing). The sidecar takes the round the agent sealed, or else the
  latest round completed before the cutoff. With no completed round the score is 0.
- **Held-out evaluation.** The selected policy runs on every held-out case in two fresh processes, without rendering.
  State hashes, metrics and noisy observations must match. `final.json` has `success` = every held-out case succeeded,
  and `graded_by = "live"`.
- **Per-case predicates** (each task's README states its family's exactly): Go2 (`simulation.py` `score()`), AnyCar
  tracking and compact laps (`trusted/anycar.py` `score_trajectory()`), Drift to Park (`trusted/anycar_drift.py`,
  `anycar_drift_v3.py` `Monitor`), Neural Fly (`trusted/fly.py` `rollout()`), Neural Landing
  (`quadrotor_landing/trusted/simulation.py`, `scoring.py`), G1 (`components/sim2realbench/g1/deploy.py`). Each case
  also has a 0-100 engineering score; its mean is `final_reward` and does not decide success.
- **Verifier.** It runs without network, checks the record's digests and transcribes it: `reward.txt` 1 or 0, and
  `reward.json` with `success`, `live_success`, `graded_by_live = 1`, `replays = 0`, `infra_error`, `final_reward`,
  `progress`, `success_rate`, `episodes`.
- **Infrastructure vs the agent's failure.** `infra_error = 1` only when the evaluator itself fails: a missing or
  mismatched asset or instance, a worker crash, a replay mismatch, a missing `final.json`. A policy that crashes the
  vehicle or makes the simulation diverge fails its case. An invalid policy is rejected before it costs a round.
- **Video.** After the verdict the sidecar renders the held-out evaluation once more (OSMesa) into `/data/replay.mp4`;
  `video.json` says whether the rendered run's state hashes match the graded ones. The video never changes the verdict.

## Tasks

30 tasks, 15 families × 2 instances, all `-standard`. "Reference" gives the held-out cases the reference controller
(`solution/`) passes on `i00` / `i01`.

| Family (`roboengineer-<family>-iNN-standard`) | Robot / objective | Adaptation / held-out cases | Reference |
|---|---|---|---|
| `landing-random-pad` | Intel Aero with the Neural Lander residual: land on a randomly placed pad | 3 / 6 | 6/6, 6/6 |
| `neuralfly-eight` | Neural Fly airframe with a flight-log force fit and wind: track a timed vertical figure eight | 5 / 10 | 10/10, 10/10 |
| `neuralfly-general` | the same, varied horizontal / vertical / inclined figure eights, both directions | 5 / 10 | 10/10, 8/10 |
| `neuralfly-general-skydio` | the same with the Skydio X2 camera appearance (960 × 720) | 5 / 10 | 10/10, 8/10 |
| `neuralfly-vector-wind` | general eights in a horizontal air-velocity field with isotropic drag | 5 / 10 | 10/10, 10/10 |
| `anycar-tracking` | AnyCar racing car: track a reference around an ellipse across surfaces of different friction | 3 / 10 | 10/10, 10/10 |
| `anycar-drift-park` | U-bend, a sideways slide, stop between two parked cars | 3 / 10 | 0/10, 0/10 |
| `anycar-tight-drift-park` | a 180° drifting turn into a tight bay | 3 / 10 | 0/10, 1/10 |
| `anycar-compact-lap-monaco-6`, `anycar-compact-lap-silverstone-8` | a 45 m loop shaped after an F1 circuit within 30 s (target 27.5 s), every gate in order | 3 / 10 | 10/10 on all four |
| `go2-attitude` | Unitree Go2: track commanded body roll and pitch | 3 / 10 | 10/10, 10/10 |
| `go2-forward-jump`, `go2-yaw-jump` | jump forward / with a heading change and land stably | 3 / 10 | 0/10 on all four |
| `go2-weave` | weave between four poles | 3 / 10 | 0/10, 0/10 |
| `g1-terrain-walk` | Unitree G1 humanoid, blind walking over flat, sloped, rough and stepped ground; the agent trains its 98 → 512 → 256 → 128 → 29 actor with mjlab / MuJoCo Warp on its own GPU | 4 / 12 | 1/12, 4/12 |

`[metadata] oracle` follows the reference: `full` where it passes every case, `partial` where it passes some, `none`
where it passes none.

## Others

### Resources

The caps are written by `scripts/task_resources.toml` (`^roboengineer-`); the verifier only reads JSON (about 20 s).

- **28 CPU tasks** (all but G1). The sidecar uses 1.7-1.9 cores while a deployment runs and its full 4 cores while it
  finalizes (held-out cases twice on four single-threaded workers, then the video: 79-199 s) and, for Neural Landing,
  through the per-case reference search before the agent starts (about 480 s). Its peak memory is 0.6-2.1 GiB.
- **G1** (`g1-terrain-walk`): one NVIDIA GPU for the agent's container (`environment/docker-compose.yaml` reserves one
  device for `main`; the sidecar has none and checks it). On an L40S the public trainer uses 1.8 GB of GPU memory at its
  default 256 environments, 4.7 GB at its cap of 1024 and 16.5 GB at 4096 (the reference solution, about 3.5 hours of
  training). A 24 GB card fits only when otherwise free and trains slower, so fewer iterations fit the time limit;
  results are comparable only on one GPU model.

### Evaluator design

The shared Control Transfer service and its fidelity notes: [control-transfer.md](control-transfer.md).
