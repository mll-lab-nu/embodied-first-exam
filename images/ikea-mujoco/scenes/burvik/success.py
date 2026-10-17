"""BURVIK success criteria (self-contained; used through scene.load().success()).

Port of the source endpoint grader with the source's acceptance gates:
  * assembled geometry, for every non-root part (leg_0..3, handle), measured in the top's frame:
      target = top pose * (manifest centre - top centre), axis = top * op.axis,
      |gap| <= 0.8 mm, lateral <= 1 mm, tilt <= 2 deg (legs: thread axis; handle: full rotation),
      relative speed < 0.025 m/s, handle: both rod ends within 1 mm laterally of the two top holes;
  * required model joints: all five retention welds (legs and handle to the top) engaged
    (mechanism.py; the source's fixed connection joints);
  * no joint on the root; no world fixture left enabled (this port has no world fixtures);
  * final upright orientation of the top within 2 deg.
Deviations: the source's upright test is angle(top quaternion, identity) < 2 deg, i.e. it also fixes
the world yaw (its turns are pure rotations about world x); here only the tilt of the top's normal
from world +z counts, because the bench yaw has no meaning for the task. Speeds are relative
velocities of the same material point (the part frame origin). As in the source ("held-top
scope"), floor support is not required: the top may still be held by a robot.
Endpoint only, like the source: success() evaluates the current state.
"""
import numpy as np
from ikea_runtime import Helpers, rotate, qmul, qinv, axis_angle_deg, quat_angle_deg
from mechanism import rel_point_speed

class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.t, self.scene = model, data, task, scene
        self.h = Helpers(model, data)
        self.acc = task['acceptance']
        self.ops = {o['part']: o for o in task['operations'] if not o['mode'].startswith('turn')}
        self.c = {n: np.array(v) for n, v in task['centers'].items()}
        self.root = task['root']
        self.reset()

    def reset(self): pass
    def update(self): pass
    def state(self): return {}
    def set_state(self, s): pass

    def evaluate(self):
        g = self.acc; root = self.root
        pt, qt = self.h.pose(root)
        rep = dict(geometry={}, failures=[])
        passed = []
        for n, op in self.ops.items():
            pp, qp = self.h.pose(n)
            target = pt + rotate(qt, self.c[n] - self.c[root]); axis = rotate(qt, op['axis'])
            dl = pp - target; gap = float(dl @ axis); lat = float(np.linalg.norm(dl - gap * axis))
            if op['mode'] == 'thread':
                tilt = axis_angle_deg(rotate(qp, op['axis']), axis)
            else:
                tilt = quat_angle_deg(qp, qt)
            speed = rel_point_speed(self.m, self.d, n, root)
            holes = 0.
            if n == 'handle':
                for p in ((-.12, .09, .44), (.12, -.09, .44)):
                    a = pp + rotate(qp, np.array(p) - self.c[n]); b = pt + rotate(qt, np.array(p) - self.c[root])
                    v = a - b; holes = max(holes, float(np.linalg.norm(v - (v @ axis) * axis)))
            ok = (abs(gap) <= g['gap_m'] and lat <= g['lateral_m'] and tilt <= g['axis_deg'] and speed < g['linear_speed']
                  and holes <= g['lateral_m'])
            passed.append(ok)
            rep['geometry'][n] = dict(gap_m=gap, lateral_m=lat, axis_deg=tilt, speed_m_s=speed, two_hole_error_m=holes, passed=bool(ok))
            if not ok: rep['failures'].append('geometry:' + n)
        mech = self.scene.mech if self.scene is not None else None
        joints = {o['part']: (mech.active(o['key']) if mech else False) for o in self.t['mechanism_operations']}
        if not all(joints.values()): rep['failures'].append('missing_required_model_joint')
        tilt_top = axis_angle_deg(rotate(qt, [0, 0, 1]), [0, 0, 1])
        upright = tilt_top < self.t['upright']['axis_deg']
        if not upright: rep['failures'].append('final_upright_orientation')
        rep.update(geometry_fraction=sum(passed) / len(passed), joint_fraction=sum(joints.values()) / len(joints),
                   joints=joints, top_tilt_deg=tilt_top, support=bool(upright),
                   mechanism=dict(mech.metrics) if mech else {})
        rep['success'] = bool(all(passed) and all(joints.values()) and upright and not rep['failures'])
        return rep

    def report(self):
        return self.evaluate()
