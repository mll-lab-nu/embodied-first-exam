# roboEngineer — G1 Walking over Terrain

> roboEngineer task names: [roboengineer.md](roboengineer.md) (the package names of #329 used on this page, `control-transfer-*` / `quadrotor-landing-*`, map to `roboengineer-*` in `scripts/roboengineer/exported.toml`).

This family extends the imported G1 flat-walking prototype to **flat, slope, rough heightfield, and steps**, with blind-policy training in mjlab/MuJoCo Warp and deployment in native **CPU MuJoCo 3.5.0**, NumPy CPU inference, and **OSMesa software rendering**. It is sim-to-sim transfer. A real robot, hardware calibration, and native Harbor isolation validation are separate requirements.

## Task and interface

The Unitree G1 has the pinned 29-actuator joint order, stiffness/damping, default pose and action scale in `scripts/control_transfer/components/sim2realbench/g1/actuator_abi.json`. These values are unchanged. Every episode stands for 2 seconds then walks forward for 18 seconds. Public forward-speed commands vary across 0.5, 0.6 and 0.65 m/s; commanded lateral/yaw velocities are zero. Initial x/y each vary within ±0.15 m of the launch area. Evaluation commands and noise differ between adaptation and held-out cases.

The fixed actor receives 98 values: noisy angular velocity (3), noisy normalized projected gravity (3), velocity command (3), sine/cosine gait phase (2), noisy relative joint position (29), noisy joint velocity (29), and previous action (29). The phase period is 0.6 s. Actor inference runs at 50 Hz; joint PD/physics run at 500 Hz. The actor receives no terrain scan, true base position, true velocity, contact flags or reward. Position/velocity used in the physical PD servo are internal simulator actuator state, not observations returned to the coding agent or inputs added to the learned actor.

Submissions are bounded NPZ numeric weights and normalization arrays for the fixed `98 → 512 → 256 → 128 → 29` ELU MLP. Validation rejects wrong shapes/fields, nonfinite or unbounded values, object arrays, invalid normalization and oversized archives through the shared numeric ABI. No Python, pickle or agent-supplied ONNX graph runs in deployment. The training-side ONNX intermediate is converted to the numeric artifact before submission.

**Coding-agent feedback** contains only `telemetry` rows `{t, values}` with 29 noisy joint angles in radians at 10 Hz, `commands` rows `{t, values}` with the three public velocity commands, and sampled images provided by the shared service. Full 320×240/10fps videos are recorded. IMU channels used inside the policy are not extra coding-agent feedback. True trajectories, terrain parameters/seeds, model parameters, success/score and contacts stay operator-only. No private reasoning is requested; the shared service archives concise observable diagnoses.

## Terrain and hidden dynamics

All courses have a flat launch area extending to x=1 m. Slopes rise for four metres then plateau, with grade 0.04–0.08 (about 2.3–4.6°). Rough terrain is a deterministic seeded sum of six spatial waves, with bounded amplitude 0.012–0.028 m, represented by a MuJoCo collision heightfield; it ramps in between x=1 and x=1.5 m. Steps have six physical box treads at levels 1, 2, 3, 3, 2, 1, with riser height 0.025–0.05 m and tread width 0.6–0.9 m. Terrain width is 6 m. This is a benchmark curriculum, not a claim of reproducing a published hardware terrain experiment.

Each instance draws **one fixed hidden plant**: mass/inertia scale 0.85–1.15, sliding friction 0.45–1.15, individual motor strengths 0.85–1.15, 0–2 policy-step command delay, fixed encoder biases and measurement noise levels. Those parameters persist throughout adaptation and held-out evaluation. Terrain geometry, initial position, commanded speed and noise samples vary by episode. Different instances use different hidden plants. Within-instance held-out performance is not labeled unseen-plant generalization.

`make_spec(index)` declares `control-transfer-instance/2`, `transfer_track=same-plant`, and fixes `plant_seed = 10000 + index * 1000 + 100` for every adaptation and held-out case. It supplies four adaptation cases (one per terrain class), three allowed deployment rounds, and **12 held-out cases**, three per terrain class. The two development instances have disjoint case banks and distinct plants. The operator must freeze undisclosed banks separately before official model comparisons; source-visible development seeds are not secret competition seeds.

## Scoring

A successful episode must survive the full 20 s without falling, have mean absolute world-x speed error below 0.25 m/s, move forward more than 65% of the commanded walking distance, and end with less than 2 m lateral displacement. Falling means pelvis clearance above the **actual collision terrain** below 0.45 m or true body-up cosine below 0.5. These privileged tests affect metrics only, never observations.

The engineering score is `100 × walking survival fraction × exp(-speed MAE / commanded speed) × clipped forward-progress fraction`. The progress factor prevents a standing controller from receiving the old flat-task survival-only credit. Scores and binary success are distinct: a controller that walks but drifts too far may have a nonzero engineering score and fail the task. Thresholds were not relaxed to make the reference pass. This changes score semantics from the imported flat prototype, so earlier scores must not be relabeled as terrain-task results.

## Training and provenance

The robot, actuator ABI and base PPO task derive from [Unitree's mjlab stack](https://github.com/unitreerobotics/unitree_rl_mjlab), pinned at commit `1425b15f73bd4095f0df53709d7c389c3eb9e790`. Keep upstream asset licenses and the prepared asset hash manifest. Robot meshes, weights and run artifacts are not committed here. The public trainer contains no hidden evaluation draws or seed banks and does not import the evaluator.

`control_public.g1_training` removes height scans from both actor and critic, preserves the actor ABI, and trains on six terrain columns: flat, uphill, downhill, random roughness, ascending steps and descending steps. Five difficulty levels increase slope up to grade 0.12 and step height up to 0.06 m. Training random roughness is bounded to ±0.025 m. The upstream terrain-level curriculum promotes/demotes environments based on performance. The critic may use privileged **nominal training** features; it is never deployed. Optional warm-start inputs are operator/agent-owned checkpoints and validated numeric actors; reference weights are not installed in the agent image.

Example commands (asset and output paths are operator supplied):

```bash
export PYTHONPATH=scripts/control_transfer/components:scripts/control_transfer
python -m control_public.g1_training --upstream "$NOMINAL_G1_SOURCE" --out "$TRAIN_OUT" \
  --gpu 0 --num-envs 256 --iterations 300 --seed 42
python -m sim2realbench.g1.validate_terrain --policy "$TRAIN_OUT/policy.npz" --out "$VALIDATION_OUT"
CONTROL_ASSETS="$PUBLIC_ASSETS" python -m unittest scripts.control_transfer.tests.test_g1_terrain -v
```

The evaluator requires the native OSMesa library installed by the image. `CONTROL_ASSETS` identifies the prepared robot assets; validation needs no GPU. Training explicitly selects one GPU, caps CPU affinity at four cores, records learning curves and its actual step budget, and compares the trained torch actor with the exported NumPy actor. A short PPO run is training/transfer evidence, **not evidence of convergence**.

## Integration contract

Lightweight generators should import `make_spec` directly from `sim2realbench.g1.terrain`; module import and spec construction require only the Python standard library. Simulation imports are local to terrain construction/query functions. The isolated-interpreter regression rejects importing MuJoCo, NumPy, Torch or Warp during spec generation.

The trusted runtime hook is `sim2realbench.g1.evaluation`: `validate(policy) -> bytes`, `make_spec(index) -> dict`, and `rollout(policy_path, case, out, render) -> record`. A case has exactly `plant_seed`, `episode_seed`, `terrain`, `duration`, `speed`. Records include `state_sha256`, `metrics.success`, `metrics.score`, `feedback.telemetry`, `feedback.commands`, and operator-only `dynamics`/`terrain`. State hashes cover qpos, qvel, actuator state and controls at **every physics tick**. Rendering does not change the dynamics or feedback-noise stream.

The shared orchestrator owns three-round admission, artifact versions, cutoff/seal behavior, private held-out execution, exact feedback-byte archiving, separate verifier, image sampling, task generation, resource limits and Harbor validation. The public image should copy only the public trainer and numeric submission utilities plus scrubbed nominal source/assets; do not copy `terrain.py`, `deploy.py`, `evaluation.py`, private cases or reference policies. The compatibility `g1/train.py` entry point is operator tooling; its asset helper also names the private reference location and is not a public-image allowlist.

The validation driver runs every held-out case twice in separate processes, checks state/feedback hashes and metrics, decodes rendered videos, verifies plant constancy, and rejects standing/falling negative controls. It records `solvability_pass` separately from replay/packaging success; integration success cannot establish reference solvability.

## Local development validation

Seven family-specific tests check the numeric artifact boundary, joint ABI, private bank disjointness/fixed plants, true terrain collision heights, deterministic roughness and command-blind negative-controller behavior. Native CPU validation runs two 12-case banks with independent process replays. It has positive reference cases on every terrain class, but **full reference solvability remains incomplete**.

On the required schema-v2 plants (10100 and 11100), the released actor succeeds in 16/24 cases (6/12 and 10/12), and the 300-iteration trained actor in 17/24 (6/12 and 11/12). Neither plant is fully solved by the trained reference. All 24 cases per actor have exact fresh-process state and feedback replays; these are local operator validations, not agent scores or Harbor isolation evidence.

A real blind-terrain PPO run used 300 iterations × 256 environments × 24 policy steps (1,843,200 transitions), initialized from the released numeric actor and an existing compatible training critic checkpoint. On the historical development plants (38471 and 38664), the resulting actor improved success from 10/24 to 17/24: first plant 3/12 → 12/12, second plant 7/12 → 5/12. These historical results are not acceptance results for the schema-v2 plants (10100 and 11100); this is not uniform improvement or evidence of convergence. The trained actor's numeric export agreed with the actual trained Torch model within 2.9e-6. Training reward and curriculum level increased modestly over complete-episode windows, while velocity error did not consistently improve; full curves are retained outside Git.

The first completed training run's post-export check called an upstream API without its required `verbose` argument. Its checkpoint was preserved and independently checked on CPU after fixing that call. A subsequent 20-iteration continuation completed training, numeric export and its fidelity check end to end, then passed a CPU flat rollout. These are operator reference-development results, not coding-agent scores or native Harbor validation.

The original zero-output negative falls and scores zero. A separate command-blind balancing controller survived all 20 seconds, moved less than 5 mm forward, failed walking success and scored zero. An initially fallen controller also scores zero. Actual OSMesa videos were decoded and visually inspected; a hidden default geometry group was corrected so terrain is visible. Full evidence, policies, exact local feedback, learning curves and per-case metrics are retained in the operator's external evidence directory. The shared integration must archive the exact service response/image bytes and perform its own Harbor isolation checks before claiming end-to-end benchmark readiness.

## Public packaging boundary

The public G1 payload requires only `control_public/g1_training.py`, `control_public/g1.py`, shared `control_public/weights.py` and the package initializer, alongside separately reviewed common client files and nominal upstream assets. No G1 component Python module is required. Keep the entire `components/sim2realbench/g1/terrain.py` private: it combines evaluation banks, seeded terrain draws, collision-course construction and privileged ground-height queries. Nominal training terrain is independently defined by `g1_training.build_config` through mjlab's terrain classes. The legacy `train.py` wrapper is operator-only because it imports an asset helper naming a private reference location.

For a G1-only upstream source package, retain `src` package initializers, `src/tasks/velocity/velocity_env_cfg.py`, `src/tasks/velocity/config/g1/*.py`, `src/tasks/velocity/mdp/*.py`, `src/tasks/velocity/rl/*.py`, and nominal `src/assets/robots/unitree_g1` Python/XML/mesh assets with their license notices. Exclude other robot task configs, deployment policies, checkpoints, caches and Git metadata. Replace the staged `src/assets/robots/__init__.py` with `from .unitree_g1.g1_constants import G1_ACTION_SCALE, get_g1_robot_cfg`: the upstream initializer imports all robot types eagerly. This subset passed configuration construction and nominal scene compilation with 29 actuators; it was not a fresh training or isolation test.

The tested training stack uses Python 3.12, mjlab 1.2.0, MuJoCo and MuJoCo Warp 3.5.0, Warp 1.12.0, Torch 2.11.0+cu128, RSL-RL 5.0.1, NumPy 2.3.1, ONNX 1.23.0, ONNXScript 0.7.2, TensorBoard 2.21.0, TensorDict 0.14.3, W&B 0.30.0, torchvision 0.26.0+cu128 and PyOpenGL 3.1.10, with their normal transitive dependencies. W&B is imported by the nominal upstream runner even when logging is disabled. The operator handoff records the complete tested environment inventory and file manifest. Official held-out runtime proof additionally requires MuJoCo 3.5.0 CPU and verified OSMesa/device evidence; local CPU rollouts do not prove device isolation.

## Deployment-container integration check

The final CPU evaluator image was built and tested on October 13, 2026 using the generated private adapter, minimal nominal G1 assets and the frozen trained numeric policy. Each of the four instance-0 adaptation terrain cases ran in two fresh Docker containers with no network, no GPU devices and actual OSMesa software rendering. State, noisy feedback and metrics matched exactly; all four videos decoded. Flat and steps succeeded; slope and rough fell. This establishes deployment-container packaging and replay, not a held-out bank result, full reference solvability, GPU training-image validation or a native Harbor training trial. See the [integration validation record](roboengineer-validation.md).
