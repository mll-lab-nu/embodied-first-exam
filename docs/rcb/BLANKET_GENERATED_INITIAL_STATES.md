## Generated Blanket birth states on other GPUs (2026-10-08)

**Why.** A Blanket instance starts from a frozen numeric PBD archive (`pbd_initial_state.py`, codec
`rigid_pbd_numeric_v2`). An archive restores only on the resource profile it was prepared on
(`initial_state_compatibility.resource_profile()`: CUDA compute capability, SM count and the software stack), because the
GPU physics is deterministic on one GPU model but not across models. Every shipped Blanket archive was prepared on lab's
RTX PRO 6000 (`cuda_sm120_mp188`). So every Blanket task, agent runs included, failed at sim start on any other GPU. The
RoboTangle PR #81 nop on an RTX 4090 failed with `Frozen initial-state incompatibility at
backend/device/compute_capability`. Qineng decided on 2026-10-08: when a frozen state is missing or does not match the
runtime, the simulator generates one on the spot.

**What changed (simulator, `topogym/`).**
- `world/physics/pbd_initial_state_generation.py` (new). `Env.reset` calls `ensure_initial_state()` after it builds the
  task and before it declares the scene.
  - If the stored archive's profile equals the runtime's, nothing happens. The same holds for a codec v1 archive, which
    names no device. The archive then restores exactly as before.
  - Otherwise the module runs the recipe frozen in the instance on this GPU:
    - the scene: the instance's task parameters with a flat birth. Its `identity` must equal the stored archive's.
    - the preparation the stored archive records (`qualification.preparation`): its `PreparationConfig`, its fold
      profile (a profile option added later counts at its default) and its acceptance scope.
    - the controller of the task's family: `initial_state_recipe()` returns `ClothPreparation` for the gathered tiers
      and `CornerFoldPreparation` for the corner tiers. The run is the same sequence as
      `scripts/prepare_blanket_initial_states.py --tier`: world, robot at home, `controller.run`,
      `export_initial_state`. It skips the script's logs and video, does not build the cameras (identity and physics do
      not depend on them) and uses one BLAS thread (below).
  - An instance that names no archive at all, such as a resource lookup on an uncatalogued profile, uses the family's
    recipe with the default `PreparationConfig`. For the five shipped tiers that default equals what their archives record.
  - The generated archive passes the same qualification and restores through the same checks as a stored one: identity,
    backend compatibility, buffer layout, and the acceptance scope.
- `tasks/blanket_flatten`:
  - `stored_initial_state()` holds the old body of `frozen_initial_state()` and returns None when no archive is named.
  - The generator sets `generated_initial_state`, and `frozen_initial_state()` returns it when it is set.
  - `initial_state_recipe()` exists on `GatheredBlanketTask` and on `CornerFoldBlanketTask`.
- One BLAS thread during the preparation. Its conjugate gradients take long dot products, and OpenBLAS splits those
  across one thread per host core. The rounding can then depend on the core count. On a loaded shared host the threaded
  dot product is also orders of magnitude slower (ws: 20,000 dots of 25,000 elements took more than 4 min threaded and
  0.03 s on one thread). The generator sets numpy's and scipy's OpenBLAS to one thread for the preparation only and
  restores them afterwards.

**What changed (task templates).**
- `rcb_topogym.py`:
  - It registers its run-time physics replacements in the recipe: the tooling sha256, the fixed-point PBD sums, the
    pinned rigid solve arm and the bounded PBD-rigid contact. These act on the preparation too.
  - New `Session.initial_state` (where the birth state came from, with its hashes) and `Session.instance_generated`.
  - The instance check handles a generated state (below).
  - New `status()["instance_generated"]`; the `replay` CLI output also prints the record.
- Standard service:
  - `startup_binding.json` gains `instance_generated`, `instance_sha` and `initial_state`.
  - `replay.py`'s verdict gains `instance_generated` and `initial_state`.
  - `finalize.sh` copies both into `final.json`.
- Graders:
  - The standard `grade.py` accepts a generated state under the rule below.
  - The privileged `grade.py` accepts `instance_exact or instance_generated`, together with `instance_matches` and the
    runtime binding.
  - Both report `initial_state_generated` in `reward.json`.

**Cache.** Each entry is `<root>/<runtime resource profile>/<recipe sha256[:32]>/` and holds:
- `state/` (`manifest.json`, `arrays.npz`);
- `recipe.json`, `qualification.json`, `generation.json`.

The root is `$TOPOGYM_INITIAL_STATE_CACHE`, else `$XDG_CACHE_HOME/topogym/initial_states`, else `~/.cache/…`. In the image
that is `/opt/rcb-cache/topogym/initial_states` (mode 1777). The recipe hash covers:
- the scene identity;
- the preparation (controller, configuration, profile, acceptance);
- the installed simulator source (`SOURCE.json`);
- the codec;
- the process's run-time physics.

How entries are written and used:
- An entry is committed with one rename under a file lock. An entry that differs from its own record is refused, not
  replaced.
- A preparation that fails its own qualification is recorded as failed. The physics is deterministic, so a retry would
  fail the same way, and crash-recovery restarts fail fast.
- In a standard task, the live service, its crash-recovery restarts and the collect hook's fresh-process replay share one
  container, so they restore the same generated bits.
- A fresh container, such as the privileged verifier's, generates the state again. That gives the same state on the same
  GPU model.

**Identity.** `instance_exact` keeps its meaning: the state hash equals the frozen evidence `state_sha`. It is false for a
generated state. A generated state counts as the instance when all of these hold:
1. The runtime binding holds, unchanged: the instance, the assets including the stored archive, the tooling, and the
   installed source and dependencies.
2. `recipe_match`: the stored archive's scene identity and recorded preparation equal the ones run here.
3. In standard mode, the live start (`startup_binding.json`) and the fresh replay (`replay.verdict.json`) report the same
   generated archive (`initial_state.manifest_sha256`) and the same initial state hash (`instance_sha`).

Every such run carries `initial_state_generated = 1` in `reward.json`. It also records the runtime profile and two hashes
of the archive:
- `manifest_sha256`: the file the run restores.
- `state_sha256`: the archived state, bit for bit, without scratch. The scratch is the rigid collider's per-substep
  buffers (its static configuration, the contact cache and the cache's validity flag are kept) and the PBD spatial hash
  with its reordered particle copies. Genesis rebuilds that scratch before use in every substep, and its slot order
  follows GPU atomics. So two identical preparations differ there, and in the zip timestamps, but not in
  `state_sha256`.

**Unchanged on the evidence GPU.** On the stored archive's own profile (lab's `cuda_sm120_mp188` for the packages) nothing
is generated. The archive restores exactly as before, with the same restore report and state hashes.

**Cost and budget.** very_easy on an RTX 4090 (ws, a loaded shared host): the preparation took 320-511 s for 6081
physics ticks; the whole Session build took 379-614 s with generation and 242 s with a cache hit. Peak VRAM was about
6 GB for our process. easy, medium and hard were not measured. Where the time is spent:
- Standard mode: the generation runs once per trial, in the sim service's startup. That is inside the agent's wall clock
  and the startup watchdog (`RCB_STARTUP_TIMEOUT_S` 1800 s). The replay then hits the cache.
- Privileged mode: the agent's first `Session` generates the state (agent time, once per container). The verifier
  generates it again in its own container (verifier time, `timeout_sec` 45000 s).

**Release impact.** `topogym/` changed, which gives a new public source hash, and so did the templates. The next release
needs a new image and regenerated packages (a new tooling version). The frozen instances (`instance.json` and the
archives) stay the same.

**Validation status (2026-10-08).** The tree was handed over before the planned validation finished.
- Run on ws, on a private image of this tree, for very_easy only. The image predates only the `state_sha256` definition
  and the `getattr` tolerance in the service and graders.
  - The generation ran: 6081 ticks with release at tick 5840, as in the lab archive; it qualified, including motion.
  - The generated state restored and ran 40 control steps (`instance_exact` 0, `instance_matches` 1,
    `instance_generated` 1).
  - Two independent generations gave the same physical state: the same `state_sha256`, every non-scratch array
    bit-identical, and the same state hash at birth and after 40 steps.
  - A cache hit in a fresh process restored the same state.
  - The generated cloth is within 13 µm of the lab state: max particle distance 12.8 µm, mean 7.4 µm. Its birth coverage
    is 0.860.
- Not run on a GPU:
  - easy, medium and hard;
  - the Harbor standard nops, with their live/replay consistency;
  - the privileged verifier;
  - the stored path with the evidence profile simulated. The stored path is covered by a unit test (the decision returns
    None and `frozen_initial_state()` returns the stored archive) and by construction.
- CI: the TopoGym tests that touch these modules pass and fail exactly as on origin/dev/jianwen (two tests fail in both
  trees for the same environmental reasons), and the new test passes.
