# Robotic Engineering Bench: control transfer

The current landing family is named **Neural Lander**, keeping `quadrotor-landing-*` IDs stable so existing evidence stays attributable. Five new families use the same engineering loop: train or optimize locally, deploy into a hidden plant, inspect noisy observations and video, revise within three rounds, then seal one policy for disjoint held-out evaluation.

## Tasks

| Family | Robot / objective | Nominal training | Hidden deployment variation | Development / held-out per instance |
|---|---|---|---|---|
| Neural Fly | Paper-inspired 2.53 kg quadrotor; six timed vertical figure-eight laps | CPU MuJoCo; geometric controller plus learned force coefficients | Flight-log-fitted force surrogate; five constant/time-varying wind strata; motor lag, small mass variation; random reference phase/center and initial offset | 5 / 10 |
| Linearbot fixed | Supplied Linearbot; base x/y/yaw and both gripper 6D poses | Nominal IK imitation initialization, then PPO in MuJoCo Warp | Mass/inertia, servo strength/damping, command delay and encoder noise; independent world-frame targets with initial separation | 3 / 6 |
| Linearbot moving | Same robot and policy; coordinated, world-lock, and height-sweep references | Same GPU pipeline | Same dynamics; each trajectory is fixed before rollout and cannot follow the actual robot | 3 / 6 |
| Spacecraft rendezvous | Six-DoF chaser approaching a fixed station in LVLH | CPU MuJoCo nonlinear controller tuning | Mass/inertia, orbital radius, thruster scale/bias/misalignment, lag, delay, sensor noise and initial pose | 3 / 6 |
| YAM catch | Menagerie I2RT YAM with original parallel fingers | Nominal CPU simulation; intercept/servo/filter tuning | Three approach directions × three launch-height bands; mass, strength, friction, delays and noisy encoders/vision | 9 / 18 |
| G1 training and transfer | Unitree G1, 29 DoF; stand then walk at 0.6 m/s | Pinned Unitree mjlab / MuJoCo Warp PPO | Mass/inertia 0.85–1.15, friction 0.45–1.15, motor strength 0.85–1.15, delay 0–40 ms, encoder biases/noise | 3 / 6 |

There are two reproducible development instances for each row: twelve native Harbor task definitions.
The checked-in banks are public reproducibility fixtures. They are **not secret competition seeds**; an official campaign must freeze fresh operator-owned banks before agents start and use matched banks across models.

## Policy and feedback contract

`eai-policy/1.1` retains `describe`, `deploy`, and `seal`. Controllers for Neural Fly, spacecraft and YAM accept bounded numerical coefficients. Linearbot and G1 accept a base64 NPZ containing fixed-shape numeric MLP tensors. Archive size, decompressed size, tensor headers, shapes, dtypes and finiteness are checked before allocation/inference. No pickle, Python module, arbitrary ONNX graph or external tensor filename executes in the target simulator.

The coding agent can change its local fitting and training code. Controller coefficients and network weights are the deployment ABI; this release does not evaluate arbitrary low-level controller programs in the target process. GPU policies are trained in the agent container; CPU evaluation has its own filesystem. The evaluator never mounts the agent workspace or exposes a file-reading API. The separate verifier has no network and accepts simulator-collected evidence only.

Each round preserves the policy bytes/hash, a short diagnosis, full operator MP4s and the **exact JSON and base64 images returned to the agent**. These are observable diagnoses and predictions, not private chain of thought. `control_public.client` saves responses and decodes the same JPEG bytes for the agent to inspect. Training stdout/configuration/checkpoints belong under `/app/output/`; Harbor records the agent transcript. A response receipt proves delivery, not that a model actually inspected every frame.

Only noisy telemetry, public targets where applicable, and sampled camera frames are returned. No target scores, contacts, realized dynamics, seed bank, reference search, true state or filesystem path is returned. G1 coding-agent feedback contains 29 noisy joint angles and images; the embedded robot actor retains its documented noisy proprioceptive input.

Rounds are charged before simulation and persist across restarts. An interrupted round is an infrastructure error. Sealing is irreversible. At cutoff only completed eligible rounds can be selected. Held-out policies replay in fresh processes; state-sequence hashes, metrics and observation sequences must match exactly. No submission produces zero. Infrastructure failures are distinct from controller failures.

## Scoring

Continuous scores and binary success are reported together, separately by task/class and dynamics stratum. Reference tracking uses prescribed time, so moving more slowly cannot avoid tracking error. Landing's oracle-relative time score remains specific to Neural Lander.

* Neural Fly: crash/escape gives zero; otherwise `100 exp(-max(0,RMSE-0.03)/0.25)`. Success requires the full horizon and RMSE below 0.25 m. These tolerances are provisional benchmark choices, not the paper's claimed result.
* Linearbot: exponential score over six normalized time-mean errors after a 1 s acquisition interval. Success requires base xy <0.06 m, yaw <0.12 rad, each hand position <0.07 m and orientation <0.20 rad.
* Spacecraft: weighted terminal pose/speed/angular-rate/fuel-impulse quality; collisions/escape score zero and unsuccessful capture is capped at 49. Capture requires a final 3 s dwell within the four public tolerances.
* YAM: 100 requires final bilateral contact, ball elevation and low velocity sustained for at least 0.5 s; earlier retention is capped at 49. Proximity alone is zero.
* G1: survival-weighted speed tracking; success also requires full duration, forward travel and limited lateral drift. Always retain the binary result because continuous speed score alone does not enforce all criteria.

## Fidelity and provenance

Neural Fly follows the [paper](https://arxiv.org/abs/2205.06908) and its [released trajectory definition](https://github.com/aerorobotics/neural-fly): `x=1.25 sin(t), y=0, z=center_z+0.75 sin(2t)`, approximately 6.28 s per lap. Mass 2.53 kg uses supplementary Table S2 (main text rounds to 2.6 kg); propeller diameter 11 inches, motor spacing 39 cm, thrust/weight 2.2. Inertia, motor response, inner attitude controller, clipping and collision geometry are benchmark assumptions. This is **not PX4 SITL, a DAIML reproduction, or a fully identified digital twin**.

`calibrate_fly.py` fits a bounded quadratic force surrogate to released baseline flight logs at pinned commit `0ed50246b1f1db194e8f0726749351636d3501bf`. CSV xyzw quaternions are converted to MuJoCo wxyz, checked against each logged rotation matrix, and sign-canonicalized. Force labels are the released measured/estimated residuals. Validation uses the final 20% of each flight, not unseen flights; per-axis RMSE is approximately 0.875, 0.589, 1.696 N. It includes random-waypoint and baseline figure-eight logs to cover high-wind conditions. It does not establish real-world controller performance. Training the simulator surrogate and training an agent policy are different operations.

The upstream flight data/code are personal/educational-use only with written permission required for further use. Derived assets remain operator-supplied, local-build only. No flight data or weights are committed or published here.

YAM assets: Menagerie `0059d4335f8156206f63a35662313385f7ad6d74`. G1 assets/training: Unitree `1425b15f73bd4095f0df53709d7c389c3eb9e790`. Linearbot is from the supplied robot archive; redistribution permissions are not assumed. Asset manifests verify runtime bytes. `component-provenance.json` identifies the original local environment sources; the copies add native transport, strict policy loading, and state-hash instrumentation.

Linearbot's base remains an idealized planar actuator, not a physically driven wheel system. Spacecraft uses exact two-body relative translation about a circular reference, but continuous wrench actuation, simplified contact geometry and no docking latch. YAM uses a synthetic noisy 3D ball detector, not learned image-only perception. G1 deploys in another simulator, not physical hardware.

## Build and run

Prepare assets from the existing local environments, then prepare the image context. No task downloads robot assets at runtime:

```bash
python -m scripts.control_transfer.prepare_assets --workspace /path/to/workspace --out /operator/assets
python -m scripts.control_transfer.calibrate_fly --source /operator/neural-fly-pinned --out /operator/fly-calibration
python images/control-transfer/prepare_assets.py --assets /operator/assets --fly /operator/fly-calibration
images/control-transfer/build.sh
python scripts/control_transfer/gen_tasks.py render
harbor run -p tasks/control-transfer-spacecraft-i00-standard -a nop -e docker
```

The image has separate `nominal`, `train`, and `evaluator` targets. Only the evaluator contains the private force asset. The GPU training target uses the same public model assets with a pinned training stack. Images are marked `BUILD_ONLY`; do not publish them without asset permissions.

```bash
python -m unittest scripts.control_transfer.tests.test_boundary -v
python -m scripts.control_transfer.validate --out /operator/new-validation \
  --assets /operator/assets --fly /operator/fly-calibration/forces.npz --smoke
```

`--smoke` explicitly reduces the bank to one development and one held-out case per instance; it validates plumbing, media and replay, **not benchmark performance**. Omit it to exercise complete banks. All operator validation is labeled `model_evaluation=false`. New task oracle status remains `none` until positive references and native Harbor runs are validated. Resource allocations and the four-hour agent cutoff are provisional; short GPU training/export tests do not prove convergence or establish a fair training budget.
