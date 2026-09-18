"""Execute the full Cast Coil prototype route with physical ALOHA control.

Starts at a declared open pregrasp reset. Bilateral finger contacts gate two
explicit grasp-assistance constraints, removed before placement release.
No live object or robot pose overwrite is used. Pass --record for five
synchronized physical camera streams; archive only successful complete runs.
"""


def main():
    import json, argparse, time
    from pathlib import Path
    import numpy as np
    from scipy.spatial.transform import Rotation as R
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from topogym.tasks.cast_coil.geometry import CoilAssembly
    from topogym.tasks.cast_coil.verification import CompoundCollision, box_corners
    from topogym.tasks.cast_coil.robot_plan import Kinematics, PAD_CENTER
    from topogym.tasks.cast_coil.robot_grasp import active_grasps, release_grasps
    from topogym.world.aloha_cameras import configure_aloha_rig, CAMERA_NAMES

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--save-render-states", action="store_true",
                        help="Capture exact 20 Hz physical states for offline Nyx rendering")
    parser.add_argument("--dt", type=float, default=0.0025)
    parser.add_argument("--backend", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args()
    if args.dt not in (0.0025, 0.00125):
        raise ValueError("Supported control steps are 0.0025 and 0.00125 seconds")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "result.json").exists():
        raise FileExistsError(out)
    plan = json.loads(Path(args.plan).read_text())
    from topogym.tasks.cast_coil.verification import geometric_audit

    planned_assembly = CoilAssembly(plan.get("template"))
    if plan["template_sha256"] != geometric_audit(planned_assembly)["template_sha256"]:
        raise ValueError("Plan does not match current geometry")
    (out / "source_plan.json").write_text(json.dumps(plan))
    with initialize_config_dir(
        config_dir=str(Path(__file__).resolve().parents[3] / "configs"),
        version_base=None,
    ):
        cfg = compose(config_name="cast_coil_aloha")
    cfg.task.center_xy_m = [-0.1356786, 0.05]
    cfg.task.yaw_deg = 90
    cfg.task.initial_floor_clearance_m = 0.0
    if "template" in plan:
        (out / "input_template.json").write_text(json.dumps(plan["template"], indent=2))
        OmegaConf.set_struct(cfg.task, False)
        cfg.task.template_path = str((out / "input_template.json").resolve())
        cfg.task.variant = plan["template"]["template_id"]
    cfg.run.output = str(out)
    cfg.env.sim.dt = args.dt
    cfg.env.sim.substeps = 10
    cfg.env.genesis.backend = args.backend
    cfg.robot_control.controller.kp = [10000, 18000, 14000, 6000, 4000, 2500, 2000]
    cfg.robot_control.controller.kv = [200, 300, 250, 100, 80, 40, 124]
    cfg.env.renderer.type = "nyx" if args.record else "rasterizer"
    cfg.env.renderer.spp = 24
    meta = configure_aloha_rig(
        cfg, keep=(), resolution=(960, 540), low_pitch_offset_deg=20
    )
    camera_names = (*CAMERA_NAMES, "front_oblique")
    OmegaConf.set_struct(cfg.env.cameras, False)
    cfg.env.cameras.front_oblique = dict(
        res=[960, 720],
        pos=[0.20, -0.57, 1.34],
        lookat=[-0.135, 0.12, 1.02],
        up=[0, 0, 1],
        fov=38,
        near=0.005,
        far=12,
    )
    if not args.record:
        (out / "recording_cameras.json").write_text(json.dumps(OmegaConf.to_container(cfg.env.cameras, resolve=True), indent=2))
        cfg.env.cameras = {}
    OmegaConf.save(cfg, out / "config.yaml", resolve=True)
    (out / "execution_source.py").write_text(Path(__file__).read_text())
    for name in (
        "robot_grasp.py",
        "robot_plan.py",
        "geometry.py",
        "verification.py",
        "scene.py",
        "inverse_design.py",
        "appearance.py",
    ):
        (out / ("source_" + name)).write_text(
            Path(__file__).with_name(name).read_text()
        )
    (out / "camera_report.json").write_text(json.dumps(meta, indent=2))
    import genesis as gs
    from topogym.tasks.cast_coil.scene import build_scene
    from topogym.robot.aloha import AlohaDualArmController
    import imageio.v2 as imageio

    def arr(x):
        return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)

    def rot(q):
        return R.from_quat(arr(q)[[1, 2, 3, 0]])

    precision = str(cfg.task.get("physics", {}).get("precision", "32"))
    gs.init(backend=getattr(gs, args.backend), logging_level="warning", seed=0, precision=precision)
    task = build_scene(cfg, out / "assets")
    scene = task.scene
    robot = task.manifest.get("robot")
    ctrl = AlohaDualArmController(scene, robot, cfg.robot_control)
    ctrl.configure()
    solver = scene.sim.rigid_solver
    bodies = [task.bodies[n] for n in ("coil_gold", "coil_silver")]
    origins = [np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]]
    base = np.asarray(cfg.env.robot_mount.pos)
    assembly = task.assembly
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    q = np.asarray(plan["frames"][0]["qpos"])
    robot.set_qpos(q, zero_velocity=True)
    for side in ("left", "right"):
        c = ctrl.arms[side]
        c.set_arm_qpos(q[c.qs_idx[:6]])
        c.set_gripper(0.0203)
    writers = (
        {
            n: imageio.get_writer(
                out / f"{n}.mp4",
                fps=20,
                codec="libx264",
                quality=8,
                macro_block_size=1,
                ffmpeg_log_level="error",
            )
            for n in camera_names
        }
        if args.record
        else {}
    )
    camera_trace = (out / "camera_poses.jsonl").open("w")
    trace = (out / "states.jsonl").open("w")
    render_trace = (out / "render_states.jsonl").open("w") if args.save_render_states else None
    physical_frames = 0
    phase = "pregrasp"
    nstep = 0
    welded = False
    frames_count = 0
    phases = []
    snapshots = set()
    max_pair_pen = 0.0
    max_cross_arm_pen = 0.0
    max_forbidden_pen = 0.0
    max_finger_pen = 0.0
    max_error = 0.0
    min_sat = float("inf")
    last_contacts = {}
    result = {"success": False, "complete": False}
    t0 = time.monotonic()
    bodylinks = {b.base_link_idx for b in bodies}
    robotlinks = {l.idx: l.name for l in robot.links}
    fingerlinks = {
        s: {robot.get_link(f"{s}/{f}_finger_link").idx for f in ("left", "right")}
        for s in ("left", "right")
    }
    fingerpart = {0: fingerlinks["right"], 1: fingerlinks["left"]}
    robots = set(robotlinks)
    tables = {task.manifest.get("table").base_link_idx}

    def pose(i):
        r = rot(bodies[i].get_quat())
        return arr(bodies[i].get_pos()) - r.apply(origins[i]), r

    def capture_physical_frame():
        nonlocal physical_frames
        if render_trace is None:
            return
        render_trace.write(json.dumps(dict(frame=physical_frames, step=nstep,
            time_s=nstep*args.dt, phase=phase, qpos=arr(robot.get_qpos()).tolist(),
            bodies=[dict(origin_m=p.tolist(), quaternion_xyzw=r.as_quat().tolist())
                    for p,r in [pose(0),pose(1)]], grasp_assistance_active=welded)) + "\n")
        physical_frames += 1

    def render():
        nonlocal frames_count
        from PIL import Image, ImageDraw

        transforms = {}
        for name, writer in writers.items():
            camera = task.cameras[name]
            rgb = camera.render()[0]
            transforms[name] = arr(camera.transform).tolist()
            picture = Image.fromarray(rgb)
            draw = ImageDraw.Draw(picture)
            draw.rectangle((0, 0, picture.width, 52), fill=(16, 25, 34))
            draw.text(
                (12, 7),
                f"CAST COIL | {name} | {nstep * args.dt:.2f} s | {phase}",
                fill="white",
            )
            draw.text(
                (12, 28),
                "PHYSICAL EXECUTION - CONTACT-GATED GRASP ASSIST - PREGRASP START",
                fill=(242, 210, 120),
            )
            rgb = np.asarray(picture)
            writer.append_data(rgb)
            if phase not in snapshots:
                imageio.imwrite(out / f"{phase}_{name}.jpg", rgb, quality=90)
        camera_trace.write(
            json.dumps(
                dict(
                    frame=frames_count,
                    time_s=nstep * args.dt,
                    phase=phase,
                    transforms=transforms,
                )
            )
            + "\n"
        )
        snapshots.add(phase)
        frames_count += 1

    def step():
        nonlocal \
            nstep, \
            max_pair_pen, \
            max_cross_arm_pen, \
            max_forbidden_pen, \
            max_finger_pen, \
            min_sat, \
            last_contacts
        scene.step()
        nstep += 1
        ct = solver.collider.get_contacts(as_tensor=True, to_torch=True)
        la, lb = arr(ct["link_a"]), arr(ct["link_b"])
        pen = arr(ct["penetration"])
        force = np.linalg.norm(arr(ct["force"]), axis=-1)
        pair = ((la == bodies[0].base_link_idx) & (lb == bodies[1].base_link_idx)) | (
            (lb == bodies[0].base_link_idx) & (la == bodies[1].base_link_idx)
        )
        pairpen = float(pen[pair].max(initial=0))
        max_pair_pen = max(max_pair_pen, pairpen)
        intended = np.zeros(len(pen), dtype=bool)
        contact = {}
        for i in range(2):
            mask = (
                (la == bodies[i].base_link_idx) & np.isin(lb, list(fingerpart[i]))
            ) | ((lb == bodies[i].base_link_idx) & np.isin(la, list(fingerpart[i])))
            intended |= mask
            contact[i] = set(la[mask & (force > 0.05)].tolist()) | set(
                lb[mask & (force > 0.05)].tolist()
            )
        robotpuzzle = (
            np.isin(la, list(robots)) & np.isin(lb, list(bodylinks | tables))
        ) | (np.isin(lb, list(robots)) & np.isin(la, list(bodylinks | tables)))
        forbidden = robotpuzzle & ~intended
        # The fixed robot bases legitimately meet their mounting surface.
        for link, name in robotlinks.items():
            if "base_link" in name:
                forbidden &= ~(
                    ((la == link) & np.isin(lb, list(tables)))
                    | ((lb == link) & np.isin(la, list(tables)))
                )
        left_links = [i for i, n in robotlinks.items() if n.startswith("left/")]
        right_links = [i for i, n in robotlinks.items() if n.startswith("right/")]
        cross_arm = (np.isin(la, left_links) & np.isin(lb, right_links)) | (
            np.isin(lb, left_links) & np.isin(la, right_links)
        )
        cross_pen = float(pen[cross_arm].max(initial=0))
        max_cross_arm_pen = max(max_cross_arm_pen, cross_pen)
        if cross_pen > 0.00015:
            raise RuntimeError(f"Cross-arm collision {cross_pen * 1000:.3f} mm")
        fpen = float(pen[forbidden].max(initial=0))
        max_forbidden_pen = max(max_forbidden_pen, fpen)
        max_finger_pen = max(max_finger_pen, float(pen[intended].max(initial=0)))
        last_contacts = contact
        if nstep % max(1, round(0.02 / args.dt)) == 0:
            pg, rg = pose(0)
            ps, rs = pose(1)
            gap = collision.gap((rg.inv() * rs).as_matrix(), rg.inv().apply(ps - pg))
            min_sat = min(min_sat, gap)
            row = dict(
                time_s=nstep * args.dt,
                phase=phase,
                qpos=arr(robot.get_qpos()).tolist(),
                bodies=[
                    dict(
                        origin_m=p.tolist(),
                        quaternion_xyzw=r.as_quat().tolist(),
                        linear_speed_m_s=float(np.linalg.norm(arr(b.get_vel()))),
                        angular_speed_rad_s=float(np.linalg.norm(arr(b.get_ang()))),
                    )
                    for b, (p, r) in zip(bodies, [(pg, rg), (ps, rs)])
                ],
                sat_gap_m=gap,
                interpiece_penetration_m=pairpen,
                forbidden_robot_penetration_m=fpen,
                grasp_assistance_active=welded,
            )
            trace.write(json.dumps(row) + "\n")
            if gap < -0.00015:
                raise RuntimeError(f"Actual geometric overlap {gap * 1000:.3f} mm")
        if writers and nstep % round(0.05 / args.dt) == 0:
            render()
        if nstep % round(0.05 / args.dt) == 0:
            capture_physical_frame()
        if nstep % round(1 / args.dt) == 0:
            print(
                json.dumps(
                    dict(
                        t=nstep * args.dt,
                        phase=phase,
                        pair_mm=max_pair_pen * 1000,
                        forbidden_mm=max_forbidden_pen * 1000,
                        sat_mm=min_sat * 1000,
                    )
                ),
                flush=True,
            )
        if pairpen > 0.00015:
            raise RuntimeError(
                f"Interpiece contact penetration {pairpen * 1000:.3f} mm"
            )
        if fpen > 0.0003:
            raise RuntimeError(f"Robot forbidden penetration {fpen * 1000:.3f} mm")

    def phase_to(name):
        nonlocal phase
        phase = name
        phases.append(dict(name=name, time_s=nstep * args.dt))
        print("PHASE", name, flush=True)

    def wait(seconds):
        for _ in range(round(seconds / args.dt)):
            step()

    def command(q):
        for side, c in ctrl.arms.items():
            c.set_arm_qpos(q[c.qs_idx[:6]])

    def execute(frames):
        nonlocal max_error
        current = arr(robot.get_qpos()).copy()
        for idx, frame in enumerate(frames):
            if phase != frame["phase"]:
                phase_to(frame["phase"])
            goal = np.asarray(frame["qpos"])
            start = current.copy()
            for t in np.linspace(0, 1, round(0.02 / args.dt) + 1)[1:]:
                command(start + (goal - start) * t)
                step()
            current = goal
            for i in range(2):
                p, r = pose(i)
                expected = np.asarray(frame["bodies"][i]["p"]) + base
                error = np.linalg.norm(p - expected)
                max_error = max(max_error, float(error))
                if error > 0.004:
                    raise RuntimeError(
                        f"Body {i} tracking error {error * 1000:.3f} mm in {phase}"
                    )

    def adjust_plan():
        kin = Kinematics(cfg.robot_control)
        kin.q = arr(robot.get_qpos()).astype(float)
        relative = {}
        for side, i in [("right", 0), ("left", 1)]:
            p, r = pose(i)
            c = ctrl.arms[side]
            relative[side] = (
                r.inv().apply(c.hand_pos() - p),
                r.inv() * rot(c.hand_quat()),
            )
        frames = []
        for source in plan["frames"]:
            for side, i in [("right", 0), ("left", 1)]:
                rb = R.from_quat(source["bodies"][i]["r"])
                pb = np.asarray(source["bodies"][i]["p"])
                p0, r0 = relative[side]
                handr = rb * r0
                handp = pb + rb.apply(p0)
                target = handp + handr.apply(PAD_CENTER)
                err = kin.solve(side, target, handr)
                if err[0] > 0.0004 or err[1] > 0.004:
                    raise RuntimeError(
                        f"Updated grasp IK failed {source['phase']}: {err}"
                    )
            frames.append(dict(source, qpos=kin.q.tolist()))
        (out / "executed_plan.json").write_text(
            json.dumps(
                dict(
                    frames=frames,
                    grasp_transforms={
                        s: dict(position=p.tolist(), quaternion=r.as_quat().tolist())
                        for s, (p, r) in relative.items()
                    },
                )
            )
        )
        return frames

    try:
        capture_physical_frame()
        if writers:
            render()
        phase_to("close_grippers")
        for c in ctrl.arms.values():
            c.set_gripper(0.0176)
        simultaneous = 0
        for _ in range(round(1.5 / args.dt)):
            step()
            simultaneous = (
                simultaneous + 1
                if all(fingerpart[i].issubset(last_contacts[i]) for i in range(2))
                else 0
            )
            if simultaneous >= round(0.02 / args.dt):
                break
        if simultaneous < round(0.02 / args.dt):
            raise RuntimeError(
                f"Bilateral grasp contact not established: {last_contacts}"
            )
        result["bilateral_grasp_contact_step"] = nstep
        result["bilateral_grasp_contact_links"] = {
            str(i): sorted(v) for i, v in last_contacts.items()
        }
        for side, i in [("right", 0), ("left", 1)]:
            solver.add_weld_constraint(
                ctrl.arms[side].ee_link.idx, bodies[i].base_link_idx
            )
        welded = True
        phase_to("hold_grasp")
        wait(0.5)
        frames = adjust_plan()
        execute(frames)
        phase_to("release")
        registration_order = [
            (ctrl.arms[side].ee_link.idx, bodies[i].base_link_idx)
            for side, i in [("right", 0), ("left", 1)]
        ]
        result["release_evidence"] = release_grasps(solver, registration_order)
        (out / "release_evidence.json").write_text(
            json.dumps(result["release_evidence"], indent=2)
        )
        welded = False
        for c in ctrl.arms.values():
            c.open_gripper()
        wait(1.0)
        released_positions = [pose(i)[0] for i in range(2)]
        phase_to("retreat")
        kin = Kinematics(cfg.robot_control)
        kin.q = arr(robot.get_qpos()).astype(float)
        starts = {s: kin.pose(s) for s in ("left", "right")}
        for u in np.linspace(0, 1, 151)[1:]:
            smooth = u * u * (3 - 2 * u)
            for side in ("left", "right"):
                p, r = starts[side]
                direction = r.apply([-1, 0, 0])
                err = kin.solve(side, p + direction * 0.08 * smooth, r)
                if err[0] > 0.0005 or err[1] > 0.005:
                    raise RuntimeError("Retreat IK failed")
            command(kin.q)
            for _ in range(round(0.02 / args.dt)):
                step()
        result["released_body_displacement_during_retreat_m"] = [
            float(np.linalg.norm(pose(i)[0] - released_positions[i])) for i in range(2)
        ]
        if max(result["released_body_displacement_during_retreat_m"]) > 0.002:
            raise RuntimeError("A released piece moved with the retreating gripper")
        phase_to("settle")
        wait(2.0)
        pg, rg = pose(0)
        ps, rs = pose(1)
        vertices = box_corners(assembly.bodies[1].boxes) @ (
            rg.inv() * rs
        ).as_matrix().T + rg.inv().apply(ps - pg)
        separation = float(
            vertices[:, 0].min() - assembly.bodies[0].boxes[:, 1, 0].max()
        )
        speeds = [float(np.linalg.norm(arr(b.get_vel()))) for b in bodies]
        angular = [float(np.linalg.norm(arr(b.get_ang()))) for b in bodies]
        result.update(
            success=bool(
                separation > 0.01 and max(speeds) < 0.001 and max(angular) < 0.02
            ),
            complete=True,
            final_separation_m=separation,
            final_speed_m_s=speeds,
            final_angular_speed_rad_s=angular,
        )
    except Exception as exc:
        result.update(error=str(exc), failed_phase=phase)
        print("FAILED", str(exc), flush=True)
    finally:
        remaining = active_grasps(solver, bodylinks)
        if remaining:
            result.update(
                success=False,
                complete=False,
                error="Physical grasp constraints remain active",
            )
        result.update(
            scope="bimanual pregrasp instance; physical execution with bilateral-contact-gated weld assistance",
            geometry_modified=False,
            geometry_variant=assembly.template["template_id"],
            seed_geometry_changed=any(k in assembly.template for k in ("inverse_design", "appearance_design")),
            inverse_design_kind=assembly.template.get("inverse_design", {}).get("kind"),
            appearance_kind=assembly.template.get("appearance_design", {}).get("kind"),
            appearance_parameters=assembly.template.get("appearance_design", {}).get("parameters"),
            lift_m=plan["lift"],
            route_phases=[m["name"] for m in plan["geometric_audit"]["route"]],
            backend=args.backend,
            initial_layout_changed=True,
            initial_yaw_deg=90,
            live_object_pose_writes=False,
            live_robot_pose_writes=False,
            grasp_assistance="temporary hand/body welds enabled after simultaneous bilateral finger contacts; removed before release",
            grasp_assistance_active_at_end=bool(remaining),
            grasp_constraints_remaining=remaining,
            final_finger_contact_links={
                str(i): sorted(v) for i, v in last_contacts.items()
            },
            dt=args.dt,
            precision_bits=int(precision),
            substeps=10,
            noslip_iterations=int(
                cfg.task.get("physics", {}).get("noslip_iterations", 0)
            ),
            physics_steps=nstep,
            simulated_seconds=nstep * args.dt,
            maximum_interpiece_penetration_m=max_pair_pen,
            maximum_cross_arm_penetration_m=max_cross_arm_pen,
            maximum_forbidden_robot_penetration_m=max_forbidden_pen,
            maximum_finger_penetration_m=max_finger_pen,
            minimum_sampled_sat_gap_m=min_sat if np.isfinite(min_sat) else None,
            maximum_tracking_error_m=max_error,
            phases=phases,
            camera_names=list(writers),
            video_frames=frames_count,
            video_fps=20,
            physical_frame_count=physical_frames,
            physical_frame_fps=20,
            wall_seconds=time.monotonic() - t0,
        )
        for writer in writers.values():
            writer.close()
        camera_trace.close()
        trace.close()
        if render_trace is not None:
            render_trace.close()
            import hashlib
            result["render_states_sha256"] = hashlib.sha256((out / "render_states.jsonl").read_bytes()).hexdigest()
        (out / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
