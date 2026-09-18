"""Retain a verified continuous physical execution and its independent videos."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

from .qualification import summarize

ROOT = Path(__file__).resolve().parents[3]
CAMERAS = {"cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"}


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
    if not (report.get("full_threading_verified") and report.get("passed")
            and report.get("complete_physics_suite_passed") and video_check.get("passed")
            and qualification["passed"]):
        raise ValueError("Only a verified full physical execution may be archived as complete")
    streams = video_check["streams"]
    if not CAMERAS <= streams.keys() or len({s["decoded_frames"] for s in streams.values()}) != 1:
        raise ValueError("Four synchronized ALOHA camera streams are required")
    metadata_root = ROOT/"runs/demo_metadata"
    metadata = metadata_root/"rope_threading"/run_id
    videos = ROOT/"runs/demos/rope_threading"
    if metadata.exists() or any(videos.glob(run_id+"_*.mp4")):
        raise FileExistsError("Archive destination already exists; choose a new identifier")
    for name, stream in streams.items():
        if digest(source/f"{name}.mp4") != stream["sha256"]:
            raise ValueError(f"Video changed after validation: {name}")
    shutil.copytree(source, metadata, ignore=shutil.ignore_patterns("*.mp4", "STOP", "__pycache__"))
    evidence = metadata/"physics_qualification"
    evidence.mkdir()
    save(evidence/"qualification.json", qualification)
    if (qualification_folder/"cases.json").exists():
        shutil.copy2(qualification_folder/"cases.json", evidence/"cases.json")
    for relative in qualification["case_directories"].values():
        shutil.copytree(qualification_folder/relative, evidence/relative,
                        ignore=shutil.ignore_patterns("__pycache__", "STOP", "partial_*"))
    if not summarize(evidence)["passed"]:
        raise RuntimeError("Copied qualification evidence did not validate")
    reference = ROOT/"runs/environment-solvability/rope_threading/reference_motion_v1"
    shutil.copytree(reference, metadata/"motion_reference")
    shutil.copy2(ROOT/"assets/tasks/rope_threading/wang_reference_v1/LICENSE", metadata/"reference_LICENSE")
    videos.mkdir(parents=True, exist_ok=True)
    copied_videos = {}
    page = (metadata/"index.html").read_text()
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
        relative = f"../../../demos/rope_threading/{destination.name}"
        page = page.replace(f'src="{name}.mp4"', f'src="{relative}"')
        copied_videos[name] = dict(path=str(destination.relative_to(ROOT)), sha256=stream["sha256"],
            frames=count, fps=fps, duration_s=count/fps)
    (metadata/"index.html").write_text(page)
    scope = ("从参考待命初态开始，完整执行 51 阶段动作；关节位置控制驱动机器人，FEM+IPC 重新模拟绳子。"
             "双指实际接触后辅助抓持，6 次抓取与全部释放；三环材料顺序通过，双端落桌、双臂退出并静置。")
    save(metadata/"archive_manifest.json", dict(schema_version=2, task_id="rope_threading", variant="wang_reference_v1",
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        original_directory=str(source.relative_to(ROOT)), scope=scope,
        reference_speed=report["reference_speed"], simulated_seconds=report["simulated_seconds"],
        cameras=list(streams), videos=copied_videos, same_continuous_rollout=True,
        archived_at_utc=datetime.now(timezone.utc).isoformat(),
        files={str(p.relative_to(ROOT)): digest(p) for p in sorted(metadata.rglob("*")) if p.is_file()}))
    local_links = re.findall(r'(?:href|src)="([^"#]+)"', page)
    for target in local_links:
        if not target.startswith(("http:", "https:")) and not (metadata/target).resolve().is_file():
            raise RuntimeError(f"Missing archived playback dependency: {target}")
    relative = str(metadata.relative_to(metadata_root))
    entry = dict(task_id="rope_threading", title="绳穿三环 · ALOHA 完整物理执行", variant="wang_reference_v1",
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        duration_s=next(iter(copied_videos.values()))["duration_s"], cameras=list(streams), scope=scope,
        source_directory=str(source.relative_to(ROOT)), directory=relative, index=relative+"/index.html",
        video_directory="../demos/rope_threading",
        video_files={name+".mp4": "../demos/rope_threading/"+Path(item["path"]).name for name, item in copied_videos.items()},
        archived_at_utc=datetime.now(timezone.utc).isoformat())
    catalog_path = metadata_root/"catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["entries"].append(entry)
    catalog["complete_robotics_demo_count"] = sum(bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"])
    catalog["archived_at_utc"] = entry["archived_at_utc"]
    save(catalog_path, catalog)
    index = metadata_root/"index.html"
    text = re.sub(r'<tr><td>rope_threading</td><td>.*?</td></tr>', '', index.read_text())
    card = f'<section><h2><a href="{relative}/index.html">{entry["title"]}</a></h2><p>{html.escape(scope)}</p>'
    card += f'<p>{entry["duration_s"]:.2f} 秒 · {len(streams)} 路同步视角 · <a href="{relative}/archive_manifest.json">独立副本与证据</a></p></section>'
    index.write_text(text.replace("</body>", card+"</body>") if "</body>" in text else text+card)
    readme = metadata_root/"README.md"
    with readme.open("a") as handle:
        handle.write(f'\n绳穿三环：[完整物理执行]({relative}/index.html)，{len(streams)} 路同步视频。{scope}\n')
    return metadata/"index.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("qualification_folder", type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(archive(args.source, args.qualification_folder, args.run_id))


if __name__ == "__main__":
    main()
