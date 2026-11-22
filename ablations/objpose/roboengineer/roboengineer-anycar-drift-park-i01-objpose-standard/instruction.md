# roboEngineer · anycar-drift-park (standard)

## Task
A simulated AnyCar racing car (an RC car; MuJoCo). Follow the ordered U-bend, then slide sideways into a
parallel-parking space between two stationary cars and hold a precise stop. You tune its numeric controller on the
public nominal model in your container and deploy it to a hidden evaluator whose dynamics differ in ways you are not
told; the evaluator runs as a service you reach only through its client.

## Goal
Success: the car completes the ordered U-route, then slides sideways into the parking bay in a real drift (a sustained
sideways slide near the bay, not just steering in), and stops with the whole car inside the bay, close to its centre and
its heading, standing still for the last half second. A collision, a rollover, the chassis touching the ground or
leaving the route fails. A successful case scores higher the closer the car stops to the bay's centre and heading; any
other scores zero. The evaluator runs the policy you select on 10 held-out cases (new episodes of the same hidden plant,
never shown to you): success needs every case to pass, and `final_reward` reports the mean score (0-100).

Deliverable: the policy of one completed deployment round. `seal(round_id, summary)` selects it (once; it ends
adaptation). If you seal none, the latest round completed before the cutoff counts; with no completed round the score is
zero. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact
response and image bytes.

Real-robot rules:
- No reset: deployments are your only runs on the hidden evaluator, at most three rounds, each on the same 3 development
  cases from their start; no reset or privileged-state endpoint exists.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own fitting, training and analysis code; do not use published or reference solutions, trained policies for
  this task, or hidden evaluator information.

## Robot Interface
### Client
- `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds.
- `deploy(policy, diagnosis)` for one deployment round: it runs your policy on the development cases and returns their
  feedback. A diagnosis should briefly state the observed failure, proposed change and expected effect.
- A deployment can take minutes: if your tool call times out and the response is lost, `result(round_id)` returns that
  completed round's stored response again (it runs nothing).
- `seal(round_id, summary)` selects a completed round for grading.
- The service: `http://127.0.0.1:8000`; it accepts data-only policies.

### Training
Use the public nominal model and write fitting/optimization code locally. Submit the documented numeric controller
parameters. This track evaluates adaptation within a fixed controller ABI; it does not deploy arbitrary controller
Python. Run `python -m control_public.anycar_drift_nominal --out /app/output/nominal` for local nominal rollouts. The
public numeric ABI is in `control_public.anycar_drift`.

### Feedback
Each round reuses the same 3 development cases. Each response preserves the public course in `feedback.command`, all 161
noisy telemetry rows and all 161 video frames at 10 Hz through 16 seconds. Use the course to distinguish changes in the
parking target from changes in vehicle response. An episode that crashes, leaves its course or arena, or makes the
simulation diverge ends at that moment: its telemetry and frames stop there. Diagnose failures from the returned video
frames and noisy telemetry, then revise.

### This run: privileged state queries
This run lets you read the simulator's true state during your development episodes.

- `GET /state/entities` (in Python: `Client().state_entities()`) lists what you can query:
  `{"frame", "quaternion_order", "entities": {name: {"kind", "fields": {field: unit}, "static"}}, "rounds"}`. The kinds
  are `robot` (the robot's base or root, the car, the drone), `object` (parked cars) and `scene_feature` (poles, a
  parking slot, a curb, a pad). `rounds` lists the completed rounds you can query.
- `POST /state/query` with `{"names": [...], "fields": [...], "round_id": ..., "case": ..., "t": ...}` (in Python:
  `Client().state_query(["car"], case=0)`) answers
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
- Modeling limitations: Rigid RC tire contact and rear-wheel dry-friction brake; not a calibrated pneumatic-tire
  drifting or vehicle-damage model.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the deployment service
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
- Resources: 2 CPUs, 6 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: deployments are your only runs, each starting its development cases afresh.
- Rounds: at most three deployment rounds (`Client().describe()` has what is left).
