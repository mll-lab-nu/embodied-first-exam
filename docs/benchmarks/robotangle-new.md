# RoboTangle-New (RoboTangle on MuJoCo)

RoboTangle's topological puzzle families (docs/benchmarks/robotangle.md) on MuJoCo 3.14.0 physics, as a benchmark of its
own (user decision, 2026-10-12). The Genesis benchmark RoboTangle (`robotangle-*`, image `eai-robotangle:0.2.22`) stays
as it is: its tasks, image, tooling and dataset entries are not changed by this one.

- Name: `robotangle-new` is a working name (the user may choose the final one). It is one parameter (Registration,
  below).
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

21600 s (6 h) in both modes, RoboTangle's budget (`scripts/task_cutoffs.toml`). Pending: the owner's decision to record
it as this benchmark's exception in PROTOCOL §2.3 (the cutoff table, `CUTOFF_CAP_EXCEPTIONS` and `check-task-fields.sh`
carry it already).

## Standard mode, safety readings, world frame, network

As RoboTangle (docs/benchmarks/robotangle.md): `eai-standard/2.4`; `meta["safety"]` as declared there (pending: the
owner lists this benchmark under PROTOCOL §4.5's declared telemetry); no world coordinates in standard texts (D7,
`check-standard-texts.sh`); agent egress on the allowlist (PROTOCOL §2.11).

## Registration (the lines a rename changes)

`BENCH` in `scripts/robotangle-new/mk_tasks.py` and `BENCH` in dev/robotangle_mujoco's
`scripts/robotangle/release_rebuild.py` (or `--bench`); `git mv` of `scripts/robotangle-new/`, `images/robotangle-new/`
and this page; then the registration lines: `scripts/task_conventions.py` (`BENCHMARKS`, `CUTOFF_CAP_EXCEPTIONS`),
`scripts/task_cutoffs.toml` (row and `[[history]]`), `scripts/task_resources.toml` (six `^robotangle-new-` rules),
`ci_checks/check-task-fields.sh` (`BUDGET_EXCEPTIONS`), `ci_checks/check-tooling-identity.sh` (`MODULE`),
`ci_checks/check-generated-tasks.sh`, `ci_checks/check-unit-tests.sh`, `docs/TAXONOMY.md`, `README.md`, and the
`docs/CUTOFFS.md` render (`python3 scripts/task_cutoffs.py apply "<label>"`). A name that starts with `robotangle-`
overlaps RoboTangle's prefix: `BENCHMARKS` lists it first, RoboTangle's generator and `check-tooling-identity.sh` tell
the two apart; a name without that overlap needs none of this.
