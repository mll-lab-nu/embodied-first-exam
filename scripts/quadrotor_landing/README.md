# Random-pad quadrotor landing (v4)

See [the benchmark design and run instructions](../../docs/benchmarks/quadrotor-landing.md).

- `public/`: agent-visible nominal MuJoCo simulator, fixed numeric policy ABI, feedback-only training utility, HTTP client, scripted iteration example, and task instructions.
- `trusted/oracle.py`: private per-case full-model timing optimization, candidate history and independently verified replay artifacts.
- `trusted/rendering.py`: separate presentation model, fixed camera, detailed airframe and 720p/25fps flight-lab video.
- `trusted/`: hidden residual model, deployment simulation/service, persistent budgets and separate held-out grading.
- `calibration.json`: parameter-by-parameter provenance and explicit missing airframe calibration.
- `audit_calibration.py`: pinned source checks, original-checkpoint inference parity, and released-flight diagnostics.
- `prepare_assets.py`: operator-only pinned checkpoint preparation; weights stay outside the repository.
- `validate.py`: recorded nominal/baseline/oracle checks and three-round public-API adaptation.
- `tests/`: physical success, information boundary, replay, policy validation and session lifecycle tests.
- `native/`, `gen_tasks.py`: self-contained Harbor policy tasks, trusted collect lifecycle and numeric verifier; `eai-policy/1.0`.
- `reference/`: the scripted reference learner (copied only into the tasks' `solution/`); the tasks use `images/quadrotor-landing/` and their generated compose files.

`python3 -m scripts.quadrotor_landing.gen_tasks render|check` writes `tasks/roboengineer-landing-random-pad-i00/i01-standard`; validation: docs/benchmarks/roboengineer.md.

No LLM evaluation or hardware validation is claimed. This initial task uses CPU physics and supervised residual fitting; GPU RL training is not required or implemented here.

The task randomizes start height, start x/y, and a fixed target pad. The evaluator uses all three outputs of the released real-flight aerodynamic model. The nominal model uses the published mass/propeller/thrust calibration, while rotational and contact parameters remain assumptions; it must not be labeled a fully calibrated Intel Aero simulation. Version 4 normalizes time against a frozen numerical full-model oracle for each case. Safe completion within 110% of the reference time earns 100; later safe completion decays to 60 at the 16 s deadline, while failures earn zero. The search optimizes six gains/timings within the fixed controller family; it does not certify a global physical optimum. Completion includes one continuous settled second, with stability required through episode end. Success rate is reported separately. Earlier v1/v2/v3 records remain unchanged and cannot be resumed as v4 sessions. Oracle source/assets, references and candidate traces are evaluator-private and hash-pinned before agent interaction.
