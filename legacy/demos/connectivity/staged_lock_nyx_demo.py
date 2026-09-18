"""Film insertion through three drive discs into a fixed endpoint in Genesis/Nyx.

This is an explicitly kinematic, geometry-checked pitch demonstrator. It is NOT
a contact-driven rollout, not a robot policy evaluation, and not registered as
a completed TopoGym benchmark task. All moving poses are written from the
mechanism contract; their radial/axial clearances are checked independently.

    .venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_nyx_demo --preview-only
    .venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_nyx_demo
    .venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_nyx_demo --variant backtrack
    .venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_nyx_demo --variant classic_endpoint
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
import math
from pathlib import Path
import time

import genesis as gs
from hydra import compose, initialize_config_dir
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
import torch
import trimesh

from demos.connectivity import _staged_lock_model as m
from topogym.world.tabletop import StandardTabletopSceneBuilder
from topogym.world import nyx

ROOT=Path(__file__).resolve().parents[2]
COLORS=((.76,.53,.23),(.20,.43,.60),(.72,.34,.22))
RGB=((215,163,76),(85,163,210),(220,113,78))
FONT="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
BOLD="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONTS={}


def font(size,bold=False):
    key=(size,bold)
    if key not in FONTS:
        FONTS[key]=ImageFont.truetype(BOLD if bold else FONT,size)
    return FONTS[key]


def extruded_annulus(inside,outside,thickness,samples=720):
    a=np.arange(samples)*2*np.pi/samples
    ri=np.asarray(inside(np.degrees(a)))
    ro=np.asarray(outside(np.degrees(a)))
    v=[]
    for x in (-thickness/2,thickness/2):
        for r in (ri,ro):
            v.extend(np.c_[np.full(samples,x),r*np.sin(a),r*np.cos(a)])
    faces=[]
    for i in range(samples):
        j=(i+1)%samples
        for q in ((i,j,samples+j,samples+i),
                  (2*samples+i,3*samples+i,3*samples+j,2*samples+j),
                  (i,2*samples+i,2*samples+j,j),
                  (samples+i,samples+j,3*samples+j,3*samples+i)):
            faces.extend(((q[0],q[1],q[2]),(q[0],q[2],q[3])))
    mesh=trimesh.Trimesh(vertices=np.asarray(v),faces=np.asarray(faces),process=True)
    mesh.fix_normals()
    if not mesh.is_watertight:
        raise RuntimeError("Lock disc mesh is not watertight")
    return mesh


def disc_mesh(index):
    def inner(a):
        near=np.minimum.reduce([np.abs((a-s+180)%360-180) for s in m.SLOTS[index]])
        return np.where(near<=m.SLOT_HALF_DEG,m.SLOT_R,m.BORE_R)
    return extruded_annulus(inner,lambda a:np.full_like(a,m.DISC_R),m.DISC_THICK)


def endpoint_mesh():
    def inner(a):
        return np.where(np.abs((a-m.END_DEG+180)%360-180)<=m.SLOT_HALF_DEG,m.SLOT_R,m.BORE_R)
    def outer(a):
        # A rectangular fixed plate visually distinguishes the terminal hole
        # from the three rotatable discs. It has one upward radial aperture.
        a=np.radians(a)
        return np.minimum(.066/np.maximum(np.abs(np.sin(a)),1e-8),
                          .090/np.maximum(np.abs(np.cos(a)),1e-8))
    return extruded_annulus(inner,outer,m.END_THICK)


def cylinder_x(radius,length,center):
    mesh=trimesh.creation.cylinder(radius=radius,height=length,sections=48)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,(0,1,0)))
    mesh.apply_translation(center)
    return mesh


def tab_mesh(x):
    a=np.radians([-m.TAB_HALF_DEG,m.TAB_HALF_DEG])
    section=np.array([[r*np.sin(t),r*np.cos(t)] for r in (.006,m.TAB_R) for t in a])
    # Convex hull of eight vertices: a thin radial metal fin, not a disc.
    verts=np.array([[x+dx,y,z] for dx in (-m.TAB_THICK/2,m.TAB_THICK/2) for y,z in section])
    return trimesh.convex.convex_hull(verts)


def key_mesh():
    parts=[cylinder_x(.006,.515,(-.2375,0,0))]
    for i,phase in enumerate(m.TAB_PHASE_DEG):
        tab=tab_mesh(-i*m.PITCH)
        tab.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-phase),(1,0,0)))
        parts.append(tab)
    # A recognisable old-key bow. Its bore remains a real mesh hole.
    bow=extruded_annulus(lambda a:np.full_like(a,.020),lambda a:np.full_like(a,.031),.010,144)
    bow.apply_translation((-.480,0,0));parts.append(bow)
    return trimesh.util.concatenate(parts)


def build_scene(args,output,*,camera_rig=None,prepare_scene=None):
    meshes=output/"meshes";meshes.mkdir(parents=True,exist_ok=True)
    # Nyx loads the source OBJ directly. Split normal seams so planar metal
    # faces are not shaded as if they bulge around every aperture.
    for i in range(3):
        trimesh.graph.smooth_shade(disc_mesh(i)).export(meshes/f"disc_{i+1}.obj",include_normals=True)
    trimesh.graph.smooth_shade(endpoint_mesh()).export(meshes/"endpoint.obj",include_normals=True)
    trimesh.graph.smooth_shade(key_mesh()).export(meshes/"key.obj",include_normals=True)
    with initialize_config_dir(config_dir=str(ROOT/"configs"),version_base="1.3"):
        cfg=compose(config_name="bar_through_hole_nyx")
    # This presentation derives the table/lab assets, not the frozen benchmark
    # camera/gravity contract. The saved config records that distinction.
    cfg.env.preset.locked=False
    cfg.env.sim.gravity=[0,0,0]
    cfg.env.sim.substeps=1
    cfg.env.renderer.spp=args.spp
    # A mechanism close-up, deliberately separate from the robot's policy rig.
    camera=OmegaConf.create(dict(res=[1024,768],pos=[-.91,-.95,1.52],
        lookat=[-.105,0,1.105],up=[0,0,1],fov=40.,near=.01,far=12.))
    cfg.env.cameras=OmegaConf.create({"mechanism":OmegaConf.to_container(camera)} if camera_rig is None else camera_rig)
    builder=StandardTabletopSceneBuilder(cfg.env,cfg.robot_control)
    base=builder.create(show_viewer=False,include_robot=False)
    scene,manifest=base.scene,base.manifest

    def box(name,pos,size,color,metal=.1):
        return manifest.add(name,scene.add_entity(
            gs.morphs.Box(pos=pos,size=size,fixed=True,collision=False),
            surface=gs.surfaces.Plastic(color=color,metallic=metal,roughness=.35),name=name))
    box("lock_base",(.195,0,.944),(.555,.260,.042),(.10,.14,.17),.45)
    box("lock_base_top",(.195,0,.968),(.545,.248,.008),(.48,.51,.52),.7)
    for i,x in enumerate(m.DISC_X):
        box(f"lock_support_{i}",(x,0,1.002),(.027,.180,.06),(.19,.23,.25),.55)
        for side in (-1,1):
            box(f"lock_fork_{i}_{side}",(x,side*.0825,1.045),(.027,.018,.075),(.28,.32,.34),.65)
    box("lock_endpoint_support",(m.END_X,0,1.001),(.050,.155,.060),(.19,.29,.26),.55)
    for x in (-.055,.445):
        for y in (-.101,.101):
            scene.add_entity(gs.morphs.Cylinder(pos=(x,y,.976),radius=.008,height=.006,
                              fixed=True,collision=False),
                             surface=gs.surfaces.Plastic(color=(.12,.14,.15),metallic=.7,roughness=.3))
    discs=[]
    for i,x in enumerate(m.DISC_X):
        discs.append(manifest.add(f"lock_disc_{i+1}",scene.add_entity(
            gs.morphs.Mesh(file=str(meshes/f"disc_{i+1}.obj"),pos=(x,0,m.AXIS_Z),
                           fixed=False,collision=False,convexify=False,decimate=False),
            surface=gs.surfaces.Plastic(color=COLORS[i],metallic=.75,roughness=.28),name=f"lock_disc_{i+1}")))
    key=manifest.add("lock_key",scene.add_entity(
        gs.morphs.Mesh(file=str(meshes/"key.obj"),pos=(m.Pose().tip_x,0,m.AXIS_Z),
                       fixed=False,collision=False,convexify=False,decimate=False),
        surface=gs.surfaces.Plastic(color=(.68,.71,.72),metallic=.92,roughness=.21),name="lock_key"))
    endpoint=manifest.add("lock_endpoint",scene.add_entity(
        gs.morphs.Mesh(file=str(meshes/"endpoint.obj"),pos=(m.END_X,0,m.AXIS_Z),
                       fixed=True,collision=False,convexify=False,decimate=False),
        surface=gs.surfaces.Plastic(color=(.25,.52,.40),metallic=.6,roughness=.32),name="lock_endpoint"))
    rules=OmegaConf.to_container(cfg.env.appearance,resolve=True)
    for i,color in enumerate(COLORS):
        rules.append(dict(pattern=f"lock_disc_{i+1}",color=list(color),
                          metallic=getattr(args,"disc_metallic",.75),
                          roughness=getattr(args,"disc_roughness",.3)))
    rules.extend([dict(pattern="lock_key",color=[.68,.71,.72],metallic=.92,roughness=.21),
                  dict(pattern="lock_endpoint",color=[.25,.52,.40],metallic=.6,roughness=.32)])
    cfg.env.appearance=OmegaConf.create(rules)
    if prepare_scene is not None:
        prepare_scene(scene,manifest)
    builder.finalize(base)
    sensor=(base.cameras["mechanism"].sensor if camera_rig is None else
            {name:cam.sensor for name,cam in base.cameras.items()})
    OmegaConf.save(cfg,output/"render_config.yaml",resolve=True)
    return scene,sensor,discs,key,endpoint


def set_pose(scene,discs,key,endpoint,pose):
    def quat(angle):
        a=math.radians(-angle)/2  # model angles run clockwise from world +z to +y
        return (math.cos(a),math.sin(a),0.,0.)
    for i,d in enumerate(discs):
        d.set_pos((m.DISC_X[i],0,m.AXIS_Z),zero_velocity=True)
        d.set_quat(quat(pose.disc_deg[i]),zero_velocity=True)
    key.set_pos((pose.tip_x,0,m.AXIS_Z),zero_velocity=True)
    key.set_quat(quat(pose.key_deg),zero_velocity=True)
    scene.step()
    # Read Genesis state back so the HUD cannot silently disagree with the
    # rendered mechanism because a solver or transform moved an entity.
    for entity,position,angle in [
            *[(d,(m.DISC_X[i],0,m.AXIS_Z),pose.disc_deg[i]) for i,d in enumerate(discs)],
            (key,(pose.tip_x,0,m.AXIS_Z),pose.key_deg),
            (endpoint,(m.END_X,0,m.AXIS_Z),0)]:
        actual_pos=entity.get_pos().detach().cpu().numpy()
        actual_quat=entity.get_quat().detach().cpu().numpy()
        if not np.allclose(actual_pos,position,atol=2e-6,rtol=0):
            raise RuntimeError("Genesis position does not match the mechanism storyboard")
        if not np.allclose(np.abs(np.sum(actual_quat*np.asarray(quat(angle)),axis=-1)),1,atol=2e-6,rtol=0):
            raise RuntimeError("Genesis orientation does not match the mechanism storyboard")


def face_panel(draw,cx,cy,r,angle,slots,color,key,engaged,*,fixed=False):
    # Front schematic is drawn from the same angles and slot sets as the meshes.
    n=180
    def point(a,rr):
        a=math.radians(a)
        return cx+rr*math.sin(a),cy-rr*math.cos(a)
    inner=[]
    for j in range(n):
        a=j*360/n
        near=min(m.angular_error(a-angle,s) for s in slots)
        ri=r*(m.SLOT_R/m.DISC_R if near<=m.SLOT_HALF_DEG else m.BORE_R/m.DISC_R)
        inner.append(point(a,ri))
    if fixed:
        draw.rectangle((cx-r,cy-r,cx+r,cy+r),fill=color)
    else:
        draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=color)
    draw.polygon(inner,fill=(27,37,48))
    draw.line((cx,cy-r-12,cx,cy-r+2),fill=(84,211,174) if fixed else (149,165,178),width=3)
    if engaged:
        end=point(key,r*m.TAB_R/m.DISC_R)
        draw.line(((cx,cy),end),fill=(235,240,244),width=8)
        draw.ellipse((cx-5,cy-5,cx+5,cy+5),fill=(235,240,244))
    if not fixed:
        draw.ellipse((cx-r-5,cy-r-5,cx+r+5,cy+r+5),outline=(94,219,238) if engaged else (65,82,96),width=2)


def compose_frame(rgb,pose,index,frame_no,total):
    canvas=Image.new("RGB",(1440,960),(18,27,38));draw=ImageDraw.Draw(canvas)
    draw.text((30,18),"STAGED LOCK",font=font(34,True),fill=(244,247,250))
    backtrack=m.VARIANT=="backtrack"
    classic=m.VARIANT=="classic_endpoint"
    heading="二层受阻 → 浅退修正 → 贯穿" if backtrack else "穿过三层 · 插入固定终点"
    if classic:
        heading="同向凸片 · 回退换槽 · 贯穿"
    draw.text((328,29),heading,font=font(25),fill=(194,212,226))
    draw.text((1045,32),"TopoGym  /  CONCEPT",font=font(20),fill=(124,166,190))
    canvas.paste(Image.fromarray(rgb),(0,92))
    draw.rounded_rectangle((22,109,498,147),radius=7,fill=(23,37,49))
    draw.text((36,116),"GENESIS + NYX   ·   机构剖视展示",font=font(18),fill=(224,237,245))
    if classic:
        draw.rounded_rectangle((22,159,614,198),radius=7,fill=(23,37,49))
        draw.text((36,166),"三个凸片固定同向 · 相对相位 0° / 0° / 0°",font=font(20),fill=(224,237,245))
    if backtrack:
        draw.rounded_rectangle((22,159,614,198),radius=7,fill=(23,37,49))
        draw.text((36,166),"凸片固定相位：前 0° / 中 60° / 后 150°",font=font(20),fill=(224,237,245))
        if index in (4,5,6,7):
            windows=m.third_level_windows(pose)
            draw.rounded_rectangle((26,666,998,826),radius=8,fill=(23,37,49))
            draw.text((44,677),"进入三级时：后凸片须过 D1，中凸片须过 D2",font=font(22,True),fill=(224,237,245))
            for line,(name,angles,color) in enumerate((
                    ("D1",windows["d1_rear_tab_centers"],RGB[0]),
                    ("D2",windows["d2_middle_tab_centers"],RGB[1]))):
                text=f"{name} 允许钥匙朝向："+" / ".join(f"{a:.0f}°" for a in angles)
                draw.text((44,719+line*39),text,font=font(21),fill=color)
            possible=windows["overlap_possible"]
            draw.text((715,731),"前两片入口相容" if possible else "无共同入口",font=font(23,True),
                      fill=(107,222,185) if possible else (245,139,108))
    # A compact key legend is independent of the camera's perspective.
    draw.text((1038,95),"同步角度 · 前视示意",font=font(22,True),fill=(224,237,245))
    active=m.active_discs(pose)
    for i,a in enumerate(pose.disc_deg):
        cy=198+i*150
        tab=m.active_tab(pose,i)
        tab_angle=pose.key_deg+(m.TAB_PHASE_DEG[tab] if tab is not None else 0)
        face_panel(draw,1126,cy,52,a,m.SLOTS[i],RGB[i],tab_angle,i in active)
        draw.text((1221,cy-45),f"D{i+1}",font=font(30,True),fill=RGB[i])
        draw.text((1221,cy-1),f"{a%360:05.1f}°",font=font(24),fill=(235,241,245))
        state="凸片啮合" if i in active else "保持角度"
        draw.text((1221,cy+35),state,font=font(19),fill=(95,215,230) if i in active else (147,168,184))
    face_panel(draw,1126,648,49,0,(m.END_DEG,),(72,152,119),pose.key_deg,
               m.tab_sweeps_plane(pose,pose.depth,m.END_X,m.END_THICK),fixed=True)
    draw.text((1210,598),"END  固定",font=font(23,True),fill=(110,219,177))
    draw.text((1210,634),"槽口朝上 0°",font=font(21),fill=(235,241,245))
    draw.text((1210,671),"已插入" if m.succeeded(pose) else "不可旋转",font=font(19),fill=(147,200,179))
    draw.line((1038,723,1410,723),fill=(55,75,92),width=2)
    depth=f"{pose.depth:.1f}" if abs(pose.depth-round(pose.depth))>.03 else str(round(pose.depth))
    draw.text((1042,734),f"插入深度  {depth} / 4",font=font(23,True),fill=(233,241,248))
    draw.text((1042,772),"当前啮合  "+(" + ".join(f"D{i+1}" for i in active) or "无"),
              font=font(21),fill=(105,216,231))
    draw.text((1042,809),f"钥匙朝向  {pose.key_deg%360:05.1f}°",font=font(19),fill=(180,199,213))
    beat=m.BEATS[index]
    c=(245,139,108) if beat.kind=="blocked" else (107,222,185) if m.succeeded(pose) else (233,241,248)
    draw.rectangle((0,844,1440,960),fill=(18,27,38))
    draw.text((28,853),beat.title,font=font(26,True),fill=c)
    draw.text((28,892),beat.subtitle,font=font(21),fill=(194,211,224))
    draw.text((28,930),"几何约束驱动的机构原型 · 非接触动力学 / 非机器人评测结果",font=font(15),fill=(124,149,169))
    draw.rectangle((0,956,int(1440*(frame_no+1)/total),959),fill=(87,192,179))
    if beat.kind=="blocked":
        draw.rounded_rectangle((610,111,997,151),radius=7,fill=(113,47,39))
        target="END" if beat.value==m.END_DEPTH else f"D{int(beat.value)}"
        draw.text((624,116),f"进入 {target}：方向不符，拒绝",font=font(20),fill=(255,224,214))
    elif m.succeeded(pose):
        draw.rounded_rectangle((590,111,997,151),radius=7,fill=(25,102,82))
        draw.text((610,115),"INSERTED  ·  到达终点",font=font(23,True),fill=(221,255,240))
    return np.asarray(canvas)


def main():
    global m
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant",choices=("endpoint","backtrack","classic_endpoint"),default="endpoint")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--fps",type=int,default=20)
    parser.add_argument("--spp",type=int,default=32)
    parser.add_argument("--preview-only",action="store_true")
    args=parser.parse_args()
    if args.variant=="backtrack":
        from demos.connectivity import _staged_lock_backtrack_model as m
    elif args.variant=="classic_endpoint":
        from demos.connectivity import _staged_lock_classic_endpoint_model as m
    if args.output is None:
        args.output=(ROOT/"runs/staged_lock_nyx_pitch/fixed_endpoint" if args.variant=="classic_endpoint"
                     else ROOT/f"runs/staged_lock_{args.variant}_nyx_pitch")
    if not torch.cuda.is_available():
        raise RuntimeError("Nyx needs GPU access; use the existing .venv-gs121-nyx environment")
    args.output.mkdir(parents=True,exist_ok=True)
    states=m.timeline(args.fps)
    gs.init(backend=gs.cuda,logging_level="warning",seed=0)
    scene,sensor,discs,key,endpoint=build_scene(args,args.output)
    if args.preview_only:
        deep_index=next(i for i,b in enumerate(m.BEATS) if b.kind=="depth" and b.value==3)
        for name,index,pose in [("initial",0,states[0][1]),("deep",deep_index,[p for i,p in states if i==deep_index][-1]),
                                ("final",len(m.BEATS)-1,states[-1][1])]:
            set_pose(scene,discs,key,endpoint,pose)
            image=compose_frame(nyx.rgb(sensor),pose,index,0,len(states))
            Image.fromarray(image).save(args.output/f"preview_{name}.png")
        print(f"Previews -> {args.output}",flush=True)
        return
    report_path=args.output/"report.json"
    movie=args.output/f"staged_lock_{args.variant}_pitch.mp4"
    start=time.perf_counter();last_pose=None;last_index=None;records=[];renders=0
    with imageio.get_writer(str(movie),fps=args.fps,codec="libx264",quality=8,
                            macro_block_size=16,ffmpeg_log_level="error",
                            ffmpeg_params=["-movflags","+faststart"]) as writer:
        for frame_no,(index,pose) in enumerate(states):
            if pose!=last_pose:
                set_pose(scene,discs,key,endpoint,pose)
                rgb=nyx.rgb(sensor);renders+=1
                last_pose=pose
            image=compose_frame(rgb,pose,index,frame_no,len(states))
            writer.append_data(image)
            if index!=last_index:
                print(f"Phase {index:02d}: {m.BEATS[index].title}; frame={frame_no}",flush=True)
                last_index=index
            if frame_no+1==len(states) or states[frame_no+1][0]!=index:
                Image.fromarray(image).save(args.output/f"phase_{index:02d}.png")
            records.append(dict(frame=frame_no,time_s=frame_no/args.fps,beat=index,
                                pose=asdict(pose),active_discs=list(m.active_discs(pose))))
            if frame_no%100==0:
                print(f"frames={frame_no}/{len(states)} renders={renders} wall_s={time.perf_counter()-start:.1f}",flush=True)
    Image.fromarray(image).save(args.output/"final.png")
    (args.output/"frames.json").write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n")
    report=dict(video=str(movie),frames=len(states),fps=args.fps,seconds=len(states)/args.fps,
        renders=renders,wall_seconds=time.perf_counter()-start,gpu=torch.cuda.get_device_name(),
        versions={n:version(n) for n in ("genesis-world","gs-nyx","gs-nyx-plugin")},
        fidelity="kinematic geometry-checked mechanism; collision=False on mechanism; no robot policy",
        task_registered=False,contact_dynamics_validated=False,
        geometry_checks="tab-disc and tab-fixed-endpoint clearance per frame; swept insertion/withdrawal checks",
        genesis_pose_readback_verified=True,
        goal="leading key tab inserted into fixed upward endpoint aperture",
        variant=args.variant,tab_phase_degrees=m.TAB_PHASE_DEG,
        success=m.succeeded(states[-1][1]),backtracking_required_from_initial_state=False,
        backtracking_required_from_demonstrated_depth2_state=args.variant=="backtrack",
        endpoint=dict(x=m.END_X,thickness=m.END_THICK,slot_degrees=m.END_DEG,fixed=True),
        geometry_errors=0,final_pose=asdict(states[-1][1]),drive_slot_degrees=m.SLOTS,
        dimensions_m={k:getattr(m,k) for k in ("PITCH","DISC_R","DISC_THICK","BORE_R","SLOT_R","TAB_R","TAB_THICK")},
        beats=[asdict(b) for b in m.BEATS])
    if args.variant=="backtrack":
        trap=[p for i,p in states if i==3][-1]
        corrected=[p for i,p in states if i==6][-1]
        report["conditional_backtracking_proof"]=dict(
            trapped_pose=asdict(trap),trapped_windows=m.third_level_windows(trap),
            corrected_pose=asdict(corrected),corrected_windows=m.third_level_windows(corrected),
            scope="slot-driven coaxial kinematic model; free key rotation in gaps allowed; no contact dynamics")
    elif args.variant=="classic_endpoint":
        report["derived_from"]="runs/staged_lock_nyx_pitch/source_v1"
        report["changes_from_original"]=["remove outer gates and release fence",
            "fixed upward endpoint", "D3 local slot 60 degrees -> 0 degrees",
            "one continuous stroke from depth 1 to depth 3 after shallow correction"]
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(f"Saved {movie} ({len(states)/args.fps:.1f}s) and {report_path}",flush=True)


if __name__=="__main__":
    main()
