"""EKET steps 1-4 success criteria (port of the source grader).

The source EketGrader passes when ALL of:
  ordered_operations          the seven operations were measured in the source order
                              side_a_entry, side_a_slide, side_b_entry, side_b_slide, back_slide,
                              bottom_entry, bottom_slide
  measured_gates              each one passes the frozen source gate (eket_ops.MotionGate) on independent
                              measurements of the panel relative to the TOP frame: goal error <= 0.8 mm
                              (side slides 0.25 mm, bottom_slide 0.5 mm), angle <= 1 deg (slides 0.1 deg),
                              relative speed < 0.012 m/s, angular speed < 0.1 rad/s, travel along the
                              start->goal axis >= 14 mm (entries) / 8 mm (slides) / 0.30 m (back), >= 3
                              contact samples >= 0.015 N with every counterpart panel within 4 mm of the
                              goal, held for 12 source steps (slides 24); slides also need < 0.05 mm and
                              < 0.02 deg at acceptance; bottom_slide needs a 1 s pose window (range
                              <= 0.2 mm, drift <= 0.05 mm, max error <= 0.5 mm, speed < 0.012 m/s);
                              back_slide cannot be accepted within 1.05 s of first coming within 2 mm.
  finite_five_panels          five finite panel states
  four_physical_frame_joints  exactly the four source frame joints (side_a, side_b, bottom_a, bottom_b)
                              are physically enabled (MuJoCo weld equalities joint_*).
Added for this port (the source endpoint is held by its force fixture; here the cabinet must stand alone):
  released                    no external force/torque applied to any panel (xfrc_applied, qfrc_applied)
                              and no robot contact with any panel
  resting_on_table            at least one panel touches the table top, no panel touches the floor, and
                              every panel moves slower than 0.01 m/s and 0.05 rad/s
The monitor runs its own OpTracker (independent of the latch mechanism's tracker), like the source
grader's independent replay of the measurement journal.  Robot handling is allowed throughout (the
source has no release requirement for this step-4 endpoint).
"""
import numpy as np
from eket_ops import OpTracker, OPERATIONS, JOINT_PAIRS, Measure

class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t = model, data, task
        self.tracker = OpTracker(model, data, task['canonical_in_cabinet_frame'])
        self.eq = {j: model.equality('joint_' + j).id for j in JOINT_PAIRS}
        self.meas = Measure(model, data)
        self.parts = [model.body(r).id for r in task['parts']]
        self.robot = set(i for i in range(model.nbody) if model.body(i).name.startswith(('left_', 'right_')))
        self.table = model.geom('table_top').id; self.floor = model.geom('floor').id
        self.reset()

    def _released_resting(self):
        m, d = self.m, self.d
        dofs = [m.jnt_dofadr[m.body_jntadr[b]] for b in self.parts]
        released = bool(np.all(d.xfrc_applied[self.parts] == 0) and all(np.all(d.qfrc_applied[a:a + 6] == 0) for a in dofs))
        on_table = False; on_floor = False; part = set(self.parts)
        for i in range(d.ncon):
            c = d.contact[i]; b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
            if (b1 in part and b2 in self.robot) or (b2 in part and b1 in self.robot):
                released = False
            if self.table in (c.geom1, c.geom2) and (b1 in part or b2 in part): on_table = True
            if self.floor in (c.geom1, c.geom2) and (b1 in part or b2 in part): on_floor = True
        still = True
        for b in self.parts:
            v = np.zeros(6); import mujoco; mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
            still &= bool(np.linalg.norm(v[3:]) < 0.01 and np.linalg.norm(v[:3]) < 0.05)
        return released, bool(on_table and not on_floor and still)

    def reset(self):
        self.tracker.reset()

    def update(self):
        self.tracker.update()

    def state(self):
        return self.tracker.state()

    def set_state(self, s):
        self.tracker.set_state(s)

    def report(self):
        names = [r['name'] for r in self.tracker.records]
        joints = {j for j, i in self.eq.items() if self.d.eq_active[i]}
        checks = dict(ordered_operations=names == list(OPERATIONS),
                      measured_gates=len(names) == 7 and all(r['passed'] for r in self.tracker.records),
                      finite_five_panels=self.meas.finite(),
                      four_physical_frame_joints=joints == set(JOINT_PAIRS))
        checks['released'], checks['resting_on_table'] = self._released_resting()
        return dict(success=all(checks.values()), checks=checks, operations=self.tracker.records,
                    status=self.tracker.status(), active_frame_joints=sorted(joints),
                    scope='steps-1-4', full_manual_completion=False)
