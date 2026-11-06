# neuralfly-general-skydio

Track six timed laps of a randomized figure eight: vertical, horizontal or inclined plane; yaw in [-pi,pi]; both traversal directions; half extents 0.9-1.5 m and 0.45-0.85 m; angular rate 0.8-1.1 rad/s; randomized phase, center and initial offset. Follow the provided world-frame position, velocity and acceleration commands.

## Train, deploy, inspect and revise
Use the public nominal model and write fitting/optimization code locally. Submit the documented numeric controller parameters. This track evaluates adaptation within a fixed controller ABI; it does not deploy arbitrary controller Python. The reference and controller are in `control_public.fly`; a public nominal simulator is provided in `nominal_fly.py`. This observation revision uses Skydio X2 appearance at 960 by 720 pixels, with unchanged surrogate dynamics and noisy-sensor/controller interfaces. Public mesh assets are preinstalled; no download is required.

Use `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds. Call `deploy(policy, diagnosis)` for up to three rounds. A deployment can take minutes: if your tool call times out and the response is lost, `result(round_id)` returns that completed round's stored response again (it runs nothing). An episode that crashes, leaves its course or arena, or makes the simulation diverge ends at that moment: its telemetry and frames stop there. Each round reuses the same 5 development cases. Diagnose failures from the returned video frames and noisy telemetry, then revise. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact response and image bytes. A diagnosis should briefly state the observed failure, proposed change and expected effect.

`seal(round_id, summary)` selects a completed round. No held-out feedback is returned. At agent exit the evaluator uses the sealed round or the latest round completed before cutoff; no eligible round scores zero. Hidden simulation runs in a separate container and accepts data-only policies. Network endpoint: `http://127.0.0.1:8000`. No reset or privileged-state endpoint exists.

## Verification and score
Crash or escape: 0. Otherwise 100 exp(-max(0,RMSE_m-0.03)/0.25). Success requires the full horizon and RMSE<0.25 m; acquisition is included.
The selected policy is tested on 10 disjoint cases in two fresh processes. Binary success requires all cases to pass; `final_reward` reports the continuous mean score. Evaluation dynamics, seeds, true state, contacts and grades are never returned during adaptation.

## Modeling limitations
Flight-data quadratic force surrogate and approximate rigid-body/actuator dynamics; not a learned aerodynamics model or flight-stack simulation. Fixed 50-degree command tilt envelope; 2.2 thrust-to-weight limit. Skydio X2 appearance only; the underlying Neural Fly surrogate is not calibrated Skydio dynamics.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **6 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the deployment service counts, deployments included. When it is up you are stopped without warning and the evaluator takes the round you sealed or, if you sealed none, the latest deployment that completed before that moment; a deployment still running then is not graded. The service's own deadline counts the same limit from your first request to it, so it never runs out before your time does. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
