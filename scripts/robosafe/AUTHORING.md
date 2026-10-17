# RoboSafeBench tasks: how they are made

The tasks are RoboSafeBench's own families. Nothing about a family is written here: the scene, the request, the rules,
the operator's answers, the verdict and the scripted reference all live in RoboSafeBench, in the image
`eai-robosafe` (`images/robosafe/`). This directory freezes instances of them and renders the task directories.

## Steps

1. **Pin RoboSafeBench.** Set the commit and version in `images/robosafe/source.env`, bump `images/robosafe/VERSION`,
   prepare the build context and build the image (`images/robosafe/BUILD_ONLY` says how). A new commit is a new image
   tag: never rebuild a tag that trials have used.
2. **Freeze the instances** (needs the simulator: the image, or a venv with its pins and RoboSafeBench on the path):
   `python scripts/robosafe/make_instances.py` writes `families.json` (the selection: tracks AB, C, D, E, F on the
   UR5e, every member, seed 0), `instances/<slug>-<NN>.json` (the key, the task text, the start state's hash, the
   control API's description) and `oracles/<slug>-<NN>.json` (the reference as rows, with its outcome, and the outcome
   of doing nothing and of exiting `done` at once). It fails a family whose reference does not pass, or where a
   trivial strategy passes. Run it with the same RoboSafeBench commit as the image: the service refuses to start when
   the image does not rebuild the frozen start (`state_sha`).
3. **Render**: `python3 scripts/robosafe/gen_tasks.py render` (standard library only; every task's DIGEST is written
   with it), then `check` must pass.
4. **Evidence** (CONTRIBUTING.md): `python scripts/robosafe/tests/test_service.py <slug>-<NN> ...` in the simulator's
   environment, then Harbor's oracle (reward 1) and nop (reward 0) on every task, and the two replays' hashes from
   `verifier/verdict.json` (`replays.state_sha`).

## Rules that keep a task honest

- **Names.** A task is `rsb-<slug>-i<NN>-standard`; the slug is `<track><nn>`, neutral, and NN runs over the
  family's members in a hashed order. Nothing the agent's container holds names the RoboSafeBench family, the member
  or the hazard: `environment/Dockerfile` copies the client only; `environment/sim/` (with `instance.json`) is mounted
  into the sim sidecar alone.
- **The task text** is RoboSafeBench's brief under the condition `sim` (`prompts.task_brief`), with its closing
  sentence pointing to the exits instead of the `end` tool; `make_instances.py` refuses a brief whose closing sentence
  changed. No safety policy is added.
- **The interface** is RoboSafeBench's control API, relayed unchanged (`shared/standard/rcb_rsb.py` documents what
  the adapter needs from it). A type or layout name must not say what is on the table (no `object`, `label`, `mask`,
  `name`); results the API returns must not name the scene's things beyond what the agent's own reference allows.
- **Shared files.** `shared/standard/rcb_service.py`, `rcb1.py` and `rcb_client.py` are byte-identical to the other
  `eai-standard/2.1` benchmarks'; additions go into `server.py`, never into them.
- **No twin.** No task has a privileged twin: the standard tasks, and the realtime set's `-standard-realtime` tasks
  (`gen_realtime.py`; docs/benchmarks/robosafe.md, "Owner review" and "Standard-realtime tasks"); the generator keeps
  one instance file per task so that a privileged twin could be added.

## The development stand-in

`dev/rcb_rsb_dev.py` gives an episode RoboSafeBench's skill tools as one-row command types. It exists to test the
plumbing (notes, exits, finalize, grader, Harbor) and is copied only into development renders
(`make_instances.py --dev`, `gen_tasks.py render --dev --out <scratch>`; `gen_tasks.py` refuses `--dev` into
`tasks/`). The tasks use RoboSafeBench's low-level control API.

## New mechanism and visual candidates

The append-only reservations are `a38` (`h_bimanual_knife_transfer`, YAM), `c19`
(`d_bounded_recovery`, UR5e), `f12` (`g_plate_cloth_clearance`, UR5e) and `d18`
(`e_delegation_revoked`, UR5e). The plate panel has four separate criterion/plan
hazard/benign members. Authority's `explicit_safe_plan` is a request variant,
allocated only when requested with `--variants explicit_safe_plan`; its IDs do
not replace the default pair. G1 pressure uses the existing
`e_room_stranger_escalates` / `d10` family. Its room and onboard conditions need
independent evidence. Native body exclusions still apply. Disabled state
freshness remains held. Selection metadata describing development scope is not
admission evidence, and retired instance IDs are never assigned to another key.

For a new realism candidate, first join the frozen source and actual installed
image receipts with `candidate_identity.py --frozen <frozen_candidate.json>
--installed-audit <installed_audit_NODE.json> --image <image/candidate.json>
--out <new-receipt.json>`. The receipt requires a
full source commit, image ID, tracked source digest and all four visual fields:
`asset_profile=realism_v3`, `visual_revision`, `asset_manifest_sha256` and
`physics_catalog_version`. It grants no admission.

Pass the same `--candidate <new-receipt.json>` to `make_instances.py --index-only`,
`import_admission.py` and `make_instances.py --served-only`. Index and freeze run
inside that exact installed image, with `ROBOSAFEBENCH_COMMIT`,
`RCB_FREEZE_IMAGE_ID` and `ROBOSAFEBENCH_ASSET_PROFILE` set to its receipt. Mount
the RCB authoring files, never a native simulator checkout. A pruned image also
needs the exact-source checksummed prompts helper described in `task_text()`.
Admission import checks the raw complete native gates, installed package path,
empty native `PYTHONPATH`, isolated Python, absence of a source overlay, actual
image identity and complete visual record coverage. Exact admitted keys retain
family, body, member/evidence, seed, camera condition, interface, clock, request
variant, movers and realtime think interval. A seed or camera cannot inherit
another key's proof. Required image cameras such as the plate's front and top
are distinct from room camera conditions.

Collecting native results into import rows, selecting the served set and exporting it are done by RoboSafeBench's
release tooling, which this repository does not carry. The 0.5.4 tasks in `tasks/` are such a frozen export:
`check_release.py check` (ci_checks/check-generated-tasks.sh) holds them to `release.json`, and `check_release.py write`
records a deliberate change.

The frozen instance and oracle both retain the complete candidate receipt.
New generated oracle plans retain their key, start hash, expected final result
and candidate identity. Their frozen HTTP policy requests every public camera
initially and after each chunk, so a required top view is received through the
same public image path as the front view. The canonical oracle player and the
full-task HTTP checker execute that same policy; historical oracle playback
keeps its original camera selection.
Rendering binds the compose image by actual image ID and records source,
digest, profile, revision and manifest hash in public task metadata and README.
The sim sidecar checks runtime profile and manifest identity before building an
episode. A registry with this receipt cannot accept old instances, oracles or
admissions without an identical receipt. Realtime freezes also require their
own matching receipt and remain held until independently implemented and checked.
Native assets must resolve inside the installed package. The retired
`ROBOSAFE_THIRD_PARTY` variable must be absent, including when an inherited value
is empty; new compose commands unset it before importing the package. The current
`ROBOSAFEBENCH_THIRD_PARTY` is empty so the packaged vendor directory is used.
Generated `DIGEST` values bind the final task bytes through the existing
normalization step. Keep complete-task freeze, full oracle HTTP completion,
invariants, image preflight and model difficulty as distinct evidence stages;
never create placeholder successful exports while any stage is pending.
