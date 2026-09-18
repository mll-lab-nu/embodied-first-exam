"""Keep independently playable Claw videos and their complete review evidence."""
import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .recording import NAMES, sha, write_page
from .reference import ROOT
from .verification import validate_physical


def video_info(path):
    r=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-select_streams","v:0",
        "-show_entries","stream=nb_read_frames,width,height,avg_frame_rate:format=duration","-of","json",str(path)]))
    s=r["streams"][0]
    subprocess.run(["ffmpeg","-v","error","-threads","2","-i",str(path),"-f","null","-"],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    return dict(frames=int(s["nb_read_frames"]),duration_s=float(r["format"]["duration"]),
                width=s["width"],height=s["height"],frame_rate=s["avg_frame_rate"],fully_decoded=True)


def archive(source, run_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+",run_id):raise ValueError("Unsafe archive identifier")
    source=Path(source).resolve()
    report=json.loads((source/"recording_report.json").read_text())
    physical=report["classification"]=="physical_execution_with_grasp_assistance"
    if report["keyframes_only"] or report["states_sha256"]!=sha(source/"render_states.jsonl"):
        raise ValueError("Incomplete or altered recording")
    if physical:
        result,_=validate_physical(source/"evidence/physical")
        if report["source_physical_states_sha256"]!=result["states_sha256"]:
            raise ValueError("Recording/physics mismatch")
        if sha(source/"render_states.jsonl")!=result["states_sha256"]:
            raise ValueError("Rendering did not use the exact saved physical states")
    metadata=ROOT/"runs/demo_metadata/interlocked_claws"/run_id
    videos=ROOT/"runs/demos/interlocked_claws"
    if metadata.exists():raise FileExistsError(metadata)
    prefix=run_id+("" if physical else "_kinematic")
    destinations={n:videos/f"{prefix}_{n}.mp4" for n in NAMES}
    if any(p.exists() for p in destinations.values()):raise FileExistsError("Existing video prefix")
    checks={n:video_info(source/f"{n}.mp4") for n in NAMES}
    if any(v["frames"]!=report["frames"] or abs(v["duration_s"]-report["duration_s"])>1e-3 for v in checks.values()):
        raise ValueError("Video frame count/duration differs from the recorded states")
    shutil.copytree(source,metadata,ignore=shutil.ignore_patterns("*.mp4","__pycache__"))
    videos.mkdir(parents=True,exist_ok=True)
    records={}
    for n,path in destinations.items():
        shutil.copy2(source/f"{n}.mp4",path)
        if sha(path)!=sha(source/f"{n}.mp4") or path.stat().st_ino==(source/f"{n}.mp4").stat().st_ino:
            raise ValueError("Archive must contain verified independent copies")
        records[n]=dict(path=os.path.relpath(path,metadata),sha256=sha(path),bytes=path.stat().st_size,**checks[n])
    write_page(metadata,report,{n:v["path"] for n,v in records.items()})
    # Snapshot implementation alongside the states and source asset exports.
    shutil.copytree(Path(__file__).parent,metadata/"implementation",ignore=shutil.ignore_patterns("__pycache__"))
    for page in metadata.glob("*.html"):
        for url in re.findall(r'(?:href|src)="([^"#]+)',page.read_text()):
            if "://" not in url and not (page.parent/url.split("#")[0]).exists():
                raise ValueError(f"Broken local link in {page}: {url}")
    files={str(p.relative_to(metadata)):dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in metadata.rglob("*") if p.is_file()}
    manifest=dict(schema_version=1,task_id="interlocked_claws",variant="cspace_claw_wang_v1",
        classification=report["classification"],counts_as_complete_robotics_demo=physical,
        recording_kind="offline_render_of_exact_physical_states" if physical else "kinematic_rehearsal",
        scope="原始网格与完整12阶段；预抓取、理想刚性辅助抓持；释放后自由静置。非纯摩擦抓取验证。",
        source_directory=str(source.relative_to(ROOT)),physical_source_directory=report["source_directory"],
        archived_at_utc=datetime.now(timezone.utc).isoformat(),duration_s=report["duration_s"],
        frames=report["frames"],fps=report["fps"],cameras=list(NAMES),videos=records,files=files,
        source_motion_sha256=report["source_motion_sha256"],states_sha256=report["states_sha256"],
        video_decoding_passed=True,local_links_passed=True,independent_file_copies=True)
    (metadata/"archive_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    update_catalog(metadata,manifest)
    return metadata


def update_catalog(metadata,manifest):
    folder=ROOT/"runs/demo_metadata";relative=str(metadata.relative_to(folder))
    catalog=json.loads((folder/"catalog.json").read_text())
    if any(e["directory"]==relative for e in catalog["entries"]):raise ValueError("Duplicate catalog entry")
    entry=dict(task_id="interlocked_claws",title="Claw · 原视频完整动作与物理验收",
        variant=manifest["variant"],classification=manifest["classification"],
        counts_as_complete_robotics_demo=manifest["counts_as_complete_robotics_demo"],
        duration_s=manifest["duration_s"],cameras=manifest["cameras"],scope=manifest["scope"],
        recording_kind=manifest["recording_kind"],source_directory=manifest["source_directory"],
        directory=relative,index=f"{relative}/index.html",archived_at_utc=manifest["archived_at_utc"],
        video_directory="../demos/interlocked_claws",
        video_files={n:os.path.relpath(metadata/v["path"],folder) for n,v in manifest["videos"].items()})
    catalog["entries"].append(entry)
    catalog["excluded"]=[e for e in catalog.get("excluded",[]) if e["task_id"]!="interlocked_claws"]
    catalog["complete_robotics_demo_count"]=sum(bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"])
    catalog["kinematic_preview_count"]=sum(e.get("classification")=="kinematic_rehearsal" for e in catalog["entries"])
    catalog["archived_at_utc"]=manifest["archived_at_utc"]
    (folder/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n")
    page=(folder/"index.html").read_text()
    card=f'<section><h2><a href="{relative}/index.html">{entry["title"]}</a></h2><p>{entry["duration_s"]:.1f} 秒 · 五路同步视角 · {escape(entry["scope"])}</p><p><a href="{relative}/reliability.html">物理验收与限制</a> · <a href="{relative}/archive_manifest.json">来源与文件清单</a></p></section>'
    page=page.replace("<section><h2>本次暂未收录",card+"<section><h2>本次暂未收录",1)
    page=re.sub(r"<tr><td>interlocked_claws</td><td>.*?</td></tr>","",page)
    page=re.sub(r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演",
        f"当前保留 {catalog['complete_robotics_demo_count']} 份完整物理执行及 {catalog['kinematic_preview_count']} 份运动学预演",page)
    page=re.sub(r"\d{4}-\d{2}-\d{2} (?:整理|更新)：\d+ 份(?:三视角|多视角)完整物理执行",
        f"{manifest['archived_at_utc'][:10]} 更新：{catalog['complete_robotics_demo_count']} 份多视角完整物理执行",page)
    (folder/"index.html").write_text(page)
    readme=(folder/"README.md").read_text()
    row=f"| {entry['title']} | [打开]({relative}/index.html) | 5 | {entry['scope']} |\n"
    readme=readme.replace("\n\n保留全部既有 MP4","\n"+row+"\n保留全部既有 MP4",1)
    readme=re.sub(r"^- `interlocked_claws`：.*\n","",readme,flags=re.MULTILINE)
    (folder/"README.md").write_text(readme)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--source",required=True);p.add_argument("--run-id",required=True)
    a=p.parse_args();print(archive(a.source,a.run_id))
