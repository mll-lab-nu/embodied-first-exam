"""Build/freeze the versioned, fixed IK mechanisms consumed by seed generation.

This design-time command is not called per episode. Runtime generation only
reads the frozen asset catalog; it never searches for another macro mechanism.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .variants import ASSETS, VERSION, file_sha, save

FILES = ("proposal.json", "ik_proposal.json", "geometry.json", "certificate.json", "robot_motion.json")


def design(family, output):
    from . import eccentric_window, long_stroke
    from .inverse_variants import certify_variant, check_robot
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    if family == "F1":
        data, seed = long_stroke.propose(folder, 1.6)
        data["fill_stock_pockets"] = True
        infer = long_stroke.infer
    elif family == "F2":
        data, seed = eccentric_window.propose(folder, 8.)
        data["discard_small_sweep_offcuts"] = True
        infer = eccentric_window.infer
    else:
        raise ValueError("F3 retains the previously qualified turnback core")
    save(folder / "proposal.json", data)
    trace = long_stroke.plan(data, seed, folder)
    record, meshes, cells = infer(data, trace, folder)
    proof = certify_variant(data, trace, record, meshes, cells, folder)
    if not all(n["collision_found"] for n in proof["negative_controls"].values()):
        raise ValueError("The mechanism lost a required obstacle")
    check_robot(trace, record, cells, folder)


def freeze(sources, baseline, output=ASSETS):
    from .variant_assets import require_variant
    if set(sources) != {"F1", "F2", "F3"}:
        raise ValueError("All three fixed cores are required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    entries = {}
    for family, path in sources.items():
        path = Path(path)
        motion = json.loads((path / "robot_motion.json").read_text())
        _, proof = require_variant(path / "geometry.json", motion)
        if not all(n["collision_found"] for n in proof["negative_controls"].values()):
            raise ValueError("A core has lost its mechanism controls")
        if json.loads((path / "proposal.json").read_text())["source_ik_sha256"] != file_sha(baseline):
            raise ValueError("Core lineage does not match baseline IK")
        target = output / family
        target.mkdir()
        for name in FILES:
            shutil.copy2(path / name, target / name)
        entries[family] = dict(directory=family, geometry_sha256=file_sha(target / "geometry.json"),
            motion_sha256=file_sha(target / "robot_motion.json"), styles=["A", "B", "C"],
            motion_feature={"F1": "50.88 mm longitudinal tooth passage",
                            "F2": "24 mm lateral and 12 mm upward cap detour",
                            "F3": "25 degree chamber turn followed by 25.5 mm return"}[family])
    shutil.copy2(baseline, output / "baseline_robot_motion.json")
    hashes = {str(p.relative_to(output)): file_sha(p) for p in sorted(output.rglob("*.json"))}
    save(output / "catalog.json", dict(version=VERSION, families=entries, files=hashes,
        macro_design_frozen=True, qualification_scope="geometry_and_robot_checked_cores",
        all_parameter_combinations_physics_verified=False,
        source_directories={k: str(Path(v).resolve()) for k, v in sources.items()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=("F1", "F2"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    design(args.family, args.output)


if __name__ == "__main__":
    main()
