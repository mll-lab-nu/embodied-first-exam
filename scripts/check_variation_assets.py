#!/usr/bin/env python3
"""Audit canonical settings without constructing physics or claiming task success.

Run from an installed checkout or pass --package-root for an isolated wheel.
Every output includes source/package fingerprints and per-setting failures.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import xml.etree.ElementTree as ET


def check_setting_geometry(task, spec, folder):
    """Check authored structural differences in the generated assets."""
    level, name = task.difficulty, task.task_id
    if level is None:
        return {}
    if name == "rope_threading":
        data = json.loads((folder/"layout.json").read_text())
        ids = ["R1", "R2"] if level == "easy" else ["R1", "R2", "R3"]
        diameter = .100 if level == "hard" else .138
        assert data["selected_ring_ids"] == ids
        assert data["target_material_order"] == ["R1-", "R2+", "R3+"][:len(ids)]
        assert not data["initial_crossings"] and data["geometry_verified"]
        assert data["minimum_fixture_gap_lower_bound_m"] > 0
        assert all(abs(d-diameter) < 1e-12 for d in data["ring_aperture_diameters_m"].values())
        assert {e.name for e in spec.entities} == {"rope"} | {
            ring+suffix for ring in ids for suffix in ("", "_stand", "_base")}
        return dict(rings=len(ids), aperture_diameter_m=diameter,
                    target_material_order=data["target_material_order"],
                    initial_fixture_clearance_lower_bound_m=data["minimum_fixture_gap_lower_bound_m"])
    if name == "fiber_bundling":
        data = json.loads((folder/"anchored_centerlines.json").read_text())
        count = {"easy": 4, "medium": 8, "hard": 16}[level]
        assert len(data["fibers_m"]) == count
        return dict(strands=count)
    if name == "cast_coil" and level != "easy":
        data = json.loads((folder/"template.json").read_text())["inverse_design"]
        parameter = "axial_advance_mm" if level == "medium" else "step_height_mm"
        assert data["parameters"][parameter] == 9.
        assert data["kind"] == task.family_id
        return {parameter: 9.}
    if name == "cast_keyhole":
        data = json.loads((folder/"inverse_geometry.json").read_text())
        assert data["id"] == task.family_id
        report = json.loads((folder/"geometry_report.json").read_text())
        assert report["passed"] and report["no_initial_collision"]
        return dict(family=data["id"], initial_clearance_m=report["minimum_initial_surface_clearance_m"])
    if name == "lock_picking":
        count = {"easy": 2, "medium": 3, "hard": 4}[level]
        assert len(task.layout.slots[0]) == count
        assert len([e for e in spec.entities if e.name.startswith("lock_frame_")]) == 3
        return dict(first_disc_slots=count, physical_rotor_frames=3)
    if name == "interlocked_claws" and level != "hard":
        report = json.loads((folder/"family/model.json").read_text())
        assert report["family"] == task.geometry_family
        assert len(report["parts"]) == 2
        return dict(family=report["family"], boxes=[len(p["boxes"]) for p in report["parts"]])
    if name == "buzz_wire_3d":
        from topogym.assets.variation_resources import read_json
        report = json.loads((folder/"geometry_report.json").read_text())
        source = read_json(task.layout_resource)
        assert report["layout"]["authored_controls_m"] == source["authored_controls_m"]
        assert report["layout"]["supported_endpoints"]
        return dict(authored_controls=len(source["authored_controls_m"]), supported_endpoints=True)
    if name == "knot_untying":
        assert task.layout.family == task.family_id
        if level == "medium":
            assert task.layout.planar_scale_m == .0325 and task.layout.crossing_height_m == .010
        return dict(family=task.layout.family, planar_scale_m=task.layout.planar_scale_m)
    if name == "blanket_flatten":
        if level == "medium":
            assert task.layout.fold_count == 3 and task.layout.roll_fold_count == 5
        return dict(folds=task.layout.fold_count, roll_folds=task.layout.roll_fold_count)
    if name == "orbits":
        count = {"easy": 2, "medium": 3, "hard": 4}[level]
        assert task.layout.ring_count == count and task.layout.template_scale == .85
        assert task.layout.handle_x_m == .41 and len(spec.attachments) == 2
        assert spec.metadata["geometry_report"]["passed"]
        assert abs(spec.metadata["geometry_report"]["cord_length_m"] - .80) < .001
        assert len([e for e in spec.entities if e.name.startswith("ring_")]) == count
        assert len([e for e in spec.entities if e.name.startswith("post_")]) == count+1
        return dict(rings=count, fixture_scale=.85, handle_x_m=.41,
                    cord_length_m=spec.metadata["geometry_report"]["cord_length_m"])
    if name == "hedgehog_in_cage" and level != "easy":
        count = 10 if level == "medium" else 6
        assert spec.metadata["asset_report"]["spike_count"] == count
        return dict(spikes=count)
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--tasks", nargs="*")
    parser.add_argument("--repeat", action="store_true", help="Rebuild in another folder and compare output hashes")
    args = parser.parse_args()
    sys.path.insert(0, str(args.package_root.resolve()))
    import topogym
    from topogym.config.registry import task_catalog, variation_catalog, task_definition
    from topogym.assets.library import describe_build
    root = Path(topogym.__file__).parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fingerprints = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(root.rglob("*")) if p.is_file() and p.suffix in
                    (".py", ".json", ".yaml", ".zip", ".obj", ".glb")}
    (output/"source_identity.json").write_text(json.dumps(fingerprints, indent=2)+"\n")
    report = dict(scope="asset declarations only; no physics or robot success qualification",
                  package_root=str(root), seed=args.seed, results=[])

    def save():
        (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")

    save()
    for task in task_catalog():
        if args.tasks and task["task_id"] not in args.tasks:
            continue
        for row in variation_catalog(task["task_id"]):
            item = dict(task_id=task["task_id"], variation_id=row["variation_id"],
                        difficulty=row["difficulty"], catalog_status=row["status"])
            report["results"].append(item)
            start = time.monotonic()
            if row["status"] != "integrated":
                item.update(status="unavailable", reason=row["reason"])
                save()
                continue
            try:
                cls = task_definition(task["task_id"], row["variation_id"])
                obj = cls(seed=args.seed)
                asset_root = output/row["variation_id"]
                spec = obj.declare(asset_root, .9196429)
                names = [e.name for e in spec.entities]
                assert names and len(names) == len(set(names)), names
                for entity in spec.entities:
                    if entity.asset_path:
                        path = Path(entity.asset_path).resolve()
                        assert path.is_file() and path.is_relative_to(asset_root)
                    if entity.volume_path:
                        assert Path(entity.volume_path).is_file()
                for path in asset_root.rglob("*.urdf"):
                    for node in ET.parse(path).iter("mesh"):
                        name = node.attrib["filename"]
                        assert not Path(name).is_absolute(), (path, name)
                        target = (path.parent/name).resolve()
                        assert target.is_file() and target.is_relative_to(asset_root), target
                build = describe_build(obj.task_id, asset_root, obj.config, obj.seed)
                item.update(status="passed", instance_id=obj.instance_id, effective_parameters=obj.config,
                            entities=names, asset_sha256=dict(build.sha256),
                            structural_checks=check_setting_geometry(obj, spec, asset_root))
                if args.repeat:
                    other = cls(seed=args.seed)
                    second = output/(row["variation_id"]+"_repeat")
                    other.declare(second, .9196429)
                    comparison = describe_build(other.task_id, second, other.config, other.seed)
                    assert other.instance_id == obj.instance_id
                    differences = sorted(k for k in set(build.sha256) | set(comparison.sha256)
                                         if build.sha256.get(k) != comparison.sha256.get(k))
                    item["repeat_differences"] = differences
                    assert not differences, differences
                for module_name, module in tuple(sys.modules.items()):
                    if module_name.startswith("topogym.") and getattr(module, "__file__", None):
                        assert Path(module.__file__).resolve().is_relative_to(root.resolve()), module.__file__
            except Exception as exc:
                item.update(status="failed", error=str(exc), traceback=traceback.format_exc())
            item["elapsed_s"] = time.monotonic()-start
            print(row["variation_id"], item["status"], item.get("error", "")[:150], flush=True)
            save()
    counts = {state: sum(x["status"] == state for x in report["results"])
              for state in ("passed", "failed", "unavailable")}
    report["counts"] = counts
    save()
    print(counts)
    return int(bool(counts["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
