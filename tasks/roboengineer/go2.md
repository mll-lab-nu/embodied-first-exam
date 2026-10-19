# roboEngineer: Unitree Go2 tasks

> roboEngineer task names: [README.md](README.md) (the package names of #329 used on this page, `control-transfer-*` / `quadrotor-landing-*`, map to `roboengineer-*` in `ci_checks/benchmarks/roboengineer/exported.toml`).

This family ports four SPI-Active-inspired objectives to **native CPU MuJoCo**, with NumPy controller inference and **OSMesa software rendering**. It is a new simulator port and benchmark definition, not reproduction of the paper's physical experiments or released trained policies. No upstream Go2 checkpoint is assumed.

## Task definitions

| Family | Commands / cases | Success predicate |
|---|---|---|
| `go2-weave` | Four poles at x = 0.9, 1.9, 2.9, 3.9 m; public predeclared velocity schedule, 20 s; forward command 0.23–0.27 m/s | Pass poles in order on alternating sides with base-center lateral clearance >=0.16 m, no pole or non-foot ground contact, and finish beyond x=4.25 m. |
| `go2-attitude` | Explicit sinusoidal roll amplitude 0.18–0.30 rad and pitch amplitude 0.20–0.35 rad; period 4–6 s; randomized phase; 10 s | After 1 s acquisition: body roll/pitch RMSE <0.08 rad, >=95% of samples with at least three feet supported, final base displacement <0.25 m, no non-foot ground collision. |
| `go2-forward-jump` | Public forward displacement 0.70–1.00 m; 6 s | At least 0.08 s verified flight and 0.07 m rise; >=70% of commanded distance traversed during flight; first-touch and final longitudinal errors <0.15 m; lateral error <0.15 m; final 1 s stable support. |
| `go2-yaw-jump` | Public heading change 110–150 degrees; 6 s | At least 0.08 s verified flight and 0.07 m rise; >=70% of command rotated during flight; first-touch yaw error <0.25 rad, final error <0.18 rad, final base drift <0.25 m; final 1 s stable support. |

Stable jump touchdown requires at least three feet supported, speed <0.25 m/s, angular-rate norm <0.35 rad/s, and absolute roll/pitch <0.22 rad throughout the last second. Scoring uses actual native contact records and unwrapped yaw. A contact dropout without height gain, walking after a hop, or rotating on the ground cannot satisfy the jump gates. Non-foot ground or pole contact, body height below 0.12 m, or absolute roll/pitch above 1.1 rad makes the episode unsafe and scores zero.

Safe task quality is 0–100, capped at 49 when success is false. Attitude quality is `100 exp(-RMSE/0.2)`; weave uses the fraction of correctly passed poles; jump quality uses final target error with scales 0.4 m or 0.7 rad. A jump without qualifying flight scores zero. Binary success remains separate from the continuous quality metric. These thresholds are defined independently of reference-controller performance.

The weave controller receives **no global position, linear velocity, contacts, or collision signal**. It follows a schedule with noisy joint/IMU feedback; global pose is used only by the scorer. This preserves the distinction between predeclared navigation commands and closed-loop low-level stabilization.

## Source fidelity and model provenance

- [SPI-Active project](https://lecar-lab.github.io/spi-active_/), official [source](https://github.com/LeCAR-Lab/SPI-Active/tree/edc07d0b957bce9a430aa5a48b71a266a0a9f635), pinned commit `edc07d0b957bce9a430aa5a48b71a266a0a9f635`.
- [MuJoCo Menagerie Go2](https://github.com/google-deepmind/mujoco_menagerie/tree/0059d4335f8156206f63a35662313385f7ad6d74/unitree_go2), pinned commit `0059d4335f8156206f63a35662313385f7ad6d74`, BSD-3-Clause model derived from Unitree's robot description. Original visual meshes, native inertias, articulated 12-joint geometry and foot/body collision shapes are retained. Assets are prepared outside Git, with a checksum manifest verified at rollout start.

The official `spigym/config/robot/go2/go2.yaml` specifies DFS joint order FL, FR, RL, RR, each hip/thigh/calf. This port maps by **joint name** and discovers each motor's joint transmission rather than assuming array order. Joint limits match the native model. Hip/thigh effort is capped at 23.7 Nm and calf at 35.55 Nm following SPI-Active; Menagerie's 45.43 Nm calf motor limit is deliberately reduced. Rated speeds are 30.1/30.1/20.07 rad/s. A bounded torque-speed approximation reduces motoring torque above half rated speed while retaining braking torque.

SPI-Active's Isaac Gym config uses 200 Hz physics and decimation 4 (50 Hz actions), with representative PD gains 25/0.6 and action scaling 0.25 rad (jump robot config: 0.5 rad). Here physics is 500 Hz with 50 Hz target updates and 500 Hz noisy encoder PD. The numeric artifact specifies gains, bounded radian trajectory offsets and nominal foot-trajectory parameters; it does **not** reinterpret a released neural policy's normalized actions. Menagerie's default joint damping 2 is replaced with 0.05 Nms/rad and friction loss 0, explicitly separating actuator response from joint passive damping. The native elliptic contacts and foot compliance remain MuJoCo's; matching the Isaac contact solver or real Go2 hardware is not claimed.

## Persistent hidden plant

Instances use `control-transfer-instance/2` and `transfer_track="same-plant"`. The operator bank uses `base=10000+index*1000`, fixed `plant_seed=base+100`, adaptation episode seeds `base+[0,1,2]`, and held-out episode seeds `base+300+[0,...,9]`. These seeds never enter public feedback. Legacy bank results are not acceptance evidence for this schema.

One plant is drawn once per instance and reused across all three adaptation cases and ten held-out cases. The cases vary commands, initial yaw (-0.025 to 0.025 rad), initial joint perturbations (±0.004 rad), and measurement noise. Changing the instance changes the plant; this is a separate axis from case randomization.

| Hidden property | Draw |
|---|---|
| Base mass | 0.85–1.15 times native base mass |
| Base COM | independent ±0.012 m offsets |
| Base principal inertia | common 0.85–1.15 multiplier, additionally scaled with base mass |
| Per-motor strength | independent 0.90–1.10 |
| Nonlinear torque saturation | `A tanh(strength * requested / A)`; hip/thigh A=35–70 Nm, calf A=45–90 Nm, repeated by joint type |
| First-order motor time constant | 3–15 ms |
| Foot/ground friction | 0.65–0.95 |
| Persistent joint-angle sensor bias | normal, sigma=0.002 rad |

These are benchmark assumptions motivated by SPI-Active's mass/COM/inertia/motor identification targets, not recovered physical identification estimates. Unlike some upstream training randomizers, hidden motor draws do not change every control step. Fresh sensor noise is drawn from the episode RNG: joint angle 0.003 rad, joint velocity 0.025 rad/s, Euler attitude 0.004 rad, and body gyro 0.01 rad/s.

## Numeric policy and feedback boundary

`control_public/go2.py` implements `validate(policy) -> bytes`: exact schema keys, finite bounded numbers, 12 gains per vector, 17×12 radian trajectory offsets and 12×6 feedback coefficients. No Python code, serialized objects, ONNX graphs or arbitrary array shapes cross into the evaluator. The worker also rejects policy files over 64 KiB. The controller consumes a 30-element sensor vector plus seven public command channels; it never receives `MjModel`, `MjData`, private contacts, seeds or plant parameters.

Public feedback is `{"telemetry": [{"t": ..., "values": [...37 numbers...]}]}` at 20 Hz, plus shared-layer sampled images at 1 Hz. Channel names and units are declared in `make_spec(...)["public"]`. There is no global position/velocity or reward channel. The full 10 fps video, true state trace, contact events, plant values, policy digest and state replay hash are **operator-only** evidence. The shared service must project the exact telemetry/images allowlist and retain exact delivered bytes and per-round artifact versions. Short user-visible observation/change/prediction diagnoses belong to the shared round record; no private chain of thought is required.

`control_public/go2_nominal.py` builds the editable nominal model from a caller-supplied public asset directory. `control_public/go2_train.py` is a runnable nominal CPU training rollout and numeric artifact exporter; it imports no hidden evaluator module and contains no private draw or asset path. Agents may implement their own parameter search or GPU training, exporting the same data-only controller artifact. This family currently supplies an analytic controller and bounded trajectory/feedback parameterization, not an unconstrained neural-network submission ABI.

## Integration hooks (orchestrator-owned packaging)

- `scripts.control_transfer.trusted.go2.make_spec(index=0, task="attitude")`: accepts `weave`, `attitude`, `forward-jump`, `yaw-jump` or their `go2-` prefixes. Returns the shared instance structure with `family`, `name`, `public`, and a bank of 3 adaptation / 10 held-out cases. The shared service owns the three-round budget and seal/cutoff gating.
- `scripts.control_transfer.trusted.go2.validate(policy) -> bytes`: canonical JSON artifact.
- `scripts.control_transfer.trusted.go2.rollout(policy_path, case, out, render=True) -> record`: writes operator `record.json`, `states.json`, and `video.mp4`. The output directory must not already exist.
- Record keys include `state_sha256`, `metrics.success`, `metrics.score`, `feedback.telemetry`, `dynamics`, frame times and runtime provenance. Shared feedback handling must register dimension **37** and image rate **1 Hz**, from full video rate **10 Hz**.
- Shared packaging should copy only the explicitly listed public `control_public/go2*.py` files and prepared nominal Go2 assets into the agent image (only the required MJCF/meshes/license, without upstream README, screenshots or provenance manifests); private `trusted/go2.py`, quadruped evaluation components, private specs and reference evidence remain outside it. Do not make the repository's `components` tree reachable from the public training module.
- Runtime: MuJoCo **3.5.0**, NumPy **2.3.1**, PyOpenGL supplied by MuJoCo, `ffmpeg`, and `libosmesa6`; no torch, CUDA, Isaac or GPU inference runtime. Set `MUJOCO_GL=osmesa`, `LIBGL_ALWAYS_SOFTWARE=1`, `LP_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=1`; omit all GPU device reservations. Assets use `CONTROL_ASSETS/go2` or operator `GO2_ASSET_DIR`.

## Reproduce local checks

Prepare the pinned source outside the source repository, then prepare assets at build time (never during verification):

```bash
python -m scripts.control_transfer.components.quadrupedbench.assets --out /path/to/control-assets/go2
export GO2_ASSET_DIR=/path/to/control-assets/go2
export MUJOCO_GL=osmesa LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES=''
export OPENBLAS_NUM_THREADS=1 LP_NUM_THREADS=4
python -m scripts.control_transfer.control_public.go2_train --assets "$GO2_ASSET_DIR" --task attitude --out /tmp/go2-nominal
python -m scripts.control_transfer.components.quadrupedbench.simulation --policy /path/to/policy.json --case /path/to/private-case.json --out /tmp/go2-evaluation
```

Native Harbor packaging, service admission/egress and final verifier isolation are shared integration work. Local successful rollouts and unit tests do not establish that container boundary. Development seed banks in the source are reproducible fixtures; a competition's private bank must be frozen separately before agent runs.

## Reference readiness and validation limits

The analytic reference artifacts are operator-only (each task's `solution/reference.py` deploys the frozen one). The pinned SPI-Active Git tree contains no `.pt`, `.pth`, `.onnx`, `.jit` or `.ckpt` policy files; its downstream recipes describe training rather than shipping a portable expert. No GPU training or RL convergence is claimed here.

Local native CPU validation covers ten held-out cases per task, each replayed in a fresh process with identical state and noisy-feedback hashes, plus one physically unpowered no-op per task and one decoded software-rendered video per task. The actual OpenGL renderer is checked for software rasterization. Boundary tests additionally reject nonfinite/oversized/malformed artifacts and reject ground-spinning, walking-to-target, and hop-then-ground-motion substitutes for jumping.

**Reference readiness is task-specific:** attitude tracking has a positive analytic reference; weave and both jump controllers remain partial candidates and must not be labeled `oracle = "full"` or released as established-solvable tasks. The weave candidate still collides with poles and can miss the finish gate. Forward-jump trials achieve flight but undershoot first-touch displacement and fail stable landing. Yaw-jump trials achieve airborne rotation but retain contact, final-heading, drift or settling failures. The next step is task-specific trajectory optimization or learned control with the same observation boundary, followed by a new frozen held-out evaluation; success thresholds must not be relaxed to fit these candidates.

These local checks validate the family physics, data interface and replay behavior. Completed native service integration and bounded container-boundary probes are documented in the acceptance section below. Reference solvability for the three partial tasks and actual coding-agent evaluations remain outstanding. Integration evidence and full per-case media are retained outside Git by the orchestrator.

Archived MuJoCo 3.8.0 schema-v2 local validation (instance 0, same-plant bank) used the unchanged frozen references: attitude 10/10 successes, mean score 91.06475; weave 0/10, mean 0; forward jump 0/10, mean 0; yaw jump 0/10, mean 9.8. All 40 fresh-process replays matched state, feedback and metrics; four no-op scores were zero and four OSMesa videos fully decoded. These results supersede the legacy seed-bank evidence for acceptance, but do not establish shared Harbor isolation or solvability of the three partial families.

## Public training allowlist and private evaluation materials

Public nominal files: `control_public/go2_data.py`, `control_public/go2.py`, `control_public/go2_nominal.py`, and `control_public/go2_train.py` (plus empty package initializers only as needed). Public nominal assets: pinned `go2.xml`, its referenced mesh files under `assets/`, and `LICENSE`. Do not copy upstream README, screenshots, scene/MJX variants, or `asset-manifest.json`. The training module constructs the nominal scene itself.

Private evaluator materials: `trusted/go2.py`; every `components/quadrupedbench/*` module including `simulation.py`, `assets.py`, `reference.py` and validation tools; the private prepared Go2 asset directory with its checksum manifest; generated adaptation/held-out banks; reference artifacts; true state/contact traces, rewards, runtime paths and raw operator records. Shared feedback must project only the declared noisy telemetry and sampled images. The nominal robot geometry is intentionally public; private draws and evaluator data are not.

Admission: `go2-attitude` is the positive-reference candidate. `go2-weave`, `go2-forward-jump`, and `go2-yaw-jump` are explicitly **development-only**, not release-blocking tasks. Their unchanged success predicates remain authoritative. Shared registration/allowlisting and isolation validation belong to the orchestrator.

Required-runtime acceptance was repeated on MuJoCo **3.5.0**, same frozen policies and schema-v2 bank: attitude **10/10**, mean **91.06475**; weave **0/10**, mean **0**; forward jump **0/10**, mean **0**; yaw jump **0/10**, mean **9.8**. All 40 source-frozen fresh-process replays matched, four no-op controls scored zero, and four OSMesa videos decoded. The minimal public nominal asset allowlist also passed a two-second training rollout. No success thresholds or reference policies changed.

## Stdlib-only static CI

`trusted/go2_spec.py` provides `make_spec` without importing NumPy, MuJoCo or the numeric controller. The existing `trusted/go2.py` import remains compatible and loads physics only inside `rollout`. Public `control_public/go2_data.py` contains the shared pure-data constants, default artifact and JSON validator; include it in the public training allowlist alongside the existing three Go2 public modules. Keep `trusted/go2_spec.py` private because it generates seed banks.

Specs, default artifacts and task criteria remain identical to the pre-refactor version. Root may normalize the returned instance schema.

## Exact integration runtime and reference-search limits

The exact committed evaluator at `118116389` was validated using the orchestrator's specified MuJoCo3.5.0/OSMesa environment. All40 state/feedback/metric records matched the preceding3.5 run;15 tests,40 fresh-process replays,4 zero-score no-ops and4 decoded videos passed. No compatibility, physics, policy or success-predicate changes were needed. Older3.8 evidence is archived and is not current acceptance evidence.

The operator-only reference search is bounded: at most60 candidates and1200 seconds, one process, with each candidate evaluated on the same3 adaptation cases. Its private adaptation metric objective ranks reference candidates; it does not alter official scores or represent coding-agent feedback. It never reads held-out cases. Search outputs are development artifacts until a frozen candidate demonstrates the unchanged official success gates.

The current `go2-controller/1` ABI is restricted: the gait/jump state machine and transition times are hard-coded; trajectory offsets have17 knots (0.375 s spacing for6-second jumps); learned feedback is a12x6 linear matrix on roll/pitch error and angular rate, with the third input fixed at zero. The learned offset cannot consume joint history, infer contact/flight phase, or condition a general policy on changing commands. The frozen wrapper does use noisy joints for Jacobian/PD calculations, and includes fixed yaw correction, but this does not provide arbitrary trainable state feedback. Published learned locomotion policies cannot be imported directly through this ABI. These are expressiveness limits, not a proof that the task predicates are physically impossible. A future ABI supporting a bounded numeric MLP/history-based policy with fixed CPU inference would permit more capable controllers without exposing privileged state; this iteration does not change the ABI or predicates.

The bounded follow-up evaluated **60 candidates / 180 adaptation episodes in 291.6 seconds**, plus one nominal check of each selected partial candidate. No candidate passed the official task criteria, so none replaced the frozen reference or received a new held-out evaluation. Forward candidate 49 achieved safe stable landing on all three adaptation cases, but first-touch error remained 0.266–0.360 m (required <0.15 m) and airborne displacement remained 0.412–0.451 m. Yaw candidate 17 also landed safely and stably on all three, but first-touch yaw error remained 0.309–0.404 rad (required <0.25 rad). Weave's selected candidate passed only two poles and retained collisions. These partial improvements are operator development evidence, not positive references or coding-agent scores.

## Native integration acceptance

Native Harbor validation now covers both instances of all four objectives with resource enforcement. Attitude passes 10/10 on each plant (mean scores 91.0648 and 91.2450). Weave, forward jump and yaw jump remain 0/10 on both plants and development-only; their mean scores are respectively 0/0, 0/24.5 and 9.8/14.7. Every held-out replay is exact and all eight no-submission controls score zero; infrastructure success does not establish controller success. All delivered feedback bytes and videos are independently audited. These are scripted reference checks, not coding-agent scores. The [integration record](validation.md) documents the verifier build fix, bounded isolation probes, archive identity and remaining gates.
