"""STEGESUND roll stand mechanism: the shared seat weld (seat_weld.py) on the four threaded bolts.

Each bolt (bolt_1..4) screws through the clamped leg (half_A / half_B) into its threaded nut in the shelf rail
(geoms shelf/nut_<seat>_*: thread capsules). seat_weld.SeatWelder welds a bolt to the shelf (and its clamped half to
the shelf) once the bolt has seated: its head touches, and it has stopped relative to the shelf for 0.05 s; then the
bolt's geoms and its nut's thread geoms stop colliding. task.json['fasteners'] lists the bolts.

Arming (seat_weld.py: a fastener lying head-down on the table looks seated, so it is only checked once armed): the
demo armed a bolt when its drive started; here a bolt is armed at the first contact between its geoms and its own
nut's thread geoms, i.e. once it is in its hole and its thread has engaged. Nothing else differs from the shared
module: welds and contact switches happen in SeatWelder.step() after every physics step.
"""
import copy
import numpy as np
import mujoco
import seat_weld


class StegesundMechanism:
    def __init__(self, model, data, task):
        self.m, self.d, self.task = model, data, task
        m = model
        fs, self.arm_geoms = [], {}
        for b, f in sorted(task["fasteners"].items()):
            holes = [m.geom(g).name for g in range(m.ngeom) if m.geom(g).name.startswith(f["thread_holes_prefix"])]
            fs.append(seat_weld.Fastener(b, b, f["host"], thread_holes=holes, head_geoms=list(f["head_geoms"]),
                                         clamped=list(f["clamped"]), armed=False))
            own = np.array([g for g in range(m.ngeom) if m.geom_bodyid[g] == m.body(b).id])
            self.arm_geoms[b] = (own, np.array([m.geom(h).id for h in holes]))
        self.welder = seat_weld.SeatWelder(model, data, fs)
        self._orig = (m.eq_data.copy(), m.geom_contype.copy(), m.geom_conaffinity.copy())
        self.arm_events = []

    def reset(self):
        eq, ct, ca = self._orig
        self.m.eq_data[:] = eq
        self.m.geom_contype[:] = ct
        self.m.geom_conaffinity[:] = ca
        for f in self.welder.f:
            f.armed, f.welded, f.quiet_since = False, False, None
        self.welder.events = []
        self.arm_events = []

    def _arm(self):
        c = self.d.contact[: self.d.ncon]
        if not len(c):
            return
        for f in self.welder.f:
            if f.armed or f.welded:
                continue
            own, holes = self.arm_geoms[f.name]
            hit = (np.isin(c.geom1, own) & np.isin(c.geom2, holes)) | (np.isin(c.geom2, own) & np.isin(c.geom1, holes))
            if hit.any():
                self.welder.arm(f.name)
                self.arm_events.append({"time": float(self.d.time), "fastener": f.name})

    def update(self):
        self._arm()
        self.welder.step()

    def status(self):
        return {f.name: {"armed": bool(f.armed), "welded": bool(f.welded)} for f in self.welder.f}

    def state(self):
        return dict(eq_data=self.m.eq_data.copy(), contype=self.m.geom_contype.copy(),
                    conaffinity=self.m.geom_conaffinity.copy(), events=copy.deepcopy(self.welder.events),
                    arm_events=copy.deepcopy(self.arm_events),
                    fasteners=[(f.name, f.armed, f.welded, f.quiet_since) for f in self.welder.f])

    def set_state(self, s):
        self.m.eq_data[:] = s["eq_data"]
        self.m.geom_contype[:] = s["contype"]
        self.m.geom_conaffinity[:] = s["conaffinity"]
        self.welder.events = copy.deepcopy(s["events"])
        self.arm_events = copy.deepcopy(s["arm_events"])
        for f, (name, armed, welded, quiet) in zip(self.welder.f, s["fasteners"]):
            assert f.name == name
            f.armed, f.welded, f.quiet_since = armed, welded, quiet
