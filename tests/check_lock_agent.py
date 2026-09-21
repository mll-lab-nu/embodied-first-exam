"""Public lock contract, continuous rotor and terminal guard regressions."""
import json
from types import SimpleNamespace as NS
import unittest
import numpy as np

from topogym.agent_bridge.registry import factory_for
from topogym.agent_bridge.robot_adapter import StableVerdict
from topogym.tasks.hedgehog_in_cage.agent_adapter import HedgehogAdapter
from topogym.tasks.lock_picking.agent_adapter import LockPickingAdapter, configuration
from topogym.tasks.lock_picking.agent_spec import describe_task
from topogym.tasks.lock_picking._staged_lock_geometry import LockGeometry, variant_geometry


class LockAgentChecks(unittest.TestCase):
    def setUp(self):
        self.cfg = configuration()

    def test_public_description_does_not_expose_slot_or_solution_parameters(self):
        before = describe_task(self.cfg)
        self.cfg.task.geometry.slots = [[123.], [124.], [125.]]
        self.cfg.task.geometry.initial_disc_deg = [99., 98., 97.]
        self.cfg.task.motion.strategy = "private_solution"
        self.assertEqual(before, describe_task(self.cfg))
        text = json.dumps(before)
        for private in ("disc_deg", "key_tip_pos", "limited_two_retreats", "private_solution", "slots", "oracle"):
            self.assertNotIn(private, text)
        self.assertEqual(before["cameras"], ["agentview", "front_oblique", "wrist"])
        self.assertFalse(before["perception"]["reference_images_provided"])
        self.assertIs(LockPickingAdapter.step, HedgehogAdapter.step)
        self.assertEqual(factory_for("lock_picking", "cpu", "rasterizer").func.__module__,
                         "topogym.tasks.lock_picking.agent_adapter")
        self.assertEqual(self.cfg.task.initialization.spawn_clearance, 0.)

    def adapter(self):
        a = LockPickingAdapter.__new__(LockPickingAdapter)
        self.state = dict(depth=4., key_deg=0., key_tip_pos=[.65,.2,1.105], key_quat=[1.,0.,0.,0.],
            axis_offset=0., axis_tilt_deg=0., disc_deg=[0.,60.,0.], disc_speed=[0.,0.,0.],
            linear_speed=0., angular_speed=0.)
        a.task = NS(state=lambda:self.state, cfg=self.cfg.task,
            layout=variant_geometry(LockGeometry.from_config(self.cfg.task.geometry), "limited_two_retreats", 0),
            key=NS(base_link_idx=10), tabletop=NS(frames=NS(table_surface_origin=[0.,0.,.9196429])),
            max_key_contact_force=0., max_contact_penetration=0., geometry_error_steps=0,
            force_limit_triggered=False)
        a.fixed, a.registrations = [], []
        a.robotlinks, a.fixtures = {20,21}, {30,31}
        self.contacts = dict(link_a=np.array([10]), link_b=np.array([30]),
            force=np.array([[0.,0.,1.]]), penetration=np.array([0.]))
        return a

    def test_goal_requires_end_alignment_release_and_no_hand_support(self):
        a=self.adapter()
        self.assertEqual(a._failure_and_goal(self.contacts), (None, True))
        a.registrations=[(20,10)]
        self.assertEqual(a._failure_and_goal(self.contacts), (None, False))
        a.registrations=[]
        self.contacts["link_b"][0]=20
        self.assertEqual(a._failure_and_goal(self.contacts), (None, False))
        self.contacts["link_b"][0]=30
        for field,value in (("depth",3.9),("axis_offset",.02),("axis_tilt_deg",4.),
                            ("linear_speed",.011),("angular_speed",.11)):
            old=self.state[field]
            self.state[field]=value
            self.assertEqual(a._failure_and_goal(self.contacts),(None,False),field)
            self.state[field]=old

    def test_pickup_off_axis_not_falsely_rejected_as_slot_interference(self):
        a=self.adapter()
        self.state["disc_deg"]=[0.,0.,0.]
        self.assertIn("interference",a._failure_and_goal(self.contacts)[0])
        self.state["axis_offset"] = .1
        self.assertEqual(a._failure_and_goal(self.contacts),(None,False))

    def test_continuous_rotor_can_rotate_beyond_one_turn(self):
        a=self.adapter()
        self.state["disc_deg"][2]=720.
        self.assertEqual(a._failure_and_goal(self.contacts),(None,True))
        self.state["disc_deg"][0]=16.
        self.assertIn("stop range",a._failure_and_goal(self.contacts)[0])

    def test_force_penetration_and_direct_robot_contact_fail(self):
        a=self.adapter()
        self.contacts["force"][0,2]=10.1
        self.assertIn("10 N",a._failure_and_goal(self.contacts)[0])
        self.assertTrue(a.task.force_limit_triggered)
        a=self.adapter()
        self.contacts["penetration"][0]=.0021
        self.assertIn("2 mm",a._failure_and_goal(self.contacts)[0])
        a=self.adapter()
        self.contacts["link_a"][0]=20
        self.assertIn("directly",a._failure_and_goal(self.contacts)[0])

    def test_fixed_base_fall_and_nonfinite_state(self):
        a=self.adapter()
        a.fixed=[(NS(get_pos=lambda:np.array([.1,0.,0.]),get_quat=lambda:np.array([1.,0.,0.,0.])),
                  np.zeros(3),np.array([1.,0.,0.,0.]))]
        self.assertIn("base moved",a._failure_and_goal(self.contacts)[0])
        a.fixed=[]
        self.state["key_tip_pos"][2]=.7
        self.assertIn("fell",a._failure_and_goal(self.contacts)[0])
        self.state["key_tip_pos"][2]=float("nan")
        self.assertIn("Non-finite",a._failure_and_goal(self.contacts)[0])

    def test_shared_step_latches_force_stop_without_losing_terminal_tick(self):
        a=self.adapter()
        self.contacts["force"][0,2]=11.
        a.scene=NS(step=lambda:None,dt=.005)
        a.ctrl=NS(arms={"arm":NS(arm_qpos=lambda:np.zeros(7))})
        a.targets={"arm":np.zeros(7)}
        a.tick,a.tracking_ticks=0,0
        a._contacts=lambda:self.contacts
        a.verdict=StableVerdict(.005)
        a.step({})
        self.assertEqual(a.tick,1)
        self.assertEqual(a._evaluate()["status"],"failed")
        self.assertIn("10 N",a._evaluate()["reason"])
        self.assertEqual(a.verdict.update(2,True)["status"],"failed")


if __name__ == "__main__":
    unittest.main()
