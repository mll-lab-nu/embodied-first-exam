"""Object-level checks for the below-easy Horseshoe settings (very_easy, easier).

With one shoe held up the chains hang along one axis, and the ring leaves by sliding along the
chains over the lower shoe. The checks use the generator meshes in the assembled configuration
(shoes coplanar, chains straight, ring standing across both chains), where the chain axis is x:

1. Section: the right shoe seen along the chain axis against the ring bore, at every phase
   (rotation of the ring about the chain axis, 2 deg apart). very_easy: the bore holds the
   section at every phase; easier: at some phases but not all.
2. Route: a straight slide of the ring along the chain axis past the right shoe, certified edge by
   edge with RigidPathChecker at MARGIN_M, at the phase where the bore fits best; for easier the
   same slide at the worst phase must collide.
3. Start: in the settled layout the ring still encloses both chain spans (each span, followed
   through the bands, eyes and link wires, crosses the ring's bore disc an odd number of times)
   and no straight slide of the ring alone takes it off the assembly.

No robot, IK or physics, except settle_check, which re-settles the stored layout on CPU.
"""
from pathlib import Path

import fcl
import numpy as np
import shapely.geometry as sg
import trimesh
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.horseshoe_ring import HorseshoeAssembly, band_centerline
from topogym.config.registry import task_definition
from topogym.planning.rigid_reference.geometry import RigidPathChecker, matrix, pose_dict

PHASES_DEG = tuple(range(0, 180, 2))
MARGIN_M = .001
SAMPLE_STEP_M = .001


def assembly(task):
    return HorseshoeAssembly(template=task.template(), scale=float(task.config["scale"]))


def _bodies(a):
    return {body.name: body for body in a.bodies}


def shoe_section(a):
    """Convex hull of the right shoe projected along the chain axis, in (y, z) metres."""
    shoe = _bodies(a)["horseshoe_right"].visual
    return sg.MultiPoint([tuple(p) for p in shoe.vertices[:, 1:]]).convex_hull


def bore_at(a, phase_deg, center):
    """The ring's bore in the (y, z) plane after turning the ring by phase_deg about the chain axis."""
    ring = a.loops["target_ring"]
    semi = ring.radii - ring.wire_radius
    t = np.linspace(0, 2 * np.pi, 256, endpoint=False)
    local = np.c_[semi[0] * np.cos(t), semi[1] * np.sin(t), np.zeros_like(t)]
    world = Rotation.from_euler("x", phase_deg, degrees=True).apply(ring.rotation.apply(local))
    return sg.Polygon(world[:, 1:] + center)


def passing_phases(a):
    section = shoe_section(a)
    center = np.asarray(section.centroid.coords[0])
    return [phase for phase in PHASES_DEG if bore_at(a, phase, center).contains(section)]


def _fixed_and_ring(a):
    bodies = _bodies(a)
    fixed = trimesh.util.concatenate([b.visual for n, b in bodies.items() if n != "target_ring"])
    return fixed, bodies["target_ring"].visual


def _slide(a, phase_deg):
    """Start and end poses of the ring sliding along +x past the right shoe, turned by phase_deg."""
    _, ring = _fixed_and_ring(a)
    section = shoe_section(a)
    offset = np.r_[0., section.centroid.coords[0]]
    turn = Rotation.from_euler("x", phase_deg, degrees=True)
    shoe = _bodies(a)["horseshoe_right"].visual
    end_x = shoe.bounds[1][0] + np.ptp(ring.vertices[:, 0]) + .01
    return (offset, turn), (offset + [end_x, 0., 0.], turn)


def slide_certified(a, phase_deg):
    fixed, ring = _fixed_and_ring(a)
    start, end = _slide(a, phase_deg)
    result = RigidPathChecker(fixed, ring, margin_m=MARGIN_M).edge(start, end)
    return dict(phase_deg=phase_deg, passed=bool(result["passed"]),
                clearance_lower_bound_m=result.get("clearance_lower_bound_m"),
                poses=[pose_dict(start), pose_dict(end)])


def slide_collides(a, phase_deg):
    """True if the straight slide intersects the shoes or chains somewhere (1 mm samples)."""
    fixed, ring = (_bvh(mesh) for mesh in _fixed_and_ring(a))
    (p0, r), (p1, _) = _slide(a, phase_deg)
    for u in np.linspace(0, 1, int(np.ceil(np.linalg.norm(p1 - p0) / SAMPLE_STEP_M)) + 1):
        t = matrix(p0 + u * (p1 - p0), r)
        ring.setTransform(fcl.Transform(t[:3, :3], t[:3, 3]))
        if fcl.collide(fixed, ring, fcl.CollisionRequest(), fcl.CollisionResult()):
            return True
    return False


def _band_halves(a):
    """Each shoe's band centreline (assembled frame) from the bottom of its U to each tip, by branch."""
    h, c, u = a.template["horseshoe"], a.template["chain"], a.unit
    alpha = np.radians(h["mouth_half_angle_deg"])
    tip_x = band_centerline(h, u, np.array([alpha]))[0, 0]
    shoe_center = ((c["links_per_span"] - 1) * c["center_spacing"] / 2 + c["eye_to_link_center"]
                   + h["eye_offset_x"]) * u + tip_x
    halves = {}
    for side, direction in (("left", -1), ("right", 1)):
        rotation = Rotation.from_euler("z", 0 if direction == -1 else np.pi)
        for end in (alpha, 2 * np.pi - alpha):
            line = rotation.apply(band_centerline(h, u, np.linspace(np.pi, end, 64))) + [direction * shoe_center, 0., 0.]
            halves[side, "upper" if line[-1, 1] > 0 else "lower"] = line
    return halves


def span_crossings(a, poses):
    """How often each chain span passes through the ring's bore disc in the given poses.

    A span is followed through the material: from the bottom of the left shoe's U along its band
    to the tip, to the eye's centre, into the link wire where it passes nearest that centre,
    along the link wire to the point nearest the next loop's centre, and on to the right eye and
    along the right band to the bottom of its U. The ring encloses a span when the count is odd.
    ``poses`` are body poses {name: {position_m, quaternion_wxyz}} in any common frame.
    """
    origins = {body.name: body.visual.center_mass for body in a.bodies}

    def place(body, points):
        pose = poses[body]
        r = Rotation.from_quat(np.roll(pose["quaternion_wxyz"], -1))
        return r.apply(np.atleast_2d(points) - origins[body]) + pose["position_m"]

    ring = a.loops["target_ring"]
    center = place("target_ring", ring.center)[0]
    rotation = Rotation.from_quat(np.roll(poses["target_ring"]["quaternion_wxyz"], -1)) * ring.rotation
    semi = ring.radii - ring.wire_radius
    bands = _band_halves(a)
    counts = {}
    for branch in ("upper", "lower"):
        links = sorted(n for n in a.loops if n.startswith(f"chain_{branch}_"))
        eyes = [a.loops[f"{side}_{branch}_eye"] for side in ("left", "right")]
        path = [place("horseshoe_left", bands["left", branch]), place(eyes[0].body, eyes[0].center)]
        for k, name in enumerate(links):
            wire = place(name, a.loops[name].points(256))
            before = path[-1][-1]
            after = (place(a.loops[links[k + 1]].body, a.loops[links[k + 1]].center)[0] if k + 1 < len(links)
                     else place(eyes[1].body, eyes[1].center)[0])
            i = int(np.argmin(np.linalg.norm(wire - before, axis=1)))
            j = int(np.argmin(np.linalg.norm(wire - after, axis=1)))
            path.append(wire[i:j + 1] if i <= j else wire[j:i + 1][::-1])
        path += [place(eyes[1].body, eyes[1].center), place("horseshoe_right", bands["right", branch][::-1])]
        local = rotation.inv().apply(np.concatenate(path) - center)
        p, q = local[:-1], local[1:]
        crossing = (p[:, 2] > 0) != (q[:, 2] > 0)
        hit = p[crossing] + (p[crossing, 2] / (p[crossing, 2] - q[crossing, 2]))[:, None] * (q[crossing] - p[crossing])
        counts[branch] = int(np.sum(np.sum((hit[:, :2] / semi) ** 2, axis=1) < 1))
    return counts


def _bvh(mesh):
    model = fcl.BVHModel()
    model.beginModel(len(mesh.vertices), len(mesh.faces))
    model.addSubModel(np.asarray(mesh.vertices), np.asarray(mesh.faces, dtype=np.int32))
    model.endModel()
    return fcl.CollisionObject(model)


def _directions():
    """Upper hemisphere and horizon, 15 deg apart in elevation and 30 deg in azimuth."""
    out = [np.array([0., 0., 1.])]
    for elevation in np.radians(range(0, 90, 15)):
        for azimuth in np.radians(range(0, 360, 30)):
            out.append(np.array([np.cos(elevation) * np.cos(azimuth), np.cos(elevation) * np.sin(azimuth), np.sin(elevation)]))
    return out


def ring_loose(a, poses, *, reach_m=.45, skip_m=.002):
    """Directions in which the ring, alone, slides straight off the settled assembly and table.

    ``poses`` are settled body poses {name: {position_m, quaternion_wxyz}} in the layout frame
    (table top at z = 0). The first ``skip_m`` of each slide is not tested, so resting contact
    and the solver's sub-millimetre penetration do not count as blocking. An empty list means
    the ring cannot simply be lifted or slid off: it still hangs on the chains.
    """
    meshes = {}
    for body in a.bodies:
        pose, mesh = poses[body.name], body.visual.copy()
        r = Rotation.from_quat(np.roll(pose["quaternion_wxyz"], -1))
        mesh.vertices = r.apply(mesh.vertices - body.visual.center_mass) + pose["position_m"]
        meshes[body.name] = mesh
    table = trimesh.creation.box((2., 2., .1))
    table.apply_translation([0., 0., -.05])
    fixed = _bvh(trimesh.util.concatenate([table, *(m for n, m in meshes.items() if n != "target_ring")]))
    ring = _bvh(meshes["target_ring"])
    loose = []
    for d in _directions():
        clear = True
        for s in np.arange(skip_m, reach_m, SAMPLE_STEP_M):
            ring.setTransform(fcl.Transform(np.eye(3), s * d))
            if fcl.collide(fixed, ring, fcl.CollisionRequest(), fcl.CollisionResult()):
                clear = False
                break
        if clear:
            loose.append(d.round(3).tolist())
    return loose


def start_state(a, poses):
    """Whether the ring hangs on both chains in these poses: odd span crossings, no free slide."""
    crossings = span_crossings(a, poses)
    loose = ring_loose(a, poses)
    return dict(entangled=all(c % 2 for c in crossings.values()) and not loose,
                span_crossings=crossings, loose_directions=len(loose))


def _phase_gap(phase, others):
    """Smallest angle from phase to any of others; a bore repeats every 180 deg."""
    return min(min(abs(phase - q) % 180, 180 - abs(phase - q) % 180) for q in others)


def check_variant(variation):
    """Design report for one below-easy setting: 'very_easy', 'easier', or why neither."""
    task = task_definition("horseshoe_ring", variation)()
    a = assembly(task)
    section = shoe_section(a)
    phases = passing_phases(a)
    minx, miny, maxx, maxy = section.bounds
    start = start_state(a, task.rest_poses())
    result = dict(variation_id=task.variation_id, instance_id=task.instance_id,
                  bore_mm=task.config["ring"]["bore_mm"],
                  shoe_section_mm=[round((maxx - minx) * 1000, 1), round((maxy - miny) * 1000, 1)],
                  passing_phases=len(phases), phase_count=len(PHASES_DEG), start=start, margin_m=MARGIN_M,
                  scope="generator meshes, assembled configuration held fixed; no robot, IK or physics")
    if not start["entangled"]:
        return dict(result, design="not_entangled_at_start")
    if not phases:
        return dict(result, design="blocked")
    failing = [ph for ph in PHASES_DEG if ph not in phases]
    if not failing:
        sampled = [slide_certified(a, ph) for ph in PHASES_DEG[::15]]
        return dict(result, design="very_easy" if all(s["passed"] for s in sampled) else "no_certified_slide",
                    route=sampled[0], sampled_phases=[dict(phase_deg=s["phase_deg"], passed=s["passed"]) for s in sampled])
    best = max(phases, key=lambda ph: _phase_gap(ph, failing))
    route = slide_certified(a, best)
    if not route["passed"]:
        return dict(result, design="no_certified_slide", route=route)
    worst = max(failing, key=lambda ph: _phase_gap(ph, phases))
    blocked = slide_collides(a, worst)
    return dict(result, design="easier" if blocked else "easier_unblocked", route=route,
                passing_range_deg=[min(phases), max(phases)], blocked_phase_deg=worst, blocked_at_worst_phase=blocked)


def settle_check(variation, output, *, seconds=3., seed=0):
    """Hold the robot at home on CPU and report how far each body moves from the stored layout."""
    from topogym.planning.rigid_reference.feedback import body_pose
    from topogym.simulator import Env, SimulatorConfig
    config = SimulatorConfig(task_id="horseshoe_ring", variation_id=variation, compute_backend="cpu",
                             enable_rgb=False, physics_dt_s=.0025, solver_substeps=4, control_decimation=1,
                             max_physics_steps=None, work_dir=Path(output) / "scene")
    names = ("target_ring", "horseshoe_left", "horseshoe_right")
    with Env(config) as env:
        env.reset(seed=seed)
        hold = {name: {"joint_position_rad": list(group["joint_position_rad"])}
                for name, group in env._robot.observe().items()}
        start = {n: body_pose(env._world.read_state()["bodies"][n]) for n in names}
        for _ in range(int(round(seconds / config.physics_dt_s))):
            env.step(hold)
        bodies = env._world.read_state()["bodies"]
        task = env._task
        anchor = np.r_[np.asarray(task.config["center_xy_m"], float), task.table_height_m]
        end = {n: body_pose(bodies[n]) for n in names}
        settled = {n: dict(position_m=(np.asarray(b["position_m"]) - anchor).tolist(),
                           quaternion_wxyz=list(b["quaternion_wxyz"])) for n, b in bodies.items() if n in task.local_vertices}
        return dict(variation_id=task.variation_id, instance_id=task.instance_id, seconds=seconds,
                    physics_dt_s=config.physics_dt_s, solver_substeps=config.solver_substeps, backend="cpu",
                    translation_mm={n: float(np.linalg.norm(end[n][0] - start[n][0]) * 1000) for n in names},
                    rotation_deg={n: float(np.degrees((end[n][1] * start[n][1].inv()).magnitude())) for n in names},
                    end_state=start_state(assembly(task), settled))


if __name__ == "__main__":
    import argparse
    from topogym.utils.io import write_json_atomic
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", required=True, choices=("very_easy", "easier"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settle-seconds", type=float, default=0., help="also re-settle the stored layout on CPU")
    args = parser.parse_args()
    report = check_variant(args.variant)
    if args.settle_seconds:
        report["settle"] = settle_check(args.variant, args.output, seconds=args.settle_seconds)
    write_json_atomic(args.output / "below_easy_check.json", report)
    print(report["variation_id"], report["design"], report.get("settle", ""))
