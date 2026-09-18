"""Recompute contacts at saved poses for diagnostics, without a physics rollout."""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    import genesis as gs
    from omegaconf import OmegaConf
    from .scene import FiberSceneBuilder, as_numpy
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    args=parser.parse_args()
    cfg=OmegaConf.load(args.folder/"config.yaml")
    cfg.env.cameras={}
    cfg.env.renderer.type="rasterizer"
    gs.init(backend=gs.cpu,logging_level="warning",performance_mode=True)
    task=FiberSceneBuilder(cfg.env,cfg.task,cfg.robot_control).build(asset_dir=args.folder/"audit_assets")
    robot=task.manifest.get("robot")
    solver=task.scene.sim.rigid_solver
    names={link.idx:link.name for link in solver.links}
    robot_ids={link.idx for link in robot.links}
    cable_ids={link.idx for link in task.bundle.links}
    data=np.load(args.folder/"trajectory.npz")
    rows=[]
    for index in np.unique([np.abs(data['time_s']-6.814).argmin(),len(data['time_s'])-5,len(data['time_s'])-1]):
        task.bundle.set_qpos(data['cable_qpos'][index],zero_velocity=True)
        robot.set_qpos(data['robot_qpos'][index],zero_velocity=True)
        solver.collider.clear()
        solver.collider.detection()
        ct=solver.collider.get_contacts()
        a,b,pen=[as_numpy(ct[k]) for k in ['link_a','link_b','penetration']]
        pairs=[]
        for aa,bb,pp in zip(a,b,pen):
            if (int(aa) in robot_ids and int(bb) in cable_ids) or (int(bb) in robot_ids and int(aa) in cable_ids):
                pairs.append(dict(a=names[int(aa)],b=names[int(bb)],penetration_m=float(pp)))
        high=[dict(a=names[int(aa)],b=names[int(bb)],penetration_m=float(pp)) for aa,bb,pp in zip(a,b,pen) if pp>.0001]
        rows.append(dict(time_s=float(data['time_s'][index]),phase=str(data['phase'][index]),pairs=pairs,high_penetration_pairs=high))
    result=dict(scope="static_saved_pose_contact_audit_not_physics_execution",rows=rows)
    (args.folder/"contact_audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2),flush=True)


if __name__=="__main__":main()
