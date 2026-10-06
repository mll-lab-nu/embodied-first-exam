"""Read-only ALOHA IK for the Slotted Post Ring oracle.

TCP poses are converted to the hand link with the robot group's TCP offset and
solved with the native Genesis IK, then FK-checked. Several seeds are tried and
the solution closest to the current arm wins, so free transfers keep a stable
branch; straight Cartesian segments are solved sample by sample and rejected
when the branch jumps. No simulator state is written.
"""
import numpy as np
from scipy.spatial.transform import Rotation as R


def rot(wxyz):
    return R.from_quat(np.asarray(wxyz, float)[[1, 2, 3, 0]])


def wxyz(r):
    return r.as_quat()[[3, 0, 1, 2]]


def frame(x, y):
    """Rotation whose columns are x, the part of y orthogonal to x, and x × y."""
    x = np.asarray(x, float); x = x/np.linalg.norm(x)
    y = np.asarray(y, float); y = y-x*np.dot(x, y); y = y/np.linalg.norm(y)
    return R.from_matrix(np.column_stack([x, y, np.cross(x, y)]))


# Seeds: shoulder / elbow / wrist bends with three forearm rolls; the last row is the home bend.
SEED_BENDS = ((-.3, .5, 1.2), (0., .3, .8), (-.6, .9, .6), (.2, 0., 1.4), (-.96, 1.16, -.3))
SEED_ROLLS = (0., np.pi/2, -np.pi/2)


class ArmIK:
    def __init__(self, robot, *, joint_margin_rad=.01, position_tolerance_m=2e-4,
                 orientation_tolerance_rad=5e-3, max_branch_step_rad=.25):
        from topogym.solvers.genesis_kinematics import GenesisFKSolver
        from topogym.planning.oracle_ik import OracleIKSolver as GenesisIKSolver
        self.robot = robot
        self.ik_solver, self.fk_solver = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)
        self.margin, self.max_step = float(joint_margin_rad), float(max_branch_step_rad)
        self.tolerances = dict(position_tolerance_m=position_tolerance_m,
                               orientation_tolerance_rad=orientation_tolerance_rad)
        self._points = {}

    def _collision_points(self, side, per_geom=120):
        """Link-local collision vertex samples of one arm and its gripper: [(link index, points)]."""
        if side not in self._points:
            out = []
            for link in self.robot.entity.links:
                if not link.name.startswith(side+"/"):
                    continue
                for geom in link.geoms:
                    v = np.asarray(geom.init_verts, float).reshape(-1, 3)
                    if not len(v):
                        continue
                    v = v[np.linspace(0, len(v)-1, min(per_geom, len(v))).astype(int)]
                    out.append((link.idx_local, rot(geom.init_quat).apply(v)+np.asarray(geom.init_pos, float)))
            self._points[side] = out
        return self._points[side]

    def penetration(self, side, qpos, boxes, margin_m):
        """Deepest intrusion (m, 0 when clear) of the arm's collision samples into boxes grown by margin_m."""
        pose = self.fk_solver.solve(np.asarray(qpos, float))
        positions = np.asarray(pose["position_world_m"]).reshape(-1, 3)
        orientations = np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)
        points = np.vstack([rot(orientations[i]).apply(v)+positions[i] for i, v in self._collision_points(side)])
        worst = 0.
        for lower, upper in boxes:
            lo, hi = np.asarray(lower)-margin_m, np.asarray(upper)+margin_m
            depth = np.minimum(points-lo, hi-points).min(axis=1)
            worst = max(worst, float(depth.max()))
        return worst

    def arm(self, side, qpos):
        return np.asarray(qpos, float)[self.robot._q_indices[side][:6]].copy()

    def with_arm(self, qpos, side, arm):
        q = np.asarray(qpos, float).copy()
        q[self.robot._q_indices[side][:6]] = arm
        return q

    def tcp(self, side, qpos):
        g = self.robot.groups[side]
        pose = self.fk_solver.solve(np.asarray(qpos, float))
        link = self.robot.entity.get_link(g.hand_link).idx_local
        hp = np.asarray(pose["position_world_m"]).reshape(-1, 3)[link]
        hr = rot(np.asarray(pose["orientation_wxyz"]).reshape(-1, 4)[link])
        return hp+hr.apply(g.tcp_position_in_hand_m), hr*rot(g.tcp_orientation_in_hand_wxyz)

    def solve(self, side, p, r, qpos):
        """Full qpos reaching TCP pose (p, r) from seed qpos; raises ValueError when unreachable."""
        g = self.robot.groups[side]
        hand_r = r*rot(g.tcp_orientation_in_hand_wxyz).inv()
        q = self.ik_solver.solve_checked(link_name=g.hand_link,
                                         position_world_m=np.asarray(p, float)-hand_r.apply(g.tcp_position_in_hand_m),
                                         orientation_wxyz=wxyz(hand_r), initial_qpos=np.asarray(qpos, float),
                                         joint_dof_indices=self.robot._indices[side][:6], **self.tolerances)
        limits, arm = np.asarray(g.arm_limits_rad), self.arm(side, q)
        if np.any(arm < limits[:, 0]+self.margin) or np.any(arm > limits[:, 1]-self.margin):
            raise ValueError(f"{side} joint limit {np.round(arm, 3).tolist()}")
        return q

    def seeds(self, side, qpos):
        """The current configuration followed by the bend/roll seed family for one arm."""
        out = [np.asarray(qpos, float)]
        for shoulder, elbow, wrist in SEED_BENDS:
            for roll in SEED_ROLLS:
                out.append(self.with_arm(qpos, side, [0., shoulder, elbow, roll, wrist, 0.]))
        return out

    def solve_near(self, side, p, r, qpos):
        """Multi-seed IK; the solution closest to the current arm joints."""
        current, best, error = self.arm(side, qpos), None, None
        for seed in self.seeds(side, qpos):
            try:
                q = self.solve(side, p, r, seed)
            except ValueError as exc:
                error = exc
                continue
            distance = float(np.abs(self.arm(side, q)-current).max())
            if best is None or distance < best[0]:
                best = (distance, q)
        if best is None:
            raise ValueError(f"{side} pose unreachable from every seed: {error}")
        return best[1]

    def line(self, side, p1, r1, qpos, *, step_m=.004, step_rad=.03):
        """Arm joint waypoints along a straight TCP segment with slerped orientation."""
        from scipy.spatial.transform import Slerp
        q = np.asarray(qpos, float)
        p0, r0 = self.tcp(side, q)
        p1 = np.asarray(p1, float)
        count = max(2, int(np.ceil(max(np.linalg.norm(p1-p0)/step_m, (r0.inv()*r1).magnitude()/step_rad)))+1)
        slerp = Slerp([0, 1], R.concatenate([r0, r1]))
        out = []
        for u in np.linspace(0, 1, count)[1:]:
            qn = self.solve(side, p0+u*(p1-p0), slerp(u), q)
            jump = float(np.abs(self.arm(side, qn)-self.arm(side, q)).max())
            if jump > self.max_step:
                raise ValueError(f"{side} IK branch jump {jump:.3f} rad at u={u:.3f}")
            q = qn
            out.append(self.arm(side, q))
        return out
