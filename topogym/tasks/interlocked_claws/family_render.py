"""Render synchronized cameras from measured MuJoCo states; no resimulation."""
import os
os.environ.setdefault("MUJOCO_GL","egl")
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import imageio.v2 as imageio
import mujoco
import numpy as np

from .family_physics import values,save,sha


CAMERAS=("cam_high","cam_low","cam_left_wrist","cam_right_wrist","detail")


def camera(parent,name,position,target,fovy):
    position=np.array(position);z=position-np.asarray(target);z/=np.linalg.norm(z)
    x=np.cross([0,0,1],z);x/=np.linalg.norm(x);y=np.cross(z,x)
    ET.SubElement(parent,"camera",name=name,pos=values(position),xyaxes=values(np.r_[x,y]),fovy=str(fovy))


def render(run,output,prefix,cameras=CAMERAS,width=960,height=720):
    run=Path(run);output=Path(output);report=json.loads((run/"report.json").read_text())
    if not report["passed"]:raise ValueError("Only validated physical executions may use the full demo renderer")
    root=ET.parse(run/"scene.xml").getroot();world=root.find("worldbody")
    world.find("geom[@name='table']").set("size","4 4 .05")
    ET.SubElement(root.find("asset"),"texture",type="skybox",builtin="gradient",rgb1=".72 .79 .84",rgb2=".95 .96 .97",width="512",height="3072")
    camera(world,"cam_high",[.85,-1.30,1.15],[0,-.1,.22],43)
    camera(world,"cam_low",[.15,-1.50,.68],[0,-.08,.24],42)
    if report["family"]=="orthogonal_gate_balanced_v2":
        camera(world,"detail",[.50,-1.02,.91],[.02,-.12,.18],43)
    elif report["family"].startswith("orthogonal_gate"):
        camera(world,"detail",[.75,-1.3,1.],[.03,-.20,.22],45)
    else:
        camera(world,"detail",[.38,-.85,.78],[0,-.12,.16],43)
    for side in ("left","right"):
        body=root.find(f".//body[@name='{side}/gripper_link']")
        camera(body,f"cam_{side}_wrist",[.015,-.105,.105],[.24,0,-.01],76)
    xml=ET.tostring(root,encoding="unicode");(run/f"{prefix}_render_scene.xml").write_text(xml)
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    states=np.load(run/"states.npz");options=mujoco.MjvOption();options.geomgroup[3]=0
    renderer=mujoco.Renderer(model,height=height,width=width)
    writers={};paths={}
    for name in cameras:
        path=output/name/f"{prefix}_{name}.mp4";path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():raise FileExistsError(path)
        paths[name]=path
        writers[name]=imageio.get_writer(path,fps=report["fps"],codec="libx264",quality=8,macro_block_size=1,ffmpeg_params=["-pix_fmt","yuv420p","-movflags","+faststart"])
    try:
        for n,q in enumerate(states["qpos"]):
            data.qpos[:]=q;data.qvel[:]=states["qvel"][n];data.eq_active[:]=states["eq_active"][n]
            mujoco.mj_forward(model,data)
            for name,writer in writers.items():
                renderer.update_scene(data,camera=name,scene_option=options);frame=renderer.render();writer.append_data(frame)
                if n in (0,len(states["qpos"])//2,len(states["qpos"])-1):imageio.imwrite(run/f"{prefix}_{name}_{n:04d}.png",frame)
            if n%100==0:print(n,"/",len(states["qpos"]),flush=True)
    finally:
        for writer in writers.values():writer.close()
        renderer.close()
    manifest=dict(family=report["family"],scope="complete measured physical execution; ideal pregrasp welds released before final settling",
        renderer="MuJoCo EGL",rerender=True,physics_report_sha256=sha(run/"report.json"),states_sha256=sha(run/"states.npz"),
        frames=len(states["qpos"]),fps=report["fps"],duration_s=len(states["qpos"])/report["fps"],
        videos={name:dict(path=str(path.resolve()),sha256=sha(path)) for name,path in paths.items()})
    save(run/f"{prefix}_video_manifest.json",manifest)
    return manifest


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",required=True);p.add_argument("--output",required=True);p.add_argument("--prefix",required=True)
    p.add_argument("--cameras",nargs="+",default=CAMERAS);p.add_argument("--width",type=int,default=960);p.add_argument("--height",type=int,default=720)
    a=p.parse_args();render(a.run,a.output,a.prefix,a.cameras,a.width,a.height)
