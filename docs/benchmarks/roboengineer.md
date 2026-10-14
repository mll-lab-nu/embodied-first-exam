# roboEngineer

roboEngineer evaluates a coding agent's ability to engineer controllers across robot embodiments: train or tune in a nominal simulator, diagnose deployment failures from permitted observations, update the training or control pipeline, and generalize to held-out conditions. It is a collection within Robot Coding Bench, using native Harbor tasks and the repository's isolation and resource rules.

## Embodiments and tasks

| Embodiment | Task | Intended objective | Status in this collection |
|---|---|---|---|
| Drone | [Neural Fly — fixed eight](roboengineer-neuralfly.md) | Track a timed figure-eight trajectory while adapting to hidden aerodynamic disturbances. | Native Harbor validated; both reference banks 10/10; noisy-feedback adaptation and exact CPU replay |
| Drone | [Neural Fly — general eight](roboengineer-neuralfly.md#general-figure-eight-revision) | Track randomized horizontal, vertical and inclined figure eights in both directions, with varying yaw, shape and rate. | Development-only; frozen earlier controller 18/20 locally; native acceptance pending |
| Drone appearance variant | [General eight — Skydio visuals](roboengineer-neuralfly.md#skydio-appearance-upgrade) | Same Neural Fly surrogate and general trajectories, with separately versioned Skydio X2 camera appearance. | Development-only; local render/physics replay verified; native/model acceptance pending |
| Drone | [Neural Fly — vector wind](roboengineer-neuralfly.md#experimental-vector-wind-revision) | General figure eights with an explicit horizontal air-velocity field and synthetic isotropic drag. | Development-only; no directional flight calibration or native/model acceptance; wind truth is operator-only |
| Drone | [Neural Landing](quadrotor-landing.md) | Land safely and promptly on an independently randomized pad from randomized initial x/y and height, with a hidden real-flight learned force residual. | Implemented; two native Harbor instances validated with scripted oracle and nop |
| Racing car — AnyCar | [Multi-surface Tracking](roboengineer-anycar.md) | Track a driving trajectory across surfaces with differing tire–ground interaction. | Native Harbor validated; both reference banks 10/10; exact CPU replay |
| Racing car — AnyCar | [Historical circuit full laps](roboengineer-anycar.md#full-lap-task-generation-and-runtime-contract) | Complete every ordered gate of a full scaled lap; record actual finish time. | Development-only long-budget track; local positives on three circuits; full native/model evaluation pending |
| Racing car — AnyCar | [Compact 30-second laps](roboengineer-anycar.md#compact-lap-task-generation-and-runtime-contract) | Complete a 45 m smoothed F1-inspired loop within 30 s; target 28 s. | Development-only; 160 adaptation-only nominal laps pass locally; native/model evaluation pending |
| Racing car — AnyCar | [Drift to Park](roboengineer-anycar.md#drift-to-park-drift-park1) | Follow an ordered U-bend, perform a measured sideways slide and stop between two solid parked cars. | Development-only; nominal success, frozen randomized reference 0/26; transfer solvability unverified |
| Humanoid — Unitree G1 | [Walking over Terrain](roboengineer-g1.md) | Maintain commanded walking while traversing varied terrain. | Implemented locally; trained reference 17/24; incomplete solvability on both plants |
| Quadruped — Unitree Go2 | Weave Pole Navigation | Navigate a slalom between poles; follow SPI-Active's open-loop weave-pole setting when specifying the task. | Implemented development component; positive reference not established |
| Quadruped — Unitree Go2 | Attitude Tracking | Track commanded body attitude. | Native Harbor validated; both reference banks 10/10 on CPU MuJoCo 3.5 |
| Quadruped — Unitree Go2 | Forward Jump | Execute a forward jump and recover a stable landing. | Implemented development component; positive reference not established |
| Quadruped — Unitree Go2 | Yaw Jump | Execute a jump with a change in heading and recover a stable landing. | Implemented development component; positive reference not established |

The quadruped reference is [SPI-Active: Sampling-Based System Identification with Active Exploration for Legged Robot Sim2Real Learning](https://lecar-lab.github.io/spi-active_/). Its project page presents forward jump, yaw jump, and attitude tracking among its performance tasks, plus a separate **open-loop weave pole navigation** demonstration. These four tasks define this roadmap's quadruped scope; the [Go2 implementation](roboengineer-go2.md) supplies numeric targets and contact-based success predicates, with remaining reference-control failures recorded. Open-loop refers to the eventual execution setting, distinct from feedback between engineering iterations.

Neural Landing, fixed-eight Neural Fly, ellipse AnyCar and Go2 attitude have passing native Harbor scripted-reference and no-submission checks on both development instances. Go2 weave and both jumps complete native execution and replay but have no successful references. G1 has local training/held-out evidence and an isolated CPU deployment check; full GPU-training Harbor validation and reference solvability remain incomplete. These integration checks are not LLM results. Training may use Isaac, mjlab/MuJoCo Warp or CPU simulation. **Every deployment and held-out evaluator must use native CPU MuJoCo, CPU numeric inference and software OSMesa rendering**, even where the source paper uses Isaac. The actual robot, actor inputs, hidden dynamics, budgets and scoring must be frozen and validated separately for each task.

The imported Control Transfer sources also contain earlier Linearbot, spacecraft and YAM prototypes. They remain available for development, but are not generated as members of the original eight-objective collection. Existing similarly named tasks elsewhere in the repository are not automatically members.

See the [integration validation record](roboengineer-validation.md) for the tested boundaries, native build incident, trace audits and remaining acceptance gates.

## Shared evaluation structure

The collection workflow is:

1. **Nominal training:** the agent develops a controller or policy with a public model and declared compute/time limits.
2. **Deployment and improvement:** a separate evaluator runs a submitted artifact on hidden dynamics. The agent receives only the task's permitted camera/video observations and noisy measurements, records a short diagnosis and proposed change, and may improve its artifact for a bounded number of rounds.
3. **Held-out evaluation:** freeze the selected artifact before evaluation on a private bank. Held-out states, scores and videos are withheld until the agent's work is complete.
4. **Traceable reporting:** retain artifact versions, the exact feedback delivered at each round, submitted diagnoses, budgets, and final per-case metrics and recordings. Agent-visible feedback and operator-only evaluation records must be labeled separately.

Each instance preserves one hidden physical plant throughout adaptation and held-out evaluation. Commands, terrain layouts, initial conditions and sensor noise vary across disjoint cases. Different instances use different plants. This measures adaptation to a particular deployment system; unseen-plant transfer is a separate track.

Use [policy adaptation](../POLICY_MODE.md) where its contract applies. Each task must declare its actual controller interface, round count, sensor channels, privacy boundary and scoring rule; this roadmap does not imply that arbitrary agent code may execute inside the deployment service. Report results by task and embodiment. No cross-embodiment aggregate score is defined yet.

## First implementation: Neural Landing

- **Packaging:** `quadrotor-landing-random-pad-i00-standard` and `quadrotor-landing-random-pad-i01-standard`; generator: `scripts/quadrotor_landing/gen_tasks.py`.
- **Metadata:** `collection = "roboEngineer"`, `embodiment = "drone"`, `robot = "intel-aero-partial"`, `family = "quadrotor-landing/random-pad"`. Existing task IDs, the internal `Neural Lander` benchmark label, and cutoff/resource rules remain stable.
- **Plant:** CPU MuJoCo with partial Intel Aero calibration and the authors' released Neural Lander force network, private to the deployment evaluator. This is simulation-to-simulation adaptation informed by real-flight data, not a hardware evaluation or a fully calibrated aircraft model.
- **Randomization:** independent initial x/y and pad x/y in [-1, 1] m, at least 0.5 m horizontal separation, and initial body-origin height in [0.8, 1.5] m. Dynamics are the same hidden plant across cases; placements and measurement noise vary.
- **Adaptation:** three deployment-feedback rounds, each with three adaptation cases. The current submission interface is numeric controller parameters and force-correction coefficients; the agent may write its own training and analysis code, but cannot replace the evaluator's controller implementation.
- **Feedback:** noisy sensor trajectories and 16 sampled camera images per case. Full evaluation videos are retained for operator review; the scripted reference learner uses the sensors, not image analysis.
- **Verification:** six held-out cases per instance, each replayed twice in fresh processes. Binary success requires all six safe landings; a separate 0–100 engineering score rewards safety and time relative to a private finite controller search, not a certified global optimum.
- **Evidence:** native Harbor Docker CPU oracle/nop validation passed for both instances. Oracle engineering scores were 82.29 and 84.94, with 6/6 safe cases each; nop scored zero. These are scripted integration checks, not LLM model scores. Full details and limitations are in the [task specification](quadrotor-landing.md#native-harbor-packaging-and-validation).

## Adding a task

Add a task-specific specification, generator and image/asset provenance; declare `collection = "roboEngineer"` and one of `drone`, `racing-car`, `humanoid`, or `quadruped` as its `embodiment`. Preserve a separate `robot` identifier for the actual platform and a `family` for the objective. Freeze public/adaptation/held-out definitions before comparing agents, and validate the task's isolation, replay, baseline and nop behavior through native Harbor. Update this roadmap to implemented only when runnable task packages and their validation evidence exist. Follow [CONTRIBUTING.md](../../CONTRIBUTING.md) for the repository's review requirements.


AnyCar additionally provides an opt-in `circuit-sector/1` variant with scaled historical F1
circuit outlines and synthetic zigzag tracking. It is development-only and excluded from
the native ellipse acceptance totals. The [AnyCar guide](roboengineer-anycar.md#generating-optional-circuit-tasks)
describes the 78-venue catalog, historical layout availability, task generation and evidence limits.
