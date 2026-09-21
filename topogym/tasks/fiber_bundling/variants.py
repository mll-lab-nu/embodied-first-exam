"""Reproducible two-axis geometry candidates, with no implied IK certificate."""
import argparse
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from topogym.generation.variant_rng import VariantRng, VARIANT_RNG_VERSION
from .geometry import FiberLayout, minimum_fiber_clearance
from .anchored_geometry import AnchoredLayout, generate_anchored_assets
from .ring_mount import RingMount, export_fixture

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT/"configs/task_variants/fiber_bundling_density_v1.yaml"


def rules():
    return OmegaConf.to_container(OmegaConf.load(RULES), resolve=True)


def sample_parameters(seed, family_id=None, *, retry=0):
    if isinstance(seed,bool) or not isinstance(seed,int) or seed < 0:
        raise ValueError("Use a nonnegative integer episode seed")
    if isinstance(retry, bool) or not isinstance(retry, int) or retry < 0:
        raise ValueError("Use a nonnegative integer retry")
    spec = rules()
    rng = VariantRng(seed)
    families = list(spec["families"])
    family_id = families[rng.tier(len(families))] if family_id is None else family_id
    if family_id not in families:
        raise ValueError(f"Unknown density family: {family_id}")
    count = int(rng.stream("fiber_bundling/density/fiber_count", retry=retry).choice(
        spec["families"][family_id]["fiber_counts"]))
    low,high = spec["shared"]["ring_inner_radius_range_m"]
    radius = float(rng.stream("fiber_bundling/ring_inner_radius_m", retry=retry).uniform(low,high))
    return dict(family_id=family_id, fiber_count=count, ring_inner_radius_m=radius,
                shape_seed=spec["shared"]["shape_seed"], episode_seed=seed,
                generator_version=spec["generator_version"], variant_rng_version=VARIANT_RNG_VERSION)


def candidate_config(parameters):
    from hydra import compose, initialize_config_dir
    with initialize_config_dir(version_base="1.3", config_dir=str(ROOT/"configs")):
        cfg = compose(config_name=rules()["base_config"])
    cfg.task.geometry.fiber_count = parameters["fiber_count"]
    cfg.task.geometry.ring_inner_radius_m = parameters["ring_inner_radius_m"]
    cfg.task.geometry.seed = parameters["shape_seed"]
    return cfg


def validate_parameters(parameters):
    """Validate the declared sampling envelope before creating any output."""
    spec = rules()
    family = parameters.get("family_id")
    if family not in spec["families"]:
        raise ValueError(f"Unknown density family: {family}")
    count = parameters.get("fiber_count")
    if isinstance(count, bool) or not isinstance(count, int) or count not in spec["families"][family]["fiber_counts"]:
        raise ValueError("Fiber count does not belong to the requested density family")
    radius = parameters.get("ring_inner_radius_m")
    lo, hi = spec["shared"]["ring_inner_radius_range_m"]
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not lo <= radius <= hi:
        raise ValueError("Ring radius lies outside the declared sampling envelope")
    if (parameters.get("shape_seed") != spec["shared"]["shape_seed"]
            or isinstance(parameters.get("shape_seed"), bool) or not isinstance(parameters.get("shape_seed"), int)):
        raise ValueError("This generator freezes the shape seed; use a new generator version to change it")
    for key, expected in (("generator_version", spec["generator_version"]),
                          ("variant_rng_version", VARIANT_RNG_VERSION)):
        if key in parameters and parameters[key] != expected:
            raise ValueError(f"Unsupported {key}")


def inspect_candidate(cfg):
    layout = FiberLayout(**dict(cfg.task.geometry))
    anchor = AnchoredLayout.from_task_config(cfg.task)
    paths = np.asarray(layout.fibers())
    pitch = 2*layout.root_spread_m*np.sin(np.pi/layout.fiber_count)
    clearance = layout.minimum_aperture_radius-layout.trunk_radius_m
    surface_clearance = minimum_fiber_clearance(paths, layout.fiber_radius_m)
    envelope = float(np.linalg.norm(paths[:,:,1:],axis=-1).max()+layout.fiber_radius_m)
    reset_gap = (layout.trunk_length_m+anchor.ring_distance_from_roots_m-
                 layout.ring_tube_radius_m-float(paths[:,:,0].max())-layout.fiber_radius_m)
    checks = dict(no_initial_wire_intersections=surface_clearance > 0,
                  separated_root_disks=pitch > 2.4*layout.fiber_radius_m,
                  root_disks_inside_jacket=layout.root_spread_m+layout.fiber_radius_m < layout.trunk_radius_m,
                  positive_ring_initial_gap=reset_gap > 0,
                  trunk_clearance_with_margin=clearance >= rules()["shared"]["minimum_trunk_radial_clearance_m"],
                  initially_requires_gathering=envelope > layout.minimum_aperture_radius)
    return dict(geometry_checks_passed=bool(all(checks.values())),
        checks={k:bool(v) for k,v in checks.items()}, fiber_count=layout.fiber_count,
        root_center_spacing_m=float(pitch),root_surface_gap_m=float(pitch-2*layout.fiber_radius_m),
        insulation_area_fraction=layout.fiber_count*(layout.fiber_radius_m/layout.trunk_radius_m)**2,
        initial_wire_surface_clearance_m=float(surface_clearance),
        initial_bundle_radial_envelope_m=envelope,reset_ring_axial_gap_m=reset_gap,
        ring_nominal_inner_radius_m=layout.ring_inner_radius_m,
        ring_actual_min_aperture_radius_m=float(layout.minimum_aperture_radius),
        trunk_radial_clearance_m=float(clearance),
        physics_stability_verified=False,robot_ik_verified=False,full_threading_verified=False,
        note="Reset geometry only. Root packing is one circular row; no claim of distinct strategies or material calibration.")


def generate_candidate(folder, parameters):
    validate_parameters(parameters)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    cfg = candidate_config(parameters)
    cfg.run.output = str(folder.resolve())
    geometry = inspect_candidate(cfg)
    (folder/"parameters.json").write_text(json.dumps(parameters,indent=2)+"\n")
    (folder/"geometry_report.json").write_text(json.dumps(geometry,indent=2)+"\n")
    OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    if not geometry["geometry_checks_passed"]:
        raise ValueError(f"Rejected geometry; inspect {folder/'geometry_report.json'}")
    anchor = AnchoredLayout.from_task_config(cfg.task)
    layout,report = generate_anchored_assets(folder/"assets",FiberLayout(**dict(cfg.task.geometry)),anchor)
    report["candidate_parameters"] = parameters
    export_fixture(folder/"assets",layout,RingMount.from_task_config(cfg.task),
        (layout.trunk_length_m+anchor.ring_distance_from_roots_m,0.,0.),-anchor.axis_height_m,report)
    return dict(directory=folder.name,parameters=parameters,**geometry)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=7)
    parser.add_argument("--family",choices=tuple(rules()["families"]))
    parser.add_argument("--representatives",action="store_true",help="Generate a crossed 3 density × 3 aperture grid")
    args=parser.parse_args()
    if args.representatives:
        args.output.mkdir(parents=True,exist_ok=False)
        spec=rules()
        records=[]
        for family_id,family in spec["families"].items():
            for radius in spec["shared"]["representative_ring_radii_m"]:
                params=dict(family_id=family_id,fiber_count=family["representative_count"],
                    ring_inner_radius_m=radius,shape_seed=spec["shared"]["shape_seed"],
                    episode_seed=None,generator_version=spec["generator_version"],variant_rng_version=VARIANT_RNG_VERSION)
                name=f"{family_id}_{params['fiber_count']:02d}_r{radius*1000:.1f}mm"
                records.append(generate_candidate(args.output/name,params))
        (args.output/"manifest.json").write_text(json.dumps(dict(scope="nine_geometry_candidates",
            rules=spec,representatives=records,all_geometry_checks_passed=all(r["geometry_checks_passed"] for r in records),
            full_threading_verified=False),indent=2)+"\n")
    else:
        generate_candidate(args.output,sample_parameters(args.seed,args.family))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
