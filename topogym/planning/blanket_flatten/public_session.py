"""Reuse the existing Blanket route with Harbor-owned physics and recording."""
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from .robot_oracle import run_route_oracle


def run_feedback_policy(session, output, *, variation="easy"):
    if session.task != "blanket_flatten" or session.n_steps or session._resets:
        raise ValueError("Blanket reference requires a fresh frozen Blanket Session")
    if session.env._task.variation_id not in {variation, "blanket_flatten_" + variation}:
        raise ValueError("Blanket route differs from the frozen variation")
    return run_route_oracle(session.env, SessionPolicyRunner(session), output, variation=variation)
