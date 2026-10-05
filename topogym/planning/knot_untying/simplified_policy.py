"""Choose reachable node-deletion grasps for the approved open-loop variants.

The crossing rule still comes from the measured rope. IK only chooses between
candidate ends/nearby bands; the normal controller must execute the grasp.
"""
from .route_rule import choose
import numpy as np

BELOW_EASY = {"knot_untying_very_easy", "knot_untying_easier"}


def step_with_joint_limit(runner, phase, limit):
    """Execute intermediate targets now; never retime a saved successful trace.

    Native Session guards still apply to every row. A guard may stop progress
    toward a target; the controller then observes the actual accepted target.
    """
    session = runner.session
    desired = {side: q.copy() for side, q in runner.q.items()}
    initial = session.hold_action()
    starts = {side: initial[session.robot.arm_slice[side]].copy() for side in desired}
    travel = max((float(np.max(np.abs(desired[side]-starts[side]))) for side in desired), default=0.)
    budget = .95*limit  # leave room for float32 rounding at the service boundary
    count = max(1, int(np.ceil(travel/budget)))
    grippers = dict(runner.g)
    for k in range(1, count+1):
        previous = session.hold_action()
        for side in desired:
            current = previous[session.robot.arm_slice[side]]
            target = starts[side]+(desired[side]-starts[side])*(k/count)
            runner.q[side] = current+np.clip(target-current, -budget, budget)
        runner.g.update(grippers)
        runner._step_once(phase)
        accepted = session.hold_action()
        if any(np.max(np.abs(accepted[session.robot.arm_slice[side]]-
                             previous[session.robot.arm_slice[side]])) > limit+1e-6
               for side in desired):
            raise RuntimeError('Native guard changed a target beyond the standard joint step limit')


def reachable_withdrawal(runner, cfg):
    line = runner.line()
    crossings = runner.crossings(line)
    attempted, seen = [], set()
    for end, offset in (("auto", .035), ("A", .035), ("B", .035),
                        ("A", .060), ("B", .060), ("A", .015), ("B", .015)):
        action = choose(line, runner.stations, crossings, runner.length,
                        cfg['hold'], cfg['direction'], end_choice=end, pull_offset=offset)
        if action is None:
            continue
        key = (action['end'], action['s_pull'], action['s_anchor'])
        if key in seen:
            continue
        seen.add(key)
        stations = (action['s_anchor'], action['s_pull'])
        sides = runner.arms_for(stations)
        try:
            for side, station in zip(sides, stations):
                selected, _ = runner.grasp_site(station)
                runner.pose(side, selected)
        except (ValueError, RuntimeError) as error:
            attempted.append(dict(end=action['end'], pull_offset_m=offset, error=str(error)))
            continue
        return dict(action, pickup_selection=dict(
            method='live_crossings_then_read_only_pickup_ik', pull_offset_m=offset,
            rejected_candidates=attempted, physical_grasp_verified=False))
    raise ValueError(f'No reachable node-deletion pickup among {len(seen)} candidates: {attempted}')
