"""Render the exact-instance dual-arm IK rehearsal with four synchronous cameras."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

from topogym.world.aloha_cameras import CAMERA_NAMES, configure_aloha_rig
from .geometry import ASSET_ROOT
from .robot_motion import PAD_CENTER, ROOT


def canonical_to_entities(task,frame,mount):
    """Undo the assembly's baked transforms; preserve the original loaded solids."""
    rx=Rotation.from_euler("x",90,degrees=True).as_matrix()
    rz=Rotation.from_euler("z",90,degrees=True).as_matrix()
    transforms=[(rz@rx,np.array([0,0,task.assembly.template["gold_offset_z"]])*task.assembly.unit),
                (rx,np.zeros(3))]
    for item,(a,b) in zip(task.asset_report["bodies"],transforms):
        name=item["name"];pose=frame["bodies"][name]
        r=Rotation.from_quat(pose["quat"]).as_matrix();t=np.asarray(pose["pos"])
        rotation=r@a.T
        position=mount+t+rotation@(np.asarray(item["origin_m"])-b)
        task.bodies[name].set_pos(position)
        task.bodies[name].set_quat(Rotation.from_matrix(rotation).as_quat()[[3,0,1,2]])


def write_page(output,report):
    physical=bool(report.get("robot_execution_verified") and report.get("source_physical_audit_passed") and not report.get("kinematic_replay"))
    kind="完整物理执行（辅助抓持）" if physical else "完整运动学预演"
    scope=('本视频来自一次连续双臂物理执行的实际状态记录，机器人关节和零件运行中没有位姿覆写。两侧夹爪各自确认同一步双指接触后启用辅助抓持约束；'
           '末态两件完全分离并由双臂保持，辅助约束仍启用。起点为预抓取，不含桌面拾取；不宣称纯摩擦抓取。'
           f'原执行共 {report["physics_steps"]} 个物理步；图像随后从保存的实际状态统一渲染，帧内保留原物理步号和时间。') if physical else (
           '本视频为预抓取起点的全过程运动学预演：逐帧设置关节，零件位姿由实际机器人正运动学和固定抓持变换计算；物理步数为 0。'
           '已独立验证零件完整路径的连续碰撞间隙，并完成有界力／力矩驱动的动力学台架；台架通过不等于双臂物理抓取执行通过。')
    physical_links=('<p><a href="evidence/robot_physics/report.json">双臂物理执行报告</a> · '
                    '<a href="evidence/robot_physics/audit.json">实际轨迹独立碰撞及静止审查</a> · '
                    '<a href="evidence/robot_physics/trajectory.json">完整物理状态记录</a></p>') if physical else ''
    buttons="".join(f'<button onclick="seek({p["time_s"]})">{p["name"]}</button>' for p in report["phases"])
    cards="".join(f'<figure><video class="sync" controls preload="metadata" src="{n}.mp4"></video><figcaption>{n}</figcaption></figure>' for n in CAMERA_NAMES)
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Cast Keyhole · 当前实例完整 IK 解法</title>
<style>body{{max-width:1280px;margin:32px auto;padding:0 22px;font:16px/1.7 system-ui;background:#eef2f4;color:#24313b}}section{{background:white;padding:22px;margin:20px 0;border-radius:12px}}video,img{{width:100%}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}figure{{margin:0}}button{{padding:10px;margin:4px;cursor:pointer}}.scope{{background:#fff0ca;padding:16px}}a{{color:#146a94}}</style>
<h1>Cast Keyhole · {kind}</h1>
<p>保持原始板厚和槽形，从 perpendicular_lower_bore_v1 初态经过顶部转动、右侧换槽，最终完全分离。</p>
<p class="scope">{scope}</p>
<section><video id="main" controls preload="metadata" src="detail.mp4" poster="initial_detail.png"></video><div>{buttons}</div>
<p>{report['duration_s']:.2f} 秒；{report['frames']} 帧。当前初态并非商品出厂初态，未声称逐图复现官方 16 步。</p></section>
<section><h2>ALOHA 四路同步观测</h2><video id="mosaic" controls preload="metadata" src="four_views.mp4"></video><div class="grid">{cards}</div></section>
<section><h2>双臂视角</h2><video controls preload="metadata" src="oblique.mp4"></video><img src="final_detail.png" alt="最终分离"></section>
<section><h2>验证记录</h2>{physical_links}<p><a href="replay_report.json">录像报告</a> · <a href="robot_motion.json">完整关节与零件轨迹</a> · <a href="camera_report.json">相机参数</a> ·
<a href="evidence/certificate.json">连续几何证书</a> · <a href="evidence/physics_dt1ms/report.json">1 ms 动力学</a> · <a href="evidence/physics_dt05ms/report.json">0.5 ms 动力学</a> ·
<a href="evidence/baseline_solution.json">分段 SE(3) 路径</a></p><p>机器人碰撞验证范围与采样间隔见上述报告，未声称连续机器人碰撞证明。
双臂分别抓持两件，无需添加固定夹具；未排除单臂配夹具的方案。</p><p>解题参考：<a href="https://www.huzzle.eu/wp-content/uploads/2018/01/515061-Huzzle-Cast-Keyhole-Oct-2017.pdf">Huzzle 官方图解</a>。</p></section>
<script>function seek(t){{document.querySelectorAll('video').forEach(v=>v.currentTime=t)}}</script></html>''')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--motion",type=Path)
    parser.add_argument("--keyframes-only",action="store_true")
    parser.add_argument("--geometry",type=Path,help="Certified inverse-designed variant")
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    motion=json.loads((args.motion or output/"robot_motion.json").read_text())
    if not motion["report"].get("sampled_robot_scene_clearance_passed"):
        raise ValueError("The full IK trajectory must pass robot collision checks")
    variant=None
    if args.geometry is None:
        if motion["report"]["template_sha256"]!=hashlib.sha256((ASSET_ROOT/"template.json").read_bytes()).hexdigest():
            raise ValueError("Geometry changed since IK qualification")
    else:
        from .variant_assets import require_variant
        variant,_=require_variant(args.geometry,motion)
    import genesis as gs
    import imageio.v2 as imageio
    from topogym.robot import initialize_robot_controller
    from .scene import build_scene
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="cast_keyhole_aloha",overrides=["env.renderer.spp=16"])
    camera_report=configure_aloha_rig(cfg,keep=("detail","oblique"),low_pitch_offset_deg=20)
    if variant is not None:cfg.task.variant=variant["id"]
    OmegaConf.save(cfg,output/"config.yaml",resolve=True)
    gs.init(backend=gs.cuda,precision="64",logging_level="warning",seed=0)
    # This pass loads certified saved states and never steps the solver.
    # Keep every collision mesh for the asset audit, without solver work buffers.
    task=build_scene(cfg,output/"assets",geometry_path=args.geometry,replay_only=True)
    controller=initialize_robot_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    mount=np.asarray(cfg.env.robot_mount.pos);fk_errors=[];camera_poses=[]
    def pose(frame):
        controller.robot.set_qpos(np.asarray(frame["qpos"]))
        canonical_to_entities(task,frame,mount)
        task.scene.visualizer.update_visual_states(force_render=True)
        for n in CAMERA_NAMES[2:]:task.cameras[n].move_to_attach()
        for side,target in frame["grasp_targets"].items():
            arm=controller.arms[side];q=arm.hand_quat()
            actual=arm.hand_pos()+Rotation.from_quat(q[[1,2,3,0]]).apply(PAD_CENTER)
            error=float(np.linalg.norm(actual-mount-target["pos"]));fk_errors.append(error)
            if error>.00002:raise RuntimeError(f"Genesis/MuJoCo pad FK differs: {error}")
    pose(motion["frames"][0]);camera_report["initial_camera_checks"]={}
    for camera_index,(n,c) in enumerate(task.cameras.items()):
        # A Nyx refresh renders every sensor in one shared pass. One forced
        # refresh per changed physical state is sufficient for variant videos.
        rgb=c.render(force_render=variant is None or camera_index==0)[0].copy();Image.fromarray(rgb).save(output/f"initial_{n}.png")
        camera_report["initial_camera_checks"][n]=dict(transform=np.asarray(c.transform).tolist(),intrinsics=np.asarray(c.intrinsics).tolist(),std=float(rgb.std()))
        print(f"Initial {n}",flush=True)
    (output/"camera_report.json").write_text(json.dumps(camera_report,indent=2)+"\n")
    if args.keyframes_only:
        for i,phase in enumerate(motion["phases"]):
            pose(motion["frames"][phase["frame"]])
            for n in ("detail","oblique"):
                Image.fromarray(task.cameras[n].render(force_render=True)[0]).save(output/f"review_{i:02d}_{n}.png")
        pose(motion["frames"][-1])
        Image.fromarray(task.cameras["detail"].render(force_render=True)[0]).save(output/"final_detail.png")
        return
    names=[*CAMERA_NAMES,"detail","oblique"]
    with ExitStack() as stack:
        writers={n:stack.enter_context(imageio.get_writer(output/f"{n}.mp4",fps=motion["fps"],codec="libx264",quality=7,macro_block_size=1,
            ffmpeg_params=["-threads","2"],ffmpeg_log_level="error")) for n in names+["four_views"]}
        for i,frame in enumerate(motion["frames"]):
            pose(frame);grid=Image.new("RGB",(1280,720))
            for n in names:
                rgb=task.cameras[n].render(force_render=variant is None or n==names[0])[0].copy();writers[n].append_data(rgb)
                if n in CAMERA_NAMES:
                    j=CAMERA_NAMES.index(n);tile=Image.fromarray(rgb).resize((640,360));draw=ImageDraw.Draw(tile)
                    draw.rectangle((0,0,640,25),fill=(20,28,35));draw.text((12,7),n,fill="white")
                    grid.paste(tile,((j%2)*640,(j//2)*360))
            writers["four_views"].append_data(np.asarray(grid))
            camera_poses.append({n:np.asarray(task.cameras[n].transform).tolist() for n in CAMERA_NAMES})
            if i%12==0:print(f"Rendered {i+1}/{len(motion['frames'])}: {frame['stage']}",flush=True)
    for n in ("detail","oblique"):
        Image.fromarray(task.cameras[n].render(force_render=True)[0]).save(output/f"final_{n}.png")
    report=dict(motion["report"],frames=len(motion["frames"]),fps=motion["fps"],duration_s=len(motion["frames"])/motion["fps"],
        maximum_genesis_pad_fk_error_m=max(fk_errors),phases=motion["phases"],renderer="nyx",rendering_physics_steps=0,
        loaded_collision_audit=task.asset_report["loaded_collision_audit"],collision_enabled_during_rendering=False)
    (output/"replay_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    (output/"camera_poses.json").write_text(json.dumps(camera_poses)+"\n")
    if variant is None:write_page(output,report)
    print(f"Complete recording: {output}",flush=True)


if __name__=="__main__":main()
