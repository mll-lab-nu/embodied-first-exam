"""Bounded object-space route proposals and explicit mechanism controls.

These searches are geometric diagnostics. They do not manufacture robot TCP
routes, establish grasp feasibility, or turn finite failure into impossibility.
"""
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from .feedback import body_pose, relative_pose
from .geometry import RigidPathChecker, freeze_scene, matrix, pose_dict, combine_meshes


def check_path(checker, poses):
    edges = []
    for i, (a, b) in enumerate(zip(poses, poses[1:])):
        result = checker.edge(a, b)
        edges.append(result)
        if not result["passed"]:
            return dict(passed=False, blocked_edge=i, edges=edges)
    return dict(passed=True, edges=edges,
                clearance_lower_bound_m=min((e["clearance_lower_bound_m"] for e in edges), default=None))


def pull_controls(task_id, variant, seed, output, *, distance_m=.30, tilt_deg=15., sidestep_m=.01):
    """Shortcut controls: the placement target leaves by one short move while
    every other body and the table stay fixed.

    Families: 26 straight pulls; pre-tilt then pull along +-x/y/z; sidestep then
    pull along +-x/y/z. A passing path is a shortcut. All blocked means only
    that these declared shortcuts are blocked, not that no other short route exists.
    """
    from itertools import product
    task, spec, scene, meshes, report = freeze_scene(task_id, variant, seed, Path(output)/"assets")
    moving_name = task.placement_targets[0]
    poses = {name: body_pose(p) for name, p in report["initial_poses"].items()}
    fixed = []
    for name, mesh in meshes.items():
        if name != moving_name:
            mesh = mesh.copy()
            mesh.apply_transform(matrix(*poses[name]))
            fixed.append(mesh)
    table = scene.env.world.table
    mesh = trimesh.creation.box(table.size)
    mesh.metadata["components"] = [dict(name="table", first_face=0, face_count=len(mesh.faces))]
    mesh.apply_transform(matrix(np.array(table.pos), Rotation.identity()))
    fixed.append(mesh)
    checker = RigidPathChecker(combine_meshes(fixed), meshes[moving_name])
    initial = poses[moving_name]
    report.update(moving=moving_name, fixed=[n for n in meshes if n != moving_name]+["table"],
        limits=dict(margin_m=checker.margin, distance_error_m=checker.error, max_depth=checker.max_depth),
        control_scope="declared one-move shortcuts only; other bodies fixed; no robot", controls=[])
    if not checker.initial_free(initial):
        report.update(status="initial_clearance_failed", queries=checker.queries)
        return report
    axes = [np.array(v, float) for v in np.eye(3)] + [-np.array(v, float) for v in np.eye(3)]
    def run(kind, path, **fields):
        result = check_path(checker, path)
        report["controls"].append(dict(kind=kind, passed=result["passed"], **fields,
            blocked_edge=result.get("blocked_edge"), clearance_lower_bound_m=result.get("clearance_lower_bound_m"),
            obstruction=None if result["passed"] else result["edges"][-1].get("obstruction")))
    for v in product((-1, 0, 1), repeat=3):
        if any(v):
            u = np.array(v, float)/np.linalg.norm(v)
            run("straight_pull", [initial, (initial[0]+distance_m*u, initial[1])], direction=u.tolist())
    for u, axis, sign in product(axes, range(3), (-1, 1)):
        r = Rotation.from_rotvec(np.eye(3)[axis]*np.deg2rad(sign*tilt_deg))*initial[1]
        run("tilt_then_pull", [initial, (initial[0], r), (initial[0]+distance_m*u, r)],
            direction=u.tolist(), tilt_axis=int(axis), tilt_deg=sign*tilt_deg)
    for u in axes:
        for side in axes:
            if abs(side@u) < .5:
                step = initial[0]+sidestep_m*side
                run("sidestep_then_pull", [initial, (step, initial[1]), (step+distance_m*u, initial[1])],
                    direction=u.tolist(), sidestep=(sidestep_m*side).tolist())
    passed = [c for c in report["controls"] if c["passed"]]
    report.update(status="shortcut_found" if passed else "declared_shortcuts_blocked",
                  controls_run=len(report["controls"]), shortcuts_passed=len(passed), queries=checker.queries)
    return report


def search_geometry(task_id, variant, seed, output, *, samples=128, rrt_iterations=0):
    task, spec, scene, meshes, report = freeze_scene(task_id, variant, seed, Path(output)/"assets")
    if variant not in {"medium", task_id+"_medium"}:
        report.update(status="unsupported_search_variant", geometry_path_verified=False)
        return report
    expected = {"hedgehog_in_cage": "waisted4_dark_wood_v1", "interlocked_claws": "opposed_pregrasp_wide2_v1"}
    if task.model_revision != expected[task_id]:
        raise ValueError("New model revision requires a new search domain")
    moving_name = "hedgehog_ball" if task_id == "hedgehog_in_cage" else "piece_1"
    frame_name = "hedgehog_cage" if task_id == "hedgehog_in_cage" else "piece_0"
    poses = {name: body_pose(p) for name, p in report["initial_poses"].items()}
    frame = poses[frame_name]
    fixed = []
    for name, mesh in meshes.items():
        if name == moving_name:
            continue
        mesh = mesh.copy()
        mesh.apply_transform(matrix(*relative_pose(frame, poses[name])))
        fixed.append(mesh)
    # Include the complete table in the same authored reference frame.
    table = scene.env.world.table
    mesh = trimesh.creation.box(table.size)
    mesh.metadata["components"] = [dict(name="table", first_face=0, face_count=len(mesh.faces))]
    mesh.apply_transform(matrix(*relative_pose(frame, (np.array(table.pos), Rotation.identity()))))
    fixed.append(mesh)
    checker = RigidPathChecker(combine_meshes(fixed), meshes[moving_name])
    initial = relative_pose(frame, poses[moving_name])
    report.update(search_seed=seed, sample_budget=samples, oracle_inputs="full frozen mesh/primitive geometry",
        geometry_path_verified=False, mechanism_geometry_path_verified=False, robot_execution_verified=False,
        placement_path_verified=False, mechanism_evidence={}, attempts=[], route=None,
        limits=dict(margin_m=checker.margin, distance_error_m=checker.error, max_depth=checker.max_depth),
        search_conclusion="Finite declared candidate search; absence is not an impossibility proof")
    if not checker.initial_free(initial):
        report.update(status="initial_clearance_failed", queries=checker.queries)
        return report
    rng = np.random.default_rng(seed)
    if task_id == "hedgehog_in_cage":
        # Window angles and the wide-band height come from the frozen asset report.
        asset_report = spec.metadata["asset_report"]
        windows = np.asarray(asset_report["window_centers_deg"], float)
        band = float(asset_report["window_band_center_m"])
        report["search_domain"] = dict(windows_deg=windows.tolist(),
            height_range_m=[band-.025, band+.025], orientation="uniform SO(3), plus authored orientation",
            route="lift at axis; reorient at axis; straight radial exit", radial_exit_m=.22,
            excluded="joint lift/rotation during exit; robot/gripper; placement transport")
        for angle in np.deg2rad(windows):
            radial = np.array([np.cos(angle), np.sin(angle), 0.])
            for label, z in (("no_lift", initial[0][2]), ("top_narrow", .095), ("lift_only", band)):
                a = (np.array([0., 0., z]), initial[1])
                result = check_path(checker, [initial, a, (a[0]+.22*radial, a[1])])
                report["mechanism_evidence"][f"{label}_{round(np.rad2deg(angle))}"] = result
        for i in range(samples):
            angle = np.deg2rad(windows[i % len(windows)])
            radial = np.array([np.cos(angle), np.sin(angle), 0.])
            z = band if i < len(windows) else rng.uniform(band-.025, band+.025)
            r = initial[1] if i < len(windows) else Rotation.random(random_state=rng)
            high = (np.array([0., 0., z]), initial[1])
            aligned = (high[0], r)
            end = (high[0]+.22*radial, r)
            path = [initial, high, aligned, end]
            # Cheap exit mid-plane rejection uses the entire ten-spike mesh.
            mid = (high[0]+.086*radial, r)
            gap = checker.clearance(mid)
            if gap <= checker.margin+checker.error:
                result = dict(passed=False, reason="exit_midplane_blocked", obstruction=checker.obstruction(mid, gap))
            else:
                result = check_path(checker, path)
            report["attempts"].append(dict(window_deg=float(np.rad2deg(angle)), height_m=z,
                                           orientation_wxyz=pose_dict(aligned)["quaternion_wxyz"], **result))
            if result["passed"] and report["route"] is None:
                report["route"] = dict(frame=frame_name, moving=moving_name, poses=[pose_dict(p) for p in path], certificate=result)
    else:
        # Scale is measured from the full current model, never copied from an
        # older orthogonal-gate family. The authored upper shaft is at z=.08*S.
        asset_report = spec.metadata["asset_report"]
        scale = asset_report["scale"]
        pivot = np.array([0., 0., .08])*scale
        report["search_domain"] = dict(roll_degrees=[-80, 80], vertical_shift_m=[-.02*scale, .02*scale],
            pull_distance_m=.42*scale, orientation="single x-axis pre-rotation, held fixed during axial pull",
            excluded="second turn; full SE(3) translation detours; reverse exits; robot; target-frame transport")
        report["mechanism_evidence"]["straight_pull"] = check_path(checker, [initial, (np.array([.42*scale, 0., 0.]), initial[1])])
        for i in range(samples):
            angle = float(np.linspace(-80., 80., samples)[i])
            z = 0. if i % 2 == 0 else rng.uniform(-.02, .02)*scale
            r = Rotation.from_euler("x", angle, degrees=True)
            aligned = (pivot-r.apply(pivot)+[0., 0., z], r)
            end = (aligned[0]+[.42*scale, 0., 0.], r)
            path = [initial, aligned, end]
            result = check_path(checker, path)
            report["attempts"].append(dict(roll_deg=angle, vertical_shift_m=z, **result))
            if result["passed"] and report["route"] is None:
                report["route"] = dict(frame=frame_name, moving=moving_name, poses=[pose_dict(p) for p in path], certificate=result)
        if report["route"]:
            report["mechanism_evidence"]["two_turns_necessary"] = False
        if report["route"] is None:
            # Head centering at A and rotation about B are proposals derived
            # from the current aperture geometry, never assumed solutions.
            # Keeping y=0 misses head-centering translations and was an
            # intentionally restricted fixed-orientation mechanism control.
            proposals = []
            gate_b = np.array([.18, 0., .08])*scale
            for roll in (-45., -35., -33.5, -33., -32.5, 32.5, 33., 33.5, 35., 45.):
                from itertools import product
                for lateral, lift in product((.025, .033, .034, .035, .045), (0., .0035, .0045)):
                    r = Rotation.from_euler("x", roll, degrees=True)
                    shift = np.array([0., -np.sign(roll)*lateral, lift])*scale
                    aligned = (pivot-r.apply(pivot)+shift, r)
                    through_a = (aligned[0]+[.115*scale, 0., 0.], r)
                    prefix = [initial, aligned, through_a]
                    prefix_check = check_path(checker, prefix)
                    proposals.append(dict(roll_deg=roll, lateral_m=float(shift[1]), lift_m=float(shift[2]), first_window=prefix_check))
                    if not prefix_check["passed"]:
                        continue
                    for yaw in (45., 50., 55., 60., 65.):
                        turn = Rotation.from_euler("z", yaw, degrees=True)
                        second = (gate_b+turn.apply(through_a[0]-gate_b), turn*r)
                        end = (second[0]+turn.apply([.4*scale, 0., 0.]), second[1])
                        path = prefix+[second, end]
                        result = check_path(checker, path)
                        proposals.append(dict(roll_deg=roll, lateral_m=float(shift[1]), lift_m=float(shift[2]), yaw_deg=yaw, full_path=result))
                        if result["passed"]:
                            report["route"] = dict(frame=frame_name, moving=moving_name,
                                poses=[pose_dict(p) for p in path], certificate=result,
                                qualification="object path only; two-turn necessity and robot feasibility unproved")
                            break
                    if report["route"]:
                        break
                if report["route"]:
                    break
            report["centered_two_window_proposals"] = proposals
    if report["route"] is None and rrt_iterations:
        from .rrt import connect_search
        if task_id == "hedgehog_in_cage":
            start = (np.array([0., 0., band]), initial[1])
            goal = (np.array([0., -.23, band]), initial[1])
            lower, upper = [-.05, -.23, band-.07], [.05, .03, band+.05]
            def sample(rng):
                return rng.uniform(lower, upper), Rotation.random(random_state=rng)
            prefix = [initial, start]
            domain = dict(position_lower_m=lower, position_upper_m=upper, orientation="uniform SO(3)")
        else:
            start, goal, prefix = initial, (np.array([.5*scale, 0., 0.]), initial[1]), [initial]
            lower, upper = np.array([-.08, -.10, -.10])*scale, np.array([.50, .10, .10])*scale
            def sample(rng):
                r = Rotation.from_euler("xyz", rng.uniform([-100, -45, -80], [100, 45, 80]), degrees=True)
                return pivot-r.apply(pivot)+rng.uniform(lower, upper), r
            domain = dict(translation_lower_m=lower.tolist(), translation_upper_m=upper.tolist(),
                          pivot_m=pivot.tolist(), euler_xyz_lower_deg=[-100, -45, -80], euler_xyz_upper_deg=[100, 45, 80])
        before = checker.queries
        prefix_result = check_path(checker, prefix)
        if prefix_result["passed"] and checker.initial_free(goal):
            path, result = connect_search(checker, start, goal, sample, rng=rng, iterations=rrt_iterations)
            report["rrt"] = dict(result, domain=domain, queries=checker.queries-before)
            if path:
                path = prefix[:-1]+path
                certificate = check_path(checker, path)
                if not certificate["passed"]:
                    raise RuntimeError("Search produced a route failing independent edge replay")
                report["route"] = dict(frame=frame_name, moving=moving_name, poses=[pose_dict(p) for p in path], certificate=certificate)
        else:
            report["rrt"] = dict(connected=False, reason="invalid_prefix_or_goal", prefix=prefix_result, domain=domain)
    report.update(status="object_route_found" if report["route"] else "no_route_in_declared_search",
                  mechanism_geometry_path_verified=report["route"] is not None, queries=checker.queries)
    return report
