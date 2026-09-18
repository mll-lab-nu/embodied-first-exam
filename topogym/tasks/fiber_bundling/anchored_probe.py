"""Physical attachment/support smoke test; no fine-strand or base pose writes."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np

from .anchored_geometry import AnchoredLayout, generate_anchored_assets
from .scene import as_numpy, cable_state
from .validation import pair_clearances
from .geometry import FiberLayout, shape_in_root_frame
from .contact_precision import CONTACT_MODEL, install_capsule_contact_fix


def main():
    import genesis as gs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("runs/environment-solvability/fiber_bundling/spaced_attachment"))
    parser.add_argument("--config",type=Path,help="Probe exact generated geometry, including its ring support")
    parser.add_argument("--dt",type=float,default=.002)
    parser.add_argument("--settle-seconds",type=float,default=2.)
    parser.add_argument("--load-seconds",type=float,default=.35)
    parser.add_argument("--release-seconds",type=float,default=1.)
    parser.add_argument("--load-scale",type=float,default=1.)
    parser.add_argument("--cradle-x",type=float,default=AnchoredLayout().cradle_x_m)
    parser.add_argument("--ring-distance",type=float,default=AnchoredLayout().ring_distance_from_roots_m)
    parser.add_argument("--performance-mode",action="store_true")
    parser.add_argument("--contact-model",choices=("genesis_default",CONTACT_MODEL),default=CONTACT_MODEL)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if not 0 < args.dt <= .002 or min(args.settle_seconds,args.release_seconds) <= 0 or args.load_seconds < 0 or args.load_scale < 0:
        parser.error("Require positive dt <= 2 ms, positive holds and nonnegative load")
    from .ring_mount import RingMount, export_fixture
    mount=None
    precision="32"
    constraint_solver="Newton"
    if args.config is None:
        anchor=AnchoredLayout(cradle_x_m=args.cradle_x,ring_distance_from_roots_m=args.ring_distance)
        layout=FiberLayout()
    else:
        from .run_config import load_run_config
        from omegaconf import OmegaConf
        cfg=load_run_config(args.config)
        precision=str(cfg.env.genesis.get("precision","32"))
        from .numerics import constraint_solver_name
        constraint_solver=constraint_solver_name(cfg.task)
        anchor=AnchoredLayout.from_task_config(cfg.task)
        layout=FiberLayout(**dict(cfg.task.geometry))
        mount=RingMount.from_task_config(cfg.task)
        args.contact_model=str(cfg.task.get("contact_model","genesis_default"))
        OmegaConf.save(cfg,args.output/"config.yaml",resolve=True)
    layout,asset=generate_anchored_assets(args.output/"assets",layout,anchor)
    spec=dict(dt=args.dt,substeps=4,settle_seconds=args.settle_seconds,load_seconds=args.load_seconds,release_seconds=args.release_seconds,
              load_force_world_N=(args.load_scale*np.array([-.4,.08,.10])).tolist(),loaded_link="trunk_04",anchor_error_limit_m=1e-5,
              penetration_limit_m=.0003,geometry_length_limit_m=1e-5,anchor=asdict(anchor),
              genesis_performance_mode=args.performance_mode,contact_model=args.contact_model,precision=precision,
              constraint_solver=constraint_solver)
    if mount is not None:
        spec["ring_fixture"]=mount.signature(layout)
        export_fixture(args.output/"assets",layout,mount,
            (layout.trunk_length_m+anchor.ring_distance_from_roots_m,0.,0.),-anchor.axis_height_m,asset)
    (args.output/"spec.json").write_text(json.dumps(spec,indent=2)+"\n")
    gs.init(backend=gs.cpu,logging_level="warning",seed=layout.seed,performance_mode=args.performance_mode,precision=precision)
    if args.contact_model == CONTACT_MODEL:
        install_capsule_contact_fix()
    scene=gs.Scene(show_viewer=False,sim_options=gs.options.SimOptions(dt=spec["dt"],substeps=spec["substeps"]),
        rigid_options=gs.options.RigidOptions(enable_collision=True,enable_self_collision=True,
            constraint_solver=getattr(gs.constraint_solver,constraint_solver),
            iterations=100,max_collision_pairs=4096,constraint_timeconst=.002))
    origin=np.array([0.,0.,anchor.axis_height_m])
    cable=scene.add_entity(gs.morphs.MJCF(file=str((args.output/"assets/bundle.xml").resolve()),pos=origin,decimate=False),
        material=gs.materials.Rigid(friction=.35,gravity_compensation=1.))
    for _,pos,size,_ in anchor.cradle_parts(layout):
        scene.add_entity(gs.morphs.Box(pos=origin+pos,size=size,fixed=True),material=gs.materials.Rigid(friction=.45))
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.45))
    scene.add_entity(gs.morphs.URDF(file=str((args.output/"assets/ring.urdf").resolve()),
        pos=origin+[layout.trunk_length_m+anchor.ring_distance_from_roots_m,0,0],euler=(0,90,0),
        fixed=True,merge_fixed_links=False,decimate=False))
    if mount is not None:
        mount.add_to_scene(scene,layout,origin+[layout.trunk_length_m+anchor.ring_distance_from_roots_m,0,0],0.)
    scene.build()
    print("Built fixed-terminal attachment experiment",flush=True)
    ids=[cable.get_link(n).idx_local for n in asset["coarse_link_names"]]
    loaded=cable.get_link(spec["loaded_link"]).idx
    lengths=np.r_[asset["lead_segments_m"],np.full(layout.trunk_segments,layout.trunk_length_m/layout.trunk_segments)]
    def state():
        s=cable_state(cable,layout)
        s["coarse_m"]=np.vstack([as_numpy(cable.get_links_pos())[ids],s["roots_m"].mean(axis=0)])
        return s
    initial=state();records=[];maximum=dict(anchor_error_m=0.,root_error_m=0.,length_error_m=0.,penetration_m=0.,strand_penetration_m=0.)
    finite=True;total=0;settle=None;previous=initial["fibers_m"].copy()
    maximum.update(fine_length_error_m=0.,point_displacement_per_step_m=0.,link_speed_m_s=0.)
    for phase,seconds in [("settle",spec["settle_seconds"]),("pull_working_trunk",spec["load_seconds"]),("release",spec["release_seconds"])]:
        for k in range(round(seconds/spec["dt"])):
            if phase=="pull_working_trunk":
                scene.sim.rigid_solver.apply_links_external_force(np.array([spec["load_force_world_N"]]),[loaded],ref="link_com")
            scene.step();total+=1;s=state()
            finite &= bool(np.isfinite(s["coarse_m"]).all() and np.isfinite(s["fibers_m"]).all())
            contacts=as_numpy(scene.sim.rigid_solver.collider.get_contacts()["penetration"])
            values=dict(anchor_error_m=max(np.linalg.norm(s["coarse_m"][0]-initial["coarse_m"][0]),
                np.linalg.norm(as_numpy(cable.get_pos())-origin)),root_error_m=s["max_root_error_m"],
                length_error_m=np.abs(np.linalg.norm(np.diff(s["coarse_m"],axis=0),axis=-1)-lengths).max(),
                penetration_m=float(contacts.max()) if contacts.size else 0.,
                strand_penetration_m=max(0.,-float(pair_clearances(s["fibers_m"],layout.fiber_radius_m).min())),
                fine_length_error_m=np.abs(np.linalg.norm(np.diff(s["fibers_m"],axis=1),axis=-1)-layout.fiber_length_m/layout.fiber_segments).max(),
                point_displacement_per_step_m=np.linalg.norm(s["fibers_m"]-previous,axis=-1).max(),
                link_speed_m_s=np.linalg.norm(as_numpy(cable.get_links_vel()),axis=-1).max())
            previous=s["fibers_m"].copy()
            for n,v in values.items():maximum[n]=max(maximum[n],float(v))
            if total%max(1,round(.02/spec["dt"]))==0:records.append(dict(time=total*spec["dt"],phase=phase,coarse=s["coarse_m"],fibers=s["fibers_m"]))
        if phase=="settle":settle=s
        print(phase,maximum,flush=True)
    final=state();drift=float(np.linalg.norm(settle["fibers_m"]-initial["fibers_m"],axis=-1).max())
    movement=float(np.linalg.norm(final["coarse_m"]-initial["coarse_m"],axis=-1).max())
    checks=dict(finite=finite,fixed_attachment=maximum["anchor_error_m"]<spec["anchor_error_limit_m"],
        roots_preserved=maximum["root_error_m"]<1e-5,coarse_lengths_preserved=maximum["length_error_m"]<1e-5,
        bounded_contacts=maximum["penetration_m"]<spec["penetration_limit_m"],
        bounded_strand_contacts=maximum["strand_penetration_m"]<spec["penetration_limit_m"],
        stable_reset=drift<.0001,working_trunk_can_move=movement>.001 if args.load_scale*args.load_seconds else movement<.0001,
        fine_lengths_preserved=maximum["fine_length_error_m"]<1e-5,
        bounded_motion_per_step=maximum["point_displacement_per_step_m"]<.0012)
    last=[r for r in records if r["time"]>=total*spec["dt"]-min(1.,spec["release_seconds"])]
    hold_drift=max(float(np.linalg.norm(shape_in_root_frame(r["fibers"])-shape_in_root_frame(last[0]["fibers"]),axis=-1).max()) for r in last)
    report=dict(scope="anchored_terminal_initial_hold_and_external_load_only",passed=all(checks.values()),
        checks=checks,maxima=maximum,settle_fiber_displacement_m=drift,loaded_coarse_displacement_m=movement,
        spec=spec,terminal_fixed=True,pose_writes=0,fine_force_commands=0,full_threading_verified=False,
        final_local_fine_shape_drift_m=hold_drift,final_link_speed_m_s=float(np.linalg.norm(as_numpy(cable.get_links_vel()),axis=-1).max()))
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    np.savez_compressed(args.output/"states.npz",**{k:np.asarray([r[k] for r in records]) for k in records[0]})
    print(json.dumps(report,indent=2),flush=True)
    if not report["passed"]:raise SystemExit(1)


if __name__=="__main__":main()
