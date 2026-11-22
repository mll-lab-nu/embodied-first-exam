# g1-terrain-walk

Train a blind 29-DoF Unitree G1 policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo over flat, sloped, rough and stepped terrain. Stand 2 s, then follow a public forward velocity command of 0.5–0.65 m/s for 18 s.

## Train, deploy, inspect and revise
Train the public terrain curriculum with `python -m control_public.g1_training --upstream /opt/control-assets/unitree_rl_mjlab --out /app/output/trained --gpu 0`. You may edit training code. Submit the exported `policy.npz` using `client.artifact(path)`. The fixed actor architecture and PD wrapper are the deployment ABI. Record actual training steps, logs and hardware. Your container has one NVIDIA GPU (`cuda:0`); measured on an L40S, the trainer's default 256 environments take about 2 GB of GPU memory and 1.1-1.4 s per PPO iteration, 1024 environments (its cap) about 5 GB and 1.4 s, 4096 environments about 17 GB and 2.0-2.5 s, at about one CPU core.

Use `from control_public.client import Client, artifact`; `Client().describe()` provides the public defaults and bounds. Call `deploy(policy, diagnosis)` for up to three rounds. A deployment can take minutes: if your tool call times out and the response is lost, `result(round_id)` returns that completed round's stored response again (it runs nothing). An episode that crashes, leaves its course or arena, or makes the simulation diverge ends at that moment: its telemetry and frames stop there. Each round reuses the same 4 development cases. Diagnose failures from the returned video frames and noisy telemetry, then revise. Preserve code, training logs, policies and exact feedback under `/app/output/`. The client saves the exact response and image bytes. A diagnosis should briefly state the observed failure, proposed change and expected effect.

`seal(round_id, summary)` selects a completed round. No held-out feedback is returned. At agent exit the evaluator uses the sealed round or the latest round completed before cutoff; no eligible round scores zero. Hidden simulation runs in a separate container and accepts data-only policies. Network endpoint: `http://127.0.0.1:8000`. No reset or privileged-state endpoint exists.

## Verification and score
100 * walking survival fraction * exp(-speed MAE/commanded speed) * clipped forward-progress fraction. Success requires full 20 s survival, speed MAE<0.25 m/s, forward travel>65% of commanded walking distance, lateral drift<2 m. Standing still scores zero.
The selected policy is tested on 12 disjoint cases in two fresh processes. Binary success requires all cases to pass; `final_reward` reports the continuous mean score. Evaluation dynamics, seeds, true state, contacts and grades are never returned during adaptation.

## Modeling limitations
Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor and public PD wrapper. Coding-agent feedback is noisy joint angles, public commands and images.

## This run: unlimited resets, save and load

This run raises the deployment budget and adds two calls. This section overrides anything above, and anything in
`/describe`, that says there are three rounds, or that no reset exists.

- You have 1003 deployment rounds (`max_rounds` in `/describe`): in practice as many as your time allows. Every
  deployment starts each development case afresh from its starting state (that is the reset); the cases and the hidden
  dynamics stay the same.
- `POST /save_state` with `{"round_id": 0, "case": 0, "t": 4.0}` names the state of that completed development
  episode at its telemetry time at or before `t` seconds and answers `{"handle": "s1", "t": ...}`. The handle is all
  you get, never the state's contents. At most 32 handles are kept (the least recently used one is dropped).
- `POST /load_state` with `{"handle": "s1"}` makes your next deployment run only that case, starting from that saved
  state, with the policy you deploy taking over there. The controller's run-time state (its phase, timers,
  integrators, last action) carries over; its parameters are the new policy's. The loaded deployment's feedback covers
  the whole episode, the saved path included, and its answer has `start` and `load_verified`. `{"handle": null}`
  cancels a pending load. Saves and loads cost no round. In Python: `c.save_state(round_id, case, t)`, `c.load_state(handle)`, then `c.deploy(policy, diagnosis)`.
- Grading is unchanged: the selected round's policy (sealed, or else the latest completed round) runs every held-out
  case from its start, as described above; a policy deployed after a load is evaluated like any other.
- Your time keeps running across deployments, saves and loads.

## This run: privileged state queries

This run lets you read the simulator's true state during your development episodes. This section overrides anything
above, and anything in `/describe`, that says the true state is never returned during adaptation.

- `GET /state/entities` (in Python: `Client().state_entities()`) lists what you can query: `{"frame", "quaternion_order", "entities": {name:
  {"kind", "fields": {field: unit}, "static"}}, "rounds"}`. The kinds are `robot` (the robot's base or root, the
  car, the drone), `object` (parked cars) and `scene_feature` (poles, a parking slot, a curb, a pad). `rounds` lists the
  completed rounds you can query.
- `POST /state/query` with `{"names": [...], "fields": [...], "round_id": ..., "case": ..., "t": ...}` (in Python:
  `Client().state_query(["robot"], case=0)`) answers `{"round_id", "cases": [{"case", "t": [...], "state": {name: {field: [one value per time]}}}],
  "state_queries"}`: the state of that round's development episodes at their telemetry times, that is the true pose
  and velocity of each body and the robot's joints as its encoders read them (the same readings as the telemetry).
  Only `names` is required: `fields` defaults to every field, `round_id` to the latest completed round, `case` to every
  development case of that round, and `t` (seconds, or a window `[t0, t1]`) to every sample. A `static` entity gives
  one value instead of a list.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s (both in the
    world frame), `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents along
    the body's axes), `bbox` [[x, y, z] min, [x, y, z] max] m. Each field's unit is in the list.
  - An unknown name, field or round is a 400 that lists the valid ones.
- A query runs no simulation, changes nothing and costs no round. Queries are counted and recorded; they do not change
  the grading. After adaptation has ended a query is refused (409).
- Nothing else changes: deployments return the same noisy feedback, and no answer holds a score, a success flag, the
  hidden dynamics or anything about the held-out cases.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **12 GiB of memory**, **1024 processes and threads**, **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`) and **one GPU, 20 GiB of its memory**. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the deployment service counts, deployments included. When it is up you are stopped without warning and the evaluator takes the round you sealed or, if you sealed none, the latest deployment that completed before that moment; a deployment still running then is not graded. The service's own deadline counts the same limit from your first request to it, so it never runs out before your time does. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
