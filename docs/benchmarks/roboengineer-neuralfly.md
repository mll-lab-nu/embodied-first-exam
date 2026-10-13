# roboEngineer / Drone / Neural Fly

Neural Fly asks a coding agent to track **six timed vertical figure-eight laps**, improve a numeric controller over three deployment-feedback rounds, and freeze it for a ten-case held-out bank. Deployment uses **native CPU MuJoCo, NumPy CPU inference and OSMesa software rendering**. This task is simulation transfer with a real-flight-data force surrogate; it is not a physical flight experiment, DAIML reproduction, or PX4 reproduction.

## Reference and provenance

The source is [Neural-Fly Enables Rapid Learning for Agile Flight in Strong Winds](https://arxiv.org/abs/2205.06908), Science Robotics (2022), with the [official code and flight logs](https://github.com/aerorobotics/neural-fly/tree/0ed50246b1f1db194e8f0726749351636d3501bf), pinned to `0ed50246b1f1db194e8f0726749351636d3501bf`. Its indoor reference is 2.5 m wide and 1.5 m tall, with period 2π seconds. The five conditions are 0, 4.2, 8.5 and 12.1 m/s constant wind, and 8.5 + 2.4 sin(t) m/s wind. The source experiments include a warm-up lap before the six measured laps; **this benchmark has no excluded warm-up** and scores acquisition from the first control step.

The custom aircraft's published mass is 2.53 kg and thrust-to-weight ratio is 2.2. This benchmark uses those values and 11-inch propeller visuals, but approximates the body as an untilted symmetric X quadrotor with rotor coordinates (±0.195, ±0.195) m, diagonal inertia (0.04, 0.04, 0.07) kg·m² and yaw torque/thrust ratio ±0.02 m. The paper aircraft is a wider, tilted-rotor custom platform. Geometry, inertia, lag, sensor noise and contact shapes here are benchmark assumptions, not a complete aircraft identification.

`calibrate_fly.py` fits an 18-feature quadratic ridge surrogate to the official baseline flight logs, using velocity, quaternion vector components and wind speed. It does not train the paper's wind-invariant DAIML representation. The existing private asset is reused without retraining:

- `forces.npz` SHA-256: `551eeb0d8e2c75e157c087f1ab2f5e40e68400a84fdf0882ed719ddfcfd8108a`.
- 36,984 training rows and 9,252 validation rows, the final 20% of each flight reserved temporally.
- Per-axis validation RMSE: 0.8749, 0.5893 and 1.6956 N. These are same-flight temporal splits, not unseen-flight validation.
- The fit includes the baseline figure-eight logs at strong winds. Consequently this task does **not** replicate the paper's unseen-wind learning experiment.
- The asset and original logs have not been committed or redistributed. Follow the upstream terms when preparing private assets; the repository license does not relicense them.

The inherited surrogate clips each force axis to ±12 N. This is an explicit benchmark stability assumption. Strongest-wind cases can hit that clipping throughout the episode; report `residual_clipping_fraction` alongside results. A nominal wind label therefore does not establish faithful physical wind response. No stratum is silently removed or relabeled.

## Cases, plant and time

`neuralfly_spec.make_spec(index)` returns a `control-transfer-instance/2` private instance with `transfer_track="same-plant"` plus its public specification. The persistent plant seed is `10000 + index * 1000 + 100`. Each instance has **one plant seed**, five adaptation cases (one per wind stratum), and ten disjoint held-out cases (two per stratum). The physical plant draws persist across both banks:

| Item | Definition |
|---|---|
| Mass and inertia scale | Uniform [0.97, 1.03] from one instance-level draw |
| Motor first-order time constant | Uniform [0.02, 0.06] s, fixed within an instance |
| Sinusoidal wind phase | Uniform [−π, π], fixed within an instance |
| Episode trajectory phase | Uniform [−π, π], independent episode draw |
| Horizontal center | Each coordinate uniform [−0.4, 0.4] m; vertical center 1.8 m |
| Initial position | Reference at t=0 plus independent per-axis offset in [−0.15, 0.15] m |
| Initial attitude / velocity | Upright, at rest |
| Physics / controller | 500 Hz / 50 Hz; residual recomputed at each physics step |
| Episode duration | Six 2π-second laps, quantized to 1,885 controller ticks (37.70 s) |

Wind strata are disturbance scenarios on that fixed physical plant. Public commands, initial positions and measurement noise differ by episode. Generalization to a newly drawn physical plant is a separate comparison and must be reported separately. These checked-in case definitions are reproducible development banks, not secret competition seeds.

Revision `neuralfly-cpu/2` fixes initialization order: `mj_setConst` restores the XML initial pose, so mass/inertia updates must occur **before** assigning the randomized position. Earlier prototype results are not directly comparable to this revision. The regression suite tests the actual MuJoCo behavior.

## Controller, learning and observations

The data-only policy has `kp`, `kd`, `ki`, `attitude_gain`, `rate_gain`, a bounded 3×7 force-regression matrix and optional `observer_gain` in [0,15] (omitted means zero for compatibility). Policy validation rejects unknown fields, booleans, non-finite values, oversized coefficient shapes and out-of-range numbers. Only these numbers reach the evaluator; neither Python nor ONNX graphs are executed.

The fixed controller is geometric attitude feedback around position PID and commanded acceleration. It applies a public 50-degree commanded-tilt envelope, a positive vertical-force floor and the original 2.2 thrust-to-weight rotor limit. These are command limits, not an assertion that actual attitude can never exceed 50 degrees. Motor thrusts remain nonnegative with the hidden first-order response.

The optional disturbance observer estimates force from **noisy velocity differences, noisy attitude and its own previous thrust command**, filtered through a public nominal actuator lag of 0.04 s. It never reads actual motor thrust, ground-truth acceleration, wind, mass scale or private force coefficients. Its estimated force is bounded to ±20 N. The fixed observer is an additional controller-family option, not DAIML.

The controller receives position (0.01 m noise standard deviation), velocity (0.02 m/s), normalized wxyz quaternion (0.0005 component noise), angular velocity (0.003 rad/s), and exact commanded target position/velocity/acceleration. Exported noisy telemetry is sampled at 10 Hz; the existing shared feedback adapter supplies camera samples at 1 Hz. Full operator recordings are 640×480, 10 fps. The camera and displayed reference curve use world coordinates. No private metric or state overlays appear in the images.

`neuralfly_reference.py` is an **operator/reference solution** and belongs only under `solution/` in generated tasks. It observes noisy tracking errors, increases bounded observer/position/damping gains between rounds, and selects a round using those same permitted measurements. It does not inspect camera images and is not an LLM evaluation. Preserve the exact responses, policy snapshots, short diagnoses and selection record. Do not install this reference in the public agent image.

`neuralfly_nominal.py`, `neuralfly_video.py` and `control_public/fly.py` provide public training. They contain no private draw functions, seed banks, evaluator scoring, asset paths or force coefficients. Never generate the nominal copy by textual substitution on `trusted/fly.py`.

## Score and verification

Any contact, numerical failure or escape more than 5 m from the center fails the episode and scores zero. Otherwise score is `100 exp(-max(0, RMSE_m − 0.03)/0.25)`. Binary success requires completing the full horizon with RMSE below **0.25 m**. The agent cannot slow the prescribed trajectory or omit an initial acquisition period. Task success requires every held-out case to succeed; continuous score and per-stratum success must also be reported.

Each held-out case is replayed in fresh processes. State hashes, metrics and noisy telemetry must match exactly, including between rendered and unrendered runs. Private `trajectory.npz` includes time, true pose/velocity and rotor thrust state; the operator record includes realized dynamics, clipping/saturation fractions and source asset hash. None of those fields are part of public feedback. CPU-only rendering is checked at runtime and rejects a loaded EGL/GLFW backend.

## Integration and validation

Owned entry points:

| Purpose | Entry point |
|---|---|
| Frozen bank and public contract | `neuralfly_spec.make_spec(index)` |
| Numeric policy validation | `control_public.fly.validate(policy) -> normalized dict`; shared adapter serializes canonical JSON bytes |
| Private deployment | `trusted.fly.rollout(policy_or_path, case, out, asset, render) -> record` |
| Public nominal training | `neuralfly_nominal.rollout(policy, phase=..., center=..., initial_offset=..., noise_seed=..., out=..., render=...)` |
| Reference adaptation | `neuralfly_reference.solve(client, out)` |
| Full local validation | `python -m scripts.control_transfer.neuralfly_validate --asset /path/to/forces.npz --out /path/to/evidence --workers 2` |

The orchestrator owns the shared generator, protocol, task metadata, bank integration and native Harbor validation. It must copy `neuralfly_video.py` into the task-local private package and public root; copy `neuralfly_nominal.py` as public `nominal_fly.py`; and import this family's `make_spec` instead of the old case generator. Canonical policy submission still uses the shared adapter. No family module requires an evaluator GPU.

Run with the evaluator's pinned Python 3.12, NumPy 2.3.1, MuJoCo 3.5.0 and SciPy 1.17.0 environment. Set `MUJOCO_GL=osmesa`, `CUDA_VISIBLE_DEVICES=''`, `OPENBLAS_NUM_THREADS=1`, `LP_NUM_THREADS=1` and `OMP_NUM_THREADS=1`; install OSMesa and FFmpeg. Two instance workers leave room for their software encoders within the four-worker local allocation.

```bash
python -m unittest scripts.control_transfer.tests.test_neuralfly -v
python -m scripts.control_transfer.neuralfly_validate --asset /path/to/forces.npz --out /path/to/new-evidence --workers 2
```

The family checks cover randomized initialization, disjoint fixed-plant banks, analytic reference derivatives, numeric validation, observation-only adaptation, public/private separation, OSMesa enforcement and no-submission behavior. The local runner executes both complete held-out banks after three adaptation rounds, checks fresh-process replay, decodes every video and records source/runtime hashes. This is local integration evidence, **not a container-isolation proof, native Harbor certification or an LLM model score**. Final numeric results and any remaining gaps are retained in the external validation receipt and worker handoff; raw run artifacts are not committed to Git.

The spec imports only standard-library code and `neuralfly_constants.py`, a public data-only source of `DEFAULT` and `BOUNDS` re-exported by the controller. Include this constants module both in the private package root and in the exported public root beside `nominal_fly.py`. Static CI can run `python -S -m unittest scripts.control_transfer.tests.test_neuralfly_spec -v` without NumPy or MuJoCo.
