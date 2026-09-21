"""Seeded Claw instance proposals and materialization, without dataset recording.

Fixed prototypes and within-prototype parameters are separate. The registry
honestly includes the two unbuilt designs: selecting one produces an explicit
failure, never a fallback to A0. Only render changes can use the existing runtime;
similarity proposals export geometry/pose targets and require new robot IK.
None of the current families passes the dataset release gates.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from functools import lru_cache
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path

from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.utils import create_config_search_path
from hydra.types import RunMode
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.generation.variant_episode import build_variant_episode
from topogym.generation.variant_rng import VariantRng, VARIANT_RNG_VERSION
from .reference import ROOT

VERSION = "claw_seed_v1"
CATALOG = ROOT / "assets/tasks/interlocked_claws/seed_families_v1/catalog.json"
FAMILIES = ("claw_weave", "helical_crown", "orthogonal_gate")
MODES = ("fixed", "similarity_candidate")
PALETTES = {
    "copper_blue": [[.741176, .396078, .243137, 1.], [.2, .533333, .611765, 1.]],
    "gold_teal": [[.80, .61, .22, 1.], [.13, .47, .43, 1.]],
    "red_slate": [[.70, .20, .18, 1.], [.35, .46, .58, 1.]],
    "violet_cream": [[.51, .30, .67, 1.], [.82, .76, .59, 1.]],
}
GEOMETRY_DEFAULTS = dict(scale=1., dx_m=0., dy_m=0., yaw_deg=0.)


class FamilyUnavailable(ValueError):
    pass


class DatasetNotReady(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def catalog():
    value = json.loads(CATALOG.read_text())
    if value["version"] != VERSION or tuple(f["id"] for f in value["families"]) != FAMILIES:
        raise ValueError("Unsupported fixed-family catalog; version the generator with the pool")
    return value


def family_record(family):
    return deepcopy(next(f for f in catalog()["families"] if f["id"] == family))


def verify_sources(record):
    if record["id"] != "claw_weave" or not record["geometry_implemented"]:
        raise FamilyUnavailable(f"{record['id']}: fixed geometry and paired robot IK are not implemented")
    for name, expected in record["source_sha256"].items():
        path = ROOT / record["source_directory"] / name
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"Fixed prototype source hash mismatch: {name}")


def derive(task):
    p = task["seed_variant"]
    family = str(p["family_id"])
    if family not in FAMILIES or str(p["parameter_mode"]) not in MODES:
        raise ValueError("Unknown family or parameter mode")
    row = family_record(family)
    if str(p["parameter_mode"]) == "fixed":
        for name, value in GEOMETRY_DEFAULTS.items():
            p[name] = value
    task["variant"] = row["asset_id"] or f"unbuilt_{row['prototype_id']}"
    task["prototype"] = row
    task["render_variant"] = dict(colors=deepcopy(PALETTES[str(p["palette"])]),
        roughness=float(p["roughness"]), metallic=float(p["metallic"]))


def validate_parameters(task):
    p = task["seed_variant"]
    if p["family_id"] not in FAMILIES or p["parameter_mode"] not in MODES:
        raise ValueError("Unknown fixed prototype or parameter mode")
    ranges = dict(scale=(.99, 1.01), dx_m=(-.002, .002), dy_m=(-.002, .002),
                  yaw_deg=(-1., 1.), roughness=(.35, .60), metallic=(.10, .30))
    for name, (lo, hi) in ranges.items():
        value = float(p[name])
        if not np.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{name} outside the versioned candidate domain")
    if str(p["palette"]) not in PALETTES:
        raise ValueError("Unknown palette")
    if p["parameter_mode"] == "fixed" and any(float(p[k]) != v for k,v in GEOMETRY_DEFAULTS.items()):
        raise ValueError("Fixed prototypes cannot silently deform")
    style = task["render_variant"]
    if (not np.array_equal(style["colors"], PALETTES[str(p["palette"])])
            or float(style["roughness"]) != float(p["roughness"])
            or float(style["metallic"]) != float(p["metallic"])):
        raise ValueError("Render materials do not match sampled parameters")


@lru_cache(maxsize=1)
def _base_config():
    # Local loader: a dataset worker may already be inside a Hydra application.
    # Never clear/reinitialize its GlobalHydra singleton, including in threads.
    loader = ConfigLoaderImpl(create_config_search_path(str(ROOT / "configs")))
    cfg = loader.load_configuration("interlocked_claws_variants", [], RunMode.RUN, from_shell=False)
    OmegaConf.set_struct(cfg, False)
    del cfg["hydra"]
    return OmegaConf.to_container(cfg, resolve=True)


def _identity(resolved, seed, attempt, draw_seed, catalog_sha256):
    return dict(generator_version=VERSION, rng_version=VARIANT_RNG_VERSION,
                seed=seed, attempt=attempt, draw_seed=draw_seed,
                catalog_sha256=catalog_sha256, resolved_config=resolved)


def _spec_digest(data):
    data = deepcopy(data)
    data["variant"]["parameters"].pop("spec_sha256", None)
    return fingerprint(data)


def sample(seed, *, family=None, parameter_mode="fixed", attempt=0, config=None):
    """Return (cfg, EpisodeSpec). A proposal is not an accepted episode.

    The original seed selects the family once. Only its parameter draws use a
    retry stream. Order, batch length, output paths and global RNG do not matter.
    """
    seed, attempt = _integer(seed, "seed"), _integer(attempt, "attempt")
    if family is not None and family not in FAMILIES:
        raise ValueError("Unknown family")
    if parameter_mode not in MODES:
        raise ValueError("Unknown parameter mode")
    chosen = family or FAMILIES[int(VariantRng(seed).stream("interlocked_claws/family").integers(len(FAMILIES)))]
    cfg = OmegaConf.create(deepcopy(_base_config() if config is None else config))
    OmegaConf.set_struct(cfg, False)
    cfg.task.seed_variant.parameter_mode = parameter_mode
    for directive in cfg.task.variation:
        if directive.get("path") == "seed_variant.family_id":
            directive["values"] = [chosen]
    draw_seed = seed if attempt == 0 else int(VariantRng(seed).stream("interlocked_claws/parameters", retry=attempt).integers(0, 2**63))
    cfg, spec = build_variant_episode(cfg, "interlocked_claws", draw_seed, variant_id=VERSION)
    cfg.task.seed = seed
    # Nyx applies env appearance rules after entity creation. Keep its final
    # overrides consistent with the actual per-instance materials and assets.
    rules = [OmegaConf.to_container(rule, resolve=True) for rule in cfg.env.get("appearance", [])
             if str(rule.get("pattern")) not in ("claw_0", "claw_1")]
    style = cfg.task.render_variant
    rules.extend(dict(pattern=f"claw_{i}", color=list(color[:3]),
                      roughness=float(style.roughness), metallic=float(style.metallic))
                 for i,color in enumerate(style.colors))
    cfg.env.appearance = rules
    # Snapshot values, never sampling directives or machine-specific output paths.
    resolved = OmegaConf.to_container(cfg, resolve=True)
    resolved.pop("hydra", None)
    resolved["task"].pop("variation", None)
    resolved["run"].pop("output", None)
    identity = _identity(resolved, seed, attempt, draw_seed, sha(CATALOG))
    digest = fingerprint(identity)
    prototype = resolved["task"]["prototype"]
    mechanical = dict(prototype=prototype, parameters={k:float(cfg.task.seed_variant[k]) for k in GEOMETRY_DEFAULTS},
        robot=resolved["robot_control"], sim=resolved["env"]["sim"],
        mount=resolved["env"]["robot_mount"], collision=dict(sdf_cell_size_m=cfg.task.sdf_cell_size_m, sdf_max_res=cfg.task.sdf_max_res))
    key = replace(spec.key, seed=seed, preset_id=str(cfg.env.preset.id), variant_id=digest[:24])
    spec = replace(spec, key=key, preset=replace(spec.preset, preset_id=key.preset_id),
        variant=replace(spec.variant, key=key, parameters=dict(spec.variant.parameters,
            instance_sha256=digest, generator_version=VERSION, rng_version=VARIANT_RNG_VERSION,
            catalog_sha256=identity["catalog_sha256"], attempt=attempt, draw_seed=draw_seed,
            mechanical_sha256=fingerprint(mechanical), split_group=fingerprint(prototype)),
            notes="Seed proposal only. Check materialization and validation gates before execution/export."),
        resolved_config=resolved)
    spec = replace(spec, variant=replace(spec.variant, parameters=dict(spec.variant.parameters,
        spec_sha256=_spec_digest(asdict(spec)))))
    return cfg, spec


def load_instance(path):
    """Restore a frozen EpisodeSpec snapshot; never resample a stored seed."""
    data = json.loads(Path(path).read_text())
    params, key = data["variant"]["parameters"], data["key"]
    if params.get("spec_sha256") != _spec_digest(data):
        raise ValueError("EpisodeSpec metadata/config hash mismatch")
    if params["generator_version"] != VERSION or params["rng_version"] != VARIANT_RNG_VERSION:
        raise ValueError("Unsupported generator/RNG version")
    if params["catalog_sha256"] != sha(CATALOG):
        raise ValueError("Fixed prototype catalog hash changed")
    digest = fingerprint(_identity(data["resolved_config"], key["seed"], params["attempt"],
                                   params["draw_seed"], params["catalog_sha256"]))
    if digest != params["instance_sha256"] or key["variant_id"] != digest[:24] or data["variant"]["key"] != key:
        raise ValueError("Instance hash or episode key mismatch")
    cfg = OmegaConf.create(data["resolved_config"])
    validate_parameters(cfg.task)
    if cfg.task.prototype != family_record(str(cfg.task.seed_variant.family_id)):
        raise ValueError("Instance prototype differs from pinned registry")
    for i,color in enumerate(cfg.task.render_variant.colors):
        matches = [r for r in cfg.env.appearance if fnmatchcase(f"claw_{i}", str(r.pattern))]
        if (not matches or list(matches[-1].color) != list(color[:3])
                or matches[-1].roughness != cfg.task.render_variant.roughness
                or matches[-1].metallic != cfg.task.render_variant.metallic):
            raise ValueError("Renderer override differs from the frozen instance material")
    if cfg.task.prototype.geometry_implemented:
        verify_sources(OmegaConf.to_container(cfg.task.prototype, resolve=True))
    return cfg


def assert_runtime_supported(task):
    """Prevent existing reference runners from ignoring unimplemented changes."""
    if not task.get("seed_variant"):
        return
    validate_parameters(task)
    row = family_record(str(task.seed_variant.family_id))
    verify_sources(row)
    if str(task.seed_variant.parameter_mode) != "fixed":
        raise ValueError("Similarity candidate requires newly solved robot IK and fixture layout; reference runtime cannot execute it")


def transform_pose(pose, parameters):
    """Common similarity of a rigid pose; local geometry is scaled separately."""
    rotation = Rotation.from_euler("z", float(parameters["yaw_deg"]), degrees=True).as_matrix()
    pivot = np.array([0., 0., .3])
    result = np.eye(4)
    result[:3,:3] = rotation @ np.asarray(pose)[:3,:3]
    result[:3,3] = pivot + rotation @ (float(parameters["scale"])*(np.asarray(pose)[:3,3]-pivot)) + [float(parameters["dx_m"]), float(parameters["dy_m"]), 0.]
    return result


def ideal_pair_certificate(cfg):
    """A common positive similarity multiplies every source surface gap by s.

    This certifies desired rigid-body motion only. A retargeted joint-linear
    path, robot/environment contacts and physical tracking need new checks.
    """
    row = family_record(str(cfg.task.seed_variant.family_id))
    verify_sources(row)
    item = row["ideal_pair_certificate"]
    path = ROOT/item["path"]
    if sha(path) != item["sha256"]:
        raise ValueError("Pinned reference path certificate hash mismatch")
    source = json.loads(path.read_text())
    if not source["passed"] or source["failures"] or source["source_motion_sha256"] != row["source_sha256"]["recorded_motion.json"]:
        raise ValueError("Reference certificate does not match prototype motion")
    return dict(passed=True, method="common_positive_similarity_of_certified_source_path",
        frame="source_reference", source_certificate_sha256=item["sha256"],
        minimum_ideal_clearance_lower_bound_m=float(cfg.task.seed_variant.scale)*source["minimum_certified_clearance_m"],
        robot_ik_certified=False, robot_collision_certified=False, dynamics_certified=False)


def materialize(cfg, output):
    """Build real A0 geometry. B/C remain unavailable, with no dummy assets."""
    from .geometry import ClawAssembly, generate_assets, geometry_report
    row = family_record(str(cfg.task.seed_variant.family_id))
    verify_sources(row)
    validate_parameters(cfg.task)
    output = Path(output)
    p = cfg.task.seed_variant
    if p.parameter_mode == "fixed":
        _, report = generate_assets(output, render_variant=cfg.task.render_variant)
        return dict(geometry="passed", robot_ik="pinned_reference", robot_runtime="supported",
            physical_execution="not_run_for_instance", generic_contact_controls="failed_reference",
            dataset_eligible=False, retarget_required=False, geometry_report=report,
            ideal_pair_path=ideal_pair_certificate(cfg))
    assembly = ClawAssembly(render_variant=cfg.task.render_variant)
    original_poses = np.asarray(assembly.reference["initial_piece_poses"]).copy()
    for body in assembly.bodies:
        body.mesh.apply_scale(float(p.scale))
        body.pose = transform_pose(body.pose, p)
    assembly.reference["initial_piece_poses"] = [b.pose.tolist() for b in assembly.bodies]
    report = geometry_report(assembly)
    report.update(triangle_positions_preserved=False, source_scale_m_per_unit=.1*float(p.scale),
                  full_path_verified=False, robot_ik_verified=False,
                  scope="similarity candidate solids and transformed initial poses",
                  source_pose_max_error=float(np.max(np.abs(np.array([b.pose for b in assembly.bodies])-original_poses))),
                  transformed_initial_pose_max_error=0.)
    if not report["passed"]:
        raise ValueError("Similarity candidate geometry/initial pose failed")
    output.mkdir(parents=True, exist_ok=False)
    for body in assembly.bodies:
        body.mesh.export(output/f"{body.name}.obj", digits=12, include_texture=False)
    (output/"geometry_report.json").write_text(canonical(report)+"\n")
    # Bind an evaluable continuous target to source motion and transform. This
    # is deliberately not a fabricated joint trajectory for the new geometry.
    target = dict(source_motion_sha256=row["source_sha256"]["recorded_motion.json"],
        source_motion=str(Path(row["source_directory"])/"recorded_motion.json"),
        frame="source_reference", length_unit="m", time_unit="s",
        pose_transform="topogym.tasks.interlocked_claws.variants:transform_pose",
        uniform_local_mesh_scale=float(p.scale), parameters={k:float(p[k]) for k in GEOMETRY_DEFAULTS},
        independent_target_evaluator="topogym.tasks.interlocked_claws.variants:motion_targets",
        robot_ik_solved=False, fixtures_retargeted=False)
    from .reference import ReferenceMotion
    target["scaled_gripper_to_piece_transforms"] = []
    for grasp in ReferenceMotion().grasps:
        grasp = grasp.copy()
        grasp[:3,3] *= float(p.scale)
        target["scaled_gripper_to_piece_transforms"].append(grasp.tolist())
    target["ideal_pair_certificate"] = ideal_pair_certificate(cfg)
    (output/"motion_target.json").write_text(canonical(target)+"\n")
    return dict(geometry="passed", robot_ik="not_run", robot_runtime="unsupported",
        physical_execution="not_run", generic_contact_controls="not_run",
        dataset_eligible=False, retarget_required=True, geometry_report=report,
        ideal_pair_path=target["ideal_pair_certificate"])


def motion_targets(cfg, seconds):
    """Evaluate desired piece poses with the same transform as generated meshes."""
    from .reference import ReferenceMotion
    verify_sources(family_record(str(cfg.task.seed_variant.family_id)))
    _, _, poses, held, phase = ReferenceMotion().sample(float(seconds))
    return [transform_pose(p, cfg.task.seed_variant) for p in poses], held, phase


def prepare_episode(instance_path, *, for_dataset=False):
    """Future pipeline boundary: load once, check capability, then build scene.

    No recorder or HDF5 dependency. Current dataset requests all fail explicitly.
    Preview/execution is supported only for fixed A0 with render-only changes.
    """
    cfg = load_instance(instance_path)
    if for_dataset:
        row = family_record(str(cfg.task.seed_variant.family_id))
        raise DatasetNotReady(f"{row['id']}: dataset export disabled; {', '.join(row['blockers'])}; per-instance release validation required")
    assert_runtime_supported(cfg.task)
    return cfg


def generate(seed, output, *, family=None, parameter_mode="fixed", max_attempts=4):
    """Materialize bounded deterministic candidates; never claim dataset success."""
    _integer(seed, "seed")
    max_attempts = _integer(max_attempts, "max_attempts")
    if max_attempts < 1 or max_attempts > 100:
        raise ValueError("max_attempts must be between 1 and 100")
    first_cfg, _ = sample(seed, family=family, parameter_mode=parameter_mode)
    chosen = str(first_cfg.task.seed_variant.family_id)
    output = Path(output).resolve()
    if output == ROOT/"demos" or ROOT/"demos" in output.parents:
        raise ValueError("Instance metadata/assets must be outside demos/")
    output.mkdir(parents=True, exist_ok=False)
    attempts = []
    for attempt in range(max_attempts):
        cfg, spec = sample(seed, family=chosen, parameter_mode=parameter_mode, attempt=attempt)
        dest = output/f"attempt_{attempt:02d}"
        dest.mkdir()
        (dest/"instance.json").write_text(canonical(asdict(spec))+"\n")
        OmegaConf.save(OmegaConf.create(spec.resolved_config), dest/"config.yaml")
        entry = dict(attempt=attempt, family_id=chosen, instance_id=spec.key.variant_id,
                     instance_sha256=spec.variant.parameters["instance_sha256"])
        try:
            report = materialize(cfg, dest/"assets")
            entry.update(materialized=True, validation=report)
            attempts.append(entry)
            break
        except (ValueError, RuntimeError) as exc:
            entry.update(materialized=False, error=str(exc), error_type=type(exc).__name__)
            attempts.append(entry)
            if isinstance(exc, FamilyUnavailable):
                break  # No amount of random retry can create an unimplemented template.
    result = dict(schema_version=1, generator_version=VERSION, seed=int(seed), family_id=chosen,
        parameter_mode=parameter_mode, materialized=attempts[-1]["materialized"],
        dataset_eligible=False, dataset_generated=False, h5_generated=False,
        attempts=attempts, candidate_directory=f"attempt_{attempts[-1]['attempt']:02d}")
    for path in sorted(output.rglob("*")):
        if path.is_file():
            result.setdefault("files", {})[str(path.relative_to(output))] = sha(path)
    (output/"result.json").write_text(canonical(result)+"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--parameter-mode", choices=MODES, default="fixed")
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.seed, args.output, family=args.family,
        parameter_mode=args.parameter_mode, max_attempts=args.max_attempts)
    print(json.dumps({k:v for k,v in result.items() if k not in ("files","attempts")}, indent=2))
    if not result["materialized"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
