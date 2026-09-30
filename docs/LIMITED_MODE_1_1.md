# Limited mode 1.1

Extends `rcb-limited/1.0`, the RoboTwin limited twins' first protocol (they have since moved to 2.x): the
simulator runs in a `sim` sidecar the agent cannot open, the agent only has an HTTP client, and the sidecar
records, replays and grades the episode. Code: `scripts/limited/` (service, verifier, client) plus one adapter
per simulator, `scripts/<sim>/shared/limited/server.py`.

## What 1.1 adds (all optional; 1.0 clients are unaffected)

| feature | how | semantics |
|---|---|---|
| batch step | `r.step("qpos", A)`, A of shape (K, D) | runs in order; a bad row rejects the whole batch; stops at episode end, or at a step the robot could not carry out (`obs["executed"]`; a kinematic robot's refused move: `obs["blocked"]`); same physics as K single steps |
| images on demand | `images=True \| False \| ["cam"]` on `step`/`reset`, `?images=` on `/observe` | proprioception is always included |
| reset budget | `RCB_RESET_BUDGET` in `docker-compose.yaml`, default 0 | the agent reads it in `spec()["budget"]["reset"]` and `obs["resets_left"]`; each reset restarts the recording; the trial ends at the first success; the last episode is graded |

Sensors are adapter config, not protocol (HumanoidBench: `RCB_OBS_PROPRIO` / `RCB_OBS_IMU` /
`RCB_OBS_ROOM_CAMERA` / `RCB_OBS_DEPTH`, defaults 1/0/0/0; depth comes with each head-camera image, in metres). Every knob is `${NAME:-default}` in the compose file, so a run sets it
from the shell (`RCB_RESET_BUDGET=3 RCB_OBS_IMU=1 harbor run ...`) or from a profile, compose overrides that
`harbor run -c` merges in: `scripts/humanoidbench/configs/limited.yaml` (reset 50, IMU, room camera: the standard
run), `limited-depth.yaml` (the same plus depth). The sim logs the resulting `/spec`. Where `room_camera` stands and,
where a task needs more pixels, the image size are per task and fixed in the compose file (`RCB_ROOM_CAMERA_POSE`,
`RCB_IMAGE_HW`: cube 512, the rest upstream's 256).

At the end of an episode the agent gets only `done` + `reason` (`success | failed | timeout | error`),
never a reward or a return.

The agent-facing API is documented in one place, `rcb_client.py`'s docstring: every call, `images=`, the
observation fields, the errors. `instruction.md` points to it and keeps only task facts: the task, the rules,
the scoring prose. Anything that belongs to the robot or to the run, the agent reads from `spec()`: the reset
budget, which sensors are on, and what a real robot's documentation (its URDF) would give. The HumanoidBench adapter
reads those facts off the model: each servo's range in radians, each joint's axis and position, each link's mass and
centre of mass, the feet's collision boxes, the IMU's frame and which way each reading goes, and each camera's field of
view and pose (position; forward, up and right axes). The service's clock
(`time_s`, `elapsed_s`) starts at the agent's first request, not when the service came up about a minute earlier.

The trial ends when the agent's session does. The collect hook's SIGUSR1 comes only once the verifier starts,
about 12 s later, so the repo's agent adapters send it themselves when the session ends
(`harbor_agents/limited.py`). Otherwise a script the agent left running keeps driving the robot in that gap.

## Fixed from 1.0
1.0 renders the replay video on a background thread; GL contexts are per thread, so MuJoCo videos come out
all black (SAPIEN/Vulkan is unaffected). Its SIGUSR1 handler also takes the lock, which can deadlock mid-request.
1.1 keeps everything on the main thread: the signal sets a flag; wrap-up and finalize run in
`HTTPServer.service_actions`, only after the signal, so the service keeps answering while the agent is still there.

## Across simulators
- **One directory per (task, mode) is what Harbor needs**: the agent image, compose, verifier, `task.toml` and
  instruction all differ. Keep one source per task and generate both, as `scripts/humanoidbench/gen_tasks.py`
  already does. Pick the mode at run time: `harbor run -p tasks -i '*-limited'` (or `-x '*-limited'`).
- **Shared**: `rcb_service.py`, `rcb_client.py`, `tests/`, the agent Dockerfile, the `task.toml` blocks.
  **Per simulator**: one adapter implementing the `Sim` contract in `rcb_service.py` (both `Session` classes
  already cover most of it). **Per task**: compose env and `instruction.md` (task facts only).
- **Done for HumanoidBench and KinDER**: each `gen_tasks.py` renders the limited twins (KinDER: one adapter per robot) from its
  `templates/limited/` and `shared/limited/` (the adapter, the client's docstring) plus `scripts/limited/`, which
  holds what every simulator shares: `rcb_service.py`, the verifier and the client's code.
