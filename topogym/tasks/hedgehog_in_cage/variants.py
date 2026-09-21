"""Fixed puzzle families + named seed streams -> portable, checked instances.

Sampling and materialization never execute physics, render, or write a dataset.
The returned EpisodeSpec is the input contract for later task/data runners.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.generation import EpisodeKey, EpisodeSpec, ExecutionProfile, ScenePreset, TaskLayout, TaskVariant
from topogym.generation.variant_episode import build_variant_episode
from topogym.generation.variant_rng import VARIANT_RNG_VERSION, VariantRng

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "assets/tasks/hedgehog_in_cage/seed_families_v1"
NEW_ASSETS = ROOT / "assets/tasks/hedgehog_in_cage/seed_families_v2"
RULES = ROOT / "configs/task_variants/hedgehog_in_cage/generator_v2.yaml"
VERSION = "hedgehog_seed_v2"
LEGACY_VERSION = "hedgehog_seed_v1"
LEGACY_FAMILIES = ("oblique_gate", "staggered_gates", "helical_guide")
FAMILIES = ("oblique_gate", "fixed_side_window", "gen_keyhole")
INSTRUCTION = "Extract the hedgehog through the cage opening, place it on the table, release and retreat."


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def inside(folder, relative):
    path = (folder / relative).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError(f"Artifact path escapes instance: {relative}")
    return path


@lru_cache(maxsize=64)
def _json_content(path, digest):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Prototype changed: {path}")
    return json.loads(data)


def prototype(family, *, verify_assets=False):
    if family not in set(FAMILIES) | set(LEGACY_FAMILIES):
        raise ValueError("Unknown fixed family")
    library = ASSETS if family in LEGACY_FAMILIES else NEW_ASSETS
    catalog = json.loads((library / "catalog.json").read_text())
    row = next(r for r in catalog["families"] if r["family_id"] == family)
    folder = inside(library, row["directory"])
    if file_sha(folder / "prototype_manifest.json") != row["manifest_sha256"]:
        raise ValueError("Fixed prototype manifest checksum mismatch")
    manifest = _json_content(str(folder / "prototype_manifest.json"), row["manifest_sha256"])
    keys = manifest["files_sha256"] if verify_assets else ("prototype.json", "scene_config.json", "grasp.json")
    for key in keys:
        if file_sha(inside(folder, key)) != manifest["files_sha256"][key]:
            raise ValueError(f"Fixed prototype checksum mismatch: {family}/{key}")
    data = deepcopy(_json_content(str(folder / "prototype.json"), manifest["files_sha256"]["prototype.json"]))
    data["manifest_sha256"] = row["manifest_sha256"]
    return folder, data, manifest


def rules(version=VERSION):
    if version not in (VERSION, LEGACY_VERSION):
        raise ValueError("Unsupported generator version")
    path = RULES if version == VERSION else RULES.with_name("generator_v1.yaml")
    return OmegaConf.to_container(OmegaConf.load(path), resolve=True)


def generator_version(task):
    return str(task.get("variant_generator_version", LEGACY_VERSION))


def families_for_version(version):
    if version not in (VERSION, LEGACY_VERSION):
        raise ValueError("Unsupported generator version")
    return FAMILIES if version == VERSION else LEGACY_FAMILIES


def derive(task):
    p = task["randomization"]
    _, core, _ = prototype(str(p["family_id"]))
    policy = rules(generator_version(task))["geometry_policy"]
    budget = min(float(policy["maximum_vertex_displacement_m"]),
                 core["parent_path_clearance_lower_bound_m"] * float(policy["clearance_budget_fraction"]))
    # Independent fractions share a bounded Euclidean vertex-displacement budget.
    radial = float(1 + float(p["radius_fraction"]) * budget / (np.sqrt(2) * core["maximum_cage_radius_m"]))
    height = float(1 + float(p["height_fraction"]) * budget / (np.sqrt(2) * core["cage_height_m"]))
    task["center_xy_m"] = [.06 + float(p["center_dx_m"]), .2 + float(p["center_dy_m"])]
    task["yaw_deg"] = -130. + float(p["yaw_delta_deg"])
    task["mount_yaw_delta_deg"] = float(p["yaw_delta_deg"])
    task["variant"] = core["prototype_id"]
    task["finish"] = "wood"
    task["derived_variant"] = dict(family_id=str(p["family_id"]), prototype_id=core["prototype_id"],
        prototype_manifest_sha256=core["manifest_sha256"], cage_radial_scale=radial, cage_height_scale=height,
        cage_scale_origin_m=[0., 0., core["cage_bottom_m"]], maximum_design_displacement_m=budget,
        parent_path_clearance_lower_bound_m=core["parent_path_clearance_lower_bound_m"],
        family_motion_frozen=True, ball_geometry_frozen=True, grasp_geometry_frozen=True)


def validate_parameters(task):
    p = task["randomization"]
    ranges = dict(radius_fraction=(-1, 1), height_fraction=(-1, 1),
        center_dx_m=(-.004, .004), center_dy_m=(-.004, .004), yaw_delta_deg=(-2, 2),
        cage_wood_tint=(.9, 1), ball_wood_tint=(.94, 1), wood_roughness_delta=(-.05, .05))
    if str(p["family_id"]) not in families_for_version(generator_version(task)) or set(p) != set(ranges) | {"family_id"}:
        raise ValueError("Unknown family or randomization axis")
    for name, (low, high) in ranges.items():
        value = float(p[name])
        if not np.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} outside the versioned sampling domain")
    if float(task["scale"]) != 3 or task["finish"] != "wood":
        raise ValueError("The fixed prototype pool uses the 3x wooden scene")


def choose_family(seed, family=None):
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if family is not None:
        if family not in FAMILIES:
            raise ValueError("Unknown family")
        return family
    return str(VariantRng(int(seed)).stream("hedgehog_in_cage/randomization.family_id").choice(FAMILIES))


def configuration(cfg):
    value = OmegaConf.to_container(cfg, resolve=True) if OmegaConf.is_config(cfg) else deepcopy(cfg)
    value.pop("hydra", None)
    value["task"].pop("variation", None)
    value["task"].pop("seed", None)
    value["run"]["output"] = "."
    return value


def identity(cfg):
    return fingerprint(dict(generator_version=generator_version(cfg.task), rng_version=VARIANT_RNG_VERSION,
                            configuration=configuration(cfg)))


def sample(seed, *, family=None, mode="parameterized", attempt=0, overrides=None, declarations=None):
    """Return (cfg, EpisodeSpec); fixed mode only selects an existing prototype.

    All retries retain the seed's selected family. Output path, batch order and
    execution timing never participate in random draws or instance identity.
    """
    family = choose_family(seed, family)
    if mode not in ("fixed", "parameterized"):
        raise ValueError("mode must be fixed or parameterized")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be a nonnegative integer")
    folder, core, manifest = prototype(family)
    base = deepcopy(_json_content(str(folder / "scene_config.json"), manifest["files_sha256"]["scene_config.json"]))
    definition = rules()
    base["task"].update(variant_generator_version=VERSION, randomization=deepcopy(definition["randomization"]),
                        variation=deepcopy(declarations if declarations is not None else definition["variation"]),
                        goal=dict(instruction=INSTRUCTION))
    p = base["task"]["randomization"]
    p["family_id"] = family
    overrides = dict(overrides or {})
    if set(overrides) - (set(p) - {"family_id"}):
        raise ValueError("Overrides may only set declared continuous axes")
    if mode == "fixed" and overrides:
        raise ValueError("Fixed mode cannot alter a prototype")
    requested = deepcopy(p)
    requested.update(overrides)
    validate_parameters(dict(base["task"], randomization=requested, finish="wood"))
    for directive in base["task"]["variation"]:
        path = directive.get("path", "")
        if not path.startswith("randomization."):
            continue
        name = path.split(".", 1)[1]
        if name == "family_id" or mode == "fixed" or name in overrides:
            directive.clear()
            directive.update(kind="choice", path=path, values=[overrides.get(name, p[name])])
    draw_seed = int(seed) if attempt == 0 else int(VariantRng(int(seed)).stream(
        "hedgehog_in_cage/parameter_attempt", retry=attempt).integers(0, 2**63))
    cfg, spec = build_variant_episode(OmegaConf.create(base), "hedgehog_in_cage", draw_seed,
                                      variant_id=VERSION, difficulty="unclassified")
    cfg.task.seed = int(seed)
    cfg.run.output = "."
    cfg.run.viewer = False
    cfg.run.record_video = False
    cfg.run.save_stills = False
    digest = identity(cfg)
    key = replace(spec.key, seed=int(seed), variant_id=f"{VERSION}_{digest[:20]}", preset_id=str(cfg.env.preset.id))
    origin = np.r_[cfg.task.center_xy_m, float(cfg.env.frames.table_surface.origin[2]) + .22]
    rotation = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    ball_pose = np.asarray(core["initial_ball_pose"])
    parameters = dict(OmegaConf.to_container(cfg.task.randomization, resolve=True),
        mode=mode, attempt=attempt, draw_seed=draw_seed, generator_version=VERSION,
        variant_rng_version=VARIANT_RNG_VERSION, instance_sha256=digest,
        geometry_sha256=fingerprint(dict(prototype=core["manifest_sha256"],
            radial_scale=cfg.task.derived_variant.cage_radial_scale, height_scale=cfg.task.derived_variant.cage_height_scale)))
    status = dict(sampling="passed", geometry="not_run", robot_ik="not_run", robot_clearance="not_run",
                  scene_load="not_run", physical_execution="not_run", export_ready=False)
    spec = replace(spec, key=key, preset=replace(spec.preset, preset_id=key.preset_id),
        variant=replace(spec.variant, key=key, parameters=parameters,
                        notes="Fixed mechanism family with optional conditional dimension, placement and wood finish sampling."),
        layout=TaskLayout("hedgehog_in_cage", layout_id=digest[:20], frame="world",
            objects=dict(cage=dict(position_m=origin.tolist(), quaternion_xyzw=rotation.as_quat().tolist()),
                         hedgehog=dict(position_m=(origin + rotation.apply(ball_pose[:3])).tolist(),
                            quaternion_xyzw=(rotation * Rotation.from_quat(ball_pose[3:])).as_quat().tolist())),
            metadata=dict(fixed_cage=True, pregrasp_start=True, grasp_spike="S2")),
        execution_profile=ExecutionProfile(profile_id="hedgehog_guided_contact_assisted_release_v1",
            parameters=dict(pregrasp_start=True, contact_triggered_assistance=True, release_and_retreat=True,
                            robot_geometry_scale=1., physical_qualification_required=True)),
        resolved_config=dict(configuration=configuration(cfg), instance_sha256=digest, validation=status,
            dependencies={name: version(name) for name in ("numpy", "scipy", "trimesh", "omegaconf")}))
    return cfg, spec


def _validate_spec(spec):
    cfg = OmegaConf.create(spec.resolved_config["configuration"])
    if spec.task_id != "hedgehog_in_cage" or spec.key != spec.variant.key or identity(cfg) != spec.resolved_config["instance_sha256"]:
        raise ValueError("EpisodeSpec identity mismatch")
    version_id = generator_version(cfg.task)
    if spec.variant.parameters["generator_version"] != version_id:
        raise ValueError("Episode generator version mismatch")
    if spec.key.variant_id != f"{version_id}_{identity(cfg)[:20]}" or spec.variant.parameters["instance_sha256"] != identity(cfg):
        raise ValueError("Episode key does not describe this configuration")
    validate_parameters(cfg.task)
    # Do not permit a stored derived field to diverge from the sampled leaves.
    expected = deepcopy(OmegaConf.to_container(cfg.task, resolve=True))
    derive(expected)
    for name in ("center_xy_m", "yaw_deg", "mount_yaw_delta_deg", "derived_variant", "variant", "finish"):
        if expected[name] != OmegaConf.to_container(cfg.task, resolve=True)[name]:
            raise ValueError(f"Inconsistent derived parameter: {name}")
    for name, value in cfg.task.randomization.items():
        if spec.variant.parameters.get(name) != value:
            raise ValueError(f"Episode parameters differ from config: {name}")
    if spec.variant.instruction != INSTRUCTION or spec.preset.preset_id != spec.key.preset_id:
        raise ValueError("Episode goal/preset mismatch")
    _, core, _ = prototype(str(cfg.task.randomization.family_id))
    origin = np.r_[cfg.task.center_xy_m, float(cfg.env.frames.table_surface.origin[2]) + .22]
    rotation = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    pose = np.array(core["initial_ball_pose"])
    expected_objects = dict(cage=dict(position_m=origin.tolist(), quaternion_xyzw=rotation.as_quat().tolist()),
        hedgehog=dict(position_m=(origin+rotation.apply(pose[:3])).tolist(),
                      quaternion_xyzw=(rotation*Rotation.from_quat(pose[3:])).as_quat().tolist()))
    if spec.layout is None or spec.layout.frame != "world" or spec.layout.objects != expected_objects:
        raise ValueError("Episode layout differs from sampled placement")
    if spec.resolved_config["validation"]["export_ready"] or spec.resolved_config["validation"]["physical_execution"] != "not_run":
        raise ValueError("Generator instances cannot inherit physical/export qualification")
    return cfg


def materialize(spec, output):
    """Materialize exactly this spec without sampling, simulation, video or H5."""
    cfg = _validate_spec(spec)
    output = Path(output).resolve()
    if output.is_relative_to(ROOT / "demos"):
        raise ValueError("Instance bundles belong under runs/, not demos/")
    if output.exists():
        raise ValueError("Preserve existing instance output")
    output.mkdir(parents=True)
    # Preserve the exact unqualified request even when preflight rejects it.
    save(output / "episode_spec.json", asdict(spec))
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    from .variant_validation import build_assets, qualify
    geometry = build_assets(cfg, output)
    save(output / "geometry_report.json", geometry)
    qualification, motion = qualify(cfg, output, geometry)
    save(output / "robot_motion.json", motion)
    save(output / "qualification.json", qualification)
    cfg.task.seed = spec.seed
    cfg.run.output = str(output)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    status = dict(spec.resolved_config["validation"], geometry="passed", robot_ik="passed", robot_clearance="passed")
    spec = replace(spec, resolved_config=dict(spec.resolved_config, validation=status))
    save(output / "episode_spec.json", asdict(spec))
    sources = ("variants.py", "variant_validation.py", "variant_runtime.py", "geometry.py", "appearance.py",
               "inverse_window.py", "family_runtime.py", "family_geometry.py", "plan_escape.py", "side_window_probe.py")
    provenance = output / "generator_source"
    provenance.mkdir()
    for name in sources:
        shutil.copy2(Path(__file__).with_name(name), provenance / name)
    rule_path = RULES if generator_version(cfg.task) == VERSION else RULES.with_name("generator_v1.yaml")
    shutil.copy2(rule_path, provenance / rule_path.name)
    for name in ("variant_rng.py", "variant_episode.py", "layout_randomization.py", "episode_spec.py"):
        shutil.copy2(ROOT / "topogym/generation" / name, provenance / name)
    files = {str(p.relative_to(output)): file_sha(p) for p in sorted(output.rglob("*")) if p.is_file()}
    save(output / "instance_manifest.json", dict(schema_version=1, task_id=spec.task_id,
         episode_id=spec.stable_id(), instance_sha256=identity(cfg), validation=status, files_sha256=files,
         dataset_generated=False, h5_generated=False))
    return cfg, spec


def _spec_from_dict(data):
    key = EpisodeKey(**data["key"])
    variant = dict(data["variant"])
    if variant.pop("key") != data["key"]:
        raise ValueError("Saved variant identity mismatch")
    return EpisodeSpec(key=key, preset=ScenePreset(**data["preset"]), variant=TaskVariant(key=key, **variant),
        layout=TaskLayout(**data["layout"]) if data["layout"] else None,
        execution_profile=ExecutionProfile(**data["execution_profile"]), resolved_config=data["resolved_config"])


def load_instance(folder):
    """Verify and reload the saved instance. Relocation never triggers sampling."""
    folder = Path(folder).resolve()
    if (folder / "result.json").exists():
        result = json.loads((folder / "result.json").read_text())
        if not result["accepted"]:
            raise ValueError("Rejected generation result")
        folder = inside(folder, result["candidate_directory"])
    manifest = json.loads((folder / "instance_manifest.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("task_id") != "hedgehog_in_cage":
        raise ValueError("Unsupported instance manifest")
    required = {"episode_spec.json", "config.yaml", "robot_motion.json", "qualification.json", "geometry_report.json"}
    if not required <= manifest["files_sha256"].keys():
        raise ValueError("Incomplete instance manifest")
    for relative, digest in manifest["files_sha256"].items():
        path = inside(folder, relative)
        if not path.is_file() or file_sha(path) != digest:
            raise ValueError(f"Instance file changed or missing: {relative}")
    spec = _spec_from_dict(json.loads((folder / "episode_spec.json").read_text()))
    cfg = _validate_spec(spec)
    saved = OmegaConf.load(folder / "config.yaml")
    if configuration(saved) != configuration(cfg):
        raise ValueError("Saved config differs from EpisodeSpec")
    if manifest["episode_id"] != spec.stable_id() or manifest["instance_sha256"] != identity(cfg):
        raise ValueError("Manifest identity mismatch")
    if manifest["validation"] != spec.resolved_config["validation"]:
        raise ValueError("Manifest qualification mismatch")
    qualification = json.loads((folder / "qualification.json").read_text())
    if not qualification["passed"] or qualification["instance_sha256"] != identity(cfg):
        raise ValueError("Unqualified instance")
    cfg.task.seed = spec.seed
    cfg.run.output = str(folder)
    return cfg, spec


class GenerationRejected(ValueError):
    def __init__(self, attempts):
        self.attempts = attempts
        super().__init__(f"No qualified candidate after {len(attempts)} attempts")


def generate(seed, output, *, family=None, mode="parameterized", max_attempts=3):
    family = choose_family(seed, family)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 20:
        raise ValueError("max_attempts must be an integer in [1, 20]")
    # Validate the request before creating a directory or entering rejection sampling.
    sample(seed, family=family, mode=mode)
    output = Path(output).resolve()
    if output.is_relative_to(ROOT / "demos"):
        raise ValueError("Instance bundles belong under runs/, not demos/")
    output.mkdir(parents=True, exist_ok=False)
    attempts = []
    for attempt in range(1 if mode == "fixed" else max_attempts):
        _, spec = sample(seed, family=family, mode=mode, attempt=attempt)
        destination = output / f"attempt_{attempt:03d}"
        try:
            _, accepted = materialize(spec, destination)
        except ValueError as error:
            attempts.append(dict(attempt=attempt, accepted=False, family=family, reason=str(error),
                                 instance_sha256=spec.resolved_config["instance_sha256"]))
            destination.mkdir(exist_ok=True)
            save(destination / "rejection.json", attempts[-1])
            continue
        attempts.append(dict(attempt=attempt, accepted=True, family=family,
                             instance_sha256=accepted.resolved_config["instance_sha256"]))
        result = dict(accepted=True, seed=int(seed), family=family, mode=mode,
            candidate_directory=destination.name, episode_id=accepted.stable_id(), attempts=attempts,
            validation=accepted.resolved_config["validation"], dataset_generated=False, h5_generated=False)
        save(output / "result.json", result)
        return result
    save(output / "result.json", dict(accepted=False, seed=int(seed), family=family, attempts=attempts,
                                     dataset_generated=False, h5_generated=False))
    raise GenerationRejected(attempts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--mode", choices=("fixed", "parameterized"), default="parameterized")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(generate(args.seed, args.output, family=args.family, mode=args.mode,
                              max_attempts=args.max_attempts), ensure_ascii=False, indent=2))
