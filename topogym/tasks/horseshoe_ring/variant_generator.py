"""Seed -> resolved Horseshoe instance, independently of video/dataset writers.

Proposal ranges are not physics certificates. A proposal is never an accepted
episode; the execution/qualification runner must verify that exact snapshot.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.generation.variant_episode import build_variant_episode
from topogym.generation.variant_rng import VariantRng, VARIANT_RNG_VERSION
from .robot_motion import ROOT, Kinematics

VERSION = "horseshoe_physical_families_v2"
LIBRARY = ROOT/"assets/tasks/horseshoe_ring/family_space_v2/library.json"
ANCHORS = LIBRARY.with_name("paired_anchors.json")
FINISHES = {"silver": [.72, .76, .80, 1.], "brass": [.72, .52, .24, 1.],
            "dark_steel": [.34, .39, .46, 1.]}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def derive(task):
    g = task["generation"]
    jitter = bool(g["jitter"])
    def delta(name, amplitude):
        return (2*float(g[name])-1)*amplitude if jitter else 0.
    parameters = dict(family_id=g["family_id"], prototype_id=g["prototype_id"],
        scale_ratio=1+delta("size_u", .01), translation_m=[delta("x_u", .003), delta("y_u", .003), 0.],
        yaw_deg=delta("yaw_u", 1.), route_offset_m=[0., delta("route_u", .005), 0.],
        finish=g["finish"] if jitter else "silver")
    if g.get("parameterization") == "paired_anchor_neighborhood_v1":
        anchor = g["anchor_parameters"]
        def around(center, name, radius, limits):
            if not jitter:
                return float(center)
            low, high = max(limits[0], center-radius), min(limits[1], center+radius)
            if high <= low:
                raise ValueError("Empty conditional sampling interval")
            return low+(high-low)*float(g[name])
        parameters.update(scale_ratio=around(anchor["scale_ratio"], "size_u", .002, (.99, 1.01)),
            translation_m=[around(anchor["translation_m"][0], "x_u", .00075, (-.003, .003)),
                           around(anchor["translation_m"][1], "y_u", .00075, (-.003, .003)), 0.],
            yaw_deg=around(anchor["yaw_deg"], "yaw_u", .15, (-1., 1.)),
            route_offset_m=[0., around(anchor["route_offset_m"][1], "route_u", .001, (-.005, .005)), 0.],
            finish=g["finish"] if jitter else anchor["finish"])
    g["parameters"] = parameters
    task["scale"] = 2*parameters["scale_ratio"]
    task["yaw_deg"] = parameters["yaw_deg"]
    task["center_xy_m"] = (np.array([-.1356786, .05])+parameters["translation_m"][:2]).tolist()
    task["appearance"] = dict(target_ring_rgba=FINISHES[parameters["finish"]])


def validate_parameters(task):
    g = task["generation"]
    if g["version"] != VERSION or g["family_id"] not in ("F1", "F2", "F3"):
        raise ValueError("Unknown generator version or family")
    if g["prototype_id"] != "classic_circle":
        raise ValueError("Non-circular/reshaped prototypes are not physically paired")
    parameterization = g.get("parameterization")
    if parameterization not in (None, "paired_anchor_neighborhood_v1"):
        raise ValueError("Unknown conditional sampling policy")
    if parameterization and (g["anchor_parameters"]["family_id"] != g["family_id"] or
            g["anchor_parameters"]["prototype_id"] != g["prototype_id"]):
        raise ValueError("Anchor does not belong to the requested family/prototype")
    if g["finish"] not in FINISHES:
        raise ValueError("Unknown finish")
    for name in ("size_u", "x_u", "y_u", "yaw_u", "route_u"):
        if not 0 <= float(g[name]) <= 1:
            raise ValueError(f"Non-finite/out-of-domain axis: {name}")
    p = g["parameters"]
    if not .99 <= p["scale_ratio"] <= 1.01:
        raise ValueError("Scale outside the proposal envelope")


def create_instance(seed, *, family=None, jitter=True, attempt=0):
    """Pure indexed request: batch size/order/workers do not affect parameters."""
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or not 0 <= seed < 2**63:
        raise ValueError("seed must be an integer in [0, 2**63)")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError("attempt must be a nonnegative integer")
    library = json.loads(LIBRARY.read_text())
    rng = VariantRng(seed)
    selected = family or str(rng.stream("horseshoe_ring/generation.family_id").choice(["F1", "F2", "F3"]))
    if selected not in library["families"]:
        raise ValueError("Unknown requested family")
    # Fix the requested family across retries; never improve acceptance rate by
    # silently switching to a different family. The first attempt uses the
    # existing common sampler's seed mapping exactly.
    sampling_seed = int(seed) if attempt == 0 else int(rng.stream("horseshoe_ring/proposal", retry=attempt).integers(0, 2**63))
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="horseshoe_ring_variants")
    cfg.task.generation.jitter = jitter
    anchors = json.loads(ANCHORS.read_text())
    if anchors["generator_version"] != VERSION:
        raise ValueError("Anchor library version mismatch")
    cfg.task.generation.anchor_parameters = anchors["anchors"][selected]["parameters"]
    cfg.task.variation[0]["values"] = [selected]
    cfg, spec = build_variant_episode(cfg, "horseshoe_ring", sampling_seed, variant_id=VERSION)
    cfg.env.genesis.backend = "cpu"
    cfg.env.renderer.type = "rasterizer"
    cfg.env.sim.dt, cfg.env.sim.substeps, cfg.env.sim.gravity = .002, 4, [0., 0., -9.81]
    cfg.robot_control.controller.kp = [10000, 18000, 14000, 6000, 4000, 2500, 2000]
    cfg.robot_control.controller.kv = [200, 300, 250, 100, 80, 40, 124]
    # The writer/runner owns output placement. A generated instance must not
    # carry the historic demo's output directory or request video recording.
    cfg.run.output = None
    cfg.run.record_video = False
    parameters = OmegaConf.to_container(cfg.task.generation.parameters, resolve=True)
    plain = OmegaConf.to_container(cfg, resolve=True)
    prototype = library["prototypes"][parameters["prototype_id"]]
    template = json.loads((ROOT/prototype["template"]).read_text())
    sources = {p: file_hash(ROOT/p) for p in (prototype["template"], prototype["initialization_and_guide"])}
    sources["assets/tasks/horseshoe_ring/family_space_v2/library.json"] = file_hash(LIBRARY)
    sources["assets/tasks/horseshoe_ring/family_space_v2/paired_anchors.json"] = file_hash(ANCHORS)
    for name in ("variant_generator.py", "family_routes.py", "physical_motion.py", "physical_demo.py",
                 "physical_plan.py", "physical_extraction.py", "physical_place.py", "scene.py",
                 "robot_motion.py", "robot_clearance.py", "geometry.py"):
        path = Path(__file__).with_name(name)
        sources[str(path.relative_to(ROOT))] = file_hash(path)
    payload = dict(schema_version=2, generator_version=VERSION, rng_version=VARIANT_RNG_VERSION,
        request=dict(seed=int(seed), attempt=attempt, sampling_seed=sampling_seed, family_id=selected, jitter=jitter),
        parameters=parameters, template=template, resolved_config=plain, source_sha256=sources,
        units=dict(length="m", template_length="mm before task.scale", angle="degrees unless _rad", frame="ALOHA robot mount"),
        evidence=dict(status="proposed", physics="not_run", accepted=False),
        split_group=parameters["prototype_id"],
        limitation="Declared pregrasp and contact-gated ideal grasp assistance; no pure-friction claim")
    instance_id = "horseshoe_ring_v2_"+digest(payload)[:24]
    key = replace(spec.key, seed=int(seed), variant_id=instance_id)
    spec = replace(spec, key=key, variant=replace(spec.variant, key=key),
        resolved_config=plain, execution_profile=replace(spec.execution_profile,
            profile_id=VERSION, parameters=dict(instance_id=instance_id, attempt=attempt,
                planning_seed=int(rng.stream("horseshoe_ring/planner", retry=attempt).integers(1, 2**31)))))
    encoded_spec = asdict(spec)
    return dict(payload, instance_id=instance_id, payload_sha256=digest(payload),
        episode_spec=encoded_spec, episode_spec_sha256=digest(encoded_spec))


def validate_instance(instance, *, check_sources=True):
    payload = {k: v for k, v in instance.items() if k not in ("instance_id", "payload_sha256", "episode_spec", "episode_spec_sha256")}
    if instance["payload_sha256"] != digest(payload) or instance["instance_id"] != "horseshoe_ring_v2_"+digest(payload)[:24]:
        raise ValueError("Instance snapshot content hash mismatch")
    if instance["generator_version"] != VERSION or instance["rng_version"] != VARIANT_RNG_VERSION:
        raise ValueError("Unsupported instance version")
    validate_parameters(instance["resolved_config"]["task"])
    if instance["parameters"] != instance["resolved_config"]["task"]["generation"]["parameters"]:
        raise ValueError("Scene and planner parameters differ")
    spec = instance["episode_spec"]
    if (digest(spec) != instance["episode_spec_sha256"] or
            spec["resolved_config"] != instance["resolved_config"] or spec["key"]["variant_id"] != instance["instance_id"]
            or spec["key"] != spec["variant"]["key"] or spec["key"]["seed"] != instance["request"]["seed"]):
        raise ValueError("EpisodeSpec and snapshot differ")
    task = deepcopy(instance["resolved_config"]["task"])
    derive(task)
    if task != instance["resolved_config"]["task"]:
        raise ValueError("Derived parameters do not match the resolved scene")
    if check_sources:
        for name, expected in instance["source_sha256"].items():
            if file_hash(ROOT/name) != expected:
                raise ValueError(f"Changed generator/asset: {name}; regenerate under a new version")
    return instance


def retarget_seed(instance, cfg):
    """Adapt both initial grasp anchors AND every fold command by fresh IK.

    Only uniform similarity is supported; arbitrary ellipse/outline changes
    cannot use this paired grasp recipe. The extraction guide scales with it.
    """
    validate_instance(instance)
    source = json.loads((ROOT/"assets/tasks/horseshoe_ring/tutorial_solvable_v3/physical_seed.json").read_text())
    result = deepcopy(source)
    p = instance["parameters"]
    if p["scale_ratio"] == 1 and p["yaw_deg"] == 0 and p["translation_m"] == [0., 0., 0.]:
        return result
    scale = p["scale_ratio"]
    rotation = Rotation.from_euler("z", p["yaw_deg"], degrees=True)
    center = np.array([0., .05, .2])
    shift = np.asarray(p["translation_m"])
    kin = Kinematics(cfg.robot_control)
    errors = []
    for old, new in zip(source["frames"], result["frames"]):
        kin.q = np.asarray(old["qpos"]).copy()
        targets = {s: kin.pose(s) for s in ("left", "right")}
        for side, (point, turn) in targets.items():
            err = kin.solve(side, center+shift+rotation.apply(scale*(point-center)), rotation*turn)
            errors.append(err)
            if err[0] > .00005 or err[1] > .0005:
                raise RuntimeError(f"Retargeted fold IK failed: {side}, {err}")
        # ALOHA pad zero-offset is not a scale factor on the whole gripper.
        kin.q[[6, 7, 14, 15]] = .0084+scale*(np.asarray(old["qpos"])[[6, 7, 14, 15]]-.0084)
        new["qpos"] = kin.q.tolist()
        for name, pose in old.get("bodies", {}).items():
            new["bodies"][name] = dict(pos=(center+shift+rotation.apply(scale*(np.asarray(pose["pos"])-center))).tolist(),
                quat=(rotation*Rotation.from_quat(pose["quat"])).as_quat().tolist())
    result["report"]["scene_scale"] = float(cfg.task.scale)
    result["report"]["source_template_sha256"] = hashlib.sha256(json.dumps(instance["template"], sort_keys=True).encode()).hexdigest()
    result["variant_retargeting"] = dict(instance_id=instance["instance_id"], scale_ratio=scale,
        maximum_ik_error=np.max(errors, axis=0).tolist(), qualification="IK only; physics not implied")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", choices=("F1", "F2", "F3"))
    parser.add_argument("--anchor", action="store_true", help="Disable within-family jitter")
    parser.add_argument("--attempt", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    instance = create_instance(args.seed, family=args.family, jitter=not args.anchor, attempt=args.attempt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(instance, handle, ensure_ascii=False, indent=2)
    print(json.dumps(dict(instance_id=instance["instance_id"], parameters=instance["parameters"],
        status="candidate; not accepted until execution and verification"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
