"""Retain a verified continuous physical execution and its independent videos."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from omegaconf import OmegaConf

from .qualification import summarize, compare_trajectories, physical_profile, runtime_sources, identical_input_mesh

ROOT = Path(__file__).resolve().parents[3]
CAMERAS = {"cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist", "detail"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def archive(source, qualification_folder, run_id):
    source, qualification_folder = Path(source).resolve(), Path(qualification_folder).resolve()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_[a-zA-Z0-9_]+", run_id):
        raise ValueError("Use a dated, unique archive identifier")
    report = json.loads((source/"report.json").read_text())
    video_check = json.loads((source/"video_validation.json").read_text())
    qualification = summarize(qualification_folder)
    if json.loads((qualification_folder/"qualification.json").read_text()) != qualification:
        raise ValueError("Saved qualification no longer matches its evidence")
    if not (report.get("full_threading_verified") and report.get("passed")
            and report.get("complete_physics_suite_passed") and video_check.get("passed")
            and qualification["passed"]):
        raise ValueError("Only a verified full physical execution may be archived as complete")
    spec = json.loads((source/"validation_spec.json").read_text())
    cfg = OmegaConf.load(source/"config.yaml")
    expected_settling = float(cfg.task.get('validation', {}).get('final_post_sequence_settle_s', 5.))
    if (spec['actuation']['minimum_post_release_s'] != expected_settling
            or expected_settling < qualification['minimum_robot_settling_s']):
        raise ValueError('Recorded final observation differs from configuration or is shorter than qualification')
    if (spec.get("qualification", {}).get("sha256") != digest(qualification_folder/"qualification.json")
            or physical_profile(cfg) != qualification["profile"]
            or report.get("reference_speed") != qualification["reference_speed"]
            or runtime_sources(spec) != runtime_sources(qualification)
            or spec["actuation"]["reference_sha256"] != qualification["reference_sha256"]):
        raise ValueError("Full execution does not match the supplied qualification evidence")
    prefix = qualification_folder/qualification["case_directories"]["robot_prefix"]
    if not identical_input_mesh(source, prefix):
        raise ValueError("Full execution initial mesh differs from the qualified robot prefix")
    streams = video_check["streams"]
    if not CAMERAS <= streams.keys() or len({s["decoded_frames"] for s in streams.values()}) != 1:
        raise ValueError("Five synchronized ALOHA and detail camera streams are required")
    metadata_root = ROOT/"runs/demo_metadata"
    metadata = metadata_root/"rope_threading"/run_id
    videos = ROOT/"demos/rope_threading"
    if metadata.exists() or any(videos.glob(run_id+"_*.mp4")):
        raise FileExistsError("Archive destination already exists; choose a new identifier")
    for name, stream in streams.items():
        if digest(source/f"{name}.mp4") != stream["sha256"]:
            raise ValueError(f"Video changed after validation: {name}")
    shutil.copytree(source, metadata, ignore=shutil.ignore_patterns("*.mp4", "*.html", "STOP", "__pycache__"))
    evidence = metadata/"physics_qualification"
    evidence.mkdir()
    save(evidence/"qualification.json", qualification)
    if (qualification_folder/"cases.json").exists():
        shutil.copy2(qualification_folder/"cases.json", evidence/"cases.json")
    if (qualification_folder/"baseline_provenance.json").exists():
        shutil.copy2(qualification_folder/"baseline_provenance.json", evidence/"baseline_provenance.json")
    if (qualification_folder/'recording_request.json').is_file():
        shutil.copy2(qualification_folder/'recording_request.json', evidence/'recording_request.json')
    if (qualification_folder/"retry_rationale.json").exists():
        shutil.copy2(qualification_folder/"retry_rationale.json", evidence/"retry_rationale.json")
        observation = qualification_folder/"robot_release_sliding_observation.json"
        if observation.is_file():
            shutil.copy2(observation, evidence/observation.name)
        # Retain failed and interrupted attempts separately from the selected
        # completed cases, including the 40-second half-timestep tail failure.
        for name in ("robot_prefix", "ring_halfdt"):
            for previous in sorted(qualification_folder.glob(name+'*')):
                if (previous.name == qualification["case_directories"][name]
                        or not (previous/'validation_spec.json').is_file()):
                    continue
                destination = evidence/"previous_attempts"/previous.name
                destination.mkdir(parents=True, exist_ok=True)
                for filename in ("report.json", "validation_spec.json", "config.yaml", "trace.json",
                                 "trajectory.npz", "contact_trace.json"):
                    if (previous/filename).is_file():
                        shutil.copy2(previous/filename, destination/filename)
    for relative in qualification["case_directories"].values():
        shutil.copytree(qualification_folder/relative, evidence/relative,
                        ignore=shutil.ignore_patterns("__pycache__", "STOP", "partial_*", "*.html"))
    copied_qualification = summarize(evidence)
    if not copied_qualification["passed"] or copied_qualification != qualification:
        raise RuntimeError("Copied qualification evidence did not validate")
    release_limits = report.get("actuation", {}).get("release_operating_limits")
    if release_limits:
        diagnostic = ROOT/"runs/environment-solvability/rope_threading/physics_soft50_precise_v1"
        retained = metadata/"unsupported_drop_diagnostic"
        for name in ("ring_contact", "ring_halfdt"):
            shutil.copytree(diagnostic/name, retained/name,
                ignore=shutil.ignore_patterns("__pycache__", "STOP", "partial_*", "*.html", "*.mp4"))
        comparison = compare_trajectories(retained/"ring_contact", retained/"ring_halfdt")
        comparison["scope"] = "Preserved failed high-drop test of the earlier undamped profile; the current demonstration does not qualify that regime"
        save(retained/"comparison.json", comparison)
    reference = ROOT/"runs/environment-solvability/rope_threading/reference_motion_v1"
    shutil.copytree(reference, metadata/"motion_reference")
    shutil.copy2(ROOT/"assets/tasks/rope_threading/wang_reference_v1/LICENSE", metadata/"reference_LICENSE")
    from .physics_review import build as build_review
    build_review(evidence)
    videos.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() or not p.is_file() or p.suffix != '.mp4' for p in videos.iterdir()):
        raise ValueError('Task video directory must contain only independent MP4 files')
    copied_videos = {}
    import imageio.v2 as imageio
    for name, stream in streams.items():
        destination = videos/f"{run_id}_{name}.mp4"
        shutil.copy2(source/f"{name}.mp4", destination)
        with imageio.get_reader(destination) as reader:
            fps = reader.get_meta_data()["fps"]
            count = sum(1 for _ in reader)
        if (digest(destination) != stream["sha256"] or count != stream["decoded_frames"]
                or abs(fps-stream["fps"]) > 1e-8):
            raise RuntimeError(f"Archive video verification failed: {name}")
        copied_videos[name] = dict(path=str(destination.relative_to(ROOT)), sha256=stream["sha256"],
            frames=count, fps=fps, duration_s=count/fps)
    scope = ("从参考待命初态开始，完整执行 51 阶段动作；关节位置控制驱动机器人，FEM+IPC 重新模拟绳子。"
             "双指实际接触后辅助抓持，6 次抓取与全部释放；三环材料顺序通过，双端落桌、双臂退出并静置。"
             "末段右手放回目标平滑抬高 3 cm，以适配共享桌面。")
    scope += f'动作结束后继续自然静置 {spec["actuation"]["minimum_post_release_s"]:g} s。'
    if release_limits:
        scope += (f'完全松手限于距桌面 {release_limits["max_unsupported_height_m"]*1000:g} mm 内，'
                  f'高处松手须有 {release_limits["max_supported_material_span_m"]*1000:g} mm 材料距离内的另一抓持支撑；'
                  '先前无阻尼版本的 33 cm 高处完全松手未通过数值对照，本演示不覆盖该工况。')
    damping = report.get("deformation_damping")
    if damping:
        scope += f'形变耗散系数 {damping["rate_s_inv"]:g} s⁻¹，剔除整体平移/转动；绳材及耗散参数未经实物标定。'
    physical_parameters = dict(table_contact=report.get('table_contact'),
        young_modulus_pa=float(cfg.task.rope.fem.E),
        poisson_ratio=float(cfg.task.rope.fem.nu), density_kg_m3=float(cfg.task.rope.fem.rho),
        rope_material_friction=float(cfg.task.rope.fem.friction_mu),
        initial_rope_lift_m=float(cfg.task.geometry.get("rope_height_offset_m", 0.)),
        contact_distance_m=float(cfg.task.rope.fem.contact_d_hat),
        newton_velocity_tolerance_m_s=float(cfg.task.rope.fem.newton_tolerance),
        deformation_damping_rate_s_inv=float(cfg.task.rope.fem.get("deformation_damping_rate_s_inv", 0.)),
        rope_mesh=dict(axial_subdivisions=int(cfg.task.geometry.rope_subdivisions),
            radial_segments=int(cfg.task.geometry.radial_segments),
            max_tetrahedron_volume_m3=float(cfg.task.rope.mesh.maxvolume),
            centerline_interpolation=str(cfg.task.geometry.get('centerline_interpolation', 'linear'))),
        control_dt_s=float(cfg.env.sim.dt), native_dt_s=float(cfg.env.sim.dt)/int(cfg.env.sim.substeps))
    video_links = {name: os.path.relpath(ROOT/item['path'], metadata) for name, item in copied_videos.items()}
    lines = ["# 绳穿三环 · ALOHA 完整物理执行", "", scope, ""]
    lines += [f"- [{name}]({video_links[name]})：{item['duration_s']:.2f} s，{item['frames']} 帧。"
              for name, item in copied_videos.items()]
    lines += ["", "[完整执行报告](report.json) · [视频校验](video_validation.json) · "
              "[物理资格证据](physics_qualification/README.md) · [参考动作阶段](motion_reference/reference_summary.json)", ""]
    if (evidence/'retry_rationale.json').is_file():
        lines += [f"机器人前段在松手后 5 秒的静置检查中失败，延长至 {qualification['minimum_robot_settling_s']:g} 秒通过；"
                  f"完整动作后观察 {expected_settling:g} 秒，末两秒门槛相同。"
                  "[重跑说明](physics_qualification/retry_rationale.json)。失败与中断记录独立保留。", ""]
    if release_limits:
        lines += ["[先前高处释放失败对照](unsupported_drop_diagnostic/comparison.json)。", ""]
    (metadata/'README.md').write_text("\n".join(lines))
    for name, item in copied_videos.items():
        original, copied = source/f'{name}.mp4', ROOT/item['path']
        if copied.is_symlink() or os.path.samefile(original, copied) or copied.stat().st_nlink != 1:
            raise RuntimeError(f'Archive video is not an independent file: {name}')
    save(metadata/"archive_manifest.json", dict(schema_version=2, task_id="rope_threading", variant="wang_reference_v1",
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        physical_parameters=physical_parameters,
        release_operating_limits=release_limits,
        post_sequence_settle_s=spec['actuation']['minimum_post_release_s'],
        original_directory=str(source.relative_to(ROOT)), scope=scope,
        reference_speed=report["reference_speed"], simulated_seconds=report["simulated_seconds"],
        cameras=list(streams), videos=copied_videos, same_continuous_rollout=True,
        archived_at_utc=datetime.now(timezone.utc).isoformat(),
        files={str(p.relative_to(ROOT)): digest(p) for p in sorted(metadata.rglob("*")) if p.is_file()}))
    for document in (metadata/'README.md', evidence/'README.md'):
        for target in re.findall(r'\]\(([^)]+)\)', document.read_text()):
            if not target.startswith(('http:', 'https:')) and not (document.parent/target).resolve().is_file():
                raise RuntimeError(f'Missing archived dependency: {document.name}: {target}')
    relative = str(metadata.relative_to(metadata_root))
    entry = dict(task_id="rope_threading", title="绳穿三环 · ALOHA 完整物理执行", variant="wang_reference_v1",
        physical_parameters=physical_parameters,
        release_operating_limits=release_limits,
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        duration_s=next(iter(copied_videos.values()))["duration_s"], cameras=list(streams), scope=scope,
        source_directory=str(source.relative_to(ROOT)), directory=relative, readme=relative+"/README.md",
        video_directory="../../demos/rope_threading",
        video_files={name+".mp4": "../../demos/rope_threading/"+Path(item["path"]).name for name, item in copied_videos.items()},
        archived_at_utc=datetime.now(timezone.utc).isoformat())
    catalog_path = metadata_root/"catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["entries"].append(entry)
    catalog["excluded"] = [item for item in catalog.get("excluded", []) if item.get("task_id") != "rope_threading"]
    catalog["complete_robotics_demo_count"] = sum(bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"])
    catalog["archived_at_utc"] = entry["archived_at_utc"]
    catalog["updated_at_utc"] = entry["archived_at_utc"]
    catalog.setdefault("task_video_layout", {})["rope_threading"] = dict(
        organization="flat MP4-only task directory", video_directory="../../demos/rope_threading",
        metadata_directory="rope_threading", cameras=list(streams))
    save(catalog_path, catalog)
    readme = metadata_root/"README.md"
    text = re.sub(r'(?m)^- `rope_threading`：本次扫描未发现完整机器人三视角 demo。\n?', '', readme.read_text())
    links = " · ".join(f"[{name}](../../{item['path']})" for name, item in copied_videos.items())
    readme.write_text(text+f'\n绳穿三环：{links}。[{len(streams)} 路同步视频证据]({relative}/README.md)。{scope}\n')
    return metadata/"archive_manifest.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("qualification_folder", type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(archive(args.source, args.qualification_folder, args.run_id))


if __name__ == "__main__":
    main()
