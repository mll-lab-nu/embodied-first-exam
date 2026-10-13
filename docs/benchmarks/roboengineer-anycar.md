# roboEngineer — AnyCar multi-surface tracking

This family ports AnyCar's MuJoCo contact-wheel vehicle mechanism into the bounded control-transfer workflow. It evaluates a coding agent's ability to calibrate a controller using permitted deployment observations. It does not evaluate the pretrained AnyCar transformer. The earlier local desert showcase used a numeric dynamic bicycle plant and Isaac rendering; that showcase is not the evaluator here.

## Model and provenance

The source is [LeCAR-Lab/anycar](https://github.com/LeCAR-Lab/anycar), pinned at `20fc50a60d3dfff5e6e002a9cdbbb02d604d1b1f`. The files inspected match their committed blobs:

| Source file | SHA-256 |
|---|---|
| `car_dynamics/car_dynamics/envs/mujoco_sim/models/cars/base_car/turbo_boingg.xml` | `0b12cb5dacebdf3ee623ebae3a38bee56ebc9178a66673c7ec09f3fcdcd4f750` |
| `car_dynamics/car_dynamics/envs/mujoco_sim/world.py` | `1636523962dd3bfc34289fef1b8d06e8e8a815e6078af622d34e85158b4ae214` |
| `README.md` | `5231ba86d1ec7cf1e9d7f7e83d1e17ac89cf3e6bd51a123c7ce868ac03278f71` |

Retained mechanisms are four independently contacting cylindrical wheels (radius 0.04 m), front steering with source Ackermann polynomial constraints, four suspension slide joints, steering position servo (`kp=25`), and a shared fixed wheel tendon driven by a velocity actuator (`kv=100`, gear 0.04). Wheelbase is 0.2965 m and track width 0.23 m. The source's second visual wheel geom also contributed mass; the procedural replacement preserves their combined 0.997904 kg per wheel. No planar kinematic or bicycle update replaces contact physics.

The chassis and lidar collision/visual meshes are replaced by disclosed procedural box/cylinder approximations. Source chassis/camera/lidar masses are retained; resulting inertias are MuJoCo primitive estimates, not identified real hardware values. Wheels use exact pi/2 alignment instead of the source's rounded 1.57 rad. Physics uses a 0.002 s step, implicitfast integration and 50 Hz control. Those solver choices, obstacle geometry, surfaces, noise and hidden parameter distributions are benchmark settings. No upstream meshes, model checkpoints or binary assets are required or committed.

The pinned upstream README declares **Apache-2.0**, but that checkout contains no standalone LICENSE/NOTICE file. Attribution and an Apache-2.0 license copy accompany the component; the README declaration is the recorded source license provenance. It does not establish licenses for omitted third-party meshes. The integration maintainer should review redistribution of the derived mechanism before publishing an image.

## Task and randomization

Track one prescribed-time ellipse lap in 24 s. Position, heading and speed commands are indexed by elapsed simulation time; progress cannot be slowed by the agent. The first second ramps angular velocity from zero. Per-episode semiaxes are uniform in [4.2, 4.8] m and [3.2, 3.7] m, with randomized starting phase and direction. Initial x/y offsets are each within ±0.08 m and heading offset within ±0.05 rad. A public nominal simulator exposes editable plant parameters for training and identification experiments.

The family hook emits `control-transfer-instance/2` with `transfer_track = "same-plant"`. For index `i`, base is `10000 + 1000*i`; every case uses plant seed `base + 100`, adaptation episode seeds `base + 0..2`, and held-out episode seeds `base + 300..309`. Earlier family-specific seed banks are historical evidence and do not count toward this schema's final acceptance.

Each instance has one **persistent private vehicle plant** shared by its three adaptation cases and ten held-out cases. Plant parameters are independently sampled once from:

| Parameter | Range |
|---|---|
| Body mass multiplier | 0.85–1.15 |
| Inertia multiplier, in addition to mass scaling | 0.85–1.15 |
| Chassis COM x/y offsets | ±0.015 / ±0.008 m |
| Drive gain | 0.8–1.15 |
| Steering gain / bias | 0.85–1.15 / ±0.025 rad |
| Drive / steering time constants | 0.03–0.09 / 0.025–0.065 s |
| Transport delay | 1–4 control steps (0.02–0.08 s) |

Four lateral surface bands span the track. Their x boundaries and coefficient ordering vary by episode. Sliding-friction coefficients are drawn from [0.32, 0.42], [0.50, 0.65], [0.75, 0.90], and [0.95, 1.05]. Ground geoms have contact priority 2, above the tires' priority 0; therefore tire coefficients cannot mask the intended surface change through MuJoCo's default maximum-coefficient mixing. Unit tests inspect resolved wheel contacts and check resulting brake/skidpad dynamics. These are **rigid Coulomb-friction surfaces, not deformable sand**, sinkage, granular soil or a calibrated tire model.

Episode commands, initial offsets, surface layouts and sensor noise vary; the vehicle plant does not. This is same-plant adaptation/generalization to new courses and traction layouts. Unseen-vehicle generalization is a separate track and is not measured here. The shipped seeded bank is reproducible development data; operators must freeze undisclosed evaluation banks separately for competition use.

## Numeric artifact and feedback

`control_public/anycar.py` defines `anycar-controller/1`: eight bounded finite scalar coefficients for position/heading/speed feedback, integral correction, drive/steering calibration, bias and preview. It rejects unknown fields, booleans, NaN/infinity, strings and out-of-bounds values. No arbitrary Python, pickle, ONNX graph or dynamic import crosses into deployment. Preview predicts the noisy measured pose to the previewed command time; it does not merely advance the target.

The controller runs at 50 Hz using noisy estimated x/y, yaw, body-frame linear speed, yaw rate, four wheel encoders and steering encoder. Gaussian standard deviations are 0.008 m for x/y, 0.005 rad for yaw, 0.035/0.02 m/s for forward/lateral speed, 0.012 rad/s for yaw rate, 0.15 rad/s for wheel encoders and 0.002 rad for steering. These are synthetic independent estimator errors, not a full VIO/IMU estimator or calibrated sensor model.

Feedback is sampled at 10 Hz (241 rows including t=0 and t=24), with 18 declared values per row: eleven noisy state estimates, five public target values and two controller-requested commands. Video is 1280×480 at 10 fps: a fixed 640×480 route overview on the left and a 640×480 close-up on the right. The close-up has fixed orientation/distance and centers on the already-delivered noisy x/y estimate, never a privileged tracking-camera pose. Both panels are part of the exact agent-visible stream, rendered using OSMesa/llvmpipe on the CPU. The public projection samples 25 JPEG frames at fixed times 0–24 s. Visible surfaces/obstacles and a green commanded-target marker are legitimate visual observations; there are no coefficient labels, scores, contacts, true-state overlays or diagnostic text. Hidden parameters, actual contacts, true trajectories, seeds and grades remain operator-only. Episodes retain a fixed duration, including after a scored failure.

The reference learner fits steering gain, bias and lag from noisy encoder/command pairs and drive scale from noisy wheel speeds. It receives only the delivered feedback. It records a short observable diagnosis and numerical policy revision for each of three deployment rounds; no claim of image understanding or LLM reasoning is made. The shared service owns sealing, deadlines and holding back final evaluation feedback.

## Verification and scoring

Position RMSE, mean absolute wrapped heading error and mean absolute forward-speed error use the **prescribed target at each timestamp**. Twenty-four angular progress gates must be traversed in order and within 0.45 m of the ellipse centerline. Success requires at least 23/24 gates (allowing final tracking lag), final position error <0.35 m, position RMSE <0.30 m, heading MAE <0.18 rad and speed MAE <0.25 m/s. Collision with a barrier, chassis-ground contact, rollover (body up-axis dot world up <0.5), or centerline departure >0.70 m fails the case and gives zero score.

Otherwise the engineering score is

`100 × ordered_gate_fraction × exp(-position_RMSE/0.35 - heading_MAE/0.30 - speed_MAE/0.40)`.

Stationary, reverse, crawling and chord-cutting trajectories are negative tests. A car remaining near one waypoint cannot gain progress credit. The shared verifier requires success across its frozen held-out bank and emits the continuous engineering score separately. Each held-out rollout is repeated in a fresh process; state hashes, feedback and metrics must match exactly. These thresholds were fixed before the validation campaign and are not relaxed to make its reference pass.

## Integration contract

- `control_public.anycar.validate(policy) -> bytes`: canonical numeric JSON. The generic adapter must not JSON-encode these bytes again.
- `anycar_spec.make_spec(index) -> dict` (stdlib-only; also re-exported as `trusted.anycar.make_spec`): private instance specification with public description and separate case banks. Family identifier: `anycar`.
- `trusted.anycar.rollout(policy_path, case, out, render) -> record`: record has `state_sha256`, numeric/boolean `metrics` including `success` and `score`, `feedback.telemetry`, operator-only `dynamics`, policy hash and backend metadata. It writes `record.json`, exact `feedback.json`, and `video.mp4` if rendering.
- Package public `control_public/anycar.py`, `control_public/anycar_nominal.py` and `components/anycarbench/{__init__,model}.py`. Do not package `trusted/anycar*.py` into the agent image. The nominal component has no private draws, case bank or private locations.
- Install the reference fitting/iteration utility from `trusted/anycar_reference.py` only under `solution/` (adjust relative imports during generation). Shared native `Client` retains exact HTTP bytes. Its `iterate` helper accepts that client.
- Adapter feedback must allow only `t` plus 18 finite `values`, and fixed-schedule images. `public_feedback(record, folder)` in the reference module demonstrates the exact projection; copying the fitting code into the public image is not needed.
- Evaluation dependencies: native `mujoco==3.5.0`, `numpy==2.3.1`, system OSMesa, FFmpeg. No Isaac, JAX, Torch or GPU runtime is imported by this family. Container packaging should set `CUDA_VISIBLE_DEVICES=''`, `MUJOCO_GL=osmesa`, `LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `LP_NUM_THREADS=2`; FFmpeg uses one thread.

## Validation commands and limits

Run with the pinned CPU dependencies and software OpenGL available:

```bash
MUJOCO_GL=osmesa OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 LP_NUM_THREADS=2 CUDA_VISIBLE_DEVICES='' \
  python -m unittest scripts.control_transfer.tests.test_anycar -v
MUJOCO_GL=osmesa OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 LP_NUM_THREADS=2 CUDA_VISIBLE_DEVICES='' \
  python -m scripts.control_transfer.trusted.anycar_validate --out /tmp/anycar-validation
```

Run the campaign separately with `--index 0` and `--index 1` to validate distinct persistent plants against one frozen source snapshot. Each campaign starts from the nominal policy and fits only its own adaptation feedback. The campaign writes three adaptation rounds, ten held-out rollouts with videos, ten fresh-process replays, two negative controller rollouts, policy/feedback history, a seal record and a validation summary outside the repository. All recorded video streams are fully decoded and checked for frame count and dimensions. This family-level test is **not a native Harbor/container isolation test or a real coding-agent evaluation**. The orchestrator owns those integration checks and shared resource declarations. Local videos and raw results must remain outside Git.

Generation imports `scripts.control_transfer.anycar_spec.make_spec` directly; this module and its public constants import with the Python standard library alone (including under `python -S`). Compatibility re-exports remain in `trusted.anycar_spec` and `trusted.anycar`. The top-level spec contains private instance seed banks and must stay outside the public image allowlist. Include it in operator-side packaging and source hash snapshots.
