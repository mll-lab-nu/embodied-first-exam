"""Seeded Keyhole instances for EpisodeSpec consumers, with no dataset writer.

Family and silhouette are fixed design choices. Micro-parameters use the shared
named RNG; rejection never silently substitutes a different family or style.
Sampling is cheap. Materialization rechecks actual solids and the retargeted
robot motion; a separate runner must establish physical success.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from threading import RLock

import numpy as np
from omegaconf import OmegaConf

from topogym.generation.episode_spec import ExecutionProfile, TaskLayout
from topogym.generation.variant_episode import build_variant_episode
from topogym.generation.variant_rng import VARIANT_RNG_VERSION, VariantRng

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "assets/tasks/cast_keyhole/seed_families_v2"
VERSION = "cast_keyhole_seed_v2"
FAMILIES = ("F1", "F2", "F3")
STYLES = ("A", "B", "C")
RANGES = dict(width_scale=(.98, 1.02), height_scale=(.98, 1.02),
              lateral_shift_mm=(-.3, .3), center_dx_m=(-.002, .002),
              center_dy_m=(-.002, .002), yaw_deg=(-1., 1.))
DEFAULTS = dict(width_scale=1., height_scale=1., lateral_shift_mm=0.,
                palette=0, center_dx_m=0., center_dy_m=0., yaw_deg=0.)
_CONFIG_LOCK = RLock()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


@lru_cache(maxsize=1)
def _base_config():
    from hydra import compose, initialize_config_dir
    with _CONFIG_LOCK, initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
        return OmegaConf.to_container(compose(config_name="cast_keyhole_variants"), resolve=True)


def catalog(*, verify=False):
    data = json.loads((ASSETS / "catalog.json").read_text())
    if data["version"] != VERSION or set(data["families"]) != set(FAMILIES):
        raise ValueError("Unknown or incomplete fixed mechanism catalog")
    if verify:
        for relative, expected in data["files"].items():
            path = (ASSETS / relative).resolve()
            if ASSETS.resolve() not in path.parents or file_sha(path) != expected:
                raise ValueError(f"Fixed catalog input changed: {relative}")
    return data


def validate_parameters(task):
    p = task["randomization"]
    if set(p) != {*DEFAULTS, "family", "style"}:
        raise ValueError("Unknown or missing variant axis")
    if p["family"] not in FAMILIES or p["style"] not in STYLES:
        raise ValueError("Unknown fixed family or silhouette")
    for key, (lo, hi) in RANGES.items():
        v = p[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{key} outside the versioned parameter domain")
    if isinstance(p["palette"], bool) or not isinstance(p["palette"], int) or p["palette"] not in (0, 1, 2):
        raise ValueError("Unknown material palette")


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def implementation():
    names = ("variants.py", "variant_pose.py", "variant_runner.py", "family_variants.py",
             "robot_motion.py", "robot_execution.py", "physical_audit.py", "variant_assets.py")
    return {n: file_sha(Path(__file__).with_name(n)) for n in names}


def sample(seed, *, family=None, style=None, mode="parameterized", attempt=0, overrides=None):
    """Return (cfg, EpisodeSpec), invariant to batching, ordering and workers.

    ``fixed`` randomly selects a predefined family/style, with no geometry or
    pose jitter. ``parameterized`` adds independent bounded micro-parameters.
    Overrides support explicit stratification and boundary qualification.
    """
    seed, attempt = _integer(seed, "seed"), _integer(attempt, "attempt")
    if mode not in ("fixed", "parameterized"):
        raise ValueError("Unknown generation mode")
    if family is not None and family not in FAMILIES or style is not None and style not in STYLES:
        raise ValueError("Unknown fixed family or style")
    overrides = dict(overrides or {})
    if set(overrides) - set(DEFAULTS) or mode == "fixed" and overrides:
        raise ValueError("Only parameterized micro-axes support overrides")
    # Validate raw inputs before OmegaConf / choice sampling can coerce types
    # (notably True to integer 1).
    validate_parameters({"randomization": dict(DEFAULTS, family=family or "F1", style=style or "A", **overrides)})
    cfg = OmegaConf.create(deepcopy(_base_config()))
    OmegaConf.set_struct(cfg, False)
    rng = VariantRng(seed)
    for directive in cfg.task.variation:
        if directive.kind not in ("choice", "uniform"):
            continue
        key, path = directive.path.split(".")[-1], directive.path
        pinned = family if key == "family" else style if key == "style" else None
        if key in DEFAULTS:
            if mode == "fixed":
                pinned = DEFAULTS[key]
            elif key in overrides:
                pinned = overrides[key]
            elif attempt:
                stream = rng.stream("cast_keyhole/" + path, retry=attempt)
                pinned = (float(stream.uniform(directive.lo, directive.hi)) if directive.kind == "uniform"
                          else int(stream.choice(list(directive["values"]))))
        if pinned is not None:
            directive.clear()
            directive.update(dict(kind="choice", path=path, values=[pinned]))
    cfg, spec = build_variant_episode(cfg, "cast_keyhole", seed, variant_id=VERSION)
    selected = OmegaConf.to_container(cfg.task.randomization, resolve=True)
    pool = catalog()
    row = pool["families"][selected["family"]]
    provenance = dict(generator_version=VERSION, rng_version=VARIANT_RNG_VERSION,
        seed=seed, attempt=attempt, mode=mode, selected=selected, catalog_sha256=digest(pool),
        implementation=implementation(), core=row,
        runtime_sha256=digest({k: _base_config()[k] for k in ("env", "robot_control")}))
    identity = digest(provenance)
    key = replace(spec.key, variant_id=identity[:24], preset_id=str(cfg.env.preset.id))
    cfg.task.variant = key.variant_id
    cfg.task.seed = seed
    spec = replace(spec, key=key, preset=replace(spec.preset, preset_id=key.preset_id),
        variant=replace(spec.variant, key=key, parameters=provenance,
            notes="Fixed solved family and silhouette; candidates require geometry, robot and physics checks."),
        execution_profile=ExecutionProfile(profile_id="keyhole_contact_assisted_dual_arm_v2",
            safety_profile="two_timesteps_independent_collision_audit", parameters=dict(
                pregrasp_start=True, assisted_weld_grasp=True, held_at_end=True,
                friction_only_grasp_verified=False, physical_execution="not_run")),
        resolved_config=OmegaConf.to_container(cfg, resolve=True))
    return cfg, spec


def check_spec(spec):
    """Refuse stale/tampered resolved choices instead of quietly resampling."""
    p = spec.variant.parameters
    if spec.task_id != "cast_keyhole" or p["seed"] != spec.seed or p["generator_version"] != VERSION:
        raise ValueError("Wrong episode identity")
    if spec.key.variant_id != digest(p)[:24] or spec.variant.key != spec.key:
        raise ValueError("Episode identity does not bind its parameters")
    if p["catalog_sha256"] != digest(catalog(verify=True)) or p["implementation"] != implementation():
        raise ValueError("Stale catalog or generator implementation")
    cfg = spec.resolved_config
    if cfg["task"]["randomization"] != p["selected"]:
        raise ValueError("Resolved config differs from the seeded instance")
    validate_parameters(cfg["task"])
    if (digest({k: cfg[k] for k in ("env", "robot_control")}) != p["runtime_sha256"]
            or p["runtime_sha256"] != digest({k: _base_config()[k] for k in ("env", "robot_control")})):
        raise ValueError("Runner does not support modified robot/physics configuration")


def _new_output(output):
    output = Path(output).resolve()
    for root in (ROOT / "demos", ROOT / "runs/demos", ASSETS):
        if output == root or root in output.parents:
            raise ValueError("Generated metadata requires its own runs directory")
    output.mkdir(parents=True, exist_ok=False)
    return output


def prepare(spec, output):
    """Materialize one already drawn spec. Geometry success is NOT physics success."""
    check_spec(spec)
    output = _new_output(output)
    save(output / "requested_episode.json", asdict(spec))
    from .family_variants import build, qualify_geometry
    from .variant_pose import retarget
    selected = spec.variant.parameters["selected"]
    family = selected["family"]
    source = ASSETS / spec.variant.parameters["core"]["directory"]
    folder = build(family + "_" + selected["style"], root=output, instance_id="instance",
        seed=spec.seed, source_override=source,
        parameters_override={k: selected[k] for k in ("width_scale", "height_scale", "lateral_shift_mm", "palette")})
    retarget(folder, selected, spec.resolved_config["robot_control"])
    qualify_geometry(folder, baseline_seed_path=ASSETS / "baseline_robot_motion.json")
    initial = json.loads((folder / "robot_motion.json").read_text())["frames"][0]
    layout = TaskLayout("cast_keyhole", layout_id=spec.key.variant_id, frame="robot_mount",
        objects=initial["bodies"], metadata=dict(
            geometry_path=str(folder / "geometry.json"), motion_path=str(folder / "robot_motion.json"),
            geometry_sha256=file_sha(folder / "geometry.json"), motion_sha256=file_sha(folder / "robot_motion.json"),
            certificate_sha256=file_sha(folder / "certificate.json"),
            validation=dict(geometry="passed", robot_ik="passed", physical_execution="not_run")))
    prepared = replace(spec, layout=layout)
    save(output / "episode_spec.json", asdict(prepared))
    save(output / "generation_status.json", dict(passed=True, status="geometry_robot_verified_physics_pending",
        instance_id=spec.key.variant_id, physical_execution="not_run", export_ready=False))
    return prepared, folder


def generate(seed, output, *, family=None, style=None, mode="parameterized", max_attempts=3, overrides=None):
    """Bounded rejection with a report for every draw, including rejected seeds."""
    max_attempts = _integer(max_attempts, "max_attempts")
    if not max_attempts:
        raise ValueError("At least one attempt is required")
    # Validate input before creating any directories.
    sample(seed, family=family, style=style, mode=mode, overrides=overrides)
    output = _new_output(output)
    attempts = []
    for attempt in range(1 if mode == "fixed" or overrides else max_attempts):
        _, spec = sample(seed, family=family, style=style, mode=mode, attempt=attempt, overrides=overrides)
        try:
            prepared, folder = prepare(spec, output / f"attempt_{attempt:02d}")
        except ValueError as error:
            attempts.append(dict(attempt=attempt, accepted=False, instance_id=spec.key.variant_id, reason=str(error)))
            save(output / "attempts.json", dict(passed=False, attempts=attempts))
            continue
        attempts.append(dict(attempt=attempt, accepted=True, instance_id=spec.key.variant_id))
        save(output / "attempts.json", dict(passed=True, accepted_directory=str(folder), attempts=attempts,
            physical_execution="not_run", export_ready=False))
        return prepared, folder
    raise ValueError(f"No accepted candidate after {len(attempts)} attempts; see {output / 'attempts.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sample", "generate"))
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--style", choices=STYLES)
    parser.add_argument("--mode", choices=("fixed", "parameterized"), default="parameterized")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    kw = dict(family=args.family, style=args.style, mode=args.mode)
    if args.command == "sample":
        _, spec = sample(args.seed, **kw)
        print(json.dumps(asdict(spec), indent=2))
    else:
        if args.output is None:
            parser.error("generate requires --output")
        spec, folder = generate(args.seed, args.output, **kw)
        print(json.dumps(dict(instance_id=spec.key.variant_id, folder=str(folder), physical_execution="not_run")))


if __name__ == "__main__":
    main()
