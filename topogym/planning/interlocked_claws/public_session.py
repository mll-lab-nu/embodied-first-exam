"""Revalidate the original Claws object witness, then run its measured robot policy."""
import json
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.planning.harbor_bridge.callbacks import prepare_output, data_path
from .recipes import run_claws_oracle
from .object_oracle import audit_object_path


def run_feedback_policy(session, output, *, variation):
    output = prepare_output(session, output, __file__)
    witness = json.loads(data_path(f"interlocked_claws/{variation}/witness.json").read_text())
    checked = audit_object_path(witness, output / "witness_audit")
    if not checked["passed"]:
        raise ValueError("Claws reference witness failed current-model audit")
    return run_claws_oracle(session.env, SessionPolicyRunner(session), output, witness,
                           joint_speed_rad_s={"easy": .2, "medium": .1, "hard": .08}[variation])
