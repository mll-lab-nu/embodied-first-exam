"""In-place pick/place predicate; the transfer task retains its distance rule."""
from contextlib import contextmanager
from dataclasses import replace

from fixtures.cube_transfer import CubeTransferTask


class CubePickPlaceTask(CubeTransferTask):
    task_id = "cube_pick_place"
    model_revision = "cube_pick_place_v1"

    def declare(self, asset_dir, table_height_m):
        spec = super().declare(asset_dir, table_height_m)
        self.target = self.start.copy()
        entities = tuple(replace(e, position_m=(*self.start[:2], table_height_m+.0005))
                         if e.name == "target_marker" else e for e in spec.entities)
        return replace(spec, entities=entities)

    def evaluate_state(self, state):
        _, failure, metrics = super().evaluate_state(state)
        reached = (self.lifted and self.held_once and metrics["gripper_open"] and metrics["withdrawn"]
                   and metrics["target_error_m"] <= .02 and abs(metrics["clearance_m"]) <= .003
                   and metrics["linear_speed_m_s"] <= .01 and metrics["angular_speed_rad_s"] <= .1)
        return bool(reached), failure, metrics


@contextmanager
def register_cube_pick_place():
    from topogym.config import registry, variation_records
    from topogym.config.registry import TaskRegistration
    old = variation_records.RECORDS
    identity = CubePickPlaceTask.task_id
    if identity in registry._TASKS:
        raise RuntimeError("Test task already registered")
    registry._TASKS[identity] = TaskRegistration(identity, "fixtures.cube_pick_place:CubePickPlaceTask", "rigid", "panda_robotiq")
    variation_records.RECORDS = (*old, dict(task_id=identity, variation_id="base", aliases=[], status="integrated",
        implementation="fixtures.cube_pick_place:CubePickPlaceTask", family_id="test", difficulty=None,
        model_revision=CubePickPlaceTask.model_revision, reason=None, validation="test_only", pool="test"))
    try:
        yield
    finally:
        del registry._TASKS[identity]
        variation_records.RECORDS = old
