"""Verify and independently archive the trajectory-first eccentric-window demo."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
from importlib.metadata import version, PackageNotFoundError
import sys
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import ROOT
from .inverse_window import OUTPUT, SEED, save, sha
from .inverse_runtime import admitted

RUN_ID = "2026-09-17_eccentric_window_v1"
TASK = "hedgehog_in_cage"
CAMERAS = ("agentview", "front_oblique", "wrist")
TITLE = "刺球出笼 · 轨迹反推偏心斜窗笼"
SCOPE = "单臂预抓取开始；双指同时接触后辅助抓持，穿窗取出、搬运落桌、解除辅助、张爪撤离并自由静置。视频逐帧来自同一次连续物理执行。"


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_execution(folder):
    _, certificate = admitted(folder)
    robot = read(folder / "robot_audit.json")
    require(robot["passed"] and robot["certificate_sha256"] == sha(folder / "certificate.json"), "Stale robot audit")
    results = []
    for name, substeps in (("physics", 10), ("physics_substeps20", 20)):
        path = folder / name
        report, audit, rows = [read(path / filename) for filename in ("report.json", "audit.json", "trajectory.json")]
        require(report["passed"] and report["complete"] and report["grasp_released"] and audit["passed"], name + " did not finish")
        require(report["dt"] == .005 and report["substeps"] == substeps, "Unexpected time step")
        require(report["runner_sha256"] == sha(Path(__file__).with_name("inverse_runtime.py")), "Runtime source changed")
        require(report["asset_manifest_sha256"] == certificate["asset_manifest_sha256"] and report["ik_sha256"] == certificate["ik_sha256"], "Different physical instance")
        require(report["contact_gate"]["simultaneous_contact"] and not report["live_object_pose_overwrites"] and not report["live_robot_pose_overwrites"], "Execution contract changed")
        for filename, digest in audit["source_sha256"].items():
            require(sha(path / filename) == digest, "Stale actual-state audit")
        require(rows[0]["physics_step"] == 0 and rows[-1]["physics_step"] == report["physics_steps"], "Incomplete physical trace")
        require(rows[-1]["phase"] == "final_settle" and not rows[-1]["grasp_constraint_active"], "Release missing")
        results.append((report, audit, rows))
    a, b = results[0][2], results[1][2]
    displacement = float(np.linalg.norm(np.array(a[-1]["ball_position_m"])-b[-1]["ball_position_m"]))
    angle = float((Rotation.from_quat(a[-1]["ball_quaternion_xyzw"])*Rotation.from_quat(b[-1]["ball_quaternion_xyzw"]).inv()).magnitude())
    require(np.allclose(a[0]["robot_qpos"], b[0]["robot_qpos"], atol=1e-10), "Different initial robot state")
    require(np.allclose(a[0]["ball_position_m"], b[0]["ball_position_m"], atol=1e-10), "Different initial object state")
    # Both traces must independently pass. Endpoint differences are reported,
    # rather than imposing an arbitrary tolerance on settled contact equilibria.
    convergence = dict(passed=True, inner_steps_s=[.0005, .00025], outer_control_step_s=.005,
        final_position_difference_m=displacement, final_orientation_difference_deg=float(np.rad2deg(angle)),
        duration_difference_s=abs(a[-1]["time_s"]-b[-1]["time_s"]),
        scope="Two complete executions of the same instance at two physics substep sizes; not a parameter robustness study",
        reports={name:sha(folder/name/"report.json") for name in ("physics", "physics_substeps20")})
    save(folder / "time_step_comparison.json", convergence)
    return results[0], convergence


def verify_recording(folder, physical):
    report, _, rows = physical
    recording = folder / "recording"
    record = read(recording / "recording_report.json")
    frames = read(recording / "render_frames.json")
    require(record["passed"] and record["actual_physics_states"] and not record["kinematic_rehearsal"], "Not a physical recording")
    require(record["physics_steps"] == report["physics_steps"], "Different physical run")
    require(record["render_frames_sha256"] == sha(recording / "render_frames.json"), "Recording trace changed")
    require(record["asset_manifest_sha256"] == report["asset_manifest_sha256"], "Recording geometry changed")
    for filename, digest in record["source_physical_sha256"].items():
        require(sha(folder / "physics" / filename) == digest, "Stale recording source")
    require(frames[0]["source_trace_index"] == 0 and frames[-1]["source_trace_index"] == len(rows)-1, "Recording endpoint missing")
    require(len(frames) == record["frames"] == len(read(recording/"camera_poses.json")), "Camera frame count mismatch")
    previous = -1
    for frame in frames:
        index = frame["source_trace_index"]
        require(index > previous, "Recording time is not monotonic")
        require({k:v for k,v in frame.items() if k != "source_trace_index"} == rows[index], "Rendered state does not equal physics")
        previous = index
    require({r["phase"] for r in frames} == {r["phase"] for r in rows}, "A physical phase was omitted")
    videos = []
    for name in (*CAMERAS, "three_views"):
        path = recording / f"{name}.mp4"
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames,duration", "-of", "json", str(path)]))["streams"][0]
        numerator, denominator = map(int, probe["avg_frame_rate"].split("/"))
        require(int(probe["nb_read_frames"]) == len(frames), "Video frame count mismatch")
        require(numerator/denominator == record["fps"] and abs(float(probe["duration"])-record["duration_s"])<.001, "Video timing mismatch")
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-threads", "2", "-i", str(path), "-f", "null", "-"], check=True)
        videos.append(dict(camera=name, file=f"{RUN_ID}_{name}.mp4", sha256=sha(path), width=int(probe["width"]), height=int(probe["height"]), frames=len(frames), fps=record["fps"], duration_s=float(probe["duration"]), full_decode_passed=True))
    return record, videos


def profile_plot(folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    profile = read(folder / "inverse_profile.json")
    z = np.array(profile["z_knots_m"])*1000
    left, right = [np.rad2deg(profile[k]) for k in ("left_angle_rad", "right_angle_rad")]
    fig, ax = plt.subplots(figsize=(7.5, 4.5), layout="constrained")
    ax.fill_betweenx(z, left, right, color="#bfe1e5", label="Inferred asymmetric opening")
    ax.plot(left,z,color="#146779"); ax.plot(right,z,color="#146779")
    original = np.rad2deg(np.arcsin(.03/.0585))
    for side in (-1,1):
        ax.plot([side*original]*2,[-78,78],"--",color="#ba683f",label="Seed window straight section" if side==1 else None)
    ax.axvline(0,color="#a4adb4",lw=.6)
    ax.set(xlabel="Angle around cage axis (degrees)", ylabel="Height relative to cage center (mm)", title="Motion first: 3 mm side shift and -1 degree tilt")
    ax.legend(loc="lower center",fontsize=8); ax.grid(alpha=.15)
    fig.savefig(folder/"window_profile.png",dpi=160); plt.close(fig)


def playback_html(folder, record, comparison):
    cert, audit = read(folder/"certificate.json"), read(folder/"physics/audit.json")
    movie = lambda n: f"../../../demos/{TASK}/{RUN_ID}_{n}.mp4"
    names = {"agentview":"全景", "front_oblique":"斜前近景", "wrist":"腕部视角"}
    videos = "".join(f'<figure><figcaption>{names[n]} · {n}</figcaption><video data-sync controls preload="metadata" poster="recording/pregrasp_contact_{n}.jpg" src="{movie(n)}"></video></figure>' for n in CAMERAS)
    phase_names = dict(pregrasp_contact="预抓取起点", hold_grasp="接触后稳固抓持", align_with_verified_path="对齐路径",
        rotate_and_extract="调整并提取", eccentric_window_turn="偏心穿窗转动", withdraw="退出笼体",
        carry_to_release_location="搬运", orient_for_placement="调整落桌姿态", lower_to_table="降低至桌面",
        release="松爪并撤离", final_settle="自由静置")
    stages = "".join(f'<button onclick="seek({p["time_s"]})">{escape(phase_names.get(p["name"], p["name"]))} · {p["time_s"]:.1f}s</button>' for p in record["phases"])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title>
<style>body{{max-width:1320px;margin:30px auto;padding:0 24px;background:#edf2f3;color:#21353e;font:16px/1.7 system-ui}}section{{background:white;padding:24px;border-radius:14px;margin:22px 0}}video,img{{width:100%;border-radius:8px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}}figure{{margin:0}}button{{padding:9px 13px;margin:4px;cursor:pointer;border:0;border-radius:5px;background:#dcecef}}a{{color:#176d80}}.note{{padding:14px;background:#fff2d9;border-radius:8px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #dde5e8}}</style>
<h1>{TITLE}</h1><p>路线一 · 先改变已解运动与 IK，再由扫掠空间生成新窗口 · {record['duration_s']:.2f} 秒 · 单臂三视角</p>
<p class="note">{SCOPE} 起点已经位于 S2 刺的预抓取位置；抓持期间使用接触触发的辅助约束，落桌后解除。笼子固定在底座上，因此此实例使用单臂即可完成。当前几何为工程重建与新设计。</p>
<section><h2>完整流程</h2><video controls preload="metadata" src="{movie('three_views')}"></video><p>三视角合成视频；下方提供三个独立高清视角。</p><button onclick="playAll()">同步播放</button><button onclick="pauseAll()">全部暂停</button><button onclick="seek(0)">回到起点</button><div class="grid">{videos}</div><p>{stages}</p></section>
<section><h2>从运动到新结构</h2><div class="grid"><div><p>从已完成的 CLASSIC 十刺重建实例出发，对中段路径施加最大 3 mm 侧移及 −1° 倾斜，先求完整连续 IK，再用刺球与夹指扫掠体反推笼窗两侧边界。保留其余窗口、上下圈和相邻笼条，刺球本体不变。</p><p>当前方案已证实这条新路线可执行；直线拉出会碰撞。原路线在新笼中的采样检查也仍能通过，因此这是一种可解结构变体，尚未证明新动作不可省略或解法唯一。</p></div><figure><img src="window_profile.png"><figcaption>窗口角度—高度剖面。橙色虚线仅标出原窗口的直边段；新边界由动作与夹指空间共同约束。</figcaption></figure></div></section>
<section><h2>验证结果</h2><table><tr><th>检查</th><th>结果</th></tr><tr><td>规划路径连续几何间隙下界</td><td>{cert['continuous_clearance_lower_bound_m']*1000:.3f} mm</td></tr><tr><td>实际物理状态插值的间隙下界</td><td>{audit['continuous_interpolation_clearance_lower_bound_m']*1000:.3f} mm</td></tr><tr><td>物理子步复测</td><td>0.5 ms、0.25 ms 两次完整执行分别通过；末态位置差 {comparison['final_position_difference_m']*1000:.3f} mm</td></tr><tr><td>解除抓持后最后两秒漂移</td><td>{audit['final_2s_drift_m']*1000:.5f} mm</td></tr><tr><td>录制状态对应</td><td>{record['frames']} 帧 / {record['fps']} fps，各视角逐帧对应同一次物理轨迹中的真实状态</td></tr></table><p>物理执行使用关节控制，没有逐帧改写物体姿态；渲染阶段读取保存状态生成视频。两种子步验证限于这个实例，尚未测试随机初态、摩擦变化或无辅助抓持。</p>
<p><a href="certificate.json">规划几何证据</a> · <a href="robot_audit.json">机器人检查</a> · <a href="physics/report.json">物理执行</a> · <a href="physics/audit.json">实际状态检查</a> · <a href="physics_substeps20/audit.json">更细子步检查</a> · <a href="time_step_comparison.json">子步对照</a> · <a href="recording/recording_report.json">录制报告</a> · <a href="archive_manifest.json">归档清单</a> · <a href="../../index.html">全部 Demo</a></p></section>
<script>const v=[...document.querySelectorAll('[data-sync]')];const overview=document.querySelector('video:not([data-sync])');function pauseAll(){{[overview,...v].forEach(x=>x.pause())}}function seek(t){{pauseAll();[overview,...v].forEach(x=>x.currentTime=t)}}function playAll(){{overview.pause();const t=v[0].currentTime;v.forEach(x=>{{x.currentTime=t;x.play()}})}}v[0].addEventListener('timeupdate',()=>{{if(!v[0].paused)v.slice(1).forEach(x=>{{if(Math.abs(x.currentTime-v[0].currentTime)>.15)x.currentTime=v[0].currentTime}})}});</script></html>'''


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.paths=[]
    def handle_starttag(self, tag, attrs):
        self.paths.extend(v for k,v in attrs if k in ("href","src","poster") and v and not v.startswith(("http:","https:","#","data:")))


def update_catalog(entry):
    base=ROOT/"runs/demo_metadata"
    # Read immediately before writing: other task sessions can add entries.
    catalog=read(base/"catalog.json")
    require(not any(e.get("directory")==entry["directory"] for e in catalog["entries"]), "Entry already archived")
    catalog["entries"].append(entry)
    catalog["complete_robotics_demo_count"]=sum(bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"])
    catalog["archived_at_utc"]=datetime.now(timezone.utc).isoformat()
    save(base/"catalog.json",catalog)
    page=(base/"index.html").read_text()
    section=f'<section><h2><a href="{entry["index"]}">{TITLE}</a></h2><p><strong>完整物理执行 · 含辅助抓持并最终释放</strong> · {entry["duration_s"]:.2f} 秒 · 三路同步视角</p><p>{SCOPE}</p><p>规划路径反推窗口；0.5 ms / 0.25 ms 物理子步均通过。</p><p><a href="{entry["index"]}">打开播放页</a> · <a href="{entry["directory"]}/archive_manifest.json">来源与文件清单</a></p></section>'
    marker='<section><h2>本次暂未收录'
    if marker in page: page=page.replace(marker,section+marker,1)
    else: page=page.replace('</body>',section+'</body>',1)
    page=re.sub(r'当前保留 \d+ 份完整物理执行',f'当前保留 {catalog["complete_robotics_demo_count"]} 份完整物理执行',page,count=1)
    (base/"index.html").write_text(page)
    readme=(base/"README.md").read_text(); row=f'| {TITLE} | [打开]({entry["index"]}) | 4 | {SCOPE} |\n'
    pos=readme.index('\n\n',readme.index('| 环境 |'))
    (base/"README.md").write_text(readme[:pos]+"\n"+row.rstrip()+readme[pos:])


def archive(folder):
    folder=Path(folder); physical, comparison=verify_execution(folder); record,videos=verify_recording(folder,physical)
    destination=ROOT/"runs/demo_metadata"/TASK/RUN_ID
    video_dir=ROOT/"runs/demos"/TASK
    require(not destination.exists(), "Preserve existing archive")
    require(not any((video_dir/v["file"]).exists() for v in videos), "Preserve existing archived video")
    profile_plot(folder)
    exclude=shutil.ignore_patterns("attempts", "*.mp4", "*.log", "profile_rejection.json", "index.html")
    shutil.copytree(folder,destination,ignore=exclude)
    sources=destination/"provenance"; sources.mkdir()
    shutil.copy2(ROOT/"docs/develop/tasks/hedgehog_in_cage_inverse_window_zh.md",destination/"README.md")
    packages={}
    for name in ("genesis-world","torch","numpy","scipy","mujoco","python-fcl","trimesh","manifold3d","omegaconf","imageio","Pillow"):
        try: packages[name]=version(name)
        except PackageNotFoundError: packages[name]="not installed under this distribution name"
    save(sources/"runtime_versions.json",dict(python=sys.version,packages=packages))
    for filename in ("inverse_window.py","inverse_runtime.py","inverse_archive.py","geometry.py","plan_escape.py","stability.py"):
        shutil.copy2(Path(__file__).with_name(filename),sources/filename)
    seed=sources/"seed";seed.mkdir()
    for filename in ("robot_escape_plan.npz","robot_escape_plan.json","escape_upper.json","robot_release_plan.json","extraction_config.yaml"):
        shutil.copy2(SEED/filename,seed/filename)
    shutil.copy2(SEED/"assets/template.json",seed/"template.json")
    video_dir.mkdir(parents=True,exist_ok=True)
    for video in videos:
        source=folder/"recording"/(video["camera"]+".mp4"); target=video_dir/video["file"]
        shutil.copy2(source,target)
        require(not target.is_symlink() and source.stat().st_ino!=target.stat().st_ino and sha(target)==video["sha256"], "Video copy failed")
        video["path"]="../../../demos/"+TASK+"/"+video["file"]
    (destination/"index.html").write_text(playback_html(destination,record,comparison))
    parser=Links();parser.feed((destination/"index.html").read_text())
    missing=[p for p in parser.paths if p!='archive_manifest.json' and not (destination/p).exists()]
    require(not missing, "Broken playback links: "+str(missing))
    save(destination/"delivery_checks.json",dict(passed=True,independent_video_copies=True,full_video_decode=True,
        synchronized_cameras=True,exact_physical_state_correspondence=True,local_links_passed=True,
        two_complete_physics_executions=True,metadata_has_no_symlinks=not any(p.is_symlink() for p in destination.rglob('*'))))
    files={str(p.relative_to(destination)):sha(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    manifest=dict(schema_version=1,task_id=TASK,instance_id="eccentric_window_v1",source_directory=str(folder.relative_to(ROOT)),
        archived_at_utc=datetime.now(timezone.utc).isoformat(),recording_scope=SCOPE,
        classification="physical_execution_with_grasp_assistance",pregrasp_start=True,grasp_released=True,
        duration_s=record["duration_s"],cameras=list(CAMERAS),videos=videos,metadata_sha256=files,
        geometry_sha256=sha(destination/"assets/sha256.json"),physical_trace_sha256=sha(destination/"physics/trajectory.json"),
        limitations=["Fixed cage and pregrasp start", "Contact-triggered grasp assistance until placement", "Original route remains compatible in sampled check", "No proof of unique solution", "Two time-step executions, not a robustness sweep"])
    save(destination/"archive_manifest.json",manifest)
    for relative,digest in files.items():require(sha(destination/relative)==digest,"Archive metadata checksum failed")
    entry=dict(task_id=TASK,title=TITLE,variant="eccentric_window_v1",classification=manifest["classification"],
        counts_as_complete_robotics_demo=True,duration_s=record["duration_s"],cameras=list(CAMERAS),scope=SCOPE,
        source_directory=manifest["source_directory"],directory=f"{TASK}/{RUN_ID}",index=f"{TASK}/{RUN_ID}/index.html",
        archived_at_utc=manifest["archived_at_utc"],video_directory=f"../demos/{TASK}",
        video_files={v["camera"]+".mp4":f'../demos/{TASK}/{v["file"]}' for v in videos})
    update_catalog(entry)
    (folder/"index.html").write_text(f'<!doctype html><meta charset="utf-8"><a href="../../../demo_metadata/{TASK}/{RUN_ID}/index.html">偏心斜窗笼完整流程 Demo · 独立归档播放页</a>')
    print(json.dumps(dict(passed=True,index=str(destination/"index.html"),videos=videos),ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=OUTPUT)
    archive(parser.parse_args().output)


if __name__=="__main__":main()
