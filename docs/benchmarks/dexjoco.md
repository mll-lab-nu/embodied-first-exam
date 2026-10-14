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
| agent time budget | 3600 s for every task since 2026-10-12 (owner: stricter cutoffs in 30-minute steps, one number for both modes); 5400 s before (D8: dexterous control of 16 hand joints per arm through a thin interface; the model runs we made used most of it); the number lives in `scripts/task_cutoffs.toml` (shown in [`docs/CUTOFFS.md`](../CUTOFFS.md)), and every instruction states it in its closing `## Time limit` section (PROTOCOL §2.12) |
| egress | allowlisted to the model APIs and the package registries in both modes: the reference demonstrations are public (PROTOCOL §2.7) |

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

## Task definition
- **Instance.** The task's env after DexJoCo's reset, with the initial object poses and table height of one human
  demonstration restored by DexJoCo's own state restorer (demo `state[0]`). DexJoCo's reset samples poses from the
  global RNG and its restorers edit the MuJoCo model (table height, fixed bodies), so the instance is a snapshot, not a
  seed: `instance.npz` holds the full physics state (`mjSTATE_INTEGRATION`), mocap targets, controls, every numeric
  `MjModel` array a task can change, and the env's Python-side task state (counters, flags). Its hash is checked
  whenever a task rebuilds it (privileged verifier, standard service, every replay). Its `meta` entry never says which
  demonstration the scene came from (the reference is that demonstration's actions, and the agent reads
  `/app/instance.npz`; PROTOCOL §2.7): `rcb_dexjoco.save_instance` refuses such keys and values, `generate.py` refuses
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
  (measured in the image on a 32-thread host, 2026-10-10: 4, 8, 16, 32 and 64 threads agree on all 11 references, which
  were made with the default, one thread per core). Every container that runs the simulator therefore sets
  `OPENBLAS_NUM_THREADS=4` (the sim sidecar: service, resume and the hook's replays; the privileged agent container and
  verifier): the references' numerics on any host that lets the container run on 4 CPUs. It also stops the default
  from spinning against the containers' 4-CPU quota: `bimanual_hanoi` ran at 35 control steps/s that way on the
  32-thread host, 150 with 4 threads (the `steps_per_s` of `facts.json` are without a quota).
  - **4 visible CPUs are the minimum** (`min_cpus = verifier_min_cpus = 4`, `scripts/task_resources.toml`). The
    variable is an upper bound only: OpenBLAS never runs more threads than the CPUs the process may run on (its
    affinity, `os.sched_getaffinity`). A cpuset narrows that (`docker --cpuset-cpus`, `taskset`, a Slurm allocation of
    2 CPUs); a CFS quota does not (the tasks' `cpus: 4` caps, `docker --cpus 2`: the process still sees every host CPU
    and OpenBLAS still runs 4 threads, only slower). Measured in the image, 2026-10-10 (`openblas_get_num_threads64_`
    of numpy's own library): `--cpuset-cpus 0,1` with `OPENBLAS_NUM_THREADS=4` runs 2 threads, `--cpuset-cpus 0-2`
    runs 3, `--cpus 2` runs 4, and the `fold_glasses` reference fails on 2 (final-state hash `0abf8081…` instead of
    `fd58ca0b…`), with `deterministic = 1` and the instance exact: it would read as the agent's failure.
  - **The guard.** `rcb_dexjoco.blas_threads()` asks the loaded OpenBLAS for its thread count (if that cannot be
    read: min(visible CPUs, `OPENBLAS_NUM_THREADS`)). With fewer than 4 no verdict on the agent is produced:
    the privileged verifier replays nothing and writes `too_few_cpus = 1`, `grader_error = 1`, `infra_error = 1`
    (a missing or malformed file is still the agent's 0: that needs no simulation); the standard service starts no
    episode (`final.json`: `reason = "too_few_cpus"`, `gave_up`, `infra_error = 1`; the port never opens, so the
    agent's client times out), the collect hook checks the count of each of its replay processes, and `tests/grade.py`
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
- **evidence and grading:** the collect hook (`finalize.sh`) ends the service, replays the recorded trajectory in two
  fresh processes and renders `replay.mp4` in a third; success = live ∧ both replays ∧ deterministic.
- **the hook's time:** the recorded episode has no step cap; a replay steps the physics the live episode stepped,
  without rendering or the agent's thinking time. The hook has 7200 s (`[[verifier.collect]] timeout_sec`, passed to
  `finalize.sh` as `RCB_COLLECT_BUDGET_S`), about 3500 s per replay: more than the service can have spent stepping
  unless the agent drove it for two thirds of its 5400 s without a pause. A replay still running a minute before the
  end is stopped and the trial is an infrastructure failure. The replays run one after the other (side by side they are
  no faster on the sidecar's 4 CPUs). The video gets what is left (at most 1200 s) and never changes the verdict, which
  is on disk (`finalized`) before it starts. `final.json` is written whole (temporary file + rename).
- **no verdict is infrastructure:** `tests/grade.py` reports `infra_error = 1` (never the agent's 0) when `final.json` is
  missing, unreadable, or without a verdict (not `finalized`, or neither the replays' `deterministic` nor a give-up
  after crashes), when a replay gave no result or ran out of the hook's time, and when the sidecar ran fewer than 4
  OpenBLAS threads (`too_few_cpus`, with `grader_error = 1`; Threads above). An episode that a simulator error
  ended (`reason = "error"`) is reported as `sim_error = 1` and stays the trial's result: `eai-standard/2.2` has no
  rule that makes it an infrastructure failure (that rule is standard-realtime's, PROTOCOL §4b).
- **malformed requests:** a request is checked in full before anything is executed (`parse_submit` / `parse_observe`
  under `checked`): a field of the wrong JSON type (a number or an object as `note`, a string or
  a list as `dt` / `seconds` / `video_fps`, a string as `cameras`), a number too large for a float, NaN, a bad `depth`
  is a 400, no physics, the episode goes on; `null` for `dt`, `seconds`, `video_fps`, `cameras` or `note` is the
  default (what the 2.2 client sends for an argument left out). `scripts/dexjoco/tests/test_server_validation.py`
  fuzzes these functions (13,068 requests, numpy only, no simulator).
- `ci_checks/check-standard-protocol.py` passes against a live service of a single-arm and a bimanual task (velocity limits are null:
  WARN only). Crash recovery: the service killed between calls and inside a call resumes the same episode
  (`resumes = 2`, exact hash) and the oracle still ends in success with `live_matches_replay`.

## World-frame information (D7)
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

## Change log
- 2026-10-14 (review of board 0105, B-M3 and B6-3; the scenes, the success checks and the references are unchanged, so
  the tasks keep their names):
  - all 22 tasks: the committed instances (`instances/<family>/instance.npz` and its copies in `environment/`,
    `tests/` and `environment/sim/`) had `meta` = `{"source": "DexJoCo-Datasets-Raw demo initial state …", "demo":
    "<demonstration id>", "dexjoco": "8d23b0f"}`. The reference solution is that demonstration's own actions, so a
    privileged agent could read at `/app/instance.npz` where a solution was (PROTOCOL §2.7); `ci_checks/check-agent-
    pointers.py` skipped binary files and did not see it. `meta` is now `{"dexjoco": "8d23b0f"}`, rewritten by
    `make_instances.py --strip-meta` (every other array is written back as loaded; all 11 rebuild to their recorded
    instance sha). The tooling refuses to save such a `meta`, the generator refuses such an instance, and the pointer
    check reads `.npz` string members and keys that name a demonstration or episode.
  - privileged `tests/grade.py`: an instance that does not rebuild exactly is no verdict (`instance_mismatch`,
    `grader_error`, `infra_error` = 1, nothing replayed); before, it was the agent's 0 (`instance_ok = 0`,
    `infra_error = 0`). `scripts/dexjoco/tests/test_grade_privileged.py` covers both.
  - Past results: under the egress allowlist the demonstration itself was out of reach (Hugging Face is not on it), so
    a privileged result stands unless the trial had open network and fetched it. A past privileged 0 with
    `instance_ok = 0` was an infrastructure failure.
- 2026-10-10 (review of 2026-10-10, board 0067; verifiers, the collect hook and the tooling's hand-in checks only: the
  instances, the success checks and the reference trajectories are unchanged, so the tasks keep their names):
  - standard: `final.json` missing / unreadable / without a verdict is `infra_error = 1` (a missing file used to be the
    agent's 0 with `infra_error = 0`, an unreadable one left no reward at all); the collect hook has 7200 s (was 3600 s),
    stops a replay that would run past it (infrastructure, not the agent's 0), time-boxes the video and writes
    `final.json` atomically.
  - privileged: the 50,000-row hand-in cap (the tooling accepted 10,000,000 rows, which the verifier could not replay
    in its timeout: no reward); the verifier's timeout is 3600 s (was 1800 s); the verdict is written before the video;
    a malformed file is `bad_trajectory` (was `grader_error`); every `reward.json` has `deterministic`.
  - both modes: `OPENBLAS_NUM_THREADS=4` wherever the simulator runs (Threads, above). On a host with 4 or more cores
    the numerics are the ones every earlier run had; the simulator is faster under the CPU quota (up to 4x on the
    bimanual tasks), so an agent gets more simulated steps out of the same wall clock than before.
  - Past results: a privileged trajectory of more than 50,000 rows that passed before would now score 0; none is known
    (the references have 202-1085 rows). Nothing else changes a verdict that was reached before.
- 2026-10-10, third review (board 0067, R3B-M1, R3B-M2; standard mode only: the instances, the success checks and the
  references are unchanged, so the tasks keep their names):
  - bimanual_photograph: `cam_pos_z` rides on the camera the hands pick up (a free body), and the service published its
    mount and live pose like a robot camera's: the object's pose, which standard mode must not give. It now gives
    images and depth only (Standard mode, observations). Past standard results of
    `dexjoco-bimanual-photograph-i00-standard` could read the object's pose and are reported separately; the other ten
    families have no such camera (checked on every frozen instance's model).
  - all 11: at most 1000 images per call (400 above; Standard mode, frames per call). Before, one request within the
    documented ranges could exhaust the sidecar's memory; a failed trial recorded as `infra_error` with
    `resource_service_oom` before this date may have been caused by such a request. The standard READMEs get a
    Change Log section.
- 2026-10-10, second review (board 0067, R2: M2, M3; the instances, the success checks and the references are
  unchanged, so the tasks keep their names):
  - both modes: the minimum is 4 CPUs visible to every container that runs the simulator (`min_cpus` and
    `verifier_min_cpus` were 2), and a grading process that runs fewer than 4 OpenBLAS threads gives no verdict
    (`too_few_cpus`, `grader_error`, `infra_error`; Threads above). `OPENBLAS_NUM_THREADS=4` alone did not guarantee
    the references' numerics under a 2-3 CPU cpuset. Privileged `reward.json` now carries `infra_error` (1 next to
    every `grader_error`), `visible_cpus` and `blas_threads`; standard `reward.json` carries `too_few_cpus`,
    `visible_cpus`, `blas_threads`.
  - standard: a malformed request field is a 400 before anything is executed. Before, a non-string `note` ran the
    chunk and then ended the episode with a 500 (`reason = "error"`, `sim_error = 1`, the agent's 0), and `null` for
    `dt` / `seconds` ended it before any step; `null` is now the default. The client (`environment/rcb_client.py`, the
    shared eai-standard/2.2 one): `Robot()` waits up to 3600 s for the service (was 600 s; no effect here, the service
    is up in seconds) and `cameras="name"` (a string) is one camera, no longer its characters.
  - Past results: on a host whose containers saw 4 or more CPUs (every pool host: docker without a cpuset) nothing
    changes. A past trial whose verifier or sim sidecar was confined to 2-3 CPUs (a Slurm cpuset) was replayed on other
    numerics: a 0 there with `deterministic = 1` may be a false failure, and such a trial would now be
    `infra_error = 1`. A past standard trial that ended with `sim_error = 1` after a non-string `note` or a `null`
    field would now go on (it could score 1).
