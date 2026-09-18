"""Archive a verified complete IK rehearsal as independent video/evidence copies."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .geometry import ASSET_ROOT
from .instance_solution import require_current_instance_certificate

ROOT=Path(__file__).resolve().parents[3]
CAMERAS=("cam_high","cam_low","cam_left_wrist","cam_right_wrist","detail","oblique","four_views")


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archive(source,run_id):
    source=Path(source).resolve();report=json.loads((source/"replay_report.json").read_text())
    motion=json.loads((source/"robot_motion.json").read_text())
    physical=bool(report.get("robot_execution_verified") and report.get("source_physical_audit_passed") and not report.get("kinematic_replay"))
    if not (report.get("passed") and report.get("sampled_robot_scene_clearance_passed")
            and len(motion["frames"])==report["frames"] and
            (physical or (report.get("kinematic_replay") and report.get("physics_steps")==0))):
        raise ValueError("Expected a complete, checked physical execution or explicitly kinematic rehearsal")
    evidence=ROOT/"runs/environment-solvability/cast_keyhole/diagram_reference_v1/current_instance"
    require_current_instance_certificate(ASSET_ROOT/"baseline_solution.json",evidence/"certificate.json")
    if physical:
        audit=json.loads((evidence/"robot_physics/audit.json").read_text())
        if not audit["passed"]:raise ValueError("Physical state audit failed")
        for name,digest in audit["source_sha256"].items():
            if sha(evidence/"robot_physics"/name)!=digest:raise ValueError("Physical trace changed")
        if report.get("physical_source_sha256")!=audit["source_sha256"]:
            raise ValueError("Rendered physical source differs from the audit")
        trace=json.loads((evidence/"robot_physics/trajectory.json").read_text())
        for frame in motion["frames"]:
            actual=trace[frame["source_trace_index"]]
            if any(frame[k]!=actual[k] for k in ("qpos","bodies","physics_step","time_s")):
                raise ValueError("Rendered frame is not an actual physics state")
    for name in ("physics_dt1ms","physics_dt05ms"):
        if not json.loads((evidence/name/"report.json").read_text())["passed"]:
            raise ValueError("Both complete route force benches must pass")
    if report["solution_sha256"]!=sha(ASSET_ROOT/"baseline_solution.json"):
        raise ValueError("The rendered route differs from the current certificate")
    video_checks={}
    for n in CAMERAS:
        p=source/f"{n}.mp4"
        probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-select_streams","v:0",
            "-show_entries","stream=nb_read_frames,avg_frame_rate,duration,width,height","-of","json",str(p)]))
        s=probe["streams"][0];num,den=map(int,s["avg_frame_rate"].split("/"))
        if int(s["nb_read_frames"])!=report["frames"] or abs(num/den-report["fps"])>1e-9 or abs(float(s["duration"])-report["duration_s"])>.001:
            raise ValueError(f"Unsynchronized video: {n}")
        subprocess.run(["ffmpeg","-v","error","-i",str(p),"-f","null","-"],check=True,capture_output=True)
        video_checks[n]=dict(s,sha256=sha(p),decoded=True)
    meta_root=ROOT/"runs/demo_metadata";meta=meta_root/"cast_keyhole"/run_id
    video_dir=ROOT/"runs/demos/cast_keyhole"
    if meta.exists():raise ValueError("Archive already exists; choose a new run ID")
    video_dir.mkdir(parents=True,exist_ok=True)
    suffix="" if physical else "_kinematic"
    classification="physical_execution_with_grasp_assistance" if physical else "kinematic_rehearsal"
    targets={n:video_dir/f"{run_id}{suffix}_{n}.mp4" for n in CAMERAS}
    if any(p.exists() for p in targets.values()):raise ValueError("Refusing to overwrite archived videos")
    shutil.copytree(source,meta,ignore=shutil.ignore_patterns("*.mp4"))
    shutil.copytree(evidence,meta/"evidence",dirs_exist_ok=True)
    for name in ("template.json","baseline_solution.json","sources.json"):
        shutil.copy2(ASSET_ROOT/name,meta/"evidence"/name)
    saved_sources={}
    cert=json.loads((evidence/"certificate.json").read_text())
    for path,digest in cert["fingerprint"].items():
        src=Path(path);dst=meta/"evidence/certified_sources"/src.name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
        if sha(dst)!=digest:raise ValueError("Certificate source changed")
        saved_sources[path]=str(dst.relative_to(meta))
    for name in ("robot_motion.py","aloha_demo.py","trajectory_probe.py","robot_execution.py","archive_demo.py","physical_audit.py","physical_recording.py"):
        dst=meta/"evidence/runner_sources"/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(__file__).with_name(name),dst)
    (meta/"evidence/certified_sources.json").write_text(json.dumps(saved_sources,indent=2)+"\n")
    videos={}
    page=(meta/"index.html").read_text()
    for n,dst in targets.items():
        src=source/f"{n}.mp4";shutil.copy2(src,dst)
        if sha(dst)!=sha(src) or dst.stat().st_ino==src.stat().st_ino or dst.is_symlink():
            raise ValueError("Archive is not an independent verified copy")
        relative=os.path.relpath(dst,meta)
        page=page.replace(f'src="{n}.mp4"',f'src="{relative}"')
        videos[n]=dict(path=relative,sha256=sha(dst),**{k:v for k,v in video_checks[n].items() if k!="sha256"})
    (meta/"index.html").write_text(page)
    missing=[]
    for link in re.findall(r'(?:href|src)="([^"]+)"',page):
        if not re.match(r"https?://|#|data:",link) and not (meta/link.split("#")[0]).exists():missing.append(link)
    if missing:raise ValueError(f"Archive page has missing local links: {missing}")
    validation=dict(passed=True,video_checks=video_checks,frames=report["frames"],fps=report["fps"],
        all_views_synchronous=True,local_page_links_valid=True,independent_copies=True,classification=classification)
    (meta/"archive_validation.json").write_text(json.dumps(validation,indent=2)+"\n")
    (meta/"recording_qualification.json").write_text(json.dumps(dict(
        formal_demo_qualified=physical,classification=classification,
        actual_physical_trace_verified=physical,video_decode_and_synchronization_passed=True,
        initial_scope="pregrasp current authored relative instance",
        final_scope="separated pieces held by the two arms; assisted grasp remains active" if physical else "complete kinematic extraction",
        pure_friction_grasp_verified=False),indent=2)+"\n")
    files={str(p.relative_to(meta)):sha(p) for p in sorted(meta.rglob("*")) if p.is_file()}
    now=datetime.now(timezone.utc).isoformat()
    scope=("当前下部孔道初态到完全分离；预抓取开始，同步双指接触后辅助抓持；全程关节控制，末态双臂保持分离，辅助约束仍启用。视频来自同一次连续物理执行的实际状态。" if physical else
           "当前下部孔道初态到完全分离；预抓取开始；完整运动学预演，physics_steps=0。独立完整力控台架通过；机器人受力执行单独报告。")
    manifest=dict(task_id="cast_keyhole",instance="perpendicular_lower_bore_v1",source_directory=str(source),
        run_id=run_id,archived_at_utc=now,classification=classification,scope=scope,
        counts_as_complete_robotics_demo=physical,cameras=list(CAMERAS[:4]),duration_s=report["duration_s"],
        videos=videos,metadata_sha256=files)
    (meta/"archive_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
    catalog_path=meta_root/"catalog.json";catalog=json.loads(catalog_path.read_text())
    relative=str(meta.relative_to(meta_root))
    title="Cast Keyhole · 双臂物理执行" if physical else "Cast Keyhole · 当前实例双臂 IK"
    entry=dict(task_id="cast_keyhole",title=title,variant="perpendicular_lower_bore_v1",
        classification=classification,counts_as_complete_robotics_demo=physical,duration_s=report["duration_s"],
        cameras=list(CAMERAS[:4]),scope=scope,source_directory=str(source.relative_to(ROOT)),directory=relative,
        index=relative+"/index.html",archived_at_utc=now,video_directory="../demos/cast_keyhole",
        video_files={f"{n}.mp4":os.path.relpath(p,meta_root) for n,p in targets.items()})
    catalog["entries"].append(entry);catalog["archived_at_utc"]=now
    catalog["kinematic_preview_count"]=sum(e["classification"]=="kinematic_rehearsal" for e in catalog["entries"])
    catalog["complete_robotics_demo_count"]=sum(e.get("counts_as_complete_robotics_demo",False) for e in catalog["entries"])
    catalog["excluded"]=[e for e in catalog.get("excluded",[]) if e["task_id"]!="cast_keyhole"]
    catalog_path.write_text(json.dumps(catalog,indent=2,ensure_ascii=False)+"\n")
    readme=meta_root/"README.md";text=readme.read_text();row=f'| {title} | [打开]({relative}/index.html) | 7 | {scope} |\n'
    text=text.replace("\n\n保留全部既有 MP4", "\n"+row+"\n保留全部既有 MP4")
    text=text.replace("- `cast_keyhole`：完整路线与机器人抓持尚未验收，现有三正交诊断图不是机器人三视角视频。", "- `cast_keyhole`：已另存完整四视角 IK 预演及当前实例可解性证据；不计为已验收物理机器人 demo。")
    if physical:text=text.replace("- `cast_keyhole`：已另存完整四视角 IK 预演及当前实例可解性证据；不计为已验收物理机器人 demo。", "- `cast_keyhole`：已新增同一初态的完整双臂辅助抓持物理执行，保留四路同步视角；另存 IK 预演。")
    readme.write_text(text)
    index=meta_root/"index.html";text=index.read_text()
    text=re.sub(r"2026-09-16 整理：1 份三视角完整物理执行，另保留 1 份四视角运动学预演。",
        f'当前保留 {catalog["complete_robotics_demo_count"]} 份完整物理执行及 {catalog["kinematic_preview_count"]} 份运动学预演。',text)
    text=re.sub(r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演。",
        f'当前保留 {catalog["complete_robotics_demo_count"]} 份完整物理执行及 {catalog["kinematic_preview_count"]} 份运动学预演。',text)
    label="完整物理执行 · 含辅助抓持" if physical else "完整运动学预演"
    card=f'<section><h2><a href="{relative}/index.html">{title}</a></h2><p><strong>{label}</strong> · {report["duration_s"]:.1f} 秒 · 四路同步观测</p><p>{scope}</p><p><a href="{relative}/index.html">播放页</a> · <a href="{relative}/archive_manifest.json">来源与哈希清单</a> · <a href="{relative}/archive_validation.json">归档检查</a></p></section>'
    text=text.replace("<section><h2>本次暂未收录",card+"<section><h2>本次暂未收录")
    text=re.sub(r"<tr><td>cast_keyhole</td><td>.*?</td></tr>","",text)
    index.write_text(text)
    print(meta/"index.html")
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--source",type=Path,required=True)
    p.add_argument("--run-id",required=True);a=p.parse_args();archive(a.source,a.run_id)


if __name__=="__main__":main()
