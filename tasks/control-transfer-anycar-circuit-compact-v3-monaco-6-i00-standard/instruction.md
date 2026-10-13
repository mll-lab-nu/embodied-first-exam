# anycar-circuit-compact-v3-monaco-6

Track a complete compact F1-inspired lap, targeted at 28 seconds within a 30-second episode, avoiding collisions/offtrack.

## Train, deploy, inspect and revise
Use the public nominal model and write fitting/optimization code locally. Submit the documented numeric controller parameters. This track evaluates adaptation within a fixed controller ABI; it does not deploy arbitrary controller Python. Run `python -m scripts.control_transfer.control_public.anycar_nominal --out /app/output/nominal` for local nominal rollouts. The public controller ABI is in `control_public.anycar`. Use `--track monaco-6 --compact-30s` for nominal training. The public route is a compact 45 m F1-inspired approximation, targeted at a 28 s lap with a hard 30 s episode. Every ordered gate and the finish must be crossed. Feedback includes all 301 noisy rows and 31 one-second images covering 0 through 30 s; operator videos retain all 301 frames. Smoothing and aspect widening can remove sharp turns and crossovers; the original F1 outline is not preserved.

Use `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds. Call `deploy(policy, diagnosis)` for up to three rounds. Each round reuses the same 3 development cases. Diagnose failures from the returned video frames and noisy telemetry, then revise. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact response and image bytes. A diagnosis should briefly state the observed failure, proposed change and expected effect.

`seal(round_id, summary)` selects a completed round. No held-out feedback is returned. At agent exit the evaluator uses the sealed round or the latest round completed before cutoff; no eligible round scores zero. Hidden simulation runs in a separate container and accepts data-only policies. Network endpoint: `http://127.0.0.1:8000`. No reset or privileged-state endpoint exists.

## Verification and score
Ordered completion and time-indexed position/heading/speed accuracy. Safety violation gives zero. No nearest-waypoint score.
The selected policy is tested on 10 disjoint cases in two fresh processes. Binary success requires all cases to pass; `final_reward` reports the continuous mean score. Evaluation dynamics, seeds, true state, contacts and grades are never returned during adaptation.

## Modeling limitations
Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No AnyCar learned transformer is evaluated. F1-inspired: periodic smoothing and minor-axis widening, then 45m normalization. Not exact scaled circuit outlines; tight corners/crossovers may be removed.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **4 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
