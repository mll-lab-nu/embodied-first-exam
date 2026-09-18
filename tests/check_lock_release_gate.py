"""A release must wait for both actual aperture and disappearing contact."""
from types import SimpleNamespace
import unittest
import numpy as np

from topogym.tasks.lock_picking.runner import open_before_withdrawal


class Controller:
    def __init__(self, stuck=False):
        self.steps=0
        self.stuck=stuck
        self.cfg=SimpleNamespace(gripper=SimpleNamespace(open_qpos=.04))
        self.robot=SimpleNamespace(get_contacts=self.contacts)

    def open_gripper(self, steps):
        self.step(steps)

    def step(self, steps):
        self.steps+=steps

    def gripper_qpos(self):
        return np.array([.04,.04]) if self.steps>=10 else np.array([.025,.025])

    def contacts(self, with_entity):
        # The entity interface reports force_a/force_b, unlike collider.force.
        return {"force_a":np.array([[.1,0,0]]) if self.stuck or self.steps<20 else np.empty((0,3))}


class ReleaseChecks(unittest.TestCase):
    def test_open_aperture_alone_does_not_release_motion(self):
        c=Controller();status={}
        task=SimpleNamespace(scene=SimpleNamespace(dt=.005),key=object(),layout=SimpleNamespace(handle_radius=.018))
        open_before_withdrawal(task,c,status)
        self.assertGreaterEqual(c.steps,39)
        self.assertEqual(status['phase'],'release_withdraw')
        self.assertEqual(status['release_robot_key_force_N'],0.)

    def test_persistent_contact_times_out(self):
        c=Controller(stuck=True)
        task=SimpleNamespace(scene=SimpleNamespace(dt=.005),key=object(),layout=SimpleNamespace(handle_radius=.018))
        with self.assertRaisesRegex(RuntimeError,'did not physically open'):
            open_before_withdrawal(task,c,{})
        self.assertEqual(c.steps,1600)


if __name__=='__main__':unittest.main()
