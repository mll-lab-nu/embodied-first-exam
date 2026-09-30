"""Core test fixtures; declaring them does not initialize Genesis."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

import topogym.simulator.config as _simulator_config

# The suites rewind to arbitrary ticks: keep a complete checkpoint per tick unless a test selects "segment".
_simulator_config.DEFAULT_HISTORY_STORAGE = "memory"


@pytest.fixture
def local_env(monkeypatch):
    """Exercise real Env/history orchestration with a deterministic tiny world."""
    import topogym.simulator.env as module
    import topogym.config.scene as scene_config
    from topogym.config import SimulatorConfig
    from topogym.world.genesis_world import GenesisWorld
    import topogym.robot.joint_position as robot_module
    from topogym.tasks.base import TaskDefinition, TaskSpec

    class Task(TaskDefinition):
        task_id = "fixture"
        defaults = {"stable_duration_s": .03}

        def declare(self, asset_dir, table_height_m):
            return TaskSpec(())

        def evaluate_state(self, state):
            return state["position"] >= 10., None, {"position": state["position"]}

    class World:
        def __init__(self):
            self.physics_step = 0
            self.physics_dt_s = .01
            self.position = 0.
            self.target = 0.
            self.entities = {"robot": self}
            self.cameras = {}
            self.closed = False

        @property
        def sim_time_s(self):
            return self.physics_step * self.physics_dt_s

        def add_entities(self, _):
            pass

        def build(self):
            pass

        def advance(self):
            self.position += (self.target - self.position) * .1
            self.physics_step += 1

        def reset_clock(self):
            self.physics_step = 0

        def read_state(self):
            return {"physics_step": self.physics_step, "position": self.position}

        def capture_state(self):
            return deepcopy((self.physics_step, self.position, self.target))

        def restore_state(self, state):
            self.physics_step, self.position, self.target = deepcopy(state)

        def close(self):
            self.closed = True

    class Robot:
        action_spec = {"target": "finite displacement in metres"}
        description = SimpleNamespace(robot_id="aloha")

        def __init__(self, entity):
            self.entity = entity

        def reset_home(self):
            self.entity.position = self.entity.target = 0.

        def validate_action(self, action):
            if set(action) != {"target"} or not np.isfinite(action["target"]):
                raise ValueError("Invalid target")
            return dict(action)

        def apply_action(self, command):
            self.entity.target = command["target"]

        def observe(self):
            return {"arm": {"joint_position_rad": np.array([self.entity.position]), "joint_velocity_rad_s": np.array([0.])}}

        def capture_state(self):
            return SimpleNamespace(targets={"target": self.entity.target})

        def restore_state(self, state):
            self.entity.target = state.targets["target"]

    monkeypatch.setattr(module, "task_definition", lambda name, variation_id="base": Task)
    monkeypatch.setattr(scene_config, "load_scene_config", lambda config: SimpleNamespace(
        env=SimpleNamespace(world=SimpleNamespace(table=SimpleNamespace(pos=[0, 0, 0], size=[1, 1, 1]))),
        robot_control=None))
    monkeypatch.setattr(GenesisWorld, "from_tabletop", lambda *args, **kwargs: World())
    monkeypatch.setattr(robot_module, "make_robot", lambda entity, config: Robot(entity))
    env = module.Env(SimulatorConfig(physics_dt_s=.01, control_decimation=3, max_physics_steps=12, enable_rgb=False, enable_privileged=True))
    try:
        env.reset(seed=4)
        yield env
    finally:
        env.close()
