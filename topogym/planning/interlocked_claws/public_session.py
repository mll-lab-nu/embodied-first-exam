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
    # hard at .04 (was .08): at .08 the pieces press together mid-separation (5.5 N > the 5 N guard at physics step
    # 56700, with or without the droop start); at .04 the separation has no piece/piece contact at all (lab, 2026-10-04).
    return run_claws_oracle(session.env, SessionPolicyRunner(session), output, witness,
                           joint_speed_rad_s={"easy": .2, "medium": .1, "hard": .04}[variation])
