"""Seed -> fixed family + coupled appearance/layout -> checked assembly instance.

Uses the existing named RNG and declarative sampler. No simulation, recording or
dataset writer is imported by sampling. Generated instances are geometry/IK
candidates; physical execution has its own explicit validation status.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.generation.episode_spec import TaskLayout
from topogym.generation.variant_episode import build_variant_episode
from topogym.generation.variant_rng import VARIANT_RNG_VERSION, VariantRng
from .geometry import CoilAssembly, geometry_report, partition_solid
from .inverse_design import KINDS

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "assets/tasks/cast_coil/seed_families_v1"
VERSION = "cast_coil_seed_v2"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def catalog():
    result = json.loads((ASSETS / "catalog.json").read_text())
    for row in result["families"]:
        if (
            hashlib.sha256((ASSETS / row["core_template"]).read_bytes()).hexdigest()
            != row["sha256"]
        ):
            raise ValueError("Fixed prototype checksum mismatch")
    return result


def profile_cuts(family, length_mm):
    """Family outline, cut outside the protected |x| <= 33 mm grasp slab."""
    if family not in KINDS or not 15 <= length_mm <= 16.5:
        raise ValueError("Unknown family or profile outside the versioned domain")
    length, cuts = length_mm / 1000, []
    if not np.isclose(length_mm / 0.75, round(length_mm / 0.75)):
        raise ValueError("Profile must lie on the 0.75 mm grid")
    for sx in (-1,) if family == "eccentric_turn" else (-1, 1):
        for sz in (-1, 1):
            if family == "split_turn_offset":
                boxes = [
                    np.array(
                        [
                            [0.051 - length, -0.1, 0.051 - length / 2],
                            [0.052, 0.1, 0.052],
                        ]
                    )
                ]
            else:
                boxes = [
                    np.array(
                        [
                            [
                                0.051 - length + i * 0.00075,
                                -0.1,
                                0.051 - (i + 1) * 0.00075,
                            ],
                            [0.052, 0.1, 0.052],
                        ]
                    )
                    for i in range(round(length_mm / 0.75))
                ]
            cuts.extend(np.sort(box * [sx, 1, sz], axis=0) for box in boxes)
    return np.round(cuts, 12)


@lru_cache(maxsize=9)
def _profile(family, delta_mm, core_sha):
    # SHA in the key prevents stale reuse if the fixed pool is revised.
    row = next(r for r in catalog()["families"] if r["family_id"] == family)
    template = json.loads((ASSETS / row["core_template"]).read_text())
    boxes = {}
    for name, blocks in template["authored_boxes_mm"].items():
        _, cells = partition_solid(
            np.round(np.asarray(blocks) * 0.003, 12),
            profile_cuts(family, 15 + delta_mm),
        )
        boxes[name] = (cells / 0.003).tolist()
    template["authored_boxes_mm"] = boxes
    template["family_profile"] = dict(
        kind=family,
        length_mm=15 + delta_mm,
        method={
            "eccentric_turn": "one_sided_chamfer",
            "split_turn_offset": "rectangular_corner_steps",
            "axial_screw_turn": "four_corner_chamfer",
        }[family],
        staircase_pitch_mm=0.75,
    )
    volumes = [
        float(np.prod(np.diff(np.asarray(b), axis=1)[:, 0], axis=1).sum())
        for b in boxes.values()
    ]
    return template, np.array(volumes)


def derive(task):
    """Pure conditioned transform for the shared sampler's derived hook."""
    p = task["randomization"]
    family, s, delta = (
        str(p["family_id"]),
        float(p["face_scale"]),
        float(p["profile_delta_mm"]),
    )
    row = next((r for r in catalog()["families"] if r["family_id"] == family), None)
    if row is None:
        raise ValueError("Unknown fixed family")
    source, volumes = _profile(family, delta, row["sha256"])
    _, reference = _profile(family, 0.0, row["sha256"])
    ratio = s * s * volumes / reference
    lo, hi = (
        max(0.94, float(np.max(0.9 / ratio))),
        min(1.06, float(np.min(1.1 / ratio))),
    )
    if lo > hi:
        raise ValueError("Empty coupled mass/depth range")
    d = lo + float(p["depth_fraction"]) * (hi - lo)
    template = deepcopy(source)
    scale = np.array([s, d, s])
    template["authored_boxes_mm"] = {
        k: (np.asarray(v) * scale).tolist()
        for k, v in source["authored_boxes_mm"].items()
    }
    for key in (
        "outer_width",
        "band_width",
        "bridge_height",
        "bridge_center_clearance",
        "relief_width",
        "relief_depth",
        "central_bore_half_width_mm",
    ):
        if key in template:
            template[key] *= s
    for key in ("layer_thickness", "layer_clearance"):
        template[key] *= d
    parameters = dict(face_scale=s, depth_scale=d, profile_delta_mm=delta)
    template["appearance_design"] = dict(
        kind="seed_family",
        parameters=parameters,
        prototype_id=row["prototype_id"],
        core_sha256=row["sha256"],
        generator_version=VERSION,
    )
    template["template_id"] = (
        "cast_coil_"
        + family
        + "_"
        + fingerprint(dict(core=row["sha256"], version=VERSION, **parameters))[:16]
    )
    task["template"] = template
    task["variant"] = template["template_id"]
    task["center_xy_m"] = [
        -0.1356786 + float(p["center_dx_m"]),
        0.05 + float(p["center_dy_m"]),
    ]
    task["yaw_deg"] = 90 + float(p["yaw_delta_deg"])
    task["initial_xy_offset_m"] = [
        -0.12 + float(p["separation_dx_m"]),
        0.18 + float(p["separation_dy_m"]),
    ]
    task["derived_variant"] = dict(
        prototype_id=row["prototype_id"],
        family_id=family,
        generator_version=VERSION,
        depth_range=[lo, hi],
        mass_ratios=(ratio * d).tolist(),
        parameters=parameters,
        core_sha256=row["sha256"],
        profile_length_mm=(15 + delta) * s,
        actual_axial_advance_mm=9 * d if family == "axial_screw_turn" else 0.0,
    )


def validate_parameters(task):
    p = task["randomization"]
    ranges = dict(
        face_scale=(0.97, 1.03),
        depth_fraction=(0, 1),
        profile_delta_mm=(0, 1.5),
        yaw_delta_deg=(-3, 3),
        center_dx_m=(-0.005, 0.005),
        center_dy_m=(-0.005, 0.005),
        separation_dx_m=(-0.005, 0.005),
        separation_dy_m=(-0.005, 0.005),
    )
    if task["objective"] != "assemble" or float(task["scale"]) != 3.0:
        raise ValueError("This generator supports the 3x assembly task")
    for key, (lo, hi) in ranges.items():
        value = float(p[key])
        if not np.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} outside the versioned domain")
    if float(p["profile_delta_mm"]) not in (0.0, 1.5):
        raise ValueError("Invalid outline step")
    if not all(
        0.9 - 1e-12 <= r <= 1.1 + 1e-12 for r in task["derived_variant"]["mass_ratios"]
    ):
        raise ValueError("Coupled mass rule violated")


@lru_cache(maxsize=1)
def _base_config():
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        return OmegaConf.to_container(
            compose(config_name="cast_coil_variants"), resolve=True
        )


def sample(seed, *, family=None, attempt=0, representative=False, config=None):
    """Return (resolved cfg, EpisodeSpec), independent of batch/order/output path."""
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be a nonnegative integer")
    if family is not None and family not in KINDS:
        raise ValueError("Unknown family")
    cfg = OmegaConf.create(_base_config() if config is None else deepcopy(config))
    OmegaConf.set_struct(cfg, False)
    if family:
        directive = next(
            d for d in cfg.task.variation if d.get("path") == "randomization.family_id"
        )
        directive.values = [family]
    if representative:
        if family is None:
            raise ValueError("A representative requires a fixed family")
        for directive in cfg.task.variation:
            if directive.get("kind") in ("uniform", "choice"):
                path = directive.path
                value = OmegaConf.select(cfg.task, path)
                directive.clear()
                directive.update(
                    dict(
                        kind="choice",
                        path=path,
                        values=[family if path.endswith("family_id") else value],
                    )
                )
    draw_seed = (
        int(seed)
        if attempt == 0
        else int(
            VariantRng(seed)
            .stream("cast_coil/accepted_attempt", retry=attempt)
            .integers(0, 2**63)
        )
    )
    cfg, spec = build_variant_episode(cfg, "cast_coil", draw_seed, variant_id=VERSION)
    cfg.task.seed = int(seed)
    # Immutable identity binds the actual instance, including fixed physics and robot settings.
    resolved = OmegaConf.to_container(cfg, resolve=True)
    resolved.pop("hydra", None)
    identity = dict(
        generator_version=VERSION,
        rng_version=VARIANT_RNG_VERSION,
        seed=int(seed),
        attempt=attempt,
        draw_seed=draw_seed,
        task=resolved["task"],
        env=resolved["env"],
        robot_control=resolved["robot_control"],
    )
    instance_id = fingerprint(identity)
    key = replace(
        spec.key,
        seed=int(seed),
        variant_id=instance_id[:24],
        preset_id=str(cfg.env.preset.id),
    )
    spec = replace(
        spec,
        key=key,
        preset=replace(spec.preset, preset_id=key.preset_id),
        variant=replace(
            spec.variant,
            key=key,
            parameters=dict(
                spec.variant.parameters,
                instance_sha256=instance_id,
                generator_version=VERSION,
                rng_version=VARIANT_RNG_VERSION,
                attempt=attempt,
                draw_seed=draw_seed,
            ),
        ),
        resolved_config=resolved,
    )
    return cfg, spec


def check_geometry(cfg):
    from .assembly_task import initial_poses, motions, xy_surface_gaps, route_lift
    from .verification import CompoundCollision, Motion

    template = OmegaConf.to_container(cfg.task.template, resolve=True)
    assembly = CoilAssembly(template)
    geometry = geometry_report(assembly)
    if not geometry["passed"]:
        raise ValueError("Invalid solid, bore or initial assembled clearance")
    origin = np.r_[
        np.asarray(cfg.task.center_xy_m) - np.asarray(cfg.env.robot_mount.pos)[:2],
        -min(b.visual.bounds[0, 2] for b in assembly.bodies),
    ]
    poses = initial_poses(
        assembly,
        origin,
        Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True),
        cfg.task.initial_xy_offset_m,
    )
    route, certificates = motions(assembly, poses)
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    # Material removal must not open a trivial straight escape. An overlap
    # witness proves blockage; failing a clearance margin alone does not.
    negatives = []
    for axis in range(3):
        for sign in (-1, 1):
            m = Motion(
                f"straight_{axis}_{sign}",
                1.0,
                np.eye(3),
                np.zeros(3),
                np.eye(3)[axis] * sign * 0.24,
            )
            samples = [
                (float(u), collision.gap(*m.pose(u))) for u in np.linspace(0, 1, 65)
            ]
            u, gap = min(samples, key=lambda x: x[1])
            negatives.append(dict(name=m.name, u=u, gap_m=gap, blocked=gap < 0))
    if not all(n["blocked"] for n in negatives):
        raise ValueError(
            "An outline change removed a required straight-motion obstacle"
        )
    from .inverse_design import FAMILY_PARAMETERS, variant_route

    scales = np.array(
        [
            float(cfg.task.derived_variant.parameters.face_scale),
            float(cfg.task.derived_variant.parameters.depth_scale),
            float(cfg.task.derived_variant.parameters.face_scale),
        ]
    )
    family_controls = []
    for other in KINDS:
        if other == cfg.task.derived_variant.family_id:
            continue
        witness = None
        for motion in variant_route(other, {FAMILY_PARAMETERS[other][0]: 9.0}):
            motion = replace(
                motion,
                **{
                    k: getattr(motion, k) * scales
                    for k in (
                        "start_translation",
                        "end_translation",
                        "pivot",
                        "advance",
                    )
                    if getattr(motion, k, None) is not None
                },
            )
            for u in np.linspace(0, 1, 33):
                gap = collision.gap(*motion.pose(float(u)))
                if gap < -1e-9:
                    witness = dict(phase=motion.name, u=float(u), gap_m=gap)
                    break
            if witness is not None:
                break
        if witness is None:
            raise ValueError(f"Other-family route {other} lacks a real overlap witness")
        family_controls.append(dict(family=other, blocked=True, witness=witness))
    for a, b in zip(route, route[1:]):
        if any(
            not np.allclose(x, y, atol=1e-12, rtol=0)
            for x, y in zip(a.pose(1), b.pose(0))
        ):
            raise ValueError("Discontinuous construction witness")
    return dict(
        status="passed",
        geometry=geometry,
        assembly_certificates=certificates,
        route_table_clearance=route_lift(
            assembly,
            origin,
            poses[0][0],
            route,
            nominal=0.08 * float(cfg.task.derived_variant.parameters.face_scale),
        ),
        negative_controls=negatives,
        initial_xy_surface_gap_m=xy_surface_gaps(assembly, poses),
        other_family_controls=family_controls,
        initial_poses=[dict(r=r.as_quat().tolist(), p=p.tolist()) for r, p in poses],
        frame="robot_mount",
        route_phases=[m.name for m in route],
        minimum_certified_gap_m=min(
            c["certified_separation_lower_bound_m"] for c in certificates
        ),
    )


def generate(
    seed, output, *, family=None, representative=False, robot=True, max_attempts=8
):
    """Materialize checked candidates; never returns a failed draw as accepted."""
    output = Path(output).resolve()
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if representative:
        max_attempts = 1
    if (ROOT / "demos") == output or (ROOT / "demos") in output.parents:
        raise ValueError("Variant metadata belongs under runs/, not demos/")
    output.mkdir(parents=True, exist_ok=False)
    attempts = []
    for attempt in range(max_attempts):
        cfg, spec = sample(
            seed, family=family, attempt=attempt, representative=representative
        )
        candidate = output / f"attempt_{attempt:02d}"
        candidate.mkdir()
        template = OmegaConf.to_container(cfg.task.template, resolve=True)
        (candidate / "template.json").write_text(canonical(template) + "\n")
        try:
            geometry = check_geometry(cfg)
            spec = replace(
                spec,
                layout=TaskLayout(
                    "cast_coil",
                    frame="robot_mount",
                    objects=dict(initial_poses=geometry["initial_poses"]),
                    metadata=dict(objective="assemble"),
                ),
            )
            plan = None
            if robot:
                from .robot_plan import build

                plan = build(
                    candidate / "robot_plan.json",
                    candidate / "template.json",
                    objective="assemble",
                    task_config=cfg.task,
                )
            status = dict(
                geometry="passed",
                robot_ik="passed" if robot else "not_run",
                physical_execution="not_run",
            )
            entry = dict(
                attempt=attempt,
                accepted=True,
                instance_id=spec.key.variant_id,
                validation=status,
                maximum_ik_error=plan["maximum_ik_error"] if plan else None,
            )
            attempts.append(entry)
            (candidate / "geometry.json").write_text(canonical(geometry) + "\n")
            (candidate / "instance.json").write_text(canonical(asdict(spec)) + "\n")
            OmegaConf.save(cfg, candidate / "config.yaml", resolve=True)
            result = dict(
                schema_version=1,
                generator_version=VERSION,
                seed=int(seed),
                family_id=cfg.task.derived_variant.family_id,
                accepted=True,
                accepted_attempt=attempt,
                candidate_directory=candidate.name,
                instance_id=spec.key.variant_id,
                validation=status,
                attempts=attempts,
                dataset_generated=False,
                video_generated=False,
            )
            (output / "result.json").write_text(canonical(result) + "\n")
            return result
        except (ValueError, RuntimeError) as exc:
            attempts.append(
                dict(
                    attempt=attempt,
                    accepted=False,
                    error=str(exc),
                    instance_id=spec.key.variant_id,
                )
            )
            (candidate / "rejection.json").write_text(canonical(attempts[-1]) + "\n")
    result = dict(
        seed=int(seed), accepted=False, attempts=attempts, generator_version=VERSION
    )
    (output / "result.json").write_text(canonical(result) + "\n")
    raise RuntimeError(
        f"No valid candidate after {max_attempts} attempts; see {output / 'result.json'}"
    )


def load_instance(path):
    """Recover the saved config and verify its bound contents without sampling."""
    data = json.loads(Path(path).read_text())
    p, resolved = data["variant"]["parameters"], data["resolved_config"]
    identity = dict(
        generator_version=p["generator_version"],
        rng_version=p["rng_version"],
        seed=data["key"]["seed"],
        attempt=p["attempt"],
        draw_seed=p["draw_seed"],
        task=resolved["task"],
        env=resolved["env"],
        robot_control=resolved["robot_control"],
    )
    if (
        fingerprint(identity) != p["instance_sha256"]
        or data["key"]["variant_id"] != p["instance_sha256"][:24]
    ):
        raise ValueError("Saved instance content hash mismatch")
    return OmegaConf.create(resolved)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--family", choices=KINDS)
    parser.add_argument("--representative", action="store_true")
    parser.add_argument("--geometry-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            generate(
                args.seed,
                args.output,
                family=args.family,
                representative=args.representative,
                robot=not args.geometry_only,
            ),
            indent=2,
        )
    )
