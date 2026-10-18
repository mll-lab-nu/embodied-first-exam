"""The fixture's evaluator hooks (skilleval/evaluate.py) and its one skill, swing(arm, t): an enum and a number field."""

from skilleval.contract import SkillContract, Tolerance

SWING = SkillContract(
    name="swing",
    call="swing(arm, t)",
    args={
        "arm": {"type": "enum", "values": ["left", "right", "both"]},
        "t": {"type": "number", "min": 0.05, "max": 1.0, "unit": "s"},
    },
    returns="one low-level command",
    measured="the hand's position at t",
    tolerances=(Tolerance("pos_err_m", 0.05),),
)
CONTRACTS = {"swing": SWING}


def skill_spec() -> dict:
    return {}
