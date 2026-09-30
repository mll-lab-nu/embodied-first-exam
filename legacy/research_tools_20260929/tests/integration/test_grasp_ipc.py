"""Real IPC material grasp in the shared simulator and policy runner."""
import os
from pathlib import Path
import pytest
from test_grasp_pbd import run_material_policy

pytestmark = [pytest.mark.genesis, pytest.mark.fem, pytest.mark.ipc]


def test_ipc_policy_grasp(tmp_path):
    run_material_policy(Path(os.environ.get('TOPOGYM_TEST_OUTPUT', tmp_path)), 'fem',
                        rgb=os.environ.get('TOPOGYM_TEST_RGB') == '1')
