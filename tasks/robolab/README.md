# RoboLab

[NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 on Isaac Lab 2.3.2 / Isaac Sim 5.1: tabletop language-goal tasks
for a Franka with a Robotiq 2F-85 (DROID joint-position actions). `simulator = "robolab"`, `robot = "franka-robotiq-2f85"`.
53 families, each as a privileged task `robolab-<family>-i00-privileged` and its standard twin
`robolab-<family>-i00-standard` (`eai-standard/2.2`), on the same frozen instance. Results are attributed by DIGEST
(PROTOCOL H.8).

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/robolab -a codex -m openai/gpt-6-astra
```
The first task builds the simulator image from public sources (below); later tasks reuse it.

## Before you run

- **Licence.** The simulator image contains NVIDIA Isaac Sim 5.1 / Omniverse Kit and the Isaac Lab 2.3.2 wheels from
  pypi.nvidia.com: building and running it accepts the [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html)
  and NVIDIA's terms for those wheels (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES`). Read them before your first run.
  RoboLab itself and its asset library are Apache-2.0. No account, login or token is needed.
- **GPU and driver.** Linux x86_64, Docker with BuildKit and the NVIDIA Container Toolkit, an RTX-class NVIDIA GPU (Isaac
  renders with RTX even headless) with a driver Isaac Sim 5.1 supports (checked on 580.x; RTX 4090 and RTX PRO 6000).
- **Disk.** About 60 GB free for the first build (the image is ~27 GB).
- **Data.** None to download by hand: RoboLab's asset library and the remote files it references are baked into the image.
- **First build.** The image is not on a public registry (NVIDIA does not allow anyone to redistribute Isaac Sim), so the
  first task builds it with Docker from public sources: about 20-60 min, network access to github.com (+ LFS),
  snapshot.ubuntu.com, pypi.org, pypi.nvidia.com, download.pytorch.org and NVIDIA's public Omniverse content bucket on S3.
  Every task's Dockerfile starts with that recipe (`images/robolab/Dockerfile`), so the build runs once per Docker host and
  later tasks take it from Docker's build cache. Maintainers who can pull `ghcr.io/mll-lab-nu/efe-private:robolab-0.2.0`
  get its layers instead (compose `build.cache_from`). To build it ahead of the run, run one task first
  (`harbor run -p tasks/robolab/robolab-banana-in-bowl-i00-privileged -a oracle`, reward 1).

## Tasks
- The task directories are the deliverable; the tooling that built them is kept outside this repository. Each family's
  frozen instance is in its task dir (`tasks/robolab/robolab-<family>-i00-privileged/environment/instance.json`); the code
  the tasks share has its one source in `embodied_first_exam/benchmarks/robolab/` (the tooling `rcb_robolab.py`, the oracles' skills
  `ref_primitives.py`) and `embodied_first_exam/standard/` (the 2.2 layer and the standard client).
- A family is RoboLab's benchmark task of that name, its success predicate RoboLab's own `success` termination term.
  The 53 families that have tasks are the 2 with a reference solution and the 51 with
  a graded positive example. 35 further RoboLab tasks were frozen but have no positive yet (one is needed before
  review); their instances are not kept here (repository history, 9621e47d1).
- The frozen instance is the full scene state after RoboLab's canonical seeded reset (`env.reset()` twice, as RoboLab's
  evaluation loop does), with its state hash, made in the image by `rcb_robolab.py make-instance --task <f> --seed 0`;
  the tasks carry it in `environment/` and `tests/` (privileged) and `environment/sim/` (standard). Each instance was
  checked in a second fresh process: the same hash, success false at t = 0 and during a 1 s hold.

## Oracle and review
- banana_in_bowl and rubiks_cube_left_of_bowl have a reference solution: `solution/oracle_<family>.py`, a human-written
  script on the privileged tooling plus the skills in `solution/ref_primitives.py` (never in the agent image); the
  standard oracle streams the privileged oracle's recorded joint targets through the client in one-second chunks and
  rides through a service crash (`spec.on_service_error`). The labels follow the recorded runs (static validation):
  - privileged `oracle = "full"`: the oracle scored 1 in recorded Harbor runs; `oracle_evidence` cites the runs;
  - standard `oracle = "partial"`: oracle_replay scored 1 in recorded runs of an earlier service version and has not
    been re-run on this one.
- `oracle = "none"` (51 families): RoboLab ships no expert or planner. Every such family has at least one model trial that
  the separate verifier scored 1 (run `codex-gpt6_luna-xhigh`), cited by trial id in `oracle_evidence` and in the README
  with its trial log on the results site and its replay video on Hugging Face. These tasks have no
  `solution/` and go through human review per family in PR #3 (both modes, a positive, the `nop` result).
- bananas_in_bin_one_more and bananas_in_bin_three_total have the identical predicate (exactly 1 of `banana`,
  `banana_01`, `banana_03` in `grey_bin`, RoboLab's `choose`, K = 1); only their instructions differ.

## Success semantics (instantaneous)
RoboLab evaluates its `success` term after every control step and terminates the episode at the first step where it
holds (its termination freezes the env); the replay stops there and later rows are never executed. So a goal state that
holds at a single control step counts, in both modes. This is "success at any step" rather than "at the end of the
replay": we keep RoboLab's own definition so the predicate is upstream's. Most predicates require
the gripper to have released the object (`require_gripper_detached`), which rules out holding an object through the goal
region; the instructions state the rule in both modes. Three additions in the tooling (`rcb_robolab.py`) keep a
success from firing before the task is done:
- **"The gripper" is both fingers.** RoboLab's DROID robot declares one contact body, `left_inner_finger`
  (`robolab/robots/droid.py`, "Use one finger only": an Isaac Lab contact sensor with filters takes one prim), so an
  an object pinched by the right finger or the pads would read as released.
  `GRIPPER_CONTACT` declares both inner fingers and makes "gripper" RoboLab's own alias group of the two
  (`WorldState.resolve_contact_bodies`: any member), set before the env is registered; each finger gets RoboLab's own
  sensors. Every family's term is otherwise upstream's.
- **On the table where the words say so.** `take_measuring_spoon_out` ("... and put it on the table") and
  `cooking_clear_plate` (RoboLab's specific wording: "place each on the table surface") use RoboLab's own
  `object_outside_of_and_on_surface` with surface `table` and their own parameters instead of `object_outside_of`,
  which would count an object lifted out of the container or knocked off the table.
- **A settle hold at the end.** After a trajectory's last row the replay holds it for `SETTLE_STEPS` (30 control steps,
  2 s), the term still checked at every step, so a release in the last rows completes; in standard mode the service
  holds the last command as long when the agent's phase ends.

## Image and host
- `images/robolab/` (Isaac Lab 2.3.2 / Isaac Sim 5.1 from the pinned `uv.lock`, RoboLab's Apache-2.0 asset library baked
  in, with the remote files of the asset library: Network, below): a recipe that needs no build context, copied verbatim
  into every task's Dockerfile (privileged: environment/ and tests/; standard: the `sim` sidecar's `environment/sim/Dockerfile`)
  as the stage `robolab-base`. It contains NVIDIA Isaac Sim, whose licence forbids redistribution: **BUILD_ONLY**; the
  organization's private copy `ghcr.io/mll-lab-nu/efe-private:robolab-<images/robolab/VERSION>` (built with inline cache)
  is the tasks' `build.cache_from`. `images/robolab/BUILD_ONLY` has the licences, the pinned inputs and the check of a build.
- `images/robolab-files/`: `ghcr.io/mll-lab-nu/efe:robolab-files-<VERSION>`, files only (`FROM scratch`): the tooling
  `rcb_robolab.py` that the privileged agent and verifier images `COPY --from` (Tooling, below); public, pulled by the task builds.
- Isaac needs an RTX-class GPU even headless (PhysX runs on the CPU). One Isaac simulator at a time per 32 GB of host RAM.
- Standard mode: the agent container and the verifier use the one digest-pinned client image of every standard task and
  its exact pip pins (`embodied_first_exam/standard/client.env`, `client-requirements.txt`, copied into `environment/`); only the
  `sim` sidecar runs the simulator image (built from `environment/sim/Dockerfile`).
- Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount their own `*_trusted` cache
  volumes, never the agent's; every cache volume is scoped to the trial's compose project (no fixed name).

## Network
The agent reaches the model APIs and the package registries (PyPI, apt archives), nothing else: `[agent] network_mode =
"allowlist"` with the hosts of `scripts/set_agent_egress.py`, in every task's `task.toml`.

| Service | Network |
|---|---|
| privileged `main` (agent and its Isaac processes) | public from container start until the agent starts (the harness is installed then), the allowlist (the model APIs and the package registries) while the agent runs |
| standard `main` (agent, client only) | the same |
| standard `sim` (the simulator service) | the same as `main`: Harbor's egress control puts every compose service without a network setting of its own in one namespace, so the service's Isaac start (it begins at container start and takes 5 to 9 minutes) and a restart after a crash run with the allowlist only |
| `rcb_monitor` | none |
| privileged verifier | none (`no-network`) |
| standard verifier | none (`no-network`) |

- **Isaac itself needs no network**: the image holds Isaac Sim, Isaac Lab, RoboLab and every Python package, and the EULA
  is accepted by environment variables. Under the allowlist the oracle of `banana-in-bowl` scores 1 in both modes with
  the same initial and final state hashes as with open egress.
- **RoboLab's asset library is localized.** 15 of its USD layers reference NVIDIA's public Omniverse content bucket
  (`omniverse-content-production.s3…amazonaws.com`) by URL: the MDL materials of the four tables, of the grey bin and of
  the robot, their textures, and a few props of scenes that are not tasks here. Without them the table renders as a
  glossy red surface and the scene is ready later (physics is unchanged: none of the 53 families references remote
  geometry). The image holds the files: `images/robolab/mirror_remote_assets.py`, the last step of the build, copies
  all 419 (635 MB) to `/opt/robolab/assets/_remote`, checks each against `images/robolab/remote_assets.sha256` and
  points the layers at the copies; no layer of the library names a remote file.
- **The privileged verifier** keeps Harbor's default network (Grading and determinism) but needs it for nothing.
- **The recorded example episode is not in the agent's image.** RoboLab's repository ships one recorded successful
  episode (`examples/recorded_data/RubiksCubeAndBananaTask`: actions, video and environment configuration, replayed by
  `examples/run_recorded.py`), a solution of `rubiks_cube_and_banana` inside the base image. The privileged
  `environment/Dockerfile` removes the directory; nothing at run time reads it. The standard agent container has no
  simulator image, and the verifier's image is not the agent's.

## Time budget
3600 s for every task of both modes: each task's own `[agent] timeout_sec` (PROTOCOL §2,
docs/protocol/running.md "The agent's time"); every instruction states it in its closing `## Time limit` section, and the benchmark's
own text names no number. Every Python process pays about 2 minutes of Isaac launch and scene build, so an agent's
iterations cost more than in the other simulators.

## Grading and determinism
- PhysX on the CPU: on one host a fresh process reproduces the live run bit for bit, but a second replay inside one
  process drifts in the last bits, so the verifier replays in **two fresh processes** and compares them. Across hosts the
  final state can differ in the last bits (the banana_in_bowl oracle ends in one of two hashes on our hosts, both
  successes): a trial is graded on the host it ran on.
- Privileged: `tests/grade.py` replays `/app/output/trajectory.npz` twice; success = the predicate held in both, the final
  hashes agree, and the rebuilt frozen scene matches the recorded one.
- Standard: graded by the **live episode**, with no grading replay (PROTOCOL H.4). The service judges the episode it
  runs: RoboLab's success term after every control step (the first step where it holds ends the episode), and when the
  agent's time is up (the collect hook's signal, after the agent's container is stopped) it holds the last command for
  `SETTLE_STEPS` = 30 more control steps on the live simulator while the term is checked (`settle_steps`, the same hold
  the privileged replay applies after a trajectory's last row; a simulator error during the hold is recorded,
  `settle_error`, and the term is judged as it stands). It then writes `trajectory.npz` (the deliverable) and
  `episode.json` and exits; the hook (`environment/sim/finalize.sh`) writes `final.json` from it (`graded_by` "live",
  `replays` 0) before anything else. success = the live success, no infrastructure failure. The standard verifier only
  reads `final.json` and runs with `network_mode = "no-network"`.
- The start state (standard): the service builds the frozen scene and, before it serves anything, compares it with the
  instance's recorded state: the state hash (`instance.json` `state_sha`) or, if the hash differs, every object pose and
  robot joint within the tooling's tolerance (`Session.instance_matches`, as the tooling's strict mode). A scene that
  matches neither is a give-up as an infrastructure failure (`instance_mismatch`, `infra_error` = 1; the service answers
  409).
- The privileged verifier runs with `network_mode = "no-network"` too (PROTOCOL H.6): it starts Isaac Sim offline.
  Grading downloads nothing: RoboLab's assets, the remote files they reference and every package are in the image.
- Whose failure a 0 is. Standard: `tests/grade.py` writes a reward whatever it finds; a missing, unreadable or
  unfinalized `final.json` (the service never came up, the collect hook was killed), no record of the live episode, a
  give-up after crashes between calls and an instance mismatch at the start are `infra_error = 1`, never the agent's 0;
  a crash inside the agent's calls and a simulator error raised by them stay its 0. `finalize.sh` replaces
  `final.json` atomically. Privileged: a deliverable that is not a
  readable trajectory (not an npz, no `task` / `actions`, object arrays, wrong shape, NaN, more than 100,000 rows) is
  `bad_trajectory` (the agent's 0); a replay process without a result, a replay time-out (`replay_timed_out`) and
  `instance_ok = 0` (the rebuilt scene differs on this host) set `grader_error = infra_error = 1`.
- Time limits (Isaac start + scene ~2 min, replays 15-20 control steps/s). Privileged: each replay has max(1800 s,
  900 s + rows / 7.5) (half the nominal rate), and `[verifier] timeout_sec = 29100` fits two replays of the longest
  accepted trajectory (100,000 rows: 14,234 s each) plus 600 s. Standard: `[[verifier.collect]] timeout_sec = 3600`
  (`HOOK_BUDGET_S`, the same number) = the episode end (up to 2700 s through a resume) + the video encode (at most 600
  s, CPU, at most 3001 frames) + a margin; the hook uses no GPU after the service exits.
- The video (standard) is filmed during the live episode by the service (`live_video.py`): Isaac Lab
  renders every camera with each control step anyway (the observation), so a frame (the tooling's `_video_frame`: the
  viewport cameras + the wrist camera) is taken every 3 control steps (5 per simulated second) and written as a JPEG file
  (`/data/live_video/`, crash-safe; a resume skips the frames on disk and deletes those of the call lost in the crash); past 3000 slots the slot doubles (a time lapse).
  Cost: one JPEG encode per 3 control steps (a few ms against 70-300 ms per control step). The collect hook encodes `live.mp4` + `live.last.png` after the
  verdict (CPU, `RCB_VIDEO_LIMIT_S` 600 s); a frame or an encode that fails costs the video only (`video` false,
  `video_error`), never the verdict. Privileged: the replay video never decides a replay: the tooling catches a writer
  that cannot open, a frame that cannot be rendered or written and an encoder that fails at close (`video_ok` false in the
  replay's result; `stop_video()` returns None), and the frames go straight to the encoder. A trajectory longer than
  9,000 control steps is filmed as a time lapse (at most 9,000 frames, `MAX_VIDEO_FRAMES`).
- **Re-scoring a standard trial recorded while a grading replay still decided**: its live verdict is `final.json`
  `success` (the live result, merged from `episode.json`); `infra_error` only when the live record is missing (no or
  unfinalized `final.json`, no `live_sha`: no `episode.json`, the service never ended the episode) or the service gave up with `infra_error`;
  `replay_error`, `gpu_lost` and an `instance_mismatch` found by a replay are not the live episode's; trials re-graded
  later (`regrade_*` in `reward.json`) keep their recorded verdict.

## Crash recovery (standard mode, docs/protocol/standard_mode.md §13)
- Resume class `exact`: the resumed service is a fresh process, and replaying the journal is that process's first replay,
  so the state hash at the last checkpoint must match exactly (else the episode ends `resume_failed`, `infra_error`).
- The journal holds the float32 row handed to `Session.step` for every control step; a checkpoint (state hash = sha1 of
  the scene's full state, proprio row) follows every call. Reading the state never steps physics. A resume replays the
  episode so far at about 15-20 control steps/s, on the agent's wall clock.
- `RCB_STARTUP_TIMEOUT_S = 900`: the scene builds measured 99-217 s; 900 s is more than four times the slowest.
- The crash recovery is exercised on the CPU with a test double of the tooling under `run.sh` and a restart loop (kills
  inside and between calls, an exact-hash mismatch, three crashes inside calls, the 400s), with the shared layer's own
  selftest. Per-call state hashing only reads the scene (`InteractiveScene.get_state` reads PhysX views into Isaac
  Lab's timestamped buffers and writes nothing), so it cannot change a live run.

## Tooling (file names)
| main's convention | RoboLab |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `/opt/tools/rcb_robolab.py` in the agent's image (`Session`: the frozen scene state, thin primitives, rendering, recording, replay), from the files-only image below |
| `tests/rcb_traj.py` | `/tests/rcb_robolab.py` in the verifier's image, from the same files-only image |
| standard sidecar | `environment/sim/server.py` (the 2.2 adapter), `finalize.sh`, `rcb_robolab.py`; `run.sh`, `rcb_limited.py`, `rcb1.py` from `embodied_first_exam/standard/` |
| `rcb_client.py`, `rcb1.py` | the same names (`embodied_first_exam/standard/`) |

The privileged tasks carry no copy of the tooling: their `environment/Dockerfile` and `tests/Dockerfile` take
`rcb_robolab.py` with `COPY --from` from the files-only image `ghcr.io/mll-lab-nu/efe:robolab-files-<version>` (`images/robolab-files/`,
`scripts/files_image.py`; FILES.json pins its digest and the file's sha256; public), built
from its one source `embodied_first_exam/benchmarks/robolab/rcb_robolab.py`. The verifier's image gets its own copy from that image when
it is built; nothing from the agent's container reaches it. The standard tasks keep their copy in `environment/sim/`
(bind-mounted at `/srv`). After a change to `rcb_robolab.py`: bump `images/robolab-files/VERSION`, `python3 scripts/files_image.py build
robolab-files`, push it, `python3 scripts/files_image.py pin robolab-files <digest>`.

The tooling records (T, 8) actions (7 joint targets + the binary gripper command) at 15 Hz. Every copy of the tooling and
of the standard sidecar files is byte-identical across the benchmark, the files image's included (`check-tooling-identity.sh`); the tooling's TASKS
registry lists all 88 RoboLab tasks that were frozen (the 53 here and the 35 without a positive), so adding a family later does not change existing tasks.

## Declarations
- **Tooling: thin wrappers only.** Differential-IK moves, joint moves, gripper, hold, plus the frozen instance, state,
  recording, replay and rendering. Task-level skills (grasp, place, navigate) are never added to the agent's tooling;
  reference solutions keep theirs under `solution/`.
- **World-frame information.** Standard tasks never say where things are in the world (docs/protocol/standard_mode.md §10,
  `ci_checks/benchmarks/robolab/advisory-world-frame.sh`); the robot's root frame (Franka base at the origin) is the world convention. Privileged tasks
  give the privileged state through the tooling.

## Standard mode (eai-standard/2.2)
`joint_position` (8: 7 joints + binary gripper, switched at the row; rows `dt` apart, a multiple of 1/15 s, anything else
is a 400) and `ee_pose` (8, closed-loop differential IK, at most 0.25 m/s, fingertip-centre frame); cameras
`egocentric_mirrored_camera`, `over_shoulder_left_camera` (static) and `wrist_cam` (on the Robotiq base link); Isaac
`distance_to_image_plane` depth; `/kinematics` from a numpy model of the USD joints (7); 32 proprio columns.
docs/protocol/standard_mode.md §16.

Requests are checked completely before the first control step: a field of the wrong type (`dt`, `seconds`,
`video_fps`, `note`, `cameras`, `interpolate`, `video`, `type`, `depth`), a value out of range, an `ee_pose` position more
than 2 m from the robot's base on any axis or a zero quaternion is a 400 that executes nothing; an absent or null field
takes its default. One case is left in
the shared layer (`embodied_first_exam/standard/rcb_limited.py`): `actions` sent as a JSON object is converted before the adapter
sees it and still ends the episode with a 500.

## Known issues
- The tooling stops a runaway trajectory at 100,000 control steps (`step_guard`, 1.9 h of simulated time); the live
  service runs 3-15 steps/s, so the time limit ends an episode long before. Stated in `/spec` (`max_control_steps`,
  `episode`) and in both instructions (a technical cap, not a step budget); a
  privileged trajectory may hold at most that many rows.
- An `ee_pose` submit has no frame cap: a long one at a high `video_fps` keeps many frames in memory (the client's
  defaults, 5 fps and mp4, stay small).
- RoboLab's success terms are upstream's ("the original simulator decides"), except the three additions of Success
  semantics (both fingers, two on-table terms, the settle hold). Still looser than their words: "inside" extends without limit along the container's up axis (the instructions state it), so a toppled or
  tilted container can count objects as outside or inside; `object_upright` has no support term (an object in free fall
  passes); `is_supported_on_surface` accepts a mug lying on its side as "standing". `tools_picking_drill`'s term names the left bin while the drill starts in the
  right bin; the instruction says so.
- Contact can make the physics diverge (joint readings of 1e6 and more, objects thrown off the table) after a grasp
  that looks ordinary (rare: about once in 350 trials); in standard mode that episode is lost. A
  privileged `s.reset()` does not restore the start bit for bit; the verifier replays in a fresh process.

## Licences
RoboLab: Apache-2.0 (code and assets); Isaac Lab: BSD-3-Clause on GitHub, its pip wheels and Isaac Sim 5.1 are NVIDIA
proprietary software (no redistribution), hence BUILD_ONLY.

## Standard-mode service details

Resume class `exact` (Isaac, CPU PhysX: the resumed service is a fresh process, whose first replay is bit-exact). A
resume replays at ~20 steps/s. Its service states no `max_frames_per_call` yet.

Per-simulator notes:

| | |
|---|---|
| simulator | Isaac Lab 2.3 |
| rows streamed at | 15 Hz control (8 substeps) |
| `joint_position` | 8: 7 joints + binary gripper (switched) |
| `ee_pose` | 8, closed-loop differential IK, fingertip-centre frame |
| cameras | `egocentric_mirrored_camera`, `over_shoulder_left_camera` (static), `wrist_cam` |
| depth | Isaac `distance_to_image_plane` |
| `/kinematics` | numpy model of the USD joints (7) |
| proprio columns | 32 |
| grading replays | none (graded by the live episode) |
| resume class (docs/protocol/standard_mode.md §13.1) | `exact` |

Measured scene builds (episode `start` minus the end of Harbor's environment setup, from standard-mode trials on the laptop, RTX 4090 laptop GPU, 32 GB: a lower bound of the build):

| benchmark | measured | build | note |
|---|---|---|---|
| RoboLab | 13 families (20 trials) | 98–217 s | default enough |
