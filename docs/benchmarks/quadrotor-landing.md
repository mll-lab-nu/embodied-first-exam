# Neural Landing — roboEngineer / Drone

> roboEngineer task names: [roboengineer.md](roboengineer.md) (the package names of #329 used on this page, `control-transfer-*` / `quadrotor-landing-*`, map to `roboengineer-*` in `scripts/roboengineer/exported.toml`).

Neural Landing is the first implemented task in the [roboEngineer collection](roboengineer.md). This page specifies quadrotor landing with deployment adaptation, random-pad v4. Existing task IDs and the internal `Neural Lander` benchmark label are retained.

This implementation lives in `scripts/quadrotor_landing/`. It includes two generated native Harbor policy tasks using the explicit `eai-policy/1.0` contract ([POLICY_MODE.md](roboengineer-policy.md)); native Docker/Harbor oracle/nop validation passed on both instances with resource enforcement. Task identity is `random-pad-landing/4`, score version `oracle-relative-time/1`. Version 4 retains the ordinary agent physics and `landing-policy/2` interface, and normalizes timing against a private full-model oracle for each case. Earlier records keep their original interpretation and cannot be resumed or relabeled as v4 results.

## Task

Fly from a randomized starting position to an independently placed stationary ground pad, land gently, and settle. Initial body-origin x/y and pad x/y are drawn in [-1, 1] m; pairs with horizontal separation below 0.5 m are rejected and both positions resampled. Body-origin height is uniform in [0.8, 1.5] m (landing-foot clearance [0.71, 1.41] m). Initial attitude is upright, velocity zero. The pad is a 0.45 m radius marking on a flat floor, fixed in world coordinates throughout an episode. It has no raised platform or table edge. The commanded pad position is public; robot ground truth remains private.

MuJoCo CPU physics runs at 500 Hz and control at 100 Hz. Episodes last 16 s. The reference trajectory translates horizontally at its starting height, then descends onto the pad. Approach duration, descent duration, feedback gains, and the learned force correction are tunable.

## Paper calibration and its limits

The target aircraft is the 1.47 kg Intel Aero used in [Neural Lander](https://arxiv.org/abs/1811.08027). The [author's released flight-data notebook](https://github.com/GuanyaShi/neural_lander_sim_1d/blob/30ab04cb5ac3fd4fa55cd2a168ee28aa679f5e9b/realdata/learning_fa.ipynb) provides more calibration than the simplified 1D simulator. We use these values directly:

| Quantity | Value | Provenance |
|---|---|---|
| Mass | 1.47 kg | Flight notebook, cell 25 (zero-based) |
| Propeller diameter | 0.23 m | Same |
| Air density / gravity | 1.225 kg/m³ / 9.81 m/s² | Same |
| Dimensionless thrust coefficient | 0.08937873049125099 | Same |
| Thrust coefficient | 8.510971060074351e-8 N/RPM² | Derived as C_T rho D⁴ / 60², matching cell 26 |
| PWM-to-RPM calibration | -0.0026 PWM² + 17.0948 PWM - 14834.1065 | Cell 17; used when auditing the real flight logs |
| Aerodynamic residual | Released 12→25→30→15→3 ReLU checkpoint | Learned from real flight data |

The [released 1D simulator](https://github.com/GuanyaShi/neural_lander_sim_1d/blob/30ab04cb5ac3fd4fa55cd2a168ee28aa679f5e9b/1d_landing_simulator.ipynb) supplies a 0.09 m body clearance, 1.7× weight thrust limit, and 20% command blending at 100 Hz. The last corresponds to a first-order time constant of 44.814 ms. These are upstream simulation settings, **not measured actuator identification**. The current control ABI commands thrust in N, so PWM conversion is used in the calibration audit, not inserted as an additional nonlinear command stage.

**This is still a partially calibrated aircraft model.** We did not find the experiment's measured inertia, rotor geometry/channel ordering, yaw torque coefficient, or motor identification in the paper and these releases. The current inertia (0.025, 0.025, 0.045 kg·m²), rotor coordinates (±0.18 m, ±0.18 m), alternating yaw torque/thrust ratio (±0.015 m), body/feet geometry, friction, and measurement noise are benchmark assumptions. The visual body is procedural, not manufacturer CAD. Those parameters require the authors' calibration or new hardware identification before calling this a fully calibrated 6-DOF Intel Aero simulation. See `calibration.json` for machine-readable provenance.

## Hidden deployment dynamics

The evaluator loads the original checkpoint, pinned at commit `30ab04cb5ac3fd4fa55cd2a168ee28aa679f5e9b`, SHA-256 `abcce30c945709ace29c3c68159738717a945b8e87f73d74bd3dcb54f74002e9`. `prepare_assets.py` checks the hash, loads with `weights_only=True`, validates tensor shapes, and converts to non-pickled NumPy arrays. Evaluation inference is CPU NumPy; PyTorch is only needed for preparation/audit. Weights and flight logs stay outside the agent image and source tree.

Feature order follows the flight notebook: body-origin world z, world vx/vy/vz, quaternion xyzw, and actual four motor RPM divided by 8000. MuJoCo quaternions are reordered from wxyz and canonicalized to **negative w**, matching all samples in the released 35–325 s training interval. All three network outputs are applied as world-frame force at the center of mass, recomputed each physics step. There is no residual torque model. Unlike v1, there is no force clipping, upright-only reduction, fixed-RPM substitution, or thrust gate. The paper-weight track uses scale 1.0; optional operator scale overrides are sensitivity experiments, not paper-calibration results.

The network is an empirical surrogate. Exact checkpoint inference does not guarantee accurate aerodynamics outside its flight-data distribution, notably motors-off/contact or aggressive attitudes. MuJoCo supplies ground contact independently. No claim is made that the paper's controller stability proof applies to our controller.

`audit_calibration.py` checks source hashes and calibration literals, compares runtime inference with original PyTorch inference on 1,000 real-flight states, and reconstructs force labels using the released timestamp interpolation and velocity differentiation. Its flight-data error is an **in-sample diagnostic**, not an independent real-world holdout. The release's training/test split is not available as a frozen checkpoint-specific index set.

## Training and three-round feedback

The agent-visible nominal MuJoCo simulator has the same task sampler and calibrated nominal thrust but no deployment residual. Each candidate is a numeric `landing-policy/2` JSON object: six feedback/trajectory parameters and 3×14 bounded coefficients for a learned three-axis correction. The agent can edit its own training/analysis programs; the evaluator executes the fixed validated controller, never arbitrary agent Python, pickle, paths or plugins. The reference learner uses ridge regression on residual force estimated from noisy IMU, attitude and measured RPM. It uses no exact force labels, rewards or privileged contact flags; it is supervised system identification, not PPO or an LLM evaluation.

Each of three rounds deploys on the same three adaptation cases. Each episode returns 320 noisy observation rows at 20 Hz, the commanded pad position, own rotor commands, and sixteen JPEG frames at 1 Hz. Full 1280×720, 25 fps videos are saved for the operator. Sensor standard deviations: position 2 mm; velocity 8 mm/s; quaternion components 0.0005 before normalization; angular velocity 0.003 rad/s; body IMU specific force 0.12 m/s²; rotor RPM 15. Noise is independent Gaussian, not persistent sensor bias. The public goal is not hidden state. Seeds, exact robot state, actual forces, contact records and scores never appear in service responses.

Six final cases use new start/pad/noise seeds on the same paper residual. This measures adaptation to a particular plant across new task placements, not unseen-airframe generalization. Mass and inertia are not randomized.

Rounds are charged before rollout. State persists across service restarts; an interrupted running round marks infrastructure failure. Only completed rounds can be selected. Sealing closes all service calls and freezes the policy hash. A task-version mismatch or residual-asset mismatch refuses old sessions. After the agent stops, the trusted sidecar checks the selected policy hash and runs the final cases; a separate no-network verifier consumes its collected evidence. The standalone development server remains available; native tasks use the bounded `native/service.py` implementation of `eai-policy/1.0`.

## Verification

Safe success requires all of:

- Landing-foot contact on the target pad. Any foot contact outside its radius disqualifies the episode, including landing elsewhere and sliding onto it later.
- First-contact vertical speed <0.4 m/s and horizontal speed <0.25 m/s.
- The final continuous second in contact, with horizontal error **relative to the actual target pad** <0.15 m, tilt <0.15 rad, and translational speed <0.08 m/s.
- No body/rotor ground collision, tilt >0.8 rad, departure from the world square [-3,3]² m, or body height >3 m.

Before the agent starts, the evaluator optimizes a reference separately for every initial position, pad placement and hidden-dynamics case. Let `T_ref` be its verified safe completion time and `T_100 = 1.10 × T_ref`. Full credit allows **10% longer** than the reference:

```
score = 60 + 40 × clip((16 - t_complete) / (16 - T_100), 0, 1)  # safe success
score = 0                                                    # failure
```

`t_complete` includes approach, descent and one uninterrupted second of settling. The 100 Hz timer counts elapsed intervals between stable samples; losing contact or stability resets it. Only the final continuous settled interval counts, and simulation always continues to 16 s. Unsafe landings never receive a time bonus. A reference with `T_100 >= 16 s` is rejected as unusable instead of silently relaxing the deadline or assigning an agent zero. A rollout without calibration is an explicitly **ungraded diagnostic** (`score: null`), never an official score.

For illustration only, if a case's numerical reference is 6 s, completing safely by 6.6 s earns 100; 10 s earns about 85.53; and 16 s earns 60. The implementation does not hardcode a six-second reference. The 10% allowance and 60/40 weighting are benchmark choices, not claims from Neural Lander.

Aggregate grading reports mean score across **all** cases, success rate, and mean successful completion time (null if none succeed). A speed bonus can trade off against failure frequency, so score must always appear alongside success rate. Policies must be compared on the same private case bank, with identical frozen oracle references. Timing values, scores and oracle artifacts never appear in adaptation feedback.

### Oracle calibration and optimality limits

`trusted/oracle.py` searches the **actual CPU MuJoCo evaluator**, including the complete hidden residual network, motor lag, thrust saturation, contacts, and the same safety/settling checks. The oracle receives exact position, velocity, attitude, angular velocity and motor RPM, and subtracts the exact residual force; ordinary policies continue to receive noisy observations. It minimizes safe completion time over the six public bounded gains/timings of the existing approach-then-descent controller. It does not change actuator limits, trajectory-duration bounds, safety thresholds or episode length to obtain a faster reference.

The deterministic search uses a population of 12 starts (including the default and minimum-duration trajectories), five differential-evolution generations, and coordinate refinement at normalized steps 0.05 and 0.0125. This is at most 96 distinct rollouts per case, plus two fresh-process replays of the winning policy. The fixed search seed is independent of agent submissions; individual cases can be optimized in parallel. Every candidate, its parameters, safety metrics and objective are saved in `search.jsonl`. The selected policy, both exact-state replay trajectories, solver status and replay hashes are preserved alongside `reference.json`.

**This is a best-found feasible numerical oracle, not a certified global optimum.** The controller family is fixed; the search does not optimize arbitrary rotor-command trajectories or prove a lower bound. Records explicitly set `global_optimality_certified: false` and `optimality_gap_s: null`, and disclose optimizer convergence/budget exhaustion. The time is an upper bound on this oracle family's minimum achievable completion time. Claiming the unrestricted physical optimum would require a richer control interface and an optimality certificate or defensible lower bound; a successful local/stochastic solve is insufficient.

All adaptation and held-out references are frozen **before** the session deadline starts or the API becomes available. The private bank pins cases, residual checkpoint, relevant evaluator source hashes, Python/MuJoCo/NumPy/SciPy versions and search settings. The session stores its digest; resume and final grading validate the bank, selected policies, search logs and both replay records. Missing, tampered, stale or infeasible calibration aborts setup/grading rather than falling back to a fixed threshold. Changing the implementation/settings requires a new calibration and session. Oracle policies, exact trajectories, candidate logs and per-case times remain under the evaluator-only volume and have no service endpoint.

The verifier executes each final case twice in fresh Python processes and requires exact private-record equality, including trajectories, initial placement, pad position and full residual forces. The first replay may render video. Rendering/simulator failure is infrastructure failure, not an agent zero. Tests cover wrong-pad rejection, crossing the arena, task sampling, full residual inputs and quaternion convention, public-field filtering, replay/render independence, sealing, tampering and budget persistence.

## Run locally (trusted operator)

Use Python 3.12 with `requirements.txt`, `scipy==1.17.0` for the trusted optimizer, ffmpeg and EGL/OSMesa. SciPy is installed only in the evaluator image; the agent does not need it. Preparation and the calibration audit additionally require PyTorch. Output directories for validation must be new.

```bash
python -m scripts.quadrotor_landing.prepare_assets --out /tmp/landing-assets
python -m scripts.quadrotor_landing.audit_calibration --cache /tmp/landing-source-cache --residual /tmp/landing-assets/residual.npz --out /tmp/landing-calibration-audit.json
python -m scripts.quadrotor_landing.validate --residual /tmp/landing-assets/residual.npz --out /tmp/landing-oracle-time-v4
LANDING_TEST_RESIDUAL=/tmp/landing-assets/residual.npz python -m unittest discover -s scripts/quadrotor_landing/tests -v
```

Validation saves submitted policies, exact agent feedback/image payloads, diagnoses, videos, private trajectories, source hashes, runtime versions, and final grading records. Its disclosed reference seeds must not be reused as secret model-evaluation banks. Existing v1/v2 binary-score records and v3 unnormalized time-score records remain unchanged. Oracle calibration can take several minutes; `--oracle-workers N` controls operator-side case parallelism and is not charged to the agent deadline. The standalone validator uses operator-disclosed seeds and is not a coding-agent score.

## Isolation and integration status

The standalone development compose transport (`Dockerfile.agent`, `Dockerfile.sim`, `compose.yaml`) was removed in #329's review: its agent image copied all of `public/`, which then held the reference learner (now `scripts/quadrotor_landing/reference/`, copied only into `solution/`). The Harbor tasks are the one transport.

Native Harbor integration now includes egress controls, policy-task protocol declarations, generated tasks, resource/cutoff declarations, and CI registration; the oracle/nop validation is recorded below. LLM coding-agent evaluation remains separate. Completing the physical airframe calibration still requires the missing experimental identification data and is not implied by successful reference landings.

## Visual presentation

`trusted/rendering.py` builds a separate MuJoCo render model (`flight-studio/1`) with a detailed procedural airframe, animated propellers, a marked landing circle, architectural background, studio lighting and perimeter scale marks. The physics model is unchanged. The camera is fixed in world coordinates; all sixteen agent image samples use the same scene and contain no score or privileged-state overlays. Rotor animation uses the public noisy RPM readings. Each rendered run saves `rendering.json`; sessions pin the render style and refuse to resume across a style change. Earlier recordings remain archived with their original appearance. This visual shell is not manufacturer CAD or additional physical calibration.

## Native Harbor packaging and validation

`python3 scripts/quadrotor_landing/gen_tasks.py render` writes two standard-only tasks, `quadrotor-landing-random-pad-i00-standard` and `i01-standard`. Each has three adaptation and six held-out cases, frozen in matching simulator/verifier instance files. Instance 0 matches the disclosed standalone validation bank; instance 1 uses a different bank. These are reproducible development instances, not undisclosed competition test seeds. Official new held-out banks must be frozen by the operator before model comparisons.

The generator copies public nominal simulation and the numeric ABI into the agent image. The reference fitting algorithm is copied only into `solution/`. Hidden deployment code and casebanks are copied only into the sidecar; checkpoint weights are baked into its own simulator image. All runtime imports resolve inside the task/image. CPU OSMesa supplies 720p/25fps video rendering without a GPU. The `flight-studio/1-cpu` presentation profile keeps geometry/camera/lighting but reduces shadow resolution and disables multisample antialiasing; physics is unchanged. Image preparation downloads the pinned weights at build-preparation time; the runtime and verifier do not download assets.

The idle client container starts alongside the simulator so the resource monitor can discover it during private calibration. Both containers expose a health check against the simulator readiness endpoint. Harbor 0.23.0 with Docker Compose uses `up --wait`, so the agent starts only after calibration succeeds; the client must not depend on the simulator becoming healthy before its own container starts. This avoids the monitor's 120-second missing-container timeout without disabling monitoring or charging calibration to the agent.

On a host with Docker, Compose and Buildx installed, and NumPy and PyTorch available for preparation:

```bash
bash images/quadrotor-landing/prepare_assets.sh
docker build -f images/quadrotor-landing/Dockerfile -t ghcr.io/mll-lab-nu/eai-quadrotor-landing:0.1.0 .
python3 scripts/quadrotor_landing/gen_tasks.py check
# Use the native Harbor runner described in docs/RUNNING.md for oracle and nop on both instances.
# Keep run artifacts outside tasks/ and outside a repository-level results/ directory.
```

The versioned simulator image was built and tested privately; its registry tag has not been published. Native Harbor 0.23.0 with Docker ran the reference oracle and `nop` on both frozen instances using an AWS c7i.2xlarge (8 vCPUs, 16 GiB, no GPU), with `RCB_LIMITS_ENFORCE=1`:

| Instance | Oracle binary reward | Engineering score / 100 | Safe held-out cases | Nop reward |
|---|---:|---:|---:|---:|
| i00 | 1 | 82.29276566245893 | 6/6 | 0 |
| i01 | 1 | 84.94186810764631 | 6/6 | 0 |

All four trials completed without infrastructure errors, missing monitor records or observed resource violations. Each oracle used all three feedback rounds. Both sets of six held-out cases matched on fresh-process replay. The downloaded evidence includes 30 checked 720p/25fps videos, 288 exact agent-visible images, 5,760 noisy observation rows, policy revisions and audit records. These are scripted reference-learner integration results, not LLM/VLM model scores; the learner fits sensor feedback and does not analyze the images. `oracle = "full"` refers to Harbor's binary success predicate, not a 100/100 engineering score.

The test found and fixed a startup-order issue: waiting to create the client until calibration finished caused the shared monitor's discovery deadline to expire. Starting the idle client immediately with a readiness healthcheck preserves calibration gating and gives the monitor full coverage. Initial failed/diagnostic attempts are retained separately. The host also needed Docker Buildx before Harbor could build its task images.

During recorded agent execution, operator probes confirmed absent private evaluator paths and AWS credentials in the agent container, rejected private HTTP routes, blocked nonallowlisted AWS HTTPS and instance-metadata access, and working permitted package-registry access. The verifier ran in a separate container, and its successful transition to Harbor's controlled-TCP deny-all policy was recorded during grading. This is Harbor's network implementation, not Docker `network_mode: none`; local/DNS/ICMP exceptions remain. Harbor permits public networking during trusted setup before agent execution; setup snapshots and agent-phase probes are reported separately. These checks are not an adversarial LLM red-team or a proof against every escape. Operator-generated probe rejections are labeled separately from reference-agent behavior.

The original validation passed task-specific checks and 100 CI mutation cases. That checkout's full repository check reported pre-existing generator file-permission mismatches in unrelated task families. Full logs, media, source hashes, trial checksums and replay evidence are retained in the operator's integration-test archive (SHA-256 `bbafe6ffa619f92946c26efececa0101c7a7ba10b7900ed008536f421d21023c`); run artifacts are kept outside the source repository. Validation metadata was updated after the run; executable task contents are unchanged from the tested archive. The review branch was subsequently based on upstream `74e458323ab93103e98fc0d57d0b31abd7b131bc` in a clean checkout with `umask 022`: the full `ci_checks/run_all.sh` run passed, including all registered generator checks, 101 CI mutations, service suites and both landing task contract checks. This repository validation does not constitute an additional physics or LLM evaluation.

The protocol/CI changes are shared infrastructure and should be reviewed separately from the generated task files when preparing upstream pull requests. No upstream issue, PR, merge or registry publication is performed by generation.

For a local generated-package smoke test (separate processes, without container isolation), use a Python environment with the simulator requirements and SciPy installed:

```bash
MUJOCO_GL=egl LANDING_RENDER_QUALITY=cpu python -m scripts.quadrotor_landing.validate_native --instance 0 --out /tmp/landing-native-i00 --residual /path/to/residual.npz
# Run the other frozen bank with --instance 1 and a different output directory.
# For nop, add --mode nop; an already validated session's timing bank may be reused via --oracle-cache.
```

Use `MUJOCO_GL=osmesa` on a CPU-only host with OSMesa installed. The local smoke driver executes only the generated task copies, retains exact responses/media/private grading evidence, and labels its output `container_isolation_tested: false`. It is not an agent adapter and is not used for official model runs.
