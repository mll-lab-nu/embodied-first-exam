# RoboARC (MuJoCo release)

RoboARC's topological puzzle families on MuJoCo 3.14.0 physics, run by the simulator package `topogym`. This release
**replaces** the Genesis release of these puzzles (user decision, 2026-10-13): the previous Genesis tasks
`<family>-<tier>-i00` (52 bases, image `eai-robotangle:0.2.22`), their generator, their dataset entries and their
benchmark page are removed from the repository; their results are not comparable with this release's and are not
carried over. The new image is built FROM that published image (pinned by digest), whose recipe is kept as
`images/roboarc/Dockerfile.genesis-0.2.22`.

- Name: RoboARC (display) / `roboarc` (task prefix, image `eai-roboarc`, `scripts/roboarc/`, `images/roboarc/`, this
  page; owner, 2026-10-13). Until then the release was prepared under the working names `robotangle-new` and
  `robotangle`; Harbor records and image tags of those runs keep the names they had. Code identifiers keep the
  simulator's name: the package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables, the family keys
  (`interlocked_claws`), and the development branch dev/robotangle_mujoco with its `scripts/robotangle/` and
  `images/robotangle/`; inside the image, `/opt/robotangle/` (the instances and `stage_instance.py`).

## Tasks

`roboarc-<family>-<NN>-i01-{privileged,standard}` (PROTOCOL §2.2):
- `<family>` with dashes (`interlocked-claws`); `[metadata].family` keeps the underscores.
- `<NN>`: two digits, the base's number in its family. A number is never reused: removing a task leaves a gap. The
  difficulty is not in the name: it is `[metadata].difficulty` in task.toml (TAXONOMY).
- `i01`: the MuJoCo instance (the HF dataset's `instances/<family>-<NN>-i01/`).
- `scripts/roboarc/roboarc_names.json` maps every base of the working names to its RoboARC name: old base -> new base,
  family, number, difficulty.

Every task is RoboARC's task contract (the same tooling `rcb_topogym.py`, graders, sim service and eai-standard/2.4
layer as RoboARC; docs/benchmarks/roboarc.md, "Grading and determinism", "Standard mode") with these differences:
- physics: MuJoCo 3.14.0, CPU float64 (the blanket families' cloth: a deterministic CUDA step, `blanket_vbd_gpu`);
- the numpy / OpenBLAS SIMD masking in every container that runs a Session (so every CPU class builds the same frozen
  bytes); `render_bridge.py` and `nyx_direct.py` next to every tooling copy, named in the runtime binding;
- the texts state what the tooling grades: the contact-review values come from `CONTACT_RULE`, and the grasping rule is
  `Session.grasp_rules()` of the instance (the weld's slip force over 20 ms, 60 N ALOHA / 65 N Robotiq, and the
  Robotiq's release after 0.2 s without finger contact).

## Generator and release

- `scripts/roboarc/mk_tasks.py` (`--check` in CI) renders the task dirs from this directory: `release.json`,
  `packages/` (the texts of the RoboARC base each task ports, renamed, with the family's own texts over them),
  `oracles/`, `assets.json`, `shared/` (the tooling and the graders). Generated tasks end with
  `scripts/task_conventions.py` normalize.
- The release files are written by `scripts/robotangle/release_rebuild.py --onto <main>` on dev/robotangle_mujoco
  (its `mujoco_release.json` names each base: a tier through its family's `numbers`, a new design by its key): image,
  instances made in the image, release files, render, checks, Harbor oracle / nop.
- Large files: the frozen instances are in the private HF dataset `eai-v2-internal/robotangle-assets` (shared with the
  Genesis release), under `instances/<base>/`, pinned file by file in `scripts/roboarc/assets.json`.
- Image: `ghcr.io/mll-lab-nu/eai-roboarc:<images/roboarc/VERSION>`, built FROM the published
  `eai-robotangle:0.2.22` with the release commit's simulator source and the frozen MuJoCo instances
  (`images/roboarc/Dockerfile`, generated from dev/robotangle_mujoco's `Dockerfile.mujoco`; context:
  `scripts/roboarc/fetch_image_context.sh`).

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

User decision 2026-10-13: this release publishes main's declared fields again, with the names of the parts involved (names are allowed in standard mode; only positions / poses in the simulator's world frame, the table height and physics parameters are withheld). The service's `robot_felt` passes exactly these fields (`SAFETY_PUBLISHED`); `scripts/roboarc/tests/test_server_requests.py` checks the list and the names.

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

`BENCH` in `scripts/roboarc/mk_tasks.py` and `--bench` of dev/robotangle_mujoco's `scripts/robotangle/release_rebuild.py`;
`git mv` of `scripts/roboarc/`, `images/roboarc/` and this page; then the registration lines: `scripts/task_conventions.py`
(`BENCHMARKS`, `CUTOFF_CAP_EXCEPTIONS`), `scripts/task_cutoffs.toml` (row and `[[history]]`), `scripts/task_resources.toml`
(the `^roboarc-` rules), `docs/TAXONOMY.md`, `README.md`, the checks that name a benchmark's prefix or generator
(`ci_checks/check-tooling-identity.sh` `MODULE`, `check-standard-texts.sh`, `check-generated-tasks.sh`,
`check-unit-tests.sh`), and the `docs/CUTOFFS.md` render (`python3 scripts/task_cutoffs.py apply "<label>"`).
