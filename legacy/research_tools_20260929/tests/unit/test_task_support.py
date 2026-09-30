"""All tasks have real definitions; missing operations fail before scene construction."""

import pytest
from topogym.config import SimulatorConfig, task_catalog
from topogym.config.registry import (
    TaskSupportError,
    require_task_support,
    task_definition,
)
from topogym.simulator.env import Env
from topogym.tasks.base import TaskDefinition

SOFT_TASKS = ("rope_threading", "knot_untying", "orbits", "slotted_post_ring")


def test_all_thirteen_definitions_and_goals_match_capability_catalog():
    records = task_catalog()
    assert len(records) == 13
    for record in records:
        cls = task_definition(record["task_id"])
        assert issubclass(cls, TaskDefinition)
        assert cls.task_id == record["task_id"]
        assert cls.physics_model == record["physics_model"]
        assert cls().goal_complete == (
            not any("solve" in g["blocks"] for g in record["gaps"])
        )
        assert record["status"] == "integrated"
        assert record["validation"] == "see_runs_test_results"


@pytest.mark.parametrize("task_id", SOFT_TASKS)
def test_fem_cpu_reset_explains_device_requirement_without_building(
    task_id, monkeypatch, tmp_path
):
    import topogym.world.genesis_world as world

    def forbidden(*args, **kwargs):
        raise AssertionError("An unsupported reset must never allocate a scene")

    monkeypatch.setattr(world.GenesisWorld, "from_tabletop", forbidden)
    with Env(SimulatorConfig(task_id=task_id, compute_backend="cpu", enable_rgb=False, work_dir=tmp_path)) as env:
        assert env.support_report()["implementation"].startswith("topogym.tasks.")
        with pytest.raises(RuntimeError, match="CUDA"):
            env.reset(seed=0)
        assert not env.state_history and not list(tmp_path.iterdir())


def test_incomplete_goal_cannot_emit_success_even_if_provisional_predicate_is_true():
    class Incomplete(TaskDefinition):
        task_id = "fixture"
        goal_complete = False

        def evaluate_state(self, state):
            return True, None, {}

    task = Incomplete()
    task.initialize({"physics_step": 0})
    for tick in range(1, 20):
        result = task.update({"physics_step": tick}, 0.1)
        assert (
            not result.task_success and not result.terminated and result.reward == 0.0
        )
        assert result.metrics["goal_evaluation_complete"] is False
    forged = task.get_state()
    forged["result"].update(task_success=True, terminated=True, reward=1.0)
    with pytest.raises(ValueError):
        task.set_state(forged)


def test_unavailable_assist_is_described_separately_from_lifecycle():
    require_task_support("cast_coil", "reset")
    with pytest.raises(TaskSupportError, match="rigid_attachment_creation"):
        require_task_support("cast_coil", "assist_grasp")
