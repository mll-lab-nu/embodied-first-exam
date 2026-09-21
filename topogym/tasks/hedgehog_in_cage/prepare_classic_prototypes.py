"""Archive synchronized physical videos and promote the replacement families."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from omegaconf import OmegaConf
import trimesh

from .classic_families import FAMILIES, OUTPUT
from .family_archive import verify_physics
from .variants import ROOT, NEW_ASSETS, save, file_sha


def archive(folder):
    folder=Path(folder).resolve()
    physical,comparison=verify_physics(folder)
    recording=json.loads((folder/"recording/recording_report.json").read_text())
    if not recording["passed"] or not recording["actual_physics_states"]:
        raise ValueError("Only actual continuous physical executions can be promoted")
    for name,digest in recording["source_physical_sha256"].items():
        if file_sha(folder/"physics"/name)!=digest:raise ValueError("Stale recording")
    videos={}
    for camera in ("agentview","front_oblique","wrist"):
        relative=recording["video_files"][camera];video=ROOT/relative
        if video.parent != ROOT/"demos/hedgehog_in_cage"/camera:
            raise ValueError("Videos must use the existing per-camera archive")
        stream=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-select_streams","v:0",
            "-show_entries","stream=nb_read_frames,duration,r_frame_rate,width,height","-of","json",str(video)]))["streams"][0]
        subprocess.run(["ffmpeg","-v","error","-i",str(video),"-f","null","-"],check=True)
        if int(stream["nb_read_frames"])!=recording["frames"] or abs(float(stream["duration"])-recording["duration_s"])>.001:
            raise ValueError("Camera timing differs from the physical recording")
        videos[camera]=dict(path=relative,sha256=file_sha(video),**stream)
    save(folder/"time_step_comparison.json",comparison)
    manifest=dict(task_id="hedgehog_in_cage",family=folder.name,source_directory=str(folder.relative_to(ROOT)),
        archived_at_utc=datetime.now(timezone.utc).isoformat(),classification="physical_execution_with_grasp_assistance",
        scope="pregrasp start; bilateral contact-triggered assistance; extraction, placement, release, retreat, free settling",
        counts_as_complete_robotics_demo=True,official_CAD_replica=False,all_spikes_fixed=True,
        videos=videos,duration_s=recording["duration_s"],frames=recording["frames"],fps=recording["fps"],
        metadata_sha256={str(p.relative_to(folder)):file_sha(p) for p in sorted(folder.rglob("*"))
                         if p.is_file() and p.name!="archive_manifest.json"})
    save(folder/"archive_manifest.json",manifest)
    return manifest


def prepare(parents=OUTPUT,output=NEW_ASSETS):
    parents,output=Path(parents).resolve(),Path(output).resolve()
    if output.exists():raise FileExistsError("Preserve the versioned prototype library")
    verified=[(family,parents/family,archive(parents/family)) for family in FAMILIES]
    output.mkdir(parents=True)
    rows=[]
    for family,parent,manifest in verified:
        folder=output/family;folder.mkdir()
        shutil.copytree(parent/"assets",folder/"assets")
        for old,new in (("ik_before_geometry.json","motion.json"),("certificate.json","certificate.json"),
                        ("robot_audit.json","robot_audit.json"),("grasp.json","grasp.json")):
            shutil.copy2(parent/old,folder/new)
        cfg=OmegaConf.to_container(OmegaConf.load(parent/"recording/config.yaml"),resolve=True)
        cfg["run"].update(output=".",viewer=False,record_video=False,save_stills=False)
        cfg["env"]["genesis"].update(backend="cpu",precision="64")
        cfg["env"]["renderer"]["type"]="rasterizer"
        save(folder/"scene_config.json",cfg)
        cage=trimesh.load(folder/"assets/cage.obj",force="mesh")
        motion=json.loads((folder/"motion.json").read_text())
        proof=json.loads((folder/"certificate.json").read_text())
        descriptor=dict(family_id=family,prototype_id=f"hedgehog_{family}_fixed_v2",
            cage_bounds_m=cage.bounds.tolist(),cage_bottom_m=float(cage.bounds[0,2]),
            maximum_cage_radius_m=float(np.linalg.norm(cage.vertices[:,:2],axis=1).max()),cage_height_m=float(cage.extents[2]),
            parent_path_clearance_lower_bound_m=proof["continuous_clearance_lower_bound_m"],
            initial_qpos=motion["frames"][0]["qpos"],initial_ball_pose=motion["frames"][0]["ball_pose"],
            source_archive=str(parent.relative_to(ROOT)),source_archive_sha256=file_sha(parent/"archive_manifest.json"),
            parent_physically_verified=True,fixed_grasp="S2",spike_count=6,all_spikes_fixed=True,
            exit_type="top_keyhole" if family=="gen_keyhole" else "rounded_side_window",
            official_CAD_replica=False,distinct_ik_family_proven=False)
        save(folder/"prototype.json",descriptor)
        evidence=folder/"parent_evidence";evidence.mkdir()
        for sub in ("physics","physics_substeps20"):
            for name in ("report.json","audit.json"):
                shutil.copy2(parent/sub/name,evidence/f"{sub}_{name}")
        save(evidence/"provenance.json",dict(source_archive=descriptor["source_archive"],
            source_metadata_sha256=manifest["metadata_sha256"],scope="Parent evidence only; random descendants require independent qualification"))
        save(folder/"prototype_manifest.json",dict(schema_version=1,family_id=family,
            files_sha256={str(p.relative_to(folder)):file_sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}))
        rows.append(dict(family_id=family,directory=family,prototype_id=descriptor["prototype_id"],
                         manifest_sha256=file_sha(folder/"prototype_manifest.json")))
    save(output/"catalog.json",dict(schema_version=1,library_version="hedgehog_fixed_families_v2",families=rows,
        retained_family=dict(family_id="oblique_gate",library="../seed_families_v1"),
        replaced_families=["staggered_gates","helical_guide"],legacy_library_retained=True))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parents",type=Path,default=OUTPUT)
    p.add_argument("--output",type=Path,default=NEW_ASSETS)
    a=p.parse_args();prepare(a.parents,a.output)
