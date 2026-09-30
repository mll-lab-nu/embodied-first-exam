"""Task instructions: one per TopoGym task, equal to the task's own text where the code defines one."""
import pytest

import topogym
from topogym.config.registry import task_definition, variation_registration
from vla.gym.instructions import INSTRUCTIONS, VERSION


def test_instructions_cover_every_task():
    assert isinstance(VERSION, int) and set(INSTRUCTIONS) == set(topogym.env_list())


@pytest.mark.parametrize("task_id", ["buzz_wire_3d", "rope_threading", "lock_picking", "fiber_bundling",
                                     "knot_untying"])
def test_instructions_match_task_attributes(task_id):
    task = task_definition(task_id, variation_registration(task_id, "base", 0)["variation_id"])
    assert INSTRUCTIONS[task_id] == task.instruction
