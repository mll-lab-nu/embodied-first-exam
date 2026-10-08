"""Below-easy Slotted Post oracle (below_easy_oracle.BelowEasyPolicy) in a Harbor-owned, frozen Session."""
from topogym.planning.harbor_bridge.callbacks import prepare_output


def run_feedback_policy(session, output, *, variation):
    from topogym.planning.standard_rate import rate_limited_runner
    from topogym.utils.io import write_json_atomic
    from .below_easy_oracle import BelowEasyPolicy, EasierPolicy
    from .geometry import SceneGeometry
    from .kinematics import ArmIK

    if variation not in ("very_easy", "easier"):
        raise ValueError("The Slotted Post oracle covers the below-easy settings only")
    output = prepare_output(session, output, __file__)
    env = session.env
    policy = (EasierPolicy if variation == "easier" else BelowEasyPolicy)(
        kinematics=ArmIK(env._robot), geometry=SceneGeometry.from_task(env._task),
        control_dt_s=env.timing_spec["control_dt_s"])
    # Every recorded row keeps the standard service's joint-step limit (topogym/planning/standard_rate.py).
    runner = rate_limited_runner(session)
    try:
        result = runner.run_policy(request_id=f"slotted-below-easy-{variation}", policy=policy,
                                   submission_hash=session.instance_sha, state_fields=("world",))
    finally:
        write_json_atomic(output / "policy_report.json", dict(
            variation=variation, phase=policy.phase, policy_completed=policy.done, stage_log=policy.log,
            rate_limiter=runner.rate_limiter.report()))
    if not session.success():
        raise RuntimeError(f"Slotted below-easy oracle ended without native Task success: {result['reason']}")
    return result
