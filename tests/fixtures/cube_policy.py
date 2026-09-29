"""Trusted test policy: only public observations, specs and low-level step calls."""
import math
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def cube_policy(interaction, *, split=False, empty_grasp=False, speed_scale=1.):
    obs = interaction.observe()
    arm = interaction.action_spec["arms"][0]
    group = interaction.action_spec["groups"][arm]
    dt = interaction.timing_spec["control_dt_s"]
    gripper_field = group["gripper_field"]
    opened, closed = group["gripper_limits"]
    setup = obs["task"]
    start = np.asarray(setup["cube_initial_position_m"])
    target = np.asarray(setup["target_position_m"])
    if empty_grasp:
        start = start + [0, -.10, 0]
    downward = np.array([0., 1., 0., 0.])
    grip = opened
    results = []
    ended = False
    interaction.begin_segment(request_id="pickup")

    def send(action):
        nonlocal obs, ended
        obs, reward, terminated, truncated, info = interaction.step(action)
        ended = terminated or truncated
        return info

    def hold(seconds):
        for _ in range(math.ceil(seconds/dt)):
            if ended:
                break
            send({})

    def move(position, *, seconds, orientation=downward):
        previous = obs["robot"][arm]
        p0 = np.asarray(previous["tcp_position_world_m"])
        q0 = np.asarray(previous["tcp_orientation_wxyz"])
        rotations = Rotation.from_quat(np.array([q0, orientation])[:, [1, 2, 3, 0]])
        slerp = Slerp([0., 1.], rotations)
        count = math.ceil(seconds/speed_scale/dt)
        for index in range(1, count+1):
            if ended:
                return
            t = index/count
            u = t*t*(3-2*t)
            send({arm: {"position_world_m": (p0+u*(np.asarray(position)-p0)).tolist(),
                        "orientation_wxyz": slerp(u).as_quat()[[3, 0, 1, 2]].tolist(),
                        gripper_field: grip}})
        # Policy-local feedback: no simulator high-level operation is involved.
        for _ in range(math.ceil(.6/dt)):
            if ended:
                return
            error = np.linalg.norm(np.asarray(obs["robot"][arm]["tcp_position_world_m"])-position)
            if error < .003:
                break
            send({})

    try:
        send({arm: {gripper_field: opened}})
        hold(.3)
        move(start+[0, 0, .14], seconds=1.5)
        move(start+[0, 0, .005], seconds=1.)
        grip = closed
        if not ended:
            send({arm: {gripper_field: grip}})
        hold(3.)
        move(start+[0, 0, .10], seconds=1.)
        hold(.25)
        if split and not ended:
            results.append(interaction.end_segment())
            interaction.begin_segment(request_id="transfer")
        move(target+[0, 0, .10], seconds=1.5)
        move(target+[0, 0, .005], seconds=1.)
        grip = opened
        if not ended:
            send({arm: {gripper_field: grip}})
        hold(2.)
        move(target+[0, 0, .12], seconds=1.)
        hold(.8)
    finally:
        results.append(interaction.end_segment())
    return results
