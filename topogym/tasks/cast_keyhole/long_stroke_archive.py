"""Archive the long-stroke physical demo without changing other variant runs."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .geometry import ASSET_ROOT
from .inverse_variants import sha, save, geometry_from_record
from .long_stroke import OUTPUT, SEED
from .robot_motion import ROOT
from .variant_assets import require_variant

CAMERAS=("cam_high","cam_low","cam_left_wrist","cam_right_wrist","detail","oblique","four_views")


def update_text(path,transform):
    """Re-read a shared index if another task changed it during preparation."""
    for _ in range(10):
        before=path.read_text();after=transform(before)
        temporary=path.with_name(path.name+f".long_stroke_{os.getpid()}.tmp")
        temporary.write_text(after)
        if path.read_text()!=before:
            temporary.unlink();continue
        temporary.replace(path);return
    raise RuntimeError(f"Shared index keeps changing: {path}")


def archive(variant=OUTPUT, run_id="2026-09-17_long_stroke_v1", generator="long_stroke", scope=None):
    variant=Path(variant);source=variant/"full_demo"
    report=json.loads((source/"replay_report.json").read_text())
    motion=json.loads((source/"robot_motion.json").read_text())
    record,_=require_variant(variant/"geometry.json",motion)
    if not (report.get("passed") and report.get("robot_execution_verified") and
            report.get("source_physical_audit_passed") and not report.get("kinematic_replay")
            and len(motion["frames"])==report["frames"]):
        raise ValueError("Complete physical recording required")
    physics={}
    for folder in ("robot_physics","robot_physics_half"):
        audit=json.loads((variant/folder/"audit.json").read_text())
        physical=json.loads((variant/folder/"report.json").read_text())
        if not audit["passed"] or not physical["passed"] or audit["geometry_sha256"]!=sha(variant/"geometry.json"):
            raise ValueError(f"Physical validation failed: {folder}")
        for name,digest in audit["source_sha256"].items():
            if sha(variant/folder/name)!=digest:raise ValueError("Changed physical evidence")
        physics[folder]=dict(dt=physical["dt"],passed=True,minimum_gap_m=audit["minimum_sampled_gap_m"],
            max_penetration_m=physical["max_contact_penetration_m"],
            final_separation_lower_bound_m=audit["final_separation_lower_bound_m"])
    if abs(physics["robot_physics_half"]["dt"]*2-physics["robot_physics"]["dt"])>1e-12:
        raise ValueError("Missing time-step refinement")
    original_audit=json.loads((variant/"robot_physics/audit.json").read_text())
    if report["physical_source_sha256"]!=original_audit["source_sha256"]:
        raise ValueError("Video references another physical episode")
    trace=json.loads((variant/"robot_physics/trajectory.json").read_text())
    for frame in motion["frames"]:
        actual=trace[frame["source_trace_index"]]
        if any(frame[k]!=actual[k] for k in ("qpos","bodies","time_s","physics_step")):
            raise ValueError("Video frame differs from actual physics state")
    meta_root=ROOT/"runs/demo_metadata";meta=meta_root/"cast_keyhole"/run_id
    video_dir=ROOT/"runs/demos/cast_keyhole"
    targets={n:video_dir/f"{run_id}_{n}.mp4" for n in CAMERAS}
    if meta.exists() or any(p.exists() for p in targets.values()):raise ValueError("Archive already exists")
    videos={}
    for n in CAMERAS:
        p=source/f"{n}.mp4"
        s=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-select_streams","v:0",
            "-show_entries","stream=nb_read_frames,avg_frame_rate,duration,width,height","-of","json",str(p)]))["streams"][0]
        num,den=map(int,s["avg_frame_rate"].split("/"))
        if int(s["nb_read_frames"])!=report["frames"] or abs(num/den-report["fps"])>1e-9 or abs(float(s["duration"])-report["duration_s"])>.001:
            raise ValueError(f"Unsynchronized video: {n}")
        subprocess.run(["ffmpeg","-v","error","-i",str(p),"-f","null","-"],check=True,capture_output=True)
        videos[n]=dict(s,sha256=sha(p),decoded=True,path=os.path.relpath(targets[n],meta))
    shutil.copytree(source,meta,ignore=shutil.ignore_patterns("*.mp4"))
    evidence=meta/"evidence";evidence.mkdir()
    for p in variant.iterdir():
        if p.is_file():shutil.copy2(p,evidence/p.name)
    for folder in ("robot_physics","robot_physics_half"):shutil.copytree(variant/folder,evidence/folder)
    shutil.copy2(SEED,evidence/"seed_robot_motion.json")
    for name in ("template.json","baseline_solution.json","sources.json"):
        shutil.copy2(ASSET_ROOT/name,evidence/f"seed_{name}")
    sources=evidence/"runner_sources";sources.mkdir()
    names=("long_stroke","inverse_variants","variant_assets","scene","robot_execution","physical_audit",
        "physical_recording","aloha_demo","geometry","solution","collision","robot_motion","route_probe",
        "trajectory_probe","long_stroke_archive")
    if generator != "long_stroke":names += (generator, generator+"_archive")
    for name in names:shutil.copy2(Path(__file__).with_name(name+".py"),sources/(name+".py"))
    video_dir.mkdir(parents=True,exist_ok=True)
    for n,dst in targets.items():
        src=source/f"{n}.mp4";shutil.copy2(src,dst)
        if sha(dst)!=videos[n]["sha256"] or dst.is_symlink() or dst.stat().st_ino==src.stat().st_ino:
            raise ValueError("Video is not an independent copy")
    meshes,_=geometry_from_record(json.loads((evidence/"geometry.json").read_text()))
    if any(not m.is_watertight or len(m.split())!=1 for m in meshes):raise ValueError("Archived geometry invalid")
    for name,digest in original_audit["source_sha256"].items():
        if sha(evidence/"robot_physics"/name)!=digest:raise ValueError("Archived evidence changed")
    qualification=dict(passed=True,classification="physical_execution_with_grasp_assistance",
        complete_extraction_verified=True,pregrasp_start=True,assisted_weld_grasp=True,
        grasp_assistance_active_at_end=True,friction_only_grasp_verified=False,
        all_views_synchronous=True,independent_copies=True,actual_physics_frames_verified=True,
        geometry_reconstructed_from_archive=True,physics_validation=physics,
        frames=report["frames"],fps=report["fps"],duration_s=report["duration_s"])
    save(meta/"archive_validation.json",qualification)
    now=datetime.now(timezone.utc).isoformat();relative=str(meta.relative_to(meta_root))
    if scope is None:
        scope="长行程错齿变体：穿齿行程增加20%，由新IK轨迹反推齿位；预抓取、双指接触后辅助抓持，完整分离后双臂保持。视频逐帧来自同一次物理执行。"
    title="Cast Keyhole · "+record["title_zh"]
    manifest=dict(task_id="cast_keyhole",instance=record["id"],run_id=run_id,archived_at_utc=now,
        source_directory=str(source),classification=qualification["classification"],scope=scope,
        counts_as_complete_robotics_demo=True,cameras=list(CAMERAS[:4]),duration_s=report["duration_s"],videos=videos,
        metadata_sha256={str(p.relative_to(meta)):sha(p) for p in sorted(meta.rglob("*")) if p.is_file()})
    save(meta/"archive_manifest.json",manifest)
    entry=dict(task_id="cast_keyhole",title=title,variant=record["id"],classification=qualification["classification"],
        counts_as_complete_robotics_demo=True,duration_s=report["duration_s"],frames=report["frames"],fps=report["fps"],
        cameras=list(CAMERAS[:4]),scope=scope,source_directory=str(source.relative_to(ROOT)),directory=relative,
        index=relative+"/archive_manifest.json",archived_at_utc=now,video_directory="../demos/cast_keyhole",
        video_files={f"{n}.mp4":os.path.relpath(p,meta_root) for n,p in targets.items()})
    def catalog_update(text):
        catalog=json.loads(text)
        if any(e.get("directory")==relative for e in catalog["entries"]):raise ValueError("Duplicate catalog entry")
        catalog["entries"].append(entry);catalog["archived_at_utc"]=now
        catalog["complete_robotics_demo_count"]=sum(bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"])
        return json.dumps(catalog,indent=2,ensure_ascii=False)+"\n"
    update_text(meta_root/"catalog.json",catalog_update)
    row=f'| {title} | [近景视频]({os.path.relpath(targets["detail"],meta_root)}) · [证据]({relative}/archive_manifest.json) | 7 | {scope} |\n'
    update_text(meta_root/"README.md",lambda text:text.replace("\n\n保留全部既有 MP4","\n"+row+"\n保留全部既有 MP4"))
    card=f'<section><h2>{title}</h2><p>{scope}</p><p><a href="{os.path.relpath(targets["detail"],meta_root)}">全过程近景视频</a> · <a href="{os.path.relpath(targets["four_views"],meta_root)}">四视角视频</a> · <a href="{relative}/archive_manifest.json">来源与证据</a></p></section>'
    def index_update(text):
        catalog=json.loads((meta_root/"catalog.json").read_text())
        count=sum(bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"])
        previews=sum(e.get("classification")=="kinematic_rehearsal" for e in catalog["entries"])
        text=re.sub(r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演",
            f"当前保留 {count} 份完整物理执行及 {previews} 份运动学预演",text)
        return text.replace("<section><h2>本次暂未收录",card+"<section><h2>本次暂未收录")
    update_text(meta_root/"index.html",index_update)
    for link in re.findall(r'(?:href|src)="([^"]+)"',card):
        if not (meta_root/link).exists():raise ValueError(f"Broken archive link: {link}")
    print(json.dumps(dict(passed=True,video_directory=str(video_dir),metadata=str(meta),
        videos={n:str(p) for n,p in targets.items()}),indent=2),flush=True)


def main():
    archive()


if __name__=="__main__":main()
