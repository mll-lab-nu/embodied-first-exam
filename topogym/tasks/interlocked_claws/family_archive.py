"""Archive qualified fixed prototypes, measured states and standalone MP4 links."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .family_models import FamilyModel,geometry_audit
from .family_physics import save,sha,ROOT


def archive(plan,run,fine,bench,fine_bench,output):
    plan,run,fine,bench,fine_bench,output=map(Path,(plan,run,fine,bench,fine_bench,output))
    reports=[json.loads((p/"report.json").read_text()) for p in (plan,run,fine,bench,fine_bench)]
    if not all(r["passed"] for r in reports):raise ValueError("An input report failed")
    family=reports[1]["family"]
    if not all(r["family"]==family for r in reports):raise ValueError("Mixed family evidence")
    if reports[1]["plan_sha256"]!=sha(plan/"plan.json") or reports[2]["plan_sha256"]!=sha(plan/"plan.json"):
        raise ValueError("Physics did not execute the archived plan")
    original=json.loads((plan/"assets/model.json").read_text())
    for fixture in (bench,fine_bench):
        snapshot=json.loads((fixture/"assets/model.json").read_text())
        if snapshot!=original:raise ValueError("Fixture geometry differs from the robot plan")
    fm=FamilyModel(family)
    for p,s in zip(fm.parts,original["parts"]):
        if p.boxes!=s["boxes"] or not np.array_equal(p.grasp,s["grasp"]):raise ValueError("Current model differs from tested prototype")
    differences=[]
    for a,b in zip(reports[1]["final_poses"],reports[2]["final_poses"]):
        a,b=np.asarray(a),np.asarray(b)
        differences.append(dict(position_m=float(np.linalg.norm(a[:3,3]-b[:3,3])),rotation_rad=float(Rotation.from_matrix(a[:3,:3]@b[:3,:3].T).magnitude())))
    if any(d["position_m"]>.003 or d["rotation_rad"]>.03 for d in differences):raise ValueError("Refinement is not converged")
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(plan/"assets",output/"assets")
    for src,name in ((plan,"plan"),(run,"execution"),(fine,"refinement"),(bench,"bench"),(fine_bench,"bench_refinement")):
        shutil.copytree(src,output/name,ignore=shutil.ignore_patterns("*.mp4","assets","*.html"))
        if name.startswith("bench") and (src/"assets").exists():shutil.copytree(src/"assets",output/name/"assets")
    shutil.copytree(ROOT/"assets/robots/aloha/assets",output/"robot_assets")
    relocated=[]
    for name in ("plan","execution","refinement"):
        for path in (output/name).glob("*.xml"):
            root=ET.parse(path).getroot()
            compiler=root.find("compiler")
            if compiler is None or root.find("asset")==None:continue
            compiler.set("meshdir",".")
            for mesh in root.findall("asset/mesh"):
                file=Path(mesh.get("file"))
                mesh.set("file",str(Path("../assets" if file.name.startswith("piece_") else "../robot_assets")/file.name))
            ET.indent(root);ET.ElementTree(root).write(path,encoding="unicode")
            # Loading verifies all relocated mesh dependencies are present.
            mujoco.MjModel.from_xml_path(str(path))
            relocated.append(str(path.relative_to(output)))
    video_files=[]
    manifests=sorted(run.glob("*_video_manifest.json"))
    if (run/"video_manifest.json").exists():manifests.insert(0,run/"video_manifest.json")
    selected={}
    for p in manifests:
        manifest=json.loads(p.read_text())
        if manifest["states_sha256"]!=sha(run/"states.npz"):raise ValueError("Video states mismatch")
        selected.update(manifest["videos"])
    if not {"cam_high","cam_low","cam_left_wrist","cam_right_wrist"}<=selected.keys():raise ValueError("Incomplete synchronized cameras")
    for camera,item in selected.items():
        path=Path(item["path"])
        if sha(path)!=item["sha256"]:raise ValueError("Video hash mismatch")
        probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-select_streams","v:0","-show_entries","stream=width,height,r_frame_rate,nb_read_frames,duration","-of","json",str(path)]))["streams"][0]
        subprocess.run(["ffmpeg","-v","error","-i",str(path),"-f","null","-"],check=True,stdout=subprocess.DEVNULL)
        if int(probe["nb_read_frames"])!=reports[1]["frames"]:raise ValueError("Frame count differs from recorded states")
        video_files.append(dict(camera=camera,path=str(path.relative_to(ROOT)),sha256=sha(path),probe=probe,full_decode_passed=True))
    geometry=geometry_audit(fm)
    if not geometry["passed"]:raise ValueError("Final geometry audit failed")
    save(output/"geometry_audit.json",geometry)
    save(output/"refinement_comparison.json",dict(passed=True,coarse_dt_s=reports[1]["dt_s"],fine_dt_s=reports[2]["dt_s"],final_pose_differences=differences,limits=dict(position_m=.003,rotation_rad=.03)))
    source=output/"implementation";source.mkdir()
    for p in Path(__file__).parent.glob("family_*.py"):shutil.copy2(p,source/p.name)
    scope=("fixed engineered prototype; pregrasp-assisted complete ALOHA separation and stable held finish"
           if reports[1].get("objective")=="separate" else "fixed engineered prototype; pregrasp-assisted full ALOHA disassembly, placement, release and settling")
    manifest=dict(version="claw_authored_physical_v1",family=family,qualified=True,
        objective=reports[1].get("objective","disassemble_release"),scope=scope,
        engine="MuJoCo",dataset_generated=False,dataset_eligible=False,random_geometry_qualified=False,
        source_directories=dict(plan=str(plan),execution=str(run),refinement=str(fine),bench=str(bench),bench_refinement=str(fine_bench)),
        videos=video_files,relocated_xml=relocated,files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob("*")) if p.is_file()})
    save(output/"archive_manifest.json",manifest)
    return manifest


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("plan","run","fine","bench","fine-bench","output"):p.add_argument("--"+arg,required=True)
    a=p.parse_args();archive(a.plan,a.run,a.fine,a.bench,a.fine_bench,a.output)
