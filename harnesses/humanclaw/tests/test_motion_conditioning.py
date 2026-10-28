"""Guard the final motion boundary against substituted or truncated actions."""

import pytest

torch = pytest.importorskip("torch")

from humanclaw_bench.agent.skills import normalize_action
from humanclaw_bench.motion import runner
from humanclaw_bench.motion.conditioning import condition_args


@pytest.mark.parametrize("raw,kind,expected", [
    ("Walk forward normal", "fast_xzyaw", [[0.0, 0.4, 0.0]]),
    ("Walk forward fast", "fast_xzyaw", [[0.0, 0.6, 0.0]]),
    ("Turn right 90", "base", [[-1.2]]),
    ("Turn left 45", "base", [[0.6]]),
    ("Side step right 0.25", "side_fourier", [[-0.25]]),
    ("Step back 0.25", "fourier", [[0.0, -0.25]]),
    ("Sit down 0.455", "sit_mlp", [[0.455]]),
    ("Climb upstairs normal", "base", [[0.12, -2 / 3]]),
    ("Walk downstairs normal", "step_down_mlp", [[-0.2, -1 / 3]]),
])
def test_explicit_actions_reach_the_network_with_the_trained_encoding(raw, kind, expected):
    action = normalize_action({"action_name": raw})
    actual, = condition_args(action.skill, kind, action.cond, "cpu")
    torch.testing.assert_close(actual, torch.tensor(expected, dtype=torch.float32))


@pytest.mark.parametrize("skill,kind,condition", [
    ("walk_forward", "fast_xzyaw", [0, 0.4, 0, 1]),
    ("walk_forward", "fast_xzyaw", [0.4]),
    ("walk_forward", "fast_xzyaw", "0.4"),
    ("walk_forward", "fast_xzyaw", [0, float("inf"), 0]),
    ("walk_forward", "fast_xzyaw", [0, True, 0]),
    ("step_back", "fourier", [0, -0.25, 99]),
    ("step_back", "fourier", [0]),
    ("step_back", "fourier", -0.25),
    ("step_back", "fourier", True),
    ("sit", "sit_mlp", [0.45, 0.75]),
    ("sit", "sit_mlp", []),
    ("sit", "sit_mlp", float("nan")),
    ("side_walk", "side_fourier", float("nan")),
    ("turn", "base", float("inf")),
    ("turn", "base", 1e100),
    ("turn", "base", False),
    ("step_climb_up", "base", [0.28, 0.30, 0.4]),
    ("step_climb_down", "step_down_mlp", [0.20]),
    ("stand", "noncond_fast", [0.4]),
])
def test_invalid_conditions_raise_instead_of_discarding_values(skill, kind, condition):
    with pytest.raises(ValueError):
        condition_args(skill, kind, condition, "cpu")


def test_legacy_unambiguous_short_forms_keep_their_documented_encoding():
    torch.testing.assert_close(
        condition_args("walk_forward", "fast_xzyaw", [0, 0.4], "cpu")[0],
        torch.tensor([[0, 0.4, 0]]),
    )
    torch.testing.assert_close(
        condition_args("step_back", "fourier", 0.25, "cpu")[0],
        torch.tensor([[0, -0.25]]),
    )
    assert condition_args("stand", "noncond_fast", None, "cpu") == ()


@pytest.mark.parametrize("skill,condition", [
    ("walk_forward", [0, 0.4, 0]), ("turn", -90), ("unknown_skill", None),
])
def test_missing_skill_never_substitutes_the_loaded_stand_model(monkeypatch, skill, condition):
    motion = runner.MotionSkillRunner.__new__(runner.MotionSkillRunner)
    motion.skills = {"stand": (object(), "noncond_fast")}
    motion.motion_state = torch.zeros(1, 5, 219)
    motion.T_ref_accum = torch.eye(4)
    motion.step_index = 0
    motion.device = "cpu"
    initial = motion.motion_state.clone()

    def must_not_generate(*args):
        raise AssertionError("A rejected skill must not generate any motion")

    monkeypatch.setattr(runner, "denoise", must_not_generate)
    with pytest.raises(RuntimeError, match="not loaded; refusing to substitute"):
        motion.generate(skill, condition)
    torch.testing.assert_close(motion.motion_state, initial)
    assert motion.step_index == 0
