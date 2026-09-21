"""Place the extracted ring above the table, release it, and observe settling."""
import numpy as np
import fcl
from scipy.spatial.transform import Rotation

from .gravity_demo import array
from .physical_plan import body_frame
from .robot_clearance import RobotClearance
from .robot_motion import Kinematics


def plan_release(motion):
    """Find a checked carried-ring path to a reachable table release point."""
    checker = RobotClearance(motion.cfg.robot_control, motion.task.assembly.template, float(motion.cfg.task.scale))
    kin = Kinematics(motion.cfg.robot_control)
    start = array(motion.robot.get_qpos()).copy()
    kin.q = start.copy()
    hp, hr = kin.pose("left")
    frame = body_frame(motion)
    rp = np.asarray(frame["target_ring"]["pos"])
    rr = Rotation.from_quat(frame["target_ring"]["quat"])
    normal = rr.apply([1., 0., 0.])
    radial = hp-rp
    radial -= normal*np.dot(radial, normal)
    radial /= np.linalg.norm(radial)
    basis = np.column_stack([radial, np.cross(normal, radial), normal])
    sign = -np.sign(np.dot(hr.apply([1., 0., 0.]), normal))
    table_local_z = float(motion.task.tabletop.frames.table_surface_origin[2])-motion.mount[2]

    def carried_frame(qpos):
        kin.q = np.asarray(qpos).copy()
        p, r = kin.pose("left")
        delta = r*hr.inv()
        result = dict(frame)
        result["target_ring"] = dict(pos=(p+delta.apply(rp-hp)).tolist(), quat=(delta*rr).as_quat().tolist())
        return result

    def valid(arm):
        qpos = start.copy()
        qpos[:6] = arm
        predicted = carried_frame(qpos)
        if checker.violations(qpos, predicted, first_only=True):
            return False
        pose = predicted["target_ring"]
        vertices = Rotation.from_quat(pose["quat"]).apply(checker.puzzle.meshes[-1].vertices)+pose["pos"]
        if vertices[:, 2].min() < table_local_z+.001:
            return False
        # RobotClearance has just updated these exact-hole collision objects.
        return all(fcl.distance(checker.puzzle.objects[-1], obj, fcl.DistanceRequest(), fcl.DistanceResult()) > .001
                   for obj in checker.puzzle.objects[:-1])

    # The original demo's one world-space drop point can be outside the left
    # arm's reachable pose set after a different coupled extraction. Generated
    # instances may use two nearby table positions, preserving the first goal
    # and all IK/collision thresholds. This changes neither the grasp nor bodies.
    destinations = [(.12, .10)]
    if getattr(motion, "instance", None) is not None:
        destinations += [(0., .10), (-.12, .10)]
    goal = None
    tested = 0
    for destination_index, xy in enumerate(destinations):
        destination = np.r_[np.asarray(xy)-motion.mount[:2], table_local_z+.030]
        for angle in (180, 150, 120, 90, 60, 30, 0, -90):
            n = np.array([0., 0., sign])
            d = np.array([np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle)), 0.])
            delta = Rotation.from_matrix(np.column_stack([d, np.cross(n, d), n])@basis.T)
            kin.q = start.copy()
            error = kin.solve("left", destination+delta.apply(hp-rp), delta*hr)
            candidate = kin.q.copy()
            tested += 1
            if error[0] < .0005 and error[1] < .005 and valid(candidate[:6]):
                goal = candidate
                break
        if goal is not None:
            break
    if goal is None:
        raise RuntimeError("No checked horizontal ring release pose above the table")
    if not valid(start[:6]):
        raise RuntimeError("Ring placement must begin from a separated, collision-free grasp")
    count = max(2, int(np.ceil(np.max(np.abs(goal[:6]-start[:6]))/.003)))
    direct = all(valid((1-u)*start[:6]+u*goal[:6]) for u in np.linspace(0., 1., count+1))
    path = np.array([start[:6], goal[:6]])
    if not direct:
        from ompl import base as ob, geometric as og
        space = ob.RealVectorStateSpace(6)
        bounds = ob.RealVectorBounds(6)
        for i, (lo, hi) in enumerate(kin.limits):
            bounds.setLow(i, float(lo)+1e-6)
            bounds.setHigh(i, float(hi)-1e-6)
        space.setBounds(bounds)
        setup = og.SimpleSetup(space)
        setup.setStateValidityChecker(lambda state: valid([state[i] for i in range(6)]))
        setup.getSpaceInformation().setStateValidityCheckingResolution(.0001)
        a, b = space.allocState(), space.allocState()
        for i in range(6):
            a[i], b[i] = float(start[i]), float(goal[i])
        setup.setStartAndGoalStates(a, b, 1e-6)
        planner = og.RRTConnect(setup.getSpaceInformation())
        planner.setRange(.2)
        setup.setPlanner(planner)
        setup.solve(30.)
        if not setup.haveExactSolutionPath():
            raise RuntimeError("No collision-free attached-ring placement path")
        path = np.array([[state[i] for i in range(6)] for state in setup.getSolutionPath().getStates()])
    return dict(direct=direct, arm_waypoints=path.tolist(), release_com_above_table_m=.030,
        release_center_world_m=(destination+motion.mount).tolist(),
        release_destination_index=destination_index, release_goal_candidates_tested=tested)


def release_ring(motion):
    plan = plan_release(motion)
    path = np.asarray(plan["arm_waypoints"])
    motion.events.append(dict(time_s=motion.step_count*motion.dt, phase="place_ring", **plan))
    motion.phase = "place_extracted_ring_above_table"
    for a, b in zip(path[:-1], path[1:]):
        seconds = max(.1, np.ceil(np.max(np.abs(b-a))/.3/.05)*.05)
        target = motion.q.copy()
        target[:6] = b
        motion.joint_segment(target, seconds)
    motion.hold(.5, phase="confirm_ring_placement")
    motion.replace_grasps([("right", "horseshoe_left"), ("right", "horseshoe_right")],
                           reason="release separated ring into free gravity above the table")
    q = motion.q.copy()
    q[6:8] = .037
    motion.joint_segment(q, .5, phase="open_left_after_ring_release")
    motion.hold(3., phase="ring_free_settle_on_table")
