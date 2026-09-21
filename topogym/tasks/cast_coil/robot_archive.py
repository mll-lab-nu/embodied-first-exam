"""Validate and independently archive a complete assisted physical Coil run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.utils.demo_paths import demo_video_root

from .geometry import CoilAssembly, load_template
from .inverse_design import TITLES, variant_route
from .appearance import TITLES as APPEARANCE_TITLES
from .solvability import exported_boxes_match

ROOT = Path(__file__).resolve().parents[3]
CAMERAS = ("cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist", "front_oblique")
REQUIRED_PHASES = {
    "close_grippers",
    "hold_grasp",
    "lift",
    "prototype_slide",
    "prototype_quarter_turn",
    "prototype_extract",
    "place_silver",
    "place_gold",
    "release",
    "retreat",
    "settle",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def demo_title(report):
    if report.get("objective") == "assemble":
        family = TITLES.get(report.get("inverse_design_kind"))
        return "Cast Coil · " + (f"{family} · " if family else "") + "ALOHA 双臂完整装配"
    if report.get("appearance_kind"):
        return "Cast Coil · " + APPEARANCE_TITLES[report["appearance_kind"]]
    if report.get("inverse_design_kind"):
        return "Cast Coil · " + TITLES[report["inverse_design_kind"]]
    return "Cast Coil · ALOHA 双臂完整拆解"


def qualify_report(report, *, recording=True):
    """Fail closed on a partial, kinematic, unreleased or unobserved recording."""
    phases = REQUIRED_PHASES
    assembling = report.get("objective") == "assemble"
    if assembling:
        from .assembly_task import required_assembly_phases
        phases = (REQUIRED_PHASES - {"prototype_slide", "prototype_quarter_turn", "prototype_extract", "place_silver", "place_gold"}) | required_assembly_phases(report.get("inverse_design_kind"))
    elif report.get("inverse_design_kind"):
        phases = REQUIRED_PHASES - {
            "prototype_slide",
            "prototype_quarter_turn",
            "prototype_extract",
        }
        phases = phases | {m.name for m in variant_route(report["inverse_design_kind"])}
    required = [
        report.get("success"),
        report.get("complete"),
        report.get("physics_steps", 0) > 0,
        report.get("bilateral_grasp_contact_step", 0) > 0,
        report.get("grasp_assistance_active_at_end") is False,
        report.get("grasp_constraints_remaining") == [],
        report.get("release_evidence", {}).get("after") == [],
        max(report.get("released_body_displacement_during_retreat_m", [1])) < 0.002,
        report.get("final_finger_contact_links") == {"0": [], "1": []},
        report.get("live_object_pose_writes") is False,
        report.get("live_robot_pose_writes") is False,
        report.get("geometry_modified") is False,
        not recording or set(report.get("camera_names", [])) == set(CAMERAS),
        not recording or report.get("video_frames", 0) > 0,
        phases.issubset({p["name"] for p in report.get("phases", [])}),
        (report.get("goal_assembled") is True
         and report.get("final_relative_position_error_m", 1) < .001
         and report.get("final_relative_rotation_error_rad", 1) < .02
         and min(report.get("initial_xy_surface_gap_m", [0])) >= .01)
        if assembling else report.get("final_separation_m", 0) > 0.01,
        report.get("minimum_sampled_sat_gap_m", -1) > 0,
        report.get("maximum_interpiece_penetration_m", 1) < 0.00015,
        report.get("maximum_forbidden_robot_penetration_m", 1) < 0.00015,
        report.get("maximum_cross_arm_penetration_m", 1) < 0.00015,
        max(report.get("final_speed_m_s", [1])) < 0.001,
        max(report.get("final_angular_speed_rad_s", [1])) < 0.02,
    ]
    if not all(required):
        raise ValueError(
            "Recording does not qualify as a complete released physical execution"
        )


def read_trace(folder):
    return [
        json.loads(line)
        for line in (Path(folder) / "states.jsonl").read_text().splitlines()
    ]


def audit(source, reference):
    source, reference = Path(source), Path(reference)
    report = json.loads((source / "result.json").read_text())
    qualify_report(report)
    other = json.loads((reference / "result.json").read_text())
    qualify_report(other, recording=False)
    if (
        not np.isclose(report["dt"] / 2, other["dt"])
        or report["substeps"] != other["substeps"]
        or report.get("precision_bits", 32) != other.get("precision_bits", 32)
        or report.get("backend", "cuda") != other.get("backend", "cuda")
    ):
        raise ValueError("Expected half the timestep with unchanged substep count")
    cfg, cfg_half = (OmegaConf.load(p / "config.yaml") for p in (source, reference))
    for key in ("task", "robot_control"):
        left, right = [
            OmegaConf.to_container(c[key], resolve=True) for c in (cfg, cfg_half)
        ]
        if key == "task":
            left.pop("template_path", None)
            right.pop("template_path", None)
        if left != right:
            raise ValueError(f"Timestep comparison changed {key}")
    assembly = CoilAssembly(load_template(source / "assets/template.json"))
    plan = json.loads((source / "source_plan.json").read_text())
    if plan.get("template", assembly.template) != assembly.template:
        raise ValueError("Planned and executed geometry differ")
    if not all(
        exported_boxes_match(p / "assets", assembly) for p in (source, reference)
    ):
        raise ValueError("Recorded compounds differ from the current geometry")
    rows, half_rows = read_trace(source), read_trace(reference)
    if report.get("objective", "disassemble") != other.get("objective", "disassemble"):
        raise ValueError("Timestep runs target different objectives")
    if report.get("objective") == "assemble":
        from .assembly_task import goal_metrics, xy_surface_gaps
        for trace in (rows, half_rows):
            initial = [(Rotation.from_quat(p["quaternion_xyzw"]), np.asarray(p["origin_m"])) for p in trace[0]["bodies"]]
            if min(xy_surface_gaps(assembly, initial)) < .01:
                raise ValueError("Assembly does not begin separated in both x and y")
            for row in trace:
                if row["time_s"] < trace[-1]["time_s"] - .5:
                    continue
                g, s = row["bodies"]
                if not goal_metrics(np.asarray(g["origin_m"]), Rotation.from_quat(g["quaternion_xyzw"]),
                                    np.asarray(s["origin_m"]), Rotation.from_quat(s["quaternion_xyzw"]))["goal_assembled"]:
                    raise ValueError("Released assembly does not remain aligned in the final observation window")
    render_evidence = None
    if report.get("recording_kind") == "offline_render_of_exact_physical_states":
        raw = json.loads((source / "physics_result.json").read_text())
        qualify_report(raw, recording=False)
        render_evidence = json.loads((source / "render_evidence.json").read_text())
        if (
            sha(source / "physics_result.json")
            != render_evidence["physical_result_sha256"]
        ):
            raise ValueError("Physical source report hash mismatch")
        if sha(source / "render_states.jsonl") != raw.get("render_states_sha256"):
            raise ValueError("Physical snapshots changed after execution")
        if render_evidence.get("physical_states_sha256") != raw["render_states_sha256"]:
            raise ValueError("Renderer used different physical snapshots")
        for key, value in raw.items():
            if (
                key not in {"camera_names", "video_frames", "video_fps"}
                and report.get(key) != value
            ):
                raise ValueError(f"Rendered report changes physical evidence: {key}")
        if (
            not render_evidence.get("no_interpolation")
            or render_evidence.get("render_scene_physics_steps") != 0
            or render_evidence["maximum_qpos_roundtrip_error"] > 1e-9
            or render_evidence["maximum_body_origin_roundtrip_error_m"] > 1e-9
            or render_evidence["maximum_body_rotation_roundtrip_error_rad"] > 1e-9
        ):
            raise ValueError(
                "Renderer did not faithfully restore the recorded physical states"
            )
        recorded = [
            json.loads(s)
            for s in (source / "render_states.jsonl").read_text().splitlines()
        ]
        state_map = {round(r["time_s"], 8): r for r in rows}
        for frame in recorded:
            common = state_map.get(round(frame["time_s"], 8))
            if common and (
                frame["qpos"] != common["qpos"]
                or any(
                    frame["bodies"][i][k] != common["bodies"][i][k]
                    for i in range(2)
                    for k in ("origin_m", "quaternion_xyzw")
                )
            ):
                raise ValueError(
                    "Recorded video frame differs from the independent physics audit trace"
                )
        if len(recorded) != report["video_frames"]:
            raise ValueError("Rendered frame count differs from physical snapshots")
    tail = [r for r in rows if r["time_s"] >= rows[-1]["time_s"] - 0.5]
    if any(r["grasp_assistance_active"] for r in tail) or any(
        r["phase"] != "settle" for r in tail
    ):
        raise ValueError("Missing final unassisted settling window")
    tail_v = max(b["linear_speed_m_s"] for r in tail for b in r["bodies"])
    tail_w = max(b["angular_speed_rad_s"] for r in tail for b in r["bodies"])
    if tail_v >= 0.001 or tail_w >= 0.02:
        raise ValueError("Final half-second is not stable")
    deltas = []
    for a, b in zip(rows[-1]["bodies"], half_rows[-1]["bodies"]):
        delta = float(np.linalg.norm(np.asarray(a["origin_m"]) - b["origin_m"]))
        angle = float(
            (
                Rotation.from_quat(a["quaternion_xyzw"]).inv()
                * Rotation.from_quat(b["quaternion_xyzw"])
            ).magnitude()
        )
        deltas.append(dict(position_m=delta, rotation_rad=angle))
        if delta > 0.0005 or angle > 0.01:
            raise ValueError(f"Final state disagrees across timesteps: {deltas[-1]}")
    videos = {}
    for name in CAMERAS:
        file = source / f"{name}.mp4"
        data = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,avg_frame_rate,nb_read_frames,duration",
                    "-of",
                    "json",
                    str(file),
                ],
                text=True,
            )
        )["streams"][0]
        num, den = map(int, data["avg_frame_rate"].split("/"))
        count, fps = int(data["nb_read_frames"]), num / den
        if count != report["video_frames"] or fps != report["video_fps"]:
            raise ValueError(f"Unsynchronized video: {name}")
        decode = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-threads",
                "2",
                "-i",
                str(file),
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        if decode.returncode or decode.stderr.strip():
            raise ValueError(f"Video decoding failed: {name}: {decode.stderr}")
        videos[name] = dict(
            **data, frames=count, fps=fps, sha256=sha(file), decoded=True
        )
    cameras = [
        json.loads(line)
        for line in (source / "camera_poses.jsonl").read_text().splitlines()
    ]
    if len(cameras) != report["video_frames"] or not all(
        set(r["transforms"]) == set(CAMERAS) for r in cameras
    ):
        raise ValueError("Camera trace does not cover all recorded frames")
    if not np.allclose(
        np.diff([r["time_s"] for r in cameras]), 1 / report["video_fps"], atol=1e-9
    ):
        raise ValueError("Recorded frame timing is inconsistent")
    if render_evidence is not None and any(
        camera["frame"] != frame["frame"]
        or camera["physical_step"] != frame["step"]
        or camera["time_s"] != frame["time_s"]
        or camera["phase"] != frame["phase"]
        for camera, frame in zip(cameras, recorded)
    ):
        raise ValueError("Video camera trace is not linked to the physical frames")
    table_z = float(cfg.env.frames.table_surface.origin[2])
    minimum_table = min(
        float(
            (
                body.visual.vertices
                @ Rotation.from_quat(pose["quaternion_xyzw"]).as_matrix().T
                + pose["origin_m"]
            )[:, 2].min()
            - table_z
        )
        for row in rows
        for body, pose in zip(assembly.bodies, row["bodies"])
    )
    if minimum_table < -0.00015:
        raise ValueError(f"Observed tabletop penetration: {minimum_table}")
    result = dict(
        passed=True,
        classification="physical_execution_with_grasp_assistance",
        geometry_matches=True,
        precision_bits=report.get("precision_bits", 32),
        complete=True,
        final_unassisted_window_s=0.5,
        thresholds=dict(
            final_speed_m_s=0.001,
            final_angular_speed_rad_s=0.02,
            timestep_position_difference_m=0.0005,
            timestep_rotation_difference_rad=0.01,
            minimum_final_separation_m=None if report.get("objective") == "assemble" else .01,
            maximum_assembled_relative_position_error_m=.001 if report.get("objective") == "assemble" else None,
            maximum_assembled_relative_rotation_error_rad=.02 if report.get("objective") == "assemble" else None,
            maximum_non_grasp_contact_penetration_m=0.00015,
            maximum_table_penetration_m=0.00015,
            maximum_released_retreat_displacement_m=0.002,
        ),
        maximum_tail_speed_m_s=tail_v,
        maximum_tail_angular_speed_rad_s=tail_w,
        minimum_sampled_table_clearance_m=minimum_table,
        timestep_comparison=dict(
            passed=True,
            substeps=report["substeps"],
            dt_s=[report["dt"], other["dt"]],
            final_body_deltas=deltas,
            reference_report_sha256=sha(reference / "result.json"),
        ),
        videos=videos,
        source_result_sha256=sha(source / "result.json"),
        render_evidence=render_evidence,
        limitations=[
            "Pregrasp reset; contact-gated grasp assistance, not friction-only grasping.",
            "Authored Coil route; not a verified commercial eight-step tutorial.",
            "Solver contact maxima and sampled realized geometry are separate from the ideal continuous route certificate.",
        ],
    )
    (source / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return report, result


def archive(source, reference, run_id, *, variant_id=None):
    source, reference = Path(source).resolve(), Path(reference).resolve()
    metadata = ROOT / "runs/demo_metadata/cast_coil" / run_id
    if metadata.exists():
        raise FileExistsError("Archive already exists; preserve the validated copy")
    report, validation = audit(source, reference)
    # Keep each resolved structure separate, including generated instances.
    # A caller may give a stable representative ID for the public directory.
    variant = variant_id or report.get("geometry_variant")
    if not variant:
        variant = (
            "baseline_assembly"
            if report.get("objective") == "assemble"
            else "baseline_disassembly"
        )
    elif not variant_id and report.get("objective", "disassemble") != "assemble":
        variant += "_disassembly"
    video_root = demo_video_root(ROOT, "cast_coil", variant)
    targets = {name: video_root / name / f"{run_id}_{name}.mp4" for name in CAMERAS}
    if any(list(target.parent.glob("*.mp4")) for target in targets.values()):
        raise FileExistsError(
            "This variant already has videos; verify and migrate the existing group before replacing it"
        )
    if any(target.exists() for target in targets.values()):
        raise FileExistsError("Archive already exists; preserve the validated copy")
    metadata.mkdir(parents=True)
    video_root.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.suffix in {".mp4", ".html"}:
            continue
        if item.is_dir():
            shutil.copytree(
                item, metadata / item.name, ignore=shutil.ignore_patterns("*.mp4", "*.html")
            )
        else:
            shutil.copy2(item, metadata / item.name)
    # Keep complete comparison evidence beside the archived run; no dependency
    # on the mutable working directory for the supporting physical result.
    shutil.copytree(
        reference, metadata / "half_dt", ignore=shutil.ignore_patterns("*.mp4", "*.html")
    )
    files = {}
    for name in CAMERAS:
        target = targets[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / f"{name}.mp4", target)
        if (
            target.is_symlink()
            or target.stat().st_nlink != 1
            or sha(target) != validation["videos"][name]["sha256"]
        ):
            raise RuntimeError("Video is not an independent verified copy")
        files[name] = os.path.relpath(target, metadata)
    (metadata / "archive_source.py").write_text(Path(__file__).read_text())
    (metadata / "archive_validation.json").write_text(
        json.dumps(
            dict(
                passed=True,
                videos_independent=True,
                videos_decodable=True,
                synchronized=True,
                validation="validation.json",
            ),
            indent=2,
        )
        + "\n"
    )
    manifest = dict(
        objective=report.get("objective", "disassemble"),
        task_id="cast_coil",
        variant=report.get("geometry_variant", "photo_reference_v1_baseline_3x"),
        inverse_design_kind=report.get("inverse_design_kind"),
        variation_directory=video_root.name,
        video_layout="variant_camera_subdirectories",
        canonical_video_directory=str(video_root.relative_to(ROOT)),
        appearance_kind=report.get("appearance_kind"),
        appearance_parameters=report.get("appearance_parameters"),
        recording_kind=report.get("recording_kind", "live_physics_recording"),
        run_id=run_id,
        source_directory=str(source.relative_to(ROOT)),
        classification="physical_execution_with_grasp_assistance",
        counts_as_complete_robotics_demo=True,
        scope=report["scope"],
        duration_s=report["video_frames"] / report["video_fps"],
        cameras=list(CAMERAS),
        videos={
            n: dict(path=files[n], sha256=sha(metadata / files[n])) for n in CAMERAS
        },
        metadata_sha256={
            str(p.relative_to(metadata)): sha(p)
            for p in sorted(metadata.rglob("*"))
            if p.is_file()
        },
        archived_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    (metadata / "archive_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    update_catalog(metadata, manifest)
    return metadata


def update_catalog(metadata, manifest):
    import re

    folder = ROOT / "runs/demo_metadata"
    catalog = json.loads((folder / "catalog.json").read_text())
    relative = str(metadata.relative_to(folder))
    entry = dict(
        objective=manifest.get("objective", "disassemble"),
        task_id="cast_coil",
        title=demo_title(manifest),
        variant=manifest["variant"],
        inverse_design_kind=manifest.get("inverse_design_kind"),
        appearance_kind=manifest.get("appearance_kind"),
        appearance_parameters=manifest.get("appearance_parameters"),
        classification=manifest["classification"],
        counts_as_complete_robotics_demo=True,
        duration_s=manifest["duration_s"],
        cameras=manifest["cameras"],
        scope="张爪预抓取开始；双侧接触后辅助抓持，完整拆解、分别落桌、解除辅助并自由静置。",
        recording_kind=manifest.get("recording_kind", "live_physics_recording"),
        source_directory=manifest["source_directory"],
        directory=relative,
        manifest=f"{relative}/archive_manifest.json",
        variation_directory=manifest["variation_directory"],
        video_layout="variant_camera_subdirectories",
        archived_at_utc=manifest["archived_at_utc"],
        video_directory=os.path.relpath(
            os.path.commonpath([
                (metadata / v["path"]).resolve().parent
                for v in manifest["videos"].values()
            ]),
            folder,
        ),
        video_files={
            n: os.path.relpath(metadata / v["path"], folder)
            for n, v in manifest["videos"].items()
        },
    )
    if entry["objective"] == "assemble":
        entry["scope"] = "两件在 x、y 均分离的桌面初态；双侧接触后辅助抓持，完成对齐与装配、整体落桌、解除辅助并自由静置。"
    if entry["recording_kind"] == "offline_render_of_exact_physical_states":
        entry["scope"] += "视频为同一次物理执行的精确状态离线渲染。"
    catalog["entries"] = [e for e in catalog["entries"] if e.get("directory") != relative]
    catalog["entries"].append(entry)
    catalog["excluded"] = [
        e for e in catalog.get("excluded", []) if e.get("directory") != relative
    ]
    catalog["complete_robotics_demo_count"] = sum(
        bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"]
    )
    catalog["video_count"] = sum(len(e.get("video_files", {})) for e in catalog["entries"])
    catalog["archived_at_utc"] = manifest["archived_at_utc"]
    (folder / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    # Current navigation uses direct MP4 links, never generated HTML pages.
    readme_path = ROOT / "demos/README.md"
    if readme_path.exists():
        readme = readme_path.read_text()
        links = " · ".join(
            f"[{camera}]({os.path.relpath((metadata / video['path']).resolve(), readme_path.parent)})"
            for camera, video in manifest["videos"].items()
        )
        evidence = os.path.relpath(metadata, readme_path.parent)
        row = (
            f"| {entry['title']} ({manifest['variation_directory']}) | {links} | "
            f"{entry['duration_s']:.2f} s | {entry['scope']} [证据]({evidence}/) |\n"
        )
        pattern = r"^\|[^\n]*cast_coil/" + re.escape(manifest["variation_directory"]) + r"/[^\n]*\n"
        readme, replaced = re.subn(pattern, lambda _: row, readme, flags=re.M)
        if not replaced:
            lines = readme.splitlines(keepends=True)
            last_row = max(
                (i for i, line in enumerate(lines) if line.startswith("|")), default=-1
            )
            if last_row >= 0:
                lines.insert(last_row + 1, row)
                readme = "".join(lines)
            else:
                readme += "\n| 当前版本 | MP4 直链 | 时长 | 范围与证据 |\n| --- | --- | --- | --- |\n" + row
        readme_path.write_text(readme)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-id", default="2026-09-17_aloha_full")
    parser.add_argument("--variant-id", help="Stable public representative ID; defaults to the executed geometry ID")
    args = parser.parse_args()
    print(archive(args.source, args.reference, args.run_id, variant_id=args.variant_id))
