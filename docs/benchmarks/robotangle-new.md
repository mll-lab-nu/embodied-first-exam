# RoboTangle-New (RoboTangle on MuJoCo)

RoboTangle's topological puzzle families (docs/benchmarks/robotangle.md) on MuJoCo 3.14.0 physics, as a benchmark of its
own (user decision, 2026-10-12). The Genesis benchmark RoboTangle (`robotangle-*`, image `eai-robotangle:0.2.22`) stays
as it is: its tasks, image, tooling and dataset entries are not changed by this one.

- Name: `robotangle-new` is a working name (the user may choose the final one). It is one parameter (Registration,
  below). Final for now (user, 2026-10-12): "essentially RoboTangle, kept apart from the old results for now".
- Status: generator, image recipe and registration ready; no task yet. The tasks come with the release after the
  physics freeze (dev/robotangle_mujoco `docs/rcb/HARBOR_FREEZE_RUNBOOK.md`).

## Tasks

`robotangle-new-<family>-<tier>-i01-{privileged,standard}` (PROTOCOL §2.2):
- `<family>` with dashes (`interlocked-claws`); `[metadata].family` keeps the underscores.
- `<tier>`: the variation id without the family prefix, with dashes. A ported tier keeps RoboTangle's tier
  (`very-easy`, `easier`, `easy`, `medium`, `hard`); a redesigned set has its own ids (`rd-very-easy` … `rd-hard`); a
  new variation its own name (e.g. `v2-very-easy`).
- `i01`: the MuJoCo instance (the HF dataset's `instances/<family>-<tier>-i01/`); RoboTangle's Genesis instance of the
  same scene is its `i00`.

Every task is RoboTangle's task contract (the same tooling `rcb_topogym.py`, graders, sim service and eai-standard/2.4
layer as RoboTangle; docs/benchmarks/robotangle.md, "Grading and determinism", "Standard mode") with these differences:
- physics: MuJoCo 3.14.0, CPU float64 (the blanket families' cloth: a deterministic CUDA step, `blanket_vbd_gpu`);
- the numpy / OpenBLAS SIMD masking in every container that runs a Session (so every CPU class builds the same frozen
  bytes); `render_bridge.py` and `nyx_direct.py` next to every tooling copy, named in the runtime binding;
- the texts state what the tooling grades: the contact-review values come from `CONTACT_RULE`, and the grasping rule is
  `Session.grasp_rules()` of the instance (the weld's slip force over 20 ms, 60 N ALOHA / 65 N Robotiq, and the
  Robotiq's release after 0.2 s without finger contact).

## Generator and release

- `scripts/robotangle-new/mk_tasks.py` (`--check` in CI) renders the task dirs from this directory: `release.json`,
  `packages/` (the texts of the RoboTangle base each task ports, renamed, with the family's own texts over them),
  `oracles/`, `assets.json`, `shared/` (the tooling and the graders). Generated tasks end with
  `scripts/task_conventions.py` normalize.
- The release files are written by `scripts/robotangle/release_rebuild.py --bench robotangle-new --onto <main>` on
  dev/robotangle_mujoco: image, instances made in the image, release files, render, checks, Harbor oracle / nop.
- Large files: the frozen instances are in the private HF dataset `eai-v2-internal/robotangle-assets` (RoboTangle's),
  under `instances/<base>/`, pinned file by file in `scripts/robotangle-new/assets.json`.
- Image: `ghcr.io/mll-lab-nu/eai-robotangle-new:<images/robotangle-new/VERSION>`, built FROM the published
  `eai-robotangle:0.2.22` with the release commit's simulator source and the frozen MuJoCo instances
  (`images/robotangle-new/Dockerfile`, generated from dev/robotangle_mujoco's `Dockerfile.mujoco`; context:
  `scripts/robotangle-new/fetch_image_context.sh`).

## Time budget (D8)

10800 s (3 h) wall clock in both modes and every family (user, 2026-10-13; 7200 s from 2026-10-12; `scripts/task_cutoffs.toml`), within the default cap: no exception.
RoboTangle has its own row (7200 s since 2026-10-12). The texts say "the time limit (`## Time limit`)". The standard service's clock
(`meta["time_left_s"]`, `RCB_WALL_CLOCK_S` follows the table) counts from the agent's first request to the service (PROTOCOL §2.12;
logged in `episode.jsonl`, kept over a restart), so the instruction has the common closing sentence and no sentence of its own about the
service's clock (2026-10-13; RoboTangle's "has run since the service first started" is not carried over). The service still ends the
episode with reason `timeout` when that count reaches 0; counted from the first request, that is never before the harness's cutoff.

## Safety readings in standard mode (`meta["safety"]`)

User decision 2026-10-12: a standard response publishes only what the robot can feel itself, the readings a real robot
senses through its own drives and controller:
- `forcing`: the largest force an arm, or a part it holds, pressed with (`max_press_force_n`), the arm drive's load
  meanwhile (`max_drive_fraction_while_pressing`), the longest run of the forcing condition (`longest_forcing_s`), the
  number of forcing events and the last ones (arm, joint, step, drive fraction, torque cap, force), with the thresholds
  (`event_after_s`, `near_cap_fraction`, `contact_n`). In an event, what pressed is the robot's own link or "a held part",
  and what it pressed on is "the environment": no task part is named.
- `table_guard`: the control steps whose gripper target the table guard stopped (the robot's own targets).
- `ik_jumps`: IK solutions far from the current joints.
- `rules`, `scope`: the rules revision and what the reading covers.

Not published (the grader's evidence, final.json and the review): task-contact depths (part to part), held-finger
contact depths, review events, soft-body volume ratios, cord attachment stretch. Why: the agent may be judged on its own
forcing (a breakdown it forced is its failure), so it sees that; the depth of a contact between two task parts, which
part touched which, and the internal state of a deformable are not something the robot can sense.
Implementation: the sim service's `robot_felt` (`scripts/robotangle-new/shared/standard/sim/server.py`,
`SAFETY_PUBLISHED`), on the benchmark's own copy; RoboTangle's service is unchanged.
`scripts/robotangle-new/tests/test_server_requests.py` checks that no dropped field and no task-part name reaches a
response. Pending the owner: this listing under PROTOCOL §4.5's declared telemetry.

## Standard mode, world frame, network

As RoboTangle (docs/benchmarks/robotangle.md): `eai-standard/2.4`; no world coordinates in standard texts (D7,
`check-standard-texts.sh`); agent egress on the allowlist (PROTOCOL §2.11).

The agent-facing frame of the standard service is the robot frame (user, 2026-10-13: the table height and the robot base's
world position are never disclosed): origin at the robot's kinematic root link on its mounting, axes as the simulator's world
(+z up). The proprio TCP poses, `ee_pose` targets, `/kinematics` (ik targets, fk poses) and the camera extrinsics (static
mounts, per-observe calibration, per-frame `extrinsic_cv`) are in it; `robot_spec.base.pose` is the identity; no text and no
`/spec` field states a world coordinate of the mounting. `joint_position` rows, physics, graders and state hashes do not depend
on the frame. Privileged mode keeps the simulator's world frame (its tooling is the simulator); its texts state no table height
or robot base position either.

## Registration (the lines a rename changes)

`BENCH` in `scripts/robotangle-new/mk_tasks.py` and `BENCH` in dev/robotangle_mujoco's
`scripts/robotangle/release_rebuild.py` (or `--bench`); `git mv` of `scripts/robotangle-new/`, `images/robotangle-new/`
and this page; then the registration lines: `scripts/task_conventions.py` (`BENCHMARKS`),
`scripts/task_cutoffs.toml` (row and `[[history]]`), `scripts/task_resources.toml` (six `^robotangle-new-` rules),
`ci_checks/check-task-fields.sh` (`BUDGET_EXCEPTIONS`: the default cap, because of the prefix overlap), `ci_checks/check-tooling-identity.sh` (`MODULE`),
`ci_checks/check-generated-tasks.sh`, `ci_checks/check-unit-tests.sh`, `docs/TAXONOMY.md`, `README.md`, and the
`docs/CUTOFFS.md` render (`python3 scripts/task_cutoffs.py apply "<label>"`). A name that starts with `robotangle-`
overlaps RoboTangle's prefix: `BENCHMARKS` lists it first, RoboTangle's generator and `check-tooling-identity.sh` tell
the two apart; a name without that overlap needs none of this.
