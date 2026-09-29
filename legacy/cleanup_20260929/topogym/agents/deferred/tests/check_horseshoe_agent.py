"""Contact-based grasping, timed verdicts and the public information boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from topogym.agent_bridge.aloha_contract import validate_action
from topogym.agent_bridge.adapters import CounterTask
from topogym.agent_bridge.session import Session
from topogym.tasks.horseshoe_ring.agent_adapter import HorseshoeAdapter, StableVerdict, supported_bodies
from topogym.tasks.horseshoe_ring.agent_spec import describe_task
from topogym.world.aloha_cameras import configure_aloha_rig


class GraspChecks(unittest.TestCase):
    def contacts(self, edges):
        return dict(link_a=np.array([e[0] for e in edges]), link_b=np.array([e[1] for e in edges]),
                    force=np.array([[e[2], 0, 0] for e in edges]))

    def test_load_path_allows_pair_but_not_dangling_body(self):
        ct = self.contacts([(1, 3, 1), (3, 4, 1), (4, 2, 1), (4, 5, 1)])
        self.assertEqual(supported_bodies({1, 2}, {3, 4, 5}, ct), {3, 4})

    def test_single_pad_unloaded_and_chain_paths_do_not_attach(self):
        for edges in ([(1, 3, 1)], [(1, 3, 1), (3, 2, .005)],
                      [(1, 3, 1), (3, 99, 1), (99, 2, 1)]):
            self.assertEqual(supported_bodies({1, 2}, {3}, self.contacts(edges)), set())

    def test_stability_requires_consecutive_ticks_and_reads_do_not_advance(self):
        verdict = StableVerdict(.1)
        for _ in range(10):
            self.assertEqual(verdict.update(0, True)["status"], "running")
        for tick in (1, 2, 3, 4):
            verdict.update(tick, True)
        verdict.update(5, False)
        for tick in (6, 7, 8, 9):
            self.assertEqual(verdict.update(tick, True)["status"], "running")
        self.assertEqual(verdict.update(10, True)["status"], "succeeded")

    def test_failure_latches_even_after_later_goal(self):
        verdict = StableVerdict(.1)
        verdict.update(1, False, "chain lost")
        for tick in range(2, 20):
            self.assertEqual(verdict.update(tick, True), dict(status="failed", reason="chain lost"))


class ContractChecks(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        with initialize_config_dir(config_dir=str(root/"configs"), version_base="1.3"):
            self.cfg = compose(config_name="horseshoe_ring_aloha")
        configure_aloha_rig(self.cfg, keep=(), resolution=(640, 360), low_pitch_offset_deg=20)

    def test_object_configuration_cannot_change_public_description(self):
        before = describe_task(self.cfg)
        self.cfg.task.scale = 99
        self.cfg.task.center_xy_m = [99, 99]
        self.cfg.task.template_path = "/private/solution.json"
        self.assertEqual(before, describe_task(self.cfg))
        self.assertEqual(len(before["cameras"]), 4)
        self.assertNotIn("goal_reference", before)
        self.assertNotIn("/private", json.dumps(before))

    def test_invalid_actions_rejected_before_motion(self):
        schema = describe_task(self.cfg)["action_schema"]
        for action in ({"reset": True}, {"left": {"attach": "target_ring"}}, {"left": {}},
                       {"left": {"qpos": [0]*5}}, {"right": {"gripper": True}},
                       {"left": {"qpos": [float("nan")]*6}}, {"right": {"gripper": .1}}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_action(action, schema)
        validate_action({}, schema)
        validate_action({"left": {"gripper": .037}}, schema)

    def test_incomplete_dual_arm_rig_is_rejected_at_initialization(self):
        class MissingView(CounterTask):
            def describe(self):
                return dict(super().describe(), robot={"arms": ["left", "right"]})
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, "canonical views"):
            Session(MissingView, Path(root)/"episode")


class EvaluatorChecks(unittest.TestCase):
    def test_separated_ring_must_be_released_supported_quiet_and_intact(self):
        class Body:
            def __init__(self, idx, pos):
                self.base_link_idx, self.pos = idx, np.array(pos)
                self.velocity = np.zeros(3)
            def get_pos(self):
                return self.pos
            def get_quat(self):
                return np.array([1., 0., 0., 0.])
            def get_vel(self):
                return self.velocity
            def get_ang(self):
                return np.zeros(3)

        adapter = HorseshoeAdapter.__new__(HorseshoeAdapter)
        ring, shoe = Body(11, [1., 0., .05]), Body(10, [0., 0., .05])
        adapter.task = SimpleNamespace(bodies=dict(target_ring=ring, horseshoe=shoe),
            tabletop=SimpleNamespace(frames=SimpleNamespace(table_surface_origin=[0., 0., 0.])),
            assembly=SimpleNamespace(edges=[("a", "b")]))
        adapter.bodylinks, adapter.robotlinks, adapter.table = {10, 11}, {20, 21}, 30
        adapter.registrations = []
        adapter.vertices = {n: np.array([[-.01, -.01, -.01], [.01, .01, .01]]) for n in adapter.task.bodies}
        ct = dict(link_a=np.array([11]), link_b=np.array([30]), penetration=np.array([0.]), force=np.array([[0., 0., 1.]]))
        link = SimpleNamespace(linking=lambda _: 1)
        with patch("topogym.tasks.horseshoe_ring.demo.current_loops", return_value={"a": link, "b": link}):
            self.assertEqual(adapter._failure_and_goal(ct), (None, True))
            adapter.registrations = [(20, 11)]
            self.assertEqual(adapter._failure_and_goal(ct), (None, False))
            adapter.registrations = []
            ct["link_b"][0] = 20  # Hand support cannot masquerade as table support.
            self.assertEqual(adapter._failure_and_goal(ct), (None, False))
            ct["link_b"][0] = 30
            ring.velocity[0] = .1
            self.assertEqual(adapter._failure_and_goal(ct), (None, False))
            ring.velocity[0] = 0
            ring.pos[0] = .01  # Quiet on the table, still overlapping the assembly bounds.
            self.assertEqual(adapter._failure_and_goal(ct), (None, False))
            ring.pos[0] = 1
            ct["penetration"][0] = .002
            self.assertIn("penetration", adapter._failure_and_goal(ct)[0])
            ct["penetration"][0] = 0
            link.linking = lambda _: 0
            self.assertIn("connection lost", adapter._failure_and_goal(ct)[0])


if __name__ == "__main__":
    unittest.main()
