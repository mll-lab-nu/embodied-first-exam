"""Measured-state planning for the approved very_easy and easier layouts.

These owner-side helpers generate ordinary robot actions. They do not set body
poses, alter the task, or infer physical success from a collision query.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.utils.io import write_json_atomic
from .kinematics import BuzzIK, CheckedJointPolicy
from .policy import BuzzWirePolicy
from .recipes import measured_grasp
from . import recipes
from topogym.assets.geometry.buzz_wire_3d import endpoint_pose


def terminal_grasp(env, output, *, yaw=225., tilt=45., height=.014,
                   advance=0., approach=.04, lift=.005, adaptive=False):
    """Plan the complete open-hand approach using its measured passive joints."""
    kin = BuzzIK(env)
    p, r, _, _ = measured_grasp(env, kin)
    gr = (r * Rotation.from_euler("z", yaw, degrees=True)
          * Rotation.from_euler("y", tilt, degrees=True)
          * Rotation.from_euler("z", 180., degrees=True))
    gp = p+r.apply([.048, 0., 0.])+[0., 0., height]+gr.apply([0., 0., advance])
    path = kin.plan_free_tcp((gp-gr.apply([0., 0., approach]), gr))
    seed = np.asarray(path[-1]["qpos"])
    gaps = []
    for u in np.linspace(0., 1., max(2, int(np.ceil(approach/.0004)))+1):
        seed = kin.solve((gp-gr.apply([0., 0., approach*(1-u)]), gr), seed)
        gaps.append(kin.clearance(seed))
        if gaps[-1] < .001:
            raise ValueError("Terminal grasp approach has insufficient sampled clearance")
    layout = env._task.layout
    parameters = dict(part="acquire", plan=path, grasp_y=tilt, grasp_yaw=yaw,
        grasp_roll=180., grasp_fraction=(.048-layout.loop_radius_m-layout.stem_length_m)/layout.grip_length_m,
        grasp_height=height, grasp_advance=advance, lift_height=lift,
        close_on_contact=adaptive, settle_timeout_s=45.)
    write_json_atomic(output/"terminal_grasp_plan.json", dict(parameters=parameters,
        minimum_approach_clearance_m=min(gaps), scope="read-only sampled path; requires physical trial"))
    return parameters


def make_stage_policy(env, parameters):
    return CheckedJointPolicy(BuzzWirePolicy(route=env._task.route,
        origin=env._task.origin, **parameters), env._robot)


class SimplifiedBuzzOracle:
    """Owner-side oracle; each stage is planned at its real measured start.

    The caller executes the yielded policy parameters with SegmentRunner and
    stops on native Task success. No previous run or saved simulator state is
    needed. The optional starting stage is for explicitly marked calibration.
    """
    def __init__(self, env, output, *, variant, regrasp=True,
                 finish_mode="low_slide_regrasp", terminal_contact_close=False):
        if variant not in {"very_easy", "easier"}:
            raise ValueError("Expected an approved simplified Buzz Wire variant")
        if env._task.variation_id != "buzz_wire_3d_"+variant:
            raise ValueError("Oracle variant does not match the active task")
        self.env, self.output, self.variant = env, output, variant
        self.regrasp, self.finish_mode = regrasp, finish_mode
        self.terminal_contact_close = terminal_contact_close

    def _kinematics(self, iterations=300):
        kin = BuzzIK(self.env)
        def solve(tcp, seed):
            p, r = tcp
            return kin.ik.solve_checked(link_name=kin.group.hand_link,
                position_world_m=p-r.apply(kin.group.tcp_position_in_hand_m),
                orientation_wxyz=r.as_quat()[[3, 0, 1, 2]],
                joint_dof_indices=kin.indices, initial_qpos=seed,
                max_solver_iterations=iterations)
        kin.solve = solve
        return kin

    def _route(self):
        env, output = self.env, self.output
        kin = BuzzIK(env)
        p, r, op, ore = measured_grasp(env, kin)
        plan = kin.plan_route(env._task.route, env._task.origin, op, ore,
            spacing=.006, beam_width=8, curve_positions=True,
            initial_orientation_wxyz=r.as_quat()[[3, 0, 1, 2]],
            progress=lambda row: write_json_atomic(output/"planning_progress.json", row))
        plan = kin.refine(plan, op, ore)
        first = plan[0]
        target = (np.asarray(first["position_m"]), Rotation.from_quat(
            np.asarray(first["quaternion_wxyz"])[[1, 2, 3, 0]]))
        entry = kin.plan_held_waypoints([target], op, ore)
        write_json_atomic(output/"route_ik.json", plan)
        entry_refs, route_refs = kin.joint_references(entry, op, ore), kin.joint_references(plan, op, ore)
        write_json_atomic(output/"entry_references.json", entry_refs)
        write_json_atomic(output/"route_references.json", route_refs)
        return entry_refs, route_refs

    def _prepare_release(self):
        kin = self._kinematics()
        p, r, op, ore = measured_grasp(self.env, kin)
        flat = r*Rotation.from_euler("x", 160.-r.as_euler("xyz", degrees=True)[0], degrees=True)
        high = p+[0., 0., .025]
        frames = kin.plan_held_waypoints([(high, r), (high, flat)], op, ore,
            minimum_clearance=.0005, allow_wand_support=True)
        refs = kin.joint_references(frames, op, ore, translation_speed=.006,
            rotation_speed=.15, allow_wand_support=True)
        write_json_atomic(self.output/"finish_slide_references.json", refs)
        return dict(part="joint_reference", plan=refs, arrival_error_m=.0008)

    def _lower(self):
        kin = self._kinematics(1200)
        p, r, op, ore = measured_grasp(self.env, kin)
        back, tilt = (5., 40.) if self.variant == "very_easy" else (10., 25.)
        intermediate = r*Rotation.from_euler("x", -back, degrees=True)
        seated = intermediate*Rotation.from_euler("y", tilt, degrees=True)
        end_p, _ = endpoint_pose(self.env._task.route, 1)
        target = end_p+self.env._task.origin+[0., 0., .015]
        frames = kin.plan_held_waypoints([(p, intermediate), (p, seated), (target, seated)],
            op, ore, minimum_clearance=.001, allow_wand_support=True)
        refs = kin.joint_references(frames, op, ore, translation_speed=.003,
            rotation_speed=.12, allow_wand_support=True)
        write_json_atomic(self.output/"finish_low_references.json", refs)
        return dict(part="joint_reference", plan=refs, progress_error_m=.0008, arrival_error_m=.0006)

    def _terminal_departure(self, delta, *, settle):
        """Check a slow departure from the narrow measured post-grasp gap."""
        kin = BuzzIK(self.env)
        p, r, op, ore = measured_grasp(self.env, kin)
        frames = kin.plan_held_waypoints([(p+delta, r)], op, ore,
            minimum_clearance=.0003, maximum_material_step=.0003, allow_wand_support=True)
        write_json_atomic(self.output/("terminal_raise.json" if settle else "terminal_center.json"),
            dict(frames=frames, minimum_sampled_gap_m=min(f.get("clearance_m", 1.) for f in frames)))
        return recipes.script([dict(operation="body", translation_m=delta, seconds=3.),
            dict(operation="settle_gripper") if settle else dict(operation="hold", seconds=.5)])

    def _finish_stages(self):
        yield recipes.script(recipes.RELEASE_ONTO_DECK)
        if self.variant == "easier":
            # Calibrated with real bilateral contact. Recenter before lifting:
            # a vertical move does not clear an off-centre ring from the post.
            yield terminal_grasp(self.env, self.output, yaw=223.625)
            yield self._terminal_departure([.003, -.003, 0.], settle=False)
            yield self._terminal_departure([0., 0., .004], settle=True)
        else:
            yield recipes.acquire(self.env, self.output, 1, 225., 45., 0., .04)
        turn = dict(recipes.TURN_1)
        if self.variant == "easier":
            turn["final_height"] = .003
            turn["speeds"] = (.05, .003, .1, .0015)
        else:
            # The oracle's own planning margin, not a Task rule (the Task fails only on wand-wire contact). Under Harbor's
            # 2.5 ms x 10 physics every turn from the measured very_easy grasp keeps at most 1.4735 mm (lab 2026-10-06:
            # TURN_1's candidates, 41 yaws, 210 xy offsets), so the 1.5 mm margin admitted none.
            turn["minimum_clearance"] = .0014
        yield recipes.checked_turn(self.env, self.output, **turn)
        yield recipes.script(recipes.PARTIAL_RELEASE)
        yield recipes.acquire(self.env, self.output, **recipes.ACQUIRE_2)
        yield recipes.checked_turn(self.env, self.output, **recipes.TURN_2)
        yield recipes.final_release(self.env)

    def stages(self, *, start="home", part="solve"):
        if start not in {"home", "traversed", "prepared", "released"}:
            raise ValueError("Unknown measured starting stage")
        if start == "home":
            yield "pickup", dict(part="pickup")
            if part == "pickup":
                return
            if self.regrasp:
                yield "regrasp", dict(part="regrasp", settle_timeout_s=45.)
            yield "settle_gripper", recipes.script([
                dict(operation="settle_gripper", phase="measure_settled_grasp")])
            entry, route = self._route()
            if part == "plan":
                return
            yield "entry", dict(part="joint_reference", plan=entry, arrival_error_m=.001)
            yield "traverse", dict(part="joint_reference", plan=route, arrival_error_m=.001)
        mode = self.finish_mode
        if mode in {"slide_regrasp", "low_slide_regrasp"} and start not in {"prepared", "released"}:
            yield "prepare_finish_slide", self._prepare_release()
        if mode == "low_slide_regrasp" and start != "released":
            yield "lower_for_release", self._lower()
        if mode in {"release_regrasp", "slide_regrasp", "low_slide_regrasp"}:
            for index, parameters in enumerate(self._finish_stages()):
                if index == 0 and start == "released":
                    continue
                if index == 0 and mode != "release_regrasp":
                    parameters = recipes.script([
                        dict(operation="hold", seconds=1., phase="settle_before_release"),
                        dict(operation="grip", value=0., seconds=.5, phase="open_before_withdraw"),
                        dict(operation="tcp", local_translation_m=[0., 0., -.1], seconds=1., phase="withdraw_after_release"),
                        dict(operation="hold", seconds=2.), dict(operation="settle_gripper")])
                if index == 1 and self.terminal_contact_close:
                    parameters = dict(parameters, close_on_contact=True)
                yield f"finish_recipe_{index}", parameters
            return
        # Retained as an explicit diagnostic: this branch was not qualified.
        kin = self._kinematics()
        p, r, op, ore = measured_grasp(self.env, kin)
        end_p, end_r = endpoint_pose(self.env._task.route, 1)
        end_p = end_p+self.env._task.origin+[0., 0., .0004]
        choices = [end_r, end_r*Rotation.from_euler("x", 180., degrees=True)]
        choices.sort(key=lambda candidate: (candidate*r.inv()).magnitude())
        errors = []
        for candidate in choices:
            try:
                frames = kin.plan_held_waypoints([(p, candidate), (end_p, candidate)], op, ore,
                    allow_wand_support=True, minimum_clearance=.0005)
                refs = kin.joint_references(frames, op, ore, allow_wand_support=True,
                    translation_speed=.006, rotation_speed=.2)
                break
            except ValueError as error:
                errors.append(str(error))
        else:
            raise ValueError(f"No collision-checked direct finish: {errors}")
        yield "finish", dict(part="joint_reference", plan=refs, arrival_error_m=.001)
        yield "release_and_settle", recipes.script([
            dict(operation="grip", value=0., seconds=1., phase="release_on_deck"),
            dict(operation="tcp", translation_m=[0., 0., .12], seconds=2., phase="withdraw_up"),
            dict(operation="hold", seconds=5., phase="final_settle")])
