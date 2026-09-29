"""Owner-side sequencing of observation policies for frozen Buzz instances."""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.buzz_wire_3d import endpoint_pose
from topogym.utils.io import write_json_atomic
from .kinematics import BuzzIK
from .policy import rotation


# Read-only collision envelope measured with the driver at 0.45 rad in
# buzz_easy_live02/command_0029_tick.json. These values are never sent as actions
# or written to a robot; the current measured geometry is checked as well.
_EASY_OPEN_PASSIVE_SAMPLE = {
    "finger_joint1": .449990777437435,
    "r85_right_coupler_joint": -.4680024151124936,
    "r85_right_spring_link_joint": .0037343694218083543,
    "r85_right_follower_joint": .7372125291888691,
    "finger_joint2": .44999077143629956,
    "r85_left_coupler_joint": -.4580272161413141,
    "r85_left_spring_link_joint": .01874026839851632,
    "r85_left_follower_joint": .6951461874753759,
}


def script(rows):
    return dict(part="script", instructions=rows, settle_timeout_s=45.)


def measured_grasp(env, kin):
    body = env._world.read_state()["bodies"]["wand"]
    p, r = np.asarray(body["position_m"]), rotation(body["quaternion_wxyz"])
    tp, tr = kin.tcp_pose(kin.seed)
    return p, r, r.inv().apply(tp-p), r.inv()*tr


def acquire(env, output, index, yaw, tilt, advance, approach, adaptive=False):
    layout = env._task.layout
    fraction = (.048-layout.loop_radius_m-layout.stem_length_m)/layout.grip_length_m
    kin = BuzzIK(env)
    p, r, _, _ = measured_grasp(env, kin)
    gr = r*Rotation.from_euler("z", yaw, degrees=True)*Rotation.from_euler(
        "y", tilt, degrees=True)*Rotation.from_euler("z", 180., degrees=True)
    gp = p+r.apply([.048, 0., 0.])+[0., 0., .014]+gr.apply([0., 0., advance])
    original_clearance = kin.clearance
    envelope = [kin.seed[7:].copy()]
    if adaptive:
        sample = kin.seed.copy()
        for name, value in _EASY_OPEN_PASSIVE_SAMPLE.items():
            sample[kin.robot.entity.get_joint(name).qs_idx_local] = value
        envelope.append(sample[7:].copy())

    def clearance(q, body=None, **kwargs):
        return min(original_clearance(np.r_[q[:7], passive], body, **kwargs)
                   for passive in envelope)

    kin.clearance = clearance
    try:
        path = kin.plan_free_tcp((gp-gr.apply([0., 0., approach]), gr))
        seed = np.asarray(path[-1]["qpos"])
        for u in np.linspace(0., 1., max(2, int(np.ceil(approach/.0004))+1)):
            seed = kin.solve((gp-gr.apply([0., 0., approach*(1-u)]), gr), seed)
            if kin.clearance(seed) < .001:
                raise ValueError("Selected free-hand path fails the final grasp approach")
    finally:
        kin.clearance = original_clearance
    write_json_atomic(output/f"finish_transfer_{index}.json",
                      dict(plan=path, passive_envelope=[v.tolist() for v in envelope]))
    return dict(part="acquire", plan=path, grasp_y=tilt, grasp_yaw=yaw,
                grasp_roll=180., grasp_fraction=fraction, grasp_height=.014,
                grasp_advance=advance, lift_height=.005, close_on_contact=adaptive,
                settle_timeout_s=45.)


def checked_turn(env, output, index, yaws, offsets, final_height, minimum_clearance, speeds, errors):
    end_p, end_r = endpoint_pose(env._task.route, 1)
    end_p = end_p + env._task.origin
    pitch = float(np.arcsin(end_r.apply([1, 0, 0])[2]))
    kin = BuzzIK(env)
    _, _, offset_p, offset_r = measured_grasp(env, kin)
    initial = kin.seed.copy()
    for yaw in yaws:
        r = Rotation.from_euler("z", yaw, degrees=True)*Rotation.from_euler(
            "y", -pitch)*Rotation.from_euler("x", 180., degrees=True)
        for x, y in offsets:
            kin.seed = initial.copy()
            try:
                frames = kin.plan_held_waypoints(
                    [(end_p+[x, y, .005], r), (end_p+[x, y, final_height], r)],
                    offset_p, offset_r, allow_wand_support=True,
                    minimum_clearance=minimum_clearance, maximum_material_step=.0004)
                refs = kin.joint_references(frames, offset_p, offset_r,
                    joint_speed=speeds[0], translation_speed=speeds[1],
                    rotation_speed=speeds[2], maximum_joint_step=speeds[3],
                    allow_wand_support=True)
            except ValueError:
                continue
            write_json_atomic(output/f"finish_turn_{index}.json",
                              dict(yaw=yaw, xy=[x, y], refs=refs))
            return dict(part="joint_reference", plan=refs,
                        progress_error_m=errors[0], arrival_error_m=errors[1])
    raise ValueError("No collision-checked terminal turn from the measured grasp")


RELEASE_ONTO_DECK = [dict(operation="tcp", local_translation_m=[0., 0., -.1], seconds=.2, gripper_position_rad=0.),
                     dict(operation="hold", seconds=2.), dict(operation="settle_gripper")]
PARTIAL_RELEASE = [dict(operation="hold", seconds=.5), dict(operation="grip", value=.78, seconds=.75),
                   dict(operation="tcp", local_translation_m=[0., 0., -.08], seconds=1.),
                   dict(operation="hold", seconds=1.), dict(operation="grip", value=.45, seconds=2.)]
TURN_1 = dict(index=1, yaws=[145., 144.5, 144., 143.5, 143.], offsets=[(.003, .002)], final_height=0.,
              minimum_clearance=.0015, speeds=(.08, .004, .12, .002), errors=(.0008, .001))
# At 0.45 rad passive followers can oscillate without satisfying the strict
# settle gate. Check their measured/sample envelope instead of closing past
# the empirically useful contact window (approximately 0.47 rad).
ACQUIRE_2 = dict(index=2, yaw=265., tilt=75., advance=.012, approach=.022, adaptive=True)
TURN_2 = dict(index=2, yaws=[164., 163., 161.5], offsets=[(.003, .002), (.002, .002), (0., .003)],
              final_height=.003, minimum_clearance=.001, speeds=(.06, .003, .1, .0015), errors=(.0006, .0008))


def final_release(env):
    hand = env._world.read_state()["grasp"]["hands"]["arm"]
    release = min(.45, .8*hand["last_fraction"]-.008)
    return script([dict(operation="hold", seconds=.5),
                   dict(operation="grip", value=release, seconds=.2),
                   dict(operation="tcp", local_translation_m=[0., 0., -.08], seconds=1.),
                   dict(operation="hold", seconds=5.)])


def easy_finish_stages(env, output):
    """Replan the audited easy execution's terminal stages from observations.

    Start held above the finish post after tick 5052. The separately frozen
    submissions in buzz_easy_continuous_20260929_02 passed the native Task and
    independent audit. This consolidated generator is derived from those
    submissions; its future executions still require their own full audit.
    """
    yield script(RELEASE_ONTO_DECK)
    yield acquire(env, output, 1, 225., 45., 0., .04)
    yield checked_turn(env, output, **TURN_1)
    yield script(PARTIAL_RELEASE)
    yield acquire(env, output, **ACQUIRE_2)
    yield checked_turn(env, output, **TURN_2)
    yield final_release(env)
