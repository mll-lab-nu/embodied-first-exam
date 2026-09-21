"""Compare measured IK-family routes after removing scene pose, size and timing."""
import argparse
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .robot_motion import Kinematics
from .family_space import route_distance
from .variant_pipeline import qualify, corridor_frames


def audit(folders):
    routes, reports = {}, {}
    for folder in map(Path, folders):
        proof = qualify(folder, require_family_release=False)
        if not proof["accepted"]:
            raise ValueError(f"Unqualified exact instance: {folder}")
        instance = json.loads((folder/"instance.json").read_text())
        p = instance["parameters"]
        family = p["family_id"]
        if family in routes:
            raise ValueError("Need one representative per family")
        kin = Kinematics(OmegaConf.load(folder/"config.yaml").robot_control)
        points = []
        frames = [json.loads(line) for line in (folder/"physical_states.jsonl").read_text().splitlines()]
        report = json.loads((folder/"result.json").read_text())
        for row in corridor_frames(frames, report, family):
            kin.q = np.asarray(row["qpos"])
            points.append(kin.pose("left")[0])
        canonical = Rotation.from_euler("z", -p["yaw_deg"], degrees=True).apply(
            np.asarray(points)-[0, .05, .2]-np.asarray(p["translation_m"]))/p["scale_ratio"]
        routes[family], reports[family] = canonical, proof
    if set(routes) != {"F1", "F2", "F3"}:
        raise ValueError("Require all three physical families")
    pairs = []
    names = sorted(routes)
    for i, a in enumerate(names):
        for b in names[i+1:]:
            metric = route_distance(routes[a], routes[b], 50.)
            pairs.append(dict(families=[a, b], **metric, passed=metric["directed_p95_max_mm"] >= 50.
                and metric["maximum_directed_fraction_above_threshold"] >= .2))
    return dict(passed=all(p["passed"] for p in pairs), pairs=pairs, instances=reports,
        normalization="Designed corridor up to its waypoint; remove initial pose and uniform scale; same hand, equal arc length (256 samples), no timing difference credit",
        actual_video_review="required separately", routes_m={k: v.tolist() for k, v in routes.items()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folders", type=Path, nargs=3)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.folders)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(passed=result["passed"], pairs=result["pairs"]), indent=2))


if __name__ == "__main__":
    main()
