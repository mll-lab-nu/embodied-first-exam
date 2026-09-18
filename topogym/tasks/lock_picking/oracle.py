"""Measured-state reindex oracle. All movement is ordinary arm IK + contacts."""

import numpy as np
from scipy.spatial.transform import Rotation
from topogym.primitives.attachment import slerp
from topogym.tasks.lock_picking.planner import insertion_window
from topogym.tasks.lock_picking.certificate import certificate


def execute_reindex(task, controller, move, status, decisions):
    g = task.layout
    cfg = task.cfg
    proof = certificate(g, cfg.rotor_stops)
    if (
        proof["minimum_required_decoupling_retreats"] != 2
        or not proof["unique_shortest_branch_sequence"]
    ):
        raise RuntimeError(
            f"Variant does not have the expected branch certificate: {proof}"
        )
    route = proof["shortest_branch_sequences"][0]
    margin = g.slot_half_deg - g.tab_half_deg
    low, high = map(float, cfg.rotor_stops[0].bounds_deg)

    def command(label, depth, angle, steps=None):
        status["phase"] = label
        before = task.state()
        target_r = Rotation.from_euler("x", -angle, degrees=True)
        target_pos = np.array([g.tip_x(depth), g.center_y, g.axis_z])
        start_pos = np.asarray(before["key_tip_pos"])
        start_q = np.asarray(before["key_quat"])
        target_q = target_r.as_quat()[[3, 0, 1, 2]]
        count = max(1, int(cfg.motion.move_steps if steps is None else steps) // 5)
        # Servo the observed key pose through arm IK. Updating the measured
        # hand/key transform compensates load-dependent weld compliance; no
        # rigid-body poses or disc angles are overwritten.
        for index in range(1, count + 25):
            f = min(1.0, index / count)
            desired_pos = start_pos + f * (target_pos - start_pos)
            desired_r = Rotation.from_quat(slerp(start_q, target_q, f)[[1, 2, 3, 0]])
            current = task.state()
            current_r = Rotation.from_quat(
                np.asarray(current["key_quat"])[[1, 2, 3, 0]]
            )
            correction = desired_r * current_r.inv()
            hand_pos = desired_pos + correction.apply(
                controller.hand_pos() - np.asarray(current["key_tip_pos"])
            )
            hand_r = correction * Rotation.from_quat(
                controller.hand_quat()[[1, 2, 3, 0]]
            )
            controller.move_ee_to(
                hand_pos,
                quat=hand_r.as_quat()[[3, 0, 1, 2]],
                continuous_ik=True,
                steps=5,
            )
        after = task.state()
        decisions.append(
            dict(
                phase=label,
                before=before,
                after=after,
                target_depth=depth,
                target_angle=angle,
            )
        )
        print(f"{label}: {after}", flush=True)
        if abs(after["depth"] - depth) > 0.035:
            raise RuntimeError(f"{label}: insertion depth tracking failed")

    def common(level):
        angle, clearance = insertion_window(g, task.state(), level, safety_deg=0.6)
        return angle

    angle = task.state()["disc_deg"][1] + g.slots[1][0]
    command("first_entry_direction", 0.0, angle, int(cfg.motion.turn_steps))
    command("enter_first_layer", 1.0, angle)
    command("enter_second_layer", 2.0, common(1))
    for cycle, branch in enumerate(route[:-1], 1):
        slot = g.slots[0][branch]
        # Stay 1 degree inside the visible end stop. Angular backlash must be
        # taken up before the rotor itself reaches this angle.
        command(
            f"coupled_prepare_{cycle}",
            2.0,
            slot + high - 1.0 + margin,
            int(cfg.motion.turn_steps),
        )
        angle = common(1)
        command(f"unload_before_retreat_{cycle}", 2.0, angle, 100)
        command(f"retreat_{cycle}_to_first", 1.0, angle)
        command(
            f"reset_first_rotor_{cycle}",
            1.0,
            slot + low + 1.0 - margin,
            int(cfg.motion.turn_steps),
        )
        angle = task.state()["disc_deg"][0] + slot
        command(f"unload_first_rotor_{cycle}", 1.0, angle, 100)
        # This axial gap is genuinely free: do not invent an engagement latch
        # or a hidden ban on turning here. Reindex before the next insertion.
        command(f"advance_to_free_gap_{cycle}", 1.50, angle)
        next_slot = g.slots[0][route[cycle]]
        state = task.state()
        target = (
            state["disc_deg"][0] + next_slot + state["disc_deg"][1] + g.slots[1][0]
        ) / 2
        command(f"change_entry_slot_{cycle}", 1.50, target, int(cfg.motion.turn_steps))
        command(f"reenter_second_layer_{cycle}", 2.0, common(1))

    third = task.state()["disc_deg"][2] + g.slots[2][0]
    command("align_third_layer", 2.0, third, int(cfg.motion.turn_steps))
    angle = common(2)
    command("center_third_entry", 2.0, angle, 100)
    command("enter_third_layer", 3.0, angle)
    angle = common(3)
    command("center_goal_entry", 3.0, angle, 100)
    command("insert_fixed_goal", 4.0, angle)
    status["required_retreats"] = 2
