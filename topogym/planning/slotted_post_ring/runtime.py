"""Slotted oracle adapter for the local release's rule-owning Session.

This module changes no material, geometry, contact rule or simulator option.
The caller owns the Session, recorder and lifecycle.
"""
from pathlib import Path

from topogym.tasks.release_profile import PROFILE, environment_inputs


def tooling():
    from harbor_templates.topogym.common import rcb_topogym
    return rcb_topogym


def build_config(variant, seed):
    parameters, overrides, _ = environment_inputs("slotted_post_ring", variant, seed=seed)
    return tooling().simulator_config(
        "slotted_post_ring", variation_id="slotted_post_ring_" + variant, seed=seed,
        task_parameters=parameters, simulator_overrides=overrides)


def run_session(session, output, *, stop_after=None):
    """Emit native JOINT_ABS targets through Session, retaining all installed v15 rules."""
    from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
    from topogym.planning.harbor_bridge.callbacks import fingerprint
    from topogym.utils.io import write_json_atomic
    from .geometry import SceneGeometry
    from .kinematics import ArmIK
    from .policy import SlottedOraclePolicy

    env = session.env
    if env.config.task_id != "slotted_post_ring" or env.config.control_mode != "JOINT_ABS":
        raise ValueError("Expected a Slotted Post Ring JOINT_ABS Session")
    if not getattr(session, "rules", None):
        raise ValueError("The caller must install the local Session rules")
    if session.n_steps or session._recording is None:
        raise ValueError("The caller must start recording a fresh Session")
    geometry = SceneGeometry.from_task(env._task)
    policy = SlottedOraclePolicy(kinematics=ArmIK(env._robot), geometry=geometry,
                                control_dt_s=env.timing_spec["control_dt_s"], stop_after=stop_after)
    output = Path(output)
    try:
        return SessionPolicyRunner(session).run_policy(
            request_id="slotted-oracle", policy=policy,
            submission_hash=fingerprint(dict(profile=PROFILE, instance_id=env._task.instance_id,
                                             stop_after=stop_after)),
            mode="unlimited", state_fields=("world",))
    finally:
        write_json_atomic(output / "policy_report.json", dict(
            phase=policy.phase, policy_completed=policy.done, stage_log=policy.log,
            geometry=geometry, qualification="unqualified",
            scope="Imported stage candidate under local Session rules; no success qualification"))
