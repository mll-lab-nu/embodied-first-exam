# roboEngineer · g1-terrain-walk (standard)

## Task
A simulated 29-DoF Unitree G1 humanoid (MuJoCo). Train a blind 29-DoF Unitree G1 policy in mjlab/MuJoCo Warp and
transfer to CPU MuJoCo over flat, sloped, rough and stepped terrain. Stand 2 s, then follow a public forward velocity
command of 0.5–0.65 m/s for 18 s. You tune its numeric controller on the public nominal model in your container and
deploy it to a hidden evaluator whose dynamics differ in ways you are not told; the evaluator runs as a service you
reach only through its client.

## Goal
Success: the G1 stays up for the whole 20 s on every kind of terrain: it stands for the first 2 s, then walks forward
close to the commanded speed, covering most of the commanded distance without drifting far sideways. The score grows
with the time it stays up, how closely it holds the speed and the distance it covers; standing still scores zero. The
evaluator runs the policy you select on 12 held-out cases (new episodes of the same hidden plant, never shown to you):
success needs every case to pass, and `final_reward` reports the mean score (0-100).

Deliverable: the policy of one completed deployment round. `seal(round_id, summary)` selects it (once; it ends
adaptation). If you seal none, the latest round completed before the cutoff counts; with no completed round the score is
zero. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact
response and image bytes.

Real-robot rules:
- Deployment rounds: as many as your time allows, with save and load of development episodes (Robot Interface,
  `### This run: unlimited resets, save and load`); grading is unchanged: the round you seal (or else the latest
  completed one) is graded.
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
Train the public terrain curriculum with
`python -m control_public.g1_training --upstream /opt/control-assets/unitree_rl_mjlab --out /app/output/trained --gpu 0`.
You may edit training code. Submit the exported `policy.npz` using `client.artifact(path)`. The fixed actor architecture
and PD wrapper are the deployment ABI. Record actual training steps, logs and hardware. Your container has one NVIDIA
GPU (`cuda:0`); measured on an L40S, the trainer's default 256 environments take about 2 GB of GPU memory and 1.1-1.4 s
per PPO iteration, 1024 environments (its cap) about 5 GB and 1.4 s, 4096 environments about 17 GB and 2.0-2.5 s, at
about one CPU core.

### Feedback
Each round reuses the same 4 development cases. An episode that crashes, leaves its course or arena, or makes the
simulation diverge ends at that moment: its telemetry and frames stop there. Diagnose failures from the returned video
frames and noisy telemetry, then revise.

### This run: unlimited resets, save and load
This run raises the deployment budget and adds two calls.

- You have 1003 deployment rounds (`max_rounds` in `/describe`): in practice as many as your time allows. Every
  deployment starts each development case afresh from its starting state (that is the reset); the cases and the hidden
  dynamics stay the same.
- `POST /save_state` with `{"round_id": 0, "case": 0, "t": 4.0}` names the state of that completed development episode
  at its telemetry time at or before `t` seconds and answers `{"handle": "s1", "t": ...}`. The handle is all you get,
  never the state's contents. At most 32 handles are kept (the least recently used one is dropped).
- `POST /load_state` with `{"handle": "s1"}` makes your next deployment run only that case, starting from that saved
  state, with the policy you deploy taking over there. The controller's run-time state (its phase, timers, integrators,
  last action) carries over; its parameters are the new policy's. The loaded deployment's feedback covers the whole
  episode, the saved path included, and its answer has `start` and `load_verified`. `{"handle": null}` cancels a pending
  load. Saves and loads cost no round. In Python: `c.save_state(round_id, case, t)`, `c.load_state(handle)`, then
  `c.deploy(policy, diagnosis)`.
- Grading is unchanged: the selected round's policy (sealed, or else the latest completed round) runs every held-out
  case from its start, as described above; a policy deployed after a load is evaluated like any other.
- Your time keeps running across deployments, saves and loads.

## Others
- Modeling limitations: Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor and public PD wrapper.
  Coding-agent feedback is noisy joint angles, public commands and images.

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
- Resources: 4 CPUs, 12 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (20 GiB of its memory); the simulator runs in its own container and does not count. Over a cap a process can
  be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: every deployment starts its development cases afresh from their starting state; save and load as in Robot
  Interface.
- Rounds: as many as the ablation section in Robot Interface gives.
