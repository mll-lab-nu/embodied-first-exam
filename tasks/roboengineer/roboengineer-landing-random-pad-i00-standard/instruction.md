# roboEngineer · Quadrotor landing adaptation (standard)

## Task
Land the drone gently near the centre of the round pad as quickly as you safely can, and keep it there, level and still,
until the end.

## Goal
Success: the drone touches down slowly on the pad, touching nothing but the pad, then settles near the pad's centre,
level and still, and stays settled until the episode ends. Touching down anywhere else fails, even if it later slides
onto the pad. Tipping far over, leaving the flying area or climbing too high fails. The evaluator runs the policy you
select on 6 held-out cases (new episodes of the same hidden plant, never shown to you): success needs every case to
pass, and `final_reward` reports the mean score (0-100).

Deliverable: the policy of one completed deployment round. Seal it with
`python -m scripts.quadrotor_landing.public.client seal --round-id round-N --note '...'`: you may select any completed
round. This is irreversible for the session. If you finish or time out without sealing, the evaluator selects the latest
round completed before the cutoff. In-flight or late rounds cannot be selected. With no eligible round the score is
zero. Work in `/app` and preserve your code, policies, exact feedback and short iteration diagnoses in `/app/output/`.
Save each policy, your code changes, and a concise diagnosis.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, trained
  policies for this task) or hidden evaluator information; trials are reviewed. Write your own fitting, training and
  analysis code.
- No reset: deployments are your only runs on the hidden evaluator. You get at most three rounds, each on the same 3
  development cases from their start. There is no reset or privileged-state endpoint.
- Actual scores, completion times, contacts, success flags and the reference controller's data are not returned during
  adaptation; infer performance only from the allowed noisy observations and images. Use only these observations to
  estimate the mismatch.

## Robot Interface
A simulated Intel Aero quadrotor (MuJoCo, with a learned ground-effect residual in the evaluator). The deployment
simulator includes unmodeled dynamics. You tune its numeric controller on the public nominal model in your container.
Then you deploy it to a hidden evaluator whose dynamics differ in ways you are not told. The evaluator runs as a service
that you reach only through its client.

### Client
- `python -m scripts.quadrotor_landing.public.client describe`: your remaining budget (counts and deadline in the live
  contract are authoritative). Calibration and health checks do not consume deployment rounds.
- Deploy a candidate:
  `python -m scripts.quadrotor_landing.public.client deploy --policy policy.json --note 'Observed failure and intended change' --out feedback.json`.
  A deployment request consumes one round before execution.
- Seal a round:
  `python -m scripts.quadrotor_landing.public.client seal --round-id round-3 --note 'Why this policy was selected'`.
- The deployment endpoint is `http://127.0.0.1:8000`; `GET /spec` describes its protocol.

### Training
Develop a numeric policy following `public/policy.py`. The controller executes at 100 Hz with four bounded rotor-thrust
commands. This task fixes the feedback-controller structure; you may train its three-axis residual-force model and tune
its public gains. It does not accept arbitrary executable controllers. The `landing-policy/2` controller first
approaches the pad horizontally, then descends; both durations and the feedback gains are tunable. Its learned
correction has 3 × 14 bounded coefficients. The nominal simulator is `scripts/quadrotor_landing/public/nominal.py`. Only
validated numeric policies reach deployment; editing your local controller implementation does not change the
evaluator's controller. Nominal training is unrestricted within the resource and time limits.

### Feedback
The three deployment rounds share three adaptation cases. Feedback includes 20 Hz noisy navigation, IMU specific force,
measured rotor RPM, your commands, and sixteen timestamped image samples. An episode that makes the simulation diverge
ends at that moment: its telemetry and image samples stop there. A crash does not stop the episode, but it already
counts as failed.
- The observations use metres, seconds, world-frame position/velocity, a body-to-world quaternion in wxyz order, body
  angular velocity in rad/s, body-frame IMU specific force in m/s², and rotor speeds in RPM. The nominal thrust
  coefficient and geometry are public. The base plane is at world z=0; the nominal body origin is 0.09 m above it at
  touchdown.
- Camera frames are 1280×720 with a fixed world camera and no state or score overlays. The live contract identifies the
  rendering style.
- The commanded landing-pad position is `pad_position` in each observation. This is a public task goal, not a
  measurement of the robot. It remains fixed throughout the episode.

### Episodes
- Initial x/y and pad x/y are sampled in [-1, 1] m, conditioned on at least 0.5 m horizontal separation. Initial
  body-origin height is 0.8–1.5 m. Episodes last 16 s.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the
  deployment service and the deployments. At the end you are stopped without warning. The evaluator then takes the round
  you sealed; if you sealed none, it takes the latest deployment that finished before then. A deployment still running
  is not graded. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). The service's own deadline
  counts the same limit from your first request to it. A call into a long-running process can block for its whole wait
  time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. Deployments are your only runs, each starting its development cases afresh.
- Rounds: three deployment rounds (`describe` has what is left).
