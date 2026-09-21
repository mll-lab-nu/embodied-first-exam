"""Promote the three verified cages into an immutable generator input library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf
import trimesh

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "assets/tasks/hedgehog_in_cage/seed_families_v1"
FAMILIES = ("oblique_gate", "staggered_gates", "helical_guide")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def prepare(output=OUTPUT):
    output = Path(output)
    if output.exists():
        raise ValueError("Preserve the existing versioned prototype library")
    prepared = []
    for i, family in enumerate(FAMILIES):
        parent = ROOT / f"runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_{chr(97+i)}_{family}_v1"
        manifest = json.loads((parent / "archive_manifest.json").read_text())
        for relative, digest in manifest["metadata_sha256"].items():
            if sha(parent / relative) != digest:
                raise ValueError(f"Changed parent evidence: {parent / relative}")
        proof = json.loads((parent / "certificate.json").read_text())
        if not proof["passed"] or not all(c["collision_found"] for c in proof["finite_controls"].values()):
            raise ValueError("A fixed family needs both a solution and mechanism controls")
        for sub in ("physics", "physics_substeps20"):
            physical = json.loads((parent / sub / "report.json").read_text())
            audit = json.loads((parent / sub / "audit.json").read_text())
            if not all((physical["passed"], physical["complete"], physical["grasp_released"], audit["passed"])):
                raise ValueError("Incomplete parent physics")
        prepared.append((family, parent, proof, manifest))
    output.mkdir(parents=True)
    rows = []
    for family, parent, proof, manifest in prepared:
        folder = output / family
        folder.mkdir()
        shutil.copytree(parent / "assets", folder / "assets")
        for old, new in (("ik_before_geometry.json", "motion.json"), ("certificate.json", "certificate.json"),
                         ("robot_audit.json", "robot_audit.json"), ("motion_proposal.json", "motion_proposal.json")):
            shutil.copy2(parent / old, folder / new)
        cfg = OmegaConf.to_container(OmegaConf.load(parent / "recording/config.yaml"), resolve=True)
        cfg["run"].update(output=".", viewer=False, record_video=False, save_stills=False)
        cfg["env"]["genesis"].update(backend="cpu", precision="64")
        cfg["env"]["renderer"]["type"] = "rasterizer"
        save(folder / "scene_config.json", cfg)
        grasp = json.loads((parent / "provenance/seed/robot_escape_plan.json").read_text())["selected"]
        save(folder / "grasp.json", {k: grasp[k] for k in ("hand_position_in_ball", "hand_quaternion_in_ball_xyzw",
                                                          "grip_point_in_ball", "pad_offset_in_hand")})
        cage = trimesh.load(folder / "assets/cage.obj", force="mesh")
        motion = json.loads((folder / "motion.json").read_text())
        descriptor = dict(family_id=family, prototype_id=f"hedgehog_{family}_fixed_v1",
            cage_bounds_m=cage.bounds.tolist(), cage_bottom_m=float(cage.bounds[0, 2]),
            maximum_cage_radius_m=float(np.linalg.norm(cage.vertices[:, :2], axis=1).max()),
            cage_height_m=float(cage.extents[2]),
            parent_path_clearance_lower_bound_m=proof["continuous_clearance_lower_bound_m"],
            initial_qpos=motion["frames"][0]["qpos"], initial_ball_pose=motion["frames"][0]["ball_pose"],
            source_archive=str(parent.relative_to(ROOT)), source_archive_sha256=sha(parent / "archive_manifest.json"),
            parent_physically_verified=True, fixed_grasp="S2", spike_count=10)
        save(folder / "prototype.json", descriptor)
        evidence = folder / "parent_evidence"
        evidence.mkdir()
        for sub in ("physics", "physics_substeps20"):
            for name in ("report.json", "audit.json"):
                shutil.copy2(parent / sub / name, evidence / f"{sub}_{name}")
        save(evidence / "provenance.json", dict(source_archive=descriptor["source_archive"],
             source_metadata_sha256=manifest["metadata_sha256"],
             scope="Immutable parent evidence only; random descendants require their own qualification."))
        hashes = {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}
        save(folder / "prototype_manifest.json", dict(schema_version=1, family_id=family, files_sha256=hashes))
        rows.append(dict(family_id=family, directory=family, prototype_id=descriptor["prototype_id"],
                         manifest_sha256=sha(folder / "prototype_manifest.json")))
    save(output / "catalog.json", dict(schema_version=1, library_version="hedgehog_fixed_families_v1", families=rows))
    print(json.dumps(dict(passed=True, output=str(output), families=FAMILIES)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    prepare(parser.parse_args().output)
