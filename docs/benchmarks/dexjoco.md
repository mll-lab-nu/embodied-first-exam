# DexJoCo

Dexterous manipulation with a 16-DoF Allegro hand on a Franka Panda arm (or two of them), from DexJoCo
([brave-eai/dexjoco](https://github.com/brave-eai/dexjoco), MIT): its 11 tasks, each on one frozen scene instance taken
from a public human demonstration, in both modes (`scripts/dexjoco/`).

| | |
|---|---|
| upstream | DexJoCo @ `8d23b0f` (MIT); human demonstrations: Hugging Face dataset `DexJoCo/DexJoCo-Datasets-Raw` (public) |
| simulator | `dexjoco`: DexJoCo's gymnasium envs on MuJoCo 3.4.0, CPU physics (bit-exact replay in a fresh process), OSMesa rendering; no GPU |
| robots | `franka-allegro` (6 tasks), `franka-allegro-bimanual` (5 tasks, two arms side by side) |
| score | binary: DexJoCo's own success check (its episode ends at the first success or task failure); `water_plant` adds an aiming condition (below) |
| tasks | 11 families × 2 modes: `tasks/dexjoco-<family>-i00-privileged` and `-standard` (`eai-standard/2.2`) |
| image | `ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2` (`images/dexjoco/`: DexJoCo @ 8d23b0f and its pinned dependency closure; no demonstrations, no policies) |
| oracle | full, both modes: the demonstration's own actions |
| agent time budget | 3600 s for every task, one number for both modes; each task's own `[agent] timeout_sec`, written by the generator, and stated in every instruction's closing `## Time limit` section (PROTOCOL §2) |
| egress | allowlisted to the model APIs and the package registries in both modes: the reference demonstrations are public (PROTOCOL H.2) |

## Tasks

| family | robot | asks | oracle rows (50 Hz) |
|---|---|---|---|
| water_plant | single | spray the plant: the trigger held while the nozzle is near the plant and aimed at it, 30 steps | 307 |
| click_mouse | single | put the mouse on the pad and click, then keep it there 10 steps | 560 |
| hammer_nail | single | drive the nail at least 4 cm deep with counted strikes | 202 |
| pick_bucket | single | put the boxed food into the bucket and lift the bucket 15 cm | 580 |
| pinch_tongs | single | three pinches with the tongs held 10 cm up, then 30 steps | 375 |
| fold_glasses | single | fold both temples and put the glasses into the case, 50 steps | 612 |
| bimanual_hanoi | bimanual | the three-disk tower moved to post C, 20 steps; an illegal stack fails | 1085 |
| bimanual_microwave_cook | bimanual | hot dog in, door closed, start pressed | 815 |
| bimanual_unlock_ipad | bimanual | enter 1-2-3 with a fingertip, unlocked 10 steps; a wrong digit fails | 392 |
| bimanual_assembly | bimanual | peg into the tray's socket, touching the bottom 30 steps | 586 |
| bimanual_photograph | bimanual | camera held 0.4 m in front of the logo, axis within 10 deg, shutter pressed | 260 |

## Easy set
The families below are in the easy set (`docs/easy_set.toml`, reason `solved`) because the screening runs (GPT-6 Luna,
Codex xhigh, or GPT-6 Astra, Codex high) solved them in both modes; bases Luna solved in any mode are listed there too
(`solved_by = "luna"`). They keep their names and are run, but are reported apart from the main table.

| family | privileged solved by | standard solved by |
|---|---|---|
| click_mouse | Luna | Luna |
| bimanual_assembly | Astra (Luna failed) | Astra (Luna failed) |
| bimanual_hanoi | Astra (Luna failed) | Astra (Luna failed) |
| bimanual_microwave_cook | Astra (Luna failed) | Astra (Luna failed) |

## Task definition
- **Instance.** The task's env after DexJoCo's reset, with the initial object poses and table height of one human
  demonstration restored by DexJoCo's own state restorer (demo `state[0]`). DexJoCo's reset samples poses from the
  global RNG and its restorers edit the MuJoCo model (table height, fixed bodies), so the instance is a snapshot, not a
  seed: `instance.npz` holds the full physics state (`mjSTATE_INTEGRATION`), mocap targets, controls, every numeric
  `MjModel` array a task can change, and the env's Python-side task state (counters, flags). Its hash is checked
  whenever a task rebuilds it (privileged verifier and its replays, the standard service when its episode begins). Its `meta` entry never says which
  demonstration the scene came from (the reference is that demonstration's actions, and the agent reads
  `/app/instance.npz`; PROTOCOL H.2): `rcb_dexjoco.save_instance` refuses such keys and values, `generate.py` refuses
  an instance that carries them, and `ci_checks/check-agent-pointers.py` reads the archive's string members. The
  demonstration is named in `facts.json` (`demo`) and the task READMEs, which the agent does not read.
- **Action.** DexJoCo's own row per control step (50 Hz, 10 physics substeps of 2 ms): per arm the tcp target pose
  (xyz, quaternion wxyz, world frame), which DexJoCo's operational-space controller tracks, and 16 Allegro joint targets.
  Single arm 23 values, bimanual 46 (right first; the left hand's fingers in DexJoCo's mirrored order).
- **Episode.** As in DexJoCo's evaluation: it ends at the first success or task failure. DexJoCo's episode cap, its
  real-time pacing, its per-step camera rendering and hanoi's wall-clock auto-reset are lifted (`rcb_dexjoco.py`):
  the wall clock is the only budget.
- **Threads.** The replay is bit-exact for one OpenBLAS thread count. DexJoCo's operational-space controller does its
  linear algebra in numpy, and OpenBLAS splits a product differently on 1 thread, on 2-3 threads and on 4 or more: three
  different final-state hashes, and the references of `bimanual_assembly` and `fold_glasses` fail on fewer than 4
  (4, 8, 16, 32 and 64 threads agree on all 11 references). Every container that runs the simulator therefore sets
  `OPENBLAS_NUM_THREADS=4` (the sim sidecar: service, resume and the hook's video pass; the privileged agent container
  and verifier): the references' numerics on any host that lets the container run on 4 CPUs. It also stops the default
  from spinning against the containers' 4-CPU quota: `bimanual_hanoi` ran at 35 control steps/s that way on the
  32-thread host, 150 with 4 threads (the `steps_per_s` of `facts.json` are without a quota).
  - **4 visible CPUs are the minimum** (`min_cpus = verifier_min_cpus = 4`, `scripts/task_resources.toml`). The
    variable is an upper bound only: OpenBLAS never runs more threads than the CPUs the process may run on (its
    affinity, `os.sched_getaffinity`). A cpuset narrows that (`docker --cpuset-cpus`, `taskset`, a Slurm allocation of
    2 CPUs); a CFS quota does not (the tasks' `cpus: 4` caps, `docker --cpus 2`: the process still sees every host CPU
    and OpenBLAS still runs 4 threads, only slower). Measured in the image (`openblas_get_num_threads64_` of numpy's
    own library): `--cpuset-cpus 0,1` with `OPENBLAS_NUM_THREADS=4` runs 2 threads, `--cpuset-cpus 0-2`
    runs 3, `--cpus 2` runs 4, and the `fold_glasses` reference fails on 2 (final-state hash `0abf8081…` instead of
    `fd58ca0b…`), with `deterministic = 1` and the instance exact: it would read as the agent's failure.
  - **The guard.** `rcb_dexjoco.blas_threads()` asks the loaded OpenBLAS for its thread count (if that cannot be
    read: min(visible CPUs, `OPENBLAS_NUM_THREADS`)). With fewer than 4 no verdict on the agent is produced:
    the privileged verifier replays nothing and writes `too_few_cpus = 1`, `grader_error = 1`, `infra_error = 1`
    (a missing or malformed file is still the agent's 0: that needs no simulation); the standard service starts no
    episode (`final.json`: `reason = "too_few_cpus"`, `gave_up`, `infra_error = 1`; the service answers every request
    with the refusal, 409), the collect hook checks the live episode's count, and `tests/grade.py`
    reports `too_few_cpus = 1` with `grader_error = 1` and `infra_error = 1`. `visible_cpus` and `blas_threads` are in
    every `reward.json` that had a simulation. In the privileged agent's container the tooling only warns (stderr): the
    agent's own runs are the agent's business, the verdict is the verifier's.
  - Regenerating (`make_instances.py`) needs 4 visible CPUs too.
- **water_plant.** Upstream's zone + trigger test passes with the bottle lying on the table and spraying away from the
  plant (two Opus 5.5 runs did exactly that). The task also requires the spray direction (the bottle's local +z) within
  45 deg of the nozzle-to-plant line, held with the rest for 30 steps; the demonstration sprays 33 deg off.

## Privileged mode
`rcb_dexjoco.Session` on the frozen instance: unlimited exact resets, live object poses (`s.objects()`), DexJoCo's state
dict, thin primitives (tcp-target moves, hand-joint interpolation, hold), rendering, recording and self-replay. The
deliverable is `/app/output/trajectory.npz`; the verifier replays it twice in a fresh process from its own copy of the
instance: success = both replays succeed ∧ same final-state hash. An instance that does not rebuild exactly (its hash
differs: the image no longer builds the scene) is no verdict: nothing is replayed, `instance_mismatch`, `grader_error`
and `infra_error` = 1.
- **Hand-in cap.** A trajectory has at most 50,000 rows (`rcb_dexjoco.MAX_TRAJECTORY_ROWS`: 1000 s of robot time; the
  longest reference has 1085). `save_trajectory` refuses a longer one and the verifier scores it 0 (`bad_trajectory`).
  The cap is what the verifier can replay: the slowest family (`bimanual_hanoi`) runs about 140 control steps/s, so two
  replays of 50,000 rows take 12 min of the verifier's 3600 s on an idle host. The agent's own sessions have no step
  budget.
- **What is the agent's 0 and what is not.** A file that is not a readable trajectory (not an npz, pickled or object
  arrays, no `task` or `actions`, a wrong shape, NaN/inf, over the cap) is `bad_trajectory = 1`; `grader_error = 1` is
  left for the verifier's own failures and comes with `infra_error = 1` (an exception in the grader, or fewer than 4
  OpenBLAS threads: `too_few_cpus`, Threads above). The verdict is written before `replay.mp4` is rendered, and the
  video stops 2700 s after the grader started.

## Standard mode (`eai-standard/2.2`)
The 2.2 adapter `scripts/dexjoco/shared/standard/server.py` on the shared layer (`scripts/eai_standard/`, copied
unchanged), resume class `exact`:
- **actions:** `ee_pose` (DexJoCo's own row) and `joint_position` (per arm 7 arm + 16 hand joint targets; the arm part
  becomes a tcp target by forward kinematics, the same controller tracks it). The service journals and records the
  executed DexJoCo row, so the recorded trajectory replays in the privileged tooling unchanged.
- **observations:** every camera of the scene (static `front`, `back`, `left`, `right`, `top0`; the hand cameras on each
  hand's mount) at 640 x 480 with calibration (static pose or mount link), optional z-depth from the same renderer;
  a camera whose body is neither fixed in the world nor moved by the robot's own joints alone (`scene_camera` in
  `server.py`, decided from the model as MyoSuite's service does; `make_instances.py` records the same list as
  `scene_cameras` in `facts.json`, and `tests/test_standard_server.py` checks it against the frozen models) gives images
  and depth only: no mount, `extrinsic_cv` / `cam2world_gl` null, NaN per frame. In the 11 families that is
  bimanual_photograph's `cam_pos_z`, the lens of the camera the hands pick up;
- **frames per call:** at most 1000 images (cameras x frames, per-frame depth counted again; `/spec`
  `max_frames_per_call`), checked before anything is executed (400). Every frame is held until the response is sent;
  measured on the layer's Recorder with 640 x 480 frames: 2.7 GB per 1000 RGB frames, 5.1 GB per 1000 images of one
  camera with per-frame depth, on top of the simulator's 1.9 GB under the sidecar's 8 GiB cap. The default camera at
  the default 10 fps needs 302 images for the longest watch (30 s) and 102 for the longest chunk (10 s);
  proprioception `joint_pos`, `joint_vel`, `joint_effort` (7 + 16 per arm), `tcp_pose`, plus `tcp_target` and
  `hand_target` (the targets being tracked); no gripper-opening column (a dexterous hand).
- **kinematics:** stateless FK of the arm links, the hand mount and the tcp; IK of each tcp over its arm's 7 joints
  (damped least squares within the joint ranges).
- **robot_spec:** joints with the simulator's limits (arm torque limits; hand position actuators unlimited in effort),
  the hand drives' gains, the tcp definition (DexJoCo's `attachment_site`, the flange), the arm bases.
- **grading: the live episode.** `success` = DexJoCo's own success check
  (`Session.step`, with this benchmark's tightened checks such as water_plant's aim and 30-step hold) on the episode the
  service ran, recorded by the service in `episode.json` when the episode ends; `final.json` has `graded_by = "live"`,
  `replays = 0`, `live_success`, `live_sha` (the final-state hash). Nothing is replayed to grade it. No settle window
  is needed: the episode ends at the first success.
- **start state:** the service checks the frozen instance when the episode begins (`server.py`, before
  `Episode.begin`): a scene that does not rebuild to the instance's recorded state hash (`instance_exact`) gets no
  episode; the service gives up (`instance_mismatch = 1`, `infra_error = 1`, 409 to every request) before the agent is
  served. A resume after a crash is checked against its checkpoint's hash.
- **video:** the collect hook (`finalize.sh`) ends the service, writes the verdict into `final.json` (`finalized`,
  `video_pending = true`), then renders `replay.mp4` in one video-only pass (`environment/sim/video.py`, a fresh
  process: the trajectory stepped once from the frozen instance, the default static camera and the right hand camera,
  at most ~1500 frames). It compares nothing and decides nothing; a video that fails or runs out of time is only a
  missing video (`video = false`). Cost: about 9 CPU-minutes per trial (median 530 s, at most 960 s, physics
  included).
- **the hook's time:** `[[verifier.collect]] timeout_sec` = 5580 s (`RCB_COLLECT_BUDGET_S`): up to 900 s for the service
  to end and dump the episode (seconds in practice), then the video, bounded by `RCB_COLLECT_VIDEO_MAX_S` = 4500 s (the
  3600 s cutoff + 900 s: the physics of the longest episode the cutoff allows, rendered). `final.json` is written whole
  (temporary file + rename).
- **no verdict is infrastructure:** `tests/grade.py` reports `infra_error = 1` (never the agent's 0) when `final.json` is
  missing, unreadable, or without a verdict (not `finalized`, or neither the live verdict `graded_by` nor a give-up),
  when the service did not end and dump its episode for the hook, after a give-up following crashes that were not all
  inside the agent's calls (`sim_crashed`, `resume_failed`), on `instance_mismatch`, and when the sidecar ran fewer than
  4 OpenBLAS threads (`too_few_cpus`, with `grader_error = 1`; Threads above). Crashes all inside the agent's calls
  (`sim_crashed_on_call`), a task failure and the timeout are the agent's 0. An episode that a simulator error ended
  (`reason = "error"`) is reported as `sim_error = 1` and stays the trial's result: `eai-standard/2.2` has no rule that
  makes it an infrastructure failure (that rule is standard-realtime's).
- **tests:** `scripts/dexjoco/tests/test_standard_grading.py` (run with `test_standard_server.py`): the hook and the
  grader on synthetic records (live success 1, live failure 0, a sim error or crashes in calls 0 and not infra, crashes
  between calls and a hook that got no episode infra, a failed or late video changes nothing, nothing calls the
  replay tooling) and the service's start-state refusal on the stub simulator.
- **malformed requests:** a request is checked in full before anything is executed (`parse_submit` / `parse_observe`
  under `checked`): a field of the wrong JSON type (a number or an object as `note`, a string or
  a list as `dt` / `seconds` / `video_fps`, a string as `cameras`), a number too large for a float, NaN, a bad `depth`
  is a 400, no physics, the episode goes on; `null` for `dt`, `seconds`, `video_fps`, `cameras` or `note` is the
  default (what the 2.2 client sends for an argument left out). `scripts/dexjoco/tests/test_server_validation.py`
  fuzzes these functions (13,068 requests, numpy only, no simulator).
- `ci_checks/check-standard-protocol.py` passes against a live service of a single-arm and a bimanual task (velocity limits are null:
  WARN only). Crash recovery: the service killed between calls and inside a call resumes the same episode
  (`resumes = 2`, exact hash) and the oracle still ends in success.

## World-frame information
Privileged mode gives world coordinates (object poses through the tooling, the table height and the arm bases in the
instruction). Standard mode gives the robot's own pose only: each arm's base pose in `robot_spec`, the tcp in
proprioception, the cameras' calibration; no table height, no object or workspace coordinates in `/spec` or the texts.
The goals state their thresholds as relative distances (e.g. "within 0.20 m of the plant").

## Reference solutions
The demonstration's own actions (`scripts/dexjoco/instances/<family>/oracle_trajectory.npz`, built by
`make_instances.py` in the image), replayed until the episode ends in success. The standard client sends float32, so
the rows are rounded to float32 for both modes; every family still succeeds, `bimanual_hanoi` after holding its last row
8 more steps (the rounded rows end its 20-step hold count short). Standard mode streams the same rows through the client
as `ee_pose` chunks; the recorded trajectory is then exactly the privileged reference.

## Regenerating
```bash
python3 scripts/dexjoco/get_demo.py water_plant 1 /tmp/demos          # only to rebuild an instance from its demo
docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/repo -w /repo ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2 \
    python scripts/dexjoco/make_instances.py --all                     # check the instances and oracles, refresh facts.json
python3 scripts/dexjoco/generate.py && python3 scripts/dexjoco/generate.py --check
```

## Standard-mode service details

Serves `eai-standard/2.2`; `max_frames_per_call` = 1000. The service refuses the episode at its start with fewer than 4 CPUs (a give-up answered at once, docs/protocol/standard_mode.md §13).
