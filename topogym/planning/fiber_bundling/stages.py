"""Fiber Bundling steps for the staged workflow in topogym/planning/solvability.py.

Quick solvability assessment, not a proof: pick up the sheath (contact weld),
comb every strand against the ring's outer surface until all stations lie
within COMB_TARGET_M of the sheath axis, verify, then feed along the ring axis
until the native Task succeeds. Each step plans read-only at its actual start
state; every tick checks contact coverage and that the Task has not failed
(a gripper-strand touch fails it at once). plan_* are shared with the
zero-physics check scripts/check_fiber_keyframes.py.
"""
import numpy as np

from topogym.planning.solvability import Stage, Step
from topogym.planning.buzz_wire_3d.keyframes import connect_held_guide
from topogym.planning.buzz_wire_3d.kinematics import CheckedJointPolicy
from topogym.utils.io import write_json_atomic
from .keyframes import (GRASP_LINK, comb_keyframes, current_roll_deg, feed_keyframes, front_offsets, grasp_tcp,
                        link_pose, ring_frame, roll_choices, strand_measures)
from .kinematics import FiberIK
from .policy import FiberPolicy

# 12.179 mm is the Task's entry radius for a strand station (13.479 hole radius,
# 1.2 fiber radius, 0.1 margin); 0.68 mm is left for sheath centring while feeding.
COMB_TARGET_M = .0115
MAXIMUM_BEND_DEG = 60.
CLEARANCE_M = .001
SPEEDS = dict(joint_speed=.25, translation_speed=.015, rotation_speed=.35)
PICKUPS = tuple(dict(tilt_deg=t, approach_m=.1) for t in (30., 40.))
# Tip distance after the slide was measured as about d_press - 21.6 mm
# (easy_01 comb_01), so these aim at 10.4 / 9.4 / 8.4 mm. The 4 mm approach
# margin is a fallback for strands fanning straight up, whose large roll brings
# the gripper base near a cradle side wall.
COMBS = tuple(dict(d_press_m=d, roll_rank=k, approach_margin_m=m, tip_past_ring_m=.004)
              for m in (.008, .004) for d in (.032, .031, .030) for k in (0, 1))
FEED = dict(front_s_m=.03, maximum_front_offset_m=.0003, hold_s=1.5)


def connect(kin, guide, offset_p, offset_r):
    """Every key pose is required; an edge that fails is not replaced by a search."""
    return connect_held_guide(kin, guide, offset_p, offset_r, mandatory_indices=list(range(1, len(guide)-1)),
                              minimum_clearance=CLEARANCE_M, **SPEEDS)


def measured_offset(kin, state):
    p, r = link_pose(state, GRASP_LINK)
    tp, tr = kin.tcp_pose(kin.seed)
    return r.inv().apply(tp-p), r.inv()*tr


def plan_pickup(env, kin, state, tilt_deg, approach_m):
    """Open-hand path to approach_m behind the grasp along the tool axis, then a
    straight descent checked every millimetre (gripper-strand margin included)."""
    home_r = kin.tcp_pose(kin.seed)[1]
    positions = np.asarray(kin.fk.solve(kin.seed)["position_world_m"]).reshape(-1, 3)
    left, right = (positions[env._robot.entity.get_link(name).idx_local] for name in ("left_finger", "right_finger"))
    target_p, target_r = grasp_tcp(state, tilt_deg, home_r.inv().apply(left-right), home_r)
    pre_p = target_p-target_r.apply([0., 0., approach_m])
    free = kin.plan_free_tcp((pre_p, target_r))
    q = np.asarray(free[-1]["qpos"])
    descent, gaps = [], []
    for u in np.linspace(0., 1., int(np.ceil(approach_m/.001))+1)[1:]:
        q = kin.solve((pre_p+u*(target_p-pre_p), target_r), q)
        gaps.append(kin.clearance(q, link_pose(state, GRASP_LINK)))
        descent.append(q.tolist())
    if min(gaps) < CLEARANCE_M:
        raise ValueError(f"Grasp descent clearance {min(gaps):.6g} m")
    return dict(free_transfer=free, descent_qpos=descent, descent_clearance_m=gaps,
                grasp_tcp=[target_p.tolist(), target_r.as_quat()[[3, 0, 1, 2]].tolist()])


def plan_comb(kin, state, layout, parameters, strand=None):
    """Comb the strand farthest from the sheath axis (or the given one)."""
    rows = strand_measures(state, layout)
    if strand is None:
        strand = int(np.argmax([row["max_radius_m"] for row in rows]))
    _, axis = ring_frame(state)
    rolls = roll_choices(rows[strand]["fan_deg"], current_roll_deg(state, axis))
    if parameters["roll_rank"] >= len(rolls):
        raise ValueError(f"Strand {strand} has only {len(rolls)} allowed rolls")
    roll = rolls[parameters["roll_rank"]]
    guide_a, guide_b, geometry = comb_keyframes(state, layout, strand, parameters["d_press_m"], roll,
                                                approach_margin_m=parameters["approach_margin_m"],
                                                tip_past_ring_m=parameters["tip_past_ring_m"])
    offset_p, offset_r = measured_offset(kin, state)
    seed = kin.seed.copy()
    first = connect(kin, guide_a, offset_p, offset_r)
    kin.seed = np.asarray(first["refs"][-1]["qpos"])
    try:
        guide_b[0] = dict(label="planned_press", position_m=first["refs"][-1]["position_m"],
                          quaternion_wxyz=first["refs"][-1]["quaternion_wxyz"])
        second = connect(kin, guide_b, offset_p, offset_r)
    finally:
        kin.seed = seed
    return dict(strand=strand, roll_deg=roll, geometry=geometry, strand_measures=rows, guides=[first, second],
                end_qpos=second["refs"][-1]["qpos"])


def plan_feed(kin, state, front_s_m, maximum_front_offset_m):
    offset_p, offset_r = measured_offset(kin, state)
    plan = connect(kin, feed_keyframes(state, front_s_m), offset_p, offset_r)
    offsets = front_offsets(plan["refs"], state)
    if max(offsets) > maximum_front_offset_m:
        raise ValueError(f"Planned front point leaves the ring axis by {max(offsets):.6g} m")
    return dict(plan=plan, front_offsets_m=offsets)


def hand(tick):
    return tick["world"]["grasp"]["hands"]["arm"]


def holding(tick):
    return {"holding": hand(tick)["phase"] == "holding"}


def unbound(tick):
    return {"unbound": hand(tick)["binding"] is None}


def common(tick):
    summary = tick["world"]["contact_events"]
    result = tick["task"]["result"]
    return dict(contact_coverage=summary["substeps_complete"] is True and summary["geometry_roles_complete"] is True,
                task_not_failed=not (result["terminated"] and not result["task_success"]))


def stages(env, context):
    output = context.output / "planning"
    output.mkdir(exist_ok=True)
    layout = env._task.layout
    variant = env.config.variation_id
    attempts = [0]

    def measures(state):
        return strand_measures(state, layout)

    def wrap(inner):
        return CheckedJointPolicy(inner, env._robot) if env.config.control_mode == "JOINT_ABS" else inner

    def stage(name, kind, definition, kwargs, entry, exit, budget_s, *, holding_throughout):
        def invariant(tick):
            values = common(tick)
            if holding_throughout:
                values.update(holding(tick))
            return values
        return Stage(name, kind, definition, lambda tick: wrap(FiberPolicy(**kwargs)), entry, invariant, exit, budget_s)

    def pickup(parameters):
        state = env._world.read_state()
        plan = plan_pickup(env, FiberIK(env), state, parameters["tilt_deg"], parameters["approach_m"])
        write_json_atomic(output / "pickup.json", dict(parameters=parameters, **plan))
        start = link_pose(state, GRASP_LINK)[0]

        def exit(tick):
            binding = hand(tick)["binding"]
            moved = np.linalg.norm(link_pose(tick["world"], GRASP_LINK)[0]-start)
            return dict(holding(tick), acquisition_evidence=bool(binding and binding["acquisition_evidence"]),
                        sheath_moved_under_3mm=bool(moved <= .003))
        kwargs = dict(part="pickup", plan=plan["free_transfer"], grasp_pose=plan["grasp_tcp"], settle_timeout_s=45.)
        return stage("pickup", "grasp", dict(parameters=parameters), kwargs, unbound, exit, 90.,
                     holding_throughout=False)

    def comb(name, parameters):
        state = env._world.read_state()
        plan = plan_comb(FiberIK(env), state, layout, parameters)
        attempts[0] += 1
        write_json_atomic(output / f"{name}_plan{attempts[0]:03d}.json", dict(parameters=parameters, **plan))
        first, second = plan["guides"]
        strand = plan["strand"]
        duration = first["refs"][-1]["time_s"]+second["refs"][-1]["time_s"]

        def exit(tick):
            after = measures(tick["world"])
            return dict(holding(tick), strand_within_target=after[strand]["max_radius_m"] <= COMB_TARGET_M,
                        bends_within_limit=max(row["max_bend_deg"] for row in after) <= MAXIMUM_BEND_DEG)
        kwargs = dict(part="references", plans=[first["refs"], second["refs"]], pauses=[1., .5],
                      progress_error_m=.001, arrival_error_m=.001)
        definition = dict(parameters=dict(parameters, strand=strand, roll_deg=plan["roll_deg"]), planned_s=duration,
                          minimum_clearance_m=min(e["minimum_clearance_m"] for e in first["edges"]+second["edges"]))
        return stage(name, "interaction", definition, kwargs, holding, exit, max(40., 2*duration+10),
                     holding_throughout=True)

    def verify(parameters):
        def exit(tick):
            rows = measures(tick["world"])
            return dict(holding(tick), all_strands_within_target=max(r["max_radius_m"] for r in rows) <= COMB_TARGET_M,
                        bends_within_limit=max(r["max_bend_deg"] for r in rows) <= MAXIMUM_BEND_DEG)
        kwargs = dict(part="script", instructions=[dict(operation="hold", seconds=parameters["hold_s"])])
        return stage("verify_combed", "interaction", dict(parameters=parameters), kwargs, holding, exit, 5.,
                     holding_throughout=True)

    def feed(parameters):
        state = env._world.read_state()
        result = plan_feed(FiberIK(env), state, parameters["front_s_m"], parameters["maximum_front_offset_m"])
        write_json_atomic(output / "feed.json", dict(parameters=parameters, **result))
        plan = result["plan"]
        duration = plan["refs"][-1]["time_s"]

        def exit(tick):
            return {"task_success": tick["task"]["result"]["task_success"] is True}
        kwargs = dict(part="references", plans=[plan["refs"]], pauses=[parameters["hold_s"]],
                      progress_error_m=.0005, arrival_error_m=.0005)
        definition = dict(parameters=parameters, planned_s=duration,
                          maximum_planned_front_offset_m=max(result["front_offsets_m"]),
                          minimum_clearance_m=min(e["minimum_clearance_m"] for e in plan["edges"]))
        return stage("feed", "settle", definition, kwargs, holding, exit, max(40., 2*duration+10),
                     holding_throughout=True)

    yield Step("pickup", PICKUPS, pickup)
    limit, index = 3*layout.fiber_count, 0
    while max(row["max_radius_m"] for row in measures(env._world.read_state())) > COMB_TARGET_M:
        if index >= limit:
            raise ValueError(f"{variant}: strands still outside {COMB_TARGET_M} m after {limit} combing steps")
        index += 1
        yield Step(f"comb_{index:02d}", COMBS, lambda parameters, name=f"comb_{index:02d}": comb(name, parameters))
    yield Step("verify_combed", (dict(hold_s=1.),), verify)
    yield Step("feed", (FEED,), feed)


def pickup_only(env, context):
    """Grasp check alone (the first step of stages): approach, close on the
    sheath, register the contact weld and settle the fingers."""
    yield next(iter(stages(env, context)))
