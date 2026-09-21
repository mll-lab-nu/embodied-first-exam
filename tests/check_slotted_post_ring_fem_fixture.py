"""Check FEM recording gates against real initialized and deliberately invalid states."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import tempfile
import unittest

import mujoco
import numpy as np

from topogym.tasks.slotted_post_ring.archive import publication_allowed
from topogym.tasks.slotted_post_ring.fem import FEMSettings, build_model
from topogym.tasks.slotted_post_ring.fem_fixture import VolumeAudit, minimum_jerk, execute, rotational_gains
from scipy.spatial.transform import Rotation
from topogym.tasks.slotted_post_ring.geometry import SlottedPostLayout


class FEMRecordingChecks(unittest.TestCase):
    def test_bead_orientation_control_converges_at_recording_timestep(self):
        model = mujoco.MjModel.from_xml_string('''<mujoco>
          <option timestep=".001" gravity="0 0 0"/>
          <worldbody><body name="bead_right"><freejoint/>
            <geom type="sphere" size=".0195" mass=".01843857"/>
          </body></worldbody></mujoco>''')
        data = mujoco.MjData(model)
        target = Rotation.from_rotvec([.3, -.2, .1])
        kp, kd = rotational_gains(model, 1, 'bead_right')
        for _ in range(1000):
            mujoco.mj_forward(model, data)
            current = Rotation.from_quat(data.xquat[1][[1, 2, 3, 0]])
            error = (target*current.inv()).as_rotvec()
            velocity = np.zeros(6)
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, 1, velocity, 0)
            data.xfrc_applied[1, 3:] = kp*error-kd*velocity[:3]
            mujoco.mj_step(model, data)
        self.assertLess(np.linalg.norm(error), 1e-5)
        self.assertLess(np.linalg.norm(velocity), 1e-4)
        self.assertFalse(any(w.number for w in data.warning))

    def test_streamed_stages_preserve_simulation_time_and_cannot_publish_a_partial_task(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            report=execute(Path(temp)/'run',iter([['first',.001,{}],['second',.001,{}]]),
                           FEMSettings(),SlottedPostLayout(),initial_seconds=0.)
            self.assertAlmostEqual(report['simulated_seconds'],.002,places=10)
            self.assertEqual(len(report['stages']),2)
            self.assertTrue(report['checks']['completed_schedule'])
            self.assertTrue(report['continuous_episode'])
            self.assertFalse(report['full_process_demo'])
            self.assertFalse(publication_allowed(report))

    def test_interpolation_roundoff_stays_inside_slerp_domain(self):
        for u in np.r_[np.linspace(0.,1.,1001), 1.-1e-12, 1.+1e-12]:
            position, speed = minimum_jerk(u, 1.2)
            self.assertGreaterEqual(position, 0.)
            self.assertLessEqual(position, 1.)
            self.assertGreaterEqual(speed, 0.)
        self.assertEqual(minimum_jerk(1.000000001,1.2), (1., 0.))

    def test_probes_failed_and_partial_runs_cannot_be_published(self):
        for report in ({'passed': True, 'scope': 'gravity'},
                       {'passed': False, 'full_process_demo': True},
                       {'passed': True, 'full_process_demo': True, 'continuation': {'checkpoint': 'probe.npz'}},
                       {'passed': True, 'full_robot_demo': False}):
            self.assertFalse(publication_allowed(report))
        self.assertTrue(publication_allowed({'passed': True, 'full_process_demo': True}))

    def test_inversion_and_unreleased_tail_fail_auditing(self):
        with tempfile.TemporaryDirectory() as temp:
            model, data, spec = build_model(Path(temp)/'model')
            with np.load(Path(temp)/'model/fem_mesh.npz') as mesh:
                audit = VolumeAudit(model, mesh, spec)
                audit.observe(data, False)
                self.assertTrue(audit.checks()['finite_no_inversion'])
                data.time = 2.
                audit.observe(data, False)
                self.assertFalse(audit.tail_checks()[0]['last_two_seconds_released'])
                data.flexvert_xpos[mesh['elements'][0, 0]] = data.flexvert_xpos[mesh['elements'][0, 1]]
                audit.observe(data, True)
                self.assertFalse(audit.checks()['positive_volume_margin'])


if __name__ == '__main__':
    unittest.main()
