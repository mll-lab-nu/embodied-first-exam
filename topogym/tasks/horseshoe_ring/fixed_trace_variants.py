"""Evaluate exact-chain-geometry variants against an immutable saved trace.

Changing only the ungrasped chain loops preserves the actual grasped surfaces.
Object poses are copied without re-planning or re-centring the assembly. Full
geometric witnesses and sampled robot clearance have deliberately separate scopes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import multiprocessing
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf

from .ik_trace import ROOT, SOURCE, OUTPUT, canonical_hash, command_hash, export_trace
from .independent_motion import IndependentWitness
from .robot_clearance import RobotClearance

SPEC = ROOT/"assets/tasks/horseshoe_ring/fixed_trace_v1/variants.json"


def variant_template(base, candidate):
    if set(candidate)-{"id", "title_zh", "radii", "wire_radius"}:
        raise ValueError("Fixed trace permits only the declared chain dimensions")
    template = deepcopy(base)
    template["template_id"] = f"horseshoe_fixed_trace_{candidate['id']}_v1"
    template["geometry_status"] = "Fixed-trace candidate; qualification is in its own compatibility report"
    template["chain"]["link_radii"] = list(candidate["radii"])
    template["chain"]["wire_radius"] = candidate["wire_radius"]
    return template


def verify_immutable_geometry(base, variant, base_centers, variant_model):
    """Reject silent grasp changes and material-frame translations."""
    for part in ("horseshoe", "target_ring"):
        if variant[part] != base[part]:
            raise ValueError(f"The grasped {part} geometry must remain unchanged")
    for key in set(base["chain"])|set(variant["chain"]):
        if key not in {"link_radii", "wire_radius"} and base["chain"].get(key) != variant["chain"].get(key):
            raise ValueError(f"Frozen chain placement/topology field changed: {key}")
    if not np.allclose(base_centers, variant_model.centers, atol=1e-12, rtol=0):
        raise ValueError("Variant changes a body origin; the saved body transforms would no longer be identical")


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def screen(model, frames, stride=24):
    indices = sorted(set(range(0, len(frames), stride))|{len(frames)-1})
    best, best_chain, worst = float("inf"), float("inf"), None
    chain_pairs = [i for i, (a, b) in enumerate(model.pairs)
                   if model.names[a].startswith("chain_") or model.names[b].startswith("chain_")]
    for index in indices:
        distances = model.distances(frames[index])
        k = int(np.argmin(distances))
        a, b = model.pairs[k]
        value = float(distances[k])
        if value < best:
            best, worst = value, dict(source_frame=index, pair=[model.names[a], model.names[b]])
        best_chain = min(best_chain, float(distances[chain_pairs].min()))
        if value <= .0001:
            return dict(passed=False, minimum_sampled_clearance_m=best,
                minimum_sampled_chain_clearance_m=best_chain, worst=worst,
                scope="A failing sample rejects this exact path; passing samples alone never qualify a variant")
    return dict(passed=True, minimum_sampled_clearance_m=best,
        minimum_sampled_chain_clearance_m=best_chain, worst=worst,
        scope="Coarse screen only; requires a complete continuous certificate")


def evaluate(candidate, source, output):
    source, output = Path(source), Path(output)
    folder = output/"variants"/candidate["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = json.loads((source/"geometry_evidence/body_poses.json").read_text())
    motion = json.loads((source/"robot_motion.json").read_text())
    template = variant_template(path["template"], candidate)
    model = IndependentWitness(template, path["scale"])
    verify_immutable_geometry(path["template"], template, path["centers"], model)
    commands_before = command_hash(motion)
    write_json(folder/"template.json", template)
    sampled = screen(model, path["frames"])
    write_json(folder/"screen.json", sampled)
    row = dict(candidate, passed=False, status="screen_rejected", command_sha256=commands_before,
        geometry_frames_sha256=hashlib.sha256(json.dumps(path["frames"], sort_keys=True).encode()).hexdigest(),
        grasp_geometry_unchanged=True, body_origins_unchanged_to_m=1e-12,
        screen=sampled, physics_steps=0, dynamic_execution_verified=False)
    if sampled["passed"]:
        geometry = model.certify(path["frames"])
        write_json(folder/"geometric_certificate.json", geometry)
        row.update(status="continuous_geometry_rejected", geometric_path_passed=geometry["passed"],
            minimum_continuous_clearance_lower_bound_m=geometry["minimum_clearance_lower_bound_m"],
            final_separation_m=geometry["goal"]["separation_m"], geometry_failures=geometry["failures"])
        if geometry["passed"]:
            cfg = OmegaConf.load(source/"config.yaml")
            clearance = RobotClearance(cfg.robot_control, template, path["scale"])
            violations = []
            for i, frame in enumerate(motion["frames"]):
                violations.extend(dict(frame=i, **v) for v in clearance.violations(frame["qpos"], frame["bodies"]))
            robot = dict(passed=not violations, frames=len(motion["frames"]), sampling_hz=motion["fps"],
                robot_self_tolerance_m=.0001, robot_puzzle_tolerance_m=.0003, table_tolerance_m=.001,
                violations=violations, scope="Sampled robot self, puzzle and table overlap; no force execution guarantee")
            write_json(folder/"robot_clearance.json", robot)
            controls = {}
            for sign, name in ((1, "positive_x"), (-1, "negative_x")):
                end = deepcopy(path["frames"][0])
                end["target_ring"]["pos"][0] += sign*.35
                control = model.certify([path["frames"][0], end])
                controls[name] = control
            write_json(folder/"straight_pull_controls.json", controls)
            nontrivial = all(not c["passed"] and c["initial_geometry_passed"]
                and c["initial_matches_template"] and c["goal"]["separated"] for c in controls.values())
            row.update(sampled_robot_clearance_passed=robot["passed"],
                straight_pull_both_directions_blocked=nontrivial,
                passed=robot["passed"] and nontrivial,
                status="qualified_kinematic_variant" if robot["passed"] and nontrivial else "robot_or_straight_control_rejected")
    if commands_before != command_hash(motion):
        raise RuntimeError("Variant evaluation modified the frozen commands")
    write_json(folder/"compatibility.json", row)
    return row


def run(source=SOURCE, output=OUTPUT, spec=SPEC, workers=3):
    source, output = Path(source), Path(output)
    trace = export_trace(source, output)
    specification = json.loads(Path(spec).read_text())
    path = json.loads((source/"geometry_evidence/body_poses.json").read_text())
    certificate = json.loads((source/"geometry_evidence/certificate.json").read_text())
    if (not certificate["passed"] or certificate["frames_sha256"] !=
            hashlib.sha256(json.dumps(path["frames"], sort_keys=True).encode()).hexdigest()
            or certificate["template_sha256"] != hashlib.sha256(json.dumps(path["template"], sort_keys=True).encode()).hexdigest()
            or path["scale"] != certificate["scale"] or path["scale"] != specification["scene_scale"]):
        raise ValueError("The archived geometry does not match its certificate or the variant scale")
    if specification["base_template"] != path["template"]["template_id"]:
        raise ValueError("Variant family targets a different base template")
    # Preserve the exact source material locally; variants reference these bytes.
    for name in ("body_poses.json", "certificate.json", "template.json"):
        target = output/"source_geometry"/name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source/"geometry_evidence"/name, target)
    shutil.copyfile(source/"robot_motion.json", output/"source_robot_motion.json")
    shutil.copyfile(source/"config.yaml", output/"source_config.yaml")
    shutil.copyfile(spec, output/"variant_spec.json")
    rows = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        pending = {pool.submit(evaluate, candidate, str(source), str(output)): candidate["id"]
                   for candidate in specification["candidates"]}
        for future in as_completed(pending):
            row = future.result()
            if row["command_sha256"] != trace["command_sha256"]:
                raise ValueError("Candidate used a different robot trace")
            rows.append(row)
            print(f"Variant {row['id']}: {row['status']}", flush=True)
    order = {c["id"]: i for i, c in enumerate(specification["candidates"])}
    rows.sort(key=lambda r: order[r["id"]])
    report = dict(scope="Exact joint/time trace reuse for discrete nominal chain geometry variants",
        source_archive=str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        command_sha256=trace["command_sha256"], source_body_motion_unchanged=True,
        candidates=len(rows), qualified=sum(r["passed"] for r in rows), results=rows,
        physical_execution_verified=False, interval_or_cartesian_product_guaranteed=False,
        nontriviality_scope="Initial +/-X straight pulls fail; five-body connectivity and the full folding/handover sequence remain; not a proof that every simpler solution fails")
    write_json(output/"variants_report.json", report)
    from .trace_review import write_review
    write_review(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    report = run(args.source, args.output, args.spec, args.workers)
    print(f"Qualified {report['qualified']}/{report['candidates']}; {args.output/'index.html'}")


if __name__ == "__main__":
    main()
