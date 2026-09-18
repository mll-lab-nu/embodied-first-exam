"""Check that the exported inverse scene is exactly the certified similarity."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .ik_trace import command_hash
from .independent_motion import IndependentWitness, interpolate
from .robot_motion import balanced_frame
from .trace_scene_variants import legacy_hash


def verify(folder):
    folder = Path(folder)
    motion = json.loads((folder/"robot_motion.json").read_text())
    trace = json.loads((folder/"ik_trace.json").read_text())
    proof = json.loads((folder/"geometry_certificate.json").read_text())
    reference = json.loads((folder/"geometry_evidence/body_poses.json").read_text())
    certificate = json.loads((folder/"geometry_evidence/source_certificate.json").read_text())
    template = json.loads((folder/"template.json").read_text())
    transforms = json.loads((folder/"common_transforms.json").read_text())
    if not proof["passed"] or not certificate["passed"]:
        raise ValueError("Missing positive geometric evidence")
    if legacy_hash(reference["frames"]) != certificate["frames_sha256"] or legacy_hash(reference["template"]) != certificate["template_sha256"]:
        raise ValueError("Referenced geometry differs from its certificate")
    if legacy_hash(template) != proof["template_sha256"] or legacy_hash(motion["frames"]) != proof["robot_frames_sha256"]:
        raise ValueError("Exported scene or motion differs from the proof")
    if command_hash(motion) != trace["command_sha256"] or [f["qpos"] for f in motion["frames"]] != [f["qpos"] for f in trace["frames"]]:
        raise ValueError("IK trace and scene replay contain different commands")
    scale = proof["scale_ratio"]
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Scale must be positive")
    expected = certificate["minimum_clearance_lower_bound_m"]*scale
    if abs(proof["minimum_clearance_lower_bound_m"]-expected) > 1e-12:
        raise ValueError("Incorrect inherited clearance bound")
    source = IndependentWitness(reference["template"], reference["scale"])
    target = IndependentWitness(template, reference["scale"]*scale)
    error = max(float(np.abs(a.vertices*scale-b.vertices).max()) for a, b in zip(source.meshes, target.meshes))
    if error > 1e-10:
        raise ValueError("Geometry is not the claimed uniform similarity")
    origin = np.asarray(proof["common_transform"]["seed_center_m"])
    if len(transforms) != len(motion["frames"]):
        raise ValueError("Missing per-frame common transforms")
    maximum = 0.
    last_index = -1.
    for frame, common in zip(motion["frames"], transforms):
        index = common["source_index"]
        if index < last_index or index != frame["source_index"]:
            raise ValueError("Invalid source witness time map")
        last_index = index
        k = min(int(index), len(reference["frames"])-2)
        base = balanced_frame(interpolate(reference["frames"][k], reference["frames"][k+1], index-k), origin)
        rotation = Rotation.from_quat(common["rotation_xyzw"])
        for name, body in base.items():
            p = common["center_m"]+rotation.apply(scale*(np.asarray(body["pos"])-origin))
            r = rotation*Rotation.from_quat(body["quat"])
            actual = frame["bodies"][name]
            maximum = max(maximum, float(np.linalg.norm(p-actual["pos"])),
                float((r.inv()*Rotation.from_quat(actual["quat"])).magnitude()))
    if maximum > 1e-9:
        raise ValueError("Exported poses do not follow the certified transform")
    if not target.goal(motion["frames"][-1]["bodies"])["separated"]:
        raise ValueError("Ring is not fully separated")
    return dict(passed=True, frames=len(transforms), maximum_pose_or_rotation_reconstruction_error=maximum,
        maximum_collision_cover_similarity_error_m=error, command_sha256=trace["command_sha256"],
        minimum_clearance_lower_bound_m=expected,
        scope="Checks the common-transform transfer and data correspondence; retains the source numerical certificate's assumptions",
        physical_execution_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    report = verify(args.folder)
    (args.folder/"verification.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
