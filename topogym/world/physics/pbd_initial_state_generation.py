"""Generated PBD birth states: a frozen Blanket instance realized from its own recipe on this runtime's GPU.

A frozen rigid/PBD birth archive (pbd_initial_state.py, codec rigid_pbd_numeric_v2) restores only on the resource profile
it was prepared on (initial_state_compatibility.resource_profile: CUDA compute capability and SM count plus the software
stack). The GPU physics is deterministic on one GPU model, not across models, so require_compatible() refuses an archive
of another GPU: every Blanket package prepared on lab's RTX PRO 6000 (cuda_sm120_mp188) failed at start on an RTX 4090
(PR #81 nop, 2026-10-07). Decision of 2026-10-08: a frozen state that is missing or does not match the runtime is
generated on the spot from the instance's own recipe.

Env.reset() calls ensure_initial_state() after the task is constructed and before the scene is declared:
  - the stored archive applies when its resource profile equals the runtime's, or when it is a codec v1 archive (which
    names no device): nothing is generated, and it restores exactly as before (its own checks refuse it otherwise);
  - otherwise the recipe frozen in the instance runs again on this GPU: the instance's scene (the archive `identity`:
    task parameters, scene configuration, generated assets, robot assets, backend and precision), which must equal the
    stored archive's, and the preparation the stored archive records (qualification.preparation: the PreparationConfig,
    the fold profile and the acceptance scope), by the family's management-only controller (the task's
    initial_state_recipe(): the same as scripts/prepare_blanket_initial_states.py --tier). An instance that names no
    archive at all uses its family's recipe with the default PreparationConfig. The generated state passes the same
    qualification gates, is exported with the same codec and restores through the same checks as a stored one;
  - the run then restores the generated archive instead (task.generated_initial_state); the restore report carries the
    record under "generated".

Cache: <cache root>/<runtime resource profile>/<recipe sha256[:32]>/ holds state/ (manifest.json, arrays.npz),
recipe.json, qualification.json and generation.json. The cache root is $TOPOGYM_INITIAL_STATE_CACHE, else
$XDG_CACHE_HOME/topogym/initial_states (the image: /opt/rcb-cache, mode 1777), else ~/.cache/topogym/initial_states.
Every process of one run (a standard sidecar's live service, its crash-recovery restarts and the collect hook's
fresh-process replay share one container) restores the identical generated bits; a fresh container generates again, which
gives the same state on the same GPU model (deterministic GPU physics). The recipe hash covers the scene identity, the
preparation, the installed simulator source, the codec and the process's run-time physics replacements
(register_runtime_physics: the task tooling's fixed-point PBD sums and bounded PBD-rigid contact act on the preparation
too). A preparation that fails its qualification is recorded in the cache as failed (deterministic physics: a retry fails
the same way); any other error is not cached.

Identity: a generated state cannot equal the instance's evidence state (state_sha of another GPU). Its identity is the
recipe (recipe_match: the stored archive's scene identity and recorded preparation equal the ones run here) plus the
generated archive's hashes (manifest_sha256, state_sha256), which the run records so a verifier can check that the
live episode and its replays started from the same state.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np

from topogym.utils.io import canonical_hash, sha256_file, to_jsonable, write_json_atomic
from topogym.world.physics.initial_state_compatibility import CODEC, WORLD_RESTORE_SEMANTICS, resource_profile

SCHEMA = "topogym_generated_pbd_initial_state_v1"
PREPARATION_KIND = "offline_bounded_velocity_preparation"
_RUNTIME_PHYSICS: dict = {}


class InitialStateGenerationError(RuntimeError):
    """The recipe cannot be realized here (a recipe mismatch or a failed qualification)."""


def register_runtime_physics(name, record):
    """Record a process-wide physics replacement (e.g. task tooling that replaces Genesis kernels at run time). It acts on
    every scene of the process, a generated state's preparation included, so it is part of the recipe."""
    _RUNTIME_PHYSICS[str(name)] = json.loads(json.dumps(to_jsonable(record), sort_keys=True))


def runtime_physics():
    return deepcopy(_RUNTIME_PHYSICS)


def cache_root():
    explicit = os.environ.get("TOPOGYM_INITIAL_STATE_CACHE")
    if explicit:
        return Path(explicit)
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else Path.home()/".cache")/"topogym"/"initial_states"


def source_identity():
    """The simulator source that runs the preparation: an installed image's SOURCE.json (checked against the files by the
    task's runtime binding), else a hash of the package's Python files (a checkout)."""
    recorded = os.environ.get("TOPOGYM_SOURCE")
    if recorded and Path(recorded).is_file():
        return dict(json.loads(Path(recorded).read_text()), kind="installed")
    import topogym
    root = Path(topogym.__file__).resolve().parent
    files = {str(p.relative_to(root.parent)): sha256_file(p) for p in sorted(root.rglob("*.py"))
             if "__pycache__" not in p.parts}
    return dict(sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files=len(files),
                kind="checkout_python")


def _scratch(path):
    """Working memory that Genesis rebuilds before use in every substep and whose slot order follows GPU atomics, so two
    identical preparations archive it in different orders: the rigid collider's per-substep buffers (all but its static
    configuration, the contact cache that warm-starts the next search and that cache's validity flag) and the PBD
    spatial hash with the particle copies in hash order."""
    collider = "/buffers/RigidSolver/collider/"
    if path.startswith(collider):
        return not path.startswith(tuple(collider+name for name in (
            "_collider_info/", "_collider_state/contact_cache/", "_collider_state/first_time/")))
    return path.startswith("/buffers/PBDSolver/sh/") or "_reordered/" in path or path.endswith("/reordered_idx")


def state_sha256(manifest_path):
    """Hash of an archived state: its metadata, tree and every array except the scratch above (bit for bit). Two
    preparations that reach the same state give the same value although their arrays.npz differ (scratch order, zip
    timestamps); the archive a run restores is identified by its manifest_sha256."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256(json.dumps(dict(schema_version=manifest["schema_version"], metadata=manifest["metadata"],
        tree=manifest["tree"]), sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    paths = {}

    def walk(node, path):
        if node["kind"] in ("array", "tensor"):
            paths[node["key"]] = path
        elif node["kind"] == "dict":
            for key, item in node["items"].items():
                walk(item, f"{path}/{key}")
        elif node["kind"] in ("tuple", "list"):
            for index, item in enumerate(node["items"]):
                walk(item, f"{path}/{index}")
    walk(manifest["tree"], "")
    with np.load(manifest_path.parent/manifest["arrays"]["path"], allow_pickle=False) as arrays:
        for key in sorted(arrays.files, key=lambda k: paths[k]):
            if _scratch(paths[key]):
                continue
            value = np.ascontiguousarray(arrays[key])
            digest.update(json.dumps([paths[key], value.dtype.str, list(value.shape)]).encode())
            digest.update(value.tobytes())
    return digest.hexdigest()


@contextmanager
def _preserved_rng():
    """The preparation seeds and draws the process RNGs; the episode's own construction continues as if it had not run."""
    import random
    import torch
    saved = (random.getstate(), np.random.get_state(), torch.get_rng_state(),
             torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None)
    try:
        yield
    finally:
        random.setstate(saved[0])
        np.random.set_state(saved[1])
        torch.set_rng_state(saved[2])
        if saved[3] is not None:
            torch.cuda.set_rng_state_all(saved[3])


@contextmanager
def _single_threaded_blas():
    """The preparation's conjugate gradients take long dot products (3 x 8181 particles), which OpenBLAS splits across one
    thread per host core: the rounding can then depend on the host's core count, and on a loaded shared host the threaded
    dot product is orders of magnitude slower (ws, 2026-10-08: 20,000 dots of 25,000 elements took > 4 min threaded and
    0.03 s on one thread). The preparation runs with one thread in every loaded OpenBLAS (numpy's and scipy's)."""
    import ctypes
    import scipy.linalg  # noqa: F401  (loads scipy's OpenBLAS, which the projection may use)
    import scipy.sparse.linalg  # noqa: F401
    with open("/proc/self/maps") as maps:
        paths = sorted({line.split()[-1] for line in maps if "openblas" in line.rsplit("/", 1)[-1]})
    restore = []
    for path in paths:
        library = ctypes.CDLL(path)
        for suffix in ("64_", ""):
            get, set_ = (getattr(library, f"scipy_openblas_{verb}_num_threads{suffix}", None) for verb in ("get", "set"))
            if get is not None and set_ is not None:
                restore.append((set_, get()))
                set_(1)
                break
    try:
        yield
    finally:
        for set_, count in restore:
            set_(count)


@contextmanager
def _locked(path):
    import fcntl
    descriptor = os.open(path, os.O_RDONLY | os.O_CREAT, 0o644)   # read access suffices for flock (any user)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def stored_profile(metadata):
    """The resource profile of a stored archive, or None for a codec v1 archive (no device: never regenerated)."""
    backend = metadata.get("backend", {})
    return resource_profile(backend) if backend.get("codec") == CODEC else None


def ensure_initial_state(config, scene_config, task):
    """Before Env.reset declares the scene: when this frozen instance's stored archive does not apply on this runtime, realize
    its recipe here (or take the cached realization) and make the task declare that state. Returns the generation record,
    or None when the stored archive applies (nothing changes)."""
    if getattr(task, "initial_state_recipe", None) is None or task.config.get("initialization_mode") != "frozen":
        return None
    from topogym.world.initial_state import read_archive_manifest
    stored = task.stored_initial_state()
    runtime = resource_profile()
    reference = None
    if stored is not None:
        metadata = read_archive_manifest(stored.manifest_path, expected_sha256=stored.sha256)["metadata"]
        profile = stored_profile(metadata)
        if profile is None or profile == runtime:
            return None
        reference = dict(manifest_sha256=stored.sha256, resource_profile=profile, metadata=metadata)
    started = time.monotonic()
    with _preserved_rng():
        record = _realize(config, scene_config, task, runtime, reference)
    from topogym.tasks.base import InitialStateSpec
    task.generated_initial_state = InitialStateSpec(record.pop("manifest_path"), record["manifest_sha256"],
        acceptance=task.config.get("initial_state_acceptance", "released_stable"))
    record["ensure_wall_s"] = round(time.monotonic()-started, 3)
    return record


def _recipe(config, scene_config, task, reference, work):
    """Declare the preparation scene (the instance's parameters, flat birth) and assemble the recipe."""
    from topogym.assets.library import describe_build
    from topogym.world.initial_state import scene_identity
    from topogym.world.physics.cloth_preparation import PreparationConfig
    from topogym.utils.variant_rng import seed_process
    seed_process(task.seed)
    parameters = deepcopy(task.config)
    parameters.update(initialization_mode="flat_for_preparation", initial_state_path=None,
                      initial_state_resource=None, initial_state_sha256=None)
    preparation_task = type(task)(parameters, seed=task.seed)
    table = scene_config.env.world.table
    spec = preparation_task.declare(work/"assets", float(table.pos[2]+table.size[2]/2))
    build = describe_build(config.task_id, work/"assets", preparation_task.config, task.seed)
    identity = scene_identity(config, scene_config, preparation_task, spec, build)
    controller, profile, preparation = preparation_task.initial_state_recipe()
    acceptance = task.config.get("initial_state_acceptance", "released_stable")
    recipe_match = None
    if reference is not None:
        metadata = reference["metadata"]
        recorded = metadata.get("qualification", {}).get("preparation", {})
        differences = [name for name, ok in (
            ("identity", metadata.get("identity") == json.loads(json.dumps(to_jsonable(identity)))),
            ("preparation.kind", recorded.get("kind") == PREPARATION_KIND),
            # A record that predates a later profile option (corner folds' 2026-10 options) means its default value.
            ("preparation.profile", isinstance(recorded.get("profile"), dict) and _profile(profile, recorded["profile"]) == profile),
            ("preparation.parameters", isinstance(recorded.get("parameters"), dict)),
            ("includes_robot", metadata.get("includes_robot") is True),
        ) if not ok]
        if differences:
            raise InitialStateGenerationError(
                f"The stored initial state ({reference['resource_profile']}) does not record this instance's recipe "
                f"({', '.join(differences)} differ), so no faithful state can be generated for {resource_profile()}; "
                "prepare and install one with scripts/prepare_blanket_initial_states.py")
        # The frozen recipe is the one the archive records, not this source's defaults.
        preparation = PreparationConfig(**recorded["parameters"])
        acceptance = metadata["qualification"].get("scope", acceptance)
        recipe_match = True
    recipe = json.loads(json.dumps(to_jsonable(dict(
        schema=SCHEMA, codec=CODEC, world_restore_semantics=WORLD_RESTORE_SEMANTICS,
        task_id=config.task_id, variation_id=preparation_task.variation_id, seed=task.seed,
        identity_sha256=canonical_hash(to_jsonable(identity)),
        preparation=dict(kind=PREPARATION_KIND, controller=f"{controller.__module__}.{controller.__qualname__}",
                         parameters=asdict(preparation), profile=asdict(profile), acceptance=acceptance),
        source=source_identity(), runtime_physics=runtime_physics()))))
    return recipe, recipe_match, dict(task=preparation_task, spec=spec, identity=identity, controller=controller,
                                      profile=profile, preparation=preparation, acceptance=acceptance)


def _profile(profile, recorded):
    try:
        return type(profile)(**recorded)
    except TypeError:
        return None


def _realize(config, scene_config, task, runtime, reference):
    root = cache_root()/runtime
    for folder in (root.parent, root):
        if not folder.is_dir():
            # One cache for every user of the image (agents and verifiers run as root, some sidecars as the caller's UID)
            folder.mkdir(parents=True, exist_ok=True)
            try:
                folder.chmod(0o1777)
            except OSError:
                pass
    work = Path(tempfile.mkdtemp(prefix=".work-", dir=root))
    try:
        recipe, recipe_match, scene = _recipe(config, scene_config, task, reference, work)
        key = canonical_hash(recipe)
        entry = root/key[:32]
        with _locked(root/f"{key[:32]}.lock"):
            record = _cached(entry, recipe)
            cache = "hit"
            if record is None:
                with _single_threaded_blas():
                    record = _generate(config, scene_config, scene, recipe, key, runtime, reference, root, entry)
                cache = "miss"
        if record.get("status") != "passed":
            raise InitialStateGenerationError(f"Generated initial state for {runtime} failed its qualification "
                                              f"(cached in {entry}): {record.get('error')}")
        return dict(record, cache=cache, recipe_match=recipe_match, manifest_path=str(entry/"state"/"manifest.json"),
                    entry=str(entry))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _cached(entry, recipe):
    """The entry's record, or None when there is none. Entries are committed whole (a rename), so one that differs from
    its own record is refused rather than silently replaced: the processes of one run must restore the same bits."""
    if not entry.exists():
        return None
    record = json.loads((entry/"generation.json").read_text())
    if (json.loads((entry/"recipe.json").read_text()) != recipe or record.get("recipe_sha256") != canonical_hash(recipe)
            or (record.get("status") == "passed"
                and sha256_file(entry/"state"/"manifest.json") != record["manifest_sha256"])):
        raise InitialStateGenerationError(f"Generated initial-state cache entry {entry} differs from its record; "
                                          "delete it to generate the state again")
    return record


def _generate(config, scene_config, scene, recipe, key, runtime, reference, root, entry):
    """scripts/prepare_blanket_initial_states.py's tiered preparation (world, robot at home, controller, export), without
    its diagnostics, logs and video; the scene's cameras are not built (identity and physics do not depend on them)."""
    import torch
    from topogym.robot import make_robot
    from topogym.world.genesis_world import GenesisWorld
    from topogym.world.physics.pbd_initial_state import export_initial_state
    staging = Path(tempfile.mkdtemp(prefix=f".{key[:32]}.", dir=root))
    task, spec = scene["task"], scene["spec"]
    record = dict(schema=SCHEMA, recipe_sha256=key, resource_profile=runtime,
                  gpu=torch.cuda.get_device_name(torch.cuda.current_device()) if torch.cuda.is_available() else None,
                  stored_profile=None if reference is None else reference["resource_profile"],
                  stored_manifest_sha256=None if reference is None else reference["manifest_sha256"],
                  created_unix_s=round(time.time(), 3))
    world = None
    started = time.monotonic()
    try:
        # from_tabletop seeds the process RNGs with the scene seed, as for the script's world
        world = GenesisWorld.from_tabletop(scene_config.env, scene_config.robot_control,
            physics_options=spec.physics_options, compute_backend=config.compute_backend,
            precision=config.precision, seed=task.seed, cameras=False)
        world.diagnostics_dir = staging/"physics_diagnostics"
        world.add_entities(spec.entities)
        world.build()
        robot = make_robot(world.entities["robot"], scene_config.robot_control)
        robot.reset_home()
        task.bind(world.entities)
        table = scene_config.env.world.table
        table_xy, half = np.asarray(table.pos[:2]), np.asarray(table.size[:2])/2
        controller = scene["controller"](world, task, scene["profile"], table_bounds=(table_xy-half, table_xy+half),
                                         config=scene["preparation"])
        try:
            controller.run(acceptance=scene["acceptance"])
        except (RuntimeError, FloatingPointError) as error:
            # The preparation's own guards and settling budget: deterministic on this GPU model, so recorded.
            record.update(status="failed", error=f"{type(error).__name__}: {error}", preparation=controller.report,
                          preparation_wall_s=round(time.monotonic()-started, 3), physics_ticks=int(world.physics_step))
            return _commit(staging, entry, recipe, record)
        write_json_atomic(staging/"qualification.json", controller.report, mode=0o644)
        qualified = controller.report["completed"]
        manifest = export_initial_state(world, staging/"state", identity=scene["identity"], robot=robot,
            qualification=dict(passed=qualified, scope=scene["acceptance"],
                scene_layout_passed=qualified or controller.report.get("scene_layout_completed", False),
                report_sha256=sha256_file(staging/"qualification.json"),
                preparation=controller.report, binding=task.binding_report))
        record.update(status="passed", manifest_sha256=sha256_file(manifest), state_sha256=state_sha256(manifest),
                      preparation_wall_s=round(time.monotonic()-started, 3), physics_ticks=int(world.physics_step),
                      motion_qualified=bool(qualified))
        return _commit(staging, entry, recipe, record)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if world is not None:
            world.close()


def _commit(staging, entry, recipe, record):
    write_json_atomic(staging/"recipe.json", recipe, mode=0o644)
    write_json_atomic(staging/"generation.json", record, mode=0o644)
    shutil.rmtree(staging/"physics_diagnostics", ignore_errors=True)
    os.chmod(staging, 0o755)
    staging.rename(entry)
    return record
