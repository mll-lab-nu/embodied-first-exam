"""IK and contact-aware plans built from measured horseshoe physical states."""
import numpy as np
from scipy.spatial.transform import Rotation

from .gravity_demo import array
from .robot_motion import Kinematics
from .robot_clearance import RobotClearance


def body_frame(motion):
    return {n: dict(pos=(p-motion.mount).tolist(), quat=r.as_quat().tolist())
            for n in motion.task.bodies for p, r in [motion.body_pose(n)]}


def horizontal_support(motion):
    offset = np.array([.04, -.04, .08])
    center = motion.mount + [0., .05, .2]
    motion.transform_pair(Rotation.identity(), offset, 2., phase="lift_to_handover_workspace")
    motion.transform_pair(Rotation.from_euler("y", -90, degrees=True), np.zeros(3), 4.,
                          center=center+offset, phase="rotate_to_horizontal_stack")
    motion.hold(1., phase="horizontal_stack_settle")


def combine_horseshoes(motion):
    motion.replace_grasps([("left", "horseshoe_left")], reason="release upper shoe onto lower shoe under gravity")
    q = motion.q.copy()
    q[14:16] = .037
    motion.joint_segment(q, 1., phase="open_right_gripper")
    motion.hold(1., phase="settle_upper_shoe_on_lower_shoe")
    ct = motion.contacts()
    lower, upper = (motion.task.bodies[n].base_link_idx for n in ("horseshoe_left", "horseshoe_right"))
    # Load alternates between the lower band and the left pad immediately next
    # to it. Both are physically supported by the holding left arm. The open
    # right hand is deliberately excluded, since it is about to withdraw.
    supports = [lower, *motion.fingers["left"]]
    mask = ((ct["link_a"] == upper) & np.isin(ct["link_b"], supports)) | \
           ((ct["link_b"] == upper) & np.isin(ct["link_a"], supports))
    support_force = float(np.linalg.norm(ct["force"][mask], axis=-1).sum())
    pl, rl = motion.body_pose("horseshoe_left")
    pu, ru = motion.body_pose("horseshoe_right")
    delta = pu-pl
    aligned = (0. < delta[2] < .03 and np.linalg.norm(delta[:2]) < .04
               and abs(np.dot(rl.apply([0, 0, 1]), ru.apply([0, 0, 1]))) > .98)
    if support_force < .1 or not aligned:
        raise RuntimeError("Upper shoe has no loaded, aligned support from the lower shoe/left pad")
    motion.events.append(dict(time_s=motion.step_count*motion.dt, phase="verify_horizontal_support",
        support_force_N=support_force, upper_minus_lower_m=delta.tolist(), upper_shoe_assistance=False))
    p, r = motion.hand_pose("right")
    motion.cartesian({"right": (p-.02*r.apply([1, 0, 0]), r)}, 1., phase="withdraw_right_20mm")
    template = motion.task.assembly.template
    h = template["horseshoe"]
    unit = motion.task.assembly.unit
    center = (template["chain"]["eye_to_link_center"]+h["eye_offset_x"]
              +h["ellipse_radii"][0]*np.cos(np.deg2rad(h["mouth_half_angle_deg"])))*unit
    origins = {b.name: b.visual.center_mass for b in motion.task.assembly.bodies}
    points = []
    for side, sign in (("left", -1), ("right", 1)):
        name = "horseshoe_"+side
        p, r = motion.body_pose(name)
        points.append(p+r.apply(np.array([sign*center, h["ellipse_radii"][1]*unit, 0])-origins[name]))
    p = np.mean(points, axis=0)
    r = Rotation.from_euler("z", -30, degrees=True)*Rotation.from_matrix(
        np.column_stack([[0, -1, 0], [0, 0, 1], [-1, 0, 0]]))
    motion.cartesian({"right": (p-.04*r.apply([1, 0, 0]), r)}, 2., phase="combined_grasp_preapproach")
    motion.cartesian({"right": (p, r)}, 2., phase="combined_grasp_approach")
    motion.phase = "close_combined_grasp"
    for opening in np.linspace(.037, .014, 47)[1:]:
        q = motion.q.copy()
        q[14:16] = opening
        motion.joint_segment(q, .1)
        if motion.grasp_connected("right", ["horseshoe_left", "horseshoe_right"]):
            motion.hold(.1, phase="confirm_combined_contact")
            if motion.grasp_connected("right", ["horseshoe_left", "horseshoe_right"]):
                break
    else:
        raise RuntimeError("No pad-shoe-shoe-pad contact path for the combined grasp")
    motion.replace_grasps([("right", "horseshoe_left"), ("right", "horseshoe_right")],
                          reason="loaded pad-shoe-shoe-pad path confirms combined grasp")
    # The upper shoe lies immediately above the old left grasp. Opening here
    # wedges the upper finger against that shoe; withdraw with a narrow jaw
    # first, while the right hand already holds both bodies.
    q = motion.q.copy()
    q[6:8] = .0123
    motion.joint_segment(q, .3, phase="unload_left_grasp")
    transfer(motion, "left", motion.cfg.robot_control.home.left[:6], phase="withdraw_left_before_opening")
    q = motion.q.copy()
    q[6:8] = .037
    motion.joint_segment(q, 1., phase="release_left_gripper")
    motion.hold(2., phase="combined_grasp_settle")


def transfer(motion, side, arm_target, *, phase):
    """Plan the empty arm around the measured puzzle while the other arm holds."""
    checker = RobotClearance(motion.cfg.robot_control, motion.task.assembly.template, float(motion.cfg.task.scale))
    start = array(motion.robot.get_qpos()).copy()
    indices = slice(0, 6) if side == "left" else slice(8, 14)
    end = start.copy()
    end[indices] = arm_target
    trajectory, evidence = checker.joint_transfer(start, end, side, body_frame(motion), fps=20)
    motion.phase = phase
    print(f"{motion.step_count*motion.dt:.2f}s {phase}: {evidence['method']}", flush=True)
    motion.events.append(dict(time_s=motion.step_count*motion.dt, phase=phase, joint_transfer=evidence))
    for target in trajectory:
        q = motion.q.copy()
        q[indices] = target[indices]
        motion.joint_segment(q, .05)


def ring_grasp_frame(motion, angle, beta, roll=1):
    p, r = motion.body_pose("target_ring")
    loop = motion.task.assembly.loops["target_ring"]
    normal = r.apply(loop.rotation.apply([0, 0, 1]))
    radial = r.apply(loop.rotation.apply([np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle)), 0]))
    beta = np.deg2rad(beta)
    x = -radial*np.cos(beta) + normal*np.sin(beta)
    y = roll*(normal*np.cos(beta) + radial*np.sin(beta))
    rotation = Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))
    radius = motion.task.assembly.template["target_ring"]["centerline_radius"]*motion.task.assembly.unit
    return p + radius*radial, rotation


def tracked_ring_grasp_frame(motion, choice):
    """A circular ring's material spin must not move the chosen grasp around it.

    New generated instances track a gravity-referenced surface point. Preserve
    the original baseline runner's saved material-angle policy for compatibility.
    This recipe is deliberately limited to the admitted circular prototype.
    """
    angle = choice["angle"]
    if getattr(motion, "instance", None) is not None:
        _, rotation = motion.body_pose("target_ring")
        plane = rotation*motion.task.assembly.loops["target_ring"].rotation
        local_down = plane.inv().apply([0., 0., -1.])
        if np.linalg.norm(local_down[:2]) < 1e-6:
            raise RuntimeError("Ring plane has no stable gravity-referenced grasp direction")
        angle = np.rad2deg(np.arctan2(local_down[1], local_down[0]))+choice["gravity_angle_offset_deg"]
    return ring_grasp_frame(motion, angle, choice["beta"], choice["roll"])


def ring_candidates(motion):
    checker = RobotClearance(motion.cfg.robot_control, motion.task.assembly.template, float(motion.cfg.task.scale))
    kin = Kinematics(motion.cfg.robot_control)
    start = array(motion.robot.get_qpos()).copy()
    frame = body_frame(motion)
    rows = []
    # A circular ring has no preferred material phase. Anchor the samples to
    # world gravity so arbitrary spin during settling does not change the
    # grasp location or send the wrist onto the opposite IK branch.
    _, ring_rotation = motion.body_pose("target_ring")
    loop_rotation = motion.task.assembly.loops["target_ring"].rotation
    ring_plane = ring_rotation * loop_rotation
    down_local = ring_plane.inv().apply([0., 0., -1.])
    bottom_angle = np.rad2deg(np.arctan2(down_local[1], down_local[0]))
    for angle in bottom_angle + np.arange(0, 360, 30):
        for beta in (-60, -30, 0, 30, 60, 90, -90):
            for roll in (1, -1):
                p, r = ring_grasp_frame(motion, angle, beta, roll)
                pre = p-.04*r.apply([1, 0, 0])
                kin.q = start.copy()
                error = kin.solve("left", pre-motion.mount, r)
                if error[0] > .0005 or error[1] > .005:
                    continue
                pre_q = kin.q.copy()
                if checker.violations(pre_q, frame, side="left", first_only=True):
                    continue
                error = kin.solve("left", p-motion.mount, r)
                if error[0] > .0005 or error[1] > .005:
                    continue
                if checker.violations(kin.q, frame, side="left", first_only=True):
                    continue
                rows.append(dict(angle=angle, gravity_angle_offset_deg=float(angle-bottom_angle),
                    beta=beta, roll=roll, pre_qpos=pre_q.tolist(),
                    target_qpos=kin.q.tolist(), point_world=p.tolist(), quat_xyzw=r.as_quat().tolist(),
                    joint_distance=float(np.linalg.norm(pre_q[:6]-start[:6]))))
    # The low arc leaves the entire gripper below the horseshoes during the
    # subsequent lift/rotation. A shorter IK route to the side arc traps the
    # gripper base against the shoe/chain even though the ring itself clears.
    return sorted(rows, key=lambda row:(round(row["point_world"][2]/.002),
        Rotation.from_quat(row["quat_xyzw"]).apply([1, 0, 0])[1] > 0.,
        Rotation.from_quat(row["quat_xyzw"]).apply([1, 0, 0])[2] < .2,
        row["joint_distance"]))


def grasp_ring(motion):
    transfer(motion, "left", motion.cfg.robot_control.home.left[:6], phase="left_to_clearance_home")
    motion.hold(2., phase="ring_settle_before_grasp")
    rows = ring_candidates(motion)
    if not rows:
        raise RuntimeError("No collision-free reachable grasp of the actual ring")
    choice = rows[0]

    def attach_if_loaded():
        if not motion.grasp_connected("left", ["target_ring"]):
            return False
        motion.replace_grasps([("right", "horseshoe_left"), ("right", "horseshoe_right"), ("left", "target_ring")],
                              reason="bilateral loaded finger contact with the actual ring")
        motion.hold(1., phase="ring_grasp_hold")
        return True

    motion.events.append(dict(time_s=motion.step_count*motion.dt, ring_grasp_plan=choice, candidate_count=len(rows)))
    if getattr(motion, "instance", None) is None:
        transfer(motion, "left", choice["pre_qpos"][:6], phase="left_to_ring_pregrasp")
    else:
        from .family_routes import execute
        execute(motion, choice["pre_qpos"][:6])
    # Follow the measured free ring, including its remaining pendulum motion.
    motion.phase = "track_and_approach_ring"
    for k in range(1, 61):
        u = k/60
        p, r = tracked_ring_grasp_frame(motion, choice)
        p -= .04*(1-u)*r.apply([1, 0, 0])
        motion.kin.q = motion.q.copy()
        error = motion.kin.solve("left", p-motion.mount, r)
        if error[0] > .0005 or error[1] > .005:
            raise RuntimeError(f"Ring tracking IK failed: {error}")
        motion.joint_segment(motion.kin.q.copy(), .05)
    motion.phase = "close_ring_grasp"
    for opening in np.linspace(.037, .0098, 69)[1:]:
        p, r = tracked_ring_grasp_frame(motion, choice)
        motion.kin.q = motion.q.copy()
        error = motion.kin.solve("left", p-motion.mount, r)
        if error[0] > .0005 or error[1] > .005:
            raise RuntimeError(f"Ring closing IK failed: {error}")
        target = motion.kin.q.copy()
        target[6:8] = opening
        motion.joint_segment(target, .10)
        if attach_if_loaded():
            return choice
    # A tilted wire can rest on the edge of one pad while the other pad has
    # no load. Do not attach it in that state. Stop chasing the moving ring,
    # then search up to 6 mm along the pad depth with real joint control.
    # Every correction keeps gravity, contact and the penetration guards on.
    motion.hold(1., phase="settle_ring_grasp_contacts")
    if attach_if_loaded():
        return choice
    for correction in range(1, 7):
        p, r = motion.hand_pose("left")
        motion.cartesian({"left": (p-.001*r.apply([1, 0, 0]), r)}, .3,
                         phase="center_wire_in_pad_depth")
        motion.hold(.3, phase="confirm_ring_grasp_contacts")
        motion.events.append(dict(time_s=motion.step_count*motion.dt,
            phase="ring_grasp_depth_correction", cumulative_retraction_m=correction*.001))
        if attach_if_loaded():
            return choice
    raise RuntimeError("Ring grasp never established bilateral physical contact")
