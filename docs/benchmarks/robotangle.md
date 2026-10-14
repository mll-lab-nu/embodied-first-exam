# RoboTangle (MuJoCo release)

RoboTangle's topological puzzle families on MuJoCo 3.14.0 physics. This release **replaces** the Genesis release (user
decision, 2026-10-13): the previous tasks `robotangle-<family>-<tier>-i00-*` (52 bases, image `eai-robotangle:0.2.22`),
their generator, their dataset entries and their benchmark page are removed from the repository; their results are not
comparable with this release's and are not carried over. The new image is built FROM the published
`eai-robotangle:0.2.22` (pinned by digest), whose recipe is kept as `images/robotangle/Dockerfile.genesis-0.2.22`.

- Name: `robotangle` / RoboTangle. Until 2026-10-13 the release was prepared as a benchmark of its own under the working
  name `robotangle`; the name is one parameter (Registration, below).
- History of the name in records: the Harbor trials of the first delivery (2026-10-13) ran on task dirs named
  `robotangle-*` with image tags `eai-robotangle:0.1.0-r3*`; the delivered dirs differ in the benchmark name and the
  image tag strings only (the images are the same, retagged `eai-robotangle:0.3.1-r3*`).
- Layout: the generator directory is `scripts/robotangle/` (it was `scripts/robotangle/`), the image directory
  `images/robotangle/`.

## Tasks

`robotangle-<family>-<tier>-i01-{privileged,standard}` (PROTOCOL §2.2):
- `<family>` with dashes (`interlocked-claws`); `[metadata].family` keeps the underscores.
- `<tier>`: the variation id without the family prefix, with dashes. A ported tier keeps RoboTangle's tier
  (`very-easy`, `easier`, `easy`, `medium`, `hard`); a redesigned set has its own ids (`rd-very-easy` … `rd-hard`); a
  new variation its own name (e.g. `double-maze`). No version in a task name: a redesign of a tier is another instance.
- `i01`: the MuJoCo instance (the HF dataset's `instances/<family>-<tier>-i01/`); RoboTangle's Genesis instance of the
  same scene is its `i00`.
- `i02`: the redesigned instance of the same tier: `cast-coil-{very-easy,easier,easy}-i02` (the redesigned Cast Coil,
  internal variation ids `cast_coil_v2_*`), beside the ported `cast-coil-<tier>-i01`.

Every task is RoboTangle's task contract (the same tooling `rcb_topogym.py`, graders, sim service and eai-standard/2.4
layer as RoboTangle; docs/benchmarks/robotangle.md, "Grading and determinism", "Standard mode") with these differences:
- physics: MuJoCo 3.14.0, CPU float64 (the blanket families' cloth: a deterministic CUDA step, `blanket_vbd_gpu`);
- the numpy / OpenBLAS SIMD masking in every container that runs a Session (so every CPU class builds the same frozen
  bytes); `render_bridge.py` and `nyx_direct.py` next to every tooling copy, named in the runtime binding;
- the texts state what the tooling grades: the contact-review values come from `CONTACT_RULE`, and the grasping rule is
  `Session.grasp_rules()` of the instance (the weld's slip force over 20 ms, 60 N ALOHA / 65 N Robotiq, and the
  Robotiq's release after 0.2 s without finger contact).

## Generator and release

- `scripts/robotangle/mk_tasks.py` (`--check` in CI) renders the task dirs from this directory: `release.json`,
  `packages/` (the texts of the RoboTangle base each task ports, renamed, with the family's own texts over them),
  `oracles/`, `assets.json`, `shared/` (the tooling and the graders). Generated tasks end with
  `scripts/task_conventions.py` normalize.
- The release files are written by `scripts/robotangle/release_rebuild.py --bench robotangle --onto <main>` on
  dev/robotangle_mujoco: image, instances made in the image, release files, render, checks, Harbor oracle / nop.
- Large files: the frozen instances are in the private HF dataset `eai-v2-internal/robotangle-assets` (RoboTangle's),
  under `instances/<base>/`, pinned file by file in `scripts/robotangle/assets.json`.
- Image: `ghcr.io/mll-lab-nu/eai-robotangle:<images/robotangle/VERSION>`, built FROM the published
  `eai-robotangle:0.2.22` with the release commit's simulator source and the frozen MuJoCo instances
  (`images/robotangle/Dockerfile`, generated from dev/robotangle_mujoco's `Dockerfile.mujoco`; context:
  `scripts/robotangle/fetch_image_context.sh`).

## Time budget (D8)

10800 s (3 h) wall clock in both modes and every family (user, 2026-10-13; 7200 s from 2026-10-12; `scripts/task_cutoffs.toml`), within the default cap: no exception.
(The Genesis release had 21600 s, then 7200 s from 2026-10-12.) The texts say "the time limit (`## Time limit`)". The standard service's clock
(`meta["time_left_s"]`, `RCB_WALL_CLOCK_S` follows the table) counts from the agent's first request to the service (PROTOCOL §2.12;
logged in `episode.jsonl`, kept over a restart), so the instruction has the common closing sentence and no sentence of its own about the
service's clock (2026-10-13; the Genesis release's "has run since the service first started" is not carried over). The service still ends the
episode with reason `timeout` when that count reaches 0; counted from the first request, that is never before the harness's cutoff.

## Safety readings in standard mode (`meta["safety"]`)

Owner decision, 2026-10-10: the standard service keeps publishing `meta["safety"]` in every response, and the protocol
records it as a declared exception to "no object contact forces". Why: the benchmark's physical-validity policy judges
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
A change to this list is a change of the declaration and goes through the protocol-change process (PROTOCOL §6).

User decision 2026-10-13: this release publishes main's declared fields again, with the names of the parts involved (names are allowed in standard mode; only positions / poses in the simulator's world frame, the table height and physics parameters are withheld). The service's `robot_felt` passes exactly these fields (`SAFETY_PUBLISHED`); `scripts/robotangle/tests/test_server_requests.py` checks the list and the names.

## Standard mode, world frame, network

`eai-standard/2.4` (as the Genesis release); no world coordinates in standard texts (D7,
`check-standard-texts.sh`); agent egress on the allowlist (PROTOCOL §2.11).

Every text the agent sees calls the service's frame the world frame, as main's other services call theirs, and defines it in
words; it is the robot frame: 
The agent-facing frame of the standard service is the robot frame (user, 2026-10-13: the table height and the robot base's
world position are never disclosed): origin at the robot's kinematic root link on its mounting, axes as the simulator's world
(+z up). The proprio TCP poses, `ee_pose` targets, `/kinematics` (ik targets, fk poses) and the camera extrinsics (static
mounts, per-observe calibration, per-frame `extrinsic_cv`) are in it; `robot_spec.base.pose` is the identity; no text and no
`/spec` field states a world coordinate of the mounting. `joint_position` rows, physics, graders and state hashes do not depend
on the frame. Privileged mode keeps the simulator's world frame (its tooling is the simulator); its texts state no table height
or robot base position either.

## Registration (the lines a rename changes)

`BENCH` in `scripts/robotangle/mk_tasks.py` and `BENCH` in dev/robotangle_mujoco's
`scripts/robotangle/release_rebuild.py` (or `--bench`); `git mv` of `scripts/robotangle/`, `images/robotangle/`
and this page; then the registration lines: `scripts/task_conventions.py` (`BENCHMARKS`),
`scripts/task_cutoffs.toml` (row and `[[history]]`), `scripts/task_resources.toml` (six `^robotangle-` rules),
`ci_checks/check-task-fields.sh` (`BUDGET_EXCEPTIONS`: the default cap, because of the prefix overlap), `ci_checks/check-tooling-identity.sh` (`MODULE`),
`ci_checks/check-generated-tasks.sh`, `ci_checks/check-unit-tests.sh`, `docs/TAXONOMY.md`, `README.md`, and the
`docs/CUTOFFS.md` render (`python3 scripts/task_cutoffs.py apply "<label>"`). The rename of 2026-10-13 (`robotangle-new` -> `robotangle`)
changed exactly these, removed the Genesis generator, tasks and resource rules, and emptied `CUTOFF_NOTE_OWN` in
`scripts/task_conventions.py` (the service now counts from the first request).
