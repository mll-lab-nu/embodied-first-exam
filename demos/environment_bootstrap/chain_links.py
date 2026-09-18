"""Run hanging/loading/release qualification of three closed rigid chain links."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np

from topogym.tasks.catalog import baseline_manifest, load_card
from topogym.tasks._rigid_geometry import RingGeometry
from topogym.tasks.horseshoe_ring.chain_probe import ChainProbeLayout, build_chain_probe


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/environment_bootstrap/horseshoe_ring/three_links"))
    parser.add_argument("--dt", type=float, default=.001)
    parser.add_argument("--contact-timeconst", type=float, default=.001)
    parser.add_argument("--segments", type=int, default=48)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--renderer", choices=("nyx", "rasterizer"), default="nyx")
    args = parser.parse_args()
    if not np.isfinite(args.dt) or args.dt <= 0 or args.dt > .005 or args.seed < 0:
        parser.error("Require 0 < dt <= 0.005 and a nonnegative seed")
    if not np.isfinite(args.contact_timeconst) or args.contact_timeconst<args.dt/2:
        parser.error("Contact time constant must be finite and at least twice the substep")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline=load_card("horseshoe_ring")["baseline"]
    layout = ChainProbeLayout(ring=RingGeometry(
        radius_m=baseline["probe"]["centerline_radius_m"],
        tube_radius_m=baseline["probe"]["tube_radius_m"],
        density_kg_m3=baseline["probe"]["density_kg_m3"],segments=args.segments),
        spacing_m=baseline["probe"]["initial_center_spacing_m"])
    layout.validate()
    config = dict(layout=asdict(layout), dt=args.dt, substeps=4, seed=args.seed,
                  constraint_timeconst_s=args.contact_timeconst,friction=.3,solver_iterations=100,
                  phase_seconds={"settle":5., "load":3., "release":5.},
                  max_downward_load_N=2., max_allowed_penetration_m=.0005,
                  final_linear_speed_limit_m_s=.01, final_window_s=1.,
                  assistance="top link fixed; external bottom-link force; no pose writes after reset")
    config["rendering"] = dict(renderer=None if args.no_render else args.renderer, background=None if args.no_render else "compact_lab")
    (output/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    (output/"baseline_manifest.json").write_text(json.dumps(
        baseline_manifest("horseshoe_ring", args.seed), ensure_ascii=False, indent=2)+"\n")
    import genesis as gs
    gs.init(backend=gs.cuda, logging_level="warning", seed=args.seed)
    started = time.monotonic()
    scene, rings, camera, metadata = build_chain_probe(layout, output, dt=args.dt,
        render=not args.no_render,contact_timeconst=args.contact_timeconst,renderer=args.renderer)
    build_seconds = time.monotonic()-started
    assert [r.n_dofs for r in rings] == [0,6,6]
    writer = None
    if camera:
        import imageio.v2 as imageio
        writer = imageio.get_writer(output/"probe.mp4", fps=20, codec="libx264", macro_block_size=1)
        imageio.imwrite(output/"initial.png", camera.render()[0])
    records, phase_stats = [], {}
    max_penetration, max_speed, topology_failures = 0., 0., 0
    final_window = []
    error = None
    stride = max(1, round(.05/args.dt))
    steps = 0
    runtime = time.monotonic()
    try:
        for phase, duration in config["phase_seconds"].items():
            stats = dict(max_penetration_m=0., max_contact_force_N=0., contact_steps=0)
            for j in range(round(duration/args.dt)):
                local_t = (j+1)*args.dt
                force = -2.*min(1., local_t/.5) if phase=="load" else 0.
                rings[2].control_dofs_force([0,0,force,0,0,0])
                scene.step()
                steps += 1
                poses = [(array(r.get_pos()).reshape(3), array(r.get_quat()).reshape(4)) for r in rings]
                velocities = [array(r.get_vel()).reshape(3) for r in rings[1:]]
                angular_velocities = [array(r.get_ang()).reshape(3) for r in rings[1:]]
                if not all(np.isfinite(v).all() for pair in poses for v in pair):
                    raise RuntimeError("Non-finite rigid state")
                if not all(np.isfinite(v).all() for v in [*velocities, *angular_velocities]):
                    raise RuntimeError("Non-finite rigid velocity")
                links = layout.linking(poses)
                topology_failures += int(not all(abs(v)==1 for v in links))
                speed = max(float(np.linalg.norm(v)) for v in velocities)
                max_speed = max(max_speed, speed)
                contacts = scene.sim.rigid_solver.collider.get_contacts()
                penetration = array(contacts["penetration"])
                p = max(0., float(penetration.max())) if penetration.size else 0.
                forces = array(contacts["force"]).reshape(-1,3)
                f = float(np.linalg.norm(forces,axis=1).max()) if forces.size else 0.
                max_penetration = max(max_penetration,p)
                stats["max_penetration_m"] = max(stats["max_penetration_m"],p)
                stats["max_contact_force_N"] = max(stats["max_contact_force_N"],f)
                stats["contact_steps"] += int(f>1e-5)
                if phase=="release" and local_t>duration-1.:
                    final_window.append(speed)
                if steps%stride==0:
                    records.append(dict(time_s=steps*args.dt, phase=phase, linking=links,
                        centers_m=[p.tolist() for p,q in poses], max_speed_m_s=speed,
                        penetration_m=p, max_contact_force_N=f, external_force_z_N=force))
                    if writer: writer.append_data(camera.render()[0])
            phase_stats[phase] = stats
            if camera: imageio.imwrite(output/f"{phase}.png", camera.render()[0])
            print(phase, stats, flush=True)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if writer: writer.close()
    completed = set(phase_stats)==set(config["phase_seconds"])
    settled = bool(final_window) and max(final_window)<config["final_linear_speed_limit_m_s"]
    passed = (completed and error is None and topology_failures==0 and settled and
              max_penetration<config["max_allowed_penetration_m"] and
              all(s["contact_steps"]>0 for s in phase_stats.values()))
    report = dict(task_id="horseshoe_ring", scope="three_link_fixture_probe", passed=passed,
        full_task_deployed=False, error=error, physics_steps=steps, simulated_seconds=steps*args.dt,
        max_penetration_m=max_penetration, topology_failure_steps=topology_failures,
        max_linear_speed_m_s=max_speed, final_window_max_speed_m_s=max(final_window) if final_window else None,
        release_settled=settled, phase_stats=phase_stats, bodies=metadata,
        free_dofs=[r.n_dofs for r in rings], build_seconds=build_seconds,
        rollout_wall_seconds=time.monotonic()-runtime, genesis_version=version("genesis-world"),
        config=config, pose_writes_after_reset=False, inter_link_joints=False)
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    (output/"frames.json").write_text(json.dumps(records,indent=2,allow_nan=False)+"\n")
    (output/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>Three chain links</title>'
        '<h1>三链环局部接触试验</h1><p>顶环固定；其余两环自由。向下加载 2 N 后释放；这是夹具试验。</p>'
        '<p><a href="report.json">实际检查报告</a> · <a href="config.json">配置</a></p>'
        + ('<video controls src="probe.mp4" style="max-width:100%"></video>' if camera else '<p>本次未渲染。</p>'))
    print(json.dumps(report,indent=2),flush=True)
    if not passed: raise SystemExit(1)


if __name__ == "__main__":
    main()
