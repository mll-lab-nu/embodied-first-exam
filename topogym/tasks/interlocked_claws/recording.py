"""Render one complete recorded run into synchronized ALOHA observation videos."""
import argparse
from contextlib import ExitStack
import hashlib
from html import escape
import json
from pathlib import Path
import shutil

from hydra import compose, initialize_config_dir
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

from topogym.world.aloha_cameras import configure_aloha_rig, CAMERA_NAMES
from .reference import ReferenceMotion, ROOT
from .verification import validate_physical

NAMES = (*CAMERA_NAMES, "detail")
LABELS = {"unlock":"双臂协同脱困", "env_transport":"搬运橙色件", "land_0":"橙色件落架",
          "mobile_transport":"搬运蓝色件", "land_1":"蓝色件落架", "release_0":"解除左手抓持",
          "open_0":"左手张爪", "withdraw_0":"左手撤回", "release_1":"解除右手抓持",
          "open_1":"右手张爪", "withdraw_1":"右手撤回", "settled":"释放后静置"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_page(output, report, videos=None):
    videos = videos or {n:f"{n}.mp4" for n in NAMES}
    physical = report["classification"] == "physical_execution_with_grasp_assistance"
    kind = "完整物理执行（预抓取与辅助抓持）" if physical else "参考动作全过程运动学预演"
    scope = ("视频来自一次连续物理积分的实际状态，关节由限力控制器驱动。起点采用原演示的预抓取与理想抓持假设；落架后解除约束、张爪、撤回并自由静置。不是纯摩擦抓取验证。独立受力直拉对照尚未通过，当前配置不作为通用接触可靠性验收。"
             if physical else "按作者公开的关节轨迹和抓持变换重现全过程，渲染时逐帧设置状态、物理步数为 0。本录像用于对照动作，不计为物理执行通过；物理可靠性以独立试验报告为准。")
    buttons="".join(f'<button onclick="seek({p["time_s"]})">{escape(LABELS.get(p["name"],p["name"]))}</button>' for p in report["phases"])
    grid="".join(f'<figure><video class="sync" muted controls preload="metadata" src="{videos[n]}"></video><figcaption>{n}</figcaption></figure>' for n in CAMERA_NAMES)
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Claw · 完整流程</title>
<style>body{{max-width:1250px;margin:32px auto;padding:0 22px;font:16px/1.7 system-ui;background:#eef2f4;color:#25333d}}section{{background:white;padding:22px;border-radius:12px;margin:22px 0}}video,img{{width:100%;border-radius:8px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:15px}}figure{{margin:0}}button,select{{padding:9px;margin:4px;cursor:pointer}}.scope{{padding:16px;background:#fff0ce}}a{{color:#146a94}}@media(max-width:750px){{.grid{{grid-template-columns:1fr}}}}</style>
<p>TOPOGYM / INTERLOCKED CLAWS</p><h1>Claw：{kind}</h1><p class="scope">{scope}</p>
<section><video id="main" class="sync" controls preload="metadata" poster="initial_detail.png" src="{videos['detail']}"></video>
<p>{report['duration_s']:.2f} 秒 · {report['frames']} 帧 · {report['fps']:g} FPS · 五路同步视角。
播放速度 <select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="4" selected>4×</option></select></p><div>{buttons}</div></section>
<section><h2>ALOHA 四路观测</h2><div class="grid">{grid}</div></section>
<section><h2>起点与终点</h2><div class="grid"><figure><img src="initial_detail.png"><figcaption>原始互锁初态</figcaption></figure><figure><img src="final_detail.png"><figcaption>两件独立落架、双手撤离</figcaption></figure></div></section>
<section><h2>对应动作与验证记录</h2><p>保留原演示的两件原始三角网格和 12 个动作阶段；机器人采用 20 mm 实体垫座，恢复原视频中机器人、桌面和放置支架的相对高度。</p>
<p><a href="recording_report.json">录像与状态一致性报告</a> · <a href="config.yaml">配置</a> · <a href="assets/assembly.glb">初态模型</a> · <a href="reliability.html">物理验收与限制</a> · <a href="evidence/">原始证据目录</a></p>
<p>参考：<a href="https://qinengwang-aiden.github.io/demos/constraint_demos/">作者完整演示</a> · <a href="https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html">作者方法及边界</a>。</p></section>
<script>const main=document.getElementById('main'),all=[...document.querySelectorAll('video')];function seek(t){{all.forEach(v=>v.currentTime=t)}}document.getElementById('speed').onchange=e=>all.forEach(v=>v.playbackRate=+e.target.value);all.forEach(v=>v.playbackRate=4);main.onplay=()=>all.filter(v=>v!==main).forEach(v=>{{v.currentTime=main.currentTime;v.play().catch(()=>{{}})}});main.onpause=()=>all.forEach(v=>v.pause());main.onseeking=()=>all.filter(v=>v!==main).forEach(v=>v.currentTime=main.currentTime);</script></html>''')


def render(output, physical_source=None, keyframes_only=False):
    output=Path(output).resolve()
    if (output/"recording_report.json").exists():raise FileExistsError(output)
    output.mkdir(parents=True,exist_ok=True)
    motion=ReferenceMotion()
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="interlocked_claws_physics")
    evidence=output/"evidence";evidence.mkdir(exist_ok=True)
    fps=10
    if physical_source:
        source=Path(physical_source).resolve();physical,rows=validate_physical(source)
        cfg=OmegaConf.load(source/"config.yaml")
        fps=physical["physical_frame_fps"]
        if not np.allclose([r["time_s"] for r in rows],np.arange(len(rows))/fps,atol=1e-9):raise ValueError("Nonuniform physical frames")
        shutil.copytree(source,evidence/"physical",dirs_exist_ok=True)
        classification="physical_execution_with_grasp_assistance"
        phases=physical["phases"]
    else:
        rows=[];offset=np.asarray(cfg.env.robot_mount.pos)+[0,0,float(cfg.robot_control.robot.get("base_riser_height_m",0.))-.02]
        for frame,t in enumerate(np.arange(int(np.ceil(motion.duration*fps))+1)/fps):
            q,_,poses,held,phase=motion.sample(t)
            rows.append(dict(frame=frame,time_s=t,reference_time_s=min(t,motion.duration),step=0,phase=phase,qpos=q.tolist(),held=held,
                bodies=[dict(pos=(offset+p[:3,3]).tolist(),quat_wxyz=Rotation.from_matrix(p[:3,:3]).as_quat()[[3,0,1,2]].tolist()) for p in poses]))
        classification="kinematic_rehearsal"
        phases=[dict(name=p["name"],time_s=p["start_s"]) for p in motion.source["timeline"]]
        (evidence/"reference_motion.json").write_bytes(motion.path.read_bytes())
    (output/"render_states.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    cfg.env.renderer.type="nyx";cfg.env.renderer.spp=16;cfg.env.genesis.backend="cuda"
    cfg.run.output=str(output)
    meta=configure_aloha_rig(cfg,keep=("detail",),resolution=(640,360),low_pitch_offset_deg=20)
    cfg.env.cameras.detail=OmegaConf.create(dict(res=[960,720],pos=[.50,-1.45,2.10],lookat=[-.135,-.12,1.23],up=[0,0,1],fov=40,near=.005,far=12))
    OmegaConf.save(cfg,output/"config.yaml",resolve=True)
    (output/"camera_report.json").write_text(json.dumps(meta,indent=2)+"\n")
    import genesis as gs
    from .scene import as_numpy,build_scene
    gs.init(backend=gs.cuda,precision="64",logging_level="warning",seed=0)
    task=build_scene(cfg,output/"assets");robot=task.controller.robot
    keys=sorted(set([0,len(rows)-1]+[min(len(rows)-1,int(np.searchsorted([r["time_s"] for r in rows],p["time_s"]))) for p in phases]))
    selected=[rows[i] for i in keys] if keyframes_only else rows
    max_error=0.;seen=set()
    with ExitStack() as stack:
        writers={} if keyframes_only else {n:stack.enter_context(imageio.get_writer(output/f"{n}.mp4",fps=fps,codec="libx264",quality=8,
            macro_block_size=1,ffmpeg_params=["-threads","2"],ffmpeg_log_level="error")) for n in NAMES}
        cameras=stack.enter_context((output/"camera_poses.jsonl").open("w"))
        for row in selected:
            robot.set_qpos(np.asarray(row["qpos"]),zero_velocity=True)
            max_error=max(max_error,float(np.max(abs(as_numpy(robot.get_qpos())-row["qpos"]))))
            for b,p in zip(task.bodies.values(),row["bodies"]):
                b.set_pos(p["pos"]);b.set_quat(p["quat_wxyz"])
                max_error=max(max_error,float(np.max(abs(as_numpy(b.get_pos())-p["pos"]))))
            task.scene.visualizer.update_visual_states(force_render=True)
            for n in CAMERA_NAMES[2:]:task.cameras[n].move_to_attach()
            for c in task.cameras.values():c.sensor._stale=True
            transforms={}
            for n in NAMES:
                camera=task.cameras[n];pic=Image.fromarray(camera.render()[0]);draw=ImageDraw.Draw(pic)
                draw.rectangle((0,0,pic.width,42),fill=(18,27,35))
                draw.text((9,5),f"CLAW | {row['time_s']:.1f}s | {row['phase']} | {n}",fill='white')
                label="PHYSICAL STATES - PREGRASP / IDEAL GRASP ASSIST" if physical_source else "KINEMATIC REFERENCE REPLAY - ZERO PHYSICS STEPS"
                draw.text((9,23),label,fill=(248,205,115))
                if n in writers:writers[n].append_data(np.asarray(pic))
                if row["phase"] not in seen:pic.save(output/f"{row['phase']}_{n}.png")
                if row["frame"]==0:pic.save(output/f"initial_{n}.png")
                if row["frame"]==len(rows)-1:pic.save(output/f"final_{n}.png")
                transforms[n]=np.asarray(camera.transform).tolist()
            seen.add(row["phase"])
            cameras.write(json.dumps(dict(frame=row["frame"],time_s=row["time_s"],source_step=row["step"],transforms=transforms))+"\n")
            if row["frame"]%100==0 or keyframes_only:print(f"Render {row['frame']}/{len(rows)} {row['phase']}",flush=True)
    if max_error>1e-9:raise ValueError("Renderer changed a recorded state")
    report=dict(classification=classification,frames=len(rows),fps=fps,duration_s=len(rows)/fps,phases=phases,
        source_motion_sha256=motion.sha256,states_sha256=sha(output/"render_states.jsonl"),
        source_physical_states_sha256=None if physical_source is None else physical["states_sha256"],
        render_scene_physics_steps=0,interpolated_physical_states=False,state_restore_max_error=max_error,
        cameras=list(NAMES),keyframes_only=keyframes_only,source_directory=None if physical_source is None else str(source))
    if not keyframes_only:
        (output/"recording_report.json").write_text(json.dumps(report,indent=2)+"\n")
        write_page(output,report)
    print(output,flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--physical-source",type=Path);p.add_argument("--keyframes-only",action="store_true")
    a=p.parse_args();render(a.output,a.physical_source,a.keyframes_only)
