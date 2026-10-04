"""Run the existing Coil policy against the exact manager-created Harbor Session."""
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from .policy import CastCoilPolicy, variant_reference
from .simplified_policy import SimplifiedCoilPolicy


def run_feedback_policy(session, output):
    if session.task != "cast_coil" or session.n_steps or session._resets:
        raise ValueError("Coil reference requires a fresh frozen Coil Session")
    task = session.env._task
    arguments = dict(variant=task.variation_id, seed=session.config["seed"], task_parameters=task.config)
    assembly, _ = variant_reference(**arguments)
    policy_class = SimplifiedCoilPolicy if hasattr(assembly, "record") else CastCoilPolicy
    policy = policy_class(body_origins=task.body_origins, part="all", **arguments)
    return SessionPolicyRunner(session, control_mode="EE_ABS").run_policy(
        request_id="coil-frozen-instance", policy=policy, submission_hash=session.instance_sha,
        state_fields=("world",))
