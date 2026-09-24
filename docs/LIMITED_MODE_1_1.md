# Limited mode 1.1

Extends kangrui's `rcb-limited/1.0` (dev/kangrui): the simulator runs in a `sim` sidecar the agent cannot open,
the agent only has an HTTP client, and the sidecar records, replays and grades the episode.
Reference implementation: `tasks/humanoidbench-loco-sit-simple-i00-limited/` — `environment/sim/rcb_service.py`
is simulator-agnostic, `environment/sim/server.py` is the HumanoidBench adapter.

## What 1.1 adds (all optional; 1.0 clients are unaffected)

| feature | how | semantics |
|---|---|---|
| batch step | `r.step("qpos", A)`, A of shape (K, D) | runs in order; a bad row rejects the whole batch; stops at episode end (`obs["executed"]`); same physics as K single steps |
| images on demand | `images=True \| False \| ["cam"]` on `step`/`reset`, `?images=` on `/observe` | proprioception is always included |
| reset budget | `RCB_RESET_BUDGET` in `docker-compose.yaml`, default 0 | the agent reads it in `spec()["budget"]["reset"]` and `obs["resets_left"]`; each reset restarts the recording; the trial ends at the first success; the last episode is graded |

Sensors are adapter config, not protocol (HumanoidBench: `RCB_OBS_PROPRIO` / `RCB_OBS_IMU` /
`RCB_OBS_ROOM_CAMERA`, defaults 1/0/0). Every knob is `${NAME:-default}` in the compose file, so a run sets it
from the shell (`RCB_RESET_BUDGET=3 RCB_OBS_IMU=1 harbor run ...`); the sim logs the resulting `/spec`.

At the end of an episode the agent gets only `done` + `reason` (`success | failed | timeout | error`),
never a reward or a return.

The agent-facing API is documented in one place, `rcb_client.py`'s docstring: every call, `images=`, the
observation fields, the errors. `instruction.md` points to it and keeps only task facts.

## Fixed from 1.0
1.0 renders the replay video on a background thread; GL contexts are per thread, so MuJoCo videos come out
all black (SAPIEN/Vulkan is unaffected). Its SIGUSR1 handler also takes the lock, which can deadlock mid-request.
1.1 keeps everything on the main thread: the signal sets a flag; wrap-up and finalize run in
`HTTPServer.service_actions`.

## Cost (HumanoidBench sit_simple, RTX 4090, EGL)
0.39 ms/step physics · 1.2 ms/step one action per request · 4.3 ms/step with both head-camera images · ~0.5 ms/step
in batches of 10 or more.

## Making it repo-wide (later)
- **One directory per (task, mode) is what Harbor needs**: the agent image, compose, verifier, `task.toml` and
  instruction all differ. Keep one source per task and generate both, as `scripts/humanoidbench/gen_tasks.py`
  already does. Pick the mode at run time: `harbor run -p tasks -i '*-limited'` (or `-x '*-limited'`).
- **Shared**: `rcb_service.py`, `rcb_client.py`, `tests/`, the agent Dockerfile, the `task.toml` blocks.
  **Per simulator**: one adapter implementing the `Sim` contract in `rcb_service.py` (both `Session` classes
  already cover most of it). **Per task**: compose env and `instruction.md` (task facts only).
- **Next**: RoboTwin swaps its `server.py` for `rcb_service.py` + an adapter; HumanoidBench moves this task
  into `templates/` + `shared/` and renders the other families.
