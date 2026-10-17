"""UPPSTA hammering block mechanism, as the source tree's demo runs it (demo/core.py Sim.row, the scene's per-tick step):
the shared seat weld (seat_weld.py) on the two screws, a state rule that arms each screw's weld, and mj_forward after
every 8th physics step (one 2.5 ms tick = 8 steps of 0.3125 ms).

  - screw_a / screw_b thread into board ends a / b (internal-thread geoms board_thread_<a|b>_*); the head (geoms
    <screw>_head_0..29) clamps end block a / b. seat_weld.SeatWelder welds a screw to the board (and its end block to
    the board) once its head touches and it has stopped relative to the board for 0.05 s; then the screw and its
    hole's thread stop colliding.
  - Arming (state rule of the source, evaluated after every physics step): a screw is armed once its origin is within
    1 mm of its hole's axis, 0 to 3 mm above its seat (under-head plane at |x| = 120.5 mm in the board frame), and its
    axis within 5 deg of the hole's.
  - Each physics step: mj_step, then (update()) the arming rule, then the welder; after every 8th step mj_forward,
    as the source's per-row step does. A control row of the task is 4 physics steps, so this falls after every second
    row.
"""
import copy
import numpy as np
import mujoco
import seat_weld

SCREWS = {"screw_a": +1, "screw_b": -1}      # sign of the board end (board frame x) the screw goes into
SEAT_X = 0.1205                             # under-head plane of a seated screw, board frame |x| (m)
ARM_ABOVE_SEAT = 0.003                      # armed only in the last 3 mm
FORWARD_EVERY = 8                           # physics steps per source tick (2.5 ms)


class UppstaMechanism:
    def __init__(self, model, data, task):
        self.m, self.d, self.task = model, data, task
        m = model
        fs = []
        for s in SCREWS:
            hole = s[-1]
            fs.append(seat_weld.Fastener(name=s, body=s, host="board",
                                         thread_holes=[m.geom(g).name for g in range(m.ngeom)
                                                       if m.geom(g).name.startswith(f"board_thread_{hole}_")],
                                         head_geoms=[f"{s}_head_{i}" for i in range(30)],
                                         clamped=[f"end_block_{hole}"], armed=False))
        self.welder = seat_weld.SeatWelder(model, data, fs)
        self.bid = {n: m.body(n).id for n in ["board"] + list(SCREWS)}
        self._orig = (m.eq_data.copy(), m.geom_contype.copy(), m.geom_conaffinity.copy())
        self.events = []
        self.k = 0

    def reset(self):
        eq, ct, ca = self._orig
        self.m.eq_data[:] = eq
        self.m.geom_contype[:] = ct
        self.m.geom_conaffinity[:] = ca
        for f in self.welder.f:
            f.armed, f.welded, f.quiet_since = False, False, None
        self.welder.events = []
        self.events = []
        self.k = 0

    def arm_rule(self):
        d = self.d
        for f in self.welder.f:
            if f.armed or f.welded:
                continue
            b, h = self.bid[f.name], self.bid["board"]
            Rb = d.xmat[h].reshape(3, 3)
            p = Rb.T @ (d.xpos[b] - d.xpos[h])
            ax = Rb.T @ d.xmat[b].reshape(3, 3)[:, 2]
            sx = SCREWS[f.name]
            if (np.hypot(p[1], p[2]) < 1e-3 and 0 <= sx * p[0] - SEAT_X <= ARM_ABOVE_SEAT
                    and sx * ax[0] > np.cos(np.radians(5))):
                self.welder.arm(f.name)
                self.events.append(dict(time=float(d.time), arm=f.name))

    def update(self):
        self.arm_rule()
        for ev in self.welder.step():
            self.events.append(dict(ev))
        self.k += 1
        if self.k % FORWARD_EVERY == 0:
            mujoco.mj_forward(self.m, self.d)

    def status(self):
        return {f.name: {"armed": bool(f.armed), "welded": bool(f.welded)} for f in self.welder.f}

    def state(self):
        return dict(eq_data=self.m.eq_data.copy(), contype=self.m.geom_contype.copy(),
                    conaffinity=self.m.geom_conaffinity.copy(), welder_events=copy.deepcopy(self.welder.events),
                    events=copy.deepcopy(self.events), k=self.k,
                    fasteners=[(f.name, f.armed, f.welded, f.quiet_since) for f in self.welder.f])

    def set_state(self, s):
        self.m.eq_data[:] = s["eq_data"]
        self.m.geom_contype[:] = s["contype"]
        self.m.geom_conaffinity[:] = s["conaffinity"]
        self.welder.events = copy.deepcopy(s["welder_events"])
        self.events = copy.deepcopy(s["events"])
        self.k = int(s["k"])
        for f, (name, armed, welded, quiet) in zip(self.welder.f, s["fasteners"]):
            assert f.name == name
            f.armed, f.welded, f.quiet_since = armed, welded, quiet
