# roboEngineer / Drone / Neural Fly

> roboEngineer task names: [roboengineer.md](roboengineer.md) (the package names of #329 used on this page, `control-transfer-*` / `quadrotor-landing-*`, map to `roboengineer-*` in `scripts/roboengineer/exported.toml`).

The separately scored `neural-fly-general-v1` task asks a coding agent to track **six timed laps of varied figure-eight commands**, improve a numeric controller over three deployment-feedback rounds, and freeze it for a ten-case held-out bank. Deployment uses **native CPU MuJoCo, NumPy CPU inference and OSMesa software rendering**. This task is simulation transfer with a real-flight-data force surrogate; it is not a physical flight experiment, DAIML reproduction, or PX4 reproduction.

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

`neuralfly_spec.make_spec(index, revision="general-eight/1")` returns a `control-transfer-instance/2` private instance with `transfer_track="same-plant"` plus its public specification. The persistent plant seed is `10000 + index * 1000 + 100`. Each instance has **one plant seed**, five adaptation cases (one per wind stratum), and ten disjoint held-out cases (two per stratum). The physical plant draws persist across both banks:

| Item | Definition |
|---|---|
| Mass and inertia scale | Uniform [0.97, 1.03] from one instance-level draw |
| Motor first-order time constant | Uniform [0.02, 0.06] s, fixed within an instance |
| Sinusoidal wind phase | Uniform [−π, π], fixed within an instance |
| Plane / orientation | Vertical, horizontal or inclined (15–75 degrees); yaw uniform [−π, π] |
| Direction / shape | Both traversal senses in each wind stratum; half extents [0.9, 1.5] m and [0.45, 0.85] m |
| Episode trajectory phase | Uniform [−π, π], independent episode draw |
| Horizontal center | Each coordinate uniform [−0.4, 0.4] m; vertical center uniform [1.8, 2.2] m |
| Initial position | Reference at t=0 plus independent per-axis offset in [−0.15, 0.15] m |
| Initial attitude / velocity | Upright, at rest |
| Physics / controller | 500 Hz / 50 Hz; residual recomputed at each physics step |
| Episode duration | Six laps at episode angular rate [0.8, 1.1] rad/s; 34.28–47.12 s, quantized to 50 Hz |

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
| Frozen general bank and public contract | `neuralfly_spec.make_spec(index, revision="general-eight/1")`; omit revision only for legacy fixed-eight |
| Numeric policy validation | `control_public.fly.validate(policy) -> normalized dict`; shared adapter serializes canonical JSON bytes |
| Private deployment | `trusted.fly.rollout(policy_or_path, case, out, asset, render) -> record` |
| Public nominal training | `neuralfly_nominal.rollout(policy, phase=..., center=..., initial_offset=..., noise_seed=..., out=..., render=...)` |
| Reference adaptation | `neuralfly_reference.solve(client, out)` |
| Full local validation | `python -m scripts.control_transfer.neuralfly_validate --asset /path/to/forces.npz --out /path/to/evidence --workers 2 --revision general-eight/1` |

The orchestrator owns the shared generator, protocol, task metadata, bank integration and native Harbor validation. It must copy `neuralfly_video.py` into the task-local private package and public root; copy `neuralfly_nominal.py` as public `nominal_fly.py`; and import this family's `make_spec` instead of the old case generator. Canonical policy submission still uses the shared adapter. No family module requires an evaluator GPU.

Run with the evaluator's pinned Python 3.12, NumPy 2.3.1, MuJoCo 3.5.0 and SciPy 1.17.0 environment. Set `MUJOCO_GL=osmesa`, `CUDA_VISIBLE_DEVICES=''`, `OPENBLAS_NUM_THREADS=1`, `LP_NUM_THREADS=1` and `OMP_NUM_THREADS=1`; install OSMesa and FFmpeg. Two instance workers leave room for their software encoders within the four-worker local allocation.

```bash
python -m unittest scripts.control_transfer.tests.test_neuralfly -v
python -m scripts.control_transfer.neuralfly_validate --asset /path/to/forces.npz --out /path/to/new-evidence --workers 2 --revision general-eight/1
```

The family checks cover randomized initialization, disjoint fixed-plant banks, analytic reference derivatives, numeric validation, observation-only adaptation, public/private separation, OSMesa enforcement and no-submission behavior. The local runner executes both complete held-out banks after three adaptation rounds, checks fresh-process replay, decodes every video and records source/runtime hashes. This is local integration evidence, **not a container-isolation proof, native Harbor certification or an LLM model score**. Final numeric results and any remaining gaps are retained in the external validation receipt and worker handoff; raw run artifacts are not committed to Git.

The spec imports only standard-library code and `neuralfly_constants.py`, a public data-only source of `DEFAULT` and `BOUNDS` re-exported by the controller. Include this constants module both in the private package root and in the exported public root beside `nominal_fly.py`. Static CI can run `python -S -m unittest scripts.control_transfer.tests.test_neuralfly_spec -v` without NumPy or MuJoCo.

## Historical fixed-eight native integration acceptance

Both fixed-eight native Harbor development banks pass 10/10 held-out cases after three noisy-feedback adaptation rounds, with mean engineering scores 90.3151 and 94.2980; both no-submission controls score zero. Resource enforcement is enabled and every held-out case has an exact fresh-process CPU replay. All delivered feedback bytes and videos are independently audited. These are scripted reference checks, not coding-agent scores. The [integration record](roboengineer-validation.md) documents the verifier build fix, bounded isolation probes, archive identity and remaining gates.

## General figure-eight revision

`general-eight/1` / `neuralfly-cpu/3` replaces the single fixed-shape, fixed-plane trajectory with episode-specific orientation, shape, speed and traversal direction. Every ten-case held-out bank includes all three plane classes and both directions for each wind stratum. Phase, center and initial offsets also vary; adaptation and held-out commands are disjoint, while physical plant parameters persist. The public nominal simulator accepts the same trajectory parameters explicitly. Public feedback remains commanded world position/velocity/acceleration plus noisy sensors and images; private seeds and command-draw metadata stay operator-only. Videos display the actual rotated/scaled path, not the old fixed curve.

This evaluates held-out trajectory tracking within the declared command distribution, not unrestricted arbitrary-path generalization. The numerical controller receives commands and cannot select their speed or direction. Score thresholds and motor limits are unchanged. Prior fixed-eight results do not certify this revision and must remain separately labeled. The broader flight directions also extrapolate the existing approximate aerodynamic surrogate beyond the paper's specific flight path; no new physical calibration is claimed.

## Legacy compatibility and integration routing

Existing `neural-fly` IDs retain `make_spec(index)` / `make_spec(index, revision="fixed-eight/1")`: the original spec and three-field case bank are returned unchanged. Three-field cases dispatch to the original fixed-eight phase/center/offset RNG sequence and 1,885-tick horizon, with `neuralfly-cpu/2` records. Explicit `trajectory_revision="fixed-eight/1"` is also accepted. Unknown revisions fail admission.

The shared registry generates `control-transfer-neural-fly-general-v1-i00-standard` and `control-transfer-neural-fly-general-v1-i01-standard` separately using `make_spec(index, revision="general-eight/1")`. Family remains `neural-fly` for existing policy and feedback adapters; the new name/task revision distinguishes scoring. Each general case includes `trajectory_revision="general-eight/1"`. No extra public or private module is required: retain existing allowlists, including public constants/nominal/video modules and private trusted fly. Both new task packages declare `oracle="none"` pending acceptance. The operator validation CLI accepts `--revision general-eight/1`; default remains legacy.

Both instance banks cover three plane classes and both senses overall, and each of five wind strata has both senses among its ten held-out cases. This is **not** the full 3×2×5 Cartesian product (which requires at least 30 cases). Trajectory draws are unchanged from commit 662208446, frozen before the prior fixed-reference checks; no reference tuning has occurred. Existing failures are retained. Adaptation and held-out trajectory sets remain disjoint.

At rate 0.8, six laps round to 2,356 ticks (47.12 s). Telemetry and video contain 472 samples/frames. Frame physics times are 0.02, 0.12, ..., 47.12 s; the shared 1 Hz selector returns all 48 scheduled images at 0.02 through 47.02 s. The cap does not truncate the schedule; the last image is 0.10 s before the terminal state, within the 1 s sampling interval. Keep the shared +0.02 s correction; raw video PTS starts at zero. This does not imply an exact terminal image is returned.

## Optional Skydio visual profile

`NEURALFLY_VISUAL_STYLE=skydio-x2/1` selects manufacturer-provided Skydio X2 mesh/texture assets from MuJoCo Menagerie commit `d7b481bac63d3d600ab404ee74f7474c5efe8a67`, Apache-2.0. This is **Skydio appearance with Neural Fly surrogate dynamics**, not calibrated Skydio physics. The visual model is a separate MjModel/MjData; only the physical pose is copied into it, with no stepping or writes back into physics. Camera output is 960×720 at 10 fps. The default `primitive` profile preserves existing tasks' videos; introducing the new appearance changes visual observations and must be recorded explicitly in task metadata/environment.

Prepare the public assets outside Git with `python -m scripts.control_transfer.neuralfly_visual --out /path/to/skydio_x2`. Bake that directory, including LICENSE and README.md, into the existing public asset image at `/opt/control-assets/skydio_x2`; runtime never downloads anything. An explicit `NEURALFLY_VISUAL_ASSETS` directory overrides the default. All four source files are SHA-256 checked before model construction; absent or mismatched assets fail visibly instead of falling back. These are public visual assets, not hidden dynamics assets.

Root packaging addition: copy `neuralfly_visual.py` alongside `neuralfly_video.py` into both repository-style and top-level public/private package layouts. Set the profile only on the intended new task revision, consistently for nominal and deployment video. No controller, mass, inertia, collision, motor or scoring changes are required. The helper is safe to export publicly; spec banks and reference modules remain private. Preserve the Apache license and pinned provenance when redistributing assets. Renderer enablement/image preparation remains orchestrator-owned.

The shared registry exposes the new appearance only as
`neural-fly-general-skydio-v1` (observation revision `neuralfly-skydio/1`).
Legacy fixed/general task packages retain their frozen primitive renderer and
original image tags. A frozen `neuralfly_video_primitive.py` supplies those exact
runtime bytes; changes to the new renderer cannot silently alter old observations.
Public and private new-task packages include the render helper in both import
layouts, with the operator download function and CLI removed. Runtime requires
pre-baked, checksum-verified assets and fails closed if they are missing/modified.
The benchmark remains the original Neural Fly surrogate physically; the mesh is
appearance only. Prior reference scores are not new Skydio agent results.

### Experimental vector-wind revision

`make_spec(index, revision="general-eight-wind/1")` produces the separately named
`neural-fly-vector-wind-v1` task. Its private cases use `trajectory_revision=general-eight/1`
and `dynamics_revision=vector-wind/1`; existing hooks and absent dynamics revisions
retain scalar-wind physics exactly. Unknown dynamics revisions fail closed.

The wind is now a world-frame air velocity pointing toward airflow travel direction.
A fixed plant heading uses the pre-existing wind phase; speed uses the same five strata,
including `8.5 + 2.4 sin(t + phase)` m/s for gusts. This horizontally uniform field has
no vertical wind or spatial turbulence. Force is the existing **zero-wind** fitted
surrogate plus `c (|w-v|(w-v) + |v|v)`, with assumed `c=0.045 kg/m`. Subtracting the
calm-air drag avoids adding calm drag twice. The total still clips at +/-12 N per axis.
This is a synthetic isotropic directional extension, not a directional calibration
of the paper's aircraft or a replay of measured wind vectors. Heading and gust phase
are coupled in this initial revision.

Private records use `neuralfly-cpu/4` and identify the synthetic calibration. `wind.npz`
contains the world air velocity at saved trajectory timestamps for operator visualization.
It must remain private, alongside trajectory truth: do not add it to public exports,
feedback allowlists or agent videos. Public feedback channels remain unchanged. Operator
demos may show direction and magnitude, explicitly separate from agent-facing feedback.
The shared registry generates i00/i01 with `oracle=none`; no native acceptance or model score is claimed. Agent videos keep the primitive appearance and contain no wind arrows.

Local validation: 25 tests pass; stdlib spec checks pass. The prior i00 gusting record
replays exactly, and two new gusting rollouts match each other exactly. The unchanged
scripted controller completed 43.52 s with RMSE 0.07599 m, score 83.1984 and zero force
clipping in this one case. This is not a full-bank validation or an adaptation campaign.


The operator-only replay command renders the recorded `wind.npz` vectors at exactly
matching `trajectory.npz` timestamps, without rerunning dynamics or inferring wind
from motion. Orange arrows originate at the drone; cyan arrows show the same spatially
uniform airflow. Arrows point **toward** flow travel, not meteorological wind origin.
The HUD gives world x/y/z velocity and magnitude in m/s. Skydio geometry is appearance
only. Every frame is labeled operator-only and synthetic. Input/output SHA-256 hashes,
sampled times and vectors are retained in the adjacent private receipt.

```bash
MUJOCO_GL=osmesa CUDA_VISIBLE_DEVICES= python -m scripts.control_transfer.neuralfly_wind_demo \
  --episode /private/episode --output /private/operator-wind.mp4 \
  --assets /opt/control-assets/skydio_x2
```

Pillow and ffmpeg are operator rendering dependencies. This module is excluded from
both task runtime layouts, alongside its output and the private wind trace. It cannot
replace `video.mp4` in an episode directory; the benchmark's feedback video must stay
unchanged. A synthetic vector trace must never be described as measured hardware wind.

Integration validation on 2026-10-14 used the generated i00/i01 packages with the
previously frozen scripted policy (no new tuning or adaptation rounds): 10/10 held-out
successes per plant, mean scores 90.0123 and 88.4098, combined 89.2110. All 20
fresh-process replay pairs match whole records, true states and private wind arrays;
none of these cases clipped the residual force. This new synthetic dynamics revision
has different difficulty and must not be compared directly with scalar-wind scores.
Four feedback videos decode and 159 delivered JPEG hashes plus 1,576 noisy rows match
the recorded observations. Both no-submission instances score zero. A prior scalar-wind
record remains byte-identical; 83 earlier videos are unchanged. Two isolated public
nominal-package rollouts pass, without trusted imports. MuJoCo 3.5.0 rendering was
verified as llvmpipe. All 58 focused tests pass.

The 436-frame operator demo reads the private wind trace at exact pose timestamps;
its source episode is byte-identical to the new generated i00 gusting case. The demo
is outside the task packages. These checks establish local frozen-controller replay
and packaging only, not native container isolation, new multi-round adaptation or an
LLM result. Keep `oracle=none` until the remaining acceptance and review are complete.
