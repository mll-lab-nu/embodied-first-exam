"""Complete recordings and independent archives of certified horseshoe variants."""
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CAMERAS = ("cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist")
VIDEOS = (*CAMERAS, "oblique", "detail", "four_views")
SCOPE = "预抓取开始，完整运动学预演，physics_steps=0；换抓采用运动学接触假设，未验证力驱动执行。"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n")


def video_directory(variant):
    """Keep the initial demo and each new variant in separate video folders."""
    import re
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", variant):
        raise ValueError("Variant ID must be a single filename component")
    name = "original" if variant == "tutorial_solvable_v3" else variant
    return ROOT/"runs/demos/horseshoe_ring"/name


def prepare_recording(source, output):
    """Copy the exact instance evidence; never overwrite an earlier recording."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Recording directory already exists; choose a new output")
    motion = json.loads((source/"robot_motion.json").read_text())
    proof = json.loads((source/"geometry_certificate.json").read_text())
    trace = json.loads((source/"ik_trace.json").read_text())
    from .ik_trace import command_hash
    if not (proof["passed"] and proof["goal"]["separated"]
            and motion["report"]["sampled_robot_scene_clearance_passed"]
            and motion["report"]["physics_steps"] == 0
            and command_hash(motion) == trace["command_sha256"]
            and hashlib.sha256(json.dumps(motion["frames"], sort_keys=True).encode()).hexdigest()
                == proof["robot_frames_sha256"]):
        raise ValueError("Motion is not the certified complete variant")
    output.mkdir(parents=True)
    copied = {}
    for src in source.iterdir():
        if src.is_file() and src.suffix in (".json", ".csv", ".yaml"):
            shutil.copy2(src, output/src.name)
            copied[src.name] = sha(src)
    shutil.copytree(source/"geometry_evidence", output/"geometry_evidence")
    save(output/"recording_source.json", dict(source_directory=str(source.relative_to(ROOT)),
        source_files_sha256=copied, command_sha256=trace["command_sha256"],
        classification="kinematic_rehearsal", scope=SCOPE))


def write_instance_page(folder, video_files=None):
    folder = Path(folder)
    report = json.loads((folder/"replay_report.json").read_text())
    result = json.loads((folder/"result.json").read_text())
    p, geometry = result["proposal"], result["geometry"]
    videos = video_files or {n: f"{n}.mp4" for n in VIDEOS}
    def video(name, sync=False):
        poster = "detail" if name == "four_views" else name
        return (f'<video {"class=sync" if sync else ""} controls preload="metadata" '
                f'src="{escape(videos[name], quote=True)}" poster="initial_{poster}.png"></video>')
    buttons = "".join(f'<button onclick="seekAll({phase["time_s"]})">{escape(phase["name"])}</button>'
                      for phase in report["phases"])
    cards = "".join(f'<figure>{video(n, True)}<figcaption>{n}</figcaption></figure>' for n in CAMERAS)
    (folder/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe · {escape(p['id'])}</title>
<style>body{{max-width:1280px;margin:32px auto;padding:0 22px;font:16px/1.7 system-ui;background:#eff2f5;color:#22313f}}
section{{background:white;padding:22px;margin:22px 0;border-radius:12px}}video{{width:100%}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}figure{{margin:0}}button{{padding:10px;margin:5px;cursor:pointer}}
a{{color:#146a94}}.note{{background:#fff0ca;padding:14px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}</style>
<h1>Horseshoe Ring · {escape(p['id'])}</h1>
<p class="note">{SCOPE} 图像来自此变体在 Genesis 中逐帧回放的真实渲染。</p>
<p>尺度 {result['scene']['scale_ratio']:.2f}× · 初始偏航 {p['yaw_deg']:+g}° · 折合摆动 {p['fold_roll_deg']:+g}° ·
圆环抓点 {p['ring_grasp_shift_deg']:+g}° · 链环族 {escape(p['chain_family'])}。</p>
<section><h2>完整取环过程 · 近景</h2>{video('detail')}
<div>{buttons}</div><p>{report['frames']} 帧 / {report['fps']} FPS / {report['duration_s']:.2f} 秒。
覆盖翻转、折合、双臂交接、左臂换抓圆环、取出和最终分离。初态与终态接近种子是因为沿用同一解法族；空手换抓路线重新规划。</p></section>
<section><h2>双臂动作全景</h2>{video('oblique')}</section>
<section><h2>ALOHA 四路同步画面</h2>{video('four_views')}
<p><button onclick="toggleViews()">四路原图一起播放 / 暂停</button></p><div class="grid">{cards}</div></section>
<section><h2>此实例的验证与数据</h2><p>几何路径间隙下界 {geometry['minimum_clearance_lower_bound_m']*1000:.4f} mm；
终态分离 {geometry['goal']['separation_m']*1000:.2f} mm。机器人碰撞检查为逐帧采样，不代表连续机器人或动力学验证。</p>
<p><a href="replay_report.json">录像报告</a> · <a href="geometry_certificate.json">几何证书</a> ·
<a href="verification.json">轨迹与场景一致性</a> · <a href="camera_report.json">相机配置</a> ·
<a href="ik_trace.csv">IK CSV</a> · <a href="robot_motion.json">逐帧状态</a> · <a href="config.yaml">场景配置</a></p></section>
<script>const views=[...document.querySelectorAll('.sync')];
function seekAll(t){{document.querySelectorAll('video').forEach(v=>v.currentTime=t)}}
function toggleViews(){{const go=views[0].paused,t=views[0].currentTime;views.forEach(v=>{{v.currentTime=t;if(go)v.play().catch(()=>{{}});else v.pause()}})}}
views[0].addEventListener('seeked',()=>views.slice(1).forEach(v=>{{if(Math.abs(v.currentTime-views[0].currentTime)>.15)v.currentTime=views[0].currentTime}}));
</script></html>''')


def check_video(path, frames, fps):
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames",
        "-select_streams", "v:0", "-show_entries",
        "stream=nb_read_frames,avg_frame_rate,duration,width,height", "-of", "json", str(path)]))
    stream = probe["streams"][0]
    num, den = map(int, stream["avg_frame_rate"].split("/"))
    if (int(stream["nb_read_frames"]) != frames or abs(num/den-fps) > 1e-9
            or abs(float(stream["duration"])-frames/fps) > .001):
        raise ValueError(f"Incomplete or unsynchronized video: {path}")
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-threads", "1",
        "-i", str(path), "-f", "null", "-"], check=True, capture_output=True)
    if decoded.stderr:
        raise ValueError(f"Video decode errors: {decoded.stderr.decode()}")
    return dict(stream, decoded=True, sha256=sha(path))


def check_links(page):
    from html.parser import HTMLParser
    from urllib.parse import urlsplit, unquote
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values = []
        def handle_starttag(self, tag, attrs):
            self.values.extend(value for key, value in attrs if key in ("href", "src") and value)
    parser = Links()
    parser.feed(Path(page).read_text())
    links = [unquote(urlsplit(v).path) for v in parser.values if not urlsplit(v).scheme]
    missing = [v for v in links if not (Path(page).parent/v).exists()]
    if missing:
        raise ValueError(f"Missing local links in {page}: {missing}")
    return dict(passed=True, checked=len(links))


def archive(source, run_id):
    """Verify a whole recording, then retain independent videos and all evidence."""
    import re
    from omegaconf import OmegaConf
    from .trace_scene_verification import verify
    source = Path(source).resolve()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
        raise ValueError("Run ID must be a single filename component")
    report = json.loads((source/"replay_report.json").read_text())
    motion = json.loads((source/"robot_motion.json").read_text())
    trace = json.loads((source/"ik_trace.json").read_text())
    provenance = json.loads((source/"recording_source.json").read_text())
    if not (report["physics_steps"] == 0 and report["sampled_robot_scene_clearance_passed"]
            and report["frames"] == len(motion["frames"]) and report["fps"] == motion["fps"]
            and report["maximum_genesis_pad_tracking_error_m"] < .0005
            and all(report[k] == v for k, v in motion["report"].items())
            and sha(source/"robot_motion.json") == provenance["source_files_sha256"]["robot_motion.json"]):
        raise ValueError("Recording differs from its checked input or lacks complete tracking")
    if len(json.loads((source/"camera_poses.json").read_text())) != report["frames"]:
        raise ValueError("Missing full camera pose trace")
    verification = verify(source)
    checks = {n: check_video(source/f"{n}.mp4", report["frames"], report["fps"]) for n in VIDEOS}
    meta_root = ROOT/"runs/demo_metadata"
    meta = meta_root/"horseshoe_ring"/run_id
    proposal = json.loads((source/"proposal.json").read_text())
    video_dir = video_directory(proposal["id"])
    targets = {n: video_dir/f"{run_id}_kinematic_{n}.mp4" for n in VIDEOS}
    if meta.exists() or any(p.exists() for p in targets.values()):
        raise ValueError("Archive already exists; choose a new run ID")
    video_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, meta, ignore=shutil.ignore_patterns("*.mp4"))
    cfg = OmegaConf.load(meta/"config.yaml")
    cfg.task.template_path = str(meta/"template.json")
    cfg.run.output = str(meta)
    OmegaConf.save(cfg, meta/"config.yaml", resolve=True)
    evidence_sources = meta/"runner_sources"
    evidence_sources.mkdir()
    for name in ("aloha_demo.py", "variant_video.py", "trace_scene_variants.py", "trace_scene_verification.py"):
        shutil.copy2(Path(__file__).with_name(name), evidence_sources/name)
    videos = {}
    for name, dst in targets.items():
        src = source/f"{name}.mp4"
        shutil.copy2(src, dst)
        if sha(dst) != checks[name]["sha256"] or dst.is_symlink() or dst.stat().st_ino == src.stat().st_ino:
            raise ValueError("Video archive is not an independent identical copy")
        videos[name] = os.path.relpath(dst, meta)
    write_instance_page(meta, videos)
    save(meta/"verification.json", verify(meta))
    validation = dict(passed=True, video_checks=checks, geometry_and_trace=verification,
        local_links=check_links(meta/"index.html"), independent_video_copies=True,
        command_sha256=trace["command_sha256"], physical_execution_verified=False,
        maximum_genesis_pad_tracking_error_m=report["maximum_genesis_pad_tracking_error_m"])
    save(meta/"archive_validation.json", validation)
    files = []
    for path in sorted([p for p in meta.rglob("*") if p.is_file()]+list(targets.values())):
        files.append(dict(path=os.path.relpath(path, meta), bytes=path.stat().st_size, sha256=sha(path)))
    entry = dict(task_id="horseshoe_ring", title=f"马蹄环变体 · {proposal['id']}", variant=proposal["id"],
        classification="kinematic_rehearsal", counts_as_complete_robotics_demo=False,
        duration_s=report["duration_s"], frames=report["frames"], fps=report["fps"], cameras=list(CAMERAS),
        scope=SCOPE, source_directory=str(source.relative_to(ROOT)),
        archived_at_utc=datetime.now(timezone.utc).isoformat(), command_sha256=trace["command_sha256"])
    manifest = dict(entry, schema_version=2, directory=str(meta.relative_to(ROOT)), index="index.html",
        video_directory=os.path.relpath(video_dir, meta), video_files={f"{n}.mp4":v for n,v in videos.items()},
        files=files, file_count=len(files), total_bytes=sum(f["bytes"] for f in files),
        manifest_note="File and video paths are relative to this manifest; manifest excludes itself.")
    save(meta/"archive_manifest.json", manifest)
    entry.update(directory=str(meta.relative_to(meta_root)), index=str((meta/"index.html").relative_to(meta_root)),
        video_directory=os.path.relpath(video_dir, meta_root),
        video_files={f"{n}.mp4":os.path.relpath(p, meta_root) for n,p in targets.items()})
    catalog = json.loads((meta_root/"catalog.json").read_text())
    catalog["entries"].append(entry)
    catalog["complete_robotics_demo_count"] = sum(e["counts_as_complete_robotics_demo"] for e in catalog["entries"])
    catalog["kinematic_preview_count"] = sum(e["classification"] == "kinematic_rehearsal" for e in catalog["entries"])
    catalog["archived_at_utc"] = entry["archived_at_utc"]
    save(meta_root/"catalog.json", catalog)
    page = (meta_root/"index.html").read_text()
    page = re.sub(r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演。",
        f"当前保留 {catalog['complete_robotics_demo_count']} 份完整物理执行及 {catalog['kinematic_preview_count']} 份运动学预演。", page)
    card = (f'<section><h2><a href="{entry["index"]}">{escape(entry["title"])}</a></h2>'
        f'<p>{SCOPE}</p><p>{report["duration_s"]:.2f} 秒 · 四路同步观测、全景和近景。</p>'
        f'<p><a href="{entry["index"]}">完整播放页</a> · '
        f'<a href="{entry["directory"]}/archive_manifest.json">来源与哈希清单</a></p></section>')
    page = page.replace('<section><h2>本次暂未收录</h2>', card+'<section><h2>本次暂未收录</h2>')
    (meta_root/"index.html").write_text(page)
    readme = (meta_root/"README.md").read_text()
    row = f'| {entry["title"]} | [打开]({entry["index"]}) | 7 | {SCOPE} |\n'
    readme = readme.replace("\n保留全部既有 MP4", row+"\n保留全部既有 MP4")
    (meta_root/"README.md").write_text(readme)
    print(f"Archived and verified: {meta}", flush=True)
    return meta


def build_comparison(review, archives, run_id):
    """Compose synchronized full-length views; retain provenance for every tile."""
    review = Path(review).resolve()
    folders = [ROOT/"runs/demo_metadata/horseshoe_ring/2026-09-16_aloha_full", *map(Path, archives)]
    if len(folders) != 4:
        raise ValueError("Expected a seed and three separately verified variants")
    meta = ROOT/"runs/demo_metadata/horseshoe_ring"/run_id
    video_dir = video_directory("comparisons")
    targets = {view: video_dir/f"{run_id}_kinematic_comparison_{view}.mp4"
               for view in ("oblique", "detail")}
    if meta.exists() or any(p.exists() for p in targets.values()):
        raise ValueError("Comparison already exists; choose a new run ID")
    manifests = [json.loads((p/"archive_manifest.json").read_text()) for p in folders]
    reports = [json.loads((p/"replay_report.json").read_text()) for p in folders]
    frames, fps = reports[0]["frames"], reports[0]["fps"]
    if not all(r["frames"] == frames and r["fps"] == fps for r in reports):
        raise ValueError("Comparison recordings must have matching timelines")
    meta.mkdir(parents=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    labels = ["Seed - original", "Compact - 0.96x", "Wide - 1.04x", "Longer - new grasp"]
    sources, checks = {}, {}
    for view, target in targets.items():
        clips = [(folder/m["video_files"][f"{view}.mp4"]).resolve() for folder,m in zip(folders,manifests)]
        sources[view] = [dict(path=os.path.relpath(p,meta), sha256=sha(p), label=label)
                         for p,label in zip(clips,labels)]
        filters = [f"[{i}:v]setpts=PTS-STARTPTS,scale=640:360,setsar=1,"
            f"drawbox=x=0:y=0:w=iw:h=28:color=0x142029:t=fill,"
            f"drawtext=text='{label}':fontcolor=white:fontsize=17:x=10:y=5[v{i}]"
            for i,label in enumerate(labels)]
        filters.append("[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|640_0|0_360|640_360:shortest=1[v]")
        command = ["ffmpeg", "-v", "error", "-n", "-filter_complex_threads", "2"]
        for clip in clips:
            command.extend(["-threads", "1", "-i", str(clip)])
        command.extend(["-filter_complex", ";".join(filters), "-map", "[v]", "-an", "-c:v", "libx264",
                        "-preset", "fast", "-crf", "19", "-threads", "2", "-movflags", "+faststart", str(target)])
        subprocess.run(command, check=True)
        checks[view] = check_video(target, frames, fps)
    videos = {n: os.path.relpath(p, meta) for n,p in targets.items()}
    links = "".join(f'<li><a href="{os.path.relpath(folder/"index.html",meta)}">{escape(label)}：完整独立播放页与四路相机</a></li>'
                    for folder,label in zip(folders,labels))
    (meta/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe · 四组完整动态对照</title>
<style>body{{max-width:1280px;margin:32px auto;padding:0 22px;font:16px/1.7 system-ui;background:#eff2f5;color:#22313f}}
video{{width:100%}}section{{background:white;padding:22px;margin:22px 0;border-radius:12px}}button{{padding:10px;margin:4px}}a{{color:#146a94}}</style>
<h1>原版与三个变体 · 完整动态对照</h1><p>左上：原版；右上：compact；左下：wide；右下：longer。</p>
<p>四格按同一时间轴同步，完整 {frames/fps:.2f} 秒。三组沿用同一解法族，尺寸和初始角度变化较小；
主要动作差别在双臂交接与空手换抓。全部为运动学预演，尚未验证力驱动执行。</p>
<p><button onclick="seek(21)">21 秒：交接开始</button><button onclick="seek(29.67)">29.7 秒：右臂路线差异</button>
<button onclick="seek(37.17)">37.2 秒：左臂换抓</button><button onclick="seek(45.33)">45.3 秒：左臂路线差异</button>
<button onclick="seek(52.08)">52.1 秒：脱环</button></p>
<section><h2>双臂动作全景</h2><video controls preload="metadata" src="{videos['oblique']}"></video></section>
<section><h2>谜题操作近景</h2><video controls preload="metadata" src="{videos['detail']}"></video></section>
<section><h2>各组完整视频</h2><ul>{links}</ul><p><a href="archive_manifest.json">拼接来源与哈希</a> ·
<a href="archive_validation.json">完整帧数与解码检查</a></p></section>
<script>function seek(t){{document.querySelectorAll('video').forEach(v=>v.currentTime=t)}}</script></html>''')
    validation = dict(passed=True, frames=frames, fps=fps, video_checks=checks,
        scope="Synchronized comparison of separately recorded full kinematic runs, not one physical execution")
    save(meta/"archive_validation.json", validation)
    save(meta/"archive_manifest.json", dict(schema_version=2, task_id="horseshoe_ring",
        classification="kinematic_comparison", counts_as_complete_robotics_demo=False,
        source_directories=[str(p.relative_to(ROOT)) for p in folders], scope=validation["scope"],
        duration_s=frames/fps, frames=frames, fps=fps, inputs=sources,
        video_files=videos, files=[dict(path=os.path.relpath(p,meta),bytes=p.stat().st_size,sha256=sha(p))
            for p in [*targets.values(),meta/"index.html",meta/"archive_validation.json"]]))
    check_links(meta/"index.html")
    registry = dict(comparison_index=os.path.relpath(meta/"index.html",review),
        videos={n:os.path.relpath(p,review) for n,p in targets.items()}, frames=frames, fps=fps,
        instances=[dict(id=m["variant"], index=os.path.relpath(folder/"index.html",review),
                        video=os.path.relpath((folder/m["video_files"]["detail.mp4"]).resolve(),review))
                   for folder,m in zip(folders[1:],manifests[1:])])
    save(review/"video_demos.json",registry)
    meta_root = ROOT/"runs/demo_metadata"
    index = str((meta/"index.html").relative_to(meta_root))
    catalog = json.loads((meta_root/"catalog.json").read_text())
    catalog.setdefault("comparisons", []).append(dict(task_id="horseshoe_ring", index=index,
        classification="kinematic_comparison", counts_as_complete_robotics_demo=False,
        duration_s=frames/fps, source_archives=[str(p.relative_to(meta_root)) for p in folders]))
    save(meta_root/"catalog.json", catalog)
    page = (meta_root/"index.html").read_text()
    card = (f'<section><h2><a href="{index}">马蹄环 · 原版与三个变体完整动态对照</a></h2>'
            '<p>四格同步比较全景与近景，重点观察双臂交接和换抓路线；所有来源均为完整运动学预演。</p></section>')
    page = page.replace('<section><h2>本次暂未收录</h2>',card+'<section><h2>本次暂未收录</h2>')
    (meta_root/"index.html").write_text(page)
    readme = (meta_root/"README.md").read_text()
    readme += f'\n[马蹄环：原版与三个变体的完整动态对照]({index})：四格同步全景 / 近景，69.083 秒；由独立运动学录像拼接，不计为新增物理执行。\n'
    (meta_root/"README.md").write_text(readme)
    return meta


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    archive(args.source, args.run_id)
