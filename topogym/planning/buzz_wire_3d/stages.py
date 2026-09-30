"""Buzz Wire steps for the staged workflow in topogym/planning/solvability.py.

Each step wraps an existing BuzzWirePolicy part or recipes helper and plans at
the step's actual start state (after any diagnostic rewind). Budgets are about
twice the simulated duration the same stage took in buzz_easy_dev06 and
buzz_easy_continuous_20260929_02. Passing steps are not a proof; the continuous
run still needs native success and independent audit (the historical audit tool
is archived under legacy/research_tools_20260929/scripts/).
"""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.config.registry import variation_registration
from topogym.planning.solvability import Stage, Step
from topogym.utils.io import sha256_file, write_json_atomic
from . import recipes
from .keyframes import connect_held_guide
from .kinematics import BuzzIK, CheckedJointPolicy
from .policy import BuzzWirePolicy, rotation

# Tool pose held above the easy finish post before the release, the body
# target of buzz_easy_live02 command_0001 "flatten_before_release" (prefix
# ticks 4803-5052 of the audited easy run).
EASY_FLATTEN = dict(position_m=[.095, -.305, 1.164189305912137],
                    quaternion_wxyz=[-.0588320132458664, .5359907735054749,
                                     .8413369866395914, .037480126022373994])


def hand(tick):
    return tick["world"]["grasp"]["hands"]["arm"]


def holding(tick):
    return {"holding": hand(tick)["phase"] == "holding"}


def unbound(tick):
    return {"unbound": hand(tick)["binding"] is None}


def common(tick):
    # The Task fails only on tool-wire contact; robot-wire contact is checked here.
    summary = tick["world"]["contact_events"]
    touching = [{event["role_a"], event["role_b"]} for event in summary["events"] if event["touching"]]
    result = tick["task"]["result"]
    return dict(contact_coverage=summary["substeps_complete"] is True and summary["geometry_roles_complete"] is True,
                no_tool_wire_touch={"wand_metal", "wire_metal"} not in touching,
                no_robot_wire_touch={"robot", "wire_metal"} not in touching,
                task_not_failed=not (result["terminated"] and not result["task_success"]))


def tracked(tick):
    # Losing the Task's traversal tracking mid-route cannot be recovered: it
    # only restarts within 10 mm of the wire start.
    return {"traversal_tracked": tick["task"]["result"]["metrics"]["traversal_tracked"] is True}


def acquired(tick):
    binding = hand(tick)["binding"]
    return dict(holding(tick), acquisition_evidence=bool(binding and binding["acquisition_evidence"]))


def released_supported(tick):
    return dict(unbound(tick), supported=tick["task"]["result"]["metrics"]["supported"] is True)


def solved(tick):
    return {"task_success": tick["task"]["result"]["task_success"] is True}


# Entry, exit and whether holding is checked on every tick, per stage kind.
KIND_CHECKS = dict(grasp=(unbound, acquired, False), interaction=(holding, holding, True),
                   release=(holding, released_supported, False), settle=(holding, solved, False))


def stages(env, context):
    variant = variation_registration("buzz_wire_3d", env.config.variation_id)["variation_id"]
    if variant not in {"buzz_wire_3d_easy", "buzz_wire_3d_medium"}:
        raise ValueError(f"No staged Buzz sequence is defined yet for {variant}")
    output = context.output / "planning"
    output.mkdir(exist_ok=True)

    def policy(kwargs):
        inner = BuzzWirePolicy(route=env._task.route, origin=env._task.origin, **kwargs)
        return CheckedJointPolicy(inner, env._robot) if env.config.control_mode == "JOINT_ABS" else inner

    def stage(name, kind, parameters, kwargs, entry, exit, budget_s, *, measured_s, holding_throughout=False,
              tracked_throughout=False):
        def invariant(tick):
            values = common(tick)
            if holding_throughout:
                values.update(holding(tick))
            if tracked_throughout:
                values.update(tracked(tick))
            return values
        definition = dict(parameters=parameters, measured_simulation_s=measured_s,
                          holding_throughout=holding_throughout, tracked_throughout=tracked_throughout)
        return Stage(name, kind, definition, lambda tick: policy(kwargs), entry, invariant, exit, budget_s)

    def pickup(parameters):
        start_z = env._world.read_state()["bodies"]["wand"]["position_m"][2]

        def exit(tick):
            binding = hand(tick)["binding"]
            return dict(holding(tick), acquisition_evidence=bool(binding and binding["acquisition_evidence"]),
                        lifted_20mm=tick["world"]["bodies"]["wand"]["position_m"][2]-start_z >= .02)
        # The policy lifts the grasped tool 25 mm; 20 mm leaves 5 mm tracking margin.
        return stage("pickup", "grasp", parameters, dict(part="pickup", **parameters),
                     unbound, exit, 35., measured_s=17.075)

    def regrasp(parameters):
        return stage("regrasp", "grasp", parameters, dict(part="regrasp"), holding, holding, 58.,
                     measured_s=28.85)

    def traverse(parameters):
        kin = BuzzIK(env)
        body = env._world.read_state()["bodies"]["wand"]
        p, r = np.asarray(body["position_m"]), rotation(body["quaternion_wxyz"])
        tcp = env._robot.observe()["arm"]
        offset_p = r.inv().apply(np.asarray(tcp["tcp_position_world_m"])-p)
        offset_r = r.inv()*rotation(tcp["tcp_orientation_wxyz"])
        errors = []
        for spacing, width in parameters["route_search"]:
            try:
                plan = kin.plan_route(env._task.route, env._task.origin, offset_p, offset_r,
                                      spacing=spacing, beam_width=width)
                plan = kin.refine(plan, offset_p, offset_r)
                break
            except ValueError as error:
                errors.append(dict(spacing_m=spacing, beam_width=width, error=str(error)))
        else:
            raise ValueError(f"Route candidate search exhausted: {errors}")
        write_json_atomic(output / "traverse_plan.json", dict(plan=plan, rejected_searches=errors))

        def exit(tick):
            return dict(holding(tick), traversal_tracked=tick["task"]["result"]["metrics"]["traversal_tracked"] is True)
        return stage("traverse", "interaction", parameters, dict(part="solve", plan=plan, stop_after_route=True),
                     holding, exit, 150., measured_s=74.15, holding_throughout=True, tracked_throughout=True)

    def flatten(parameters):
        rows = [dict(operation="body", seconds=5, phase="flatten_before_release", **parameters),
                dict(operation="hold", seconds=1)]

        def exit(tick):
            return dict(holding(tick), traversal_tracked=tick["task"]["result"]["metrics"]["traversal_tracked"] is True)
        return stage("flatten_above_finish", "interaction", parameters, recipes.script(rows), holding, exit, 13.,
                     measured_s=6.225, holding_throughout=True)

    def release_onto_deck(parameters):
        # The ring slides off the rail end under gravity; the Task latches the
        # full traversal only then.
        def exit(tick):
            metrics = tick["task"]["result"]["metrics"]
            return dict(unbound(tick), traversal_complete=metrics["traversal_complete"] is True,
                        supported=metrics["supported"] is True)
        return stage("release_onto_deck", "release", parameters, recipes.script(parameters["instructions"]),
                     holding, exit, parameters.get("budget_s", 19.), measured_s=parameters.get("measured_s", 9.2))

    def acquire(name, measured_s):
        def build(parameters):
            kwargs = recipes.acquire(env, output, **parameters)

            def exit(tick):
                binding = hand(tick)["binding"]
                return dict(holding(tick), acquisition_evidence=bool(binding and binding["acquisition_evidence"]))
            return stage(name, "grasp", parameters, kwargs, unbound, exit, 2*measured_s, measured_s=measured_s)
        return build

    def turn(name, measured_s):
        def build(parameters):
            kwargs = recipes.checked_turn(env, output, **parameters)
            return stage(name, "interaction", parameters, kwargs, holding, holding, 2*measured_s,
                         measured_s=measured_s, holding_throughout=True)
        return build

    def partial_release(parameters):
        def exit(tick):
            return dict(unbound(tick), supported=tick["task"]["result"]["metrics"]["supported"] is True)
        return stage("partial_release", "release", parameters, recipes.script(parameters["instructions"]),
                     holding, exit, 12., measured_s=5.6)

    def final_release(parameters):
        def exit(tick):
            return {"task_success": tick["task"]["result"]["task_success"] is True}
        # Stage plan: 0.5 + 0.2 + 1 + 5 s; the audited run succeeded after 2.1 s.
        return stage("final_release", "settle", parameters, recipes.final_release(env), holding, exit, 14.,
                     measured_s=2.1)

    def park(parameters):
        # Measured: park 9.95 s in buzz_medium_dev03 plus the short withdraw and
        # open-gripper settle, 12.825 s in buzz_medium_live02 command_0001.
        return stage("park", "release", parameters, dict(part="park"), holding, unbound, 46., measured_s=22.775)

    def acquire_for_traverse(parameters):
        # The empty-hand grasp of run_buzz_wire_policy.py's non-easy branch.
        kin = BuzzIK(env)
        body = env._world.read_state()["bodies"]["wand"]
        p, r = np.asarray(body["position_m"]), rotation(body["quaternion_wxyz"])
        layout = env._task.layout
        gr = (r*Rotation.from_euler("z", parameters["grasp_yaw"], degrees=True)
              * Rotation.from_euler("y", parameters["grasp_y"], degrees=True)*Rotation.from_euler("z", 180, degrees=True))
        gp = p+r.apply([layout.loop_radius_m+layout.stem_length_m+layout.grip_length_m*parameters["grasp_fraction"],
                        0, 0])+[0, 0, parameters["grasp_height"]]
        plan = kin.plan_free_tcp((gp-gr.apply([0, 0, parameters["approach"]]), gr))
        write_json_atomic(output / "acquire_for_traverse.json", plan)
        kwargs = dict(part="acquire", plan=plan, grasp_y=parameters["grasp_y"], grasp_yaw=parameters["grasp_yaw"],
                      grasp_fraction=parameters["grasp_fraction"], grasp_height=parameters["grasp_height"])

        def exit(tick):
            return dict(acquired(tick), **tracked(tick))
        return stage("acquire_for_traverse", "grasp", parameters, kwargs, unbound, exit, 77., measured_s=38.375)

    def traverse_keyframes(parameters):
        # Connect the measured start through recorded tool poses (the guide),
        # keeping the anchor poses as required points. Between anchors the
        # connection is tried directly and split at guide poses only on failure.
        kin = BuzzIK(env)
        tick = env.tick_record()
        body = tick["world"]["bodies"]["wand"]
        p, r = np.asarray(body["position_m"]), rotation(body["quaternion_wxyz"])
        tp, tr = kin.tcp_pose(kin.seed)
        offset_p, offset_r = r.inv().apply(tp-p), r.inv()*tr
        cursor = tick["task"]["result"]["metrics"]["route_cursor_m"]
        # Relative to the working directory: runs execute a frozen source copy
        # from the repository root, and guides are run inputs, not source.
        guide_file = Path(parameters["guide_file"])
        if sha256_file(guide_file) != parameters["guide_sha256"]:
            raise ValueError(f"Traverse guide changed: {guide_file}")
        document = json.loads(guide_file.read_text())
        rows = [row for row in document["guide"] if row["route_cursor_m"] > cursor+parameters["guide_skip_m"]]
        anchors = set(parameters.get("anchor_labels") or document.get("offline_anchor_labels", ()))
        start = dict(label="measured_start", position_m=p.tolist(), quaternion_wxyz=list(body["quaternion_wxyz"]))
        result = connect_held_guide(kin, [start, *rows], offset_p, offset_r,
                                    mandatory_indices=[i+1 for i, row in enumerate(rows) if row["label"] in anchors],
                                    minimum_clearance=parameters["minimum_clearance_m"],
                                    joint_speed=parameters["speeds"][0], translation_speed=parameters["speeds"][1],
                                    rotation_speed=parameters["speeds"][2])
        write_json_atomic(output / "traverse_keyframes.json", result)
        kwargs = dict(part="joint_reference", plan=result["refs"], progress_error_m=parameters["tracking_m"][0],
                      arrival_error_m=parameters["tracking_m"][1])
        chosen = dict(parameters, anchor_labels=[row["label"] for row in result["keyframes"][1:]])
        duration = result["refs"][-1]["time_s"]

        def exit(tick):
            return dict(holding(tick), **tracked(tick))
        return stage("traverse", "interaction", chosen, kwargs, holding, exit, max(60., 2*duration),
                     measured_s=duration, holding_throughout=True, tracked_throughout=True)

    def develop(name):
        # Terminal steps are developed live: parameters name an action and a kind.
        def build(parameters):
            action = parameters["action"]
            if action == "script":
                kwargs = recipes.script(parameters["instructions"])
            elif action == "acquire":
                kwargs = recipes.acquire(env, output, **parameters["args"])
            elif action == "turn":
                kwargs = recipes.checked_turn(env, output, **parameters["args"])
            elif action == "final_release":
                kwargs = recipes.final_release(env)
            else:
                raise ValueError(f"Unknown development action: {action}")
            entry, exit, throughout = KIND_CHECKS[parameters["kind"]]
            return stage(name, parameters["kind"], parameters, kwargs, entry, exit, parameters["budget_s"],
                         measured_s=None, holding_throughout=throughout)
        return build

    if variant == "buzz_wire_3d_medium":
        yield Step("pickup", ({"grasp_height": .012, "grasp_tilt": 75.},), pickup)
        yield Step("park", ({},), park)
        yield Step("acquire_for_traverse", (dict(grasp_yaw=0., grasp_y=255., grasp_fraction=.4, grasp_height=.012,
                                                 approach=.04),), acquire_for_traverse)
        # The progress gate measures lag behind the time-indexed reference, not
        # distance from the path: at 0.5 mm the reference advanced at ~0.3x
        # real time while the off-path error stayed below 0.27 mm (run _01).
        guide = dict(guide_file="runs/test_results/buzz_staged_inputs_20260929/medium_traverse_guide.json",
                     guide_sha256="4511df68f53ded79077a12998ddfe76f1cbf65f6ac552b412fbdefa4bf16cd0f",
                     guide_skip_m=.002, minimum_clearance_m=.0007, tracking_m=[.0015, .0008])
        yield Step("traverse", (dict(guide, speeds=[.25, .012, .35]), dict(guide, speeds=[.12, .006, .2])),
                   traverse_keyframes)
        # buzz_medium_continuous_20260929_01 command_0002: open, back off, settle.
        yield Step("release_onto_deck", ({"instructions": [
            dict(operation="tcp", local_translation_m=[0, 0, -.04], seconds=.2, gripper_position_rad=0.),
            dict(operation="hold", seconds=3.), dict(operation="grip", value=.65, seconds=2.),
            dict(operation="settle_gripper")], "budget_s": 29., "measured_s": 14.225},), release_onto_deck)
        index = 1
        while True:
            yield Step(f"terminal_{index}", (), develop(f"terminal_{index}"))
            index += 1

    yield Step("pickup", ({"grasp_height": .012, "grasp_tilt": 75.},), pickup)
    yield Step("regrasp", ({},), regrasp)
    yield Step("traverse", ({"route_search": [[.008, 4], [.004, 12], [.002, 24]]},), traverse)
    yield Step("flatten_above_finish", (EASY_FLATTEN,), flatten)
    yield Step("release_onto_deck", ({"instructions": recipes.RELEASE_ONTO_DECK},), release_onto_deck)
    yield Step("acquire_1", (dict(index=1, yaw=225., tilt=45., advance=0., approach=.04),),
               acquire("acquire_1", 24.2))
    yield Step("turn_1", (recipes.TURN_1,), turn("turn_1", 10.85))
    yield Step("partial_release", ({"instructions": recipes.PARTIAL_RELEASE},), partial_release)
    yield Step("acquire_2", (recipes.ACQUIRE_2,), acquire("acquire_2", 24.))
    yield Step("turn_2", (recipes.TURN_2,), turn("turn_2", 9.3))
    yield Step("final_release", ({},), final_release)
