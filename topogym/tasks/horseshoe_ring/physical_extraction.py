"""Relative ring planning and redundant two-arm IK for gravity execution.

The geometric witness supplies intermediate goals, never simulated body poses.
Both complete grippers participate in relative collision checks. Joint IK can
move both hands together to keep the forearms apart. Dynamics, chain motion,
grasp qualification and the final task verdict belong to PhysicalMotion.
"""
from __future__ import annotations

import json
from itertools import product
import time

import fcl
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .physical_motion import PHYSICAL_SEED
from .robot_clearance import RobotClearance
from .robot_motion import Kinematics


class RelativeExtraction:
    def __init__(self, cfg, template, scale, frame, qpos):
        self.cfg, self.frame = cfg, frame
        self.scale_ratio = scale/2.
        self.q0 = np.asarray(qpos).copy()
        self.geometry = RobotClearance(cfg, template, scale)
        # Keep these objects separate: checking a candidate IK mutates every
        # FCL transform, whereas relative planning uses a fixed reference frame.
        self.clearance = RobotClearance(cfg, template, scale)
        self.kin = Kinematics(cfg)
        self.kin.q = self.q0.copy()
        self.hp, self.hr = self.kin.pose("left")
        self.rhp, self.rhr = self.kin.pose("right")
        self.rp = np.asarray(frame["target_ring"]["pos"])
        self.rr = Rotation.from_quat(frame["target_ring"]["quat"])
        self.normal = self.rr.apply([1., 0., 0.])
        self.azimuth = np.arctan2(self.normal[1], self.normal[0])
        self.elevation = np.arcsin(self.normal[2])
        self.tilt_axis = np.array([np.sin(self.azimuth), -np.cos(self.azimuth), 0.])
        self.puzzle = self.geometry.puzzle
        for name, obj in zip(self.puzzle.names, self.puzzle.objects):
            p = frame[name]
            obj.setTransform(fcl.Transform(Rotation.from_quat(p["quat"]).as_matrix(), np.asarray(p["pos"])))
        self.ring = self.puzzle.objects[self.puzzle.names.index("target_ring")]
        self.obstacles = [o for name, o in zip(self.puzzle.names, self.puzzle.objects) if name != "target_ring"]
        self.geometry.data.qpos[:] = self.q0
        mujoco.mj_forward(self.geometry.model, self.geometry.data)
        self.left_parts, self.right_parts = [], []
        for i, name, obj, *_ in self.geometry.geoms:
            if name.split("/")[-1] not in ("gripper_base", "gripper_link", "left_finger_link", "right_finger_link"):
                continue
            pos = self.geometry.data.geom_xpos[i].copy()
            rot = Rotation.from_matrix(self.geometry.data.geom_xmat[i].reshape(3, 3))
            obj.setTransform(fcl.Transform(rot.as_matrix(), pos))
            if name.startswith("left/"):
                self.left_parts.append((obj, pos, rot))
            else:
                self.right_parts.append(obj)
        self.request = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)
        self.kin.model.geom_margin[:] = .004
        self.floor_geoms = [(i, corners) for i, name, _, corners, _ in self.clearance.geoms if "base_link" not in name]
        from trimesh.bounds import corners
        self.reference_vertices = {}
        for name, mesh in zip(self.puzzle.names, self.puzzle.meshes):
            pose = frame[name]
            self.reference_vertices[name] = Rotation.from_quat(pose["quat"]).apply(corners(mesh.bounds))+pose["pos"]
        self.indices = np.r_[0:6, 8:14]
        self.limits = np.tile(self.kin.limits, (2, 1))
        self.calls = 0

    def ring_pose(self, state):
        v = np.asarray(state)
        turn = (Rotation.from_euler("z", v[3]/.05)
                * Rotation.from_rotvec(self.tilt_axis*v[4]/.05)
                * Rotation.from_rotvec(self.normal*v[5]/.05))
        return self.rp+v[:3], turn

    def overlap(self, a, b):
        return fcl.collide(a, b, self.request, fcl.CollisionResult()) > 0

    def valid(self, state):
        self.calls += 1
        p, r = self.ring_pose(state)
        self.ring.setTransform(fcl.Transform((r*self.rr).as_matrix(), p))
        if any(self.overlap(self.ring, o) for o in self.obstacles+self.right_parts):
            return False
        for obj, p0, r0 in self.left_parts:
            obj.setTransform(fcl.Transform((r*r0).as_matrix(), p+r.apply(p0-self.rp)))
            if any(self.overlap(obj, o) for o in self.obstacles+self.right_parts):
                return False
        return True

    def guide(self):
        """Map the baseline geometric milestones into the measured shoe frame."""
        source = json.loads(PHYSICAL_SEED.read_text())["extraction_guide"]
        old = source["fixed_left_pose"]
        actual = self.frame["horseshoe_left"]
        rotation = Rotation.from_quat(actual["quat"])*Rotation.from_quat(old["quat"]).inv()
        offset = np.asarray(actual["pos"])-rotation.apply(self.scale_ratio*np.asarray(old["pos"]))
        phases = [(0, -150), (20, -150), (40, -135), (60, -105), (80, -60),
                  (100, -30), (120, -30), (140, -15), (160, 30), (180, 15),
                  (200, 0), (220, 0), (len(source["ring_poses"])-1, 0)]
        result = []
        for index, gamma in phases:
            pose = source["ring_poses"][index]
            pos = rotation.apply(self.scale_ratio*np.asarray(pose["pos"]))+offset
            n = (rotation*Rotation.from_quat(pose["quat"])).apply([1., 0., 0.])
            phi = np.arctan2(n[1], n[0])-self.azimuth
            phi = (phi+np.pi) % (2*np.pi)-np.pi
            theta = np.arcsin(n[2])-self.elevation
            result.append((index, np.r_[pos-self.rp, phi*.05, theta*.05, np.deg2rad(gamma)*.05]))
        return result

    def plan_segment(self, start, goal, *, seconds=30.):
        from ompl import base as ob, geometric as og
        start, goal = np.asarray(start), np.asarray(goal).copy()
        requested_goal = goal.copy()
        if not self.valid(start):
            raise RuntimeError("Relative extraction starts in collision")
        if not self.valid(goal):
            # The geometric witness is a guide, not a rigid waypoint contract:
            # contact-loaded shoes and free chains differ by millimetres from
            # its ideal folded pose. Search a bounded neighbourhood while
            # retaining the exact same ring AND complete-gripper collision gate.
            phases = sorted(np.deg2rad(np.arange(-180, 180, 5))*.05,
                            key=lambda gamma: abs(gamma-goal[5]))
            alternative = None
            for radius in (0., .001, .002, .004):
                offsets = sorted(product((-radius, 0., radius), repeat=3), key=np.linalg.norm) if radius else [(0., 0., 0.)]
                for offset in offsets:
                    for gamma in phases:
                        trial = requested_goal.copy()
                        trial[:3] += offset
                        trial[5] = gamma
                        if self.valid(trial):
                            alternative = trial
                            break
                    if alternative is not None:
                        break
                if alternative is not None:
                    break
            if alternative is None:
                raise RuntimeError("No collision-free ring/gripper pose near this extraction milestone")
            goal = alternative
        space = ob.RealVectorStateSpace(6)
        bounds = ob.RealVectorBounds(6)
        for i in range(6):
            bounds.setLow(i, float(min(start[i], goal[i])-.035))
            bounds.setHigh(i, float(max(start[i], goal[i])+.035))
        space.setBounds(bounds)
        setup = og.SimpleSetup(space)
        setup.setStateValidityChecker(lambda state: self.valid([state[i] for i in range(6)]))
        setup.getSpaceInformation().setStateValidityCheckingResolution(.0018)
        a, b = space.allocState(), space.allocState()
        for i in range(6):
            a[i], b[i] = float(start[i]), float(goal[i])
        setup.setStartAndGoalStates(a, b, 1e-5)
        planner = og.RRTConnect(setup.getSpaceInformation())
        planner.setRange(.014)
        setup.setPlanner(planner)
        begun = time.monotonic()
        setup.solve(seconds)
        if not setup.haveExactSolutionPath():
            raise RuntimeError("No exact collision-free relative extraction segment")
        path = np.array([[state[i] for i in range(6)] for state in setup.getSolutionPath().getStates()])
        return path, dict(method="RRTConnect_relative_ring_and_grippers", waypoints=path.tolist(),
                          requested_goal=requested_goal.tolist(), selected_goal=goal.tolist(),
                          guide_translation_adjustment_m=float(np.linalg.norm(goal[:3]-requested_goal[:3])),
                          elapsed_s=time.monotonic()-begun, calls=self.calls,
                          scope="sampled geometry; execution must additionally pass physical contact checks")

    @staticmethod
    def samples(path, spacing=.0015):
        yield np.asarray(path[0])
        for a, b in zip(path[:-1], path[1:]):
            count = max(1, int(np.ceil(np.linalg.norm(np.asarray(b)-a)/spacing)))
            for u in np.linspace(0., 1., count+1)[1:]:
                yield (1-u)*np.asarray(a)+u*np.asarray(b)

    def solve(self, state, seed):
        """Solve both arms' relative pose, using redundancy for self clearance."""
        p, r = self.ring_pose(state)
        relpos = self.rhr.inv().apply(p+r.apply(self.hp-self.rp)-self.rhp)
        relrot = self.rhr.inv()*r*self.hr
        seed = np.asarray(seed)
        kin = self.kin
        kin.q = seed.copy()

        def residual(x):
            kin.q[self.indices] = x
            pl, rl = kin.pose("left")
            pr, rr = kin.pose("right")
            # Fixed residual dimensions; aggregate near contacts by body.
            # Every active contact contributes to both incident bodies.
            pen = np.zeros(kin.model.nbody)
            for contact in kin.data.contact:
                depth = max(0., .003-contact.dist)
                for body in kin.model.geom_bodyid[[int(contact.geom1), int(contact.geom2)]]:
                    pen[body] = max(pen[body], depth)
            floor = [max(0., .003-float((vertices@kin.data.geom_xmat[i].reshape(3, 3).T
                                       +kin.data.geom_xpos[i])[:, 2].min())) for i, vertices in self.floor_geoms]
            common = rr*self.rhr.inv()
            delta_left = rl*self.hr.inv()
            for name, vertices in self.reference_vertices.items():
                points = (pl+delta_left.apply(vertices-self.hp)) if name == "target_ring" else \
                         (pr+common.apply(vertices-self.rhp))
                floor.append(max(0., .003-float(points[:, 2].min())))
            return np.r_[100*(rr.inv().apply(pl-pr)-relpos),
                         10*(relrot*(rr.inv()*rl).inv()).as_rotvec(),
                         100*pen, 100*np.asarray(floor), .0001*(x-seed[self.indices])]

        fit = least_squares(residual, seed[self.indices],
            bounds=(self.limits[:, 0]+1e-6, self.limits[:, 1]-1e-6),
            max_nfev=100, ftol=1e-10, xtol=1e-10, gtol=1e-8)
        residuals = residual(fit.x)
        error = [float(np.linalg.norm(residuals[:3])/100), float(np.linalg.norm(residuals[3:6])/10)]
        projected = error[0] > .00001 or error[1] > .0001
        if projected:
            # Clearance is a soft preference; never trade the grasp transform
            # for a slightly larger margin. Project back onto the exact
            # relative-pose constraint, then run the same hard collision tests.
            soft = kin.q.copy()

            def exact_relative(x):
                kin.q[self.indices] = x
                pl, rl = kin.pose("left")
                pr, rr = kin.pose("right")
                return np.r_[100*(rr.inv().apply(pl-pr)-relpos),
                    10*(relrot*(rr.inv()*rl).inv()).as_rotvec(), .0001*(x-soft[self.indices])]

            fit = least_squares(exact_relative, soft[self.indices],
                bounds=(self.limits[:, 0]+1e-6, self.limits[:, 1]-1e-6),
                max_nfev=100, ftol=1e-10, xtol=1e-10, gtol=1e-8)
            residuals = residual(fit.x)
            error = [float(np.linalg.norm(residuals[:3])/100), float(np.linalg.norm(residuals[3:6])/10)]
        pr, rr = kin.pose("right")
        common = rr*self.rhr.inv()
        offset = pr-common.apply(self.rhp)
        frame = {name: dict(pos=(common.apply(pose["pos"])+offset).tolist(),
            quat=(common*Rotation.from_quat(pose["quat"])).as_quat().tolist()) for name, pose in self.frame.items()}
        frame["target_ring"] = dict(pos=(common.apply(p)+offset).tolist(), quat=(common*r*self.rr).as_quat().tolist())
        bad = self.clearance.violations(kin.q, frame, first_only=True)
        if error[0] > .0005 or error[1] > .005 or bad:
            raise RuntimeError(f"Coupled extraction IK rejected: error={error}, collisions={bad}")
        return kin.q.copy(), dict(state=np.asarray(state).tolist(), position_error_m=error[0],
            rotation_error_rad=error[1], exact_relative_projection=projected, predicted_bodies=frame)
