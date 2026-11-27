# roboEngineer · anycar-compact-lap-silverstone-8 (standard)

## Task
Drive the car round one lap of the small F1-style track, keeping up with the moving target that sets the pace, without a
collision or leaving the track.

## Goal
Success: the car passes every gate of the lap in order near the centre line and keeps close to the moving target the
whole lap, at its heading and speed, and ends close to it. A collision, a rollover or leaving the track fails. The
evaluator runs the policy you select on 10 held-out cases: new episodes of the same hidden plant, never shown to you.
Success needs every case to pass; `final_reward` reports the mean score (0-100).

Deliverable: the policy of one completed deployment round. Choose that round with `seal(round_id, summary)`. You can
seal only once, and sealing ends adaptation. If you seal none, the latest round completed before the cutoff counts; with
no completed round the score is zero. Preserve code, training logs, policies and exact feedback under `/app/output/`.
The client saves the exact response and image bytes.

Rules:
- **No cheating.** Write your own fitting, training and analysis code. Do not search for, download or use any existing
  solution (published or reference solutions, trained policies for this task) or hidden evaluator information; trials
  are reviewed.
- No reset: deployments are your only runs on the hidden evaluator. You get at most three rounds, each on the same 3
  development cases from their start. There is no reset or privileged-state endpoint.
- A deployment returns only noisy telemetry and camera frames. It never returns the evaluation dynamics, seeds, true
  state, contacts or grades, nor anything about the held-out cases.

## Robot Interface
A simulated AnyCar racing car (an RC car; MuJoCo). You tune its numeric controller on the public nominal model in your
container. Then you deploy it to a hidden evaluator whose dynamics differ in ways you are not told. The evaluator runs
as a service that you reach only through its client.

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
Python. Run `python -m scripts.control_transfer.control_public.anycar_nominal --out /app/output/nominal` for local
nominal rollouts. The public controller ABI is in `control_public.anycar`. Use `--track silverstone-8 --compact-30s` for
nominal training. The public route is a compact 45 m F1-inspired approximation, targeted at a 28 s lap with a hard 30 s
episode.

### Feedback
Each round reuses the same 3 development cases. Feedback includes all 301 noisy rows and 31 one-second images covering 0
through 30 s. An episode that crashes, leaves its course or arena, or makes the simulation diverge ends at that moment:
its telemetry and frames stop there. Diagnose failures from the returned video frames and noisy telemetry, then revise.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the deployment service
  too, deployments included). At the end you are stopped without warning and the evaluator takes the round you sealed
  or, if you sealed none, the latest deployment that completed before then; a deployment still running is not graded.
  Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's own deadline counts the same
  limit from your first request to it. Calls into a long-running process can block for their whole wait time: use short
  waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 6 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: deployments are your only runs, each starting its development cases afresh.
- Rounds: at most three deployment rounds (`Client().describe()` has what is left).
