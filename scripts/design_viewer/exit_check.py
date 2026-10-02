"""Hedgehog exit check on the exact collision meshes (python-fcl; kinematic, no physics).

very_easy: a straight pull leaves the cage from the current orientation.
easier:    one turn about a single axis through the ball centre (gripper approach /
           fingers / palm axes when a gripper holds it, else world x / y / z), up to
           +-180 deg and collision-free along the way, then a straight pull.
A gripper, when given, moves rigidly with the ball and must not touch the cage either.

python -m scripts.design_viewer.exit_check --scene hedgehog_in_cage_easy --set window_widths=24
python -m scripts.design_viewer.exit_check --scene hedgehog_in_cage_very_easy --grasp 180 --roll 90 --lift-mm 5
python -m scripts.design_viewer.exit_check --scene hedgehog_in_cage_easier --spike 4 --lift-mm 15 --axes approach
python -m scripts.design_viewer.exit_check --pose runs/design_viewer/poses/<scene>/<name>.json
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

import fcl
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from scripts.design_viewer import mjcf, scenes

STEP = .0015  # m, below the thinnest feature (spike 10.8 mm, wall 8-9 mm); continuousCollide misses BVH hits
LIFT = .003  # m; a ball resting in the viewer sinks up to ~3 mm into soft contact
ANGLE_STEP = 5  # deg between candidate turns; the turn itself is checked every degree
SPIKE_PINCH = .008  # m from the spike tip to the pinch point in a spike grasp


def directions(n=160):
    """Fibonacci directions from slightly downward (z = -0.2) to straight up."""
    i = np.arange(n)+.5
    z = i/n*1.2-.2
    phi = i*np.pi*(3-np.sqrt(5))
    r = np.sqrt(1-z*z)
    return np.c_[r*np.cos(phi), r*np.sin(phi), z]


def _bvh(mesh):
    model = fcl.BVHModel()
    model.beginModel(len(mesh.vertices), len(mesh.faces))
    model.addSubModel(np.asarray(mesh.vertices, float), np.asarray(mesh.faces, np.int32))
    model.endModel()
    return fcl.CollisionObject(model)


class _Sweep:
    def __init__(self, scene, gripper=None):
        cage, ball = scene.body("cage"), scene.body("ball")
        walls = trimesh.util.concatenate([p.copy().apply_translation(cage.pos) for p in cage.collision])
        core = trimesh.util.concatenate(ball.collision)
        self.cage = _bvh(walls)
        self.moving = _bvh(trimesh.util.concatenate([core, gripper[0]]) if gripper else core)
        self.axis = cage.pos[:2]
        self.outer = np.linalg.norm(walls.vertices[:, :2]-self.axis, axis=1).max()
        self.top = walls.vertices[:, 2].max()
        self.reach = np.linalg.norm(core.vertices, axis=1).max()
        self.dirs = directions()

    def _place(self, pos, rot):
        self.moving.setTransform(fcl.Transform(rot.as_matrix(), np.asarray(pos, float)))

    def hit(self, pos, rot):
        self._place(pos, rot)
        return fcl.collide(self.moving, self.cage, fcl.CollisionRequest(), fcl.CollisionResult()) > 0

    def depth(self, pos, rot):
        self._place(pos, rot)
        result = fcl.CollisionResult()
        fcl.collide(self.moving, self.cage, fcl.CollisionRequest(num_max_contacts=64, enable_contact=True), result)
        return max((c.penetration_depth for c in result.contacts), default=0.)

    def free(self, pos, rot, first=False):
        """Directions along which a pure translation leaves the cage's bounding cylinder without contact."""
        ok = []
        for d in self.dirs:
            for k in range(1, 2000):
                p = pos+d*k*STEP
                if self.hit(p, rot):
                    break
                if np.linalg.norm(p[:2]-self.axis) > self.outer+self.reach or p[2]-self.reach > self.top:
                    ok.append(d)
                    break
            if ok and first:
                break
        return ok

    def turns(self, pos, rot, axes):
        """Smallest turn per axis and side that stays clear and opens a straight pull."""
        found = {}
        for name, axis in axes.items():
            for sign in (1, -1):
                for deg in range(1, 181):
                    turned = Rotation.from_rotvec(np.radians(sign*deg)*np.asarray(axis, float))*rot
                    if self.hit(pos, turned):
                        break
                    if deg % ANGLE_STEP == 0 and self.free(pos, turned, first=True):
                        found[name+"+-"[sign < 0]] = sign*deg
                        break
        return found


def _central(dirs):
    """The free direction closest to the mean of all free directions."""
    if not dirs:
        return None
    dirs = np.asarray(dirs)
    mean = dirs.mean(0)
    return dirs[np.argmax(dirs@mean)].round(3).tolist()


def check(scene, pos=None, quat=None, gripper=None, rotate=True, lift=0., axes=None):
    """gripper: (mesh in the ball frame, {axis name: world unit vector}) from gripper_geometry().
    lift: raise the start pose first (m), e.g. the small pick-up before a pull.
    axes: turn only about these axis names (approach / fingers / palm, or x / y / z without a gripper)."""
    start = time.perf_counter()
    if pos is None:
        pos, quat = ball_pose_from_scene(scene)
    pos, rot = np.asarray(pos, float)+[0, 0, lift], Rotation.from_quat(np.asarray(quat, float)[[1, 2, 3, 0]])
    sweep = _Sweep(scene, gripper)
    result = dict(scene=scene.name, overrides=scene.extras.get("overrides", {}), gripper=gripper is not None,
                  directions=len(sweep.dirs), start_lift_m=lift, position_m=pos.round(5).tolist(),
                  quaternion_wxyz=np.asarray(quat, float).round(6).tolist())
    lift = next((h for h in np.arange(0, LIFT+1e-9, 5e-4) if not sweep.hit(pos+[0, 0, h], rot)), None)
    if lift is None:
        result.update(label="start in collision", start_collision_m=sweep.depth(pos, rot))
    else:
        pos = pos+[0, 0, lift]
        free = sweep.free(pos, rot)
        result.update(lift_m=float(lift), straight_exits=len(free), best_direction=_central(free))
        if free:
            result["label"] = "very_easy"
        elif rotate:
            axes = {k: v for k, v in (gripper[1] if gripper else dict(zip("xyz", np.eye(3)))).items()
                    if axes is None or k in axes}
            turns = sweep.turns(pos, rot, axes)
            result["turns_deg"] = turns
            if turns:
                name = min(turns, key=lambda k: abs(turns[k]))
                turned = Rotation.from_rotvec(np.radians(turns[name])*np.asarray(axes[name[:-1]], float))*rot
                exits = sweep.free(pos, turned)
                result["min_rotation"] = dict(axis=name[:-1], theta_deg=turns[name], straight_exits=len(exits),
                                              best_direction=_central(exits))
            result["label"] = "easier" if turns else "no exit with one turn"
        else:
            result["label"] = "no straight exit"
    result["seconds"] = round(time.perf_counter()-start, 2)
    return result


def summary(result):
    if result["label"] == "start in collision":
        return f"{result['scene']}: start in collision, depth {result['start_collision_m']*1e3:.1f} mm"
    line = f"{result['scene']}: {result['label']}; straight exits {result['straight_exits']}/{result['directions']}"
    if result.get("min_rotation"):
        r = result["min_rotation"]
        line += f"; turn {r['theta_deg']:+d} deg about {r['axis']} -> {r['straight_exits']} exits"
    if "turns_deg" in result:
        line += f"; per axis {result['turns_deg'] or 'none'}"
    return line+f" ({result['seconds']} s)"


def ball_pose_from_scene(scene):
    ball = scene.body("ball")
    return np.asarray(ball.pos, float), np.asarray(ball.quat, float)


def spikes(scene):
    """Off-centre ball collision pieces: spike direction and tip distance, in the ball frame."""
    found = []
    for piece in scene.body("ball").collision:
        centre = piece.centroid
        if np.linalg.norm(centre) > .005:  # the core sits on the origin
            d = centre/np.linalg.norm(centre)
            found.append(dict(direction=d, tip_m=float((piece.vertices@d).max())))
    return found


def spike_table(scene):
    """One line per spike at the scene's start pose: world azimuth / elevation and tip beyond the cage."""
    pos, quat = ball_pose_from_scene(scene)
    rot, cage = Rotation.from_quat(quat[[1, 2, 3, 0]]), scene.body("cage")
    outer = max(np.linalg.norm(p.vertices[:, :2]+cage.pos[:2]-cage.pos[:2], axis=1).max() for p in cage.collision)
    lines = []
    for i, s in enumerate(spikes(scene)):
        d = rot.apply(s["direction"])
        tip = pos+d*s["tip_m"]
        lines.append(f"spike {i}: azimuth {np.degrees(np.arctan2(d[1], d[0])):6.1f} deg, elevation "
                     f"{np.degrees(np.arcsin(d[2])):5.1f} deg, tip {(np.linalg.norm(tip[:2]-cage.pos[:2])-outer)*1e3:+5.1f} mm "
                     "beyond the cage's outer radius")
    return "\n".join(lines)


def grasp(scene, azimuth_deg=0., lift=0., roll_deg=0., spike=None):
    """2F-85 pinch on the ball (lifted by `lift`), fingers closed for 0.5 s on the pinned ball.
    Without `spike`: level approach from `azimuth_deg`, pinch on the ball centre. With `spike` (index
    into spikes()): approach along that spike from outside, pinch SPIKE_PINCH from its tip.
    roll as in mjcf.aim_gripper. Returns (model, data)."""
    model = mjcf.build(scene, gripper=True)
    data = mujoco.MjData(model)
    data.qpos[model.joint("ball_free").qposadr[0]+2] += lift
    mujoco.mj_forward(model, data)
    ball = model.body("ball").id
    if spike is None:
        mjcf.place_gripper(model, data, data.xpos[ball], azimuth_deg, standoff=0, roll_deg=roll_deg)
    else:
        s = spikes(scene)[spike]
        d = data.xmat[ball].reshape(3, 3)@s["direction"]
        mjcf.aim_gripper(model, data, data.xpos[ball]+d*(s["tip_m"]-SPIKE_PINCH), -d, roll_deg)
    # Ball and wrist held, cage contacts off: the fingers close until they touch the ball and nothing
    # shoves the gripper; check() judges any gripper-cage overlap afterwards.
    mjcf.hold(model, data, "ball", "pin")
    mjcf.hold(model, data, "wrist", "pin")
    static, hand = model.geom_contype == mjcf.STATIC, model.geom_contype == mjcf.GRIPPER
    model.geom_conaffinity[static] &= ~mjcf.GRIPPER  # a pair collides if either side accepts the other
    model.geom_conaffinity[hand] &= ~mjcf.STATIC
    data.ctrl[model.actuator("g_fingers_actuator").id] = 255
    for _ in range(int(.5/model.opt.timestep)):
        mujoco.mj_step(model, data)
    model.geom_conaffinity[static] |= mjcf.GRIPPER
    model.geom_conaffinity[hand] |= mjcf.STATIC
    return model, data


def ball_pose(model, data):
    ball = model.body("ball").id
    return data.xpos[ball].copy(), data.xquat[ball].copy()


def gripper_geometry(model, data):
    """2F-85 collision geoms (convex hulls, current finger opening) in the ball frame, plus its axes in the world."""
    ball = model.body("ball").id
    to_ball = data.xmat[ball].reshape(3, 3)
    parts = []
    for g in np.flatnonzero(model.geom_contype == mjcf.GRIPPER):
        if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
            m = model.geom_dataid[g]
            local = model.mesh_vert[model.mesh_vertadr[m]:model.mesh_vertadr[m]+model.mesh_vertnum[m]]
        elif model.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX:
            local = trimesh.creation.box(extents=2*model.geom_size[g]).vertices
        else:
            continue
        world = data.geom_xpos[g]+local@data.geom_xmat[g].reshape(3, 3).T
        parts.append(trimesh.convex.convex_hull((world-data.xpos[ball])@to_ball))
    wrist = data.xmat[model.body("wrist").id].reshape(3, 3)
    # The 2F-85 base is turned 90 deg about z in its MJCF: the fingers open along the root x axis.
    return trimesh.util.concatenate(parts), dict(approach=wrist[:, 2], fingers=wrist[:, 0], palm=wrist[:, 1])


def save(result):
    path = scenes.RUNS/"checks"/result["scene"]/f"check_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1)+"\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", default="hedgehog_in_cage_easy")
    parser.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    parser.add_argument("--pose", type=Path, help="pose file saved by the viewer (ball and gripper as saved)")
    parser.add_argument("--grasp", type=float, metavar="AZIMUTH_DEG",
                        help="hold the ball with the 2F-85 from this azimuth (fingers closed on the ball centre)")
    parser.add_argument("--spike", type=int, help=f"grasp this spike {SPIKE_PINCH*1e3:.0f} mm from its tip, "
                        "approaching along it (prints the spike table)")
    parser.add_argument("--roll", type=float, default=0., help="with --grasp/--spike: 0 fingers open in the vertical plane")
    parser.add_argument("--axes", nargs="*", help="turn only about these axes, e.g. approach")
    parser.add_argument("--lift-mm", type=float, default=0., help="raise the ball this much before the checks")
    parser.add_argument("--no-rotate", action="store_true")
    args = parser.parse_args()
    lift = args.lift_mm/1e3
    if args.pose:
        scene, model, data = mjcf.load_pose(args.pose)
        gripper = gripper_geometry(model, data) if mjcf.has_gripper(model) else None
        result = check(scene, *ball_pose(model, data), gripper=gripper, rotate=not args.no_rotate, lift=lift)
    elif args.grasp is not None or args.spike is not None:
        scene = scenes.build(args.scene, scenes.parse_sets(args.set))
        if args.spike is not None:
            print(spike_table(scene))
        model, data = grasp(scene, args.grasp or 0., lift, args.roll, args.spike)
        result = check(scene, *ball_pose(model, data), gripper=gripper_geometry(model, data),
                       rotate=not args.no_rotate, axes=args.axes)
        result.update(grasp_azimuth_deg=args.grasp, grasp_spike=args.spike, grasp_roll_deg=args.roll, start_lift_m=lift)
    else:
        result = check(scenes.build(args.scene, scenes.parse_sets(args.set)), rotate=not args.no_rotate, lift=lift,
                       axes=args.axes)
    print(summary(result))
    print(f"report: {save(result)}")


if __name__ == "__main__":
    main()
