"""Audit the delivered family library and retain reproducible random examples."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from shapely.geometry import Polygon

from .family_pipeline import qualify_physics
from .family_variants import TITLES, build
from .geometry import ASSET_ROOT
from .inverse_variants import save, sha
from .long_stroke import SEED
from .long_stroke_archive import update_text
from .robot_motion import ROOT

PREFIX = "2026-09-17_families_v1"


def verify_manifest(meta):
    manifest = json.loads((meta / "archive_manifest.json").read_text())
    for name, digest in manifest["metadata_sha256"].items():
        if sha(meta / name) != digest:
            raise ValueError(f"Archive metadata changed: {meta / name}")
    for video in manifest["videos"].values():
        path = meta / video["path"]
        if path.is_symlink() or sha(path) != video["sha256"] or not video["decoded"]:
            raise ValueError(f"Invalid archived video: {path}")
    return manifest


def reproducibility(folder, cache):
    proposal = json.loads((folder / "proposal.json").read_text())
    with TemporaryDirectory(prefix="keyhole_family_repro_") as temporary:
        root = Path(temporary)
        shutil.copytree(cache, root / "family_cache")
        seed = root / "source"; seed.mkdir()
        for name in ("geometry.json", "proposal.json", "ik_proposal.json", "certificate.json"):
            shutil.copy2(folder / ("family_" + name), seed / name)
        copy = build(proposal["appearance_style"], root, folder.name, proposal["random_seed"], seed)
        expected, observed = sha(folder / "geometry.json"), sha(copy / "geometry.json")
        if expected != observed:
            raise ValueError("Same seed and family source did not reproduce identical geometry")
    return dict(passed=True, instance_id=folder.name, geometry_sha256=expected,
                check="independent rebuild in a temporary directory; identical complete geometry JSON hash")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", type=Path, default=ROOT / "runs/environment-solvability/cast_keyhole/families_random_validation_v1")
    a = p.parse_args()
    meta_root = ROOT / "runs/demo_metadata"
    target = meta_root / "cast_keyhole" / (PREFIX + "_generator")
    if target.exists():
        raise ValueError("Generator archive already exists")
    representatives = {}
    for style in TITLES:
        meta = meta_root / "cast_keyhole" / (PREFIX + "_" + style)
        manifest = verify_manifest(meta)
        proof = json.loads((meta / "evidence/qualification.json").read_text())
        if not proof["passed"] or proof["status"] != "physics_verified":
            raise ValueError("Unqualified representative")
        representatives[style] = dict(archive=os.path.relpath(meta, target),
            geometry_sha256=proof["geometry_sha256"], duration_s=manifest["duration_s"],
            physics=proof["physics"])
        record = json.loads((meta / "evidence/geometry.json").read_text())
        outline = Polygon(record["rings_mm"]["gold"][0])
        volume = outline.area * record["thickness_mm"] * (record["scale"] * .001) ** 3
        representatives[style]["current_geometry_measurements"] = dict(
            gold_planar_area_template_mm2=outline.area, gold_volume_m3=volume,
            gold_mass_kg=volume * record["density_kg_m3"],
            gold_bounds_scene_mm=[v * record["scale"] for v in outline.bounds],
            inherited_area_fields_in_geometry_json="lineage measurements from the family inference; current instance uses measurements here and its exported geometry_report")
    comparison = meta_root / "cast_keyhole" / (PREFIX + "_comparison")
    verify_manifest(comparison)
    samples = json.loads((a.samples / "samples.json").read_text())
    if not samples["passed"] or {s["family"] for s in samples["accepted"]} != {"F1", "F2", "F3"}:
        raise ValueError("A validated continuously varied example for every family is required")
    random_checks = []
    for sample in samples["accepted"]:
        folder = a.samples / sample["instance_id"]
        q = qualify_physics(folder)
        if sha(folder / "qualification.json") != sample["qualification_sha256"]:
            raise ValueError("Random sample qualification changed")
        random_checks.append(dict(family=q["family"], ik_parameters=sample["ik_parameters"],
             reproducibility=reproducibility(folder, a.samples / "family_cache")))
    target.mkdir(parents=True)
    shutil.copy2(a.samples / "samples.json", target / "samples.json")
    for sample in samples["accepted"]:
        folder = a.samples / sample["instance_id"]
        shutil.copytree(folder, target / "validated_samples" / folder.name,
                        ignore=shutil.ignore_patterns("pipeline_logs"))
    sources = target / "sources"; sources.mkdir()
    names = ("family_variants", "family_pipeline", "family_variants_archive", "family_comparison", "family_suite",
             "long_stroke", "eccentric_window", "turnback", "turnback_archive", "inverse_variants", "variant_assets",
             "robot_execution", "physical_audit", "physical_recording", "aloha_demo", "robot_motion", "scene",
             "geometry", "solution", "collision", "route_probe", "trajectory_probe", "long_stroke_archive")
    for name in names:
        shutil.copy2(Path(__file__).with_name(name + ".py"), sources / (name + ".py"))
    shutil.copy2(SEED, target / "original_solved_robot_ik.json")
    for name in ("template.json", "baseline_solution.json", "sources.json"):
        shutil.copy2(ASSET_ROOT / name, target / ("original_" + name))
    space = dict(schema_version=1, family_policy="explicit --family or balanced F1/F2/F3 cycle; rejected samples do not advance the cycle",
        representative_styles=TITLES,
        family_ik_search_domains=dict(F1=dict(pass_length_factor=[1.10, 1.35]),
            F2=dict(offset_template_mm=[1.5, 3.], relation="vertical offset = horizontal offset / 2; scene scale 3"),
            F3=dict(turn_angle_deg=[20., 30.], forward_y_template_mm=[-20., -16.], return_y_template_mm=-9.5)),
        appearance_domains=dict(width_scale=[.96, 1.04], height_scale=[.96, 1.04], lateral_shift_template_mm=[-.5, .5]),
        material_policy="one shared palette bank independent of family; geometry density and contact coefficients remain fixed",
        feasibility="search domains only; every draw must independently pass geometry, robot clearance, mechanism controls, and both physics time steps",
        qualification_files=["certificate.json", "robot_motion.json", "robot_physics/audit.json", "robot_physics_half/audit.json", "qualification.json"],
        sample_command=[".venv-gs121-nyx/bin/python", "-m", "topogym.tasks.cast_keyhole.family_pipeline", "sample", "--root",
                        "runs/environment-solvability/cast_keyhole/my_random_batch", "--seed", "42", "--count", "3", "--vary-ik"],
        scope=dict(two_rigid_pieces=True, silver_geometry_fixed=True, pregrasp_start=True, assisted_weld_grasp=True,
                   complete_extraction=True, held_at_end=True, friction_only_grasp_verified=False, unique_solution_proven=False))
    save(target / "variant_space.json", space)
    visual = dict(passed=True, scope="human review of nine representative silhouettes and their three same-scale gray projections",
                  geometry_sha256={k: v["geometry_sha256"] for k, v in representatives.items()},
                  features=dict(F1="long rails; round / flat / faceted crown", F2="asymmetric upper head; curved / angular / tall lobe",
                                F3="lower turn chamber; rounded / square / two-lobed exterior"),
                  universal_random_sample_visual_uniqueness_proven=False)
    save(target / "visual_review.json", visual)
    manifest = dict(passed=True, representative_count=len(representatives), random_validated_count=len(random_checks),
         physical_episodes=2 * (len(representatives) + len(random_checks)), representatives=representatives,
         random_examples=random_checks, rejected_random_attempts=len(samples["rejected"]),
         comparison_archive=os.path.relpath(comparison, target),
         full_cartesian_parameter_space_verified=False,
         metadata_sha256={str(path.relative_to(target)): sha(path) for path in sorted(target.rglob("*")) if path.is_file()})
    save(target / "generator_manifest.json", manifest)
    relative = str(target.relative_to(meta_root))
    def catalog(text):
        data = json.loads(text)
        data.setdefault("generators", []).append(dict(task_id="cast_keyhole", directory=relative,
            manifest=relative + "/generator_manifest.json", verified_representatives=9, verified_random_examples=len(random_checks)))
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    update_text(meta_root / "catalog.json", catalog)
    card = f'<section><h2>Cast Keyhole · family 随机生成器</h2><p>九款代表与三个连续随机样本通过验证；包含两种时间步和同种子几何复现检查。</p><p><a href="{relative}/variant_space.json">参数空间与运行命令</a> · <a href="{relative}/generator_manifest.json">验证清单</a></p></section>'
    update_text(meta_root / "index.html", lambda text: text.replace("<section><h2>本次暂未收录", card + "<section><h2>本次暂未收录"))
    row = f'| Cast Keyhole · family 随机生成器 | [参数与命令]({relative}/variant_space.json) · [验证]({relative}/generator_manifest.json) | — | 九款代表与三个连续随机样本；固定 seed 可重建相同几何。 |\n'
    update_text(meta_root / "README.md", lambda text: text.replace("\n\n保留全部既有 MP4", "\n" + row + "\n保留全部既有 MP4"))
    print(json.dumps({k: v for k, v in manifest.items() if k != "metadata_sha256"}, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
