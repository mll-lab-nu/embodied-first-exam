#!/usr/bin/env python3
"""Slotted rigid-chain settings (slotted_post_ring_{hard,medium,easy}_chain): registration, the resolved simulator
settings and grasp assist (the ones the oracle's trajectories were recorded with), the chain's geometry; with the
simulator (genesis), the reset's fixed state S0 and a short replay's determinism."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'harbor_templates/topogym/common')]
import rcb_topogym
from topogym.config.registry import task_definition

RING_MAJOR_RADIUS_M = dict(hard=.061, medium=.0625, easy=.064)
RECORDED = dict(compute_backend="cpu", precision="64", solver_substeps=1, reset_physics_steps=800)


def chain(tier):
    return f"slotted_post_ring_{tier}_chain"


def config(variation):
    return rcb_topogym.simulator_config("slotted_post_ring", variation_id=variation, seed=0)


class Registration(unittest.TestCase):
    def test_the_settings_differ_only_in_the_ring(self):
        hard = task_definition("slotted_post_ring", chain("hard"))().config
        for tier, radius in RING_MAJOR_RADIUS_M.items():
            task = task_definition("slotted_post_ring", chain(tier))()
            geometry = dict(task.config["geometry"])
            self.assertEqual((geometry.pop("ring_major_radius_m"), geometry["slot_width_m"]), (radius, .034))
            self.assertEqual(geometry, {k: v for k, v in hard["geometry"].items() if k != "ring_major_radius_m"})
            self.assertEqual({k for k in task.config if task.config[k] != hard[k]}, set() if tier == "hard" else {"geometry"})
            self.assertEqual((task.physics_model, task.model_revision), ("rigid_articulated", "chain88_v6"))

    def test_the_geometry_cannot_be_overridden(self):
        with self.assertRaises(ValueError):
            task_definition("slotted_post_ring", chain("hard"))({"geometry": {"slot_width_m": .028}})


class SimulatorSettings(unittest.TestCase):
    def test_the_chain_settings_resolve_to_the_recorded_ones(self):
        for tier in RING_MAJOR_RADIUS_M:
            with self.subTest(tier=tier):
                cfg = config(chain(tier))
                self.assertEqual({k: cfg[k] for k in RECORDED}, RECORDED)
                self.assertEqual(cfg["rigid_options"], {})            # the contact island is not changed
                self.assertFalse(cfg.get("ipc_options"))
                assist = cfg["grasp_assist"]
                self.assertEqual((assist["model"], assist["max_tcp_distance_m"]), ("contact_weld_v1", .09))
                self.assertEqual([(t["entity"], t["link"]) for t in assist["targets"]], [("slotted_chain", "ring")])

    def test_the_below_easy_chain_settings_are_unchanged(self):
        for name in ("very_easy", "easier"):
            with self.subTest(name=name):
                cfg = config(f"slotted_post_ring_{name}")
                self.assertEqual((cfg["compute_backend"], cfg["precision"], cfg["reset_physics_steps"]), ("cpu", "64", 1200))
                self.assertEqual(cfg["rigid_options"], {"use_contact_island": False})
                links = [t["link"] for t in cfg["grasp_assist"]["targets"]]
                self.assertEqual(links[-1], "target_ring")
                self.assertTrue(links[:-1] and all(link.startswith("link_") for link in links[:-1]))

    def test_the_fem_settings_are_unchanged(self):
        cfg = config("slotted_post_ring_hard")
        self.assertTrue(cfg["ipc_options"])
        self.assertIn(cfg.get("grasp_assist", {}).get("model", "none"), (None, "none"))


class ChainGeometry(unittest.TestCase):
    def test_the_chain_has_equal_links_from_eye_to_eye(self):
        from topogym.assets.geometry.slotted_chain import LINKS, chain_points
        for tier in RING_MAJOR_RADIUS_M:
            points = chain_points(task_definition("slotted_post_ring", chain(tier))().make_layout())
            chords = np.linalg.norm(np.diff(points, axis=0), axis=1)
            self.assertEqual(len(points), LINKS+1)
            self.assertLess(float(np.ptp(chords)), 1e-9)


@unittest.skipUnless(importlib.util.find_spec("genesis"), "needs the simulator (genesis)")
class Physics(unittest.TestCase):
    def test_the_reset_is_s0_and_a_replay_is_deterministic(self):
        from topogym.planning.slotted_post_ring.chain import states
        from topogym.planning.slotted_post_ring.chain.session import build_session, scene
        session = build_session(chain("hard"))
        lay = session.env._task.layout
        s = scene(session)
        self.assertEqual(len(states.slot_crossings(s.points, lay)), 1)          # the cord once through the slot,
        self.assertEqual(states.ring_crossings(s.points, s.poses["ring"], lay), [])   # not through the ring,
        self.assertTrue(states.ring_on_post(s.poses["ring"], lay))             # which lies round the post
        rows = np.repeat(np.asarray(session.hold_action(), np.float32)[None], 40, axis=0)
        first, second = session.replay(rows), session.replay(rows)
        self.assertLess(scene(session).speed_m_s, .02)
        self.assertEqual(first["state_sha"], second["state_sha"])


if __name__ == "__main__":
    unittest.main()
