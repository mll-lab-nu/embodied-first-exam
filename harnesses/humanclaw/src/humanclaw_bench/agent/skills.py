"""Self-contained skill-call schema for HumanClawBench."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


@dataclass(frozen=True)
class SkillCall:
    """Represent one executable motion skill plus its numeric/string condition."""

    skill: str
    cond: Any
    source_index: int = 0
    action_id: int | None = None
    action_name: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize the skill, condition, ID, and display name to JSON fields."""

        return {
            "action_id": self.action_id,
            "action_name": self.action_name,
            "skill": self.skill,
            "cond": self.cond,
            "source_index": self.source_index,
        }


def skill_to_text(action: SkillCall) -> str:
    """Serialize a SkillCall into the action text used in prompts and logs."""

    if action.action_name:
        if action.action_id is None:
            return action.action_name
        return f"action id {action.action_id}: {action.action_name}"
    if action.cond is None:
        return action.skill
    return f"{action.skill} cond={action.cond}"


STAND_SKILL_CALL = SkillCall(skill="stand", cond=None, action_name="Stop/Stand")

# Execution semantics are versioned separately from the model-visible prompts.
ACTION_PARSER_VERSION = "humanclaw-action-parser-v2"
_NUMBER = r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
_ACTION_SYNTAX = (
    (r"Walk", (r"forward", r"slow|normal|fast"), "Walk<forward><slow|normal|fast>"),
    (r"(?:Stop\s*/\s*Stand|Stop\s+Stand|Stop|Stand)", (), "Stop/Stand"),
    (r"Turn", (r"left|right", _NUMBER), "Turn<left|right><degrees>"),
    (r"Climb\s+(?:upstairs|up)", (r"normal",), "Climb upstairs<normal>"),
    (r"Sit(?:\s+down)?", (_NUMBER,), "Sit down<height>"),
    (r"(?:Step\s+back|Back)", (_NUMBER,), "Step back<distance>"),
    (r"(?:Side\s+(?:step|walk)|Sidestep)", (r"left|right", _NUMBER),
     "Side step<left|right><distance>"),
    (r"(?:Walk\s+downstairs|Climb\s+(?:downstairs|down))", (r"normal",),
     "Walk downstairs<normal>"),
)

__all__ = [
    "ACTION_PARSER_VERSION",
    "STAND_SKILL_CALL",
    "SkillCall",
    "skill_to_text",
    "normalize_action",
]


def _parse_action(action_name: Any, action_id: Any) -> tuple[int, tuple[str, ...]]:
    """Match a complete action; never infer missing parameters or ignore text."""

    if action_id is not None:
        if isinstance(action_id, str) and re.fullmatch(r"[0-7]", action_id.strip()):
            action_id = int(action_id.strip())
        if type(action_id) is not int or action_id not in range(8):
            raise ValueError("action_id must be an integer from 0 through 7")
    if not isinstance(action_name, str) or not action_name.strip():
        raise ValueError("action_name must be a nonempty string with explicit parameters")

    for family_id, (prefix, parameters, _) in enumerate(_ACTION_SYNTAX):
        bracketed = prefix + "".join(r"\s*<\s*(" + p + r")\s*>" for p in parameters)
        plain = prefix + "".join(r"\s+(" + p + r")" for p in parameters)
        for pattern in (bracketed, plain):
            match = re.fullmatch(pattern, action_name.strip(), re.IGNORECASE)
            if match is None:
                continue
            if action_id is not None and family_id != action_id:
                raise ValueError(
                    f"action_id {action_id} does not match action_name {action_name!r}; "
                    f"expected {_ACTION_SYNTAX[action_id][2]}"
                )
            return family_id, tuple(token.lower() for token in match.groups())
    expected = (_ACTION_SYNTAX[action_id][2] if action_id is not None
                else "; ".join(row[2] for row in _ACTION_SYNTAX))
    raise ValueError(
        f"Invalid action_name {action_name!r}. Expected {expected}; provide every "
        "parameter in angle brackets or separated by spaces, with no extra text."
    )


def _bounded_parameter(text: str, minimum: float, maximum: float) -> float:
    """Apply the documented clamp only to an explicit, positive finite value."""
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Action magnitude must be positive and finite, got {text!r}")
    return max(minimum, min(maximum, value))


def _number_label(value: float, places: int = 0) -> str:
    """Keep familiar labels without rounding away an executed parameter."""
    label = f"{value:.{places}f}"
    return label if float(label) == value else str(value)


def normalize_action(chooser_plan: dict[str, Any]) -> SkillCall:
    """Parse bracketed or plain actions without guessing their semantics.

    A supplied ID must agree with the fully parsed name. Missing, unknown,
    conflicting, or malformed parameters raise ValueError instead of selecting
    a default motion. Positive numeric values retain the documented clamps.
    """
    if not isinstance(chooser_plan, dict):
        raise ValueError("Action must be an object containing action_name")
    family_id, tokens = _parse_action(
        chooser_plan.get("action_name"), chooser_plan.get("action_id")
    )
    if family_id == 1:
        return STAND_SKILL_CALL

    if family_id == 0:
        speed = tokens[1]
        distance = {"slow": 0.2, "normal": 0.4, "fast": 0.6}[speed]
        return SkillCall(
            skill="walk_forward",
            cond=[0.0, distance, 0.0],
            action_name=f"Walk<forward><{speed}>",
        )

    if family_id == 2:
        direction = tokens[0]
        degree = _bounded_parameter(tokens[1], 10.0, 120.0)
        signed_degree = degree if direction == "left" else -degree
        return SkillCall(
            skill="turn",
            cond=signed_degree,
            action_name=f"Turn<{direction}><{_number_label(degree)}>",
        )

    if family_id == 3:
        return SkillCall(
            skill="step_climb_up",
            cond=[0.28, 0.30],
            action_name="Climb upstairs<normal>",
        )

    if family_id == 4:
        target_height = _bounded_parameter(tokens[0], 0.15, 0.85)
        return SkillCall(
            skill="sit",
            cond=target_height,
            action_id=4,
            action_name=f"Sit down<{_number_label(target_height, 2)}>",
        )

    if family_id == 5:
        distance = _bounded_parameter(tokens[0], 0.10, 0.60)
        return SkillCall(
            skill="step_back",
            cond=[0.0, -distance],
            action_id=5,
            action_name=f"Step back<{_number_label(distance, 2)}>",
        )

    if family_id == 6:
        direction = tokens[0]
        distance = _bounded_parameter(tokens[1], 0.10, 0.50)
        signed_x = distance if direction == "left" else -distance
        return SkillCall(
            skill="side_walk",
            cond=signed_x,
            action_id=6,
            action_name=f"Side step<{direction}><{_number_label(distance, 2)}>",
        )

    if family_id == 7:
        return SkillCall(
            skill="step_climb_down",
            cond=[0.20, 0.40],
            action_id=7,
            action_name="Walk downstairs<normal>",
        )

    raise ValueError(f"Unsupported action_id {family_id}")
