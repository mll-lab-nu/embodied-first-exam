# embodied_first_exam/standard/: the service layers

The reference implementation of the `eai-standard/3.0` wire protocol. What a service answers is specified in
[docs/protocol/eai-standard.md](../../docs/protocol/eai-standard.md). This page is how the layers here implement it:
which file serves which capability, how a benchmark plugs in, and how a crashed service resumes its episode. None of
it is a rule a task must follow.

## The layers

| Layer | Files | Serves |
|---|---|---|
| sidecar | `sidecar/rcb_service.py`, `sidecar/rcb_client.py` (and `sidecar/clients/<name>/`), `sidecar/grade.py` | the base and the reset capability |
| shared | `rcb_limited.py`, `rcb_client.py`, `rcb1.py`, `run.sh`, `agent_end/rcb_agent_end.py` | the base and the shared capability |
| realtime | `realtime/rcb_realtime.py`, `realtime/rcb_client.py`, over `sidecar/rcb_service.py` | the base, the reset capability and the realtime capability |
| operations | `operations/rcb_limited.py`, `operations/rcb_client.py`, with the shared layer's `rcb1.py`, `run.sh` and `agent_end/` | the shared capability and the operations capability (standard mode only) |
| MCP | `mcp/server.py` and its modules, `mcp/inject.py` | every agent-facing endpoint as an MCP tool |

Also here:

- `live_video.py`: the live video several sim services film.
- `toy_server.py`: the smallest complete shared-layer adapter.
- `client.env`: the one client base image, pinned by digest. `client-requirements.txt`: the client's exact pins.

Other services that speak the same protocol:

- the benchmarks' own servers, which serve the base with their own action layouts, control rates and cameras:
  RoboTwin 2.0 (`benchmarks/robotwin-2/sim/server.py`), DexToolBench and MuJoCo Playground
  (`benchmarks/dextoolbench/sim/server_mj.py`, one file), MetaWorld+ (`benchmarks/metaworldplus/sim/server_mw.py`),
  RoboCasa and RoboCasa-GR1 (`benchmarks/robocasa/sim/server_casa.py`);
- the match extension, `benchmarks/embodied-olympics-match/eai_std/`, copied unchanged into each match task's
  `environment/sim/eai_std/` by `apply_eai_std.py` there
  (`ci_checks/benchmarks/embodied-olympics-match/invariant-eai-std.py`). The match's `core/` stays as exported.

The sidecar layer runs, with each benchmark's adapter: KinDER, HumanoidBench, Panda Dynamic Scenes, LIBERO-MAX,
VLABench, BiGym 2.0, Embodied Olympics - Fun, Embodied Safety Exam, HumanCLAW, and the realtime tasks of RoboCasa365,
MyoSuite and MuJoCo Playground. ABC Sim's realtime tasks run a byte-identical copy built into its base image
(`images/abc-sim/tools/realtime/`). `scripts/task_conventions.py` `service_layer` says which tasks are on the shared
layer.

## How tasks get the files

Tasks carry no copies. Every standard and realtime task's Dockerfiles take the files unchanged from the files-only
image `standard-files` (`COPY --from=<image@digest>`, `images/standard-files/FILES.json`):

- the agent's container: the client (`rcb_client.py`, `rcb1.py`) to `/opt/tools/`, and the MCP server to
  `/opt/tools/efe_mcp/`;
- the sidecar: the service layer to `/srv/` (for the shared layer: `rcb_limited.py`, `rcb1.py`, `run.sh`, and
  `rcb_agent_end.py`).

`ci_checks/check-tooling-identity.sh` checks the pins, that no benchmark carries a copy, and that a base image's copy
is byte-identical to the source. A change to a file here needs a new `standard-files` version (build, push, pin:
[docs/operations.md](../../docs/operations.md#files-only-images)).

A benchmark adds only its adapter: `server.py` in `embodied_first_exam/benchmarks/<benchmark>/sim/` (taken from the
benchmark's files-only image) or in the task's `environment/sim/`.

## The shared layer

`rcb_limited.py` is the service layer: HTTP, RCB1 responses, the protocol helpers, the `/spec` self-check
(`check_spec`), crash recovery. The adapter supplies the robot, the cameras and the clock.

**Design principles.**

1. *A robot, not a simulator.* No state query and no success query. Resets only within the task's declared budget.
   The wall clock is the budget, and actions and simulated time are reported as cost. The agent ends the episode
   (`/finish`), and the state it ends in is judged.
2. *One information line.* The agent may know the robot and its sensors (spec sheet, kinematics, camera calibration,
   proprioception), never the world's ground truth.
3. *Everything new is optional.* Depth, for example, costs a render and is off by default.
4. *Binary data, kept by the agent's code.* RCB1 frames, never base64. Nothing is pushed into the model's context.
5. *Evidence the agent cannot touch.* The service records every call and judges the episode it ran, in a container
   the agent never saw. The recorded trajectory stays replayable for the video and for audits.

**Defaults.** `RCB_MAX_CALL_WALL_S` 900 s; `max_frames_per_call` 3000 unless the adapter sets it;
`RCB_STARTUP_TIMEOUT_S` 900 s; `RCB_MAX_RESUMES` 2; `RCB_RESUME_MAX_DEV_M` 0.05 m.

**Agent-ended episodes.** `agent_end/rcb_agent_end.py` implements them for the shared and operations layers. An
adapter (`benchmarks/robodojo/sim/server.py` is the reference):

- records the state's success after every control step with `hidden_success()`, instead of ending the episode;
- judges the end state in its own `finish()` for the ends in `END_STATE_REASONS` (a settle or hold window, where the
  task has one, runs from that state);
- adds `final_fields()` to `final.json`, and builds its `rcb_limited.Episode` with `persist=persist(...)`;
- serves with `serve(Service(..., finish=lambda: finish("finished"), end_step_limit=lambda: finish("step_limit")))`.

`RCB_STEP_LIMIT` caps the episode at the lower of N and the adapter's own `max_control_steps`. A service without
`end_step_limit`, or whose `status()` does not state its `control_steps`, does not start when `RCB_STEP_LIMIT` is set.

**Privileged-mode parity** (recommended). A benchmark's privileged `Session` offers the same robot information from
the same code: `s.camera_info()`, `s.render_depth(cam)`, `s.robot_spec()`, `s.kinematics(req)`
(`s.kinematics_spec()` = `/spec.kinematics`). Privileged mode stays privileged: object state comes through the tooling.

## Crash recovery

The shared layer (`rcb_limited.Episode`; adapters call it as `toy_server.py` does) resumes a crashed service in the
same episode. The sidecar layer does the same with its own journal. This is an implementation of the reference
services, not a rule: the protocol's rule is the runner's rerun of an infrastructure-failed trial (invariant H.5).

- **Journal and checkpoints.** Every executed control step (the exact row given to the simulator's step) is appended
  to `journal.f64` (float64 rows). After every completed call the journal is flushed, and a checkpoint is logged in
  `episode.jsonl`: call count, rows, control steps, the state hash, the robot's proprioception row, and the adapter's
  `persist` keys (state that shapes later actions). `call_begin` and `call_end` bracket every call.
- **Restart.** `run.sh` is the sidecar's PID 1 and exits non-zero when the service crashes. Compose restarts the
  container (`restart: on-failure:N`, same container and record). The new process finds the episode's `start` event
  and resumes:
  1. it replays the journal up to the last checkpoint, without rendering;
  2. it truncates the journal there. The call in flight is lost as a whole: its caller got a connection error, not a
     result;
  3. it checks the state ([Resume classes](#resume-classes));
  4. it restores the counters, the episode end if one was logged, and the `persist` keys, and continues the same
     episode.

  The agent's clock keeps running from its first request (the logged `first_request`). The episode's `elapsed_s`
  counts from the first start.
- **Limits.** At most `RCB_MAX_RESUMES` (2) resumes. A third crash ends the episode: `sim_crashed_on_call` if every
  crash happened while a call was being served, else `sim_crashed` (`infra_error = 1`). A journal shorter than the log
  ends it as `resume_failed` (`infra_error = 1`). A verdict already on disk is never overwritten. The service then
  keeps its PID file for the collect hook and answers every request with 409 `{"gave_up": true, ...}`
  ([eai-standard.md](../../docs/protocol/eai-standard.md#service-errors)). The same holds for a service that refuses
  the episode at its start.
- **Start-up.** A crash before the scene exists is a plain restart. The start-up watchdog (faulthandler's C thread,
  which fires even while a native scene build holds the GIL) dumps every thread's traceback to `server.log` and exits
  after `RCB_STARTUP_TIMEOUT_S` (900 s on the shared layer, 300 s on the MuJoCo service). A task sets the value its
  build needs. A start that follows failed starts first waits min(120, 20·(n − 1)) s. The watchdog stands down once
  the scene exists, so a long resume replay is not taken for a hang.

### Resume classes

The adapter declares its simulator's determinism class (`Episode(..., resume=...)`). Each benchmark's class is in its
README.

| Class | Rule |
|---|---|
| `exact` | The replayed state hash must equal the checkpoint's. Otherwise the episode ends `resume_failed` (`infra_error = 1`). |
| `approx` | The hash is compared and the result recorded. A mismatch does not end the episode: `resume_state_mismatch = 1`, and the robot's deviation from its checkpointed proprioception is recorded (the largest \|Δ\| over `joint_pos`; the largest TCP position error from `tcp_pose`). Only a TCP more than `RCB_RESUME_MAX_DEV_M` (0.05 m) from where it was ends the episode, as `resume_failed` (`infra_error = 1`). |

The verdict after a resume is judged on the live state the resumed service continued from. Under `approx` a
mismatch can perturb it as well as what the agent saw. `reward.json` reports `resumes` and `resume_state_mismatch`,
and a trial with `resume_state_mismatch = 1` can be audited by replaying its trajectory.

### Evidence fields

`final.json` and `episode.json` carry `sim_startups`, `resumes`, `resume_state_mismatch` (0 or 1),
`resume_max_tcp_dev_m` and `resume_max_joint_dev` (`Episode.final_fields()`). A give-up adds `gave_up`, `reason` and
`infra_error`. Graders copy the numeric ones into `reward.json`, with `infra_error`.

Besides: `episode.jsonl` (calls, checkpoints, resumes), `journal.f64`, `startups.jsonl`, `calls/NNNNNN/` (meta and
last frames per call), `server.log`, and at the end `trajectory.npz`, `final.json` and `replay.mp4`. A GPU lost to a
host systemd reload before the episode was judged is reported as `gpu_lost` (`infra_error = 1`).

### What a shared-layer task declares

- `environment/docker-compose.yaml`, service `sim`: `command: sh /srv/run.sh` and `restart: on-failure:N` (N ≥ 3
  recommended). `RCB_DATA` is the record directory (`/data` unless the benchmark's image uses it otherwise).
- `RCB_STARTUP_TIMEOUT_S` per task, from the measured build time of its family on the evaluation hosts: at least
  twice the slowest measured build. The benchmarks' READMEs record the measurements. A family whose build exceeds the
  watchdog loops through every restart to a give-up.
- Optional: `RCB_MAX_RESUMES` (2), `RCB_MAX_CALL_WALL_S` (900), `RCB_RESUME_MAX_DEV_M` (0.05).
- `artifacts`: also `journal.f64`, `startups.jsonl` and `server.log` from `service = "sim"`.
- The agent container (`environment/Dockerfile`) and the verifier (`tests/Dockerfile`) start `FROM` the
  `CLIENT_IMAGE` of `client.env`. Any `pip install` installs `client-requirements.txt`: the full pin list inline, or
  `-r client-requirements.txt` with a byte-identical copy in the build context. A new package or version is a change
  to the pins.
- The collect hook starts with `python3 /srv/rcb_limited.py end "$DATA"`. It waits through a resume (there is no PID
  file until the service is ready), signals only the process that wrote the newest `startups.jsonl` line, and resends
  SIGUSR1 every 30 s. It exits 2 when `final.json` already holds the verdict (a give-up, or an in-process grade), and 0
  when the service dumped the episode and exited. The hook then merges the live verdict into `final.json` and renders
  the video. It replays nothing to grade.
- Adapters: `EP = L.Episode(DATA, dim, resume, persist)`; `EP.startup()` before the scene is built and
  `EP.scene_built()` after; `EP.journal(a)` in the control step (its True return stops the call: loops that test
  `E["done"]` test `EP.stopping` too); `S.record_start()` then `EP.begin(...)` instead of logging `start` and
  installing a SIGUSR1 handler; `episode=EP, state_sha=..., proprio=...` in `L.Service`; `**EP.final_fields()` in
  `final.json` and `episode.json`.

**Cost.** One state hash per call, not per step. A resume replays the episode so far without rendering, on the agent's
wall clock. The benchmarks' READMEs give their replay rates.

## The operations layer

`operations/rcb_limited.py` is the shared layer plus the operations capability: operation ids, request deadlines,
`GET /operations/{id}`, the call watchdog and the physics-tick ledger. RoboARC runs it. Its client sends operation
ids only to a service whose `/spec.operations` is `true`, and behaves as the shared client otherwise.

## Tests

`ci_checks/check-unit-tests.sh --all` runs them (CI job `unit-tests`). They need numpy and requests, and no simulator,
image or GPU.

| Test | What it covers |
|---|---|
| `selftest.py` | the shared layer, CPU only, about 2 minutes: `toy_server.py` under `run.sh` with a stand-in for compose's restart policy. Resume between and inside calls, both resume classes, the third crash, the watchdog and back-off, a client hang-up, the wall bound, both collect-hook outcomes, SIGUSR1 during a resume, a simulator error, the client's protocol names, malformed requests, a port that is taken, a negative `Content-Length` |
| `operations/selftest.py` | what the operations layer adds (about 15 seconds) |
| `sidecar/selftest.py` | the sidecar layer, and ABC Sim's copy of it |
| `frames_selftest.py` | the per-call image budget of the sidecar, shared and realtime layers |
| `agent_end/agent_end_selftest.py`, `agent_end/agent_end_sidecar_selftest.py` | agent-ended episodes on every layer |
| `mcp/tests/` | the MCP server: an oracle run once over HTTP and once through the tools leaves the same episode |

`ci_checks/check-openapi-contract.py` runs the reference layers and checks their answers against
[docs/protocol/eai-standard.openapi.yaml](../../docs/protocol/eai-standard.openapi.yaml).
