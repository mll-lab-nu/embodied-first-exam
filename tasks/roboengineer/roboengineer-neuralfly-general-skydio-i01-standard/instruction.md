# roboEngineer · neuralfly-general-skydio (standard)

## Task
A simulated quadrotor (the Neural Fly airframe with a flight-log force surrogate). Track six timed laps of a randomized
figure eight: vertical, horizontal or inclined plane; yaw in [-pi,pi]; both traversal directions; half extents 0.9-1.5 m
and 0.45-0.85 m; angular rate 0.8-1.1 rad/s; randomized phase, center and initial offset. Follow the provided
world-frame position, velocity and acceleration commands. You tune its numeric controller on the public nominal model in
your container and deploy it to a hidden evaluator whose dynamics differ in ways you are not told; the evaluator runs as
a service you reach only through its client.

## Goal
Success: the drone flies all six timed laps of its figure eight without crashing or escaping, staying close to the
moving reference throughout, the first approach to it included. The score grows the closer it tracks; a crash or an
escape scores zero. The evaluator runs the policy you select on 10 held-out cases (new episodes of the same hidden
plant, never shown to you): success needs every case to pass, and `final_reward` reports the mean score (0-100).

Deliverable: the policy of one completed deployment round. `seal(round_id, summary)` selects it (once; it ends
adaptation). If you seal none, the latest round completed before the cutoff counts; with no completed round the score is
zero. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact
response and image bytes.

Real-robot rules:
- No reset: deployments are your only runs on the hidden evaluator, at most three rounds, each on the same 5 development
  cases from their start; no reset or privileged-state endpoint exists.
- No privileged state: a deployment returns noisy telemetry and camera frames only; the evaluation dynamics, seeds, true
  state, contacts and grades are never returned, and nothing about the held-out cases.
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
Python. The reference and controller are in `control_public.fly`; a public nominal simulator is provided in
`nominal_fly.py`. Public mesh assets are preinstalled; no download is required.

### Feedback
Each round reuses the same 5 development cases. The camera frames show the Skydio X2 at 960 by 720 pixels, with
unchanged surrogate dynamics and noisy-sensor/controller interfaces. An episode that crashes, leaves its course or
arena, or makes the simulation diverge ends at that moment: its telemetry and frames stop there. Diagnose failures from
the returned video frames and noisy telemetry, then revise.

## Others
- Modeling limitations: Flight-data quadratic force surrogate and approximate rigid-body/actuator dynamics; not a
  learned aerodynamics model or flight-stack simulation. Fixed 50-degree command tilt envelope; 2.2 thrust-to-weight
  limit. Skydio X2 appearance only; the underlying Neural Fly surrogate is not calibrated Skydio dynamics.

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
