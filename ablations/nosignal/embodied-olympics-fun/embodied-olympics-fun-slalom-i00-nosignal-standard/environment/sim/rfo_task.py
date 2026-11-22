"""Illinois agility test: the 10 m x 5 m course with four centre cones 3.3 m apart; out and back, the weave up and
down through the centre cones, out and back again, without touching a cone, against the clock."""
import math

import numpy as np

from rfo.task import TaskBase
# A rigid cone (PVC; its shell's flex not modelled)'s contact with the robot, the venue's fixtures and the other props
# (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py
# SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the
# robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its own bounce.
# With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 74 mm into the robot's wrist and 39 mm
# into the floor (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

G1_FOOT_FRONT = 0.114            # m: the front end of the standing G1's feet ahead of its pelvis (measured)
# The prescribed path as the referee sees it: the crossings of the centre line (the line the four centre cones stand
# on) that the pelvis must make, in this order and no others. piece: "bottom" = the centre line beyond the first
# centre cone, on the start line's side; 1-2, 2-3, 3-4 = between two centre cones; "top" = beyond the fourth.
# direction: "LR" = from the left half (y > 0) to the right half, "RL" the other way.
WEAVE = [("bottom", "LR"), ("1-2", "RL"), ("2-3", "LR"), ("3-4", "RL"), ("top", "LR"),
         ("3-4", "RL"), ("2-3", "LR"), ("1-2", "RL"), ("bottom", "LR")]
STAGES = (["far-left cone"] + ["bottom cone, first time", "up 1-2", "up 2-3", "up 3-4", "top cone", "down 3-4",
                               "down 2-3", "down 1-2", "bottom cone, second time"] + ["far-right cone", "finish"])


def hull_points(m, g, n=400) -> np.ndarray:
    """The support points of mesh geom g (geom frame) along n fixed directions (a Fibonacci sphere)."""
    mid = int(m.geom_dataid[g])
    v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]].astype(float)
    i = np.arange(n) + 0.5
    phi, th = np.arccos(1 - 2 * i / n), math.pi * (1 + 5 ** 0.5) * i
    dirs = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]
    return v[np.unique(np.argmax(v @ dirs.T, axis=0))]


class Task(TaskBase):
    name = "slalom"
    title = "Illinois agility test"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("The Illinois Agility Test (Getchell 1979; the standard field test of agility): a course 10 m long "
                "and 5 m wide marked by four corner cones, four more cones on its centre line 3.3 m apart; the "
                "runner sprints up the left side and round the far-left cone, back to the centre cone on the start "
                "line, weaves up through the four centre cones and back down, sprints up the right side and round "
                "the far-right cone and back to the finish; a touched or knocked cone voids the trial")
    deviations = [
        "the start: the test starts lying face down behind the start line; the robot starts standing, the front "
        "ends of its feet {toe_gap_m} m behind the line, and the clock runs from t = 0 (no starter)",
        "the path is judged on the pelvis (which side of each cone it passes), the finish on the torso as in "
        "athletics (World Athletics TR 19: the leading point of the torso link's collision mesh on the line, "
        "interpolated between 1 ms physics steps)",
        "a fallen runner: a robot whose pelvis is below {down_z_m} m is down; it may get up and go on, but "
        "{down_limit_s} s down in a row end the attempt",
        "the qualifying time, {time_limit_s} s, is this benchmark's own round number: adult norms for this test are "
        "15 to 19 s",
    ]
    time_limit_s = 60.0
    start = (-(0.02 + G1_FOOT_FRONT), 1.9, 0.0)
    stages = STAGES
    fall_rule = False                # the run's own: a fallen runner may get up (the "down" rule)
    params = dict(length_m=10.0, width_m=5.0, cone_spacing_m=3.3, cone_radius_m=0.09, cone_height_m=0.23,
                  cone_mass_kg=0.25, toe_gap_m=0.02, down_z_m=0.40, down_limit_s=10.0)

    sentence = ("Run the Illinois agility course: up the left side and round the far-left cone, back to the centre "
                "cone on the start line, weave up through the four centre cones and back down, up the right side "
                "and round the far-right cone, and back over the finish line, without touching a cone.")
    rules = ("The course is {length_m} m long (x from 0 to {length_m} m) and {width_m} m wide, centred on y = 0: its "
             "left side line is half that width to the left of the centre line (y > 0), its right side line as far "
             "to the right. Corner cones stand where the side lines meet the start line x = 0 (the start cone on "
             "the left, the finish cone on the right) and the far line x = {length_m} m (the far-left and the "
             "far-right cone). Four centre cones stand on the centre line y = 0, the first on the start line and "
             "one every {cone_spacing_m} m after it. The cones are free ({cone_radius_m} m base radius, "
             "{cone_height_m} m high, {cone_mass_kg} kg). The clock starts at t = 0. The path, judged on your "
             "pelvis, in this order: (1) round the far-left cone: cross the left side line's continuation beyond "
             "the far line (x > {length_m} m), in either direction; (2) come back and go round the first centre "
             "cone on the start line's side: cross the centre line at x < 0 from the left half (y > 0) to the right "
             "half; (3) weave up: cross the centre line between the first and second centre cones from right to "
             "left, between the second and third from left to right, between the third and fourth from right to "
             "left; (4) go round the fourth centre cone: cross the centre line beyond it from left to right; "
             "(5) weave down: between the fourth and third from right to left, the third and second from left to "
             "right, the second and first from right to left; (6) go round the first centre cone again: cross the "
             "centre line at x < 0 from left to right; (7) round the far-right cone: cross the right side line's "
             "continuation beyond the far line (x > {length_m} m), in either direction; (8) finish: the leading "
             "point of your torso (not the head, arms, legs or feet) reaches the start line's plane x = 0 with your "
             "pelvis in the right half (y < 0). Any crossing of the centre line by your pelvis that is not the next "
             "one of this list, at any time, is leaving the prescribed path. You succeed when you finish within "
             "{time_limit_s} s of robot time. A fall does not end the attempt: you are down while your pelvis is below "
             "{down_z_m} m, you may get up and go on, but {down_limit_s} s down in a row end it. You fail if any "
             "part of you touches any of the eight cones, if you leave the prescribed path, when down for "
             "{down_limit_s} s, or after {time_limit_s} s.")
    venue = ("You stand at the start facing up the course (+x), 0.6 m to the right of the start cone, the front ends "
             "of your feet {toe_gap_m} m behind the start line (your pelvis at x = -0.13 m, y = +1.9 m). The cones "
             "are orange; the course's outline and its centre line are painted white on a level sports floor that "
             "goes on for several metres on every side.")
    difficulty = ("About 60 m of path with five turns round a cone and six changes of side between cones 3.3 m "
                  "apart, in {time_limit_s} s: the walking gait covers 38 m in that time, and the running gait "
                  "turns at most half a radian per second, so at speed it cannot follow the weave or round a cone.")

    def cones(self):
        p = self.p
        L, W, S = p["length_m"], p["width_m"] / 2, p["cone_spacing_m"]
        return {"start": (0.0, W), "far_left": (L, W), "far_right": (L, -W), "finish": (0.0, -W),
                **{f"centre{i + 1}": (i * S, 0.0) for i in range(4)}}

    def build(self, sc):
        p = self.p
        L, W = p["length_m"], p["width_m"] / 2
        sc.box("court", (L / 2, 0, 0.0003), (L / 2 + 5.0, W + 4.0, 0.0003), rgba=(0.76, 0.60, 0.42, 1))
        for i, (a, b) in enumerate((((0, -W), (0, W)), ((L, -W), (L, W)), ((0, W), (L, W)), ((0, -W), (L, -W)))):
            sc.line(f"outline{i}", a, b, width=0.05, z=0.0009)
        sc.line("centre_line", (0, 0), (3 * p["cone_spacing_m"], 0), width=0.03, rgba=(0.9, 0.9, 0.9, 0.6), z=0.0009)
        for name, (x, y) in self.cones().items():
            sc.cone(f"cone_{name}", x, y, radius=p["cone_radius_m"], height=p["cone_height_m"], mass=p["cone_mass_kg"])
        for g in sc.wb.iter("geom"):                         # the cones: rigid PVC at a contact (RIGID)
            if (g.get("name") or "").startswith("cone") and g.get("contype", "0") != "0":
                g.attrib.update(RIGID)
        sc.camera("venue", (L / 2, -10.5, 9.0), (L / 2, 0.0, 0.0), fovy=58)

    def reset(self, w):
        for name, (x, y) in self.cones().items():
            w.put(f"cone_{name}", (x, y, 0.0))

    def referee_reset(self, w, ref):
        m = w.m
        self.cone_mask = ref.geoms(prefix="cone_")
        self.robot = ref.part("robot")
        self.torso_geom = next(g for g in range(m.ngeom) if m.body(int(m.geom_bodyid[g])).name == "torso_link"
                               and m.geom_contype[g] and int(m.geom_dataid[g]) >= 0
                               and m.mesh(int(m.geom_dataid[g])).name.endswith("torso_link"))
        self.torso_pts = hull_points(m, self.torso_geom)
        # gate: how many of the path's twelve gates are done; prev: the pelvis (x, y) one physics step ago; back: the
        # torso's smallest x one physics step ago; down_k: down since when
        self.trackers = {"gate": 0, "prev": None, "back": None, "down_k": None}

    def torso_low_x(self, w) -> float:
        g = self.torso_geom
        R = w.d.geom_xmat[g].reshape(3, 3)
        return float(w.d.geom_xpos[g][0] + np.min(self.torso_pts @ R[0]))

    def _piece(self, x: float) -> str:
        S = self.p["cone_spacing_m"]
        return "bottom" if x < 0.0 else "1-2" if x < S else "2-3" if x < 2 * S else "3-4" if x < 3 * S else "top"

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        L, W = p["length_m"], p["width_m"] / 2
        if ref.touching(self.robot, self.cone_mask):
            cone = sorted(w.m.body(int(w.m.geom_bodyid[g])).name for g in np.flatnonzero(self.cone_mask)
                          if ref.touching(self.robot, np.arange(ref.ng) == g))
            return ref.fail("touched a cone", cone=cone[0][5:] if cone else None,
                            parts=sorted(ref.parts_touching(self.cone_mask)))
        q = w.d.xpos[w.robot.pelvis]
        x1, y1 = float(q[0]), float(q[1])
        prev, tr["prev"] = tr["prev"], [x1, y1]
        b0, b1 = tr["back"], self.torso_low_x(w)
        tr["back"] = b1
        if prev is None:
            return
        x0, y0 = prev
        n = tr["gate"]

        def cross(c):                                    # where the pelvis crossed the line y = c in this step
            if (y0 - c) * (y1 - c) > 0 or y0 == y1 or (y0 - c == 0):
                return None
            return x0 + (x1 - x0) * (c - y0) / (y1 - y0)

        xc = cross(0.0)
        if xc is not None:                               # a crossing of the centre line: it must be the next one
            got = (self._piece(xc), "LR" if y0 > 0.0 else "RL")
            if not 1 <= n <= len(WEAVE) or got != WEAVE[n - 1]:
                return ref.fail("left the prescribed path", crossed=f"centre line at {got[0]}, {got[1]}",
                                x=round(xc, 3), expected=self.stages[min(n, 11)])
            tr["gate"] = n = n + 1
            ref.stage(self.stages[n - 1], x=round(xc, 3))
        for gate, c in ((0, W), (10, -W)):               # the far corner cones
            xc = cross(c)
            if n == gate and xc is not None and xc > L:
                tr["gate"] = n = n + 1
                ref.stage(self.stages[n - 1], x=round(xc, 3))
        if n == 11 and b0 is not None and b0 > 0.0 >= b1 and y1 < 0.0:
            dt = w.m.opt.timestep
            t = ref.time - 2 * dt + b0 / (b0 - b1) * dt
            ref.metrics["time_s"] = round(t, 3)
            tr["gate"] = 12
            if ref.stage("finish", time_s=round(t, 3)):
                ref.succeed()
        ref.metrics["gates"] = tr["gate"]

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        z = float(w.pelvis()[2])
        if z < p["down_z_m"]:
            if tr["down_k"] is None:
                tr["down_k"] = w.k
                ref.event("down")
            elif (w.k - tr["down_k"]) * w.CONTROL_DT >= p["down_limit_s"]:
                ref.fail("did not finish: down for too long", down_s=p["down_limit_s"])
        elif tr["down_k"] is not None:
            tr["down_k"] = None
            ref.event("up")

    def privileged(self, w):
        n = self.trackers["gate"]
        return {"pelvis": w.pelvis().tolist(), "gates_done": n, "next": self.stages[min(n, 11)],
                "cones": {k: w.pos(f"cone_{k}").tolist() for k in self.cones()}}
