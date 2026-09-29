"""Real passive scripted policies, frozen before each Genesis/Nyx run."""
from datetime import date
import os
from pathlib import Path
import pytest
from scripts.test_scripted_policy_rollout import allocate_rollout, run_snapshot

pytestmark = [pytest.mark.genesis, pytest.mark.render]

# Same 40 Hz policy cadence and 0.625 ms solver substeps as the default rigid
# setup, but checkpoints are taken once per 25 ms physics tick in these long
# tests. This does not qualify the default ten-tick configuration.
TIMING = dict(physics_dt=.025, control_decimation=1, solver_substeps=40)


def execute(*, case="cube", seed=0, split=False, timing=TIMING):
    root = Path(os.environ.get("TOPOGYM_TEST_OUTPUT", "task_rollouts"))
    experiment = "scripted_policy_pytest_" + date.today().strftime("%Y%m%d")
    task = "cube_pick_place" if case == "pick_place" else "cube_transfer"
    output = allocate_rollout(root, experiment, task)
    return run_snapshot(output, case=case, seed=seed, split=split, **timing)


def test_cube_pick_and_place():
    execute(case="pick_place")


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_cube_transfer(seed):
    execute(seed=seed)


def test_cube_two_segments():
    execute(split=True)


def test_empty_grasp_is_not_success():
    execute(case="empty_grasp")


def test_limited_feedback_with_default_physics_ticks():
    execute(case="limited", timing=dict(physics_dt=.0025, control_decimation=10, solver_substeps=4))
