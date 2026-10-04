"""Use the existing measured-route robot oracle and explicit tier pickup."""
import json
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.planning.harbor_bridge.callbacks import prepare_output, data_path
from .recipes import run_medium_oracle


def run_feedback_policy(session, output, *, variation):
    output = prepare_output(session, output, __file__)
    pickup = None if variation == "medium" else json.loads(data_path(f"hedgehog_in_cage/{variation}/pickup.json").read_text())
    return run_medium_oracle(session.env, SessionPolicyRunner(session), output, pickup=pickup)
