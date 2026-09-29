"""Task stable windows, terminal latching and RNG follow historical state."""
import numpy as np
import pytest
from topogym.tasks.base import TaskDefinition


class Goal(TaskDefinition):
    task_id = "goal_fixture"
    defaults = {"stable_duration_s": .03}

    def evaluate_state(self, state):
        return state["goal"], state.get("failure"), {}


def test_repeated_read_does_not_advance_stability():
    task = Goal(seed=2)
    first = task.update({"physics_step": 1, "goal": True}, .01)
    for _ in range(10):
        assert task.update({"physics_step": 1, "goal": True}, .01) == first
    assert task.stable_time_s == 0.
    task.update({"physics_step": 2, "goal": True}, .01)
    assert not task.result.terminated
    assert not task.update({"physics_step": 3, "goal": True}, .01).task_success
    assert task.update({"physics_step": 4, "goal": True}, .01).task_success


def test_restore_counter_result_and_rng():
    task = Goal(seed=2)
    task.update({"physics_step": 1, "goal": True}, .01)
    saved = task.get_state()
    expected = task.rng.random(4)
    task.update({"physics_step": 2, "goal": False, "failure": "dropped"}, .01)
    task.set_state(saved)
    assert not task.result.terminated
    assert task.stable_time_s == 0.
    np.testing.assert_array_equal(task.rng.random(4), expected)
    with pytest.raises(ValueError):
        Goal(seed=3).set_state(saved)


def test_failure_has_priority_over_goal():
    task = Goal({"stable_duration_s": .01})
    task.update({"physics_step": 1, "goal": True}, .01)
    # Without failure this next tick would complete the stability window.
    result = task.update({"physics_step": 2, "goal": True, "failure": "collision"}, .01)
    assert result.terminated and not result.task_success and result.reason == "collision"


class HistoryGoal(Goal):
    def initial_task_state(self, state):
        return {"samples": np.zeros(2), "count": 0}

    def evaluate_transition(self, state, history):
        history["count"] += 1
        history["samples"][0] = state.get("sample", 1.)
        return state["goal"], state.get("failure"), {}, history


def test_history_preview_rewind_and_duplicate_tick():
    task = HistoryGoal()
    task.initialize({"physics_step": 0, "goal": False})
    assert task.task_state["count"] == 0
    task.update({"physics_step": 1, "goal": False}, .01)
    saved = task.get_state()
    assert saved["schema_version"] == 2
    task.update({"physics_step": 1, "goal": False}, .01)
    assert task.task_state["count"] == 1
    task.update({"physics_step": 2, "goal": False, "failure": "touch"}, .01)
    task.set_state(saved)
    saved["task_state"]["samples"][0] = 999
    assert task.task_state["samples"][0] == 1
    assert not task.result.terminated
    assert task.task_state["count"] == 1


def test_invalid_transition_is_atomic_and_restore_rejects_old_schema():
    task = HistoryGoal()
    task.initialize({"physics_step": 0, "goal": False})
    with pytest.raises(ValueError, match="finite"):
        task.update({"physics_step": 1, "goal": True, "sample": np.nan}, .01)
    assert task.last_physics_step == 0 and task.task_state["count"] == 0
    assert task.stable_time_s == 0 and not task._goal_active
    saved = task.get_state()
    saved["schema_version"] = 1
    with pytest.raises(ValueError, match="schema"):
        task.set_state(saved)
    saved = task.get_state()
    saved["task_state"]["samples"][0] = np.inf
    with pytest.raises(ValueError):
        task.set_state(saved)
    assert task.task_state["count"] == 0


def test_zero_confirmation_and_incomplete_failure():
    task = Goal({"stable_duration_s": 0.})
    assert task.update({"physics_step": 1, "goal": True}, .01).task_success
    task = Goal({"stable_duration_s": 0.})
    task.goal_complete = False
    result = task.update({"physics_step": 1, "goal": True, "failure": "touch"}, .01)
    assert result.terminated and not result.task_success
    with pytest.raises(ValueError):
        Goal({"stable_duration_s": -.1})
