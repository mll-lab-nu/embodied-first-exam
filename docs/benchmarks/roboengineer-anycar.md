# roboEngineer — AnyCar multi-surface tracking

> roboEngineer task names: [roboengineer.md](roboengineer.md) (the package names of #329 used on this page, `control-transfer-*` / `quadrotor-landing-*`, map to `roboengineer-*` in `scripts/roboengineer/exported.toml`).

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

Feedback is sampled at 10 Hz (241 rows including t=0 and t=24), with 18 declared values per row: eleven noisy state estimates, five public target values and two controller-requested commands. Video is 1280×480 at 10 fps: a fixed 640×480 route overview on the left and a 640×480 close-up on the right. The close-up has fixed orientation/distance and centers on the already-delivered noisy x/y estimate, never a privileged tracking-camera pose. Both panels are part of the exact agent-visible stream, rendered using OSMesa/llvmpipe on the CPU. The public projection samples 25 JPEG frames at fixed times 0–24 s. Visible surfaces/obstacles and the public commanded reference centerline are legitimate visual observations (archived earlier videos retain their target dot); there are no coefficient labels, scores, contacts, true-state overlays or diagnostic text. Hidden parameters, actual contacts, true trajectories, seeds and grades remain operator-only. Episodes retain a fixed duration, including after a scored failure.

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
- Preserve the public namespace under `/app/scripts/control_transfer/`: allowlist `control_public/anycar.py`, `control_public/anycar_nominal.py` and `components/anycarbench/{__init__,model,tracks}.py` and `components/anycarbench/circuits.json`, with empty package initializers or Python namespace packages. Do not package `trusted/anycar*.py` into the agent image. The nominal component has no private draws, case bank or private locations.
- Supported nominal training command (working directory `/app`): `python -m scripts.control_transfer.control_public.anycar_nominal --out /app/output/nominal`. Optional `--policy /app/output/policy.json` loads a validated numeric controller. The output directory must be new; outputs are `nominal.npz` and canonical `policy.json`. The parent namespace makes the relative `..components.anycarbench.model` import resolve entirely within the public allowlist.
- The duplicated `/app/control_public` alias also supports `python -m control_public.anycar_nominal`: an explicit package-name branch imports the same namespaced public components. No trusted import or exception-catching fallback is used.
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

## Native integration acceptance

Both native Harbor development banks pass 10/10 held-out cases after three independent adaptation rounds, with mean engineering scores 73.2063 and 72.8721; both no-submission controls score zero. Resource enforcement is enabled and every held-out case has an exact fresh-process CPU replay. Native delivery preserves the 1280×480 dual-panel stream. All delivered feedback bytes and videos are independently audited. These are scripted reference checks, not coding-agent scores. The [integration record](roboengineer-validation.md) documents the verifier build fix, bounded isolation probes, archive identity and remaining gates.

## Historical circuits and zigzag (circuit-sector/1)

The public circuit catalog pins [F1DB](https://github.com/f1db/f1db) at `7cf634e8e0dadd6d3bfdbbe880e34f8cae5698fa`, selecting race layouts dated through 2026-10-13. It inventories **78 historical World Championship venues and 160 layout versions**, including the Indianapolis championship races. **159 source layouts are runnable**, and every venue has a runnable raced layout. The first Buenos Aires layout (`buenos-aires-1`) has disjoint, overlapping source strokes and fails closed with an explicit unavailable reason; no substitute geometry is silently inserted. The latest raced layout resolves from a venue alias such as `monaco`; a layout ID such as `monaco-2` selects a particular historical version. `zigzag` is a separate synthetic closed slalom course, not attributed to a real circuit.

These are **planar schematic approximations**, derived from attributed CC BY4.0 SVG paths, not GPS-surveyed replicas or homologated F1 tracks. Source transforms are applied, tiny source gaps are recorded, paths are resampled at1024 points and Gaussian-smoothed at0.2% of perimeter. Each SVG path/hash, raced years, source length and conversion gap metadata remain in `circuits.json`; full license is `LICENSE.f1db`, attribution in `NOTICE`. Source start locations and path traversal ordering are retained as schematic route order, not certified F1 start-line/direction data. Elevation, banked turns and grade-separated bridges are not reconstructed; Suzuka's crossing is planar. Crossovers suppress nearby barriers, and ordered gates prevent jumping branches for credit.

Routes scale uniformly, preserving aspect ratio. Scale is chosen from the sharpest discretized curvature (0.85/m target) and an80m minimum perimeter, keeping interpolated curvature below1.2/m in all available layouts. Actual metric scale varies by layout and is recorded; this is not one fixed1:10 collection. The procedural RC vehicle dimensions/physics do not change. Asphalt appearance marks friction-region boundaries without exposing coefficients. The overview fits the whole route; the close-up still follows only delivered noisy x/y. No true-state/score/coefficient overlays are added.

The existing ellipse `make_spec(index)` remains unchanged. New **opt-in** stdlib hook `make_circuit_spec(index, track_id)` adds a resolved public route ID and `task_variant=circuit-sector/1`, with the existing persistent-plant banks and three feedback rounds. The shared generator registers it separately as `anycar-circuit-v1-<layout>`; all circuit tasks remain development-only with `oracle="none"`. Circuit feedback remains241 rows and25 images over24s. Each episode traverses a prescribed-time **sector**, not a full lap, at0.85m/s with a1s start ramp; start fraction varies by episode seed. Friction boundaries span the sector's x extent. Full-lap nominal training is separately available. Ordered oriented gates, corridor distance and time-indexed position/heading/speed replace ellipse-specific angle/radius scoring; safety and accuracy thresholds stay unchanged. A route's task geometry is public; plant, coefficients, seed bank and scorer remain private.

```bash
python -m scripts.control_transfer.control_public.anycar_nominal --list-tracks
python -m control_public.anycar_nominal --track zigzag --out /app/output/zigzag
python -m control_public.anycar_nominal --track monaco --full-lap --out /app/output/monaco-lap
# Operator-only CPU evaluator preview (never package this module publicly):
python -m scripts.control_transfer.trusted.anycar --track suzuka --policy policy.json --out preview
```

Public allowlist adds `components/anycarbench/tracks.py`, `circuits.json`, `LICENSE.f1db` and `NOTICE`; no converter or private bank belongs in the agent image. Runtime requires no extra dependency beyond existing NumPy/MuJoCo. Offline conversion only uses PyYAML, svgpathtools1.8.0 and svgwrite1.4.3:

```bash
python -m scripts.control_transfer.trusted.anycar_build_tracks --source <pinned-f1db-checkout> --output scripts/control_transfer/components/anycarbench/circuits.json
python -m unittest scripts.control_transfer.tests.test_anycar scripts.control_transfer.tests.test_anycar_tracks -v
python -m scripts.control_transfer.trusted.anycar_circuits_validate --out <fresh-external-directory>
```

The all-venue validation executes one bend-focused24s CPU rollout per latest raced venue layout plus zigzag, alternating two plants, using the unadapted public nominal controller. Four videos are replayed and exact feedback preserved. This is broad implementation smoke coverage, **not** an all-layout/full-lap or multi-round agent acceptance result. The original two-instance ellipse evidence is historical and is never relabelled as circuit evaluation.

## Generating optional circuit tasks

Existing control-transfer task identities and ellipse instances are preserved.
The catalog and nominal trainer support all 159 runnable historical layouts plus zigzag.
Create self-contained circuit tasks on demand, two independent plant instances per selected route:

```bash
python3 -S -m scripts.control_transfer.gen_tasks list-circuits
python3 -S -m scripts.control_transfer.gen_tasks render --circuit zigzag --circuit monaco --output-root /tmp/circuit-tasks
python3 -S -m scripts.control_transfer.gen_tasks check --circuit zigzag --circuit monaco --output-root /tmp/circuit-tasks
# All runnable historical layout versions, plus zigzag: 320 tasks, several GB of standalone copies.
python3 -S -m scripts.control_transfer.gen_tasks render --all-circuits --output-root /tmp/all-circuit-tasks
```

An explicit layout selects that historical version; a venue alias resolves to its latest raced
available layout in the pinned catalog. Unknown or unavailable layouts fail before task writes.
The default generator check also covers optional circuit tasks materialized in its output directory.
Refresh `tasks/dataset.toml` with Harbor if optional tasks are added under repository `tasks/`.
The trusted adapter passes the route ID unchanged; only public geometry/nominal modules and license
attribution enter the agent package. Converter, evaluator, plant draws and case banks stay private.
Current circuit evidence is local CPU sector smoke, not native Harbor circuit acceptance.


### Compact 30-second laps (`circuit-compact-lap/3`)

The user-approved compact revision is a separate task: `make_circuit_spec(index,
track_id, revision="circuit-compact-lap/3")`. Each of the 160 runnable routes has a
45 m derived layout, a target finish at 28 s and a strict 30 s simulation horizon.
The two seconds after the target finish allow tracking lag. Full ordered-gate,
tracking and safety thresholds are unchanged. The unchanged data-only controller
runs at 50 Hz, CPU MuJoCo at 500 Hz; output contains exactly 301 noisy 10 Hz rows
and (when rendered) 301 video frames at 10 fps. Wall time is separate from the
30-second simulated episode.

These are **compact F1-inspired layouts**, not faithful scaled circuit outlines.
The offline builder uses periodic Gaussian smoothing, widens the minor principal
axis when needed to limit aspect ratio to 2, resamples to 512 points and normalizes
to 45 m. It selects the first preset smoothing level whose interpolated curvature
is at most 0.8/m. This can heavily simplify corners and remove crossovers. Every
layout records smoothing sigma and widening factor in public metadata. The car's
wheelbase, mass, steering, contact, controller bounds and hidden dynamics draws
are unchanged. Existing sector and long-lap layouts/specs remain unchanged.

New public allowlist asset: `components/anycarbench/compact_routes.json` alongside
`tracks.py` and `circuits.json`. The operator-only offline builder is
`trusted/anycar_compact_routes.py`; rebuild with `--out PATH`. The public trainer
supports `--track NAME --compact-30s`; the trusted evaluator uses the same flags.
Cases set `full_lap=true, route_revision="compact-30s/1"`. Root owns separate
registration, sampling, and task budgets; the stdlib `compact_route_budget(name)`
and public spec report the fixed horizon/row/frame bounds. No held-out data was
used to tune a policy or relax scoring thresholds.


### Complete F1 laps (`circuit-lap/2`)

`make_circuit_spec(index, track_id, revision="circuit-lap/2")` generates complete-lap cases for every
available historical layout. The default `revision="circuit-sector/1"` preserves the
legacy sector spec and bank exactly. The previous 24-second sector evidence remains
sector evidence. Legacy ellipse instances and explicit CLI sector previews are
unchanged. Circuit geometry retains uniform downscaling per layout and the
steering-feasibility constraint; shrinking every circuit to a fixed small length
would make sharp corners infeasible with the retained RC wheelbase and steering.

The target travels at 0.85 m/s after a one-second speed ramp. The CPU evaluator
runs for `ceil_50Hz(length / 0.85 + 2.5)` seconds, including a two-second bounded
finish allowance. All forward gate crossings, at most 0.5 m apart, must occur in
order within 0.45 m of their centers; the final gate is the start/finish line.
Success requires every gate plus the existing tracking and safety thresholds.
`lap_time_s` is interpolated from the actual final forward crossing, or null if
unfinished. This is prescribed-speed tracking, not fastest-lap optimization.
Traction bands span the full circuit. Telemetry remains noisy at 10 Hz and video
remains the exact 10 fps dual-view stream; neither contains private metrics.

Operator CLI: `python -m scripts.control_transfer.trusted.anycar --track silverstone
--full-lap --policy POLICY --out FRESH_DIRECTORY` (one shell line). Public training
uses `python -m scripts.control_transfer.control_public.anycar_nominal --track
silverstone --full-lap --out FRESH_DIRECTORY`.

The stdlib-only `route_metadata(name)` / `route_metadata_catalog()` helpers in
`components.anycarbench.tracks` load `route_lengths.json` without NumPy/MuJoCo.
The frozen metadata covers 159 runnable historical layouts plus zigzag and binds
to the existing circuit catalog SHA-256. Every recorded length and horizon is
checked against the unchanged physics Route implementation. Rebuild offline with
`python -m scripts.control_transfer.trusted.anycar_route_metadata --out PATH`.
The longest full-lap horizon is Valencia-1: 3,878.76 seconds (193,938 control
steps, 3,294.8199857283616 m). The unavailable Buenos Aires layout stays excluded.
Copy `route_lengths.json` alongside `tracks.py` in explicit allowlists. Register
lap tasks separately from `anycar-circuit-v1`; do not regenerate sector tasks as
laps. Sector and ellipse records retain their original metric fields when
`full_lap` is absent. Sampling, budgets and registry changes remain root-owned.


`route_budget(name)` provides a stdlib-only conservative simulation horizon
bound (`ceil(frozen_horizon_s) + 1`), control-step, 10 Hz telemetry-row and 10 fps
decoded-frame bounds. It covers all 160 runnable routes, including old layouts.
The lap public spec includes this `runtime_budget`; sectors are unchanged. The
trusted runtime still computes exact horizon from the NumPy Route. Root must use
the frozen operator instance's budget, never a submitted policy or request.

The helper's wall-time **estimate**, `2 * horizon_bound_s + 60`, is a CPU OSMesa
planning estimate, not a hardware-independent upper bound. Maximum Valencia-1
bounds are 3,880 simulation seconds, 194,000 control steps, 38,801 telemetry rows
and video frames, and an estimated 7,820 wall seconds per rendered case.
Three such feedback cases estimate 23,460 seconds; nine across three rounds
estimate 70,380 seconds before agent training overhead. These exceed the existing
14,400-second agent cap. Root owns protocol exceptions and separate lap-family
budgets; this helper does not raise or override any cap. Final held-out work has
its own verifier budget. Root's fixed 128 whole-video samples must retain the
first/last decoded-frame indices, all telemetry rows, and the full MP4, while
leaving the legacy sampler unchanged.

Integration must select `circuit-lap/2`, preserve variable-length telemetry/video,
and size worker deadlines, response limits and sampled-image budgets for complete
laps. Do not truncate a lap to the legacy 241 telemetry rows/25 images or label
legacy sector results as lap results. Shared generator/runtime changes belong to
the orchestrator; this hook remains standard-library-only under `python -S`.


## Full-lap task generation and runtime contract

The shared registry keeps `anycar-circuit-v1-<layout>` as 24-second sectors and registers
`anycar-circuit-lap-v2-<layout>` separately. Default generation includes both plants for
Silverstone-8 and Monaco-6. All 159 runnable historical layouts plus zigzag can be selected:

```bash
python3 -S -m scripts.control_transfer.gen_tasks render --lap-circuit suzuka
python3 -S -m scripts.control_transfer.gen_tasks render --all-lap-circuits --output-root /operator/full-lap-tasks
python3 -S -m scripts.control_transfer.gen_tasks check --all-lap-circuits --output-root /operator/full-lap-tasks
```

The private CPU evaluator keeps the full 10 fps, 1280×480 video and every 10 Hz noisy
telemetry row. The shared adapter delivers up to 128 equally spread decoded-frame indices,
including the first and last frame, with their actual timestamps. It does not return only
an initial clip. Full operator recordings and exact delivered response/JPEG bytes are retained;
no scores, true state, contacts or hidden parameters enter adaptation feedback.

The pinned catalog's simulated full-lap horizons range from 96.62 to 3878.76 seconds.
This is a **separate 129600-second (36-hour) agent-budget track**, allowing three rounds
of three long CPU-rendered laps plus training/analysis time. Existing task budgets do not
change. These are declared maximum limits, not measured completion times or a cloud-cost
estimate; compare results only within the same budget. Worker rendering allows
`max(600, ceil(3*horizon+180))` wall seconds; non-render replay and FFmpeg extraction have
separate bounded limits. The private collector allows an in-flight round to drain, then
ten rendered cases and ten fresh-process replays. Client request timeouts and Harbor's
collection timeout are generated from the same frozen public duration. None is supplied by
the submitted controller. Actual deployment hardware must still validate these estimates.

Full-lap tasks remain `oracle="none"`. Three local positive laps and a video replay do not
establish all-layout, multi-round, native Harbor or coding-agent acceptance. The broader
catalog remains scaled planar schematics, including flattened crossovers; these are not
surveyed F1 circuits or competitive racing lap times.
### F1TENTH-style visual bodywork

The car uses original procedural GT-style RC bodywork: beveled shell, dark glazing,
roof, rear wing, splitter, lamps, mirrors and spoke wheels. This is an
F1TENTH-style visual profile, not a licensed commercial chassis asset or a new
calibration. Every added visual geom has zero mass and disabled collisions.
Original chassis/sensor collision geometry remains present but invisible; the
AnyCar mass, inertia, suspension, wheel contacts, steering and actuator model are
retained. Rendered bodywork is cosmetic; collision checking uses the retained
physical primitives. No additional external assets or packages are required.


### Compact-lap task generation and runtime contract

The registry name is `anycar-circuit-compact-v3-<layout>`. Default generation includes
Silverstone-8 and Monaco-6, each with two persistent plants. The full 160-route catalog is
available without changing either earlier circuit revision:

```bash
python3 -S -m scripts.control_transfer.gen_tasks render --compact-circuit suzuka
python3 -S -m scripts.control_transfer.gen_tasks render --all-compact-circuits --output-root /operator/compact-tasks
python3 -S -m scripts.control_transfer.gen_tasks check --all-compact-circuits --output-root /operator/compact-tasks
```

Public geometry is precomputed in `compact_routes.json`; the offline builder remains
operator-only. Each task declares its smoothing and minor-axis widening, 45 m route,
28 s target lap and hard 30 s horizon. These are **F1-inspired approximations, not exact
scaled outlines**. Strong smoothing may reduce a complex circuit to a rounded loop and
remove crossovers. The nominal command is
`python -m scripts.control_transfer.control_public.anycar_nominal --track silverstone --compact-30s --out /app/output/nominal`.

The numeric controller ABI, vehicle dynamics, hidden fixed-plant parameters, safety
predicates and accuracy score are unchanged. The car must cross every ordered forward gate
and the finish within the episode; actual interpolated finish time is retained privately.
Three adaptation cases are reused over up to three rounds, followed by ten private held-out
cases. The public response contains all 301 noisy rows and 31 images at 0, 1, …, 30 s.
Full 1280×480 operator video retains 301 frames at 10 fps. Images and noisy trajectories
carry no scores, seeds, contact flags or true-state fields.

Compact tasks use the ordinary 14400-second agent limit. Operator-owned wall deadlines are
300 s for a rendered case, 120 s for a non-rendered replay and 60 s for extraction;
a three-case request allows 1200 s. Final collection allows 5520 s to drain an in-flight
request and execute ten rendered/replayed cases, with 60 s extra in Harbor's collection
wrapper. These are limits, not measured hardware guarantees, and do not extend the
agent's cutoff. The 36-hour exception remains exclusive to `circuit-lap/2`.

The worker's frozen default controller passed one adaptation-only case per compact route
(160/160), with finish times 28.0147–28.1447 s and all four traction surfaces. This broad
smoke sweep is not a held-out model comparison. Compact tasks remain `oracle="none"`
until native multi-round acceptance and reference solvability are established separately.

### Public reference-line visual revision

The diagnostic video renders a continuous cyan reference centerline in both
views, replacing the moving target dot. Its geometry is derived only from the
public commanded route (or ellipse parameters), never from hidden robot state.
The line is a rendering overlay and does not change physics or noisy telemetry.
Previous video artifacts remain unchanged; this visual revision produces new
video bytes. Time-indexed target values remain available in noisy-feedback rows.


Generated AnyCar packages now declare `observation_revision=anycar-reference-line/1`.
This changes image observations; physical trajectories, noisy numeric feedback, policies,
scoring and task geometry are unchanged. The line is computed from the public commanded
route, with 257 points covering the loop, and drawn in both panels. Historical native
reference results predate this image revision; they are not new visual-agent evaluations.

### Dashed line and traffic-cone appearance

The latest renderer uses a dashed cyan commanded centerline in both panels.
Tapered orange-and-white cone meshes have dark square bases. These visual geoms
have zero mass and disabled collisions. The original fixed barrier collision
cylinders remain at their original positions, invisible, preserving contact
dynamics. Dash spacing depends only on public route arc length. Earlier video
artifacts are retained under their original observation revision.

Generated packages now explicitly declare `anycar-dashed-cones/1`. The preceding
`anycar-reference-line/1` denotes the continuous-line recordings. Both are image
revisions: numeric feedback, case banks, vehicle physics and scoring are unchanged.
The renderer reserves room for the complete model plus the public dash overlay,
including the largest legacy route. Native/model acceptance of this appearance
revision is still pending.

### Drift to Park (`drift-park/1`)

The separate `anycar-drift` family starts an RC car on a straight approach, follows
ordered gates around a 180-degree U-bend, then requires a sideways slide into a
parallel-parking bay bounded by two stationary cars. A physical curb bounds its
outer edge. Parked cars have solid collision envelopes, and cones mark the approach.
The nominal U-bend radius is 1.5 m. The nominal bay is 1.20 × 0.65 m, centered at
(-3.0, 2.05) m; target yaw is pi. The car collision envelope used for bay containment
is 0.49 × 0.27 m. All geometry and commands are public.

This task retains the existing free-body chassis, wheel contact, suspension,
Ackermann steering and driven-wheel mechanism. It adds a **rear-wheel handbrake**:
MuJoCo joint friction applies bounded opposing torque at both rear spin joints.
It never sets lateral velocity, yaw, friction coefficients based on phase, or
robot position to create a drift. Torque strength, surface friction and vehicle
response vary privately; this is a rigid Coulomb-contact approximation, not a
calibrated pneumatic-tire drift model. A real handbrake brake curve and tire
thermal/load/slip behavior are outside this task's claims.

Episodes are 16 simulated seconds. The trusted monitor observes each 2 ms physics
step. Completion requires ordered U-route gates, then sideslip near the parking
bay: body lateral speed >0.2 m/s, total planar speed >0.6 m/s, and sideslip angle
>10 degrees, sustained at least 0.15 s with ≥0.06 m accumulated lateral sliding.
A slow conventional parking maneuver cannot satisfy that requirement. Success
also requires the entire car envelope inside the bay, longitudinal error <0.18 m,
lateral error <0.12 m, heading error <0.14 rad, speed <0.08 m/s and yaw rate
<0.1 rad/s for at least 0.5 s. Any collision, rollover, chassis-ground contact or
approach departure fails. Successful quality is
`100 * exp(-position_error/0.25 - heading_error/0.3)`; incomplete or unsafe is zero.
These thresholds are fixed task definitions, not real-vehicle damage limits.

The data-only `anycar-drift-controller/1` policy contains bounded approach,
steering-pulse, countersteering, brake and stop gains. A controller follows the
public route using noisy pose estimates, initiates the slide, countersteers and
brakes; it never observes private gate/drift/success flags. Nominal training is
`python -m scripts.control_transfer.control_public.anycar_drift_nominal --out DIR`.
Public feedback is only course geometry, noisy 10 Hz car telemetry, requested
controls, and the exact 10 fps video (fixed overview plus noisy-position closeup).
Hidden state, seeds, contact events, plant parameters and scores stay private.

`anycar_drift_spec.make_spec(index)` is stdlib-only and uses the standard same-plant
bank with 3 adaptation cases and 10 held-out cases, across 3 bounded feedback rounds.
Vehicle parameters, friction (0.55–0.70) and brake torque (2.5–3.5 Nm per rear
wheel) persist within an instance. Episode randomization varies bay length
(1.15–1.30 m), center x (-3.1 to -2.9 m), center y (2.0–2.1 m), initial lateral
position (±0.02 m), yaw (±0.01 rad) and observation noise. Noise is identical to
the original AnyCar motion/wheel/steering channels.

Integration: root registers `anycar-drift` separately and dispatches validation to
`control_public.anycar_drift.validate` and evaluation to
`trusted.anycar_drift.rollout(policy_path, case, out, render)`. Preserve
`feedback.command`. Public allowlist adds `control_public/anycar_drift{,_nominal}.py`
and `components/anycarbench/drift.py`, with the existing public `model.py`.
Never install the spec, trusted monitor/evaluator or banks in the agent container.
The renderer is family-local; the operator image also needs the existing trusted
AnyCar parameter sampler. Shared registry,
Harbor packaging, budgets and site publication remain integration work owned by root.

The integrated task IDs are `control-transfer-anycar-drift-i{00,01}-standard`.
The shared adapter preserves the public course command and all 161 images at 10 Hz,
including the subsecond drift and final stop. A strict course-field allowlist rejects
hidden fields and non-finite values. Only the nominal controller/model modules are
agent-visible. Both public import paths run without the trusted package.

The frozen nominal controller passes the nominal example but **0/26 randomized
cases** (6 adaptation and 20 held-out across two fixed plants). All 26 complete the
route, 22 satisfy the drift requirement, 12 collide and none hold a valid park.
No tuning used the held-out results. Three family replays and both generated private
package replays match exactly. A 500-step driven comparison also confirms the added
optional scene/substep hooks preserve the original AnyCar state trajectory. The task
remains `oracle=none`; these checks do not establish robust transfer or an LLM score.

## Tight drift parking (drift-park/3)

The separate `anycar-drift-v3` family integrates worker source `16c269a352e5db4e49ce5aa97c610cca15c5ab8d` under versioned module names. The original `anycar-drift` task and ABI /1 remain intact. The new course has a nominal 0.69 × 0.43 m bay for a 0.49 × 0.27 m car and a 1 m approach. It additionally requires a net post-route turn of pi radians within 0.25 rad, with at least 120 degrees accumulated while sliding. Physical rear braking, collision predicates, containment and scoring remain those of the worker's tight-bay revision.

The public entry point `control_public.anycar_drift_v3` accepts bounded numeric ABI /2 and /3. Its legacy constants remain /2; the stdlib spec and nominal trainer default to the /3 policy in `control_public.anycar_drift_feedback`. That controller uses early acceleration, bay-relative initiation, heading/rate preview and countersteering from the declared noisy sensors. No monitor flags or hidden plant parameters are inputs. Both public layouts include `anycar_drift_v3.py`, `anycar_drift_v3_nominal.py` and `anycar_drift_feedback.py`, plus the allowlisted `anycarbench/{model,drift_v3}.py` component. The spec and evaluator remain private.

Generated IDs are `control-transfer-anycar-drift-v3-i{00,01}-standard`. There are three adaptation cases, ten held-out cases and three feedback rounds per persistent plant. The response includes the full public course, including `start_x`, `target_yaw` and the fixed `drift-park/3` revision, all 161 noisy rows and all 161 images at 10 Hz. The 50 fps presentation video is an additional operator replay, not the canonical agent video.

The frozen nominal example scores **64.70**, with no contact and full containment. It turns about 184 degrees, including 129 degrees while sliding, and stops for over seven seconds. However, frozen results are **0/6 adaptation, 1/20 held-out and 1/10 additional nominal-noise trials**; 18 of 20 held-out cases collide. All failures are retained and no fitting occurred after the bank evaluation. A positive nominal clip does not establish robust parking. The family remains `oracle=none`, requires human review, and has no native Harbor or coding-agent result.
