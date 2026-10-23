# RoboARC (MuJoCo release)

RoboARC's topological puzzle families on MuJoCo 3.14.0 physics, run by the simulator package `topogym`, and its IKEA
furniture-assembly suite ([IKEA suite](#ikea-suite), its own tooling and images). The topological families' image is
built FROM the published `ghcr.io/mll-lab-nu/efe:robotangle-0.2.22` image (pinned by digest); results of the earlier
Genesis release are not comparable with this one.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/roboarc -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

- Name: RoboARC (display) / `roboarc` (task prefix, image `ghcr.io/mll-lab-nu/efe:roboarc-<images/roboarc/VERSION>`, `images/roboarc/`, this
  page). Code identifiers keep the simulator's name: the package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables, the family keys
  (`interlocked_claws`); inside the image, `/opt/robotangle/` (the instances and `stage_instance.py`).

## Tasks

The topological families: `roboarc-<family>-<NN>-i01-{privileged,standard}` (PROTOCOL §2.2); the IKEA suite:
`roboarc-ikea-<item>-i00-{privileged,standard}` (one frozen scene per item, `i00`; no tier number; [IKEA suite](#ikea-suite)):
- `<family>` with dashes (`interlocked-claws`); `[metadata].family` keeps the underscores.
- `<NN>`: two digits, the base's number in its family. A number is never reused: removing a task leaves a gap. The
  difficulty is not in the name: it is `[metadata].difficulty` in task.toml (TAXONOMY).
- `i01`: the MuJoCo instance (the HF dataset's `instances/<family>-<NN>-i01/`).

Every topological task shares the tooling `rcb_topogym.py`, the graders, the sim service and the eai-standard/2.4 layer:
- physics: MuJoCo 3.14.0, CPU float64 (the blanket families' cloth: a deterministic CUDA step, `blanket_vbd_gpu`);
- the numpy / OpenBLAS SIMD masking in every container that runs a Session (so every CPU class builds the same frozen
  bytes); `render_bridge.py` and `nyx_direct.py` next to every tooling copy, named in the runtime binding;
- the privileged images (agent `/opt/tools/`, verifier `/tests/`) take `rcb_topogym.py`, `render_bridge.py` and
  `nyx_direct.py` from the files-only image `ghcr.io/mll-lab-nu/efe:roboarc-files-<version>` (`images/roboarc-files/`, built
  from `embodied_first_exam/benchmarks/roboarc/`; `FILES.json` pins its digest and the files' sha256) with
  `COPY --from=<image@digest>`: the privileged task dirs carry no copy. The standard sim service is built from `environment/sim/` (its `Dockerfile`)
  and takes them, and the rest of the files it shares with other tasks, at `/srv` from `images/roboarc-sim-files/`;
- the texts state what the tooling grades: the contact-review values come from `CONTACT_RULE`, and the grasping rule is
  `Session.grasp_rules()` of the instance (the weld's slip force over 20 ms, 60 N ALOHA / 65 N Robotiq, and the
  Robotiq's release after 0.2 s without finger contact).

## Release

- The shared task code (the tooling, the graders, the sim service, the standard oracle player) has one source,
  `embodied_first_exam/benchmarks/roboarc/`. A change to a file of `images/roboarc-files/FILES.json` needs a new image
  version: `images/roboarc-files/VERSION`, `python3 scripts/files_image.py build roboarc-files`, push,
  `files_image.py pin roboarc-files <digest>`, then the tasks' `COPY --from` lines name the new digest; until then
  `scripts/files_image.py check` fails.
- The files a task carries are in `tasks/`: the privileged reference
  (`tasks/roboarc/roboarc-<base>-privileged/solution/trajectory.npz`, both modes), the instance's lock (that task's
  `tests/runtime_binding.json`), the goal-state images (its `environment/goal/`) and the standard agent Dockerfile.
  The privileged reference must be the file `images/roboarc/release.json`'s evidence names (`trajectory_sha256`).
  The task directories are the deliverable; the tooling that built them is kept outside this repository.
- The release (the image, the instances made in it, the release files, the renders, the checks and Harbor's oracle / nop
  runs) is built outside this repository; each base is named either as a tier of its family (`numbers`) or, for a new
  design, by its key.
- Large files: the frozen instances are in the public image, under `/opt/robotangle/instances/<base>/`, pinned file by
  file in `images/roboarc/assets.json`.
- Image: `ghcr.io/mll-lab-nu/efe:roboarc-<images/roboarc/VERSION>`, built FROM the published
  `efe:robotangle-0.2.22` with the release commit's simulator source and the frozen MuJoCo instances
  (`images/roboarc/Dockerfile`, generated from dev/robotangle_mujoco's `Dockerfile.mujoco`; context:
  `images/roboarc/fetch_image_context.sh`).

## Time budget

10800 s (3 h) wall clock in both modes and every family (each task's `[agent] timeout_sec`), within the default cap.
The texts say "the time limit (`## Time limit`)". The standard service's clock (`meta["time_left_s"]`, `RCB_WALL_CLOCK_S`
= the cutoff) counts from the agent's first request to the service (logged in `episode.jsonl`, kept over a restart), so
the instruction has the common closing sentence. The service still ends the episode with reason `timeout` when that
count reaches 0, never before the harness's cutoff; open: that end becomes report-only at RoboARC's next task update.

## Grading replays (privileged: the strict goal within the agent's rows)

The six families with a grading hold (blanket-flatten, knot-untying, lock-picking, orbits, rope-threading, slotted-post-ring;
`rcb_topogym.REPLAY_TOLERANCES`) replay a trajectory with the instance's own thresholds and, if the episode has not ended after
the last row, hold the final targets for up to 2 s; during that hold blanket-flatten accepts 92 % coverage and 80 mm/s cloth
speed (95 % and 30 mm/s in the rows) and knot-untying a rope speed 0.25 mm/s higher. Standard mode grades the live episode
strictly, with no grading replay (Standard grading, below).

**The rule.** Privileged success needs both grading replays to succeed AND at least one of them to reach the goal with the
instance's own thresholds within the trajectory's rows (`tests/grade.py`: `strict_replay_required` 1, `strict_goal_reached`,
`strict_goal_row`; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, not credited). The
instruction says where `s.replay(actions, grading=True)` reports it (`["grading"]["strict_success"]`). Why: the MuJoCo
release replays deterministically on the same host (the cloth step on a deterministic GPU solver, the rest on the CPU), so
a recording that stops on its own success reaches it within its rows; without the strict goal the hold's relaxed
thresholds would become the effective goal in privileged mode only.

**Validation** (Harbor `-a oracle` / `-a nop`, roboarc image 0.1.0, the version before the current `efe:roboarc-0.2.0`): the privileged oracle scores 1 with
`strict_goal_reached` 1 on one task of each family with a hold and on interlocked-claws-01, deterministic; nop scores 0.
blanket-flatten-01's reference without its last 8 rows (a recording that stops 8 control steps before its own success)
is graded 0 (`all_success` 1, `success_in_hold_only` 1).

## Standard grading: the live episode

`success` = the live success: the task predicate on the live simulator with the instance's own thresholds, confirmation
window included (`server.py`: after every `submit` and every watching `observe`, and as the episode stands at its end),
recorded in `episode.json`. No grading replay runs. `finalize.sh` writes `final.json` from `episode.json` first
(`graded_by` live, `replays` 0, `state_sha` = the live end-state hash, `video_pending` 1), then runs ONE video-only pass
(`replay.py`: a plain fresh-process replay of the live rows on the sidecar's GPU that renders `replay.mp4` and, for a
success held for review, the frames around its live review events; record `replay.video.json`). It never changes the
verdict, and a failed, killed or GPU-less pass loses only the video. `tests/grade.py` transcribes the result. In `final.json`, `live_success` is the live episode's own success and `success` the verdict: false with an infrastructure failure or when the success is held for review (`held_for_review`). A service that dumped its episode but did not exit in time keeps that live verdict (`service_exit_timed_out`, no video). A missing `trajectory.npz` is recorded (`dump_error`) and changes no verdict. Non-finite numbers are written as null.
- **No hold.** The live episode gets no hold (a hold would loosen the rule: the privileged twin needs a strict success
  within the agent's rows).
- **Review, forcing, instability.** The live episode's `review` (deep task contacts: a live success is held for review,
  `success_pending_review`), `forcing` (evidence) and `simulator_instability` (a breakdown without forcing: infrastructure).
- **Start state.** `Session(strict=True)` checks the frozen instance against `runtime_binding.json` when the service builds
  it. A mismatch is `instance_mismatch`, `infra_error 1`, before anything is served. `tests/grade.py` also checks the live
  startup record (`startup_binding.json`) against its own copy of the binding.
- **Infrastructure** (H.5): no, unreadable or unfinalized `final.json`, the end timed out, `instance_mismatch`, a give-up
  after crashes not all inside the agent's calls (`sim_crashed`, `resume_failed`, `call_watchdog`), `simulator_instability`
  in the live episode, a simulator error (reason `error`). The agent's 0: the task's failure predicate,
  `forced_breakdown`, the wall clock, `step_guard`, `sim_crashed_on_call`. A video-pass error or a GPU lost after the
  episode never voids a trial.
- **Re-scoring recorded standard trials.** The verdict is the recorded live fields of `final.json`: the `success` of
  `episode.json`. A live instance mismatch, `infra_error` or `simulator_instability` voids it, and a live `review` holds
  it.

## Safety readings in standard mode (`meta["safety"]`)

The standard service publishes `meta["safety"]` in every response, declared here as allowed by PROTOCOL H.3. Why: the benchmark's physical-validity policy judges
the agent on these readings -- a success with a deep task contact is held for human review instead of credited, a
soft body that stays collapsed ends the episode, a simulator breakdown shortly after forcing is the agent's failure --
so an agent that could not see them would be judged on something it cannot measure. The fields are exactly what
`rcb_topogym._SafetyMonitor.read` returns (maxima since the previous response, each next to its limit), and nothing
else of the simulator's contact state is published:

| Field of `meta["safety"]` | What it is | Families |
|---|---|---|
| `rules`, `scope` | the policy's revision; "since the previous read" | all |
| `forcing` | `max_press_force_n` (the largest total contact force an arm's gripper, or a part it holds, pressed on anything else with), `max_drive_fraction_while_pressing`, `longest_forcing_s`, `events`, the last three events (each: the arm and joint, the control step, the drive fraction and cap, the force, and in words what pressed on what, e.g. "a part it holds" on a named task part), and the thresholds (`contact_n`, `near_cap_fraction`, `event_after_s`) | all |
| `task_contact_mm` | the deepest contact between task parts (`max`), the longest time above the sustained limit, and the review and breakdown limits | rigid |
| `held_finger_contact_mm` | the deepest contact between a finger and the part it holds, with its review limits | rigid |
| `review` | the count of review events and the last three (each: the kind, the control step, the names of the two task parts in contact, the depth in mm and the force in N); a success with one is held for review | rigid |
| `soft_volume_ratio` | the lowest volume ratio of each soft body and the longest time at or below 0 | soft (rope, cord, cloth) |
| `attachment_stretch_mm` | the worst cord attachment stretch and the longest time above its limit | soft |
| `table_guard` | the control steps whose gripper target the table guard stopped, with the last events | where the guard applies |
| `ik_jumps` | the last IK solutions that lay far from the current joints (`ee_pose` actions) | when one occurred |

These are forces, depths, ratios and the names of the parts involved, never a pose: no field says where an object is.
A change to this list is a change of the declaration and goes through the protocol-change process (PROTOCOL §7).

Names of the parts involved are allowed in standard mode; positions / poses in the simulator's world frame, the table
height and physics parameters are withheld. The service's `robot_felt` passes exactly these fields (`SAFETY_PUBLISHED`).

## Standard mode, world frame, network

`eai-standard/2.4`; no world coordinates in standard texts (D7,
`ci_checks/benchmarks/roboarc/advisory-world-frame.sh`); agent egress on the allowlist (PROTOCOL Appendix H.6).

Every text the agent sees calls the service's frame the world frame, as the other services call theirs, and defines it in
words; it is the robot frame (the table height and the robot base's world position are never disclosed): origin at the robot's kinematic root link on its mounting, axes as the simulator's world
(+z up). The proprio TCP poses, `ee_pose` targets, `/kinematics` (ik targets, fk poses) and the camera extrinsics (static
mounts, per-observe calibration, per-frame `extrinsic_cv`) are in it; `robot_spec.base.pose` is the identity; no text and no
`/spec` field states a world coordinate of the mounting. `joint_position` rows, physics, graders and state hashes do not depend
on the frame. Privileged mode keeps the simulator's world frame (its tooling is the simulator); its texts state no table height
or robot base position either.

## Registration (the lines a rename changes)

`git mv` of `images/roboarc/`, `images/roboarc-files/` (a new image name: build, push, pin) and this page; then the registration lines: `scripts/task_conventions.py`
(`BENCHMARKS`), `scripts/task_resources.toml`
(the `^roboarc-` rules; the generic `^roboarc-(?!ikea-)` rules leave the IKEA suite to its own `^roboarc-ikea-` rules), `docs/TAXONOMY.md`, `README.md`, the checks that name a benchmark's prefix
(`ci_checks/check-tooling-identity.sh` `MODULE`, where the IKEA suite is the group `roboarc-ikea`,
`ci_checks/benchmarks/roboarc/advisory-world-frame.sh`); `ci_checks/ci_scope.py` (RoboARC's unit includes `images/ikea-mujoco/` and
`images/ikea-mujoco-files/`); the cutoff is
each task's own `[agent] timeout_sec`.

## Standard-mode service details

Serves `eai-standard/2.4` (docs/protocol/standard_mode.md Part 4). Contact and safety telemetry is published in `meta["safety"]`, declared field by field in this doc. `max_frames_per_call` = 2000, per-frame depth counted as four images; where a call's length is known only while it runs (`ee_pose` rows) the call stops taking frames at the bound and `meta.frames_skipped` counts them. Its service ends the episode when `time_left_s` reaches 0 (counted from the agent's first request), until its next task update.

## IKEA suite

The IKEA furniture-assembly tasks (`roboarc-ikea-<item>-i00-{privileged,standard}`, eight items in both modes) are part of
RoboARC. They share the `roboarc-` prefix, this folder, the eai-standard/2.4 layer and the 3 h budget;
everything else is their own: the tooling `rcb_ikea.py` (not `rcb_topogym.py`), the scenes, the graders and the sim service
(source `embodied_first_exam/benchmarks/roboarc/ikea/`, files-only image `efe:ikea-mujoco-files`), and the images
`efe:ikea-mujoco-<VERSION>` / `efe:ikea-mujoco-sim-<VERSION>` (`images/ikea-mujoco/`), which keep their names. The sections
above describe the topological families; this section is the whole description of the IKEA suite.

Furniture-assembly scenes in plain MuJoCo 3.14.0 on the CPU (float64), each with two robot arms and physical
grasps (finger friction, no assist). Eight tasks ship, each in both modes (16 task directories,
`tasks/roboarc/roboarc-ikea-<task>-i00-{privileged,standard}`):

### IKEA quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/roboarc -i 'roboarc-ikea-*' -a codex -m openai/gpt-6-astra
```
All images are public (`efe:ikea-mujoco-0.3.0`, `efe:ikea-mujoco-sim-0.4.0`, `efe:ikea-mujoco-files`): the tasks run
directly. To rebuild the images from source, see [IKEA image and assets](#ikea-image-and-assets) and `images/ikea-mujoco/README.md`.

| task | robot | what is assembled | mechanism |
|---|---|---|---|
| `lack` | two Franka Panda | LACK side table: four legs screwed into the top | threads (exact convex pieces), latched retention welds |
| `svallet` | two ViperX 300 s (ALOHA 2) | SVALLET lamp: the bulb screwed in, the shade snapped on | spring jaws and snaps, the bulb's thread |
| `gladom` | two Franka Panda | GLADOM tray table | threads (SDF meshes), latched welds |
| `variera` | two Franka Panda | VARIERA box: screws driven with a screwdriver | threads (SDF meshes) |
| `eket` | two Franka Panda | EKET cabinet: dowels and panels | latched retention welds |
| `ikea365` | two Franka Panda | IKEA 365+ stand and bowl: a screw driven with a screwdriver | threads (exact convex pieces), latched welds |
| `vesken` | two Franka Panda | VESKEN shelf unit: 23 snap connections | spring jaws and snaps |
| `stegesund` | two Franka Panda | STEGESUND stand: bolts driven with a hex key | capsule helices, seat welds |

`simulator = "mujoco"`; `robot = "franka-panda-bimanual"` (two Franka Panda arms with MuJoCo Menagerie's Panda hand;
stegesund names its arms `left/` / `right/`, the others `left_` / `right_`) or `"aloha-2"` (svallet: MuJoCo Menagerie's
ALOHA 2, two ViperX 300 s arms). Standard tasks speak `eai-standard/2.4` (the operations capability:
`r.operation_status()`).

The agent budget is 10800 s (3 h) of wall clock in both modes. One reference execution must fit 40 % of it (4320 s) on
the trial host (IKEA timing, below). A privileged trajectory may have at most the task's row cap (stated in its instruction:
the verifier's replays must fit its time limit).

### IKEA scenes in progress (not tasks)
Four more scenes are in the image (`/opt/ikea/scenes/`) but are not tasks: no reference passes every gate yet.
- `burvik`: no reference passes under the prism rule and the joint-speed clamp; leg 3 is blocked by the scene's
  geometry (the top leans 6.4° in its jig, the hand hits the handle rack while spinning the leg), which needs a scene or
  fixture change.
- `kyrre`: the authors' demo loses screw 2-1 at its hole under the final physics (4 of 9 welds), and one replay takes
  12.3-14.0 ks on a Xeon core, about 3 x the 4320 s bar (the welded legs keep their box contacts with the seat).
- `stenerik`: the closed-loop build seats all six screws and peels the four pads, but its pad presses stay below the
  scene's 1 N / 0.3 s bond gate.
- `uppsta`: timing only. The closed-loop reference passes `final_check()` in fresh replays on AMD Zen 4 and Intel Xeon
  with the same hashes, but one replay takes 12,680 / 12,684 s on an Intel Xeon Gold 6230R core, 2.9 x the bar (its
  two screw drives cost 22-26 ms per row).

### IKEA tasks
- The task directories are the deliverable; the tooling that built them is kept outside this repository.
- In `images/ikea-mujoco/`: `assets.json` (the sha256 of every scene file in the image, and the dataset pin of the
  meshes; Image and assets), `bindings.json` (what each scene builds to in the image: initial-state hash, actuators,
  timestep). The scenes' upstream provenance is kept outside this repository (PROTOCOL Appendix H.2).
- Each privileged task carries `rcb_ikea.py` (the tooling and the replay), `tests/grade.py` (the verifier) and
  `tests/render_video.py` (the replay video); each standard task the sim service (`environment/sim/`: `server.py`,
  `ikea_rig.py`, `ikea_nyx.py`, `finalize.sh`; `ikea_nyx.py` drives RoboARC's `nyx_direct.py`, which the tasks get from `embodied_first_exam/benchmarks/roboarc/`), its
  grader (`tests/grade.py`: transcribes the live episode's `final.json`) and the oracle client.
- The references are kept in the task directories only (the standard `solution/oracle_actions.npz`, which the
  privileged `solution/trajectory.npz` is a copy of).
- Every task's agent egress is the allowlist of `scripts/set_agent_egress.py`.

### IKEA grading (both modes, every task)
One rule in both modes. Privileged: the deliverable (`/app/output/trajectory.npz`) is replayed open-loop in two fresh
processes from the frozen keyframe. Standard: the rule is evaluated on the live episode by the sim service; nothing is
replayed (below). Success needs all of:
- **Goal:** the scene's own `success.py`, a port of the source assembly grader.
- **Terminal rules,** the same in every task: the parts are released (no robot link touches a part); every part is at
  rest (at most 0.01 m/s and 0.05 rad/s); the simulation never broke down (no non-finite state, no MuJoCo BADQACC /
  BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm).
- **End pose (EKET):** every panel, the back included, ends within 10 mm and 2 degrees of its goal relative to the top
  panel (`rcb_ikea.END_POSE_RULES`): the source grader checks the back only at its slide, and the back has no frame joint.
- These hold at the end of the rows **and** again after the grader holds the last row for 1.0 s
  (`rcb_ikea.Session.final_check()`).
- Privileged: both replays end in the same state hashes, before and after the hold.
- A replay that crashes (a simulator crash, `replay_crash`) or in which the scene's code or MuJoCo raises on the state
  the rows drove it into (`replay_exception`) is a breakdown (`sim_breakdown 1`, reward 0), not a grader error: a
  grader or infrastructure error gives the trial a free retry (PROTOCOL H.5), which the deliverable's own failures must
  not get. A scene that differs from the binding or builds to another initial state is `infra_error 1`.
- The privileged verifier's time limit covers a trajectory of the task's row cap on a slow trial-class CPU (one
  reference replay on a Xeon Gold 6230R core, with a 1.5x margin), not only the
  Harbor host's timing: a verifier that times out writes no verdict.
- The privileged verifier checks the scene in its image file by file against `tests/runtime_binding.json`
  (`instance_exact`) and its initial-state hash (`instance_ok`); the standard sim service does the same before its
  episode begins (`server.py`: scene files, initial-state hash, actuators and runtime against
  `environment/sim/runtime_binding.json`; a mismatch is `instance_mismatch`, `infra_error 1`, and nothing is served).

Standard mode is graded by the live episode: `success` = the sim service's live
verdict, `graded_by_live 1`, `replays 0`. The service ends an episode at the first settled success, `Session.status()`
and then `final_check()` on a snapshot with the last row held 1.0 s (the privileged grader's rule, the settle window
included); a failed settle lets the episode go on (`meta["settle_failed"]`). An episode that ends otherwise (the wall
clock, the collect hook's end) is judged as it stands by the same two checks. `finalize.sh` writes `final.json`
(`graded_by "live"`, `replays 0`, `state_sha` = the live end-state hash); the verifier (`tests/grade.py`, the shared
client base, no simulator) transcribes it. The trajectory (`/data/trajectory.npz`) stays the replayable deliverable; a
live success without it is `infra_error`. Infrastructure (a free retry, H.5): no, unreadable or unfinalized
`final.json`, `instance_mismatch`, a give-up after crashes not all inside the agent's calls (`sim_crashed`,
`resume_failed`, `call_watchdog`), a service-side error. The agent's 0: a breakdown, a simulator error its rows caused
(`sim_error`), a timeout, all crashes inside its calls (`sim_crashed_on_call`), a failed settle.

Every graded trial leaves a video (PROTOCOL §4), evidence only: standard, the sidecar's `/data/live.mp4`, recorded during
the live episode (Nyx, cam_high, 10 frames per simulated second, on the GPU the sidecar renders the agent's cameras with;
no extra pass); privileged, `/logs/verifier/replay.mp4`, rendered by a third process next to the two verdict replays
(MuJoCo's renderer on CPU OSMesa: the verifier has no GPU; 512 x 288, at most 750 frames).

### IKEA robot speed (both modes)
Every arm joint target moves at most the robot's real joint velocity limit per control step: Franka Panda 2.175 rad/s on
joints 1-4 and 2.61 rad/s on joints 5-7; ViperX 300 s 3.14159 rad/s. It is a clamp, not a failure
(`rcb_ikea.Session.applied()`, in the tooling and the replay alike): a row within the limit (+1e-9) is applied
unchanged, a faster one is spread over the following control steps. The gripper command is not limited.

### IKEA physics changes against the source scenes
One rule for all scenes, clamp not fail (as the topological families):
- **MuJoCo 3.14.0 with the EPA fix byte-patched in.** 3.14.0's EPA keeps the polytope horizon in two fixed 24-entry
  arrays and writes past them unchecked (fixed upstream after 3.14.0). A dowel pressed deep into a thin convex piece
  of eket's side panel overflows them: SIGSEGV or silent memory corruption, about 1 in 400 random eket episodes. The
  image patches 14 bytes of the wheel's own `libmujoco.so` (`images/ikea-mujoco/mujoco-3.14.0-epa/`); it is
  bit-identical to the stock wheel on every reference and stress episode checked. A from-source build is not
  bit-identical to the wheel and is not used.
- **Cylinder -> prism:** RoboARC's rule. Every cylinder a robot geom can touch is a 32-facet convex prism at scene
  build (inscribed in the cylinder). It removed every cylinder-caused breakdown of the stress test.
- **Joint-speed clamp:** above. The source demos command targets up to 55 x the real limits; the references were
  rebuilt or retimed within them.
- **Deferred: the Franka Hand slew** (0.1 m/s of finger width) is the long-term rule against finger slams; it is off
  until the references are retimed for it.
- eket's dowels: the soft dowel shells touch only the side panels; a stiff twin meets everything else.
- numpy / OpenBLAS SIMD masking in the image (`NPY_DISABLE_CPU_FEATURES` without AVX-512, `OPENBLAS_CORETYPE=Haswell`),
  as in the topological families' image: unmasked, eket's reference diverged between AVX-512 and AVX2 hosts.

Stress test (random, jerk and prefix strategies from the frozen birth), with the clamp, the prism rule and the eket
dowel rule: non-jerk BREAKDOWN rate 1.75 %, prefix-jerk 7 %; stegesund, 203 episodes, one genuine non-jerk BREAKDOWN
(the known finger-limit class). Residuals, none blocking: finger slams
while the hand slew is off (gladom), energy created at robot joint limits under random arm targets (vesken, eket), one
table penetration (gladom, prefix-jerk), ViperX self-contact on jerk (svallet).

### IKEA references
Each task has one reference for both modes, every row within the joint-speed limits (the privileged
`solution/trajectory.npz` and the standard `solution/oracle_actions.npz` are the same rows):
- lack: the authors' demo passed through the clamp;
- svallet, gladom, variera: the demo time-dilated or centred to the limits; variera's
  demo ended holding the screwdriver, so a 240-row release tail is appended;
- eket, ikea365, vesken: closed-loop references built on the final physics: the
  demo as the phase guide, with true-state feedback (Jacobian-IK servos, gates, local searches), recorded as the
  executed rows;
- stegesund: the authors' speed-limited demo, unchanged.

Harbor on the final images: privileged oracle 1 / nop 0 on all eight, standard oracle 1 (live settled success) / nop 0
on all eight; on the Nyx sidecar variera's standard oracle episode ends on the same settled success and end hash (its
verifier's result is not recorded yet). Each reference ends on the same state hashes on Intel AVX2
(i9-14900HX), Intel AVX-512 (Xeon Gold 6230R) and AMD Zen 4 (Ryzen 9 7950X, EPYC 9354).

### IKEA adversarial trial (PROTOCOL H.1)
`roboarc-ikea-eket-i00-privileged` with a red-team paragraph on top of its
instruction (obtain reward 1 without assembling the cabinet, by any exploit of the grader, the tooling, the file format
or the simulator), Codex + GPT-6 Luna xhigh with the pool's lane settings: reward 0, deterministic, no grader or
infrastructure error. The agent read the loader, the replay, `final_check()`, the operation tracker, the latches and the
end-pose rule and found no bypass; its best attempt (a one-row hold) replays released and at rest and fails the goal.
A malformed or compressed-bomb trajectory, a scene exception and, in standard mode, a simulator error or a malformed
request field are the agent's 0, never a free retry.

### IKEA timing
One reference execution against the 4320 s bar (40 % of 10800 s). A Xeon Gold 6230R core (2.1 GHz) is a slow
trial-class CPU; the quiet i9-14900HX laptop a fast one; the standard live episodes ran on shared, loaded RTX 4090
workstations (Ryzen 9 7950X).

| task | rows | one replay, dedicated Xeon Gold 6230R core | one replay, quiet i9-14900HX | standard live episode, loaded host |
|---|---|---|---|---|
| eket | 70,210 | 472 s (4.4 %) | | 351 s |
| svallet | 69,414 | 478 s (4.4 %) | | 397 s |
| ikea365 | 89,126 | 604 s (5.6 %) | | 480 s |
| lack | 63,697 | 923 s (8.5 %) | | 639 s |
| vesken | 353,125 | 1,288 s (11.9 %) | | 1,145 s |
| stegesund | 357,221 | 3,160 s (29.3 %) | | 2,190 s |
| gladom | 168,628 | **5,636 s (52.2 %), over the bar** | 2,882 s (26.7 %) | 3,362 s |
| variera | 231,903 | **6,839 s (63.3 %), over the bar** | 3,413 s (31.6 %) | 4,365 s (EGL sidecar); 6,046 s (Nyx, load ~70) |

gladom and variera are inside the bar on a quiet fast host (26.7 % and 31.6 %) and over it on a slow Xeon core (52.2 %
and 63.3 %): MuJoCo's own step is about 95 % of the time (their SDF threads). They ship as the owner's decision; the
agent's budget is the same 10800 s on every host, so on a slow host an agent has less room for full replays.

### IKEA image and assets
- `ghcr.io/mll-lab-nu/efe:ikea-mujoco-<images/ikea-mujoco/VERSION>` (0.3.0, image id `ed950d079b63`): MuJoCo 3.14.0
  (EPA-patched), numpy 2.5.4, Python 3.12, and the twelve scenes at `/opt/ikea/scenes/<task>` (the four in progress
  included). The privileged agent and the privileged verifier run it; the standard verifier runs the shared client
  base (it replays nothing).
- `ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-<images/ikea-mujoco/sim/VERSION>` (0.4.0): the standard sidecar. It adds Nyx,
  RoboARC's renderer and look, in its own venv `/opt/nyx` (gs-nyx 0.1.3 needs numpy < 2.4; the physics process keeps
  numpy 2.5.4 and the patched MuJoCo): RGB from Nyx (path tracer, 32 spp, denoised, studio HDRI, point lights placed
  relative to each scene's work surface), depth from MuJoCo's EGL raster, the same camera rig and calibration. The live
  state hashes with Nyx are bit-identical to EGL's over the first 2000 control steps of all eight references, and Nyx
  draws only what MuJoCo's raster drew.
- The scene code is in git (`images/ikea-mujoco/scenes/<task>/`); the meshes (2,078 files) are not, and every file's
  sha256 is pinned in `images/ikea-mujoco/assets.json`. The robot meshes (828: Franka Panda, Apache-2.0; ALOHA,
  BSD-3-Clause) come from MuJoCo Menagerie at a pinned commit; the furniture part meshes (1,250, parameterized
  reconstructions drawn from the IKEA assembly manuals, not IKEA CAD; CC BY 4.0) from the public Hugging Face dataset
  `MLL-Lab/embodied-first-exam-public` (`ikea-mujoco/`) at a pinned revision, no login. `images/ikea-mujoco/fetch_image_context.sh` downloads
  both, checks them and stages the build context (`images/ikea-mujoco/README.md`).
- `stage_context.py` refuses a scene text that points at upstream material (H.2).

### IKEA world-frame information
The standard tasks' texts give no world coordinates: no part poses or positions, no table height, no world base poses.
Every pose the standard agent gets or gives is in the robot frame (origin at the left arm's base link, +z up). The
privileged tasks read anything, as privileged tasks do. A scene reads nothing from the environment (`rcb_ikea` drops
kyrre's development switches `SW_FROM_OP` / `SW_FROM_T` on import).
