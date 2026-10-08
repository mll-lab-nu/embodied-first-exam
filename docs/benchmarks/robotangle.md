# RoboTangle

RoboTangle is the published name of TopoGym, Jianwen Lyu's benchmark of topological manipulation puzzles: disentangling,
threading, untying and flattening. It runs on Genesis 1.2.1 (rigid bodies; deformables through libuipc's IPC and PBD) with
Nyx RGB rendering. The rename is user-facing only: directory and task names, labels, the image name and texts. Code
identifiers keep the old name: the simulator package `topogym`, the tooling `rcb_topogym.py` and `TOPOGYM_*` variables.
Renaming them would change the hashes every task is bound to.

## Families and tiers

11 families × up to 5 tiers (very_easy, easier, easy, medium, hard; `metadata.difficulty`) × 2 modes: 52 bases,
104 task directories `tasks/robotangle-<family>-<tier>-i00-{privileged,standard}`.
- Robots: ALOHA 2 bimanual (`aloha-2`; 14-D joint actions) in cast_coil, cast_keyhole, interlocked_claws,
  horseshoe_ring, rope_threading, knot_untying and blanket_flatten. A Franka Panda with a Robotiq 2F-85
  (`franka-robotiq-2f85`; 8-D) in hedgehog_in_cage, lock_picking, buzz_wire_3d and fiber_bundling.
- Physics:
  - CPU float64 rigid bodies (bit-deterministic on one host): cast_coil, cast_keyhole, hedgehog_in_cage,
    interlocked_claws, horseshoe_ring, buzz_wire_3d, fiber_bundling;
  - GPU fp32 rigid: lock_picking;
  - IPC deformables with deterministic libuipc patches: rope_threading, knot_untying;
  - PBD cloth: blanket_flatten.
- Grasping: an assisted grasp (`contact_weld_v1` and similar, metadata `grasp`) where the family uses one; physical
  grasping in knot_untying.
- Not in this release:
  - the families slotted_post_ring and orbits;
  - rope_threading very_easy / easier: their passing runs exist only on the author's working tree, and the frozen
    instances are not reachable from our hosts;
  - blanket_flatten easier: the author is reworking its oracle and prepared state.
  - These tiers follow in a later pull request (scripts/robotangle/release.json `not_shipped`).

## Tasks and generator

`python3 scripts/robotangle/mk_tasks.py [--check]` renders every task from:
- release.json;
- shared/: the release's task templates, verbatim;
- packages/: the upstream per-task texts;
- oracles/: the recorded oracle trajectories;
- the eai-standard/2.4 layer in `scripts/eai_standard/v2_4/` (+ 2.2's `rcb1.py`, `run.sh`, client pins), copied unchanged;
- `assets.json`: the pins of the frozen instances (below). With `--assets <dir>` (a local copy, `scripts/robotangle/assets.py
  fetch <dir>`) it also checks every instance's bytes against the bindings; without it, against the pinned hashes.

It needs only the Python standard library and `scripts/task_conventions.py`. `--check` re-renders into a temporary
directory and fails on any byte or mode difference. `scripts/robotangle/import_evidence.py` is the one-off importer that
made those inputs from the graded TopoGym packages; CI never runs it.

Each task carries copies of the tooling (`rcb_topogym.py`), the graders and the standard sim service (D9). Its
`runtime_binding.json` binds:
- the frozen instance (canonical JSON hash and asset hashes), which keeps its creation source as provenance;
- the tooling hash;
- the release runtime: the public simulator source, python, five pinned dependencies and the audited libuipc build;
- `uipc_builds`: both libuipc builds of the image by their `uipc-build.json` sha256, the audited wheel and the sm_86 build
  (Image, GPU architecture).

Every session refuses to start in an image whose installed runtime differs from it, whose libuipc builds are not those
two, or whose libuipc build in use is not the one the rule picks for the GPU. The session's `runtime_binding` names that
build (`uipc_build`).

## Large files: the private HF dataset

The frozen instances (`instance.json` + `instance_assets/`: archived IPC settled states, PBD initial states, up to 20 MB per
file; 52 bases, 173 MB) are **not in git** (CONTRIBUTING: no files > 2 MB). Owner decision, 2026-10-08. They live in the
private Hugging Face dataset `eai-v2-internal/robotangle-assets`, pinned by commit and by the sha256 of every file in
`scripts/robotangle/assets.json` (`scripts/robotangle/assets.py fetch|check|pin`). The same dataset holds the image's build
inputs: the release tree (`git archive` of `2dafa5f2b`, the paths the image copies), the audited libuipc wheel with its
`uipc-build.json` (recovered byte-for-byte from the wheel layer of the 0.2.17 image; its sha256 matches the build record)
and, since 0.2.21, the sm_86 build of the same recipe with its `uipc-build.json` (Image, GPU architecture).
- The image carries every instance under `/opt/robotangle/instances/<base>/`.
- A task directory keeps only `runtime_binding.json` (instance canonical sha256 + every asset's sha256 + tooling + runtime),
  so a task's identity (its dataset digest) still pins its instance.
- `/opt/robotangle/stage_instance.py <base> <dest>` copies the task's instance next to that binding and checks it:
  privileged `environment/Dockerfile` (`/app`) and `tests/Dockerfile` (`/tests`), both with `--purge` (the image keeps no
  other task's instance); the standard `sim` service's `entrypoint` (`/tmp/robotangle-instance`, `RCB_INSTANCE` points
  there), which then runs the unchanged `command: sh /srv/run.sh`. Every session checks the binding again
  (`frozen_binding.check_inputs`).
- Access: members of `eai-v2-internal` (`hf auth login` or `HF_TOKEN`). Only image builders need it; eval hosts pull the
  image.

## Image

`ghcr.io/mll-lab-nu/eai-robotangle:<images/robotangle/VERSION>` (0.2.21) is a public image, pushed by the maintainers after
validation. It contains Genesis AI's Nyx renderer (the `gs-nyx` wheels on PyPI); the benchmark owner has permission to
redistribute it in this image.

0.2.21 is 0.2.19 plus the NVIDIA Vulkan ICD and EGL vendor files and the sm_86 libuipc build (GPU architecture, below).
0.2.20, 0.2.19 plus the ICD and EGL files only, was built for validation and never pushed. 0.2.19 was an internal
organisation package. The build context comes from the private HF dataset (Large files, above). That dataset stays
internal; only the built image is public. Build instructions are in images/robotangle/README.md.

**GPU:** every task container gets exactly one GPU through its compose device reservation (`count: 1`,
`capabilities: [gpu]`) and no `runtime: nvidia`, as in `images/robopaint/`.
- NVIDIA_DRIVER_CAPABILITIES=all makes the container toolkit mount the driver's graphics libraries, and the image's ICD
  files point the Vulkan and EGL loaders at them. On a host whose toolkit injects devices through CDI (e.g. lab: Docker
  29.8 with nvidia-cdi-hook), the toolkit also mounts the host's `/etc/vulkan/icd.d/nvidia_icd.json`, and Vulkan listed
  the same GPU twice; the image sets `VK_ICD_FILENAMES` to its own ICD file, so it lists one.
- With `runtime: nvidia`, the image's NVIDIA_VISIBLE_DEVICES=all could expose every GPU of the host. Nyx crashes when two
  are visible.
- `count: 1` is always host GPU 0: Docker turns `count: N` into device IDs `0..N-1`, so on a multi-GPU host every agent,
  sim and verifier container lands on GPU 0 unless the runner pins GPUs. Two ways to use more GPUs:
  - one GPU per host or VM;
  - per-lane copies of the task directories whose reservations name the lane's GPU (`device_ids`), including
    `tests/docker-compose.yaml`. These copies are never committed (PROTOCOL §2.4).
- VRAM and concurrency:
  - an IPC sim (knot_untying, rope_threading) needs about 9-10 GB and runs alone on a 24 GB GPU. Next to other RoboTangle
    sims on one 24 GB RTX 4090, IPC scene builds failed with CUDA out of memory;
  - blanket_flatten needs about 6 GB;
  - at most 2 rigid trials per GPU.
- GPU architecture. Every family renders with Nyx, which needs RT cores; knot_untying and rope_threading also run libuipc's
  CUDA kernels, which come in two builds of one recipe:

  | compute capability | GPUs (examples) | libuipc build | run on it so far |
  |---|---|---|---|
  | 8.9 (sm_89) | RTX 4090, L4, L40S, RTX 6000 Ada | the audited wheel: native sm_89 code | RTX 4090: nops, exact restores of rope and knot |
  | 12.x (sm_120) | RTX 5090, RTX PRO 6000 Blackwell | the audited wheel: native sm_120 code | RTX PRO 6000: every oracle evidence run |
  | 8.6 (sm_86) | RTX A6000, A40, A10, RTX 3090 | the sm_86 build: native sm_86 code | nothing yet: no such GPU was available |
  | 8.0, 9.0, 10.0 | A100, H100, H200, B200 | — | none: no RT cores, so Nyx cannot render and no RoboTangle task runs |

  - The audited wheel (`89-real;120-real;120-virtual`) has native code for sm_89 and sm_120 only, and its compute_120 PTX
    cannot run on an older GPU. It stays the build every 8.9 and 12.x GPU loads, so these GPUs run the same libuipc binary
    as every evidence run and check so far. The sm_86 build (`86-real;86-virtual`) is the same recipe with only the architecture list changed,
    and the same pyuipc version and source commit, which the frozen IPC settled states record, so they restore with it.
    Every other GPU loads it: native code on 8.6, its compute_86 PTX elsewhere (untested). A GPU of compute capability
    7.5 (T4, RTX 20xx) can run neither build: its first IPC launch fails, and the sim ends with an infrastructure error.
  - Why two builds and not one wheel for all three: a single wheel of the same recipe built for sm_86, sm_89 and sm_120
    (2026-10-08) reproduced every host library and all 1216 sm_120 functions of the audited wheel byte for byte, but 8 of
    its 1230 sm_89 functions came out different (`make_spd<12>` and kernels of ExternalArticulationConstraint, the
    driving revolute and prismatic joints and the discrete-shell bending plasticity; the IPC coupler likely runs
    ExternalArticulationConstraint). An RTX 4090 would then run other IPC code than the audited wheel it was checked with,
    so that wheel is kept as evidence only (not in the image).
  - Selection (the tooling, `rcb_topogym.py` `select_uipc_build`): at Session start, before anything imports uipc, the
    tooling reads the visible GPU's compute capability through the CUDA driver API. 8.9 and 12.x keep the audited wheel in
    site-packages (`/opt/uipc-build.json`), so nothing changes there; any other GPU puts the sm_86 build's prefix
    (`/opt/uipc_sm86`) first on `sys.path`. A process that already imported uipc from the other build, or GPUs of mixed
    compute capability, are refused. `scripts/robotangle/release.json` `uipc_builds` records both builds, their rule,
    dataset folder and recipe; the sm_86 recipe is `images/robotangle/uipc-sm86-build/`.
  - The image build checks both wheels against their build records in the recipe's builder image (cuobjdump of nvcc
    12.8: wheel, version and backend hashes, native kernels, PTX) and keeps the result in `/opt/uipc-check.json`.
  - The host driver must include the graphics (GL/Vulkan) user-space libraries, not a compute-only install.

One image and one version serve both modes:
- the privileged environment and verifier `FROM` it;
- the standard `sim` sidecar uses it;
- the standard agent container and verifier use the shared client image pinned by digest.

## Time budget (D8)

`[agent].timeout_sec = 21600` (6 h) for every task, uniform within the benchmark. This is the benchmark owner's rule:
these puzzles are far harder than typical robotics tasks, and the budget probes the capability ceiling. Simulator
speed-ups give the agent more interaction within the 6 h; they never shorten it. One full reference execution takes
2–185 min (fiber_bundling hard is the longest). The standard sidecar's wall clock (`RCB_WALL_CLOCK_S`) is 21600 s as
well.

This is above PROTOCOL §2.3's default cap of 14400 s. **Accepted by the owner (2026-10-08) as a documented per-benchmark
exception** (PROTOCOL §2.3, issue #87, PR #88; `check-task-fields.sh` caps `robotangle-*` at 21600 s). RoboTangle results
state the 6 h budget and are compared only with results under the same budget (D8).

## Grading and determinism

**Privileged mode:**
- two open-loop replays of `/app/output/trajectory.npz` from the frozen instance, in fresh processes in the separate
  verifier sandbox (GPU reservation in `tests/docker-compose.yaml`);
- success requires the task's native predicate after the replay, with release and clearance checks;
- the video is rendered during the second replay.

**Standard mode:**
- the sidecar journals every executed control step and resumes crashes without a reset;
- its collect hook replays the recorded trajectory once in a fresh process;
- the verifier grades `final.json` without network.

**Rules for all families:**
- a physical-validity policy: contact-penetration limits, joint-torque caps and a table guard;
- a breakdown of the simulator is an infrastructure error, not a failure (`simulator_instability`, `infra_error`);
- CPU families replay bit-exactly on one host;
- GPU families are graded strictly live and tolerantly on replay, with the tolerances in each task's README Details.

## Standard mode: `eai-standard/2.4`

The standard twins serve `eai-standard/2.4` ([`STANDARD_MODE_2_4.md`](../STANDARD_MODE_2_4.md), issue #89, PR #90), TopoGym's
documented hardening of 2.2. The release called it "2.3" (dev/jianwen docs/rcb/STANDARD_MODE_2_3.md); that number went to
the realtime capability (#86), so it was registered as 2.4 = 2.3 + the operations capability (realtime stays optional; the
RoboTangle service does not offer it). Requests, cameras, proprioception, RCB1 frames and the process model are those of 2.2.
2.4 adds:
- request identity: `operation_id` plus a request deadline; an expired request gets 408 before execution;
- `GET /operations/<id>`, so that a timed-out call can be queried instead of re-sent, which would execute it twice;
- a service-owned watchdog for native calls that never return;
- the actual physics-tick ledger in journals and trajectories;
- instance qualification before grading (`instance_mismatch` → not evaluable).

The layer (`environment/rcb_client.py`, `environment/sim/rcb_limited.py`) is the reference implementation in
`scripts/eai_standard/v2_4/`: the release's files with the version string 2.3 → 2.4 and 2.4 module headers, nothing else.
`check-tooling-identity.sh` keeps every copy byte-identical, and `task_conventions.normalize` leaves it alone (a shared
source). The generator respells "eai-standard/2.3" to 2.4 in the task texts as well.

## World-frame information (D7)

Standard texts never say where objects are. They give the robot (base pose included), camera calibration, part names,
sizes, colours and the detailed goal; privileged texts may give world quantities. All 104 texts pass
`check-limited-texts.sh`'s patterns.

## Network policy

The agent's egress is open by default and switched per run with `scripts/set_agent_egress.py`, as for RoboWits, RoboLab and
BEHAVIOR-1K. No reference solution is publicly downloadable: this repository is private. The harness's web search is off
in official runs (PROTOCOL §5).

## Evidence and oracle levels

Every task is `oracle = "full"`, by the owner's decision of 2026-10-07. Each base has a passing oracle run in both modes on an
earlier build of this benchmark (the facts below). No oracle was re-run on this release's exact build (dev/jianwen
`2dafa5f2b`, source `ecb43962`, tooling `075ec08a`: the release template's `587043f1` plus the libuipc build selection).
The previous release, `6b6804ae4` (source `8f12ee70`, tooling `ae724119`),
had no oracle re-runs either.

The positive examples are recorded oracle runs that scored 1 in both modes:
- privileged: two fresh replays, deterministic;
- standard: live and replay;
- they ran on the TopoGym builds below (release, public source).

`solution/` ships those recordings:
- privileged: the graded `trajectory.npz`, which `solve.sh` copies;
- standard: the recorded `joint_position` rows, streamed through the client by `oracle_replay.py`.

Neither player was run on this build.

| family | very_easy | easier | easy | medium | hard |
|---|---|---|---|---|---|
| cast_coil | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` |
| cast_keyhole | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` |
| hedgehog_in_cage | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` |
| interlocked_claws | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` |
| horseshoe_ring | v18 `e0ae4ba9` | v18 `e0ae4ba9` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` |
| lock_picking | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` |
| buzz_wire_3d | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v16 `12f7c4fc` |
| fiber_bundling | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v18 `5b5677f0` | v17 `585ddc7b` |
| rope_threading | not shipped | not shipped | v18 `cadc53a3` | v18 `cadc53a3` | v18 `cadc53a3` |
| knot_untying | v18 `5b5677f0` | v18 `fc5ac3e1` | v18 `cadc53a3` | v18 `cadc53a3` | v18 `cadc53a3` |
| blanket_flatten | v19 `db0bb489` | not shipped | v19 `db0bb489` | v19 `db0bb489` | v19 `db0bb489` |

Equivalence notes are in scripts/robotangle/release.json (`note`):
- **buzz hard:** the graded trajectory replays bit-identically on the v18 image.
- **fiber hard:** CPU physics are bit-identical from v17 to v18.
- **rope and knot easy/medium/hard:** frozen instance state and configuration are identical to v18; the oracle code is
  unchanged.
- **knot easier:** its build differs from v18 in 22 public files, none of them a knot or IPC physics file.

Sources:
- the author's status pages on dev/jianwen: docs/rcb/ORACLE_FIXES_FOR_JIANWEN.md (Final status) and
  docs/progress/below_easy_status_overview_zh.md;
- the lab runs named in each task's README (Reference solution).

### What changed between each evidence build and this release

The facts below come from `git diff` of the public simulator source (what the image installs) and the task templates
(tooling, graders, sim service, client) on dev/jianwen. The owner counts these tasks as validated by the sweeps, hence
`full`; reviewers can check each family against these facts.

**This release, `6b6804ae4` (source `8f12ee70`) → `2dafa5f2b` (source `ecb43962`): blanket_flatten's generated PBD birth states (2dafa5f2b)
and work on families that are not shipped (5536fdfd6: slotted_post_ring and orbits below-easy, blanket easier).**
- Public simulator source:
  - `simulator/env.py`: `Env.reset` calls `ensure_initial_state()`, which returns at once for every task without a PBD
    initial-state recipe. Only blanket_flatten's tasks have one.
  - `world/physics/pbd_initial_state_generation.py` is new.
  - `tasks/blanket_flatten/{common,corner_folds,gathered}.py`: the recipe and the generated-state hook. Where the stored
    archive applies, the old path is unchanged.
  - slotted_post_ring and orbits files, and the orbits model revisions in `variation_records.py`.
- Templates:
  - `rcb_topogym.py`: Session records the initial-state source. It adds an `instance_generated` branch for generated
    states and keeps the old instance check otherwise. It registers its replaced kernels in the generation recipe, and has
    the slotted grasp assist.
  - Both graders accept a generated state when its recipe matches and the live run and replay start from the same state.
    Otherwise they require `instance_exact` as before, and report `initial_state_generated`.
  - `server.py`, `replay.py` and `finalize.sh` pass the initial-state record through.
- So for every shipped family except blanket_flatten, the release's changes act only on an instance with a generated
  state. They add the report fields `initial_state_generated` and `initial_state`, and nothing else.
- For blanket_flatten, see GPU portability below.

**merged-v18 (`8d7d16489`, source `5b5677f0`) → previous release (`6b6804ae4`, source `8f12ee70`): 26 files.**
- blanket_flatten:
  - corner-fold geometry and preparation: `assets/geometry/blanket_corner_folds.py`, `tasks/blanket_flatten/*`,
    `world/physics/cloth_preparation.py`;
  - the very_easy / easier archives, `catalog.json` and `variation_records.py` entries;
  - `world/genesis_world.py`: a particle's speed is its end-of-tick displacement. It reads only particle entities
    without material coordinates, i.e. the PBD cloth.
- orbits:
  - `assets/geometry/orbits_chain.py`, `tasks/orbits/*`;
  - `goal_description.py` (the chain tiers' text) and the orbits model revision in `variation_records.py`;
  - `rcb_topogym.py` `simulator_config` for the orbits chain tiers;
  - `world/genesis_world.py`: a rigid constraint solver given by name, which only the orbits chain uses.
- horseshoe_ring very_easy / easier: `tasks/horseshoe_ring/below_easy.py`, `horseshoe_ring_easier.py` and the easier
  settled poses. The horseshoe tiers that ship here are graded on the build that already has these files: all 35
  horseshoe simulator files are identical between that build and the release.
- rope_threading very_easy / easier: `tasks/release_profile.py` (they take the original tiers' environment). The original
  tiers' parameters are built as before, and a frozen instance carries its own configuration.
- Unchanged: the graders, the sim service, the client and the 2.3 layer. `rcb_topogym.py` changes only in the orbits
  block and comments.
- **So:** cast_coil, cast_keyhole, hedgehog_in_cage, interlocked_claws, lock_picking, buzz_wire_3d, fiber_bundling,
  knot_untying and horseshoe_ring easy / medium / hard have no change to a task, geometry, asset or physics file. The
  shared changes do not apply to their scenes, which have no particle entity and no solver given by name.

**Other evidence builds:**
- **rope / knot easy, medium and hard**, graded on the v18 build before its rebase (`1048cea73`, source `cadc53a3`). From
  there to merged-v18:
  - the below-easy knot and orbits definitions were added (`knot_untying.py` geometry, `knot_untying_simplified.py`, the
    knot very_easy / easier task files, the orbits files, `variation_records.py`);
  - the frozen states merged-v18 rebuilt for knot and rope easy / medium / hard are identical (state hash and simulator
    configuration);
  - then as above.
- **knot easier**, graded on a lab tree (source `fc5ac3e1`). It differs from merged-v18 in 22 public files: blanket
  below-easy, horseshoe easier, orbits below-easy, the release profile, catalog, cloth preparation and variation
  records. No knot_untying file or IPC physics file is among them, and the knot files are identical to the release's.
- **buzz_wire_3d hard**, graded on the merged-v16 tree (image 0.2.14-dev). The graded trajectory replays bit-identically
  on the merged-v18 image: every per-row state hash, the success row and the 1.027 mm minimum clearance. Then as above.
- **fiber_bundling hard**, graded on merged-v17. merged-v18's speed-ups keep CPU physics bit-identical; only fiber has an
  entity above 64 DOFs. Then as above.
- **blanket_flatten very_easy / easy / medium / hard**, graded on merged-v19 (`89cc32674`, source `db0bb489`). From there
  to the release:
  - the easier rework (new fold options): `profile_parameters` adds them only where they differ from the defaults, so
    very_easy keeps its parameters and frozen-state identity;
  - the easier archive was replaced;
  - the orbits changes above.
  - easy / medium / hard use the gathered archives, which are unchanged.

### Harbor nop records

- **easy / medium / hard, all 10 non-blanket families plus blanket:** `nop` scored 0 in both modes, 78 runs with
  `infra_error` 0, in the candidate pipeline's Harbor nop checks of the merged-v18 candidate (lab
  `align_v18/cand_v18`, 2026-10-05). The same holds for merged-v17. The frozen states are identical to the shipped ones
  for the non-blanket families.
- **very_easy / easier, on the previous release's build** (`6b6804ae4`; 2026-10-07; an RTX 4090; image
  `sha256:b4cc8d786c44…` built with the audited libuipc wheel; `scripts/robotangle/nop_records.json`):
  - 37 of 38 directories scored 0 with `infra_error` 0. Every standard run had `runtime_binding_ok` 1 and `instance_exact`.
  - The 38th, blanket_flatten very_easy standard, could not start on that GPU: that build refused a frozen PBD state
    prepared on another GPU.
- easy / medium / hard: not re-run on either release's build.
- **This release's build (`2dafa5f2b`, image 0.2.18): no nop yet. All nops on it are pending.**

### GPU portability (blanket_flatten)
- blanket_flatten's frozen PBD states were prepared on an RTX PRO 6000 Blackwell Max-Q (compute capability 12.0,
  188 SMs), the GPU of every blanket evidence run.
- Since this release (dev/jianwen `2dafa5f2b`, design note docs/rcb/BLANKET_GENERATED_INITIAL_STATES.md there),
  `Env.reset` checks the stored archive's resource profile:
  - if it matches the runtime, the stored state applies and nothing changes;
  - otherwise the task runs the recipe frozen in the instance on this GPU. It caches the result inside the container,
    under `$TOPOGYM_INITIAL_STATE_CACHE` (default `/opt/rcb-cache`), keyed by profile and recipe hash.
- `instance_exact` stays false for a generated state. The state counts as the instance when:
  - the runtime binding holds;
  - `recipe_match` holds;
  - the live run and the replay agree on `manifest_sha256` and `instance_sha`.
- Graders report `initial_state_generated`.
- Cost:
  - standard mode: generation runs once per trial, in the sim service's startup (5–9 min for very_easy). It counts
    against the agent's clock and the startup watchdog (1800 s); the replay hits the cache.
  - privileged mode: the agent's first Session generates the state, and the verifier generates it again in its own
    container.
- **Validated** (by the author): only very_easy on an RTX 4090. It was generated deterministically twice (identical
  `state_sha256`), and the cloth lies within 13 µm of the lab state. The CI tests are unchanged, plus a new test (7/7).
- **Not validated:**
  - generation for easy / medium / hard;
  - any oracle on a generated state: the blanket evidence comes from the stored states on the RTX PRO 6000;
  - nops on this build;
  - a GPU A/B of the stored path.
- Other families: the rigid families simulate on the CPU and are not affected. knot very_easy restored exactly on an
  RTX 4090 (previous build); rope was not checked on one.

## Pending (stated in the pull request)

1. ~~The audited libuipc wheel~~ done 2026-10-08: in the private HF dataset (Large files, above).
2. ~~Build and check the image~~ done 2026-10-08: 0.2.19 built from the pinned dataset; its installed runtime equals
   `release.json` `runtime` (the check in images/robotangle/README.md); every task image stages its instance and passes
   `check_inputs`. 0.2.21 (public; the GPU fix and the sm_86 libuipc build above) is to be validated the same way before
   it is pushed, on an RTX 4090 and an RTX PRO 6000.
3. **Exact-restore preflight per frozen instance on that image.** Each instance was frozen by an earlier TopoGym source
   and is bound to this release's runtime; whether it restores bit-exactly here is not yet checked.
4. **nop, both modes, every task, on this build (`2dafa5f2b`).** The records above are from earlier builds:
   `harbor run -p tasks/<task> -a nop`, or
   `for t in tasks/robotangle-*/; do harbor run -p "$t" -a nop -n 1 -k 1; done`.
   Each needs a GPU host with the image; one simulator per GPU.
5. **The oracle players** (`harbor run -p tasks/<task> -a oracle`) on a sample: two or more tasks per mode.
6. **blanket_flatten on GPUs other than the RTX PRO 6000:** validate the generated states for easy / medium / hard, and an
   oracle on a generated state (GPU portability above). Owner decision 2026-10-08: blanket_flatten ships (all 8 tasks); the
   maintainers pre-generate and cache the blanket initial states on the eval hosts, so the 5–9 min generation is not on
   the agent's clock, and spot-check easy / medium / hard generation before formal runs.
7. **The tiers not in this release** (above).
8. **IPC on compute capability 8.6** (RTX A6000 class, the sm_86 libuipc build): compiled and audited, never run on such a
   GPU; none was available. GPU physics is not bit-identical across GPU models anyway, so the evidence from the RTX PRO 6000
   does not transfer bit for bit to any other GPU.

## Protocol requests (raised in the proposal issue; decided 2026-10-08)

- **Agent budget:** accepted as a documented per-benchmark exception, 21600 s (issue #87, PR #88).
- **Standard protocol:** accepted as `eai-standard/2.4` (2.3 went to the realtime capability): the allowlist, the
  reference implementation `scripts/eai_standard/v2_4/`, the identity and client checks (issue #89, PR #90).

## Licences

- Genesis 1.2.1: Apache-2.0.
- libuipc: Apache-2.0.
- ALOHA 2 and Robotiq 2F-85 models: MuJoCo Menagerie (BSD-3-Clause / per their LICENSE files).
- Nyx (Genesis AI, the `gs-nyx` wheels on PyPI): the benchmark owner has permission to redistribute it in the public image.
