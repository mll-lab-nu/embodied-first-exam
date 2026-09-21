"""Visualize the three motion blocks together; never merge physics evidence.

The first block uses a prior run's measured robot joints. The second is the
conditional offline handoff. The third is reference IK. Rope dynamics are
omitted throughout, and the result is explicitly not a continuous physical run.
"""
import argparse
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont

from .feedback_ik_plan import JOIN_SOURCE_S, smoothstep
from .feedback_paths import ARM, MeasuredHandoffPlanner, PathBuilder
from .ik_plan import ROOT, REFERENCE
from .reference_actions import ReferenceThreadingActions
from .reference_preflight import model_with_fixtures


def refine_mesh_contacts(model, time, qpos, candidates):
    """Resolve convex-hull false positives using original collision triangles."""
    import ipctk
    ipctk.set_num_threads(2)
    data, cache, records = mujoco.MjData(model), {}, []
    for item in candidates:
        ids = tuple(item["geom_ids"])
        if any(model.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH for g in ids):
            records.append(dict(item, unresolved_nonmesh=True, passed=False))
            continue
        data.qpos[:] = [np.interp(item["time_s"], time, qpos[:, j]) for j in range(16)]
        mujoco.mj_forward(model, data)
        vertices, faces, count, first_count = [], [], 0, 0
        for g in ids:
            mesh = int(model.geom_dataid[g])
            v = model.mesh_vert[model.mesh_vertadr[mesh]:model.mesh_vertadr[mesh]+model.mesh_vertnum[mesh]].astype(float)
            f = model.mesh_face[model.mesh_faceadr[mesh]:model.mesh_faceadr[mesh]+model.mesh_facenum[mesh]]
            vertices.append(v@data.geom_xmat[g].reshape(3, 3).T+data.geom_xpos[g])
            faces.append(f+count)
            count += len(v)
            if not first_count:
                first_count = count
        vertices = np.asfortranarray(np.vstack(vertices))
        if ids not in cache:
            f = np.vstack(faces).astype(np.int32)
            edges = np.unique(np.sort(np.vstack([f[:, :2], f[:, 1:], f[:, [0, 2]]]), axis=1), axis=0)
            mesh = ipctk.CollisionMesh(vertices, np.asfortranarray(edges), np.asfortranarray(f))
            mesh.can_collide = ipctk.make_vertex_patches_filter(np.r_[
                np.zeros(first_count, dtype=np.int32), np.ones(count-first_count, dtype=np.int32)])
            cache[ids] = dict(mesh=mesh, previous=None, time=None)
        state = cache[ids]
        mesh = state["mesh"]
        intersects = bool(ipctk.has_intersections(mesh, vertices, None))
        swept = True
        if state["previous"] is not None and item["time_s"]-state["time"] <= .010001:
            swept = bool(ipctk.is_step_collision_free(mesh, state["previous"], vertices, broad_phase=None))
        collisions = ipctk.NormalCollisions()
        collisions.build(mesh, vertices, .002)
        distance = None if collisions.empty() else float(np.sqrt(max(0., collisions.compute_minimum_distance(mesh, vertices))))
        records.append(dict(item, triangle_intersection=intersects, local_linear_surface_sweep_clear=swept,
                            triangle_distance_m=distance, passed=bool(not intersects and swept)))
        state.update(previous=vertices, time=item["time_s"])
    return dict(passed=all(r["passed"] for r in records), samples=len(records), records=records,
                scope="original robot collision triangles at convex candidate frames, with local linear surface sweeps")


def build(output, *, repair_first_release=False):
    output.mkdir(parents=True, exist_ok=False)
    base = ROOT/"runs/environment-solvability/rope_threading"
    prior = base/"full_ik_v3_20260921_attempt_1"
    local = base/"feedback_handoff_v5_20260921"
    reference = base/"ik_margin_v3_20260920"
    trace = json.loads((prior/"contact_trace.json").read_text())
    time = np.r_[0., [s["time_s"] for s in trace]]
    measured = np.asarray([np.concatenate([np.r_[s["robot"][side]["arm_qpos"],
        s["robot"][side]["finger_qpos"]] for side in ("left", "right")]) for s in trace])
    cfg = OmegaConf.load(prior/"config.yaml")
    q = np.vstack([np.r_[cfg.robot_control.home.left, cfg.robot_control.home.right], measured])
    label = ["prior measured robot prefix"]*len(q)
    first_repair = None
    if repair_first_release:
        # Kinematic counterpart of the online task_clearance correction. These
        # modified joint samples are explicitly no longer measured execution.
        early = MeasuredHandoffPlanner(cfg, q[0])
        source_clock = np.r_[0., [s["source_time_s"] for s in trace]]
        for i in np.flatnonzero(np.abs((source_clock-41.2)/3.) < 1.):
            u = (source_clock[i]-41.2)/3.
            p, r = early.ik.pose("left", q[i, :6])
            q[i, :6] = early.ik.solve("left", p+[.01*(1.-u*u)**3, 0., 0.],
                                      r.as_quat(scalar_first=True), seed=q[i, :6])
            label[i] = "conditional left clearance near base"
        original_time, original_q = time.copy(), q.copy()
        cut = int(np.flatnonzero(time <= 52.705+1e-8)[-1])
        actions = ReferenceThreadingActions(REFERENCE)
        join_source = float(actions.summary["stages"][27]["start_s"])
        resume = 1+next(i for i, s in enumerate(trace) if s["source_time_s"] >= join_source)
        time, q, label = time[:cut+1], q[:cut+1], label[:cut+1]
        planner = MeasuredHandoffPlanner(cfg, q[-1])
        join, hands, _, _ = actions._sample(join_source)
        for i, side in enumerate(("left", "right")):
            join[i*8:i*8+6] = planner.ik.solve_reference(side, hands[i, :3]+[0, 0, .0009],
                                                        hands[i, 3:], join[i*8:i*8+6])
        audits = []

        def append_path(name, path):
            nonlocal time, q, label
            directory = output/"first_release"/name
            directory.mkdir(parents=True)
            np.savez_compressed(directory/"path.npz", time_s=path.time, qpos=path.qpos, stage=path.stage)
            (directory/"audit.json").write_text(json.dumps(path.audit, indent=2)+"\n")
            time = np.r_[time, time[-1]+path.time[1:]]
            q = np.vstack([q, path.qpos[1:]])
            label += [str(s) for s in path.stage[1:]]
            audits.append(dict(name=name, audit=path.audit))

        append_path("unpinch", planner.unpinch(q[-1], side="right"))
        append_path("withdraw", planner.withdraw(q[-1], side="right", distance=.08))
        append_path("left_join", planner.join_arm(q[-1], join, "left"))
        append_path("right_join", planner.join_arm(q[-1], join, "right", match_fingers=True))
        bridge_difference = float(np.abs(q[-1, ARM]-original_q[resume, ARM]).max())
        bridge = PathBuilder(planner.ik, q[-1]).joints("visual_join_to_observed_checkpoint", 1.,
                    slice(0, 16), original_q[resume]).finish()
        # This bridge is ONLY for this hypothetical visualization. Runtime
        # resumes reference controls and never targets an old observed state.
        append_path("visual_checkpoint_join", bridge)
        time = np.r_[time, time[-1]+original_time[resume+1:]-original_time[resume]]
        q = np.vstack([q, original_q[resume+1:]])
        label += ["prior observed checkpoint continuation"]*(len(original_time)-resume-1)
        first_repair = dict(paths=audits, resume_source_s=join_source,
            early_left_clearance_maximum_x_m=.01,
            visualization_checkpoint_time_s=float(original_time[resume]),
            visualization_bridge_joint_difference_rad=bridge_difference,
            visualization_bridge_not_executed_online=True,
            rope_compatibility_between_independent_checkpoints_not_verified=True)
    prefix_end = float(time[-1])
    with np.load(local/"handoff_trajectory.npz") as z:
        first_gap = float(np.abs(q[-1]-z["qpos"][0]).max())
        time = np.r_[time, prefix_end+z["time_s"][1:]]
        q = np.vstack([q, z["qpos"][1:]])
        label += [str(s) for s in z["stage"][1:]]
    handoff_end = float(time[-1])
    local_end = q[-1].copy()
    with np.load(reference/"ik_trajectory.npz") as z:
        source_times = np.r_[JOIN_SOURCE_S, z["source_time_s"][z["source_time_s"] > JOIN_SOURCE_S]]
        suffix = np.column_stack([np.interp(source_times, z["source_time_s"], z["qpos"][:, j]) for j in range(16)])
        phase = np.interp(source_times, z["source_time_s"], z["phase"]).astype(int)
    second_gap = float(np.abs(local_end[ARM]-suffix[0, ARM]).max())
    # Preserve the nominal local grasp aperture until R3 releases that grasp;
    # actual execution instead freezes the aperture measured at native contact.
    release = 285.18449999671225
    for i, t in enumerate(source_times):
        u = smoothstep(float(np.clip((t-release)/1., 0., 1.)))
        suffix[i, 14:16] = local_end[14:16]*(1-u)+suffix[i, 14:16]*u
    time = np.r_[time, handoff_end+(source_times[1:]-JOIN_SOURCE_S)/3.]
    q = np.vstack([q, suffix[1:]])
    label += [f"reference phase {p:02d}" for p in phase[1:]]
    motion_end = float(time[-1])
    # Only a visual duration marker. With the rope omitted, this is no evidence
    # that it settles physically or even retains the target route.
    time = np.r_[time, motion_end+.5, motion_end+20.]
    open_final = q[-1].copy()
    open_final[[6, 7, 14, 15]] = .037
    q = np.vstack([q, open_final, open_final])
    label += ["final observation placeholder", "final observation placeholder"]
    model, data = model_with_fixtures(cfg), None
    data = mujoco.MjData(model)
    negative, minimum = [], 0.
    audit_time = np.unique(np.r_[time, np.arange(0., time[-1], .005)])
    for t in audit_time:
        data.qpos[:] = [np.interp(t, time, q[:, j]) for j in range(16)]
        mujoco.mj_forward(model, data)
        if len(data.contact):
            c = min(data.contact, key=lambda c: c.dist)
            minimum = min(minimum, float(c.dist))
            if c.dist < 0.:
                negative.append(dict(time_s=float(t), distance_m=float(c.dist),
                    geom_ids=[int(c.geom1), int(c.geom2)],
                    pair=[model.geom(g).name or model.body(model.geom_bodyid[g]).name for g in (c.geom1, c.geom2)]))
    seams_ok = max(first_gap, second_gap) < 1e-6
    refinement = refine_mesh_contacts(model, time, q, negative) if repair_first_release else None
    report = dict(kind="combined robot kinematic visualization; rope omitted",
        physical_execution_verified=False, same_continuous_physical_rollout=False,
        nominal_duration_s=float(time[-1]), prefix_end_s=prefix_end, handoff_end_s=handoff_end,
        final_motion_end_s=motion_end, source_resume_s=JOIN_SOURCE_S, reference_speed=3.,
        seam_joint_differences_rad=[first_gap, second_gap], joint_seams_continuous=seams_ok,
        collision_samples=len(audit_time), negative_contact_samples=len(negative),
        minimum_sampled_contact_distance_m=minimum, negative_contacts=negative,
        first_release_repair=first_repair, triangle_contact_refinement=refinement,
        source_blocks=[str(prior), str(local), str(reference)],
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [prior/"contact_trace.json", local/"handoff_trajectory.npz", reference/"ik_trajectory.npz"]},
        limitations=["No replayed or simulated rope in this visualization",
            "Conditional handoff must reobserve tip; its predicted grasp is not proof of capture",
            "Finger apertures after the new grasp are nominal; actual native contact determines them",
            "The final 20-second hold is a duration marker, not physical settling evidence"])
    report["sampled_kinematic_checks_passed"] = bool(seams_ok and (not negative or (refinement and refinement["passed"])))
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    np.savez_compressed(output/"combined_trajectory.npz", time_s=time, qpos=q, stage=label)
    OmegaConf.save(cfg, output/"config.yaml")
    return report


def render(output, report, fps=20):
    if not report["joint_seams_continuous"]:
        raise ValueError("Cannot present discontinuous joints as connected motion")
    with np.load(output/"combined_trajectory.npz") as z:
        time, qpos, labels = z["time_s"], z["qpos"], z["stage"]
    model = model_with_fixtures(OmegaConf.load(output/"config.yaml"))
    model.vis.global_.offwidth, model.vis.global_.offheight = 960, 540
    model.vis.headlight.active = 1
    model.vis.headlight.ambient[:] = .5
    model.vis.headlight.diffuse[:] = .8
    for i in range(model.ngeom):
        for prefix, rgba in [("audit_R1", [.04, .68, .73, 1.]), ("audit_R2", [.16, .58, .28, 1.]),
                             ("audit_R3", [.62, .33, .78, 1.]), ("audit_table", [.48, .40, .3, 1.])]:
            if model.geom(i).name.startswith(prefix):
                model.geom_rgba[i] = rgba
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, 540, 960)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    cameras, writers, paths = {}, {}, {}
    for name, lookat, distance, elevation in [("overview", [0., .1, .23], 1.8, -33.),
                                              ("detail", [.02, .16, .26], 1.05, -27.)]:
        camera = mujoco.MjvCamera()
        camera.lookat[:] = lookat
        camera.distance, camera.azimuth, camera.elevation = distance, 40., elevation
        cameras[name] = camera
        paths[name] = output/f"combined_kinematic_{name}.mp4"
        if paths[name].exists():
            raise FileExistsError(paths[name])
        writers[name] = imageio.get_writer(str(paths[name]), fps=fps, codec="libx264", quality=8,
                                          macro_block_size=1, pixelformat="yuv420p")
    frame_times = np.linspace(0., time[-1], int(round(time[-1]*fps)))
    try:
        for frame, t in enumerate(frame_times):
            data.qpos[:] = [np.interp(t, time, qpos[:, j]) for j in range(16)]
            mujoco.mj_forward(model, data)
            label = str(labels[min(np.searchsorted(time, t), len(time)-1)]).replace("_", " ")
            block = 1 if t <= report["prefix_end_s"] else 2 if t <= report["handoff_end_s"] else 3
            for name, camera in cameras.items():
                renderer.update_scene(data, camera=camera)
                image = Image.fromarray(renderer.render())
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 960, 78), fill=(18, 25, 34))
                draw.text((16, 8), "FULL-SEQUENCE KINEMATIC PREVIEW | Rope omitted | NOT a physics demo", font=font, fill="white")
                draw.text((16, 40), f"{t:06.2f} s | block {block}/3 | {label}", font=font, fill=(120, 215, 250))
                draw.rectangle((0, 504, 960, 540), fill=(18, 25, 34))
                footer = ("Conditional robot paths and observed checkpoints. Rope omitted; continuous physics run is separate."
                          if report["sampled_kinematic_checks_passed"] else
                          "DIAGNOSTIC: collision screen failed. See report. This is not a successful motion plan.")
                draw.text((16, 512), footer,
                          font=small, fill=(255, 193, 142))
                writers[name].append_data(np.asarray(image))
            if frame % 500 == 0:
                print(f"Rendered {frame}/{len(frame_times)} frames per view", flush=True)
    finally:
        for writer in writers.values():
            writer.close()
        renderer.close()
    manifest = dict(kind=report["kind"], physical_execution_verified=False, same_continuous_physical_rollout=False,
        fps=fps, frames_per_view=len(frame_times), playback_duration_s=len(frame_times)/fps,
        report_sha256=hashlib.sha256((output/"report.json").read_bytes()).hexdigest(),
        trajectory_sha256=hashlib.sha256((output/"combined_trajectory.npz").read_bytes()).hexdigest(),
        videos={name: dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                for name, path in paths.items()})
    (output/"preview_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repair-first-release", action="store_true")
    args = parser.parse_args()
    result = build(args.output, repair_first_release=args.repair_first_release)
    print(json.dumps({k: v for k, v in result.items() if k not in
        ("negative_contacts", "first_release_repair", "triangle_contact_refinement")}, indent=2), flush=True)
    render(args.output, result)
