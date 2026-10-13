# g1

Train a blind 29-DoF Unitree G1 policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo over flat, sloped, rough and stepped terrain. Stand 2 s, then follow a public forward velocity command of 0.5–0.65 m/s for 18 s.

## Train, deploy, inspect and revise
Train in your local nominal model. Linearbot: `python -m locomanipbench.imitation_train --robot linearbot --out /app/output/initial --device cuda:0`, then `CONTROL_INITIAL_POLICY=/app/output/initial/policy.npz python -m locomanipbench.train --robot linearbot --out /app/output/trained --device cuda:0`. G1: `python -m sim2realbench.g1.train --out /app/output/trained --gpu 0`. You may edit training code. Submit the exported `policy.npz` using `client.artifact(path)`. The fixed actor shape/activation and PD wrapper are the deployment ABI; editing them locally does not change evaluation. Record actual training steps and hardware.

Use `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds. Call `deploy(policy, diagnosis)` for up to three rounds. Each round reuses the same 4 development cases. Diagnose failures from the returned video frames and noisy telemetry, then revise. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact response and image bytes. A diagnosis should briefly state the observed failure, proposed change and expected effect.

`seal(round_id, summary)` selects a completed round. No held-out feedback is returned. At agent exit the evaluator uses the sealed round or the latest round completed before cutoff; no eligible round scores zero. Hidden simulation runs in a separate container and accepts data-only policies. Network endpoint: `http://127.0.0.1:8000`. No reset or privileged-state endpoint exists.

## Verification and score
100 * walking survival fraction * exp(-speed MAE/commanded speed) * clipped forward-progress fraction. Success requires full 20 s survival, speed MAE<0.25 m/s, forward travel>65% of commanded walking distance, lateral drift<2 m. Standing still scores zero.
The selected policy is tested on 12 disjoint cases in two fresh processes. Binary success requires all cases to pass; `final_reward` reports the continuous mean score. Evaluation dynamics, seeds, true state, contacts and grades are never returned during adaptation.

## Modeling limitations
Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor and public PD wrapper. Coding-agent feedback is noisy joint angles, public commands and images; reference solvability remains incomplete on the second plant.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **24 GiB of GPU memory**, **20 GiB of memory**, **512 processes** and **40 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
