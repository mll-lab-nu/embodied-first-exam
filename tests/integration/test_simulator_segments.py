"""Real short segments cover both robots and all four control modes."""
import os
from pathlib import Path
import pytest
from scripts.test_policy_cube_transfer import run_case

pytestmark = [pytest.mark.genesis, pytest.mark.render]


@pytest.mark.parametrize("robot", ["aloha", "panda_robotiq"])
@pytest.mark.parametrize("mode", ["JOINT_ABS", "JOINT_DELTA", "EE_ABS", "EE_DELTA"])
def test_segments(robot, mode):
    run_case(Path(os.environ["TOPOGYM_TEST_OUTPUT"]) / f"segments_{robot}_{mode}",
             case="interfaces", robot=robot, mode=mode)
