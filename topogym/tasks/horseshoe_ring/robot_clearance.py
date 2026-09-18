"""Sampled robot/scene checks and collision-aware unladen joint transfers."""
import numpy as np
import fcl
import mujoco
from scipy.spatial.transform import Rotation
import trimesh

from topogym.robot.assets import robot_asset
from .independent_motion import IndependentWitness


class RobotClearance:
    def __init__(self, cfg, template, scale=2.):
        self.model = mujoco.MjModel.from_xml_path(robot_asset(cfg))
        self.data = mujoco.MjData(self.model)
        self.puzzle = IndependentWitness(template, scale)
        self.geoms = []
        m = self.model
        for i in range(m.ngeom):
            if not (m.geom_contype[i] or m.geom_conaffinity[i]):
                continue
            if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = m.mesh(m.geom_dataid[i])
                vertices = m.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0]+mesh.vertnum[0]]
                hull = trimesh.convex.convex_hull(vertices)
                shape = fcl.Convex(hull.vertices, len(hull.faces),
                    np.column_stack([np.full(len(hull.faces), 3), hull.faces]).reshape(-1))
                vertices = hull.vertices
                bounds = hull.bounds
            elif m.geom_type[i] == mujoco.mjtGeom.mjGEOM_SPHERE:
                radius = m.geom_size[i, 0]
                shape = fcl.Sphere(radius)
                bounds = np.array([[-radius]*3, [radius]*3])
                vertices = trimesh.bounds.corners(bounds)
            else:
                raise ValueError("Unsupported ALOHA collision primitive")
            self.geoms.append((i, m.body(m.geom_bodyid[i]).name, fcl.CollisionObject(shape),
                               trimesh.bounds.corners(bounds), vertices))
        self.request = fcl.CollisionRequest(num_max_contacts=16, enable_contact=True)

    def violations(self, qpos, frame, *, side=None, first_only=False):
        m, d = self.model, self.data
        d.qpos[:] = qpos
        mujoco.mj_forward(m, d)
        bad = []
        for contact in d.contact:
            if contact.dist < -.0001:
                bad.append(dict(kind="robot_self_contact", depth_m=float(-contact.dist),
                    a=m.body(m.geom_bodyid[contact.geom1]).name, b=m.body(m.geom_bodyid[contact.geom2]).name))
                if first_only:
                    return bad
        bounds = []
        for name, obj, mesh in zip(self.puzzle.names, self.puzzle.objects, self.puzzle.meshes):
            pose = frame[name]
            r, p = Rotation.from_quat(pose["quat"]).as_matrix(), np.asarray(pose["pos"])
            obj.setTransform(fcl.Transform(r, p))
            points = trimesh.bounds.corners(mesh.bounds)@r.T+p
            bounds.append((points.min(0), points.max(0)))
        for i, name, obj, corners, vertices in self.geoms:
            if side and not name.startswith(side+"/"):
                continue
            r, p = d.geom_xmat[i].reshape(3, 3), d.geom_xpos[i]
            obj.setTransform(fcl.Transform(r, p))
            points = corners@r.T+p
            low, high = points.min(0), points.max(0)
            if low[2] < -.001 and "base_link" not in name:
                z = float((vertices@r.T+p)[:, 2].min())
                if z < -.001:
                    bad.append(dict(kind="table_penetration", robot=name, depth_m=-z))
            for part, other, (lo, hi) in zip(self.puzzle.names, self.puzzle.objects, bounds):
                if np.any(low > hi) or np.any(high < lo):
                    continue
                result = fcl.CollisionResult()
                fcl.collide(obj, other, self.request, result)
                depth = max((c.penetration_depth for c in result.contacts), default=0.)
                if result.is_collision and depth > .0003:
                    bad.append(dict(kind="robot_puzzle_penetration", robot=name, puzzle=part, depth_m=float(depth)))
                if bad and first_only:
                    return bad
        return bad

    def joint_transfer(self, start, end, side, frame, *, fps=12):
        """Return a sampled, checked path with the other arm and puzzle fixed."""
        from ompl import base as ob, geometric as og
        start, end = np.asarray(start).copy(), np.asarray(end).copy()
        indices = np.arange(0, 6) if side == "left" else np.arange(8, 14)
        limits = self.model.jnt_range[indices]

        def valid(values):
            q = start.copy()
            q[indices] = np.asarray(values)
            return not self.violations(q, frame, side=side, first_only=True)

        if not valid(start[indices]) or not valid(end[indices]):
            raise RuntimeError(f"Invalid {side} transfer endpoint")
        samples = max(2, int(np.ceil(np.max(np.abs(end[indices]-start[indices]))/.003))+1)
        direct = all(valid((1-t)*start[indices]+t*end[indices]) for t in np.linspace(0, 1, samples))
        method = "checked_joint_segment"
        if direct:
            path = np.array([start[indices], end[indices]])
        else:
            space = ob.RealVectorStateSpace(6)
            bounds = ob.RealVectorBounds(6)
            for i, (lo, hi) in enumerate(limits):
                bounds.setLow(i, float(lo)+1e-6)
                bounds.setHigh(i, float(hi)-1e-6)
            space.setBounds(bounds)
            setup = og.SimpleSetup(space)
            setup.setStateValidityChecker(lambda s: valid([s[i] for i in range(6)]))
            setup.getSpaceInformation().setStateValidityCheckingResolution(.0001)
            a, b = space.allocState(), space.allocState()
            for i in range(6):
                a[i], b[i] = float(start[indices[i]]), float(end[indices[i]])
            setup.setStartAndGoalStates(a, b, 1e-6)
            planner = og.RRTConnect(setup.getSpaceInformation())
            planner.setRange(.3)
            setup.setPlanner(planner)
            setup.solve(20)
            if not setup.haveExactSolutionPath():
                raise RuntimeError(f"No checked {side} joint transfer found")
            setup.simplifySolution(.25)
            path = np.array([[s[i] for i in range(6)] for s in setup.getSolutionPath().getStates()])
            method = "RRTConnect_joint_transfer"
        lengths = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        count = max(2*fps, int(np.ceil(lengths[-1]/.8*fps)))
        result = []
        for t in np.linspace(0, lengths[-1], count+1)[1:]:
            k = min(np.searchsorted(lengths, t, side="right")-1, len(path)-2)
            u = (t-lengths[k])/max(lengths[k+1]-lengths[k], 1e-12)
            q = start.copy()
            q[indices] = (1-u)*path[k]+u*path[k+1]
            result.append(q)
        return result, dict(method=method, side=side, waypoints=path.tolist(), frames=count,
                            validity_scope="sampled robot self contact, puzzle overlap and tabletop clearance")
