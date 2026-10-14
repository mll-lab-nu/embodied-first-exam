"""Small contact/geometry measurements shared by the continuous tasks."""

import numpy as np
from panda_dynamics.props.primitives import body, position, velocity


def supported(env, name, receiver, max_gap=0.025):
    key = f"support:{name}:{receiver}"
    if env.contact(name, receiver) > 1e-8:
        env.events.flags[key] = env.time
    return env.time - env.events.flags.get(key, -10) <= max_gap


def containment(env, name, receiver, half, height, radius=0.018, speed=0.09):
    obj = env.objects[name]
    rb = body(receiver)
    local = (rb.entity_pose.inv() * body(obj).entity_pose).p
    com = (
        (rb.entity_pose * rb.cmass_local_pose).p
        if hasattr(rb, "cmass_local_pose")
        else rb.entity_pose.p
    )
    offset = position(obj) - com
    relative = (
        velocity(obj)
        - getattr(rb, "linear_velocity", np.zeros(3))
        - np.cross(getattr(rb, "angular_velocity", np.zeros(3)), offset)
    )
    receiver_name = env.contact_labels.get(rb, rb.entity.name.removeprefix("scene-0_"))
    return (
        max(abs(local[:2])) < half - radius * 0.45
        and radius - 0.004 < local[2] < height - radius * 0.12
        and supported(env, name, receiver_name)
        and np.linalg.norm(relative) < speed
    )


def cup_catch(env, name, uid, key, hold=0.18):
    arm = env.arms[uid]
    half = env.params.get(
        arm.role + "_tool_half", env.params.get("tool_half", arm.setup.half)
    )
    height = env.params.get(
        arm.role + "_tool_height", env.params.get("tool_height", 0.055)
    )
    radius = env.params.get("radius", 0.018)
    local = (arm.tool_pose.inv() * body(env.objects[name]).entity_pose).p
    flags = env.events.flags
    previous = np.asarray(flags.get(key + ":previous", local))
    in_contact = any(name in pair for pair in env.contacts)
    if not in_contact:
        flags.setdefault(key + ":flight", env.time)
    flight = env.time - flags.get(key + ":flight", env.time)
    if (
        previous[2] > height + radius >= local[2]
        and max(abs(local[:2])) < half - radius
        and flight >= 0.025
    ):
        env.events.once(
            key + ":entry",
            env.time,
            object=name,
            arm=uid,
            speed=float(np.linalg.norm(velocity(env.objects[name]))),
        )
    if in_contact:
        flags.pop(key + ":flight", None)
    flags[key + ":previous"] = local.tolist()
    retained = containment(env, name, arm.tool, half, height, radius)
    return env.events.hold(
        key + ":retained", env.events.has(key + ":entry") and retained, env.time, hold
    )


def ball_on_plate(env, name, uid="panda-0", margin=0.025):
    arm = env.arms[uid]
    radius = env.params.get("radius", 0.018)
    local = (arm.tool_pose.inv() * body(env.objects[name]).entity_pose).p
    half = env.params.get("tool_half", arm.setup.half)
    return (
        max(abs(local[:2])) < half - margin
        and radius - 0.004 < local[2] < radius + 0.015
        and supported(env, name, arm.contact_name)
    )


def bilateral_grip(env, name, uid="panda-0"):
    arm = env.arms[uid]
    prefix = "" if len(env.arms) == 1 else arm.role + "/"
    return all(
        sum(
            env.contact(name, prefix + "panda_" + side + suffix)
            for suffix in ("finger", "finger_pad")
        )
        > 1e-7
        for side in ("left", "right")
    )


def crossed(env, name, point, axis=0, direction=1, half=0.055):
    p = position(env.objects[name])
    previous = env.previous_positions[name]
    other_axis = 1 if axis == 0 else 0
    return (
        direction * (previous[axis] - point[axis])
        <= 0
        < direction * (p[axis] - point[axis])
        and abs(p[other_axis] - point[other_axis]) < half
    )


def free_interval(env, name, key):
    if any(name in pair for pair in env.contacts):
        env.events.flags.pop(key, None)
        return 0.0
    env.events.flags.setdefault(key, env.time)
    return env.time - env.events.flags[key]


def face_up(env, name, local_axis, tolerance=0.18):
    matrix = body(env.objects[name]).entity_pose.to_transformation_matrix()[:3, :3]
    return float(np.dot(matrix @ np.asarray(local_axis), [0, 0, 1])) > np.cos(tolerance)


def inertial_flip(env, name, tool, key, target_axis, balance_axis=(0, 0, 1)):
    rb = body(env.objects[name])
    matrix = rb.entity_pose.to_transformation_matrix()[:3, :3]
    angle = float(np.arccos(np.clip((matrix @ np.asarray(balance_axis))[2], -1, 1)))
    flags = env.events.flags
    touching = env.contact(name, tool) > 0
    if (
        touching
        and env.events.has(key + ":early_release")
        and not env.events.has(key + ":inertial_crossing")
    ):
        env.events.fail("flip_recontact_before_balance", env.time)
    previous_angle = flags.get(key + ":previous_angle", angle)
    flags[key + ":previous_angle"] = angle
    if touching:
        flags[key + ":had_contact"] = True
        flags[key + ":release_angle"] = angle
        flags[key + ":last_contact"] = env.time
    if (
        flags.get(key + ":had_contact")
        and not touching
        and env.time - flags[key + ":last_contact"] > 0.02
    ):
        released = flags.get(key + ":release_angle", 10)
        if (
            0.03 < released < np.pi / 4 - 0.02
            and np.linalg.norm(rb.angular_velocity) > 0.4
        ):
            env.events.once(
                key + ":early_release",
                env.time,
                angle=released,
                angular_speed=float(np.linalg.norm(rb.angular_velocity)),
            )
        if previous_angle <= np.pi / 4 < angle and env.events.has(
            key + ":early_release"
        ):
            env.events.once(key + ":inertial_crossing", env.time)
    return (
        env.events.has(key + ":inertial_crossing")
        and face_up(env, name, target_axis)
        and np.linalg.norm(velocity(env.objects[name])) < 0.05
        and np.linalg.norm(rb.angular_velocity) < 0.3
    )
