# roboEngineer · Quadrotor landing adaptation (standard)

## Task
A simulated Intel Aero quadrotor (MuJoCo, with a learned ground-effect residual in the evaluator). Make the quadrotor
land gently on the visible circular pad and remain settled. The deployment simulator includes unmodeled dynamics. You
tune its numeric controller on the public nominal model in your container and deploy it to a hidden evaluator whose
dynamics differ in ways you are not told; the evaluator runs as a service you reach only through its client.

## Goal
Success: the quadrotor lands gently on the pad (slowly at the first touch, touching nothing but the pad), settles there,
level and still, and stays settled until the episode ends at 16 s. Landing elsewhere on the floor fails even if it later
slides onto the pad, and so do tipping far over, leaving the flying area or climbing too high. A safe landing about as
quick as a strong reference controller manages for that case scores 100, a slower safe landing 60 to 100, a failure 0.
The evaluator runs the policy you select on 6 held-out cases (new episodes of the same hidden plant, never shown to
you): success needs every case to pass, and `final_reward` reports the mean score (0-100).

Deliverable: the policy of one completed deployment round. Seal it with
`python -m scripts.quadrotor_landing.public.client seal --round-id round-N --note '...'`: you may select any completed
round. This is irreversible for the session. If you finish or time out without sealing, the evaluator selects the latest
round completed before the cutoff. In-flight or late rounds cannot be selected. With no eligible round the score is
zero. Work in `/app` and preserve your code, policies, exact feedback and short iteration diagnoses in `/app/output/`.
Save each policy, your code changes, and a concise diagnosis.

Real-robot rules:
- No reset: deployments are your only runs on the hidden evaluator, at most three rounds, each on the same 3 development
  cases from their start; no reset or privileged-state endpoint exists.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own fitting, training and analysis code; do not use published or reference solutions, trained policies for
  this task, or hidden evaluator information.

## Robot Interface
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
measured rotor RPM, your commands, and sixteen timestamped image samples. An episode that crashes or makes the
simulation diverge ends at that moment: its telemetry and image samples stop there.
- The observations use metres, seconds, world-frame position/velocity, a body-to-world quaternion in wxyz order, body
  angular velocity in rad/s, body-frame IMU specific force in m/s², and rotor speeds in RPM. The nominal thrust
  coefficient and geometry are public. The base plane is at world z=0; the nominal body origin is 0.09 m above it at
  touchdown.
- Camera frames are 1280×720 with a fixed world camera and no state or score overlays. The live contract identifies the
  rendering style.
- The commanded landing-pad position is `pad_position` in each observation. This is a public task goal, not a
  measurement of the robot. It remains fixed throughout the episode.

### This run: privileged state queries
This run lets you read the simulator's true state during your development episodes.

- `GET /state/entities` (in Python: `json.load(urllib.request.urlopen("http://127.0.0.1:8000/state/entities"))`) lists
  what you can query:
  `{"frame", "quaternion_order", "entities": {name: {"kind", "fields": {field: unit}, "static"}}, "rounds"}`. The kinds
  are `robot` (the robot's base or root, the car, the drone), `object` (parked cars) and `scene_feature` (poles, a
  parking slot, a curb, a pad). `rounds` lists the completed rounds you can query.
- `POST /state/query` with `{"names": [...], "fields": [...], "round_id": ..., "case": ..., "t": ...}` (in Python:
  `call("state/query", {"names": ["drone"], "case": 0}, url="http://127.0.0.1:8000")` (with `call` from
  `scripts.quadrotor_landing.public.client`)) answers
  `{"round_id", "cases": [{"case", "t": [...], "state": {name: {field: [one value per time]}}}], "state_queries"}`: the
  state of that round's development episodes at their telemetry times, that is the true pose and velocity of each body
  and the robot's joints as its encoders read them (the same readings as the telemetry). Only `names` is required:
  `fields` defaults to every field, `round_id` to the latest completed round, `case` to every development case of that
  round, and `t` (seconds, or a window `[t0, t1]`) to every sample. A `static` entity gives one value instead of a list.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s (both in the
    world frame), `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents along
    the body's axes), `bbox` [[x, y, z] min, [x, y, z] max] m. Each field's unit is in the list.
  - An unknown name, field or round is a 400 that lists the valid ones.
- A query runs no simulation, changes nothing and costs no round. Queries are counted and recorded; they do not change
  the grading. After adaptation has ended a query is refused (409).
- Nothing else changes: deployments return the same noisy feedback, and no answer holds a score, a success flag, the
  hidden dynamics or anything about the held-out cases.

## Others
- Initial x/y and pad x/y are sampled in [-1, 1] m, conditioned on at least 0.5 m horizontal separation. Initial
  body-origin height is 0.8–1.5 m. Episodes last 16 s.
- The nominal model includes published mass and thrust calibration; inertias and geometry are approximate. This task
  does not claim a fully calibrated airframe.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the deployment service
  too, deployments included). At the end you are stopped without warning and the evaluator takes the round you sealed
  or, if you sealed none, the latest deployment that completed before then; a deployment still running is not graded.
  Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's own deadline counts the same
  limit from your first request to it. Calls into a long-running process can block for their whole wait time: use short
  waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: deployments are your only runs, each starting its development cases afresh.
- Rounds: three deployment rounds (`describe` has what is left).
