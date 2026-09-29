"""Small FEM tube with fixed/dynamic ends, using the real shared Env and video."""

from pathlib import Path
import numpy as np
import pytest

from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec, AttachmentSpec

pytestmark = [pytest.mark.genesis, pytest.mark.fem, pytest.mark.ipc, pytest.mark.render]


class CheckpointProbeTask(TaskDefinition):
    task_id = "fem_checkpoint_probe"
    physics_model = "fem_ipc"
    goal_complete = False

    def declare(self, asset_dir, table_height_m):
        from topogym.assets.geometry.rope_volume import write_rope_volume
        from topogym.assets.materials import rope_fem_parameters
        from topogym.utils.geometry.rope import make_elastic_tube_mesh, write_obj

        folder = Path(asset_dir)
        folder.mkdir(parents=True)
        line = np.column_stack(
            [np.linspace(-0.06, 0.06, 16), np.full(16, -0.22), np.full(16, 0.12)]
        )
        volume = write_rope_volume(folder / "volume.npz", line, 0.004)
        vertices, faces = make_elastic_tube_mesh(line, radius=0.004, radial_segments=8)
        write_obj(folder / "rope.obj", vertices, faces)
        entities = (
            EntitySpec(
                "rope",
                "mesh",
                folder / "rope.obj",
                (0, 0, table_height_m),
                physics_model="fem_elastic",
                material=rope_fem_parameters(),
                volume_path=volume,
            ),
            EntitySpec(
                "fixed_anchor",
                "box",
                None,
                (-0.08, -0.22, table_height_m + 0.12),
                fixed=True,
                morph_options={"size": (0.02, 0.02, 0.02)},
                material={"coup_type": "ipc_only"},
            ),
            EntitySpec(
                "moving_anchor",
                "box",
                None,
                (0.08, -0.22, table_height_m + 0.12),
                morph_options={"size": (0.02, 0.02, 0.02)},
                material={"coup_type": "ipc_only"},
            ),
        )
        return TaskSpec(
            entities,
            {"fem": {}, "ipc": {}},
            attachments=(
                AttachmentSpec("fixed_end", "rope", "fixed_anchor", "start", 0.004),
                AttachmentSpec("moving_end", "rope", "moving_anchor", "end", 0.004),
            ),
        )

    def evaluate_state(self, state):
        return (
            False,
            None,
            {"goal_evaluation_complete": False, "scope": "physical checkpoint probe"},
        )


def test_fem_native_checkpoint_and_end_constraints(monkeypatch):
    from topogym.config import registry
    from test_base_task_runtime import exercise_runtime

    monkeypatch.setitem(
        registry._TASKS,
        CheckpointProbeTask.task_id,
        registry.TaskRegistration(
            CheckpointProbeTask.task_id, f"{__name__}:CheckpointProbeTask", "fem_ipc"
        ),
    )
    exercise_runtime(CheckpointProbeTask.task_id)
