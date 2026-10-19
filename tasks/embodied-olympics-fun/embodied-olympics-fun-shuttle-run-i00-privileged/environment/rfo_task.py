"""4 x 10 m shuttle run (the school fitness test): four legs between two lines 10 m apart, a foot on the ground beyond
the line at each of the three turns, the torso over the start line at the end, against the clock."""
import math

import numpy as np

from rfo.task import TaskBase

SIDES = ("left", "right")
G1_FOOT_FRONT = 0.114            # m: the front end of the standing G1's feet ahead of its pelvis (measured)


def span(w, ids, axis):
    """The extent of the geoms `ids` along a unit vector (their oriented bounding boxes)."""
    m, d = w.m, w.d
    ax = np.asarray(axis, float)
    R = d.geom_xmat[ids].reshape(-1, 3, 3)
    c = d.geom_xpos[ids] + np.einsum("gij,gj->gi", R, m.geom_aabb[ids, :3])
    half = np.sum(np.abs(np.einsum("i,gij->gj", ax, R)) * m.geom_aabb[ids, 3:], axis=1)
    p = c @ ax
    return float(np.min(p - half)), float(np.max(p + half))


def hull_points(m, g, n=400) -> np.ndarray:
    """The support points of mesh geom g (geom frame) along n fixed directions (a Fibonacci sphere)."""
    mid = int(m.geom_dataid[g])
    v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]].astype(float)
    i = np.arange(n) + 0.5
    phi, th = np.arccos(1 - 2 * i / n), math.pi * (1 + 5 ** 0.5) * i
    dirs = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]
    return v[np.unique(np.argmax(v @ dirs.T, axis=0))]


class Task(TaskBase):
    name = "shuttle-run"
    title = "4 x 10 m shuttle run"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("The 4 x 10 m shuttle run of school fitness test batteries (the speed-agility test of the ALPHA-Fitness "
                "battery): two parallel lines 10 m apart, four legs, the line crossed at every turn, the time taken "
                "when the runner crosses the start line at the end of the fourth leg")
    deviations = [
        "the sponges the ALPHA version has the runner carry between the lines are left out (the robot has no "
        "fingers), and a turn needs one foot on the ground beyond the line where ALPHA asks for both",
        "the start: no starter and no reaction time; the clock runs from t = 0 with the robot standing behind the "
        "start line",
        "the finish is timed as in athletics (World Athletics TR 19): the leading point of the torso link's collision "
        "mesh on the plane of the start line, interpolated between 1 ms physics steps",
        "a fallen runner: a robot whose pelvis is below {down_z_m} m is down; it may get up and go on, but "
        "{down_limit_s} s down in a row end the attempt",
        "the qualifying time, {time_limit_s} s, is this benchmark's own round number: school norms for this test are "
        "10 to 14 s",
    ]
    time_limit_s = 30.0
    start = (-(0.02 + G1_FOOT_FRONT), 0.0, 0.0)
    stages = ["turn 1", "turn 2", "turn 3", "finish"]
    fall_rule = False                # the run's own: a fallen runner may get up (the "down" rule)
    params = dict(distance_m=10.0, toe_gap_m=0.02, down_z_m=0.40, down_limit_s=10.0)

    sentence = ("Run the 4 x 10 m shuttle: to the far line, back to the start line, to the far line again and back "
                "through the start line, putting a foot on the ground beyond the line at each turn, as fast as you can.")
    rules = ("Two lines cross the floor: the start line x = 0 and the far line x = {distance_m} m (the planes meant "
             "are the edges of the painted lines that face each other). The clock starts at t = 0. You run four "
             "legs: to the far line, back to the start line, to the far line, back to the start line. At each of the "
             "three turns you must put a foot on the ground wholly beyond the line: every part of that foot at "
             "x > {distance_m} m at the far line (turns 1 and 3), at x < 0 at the start line (turn 2); a foot on the "
             "line does not count. The turns count in this order only. After the third turn you finish at the "
             "moment the leading point of your torso (not the head, arms, legs or feet) reaches the start line. Which "
             "way you face and how you turn is up to you. You succeed when you finish within {time_limit_s} s of robot time. A "
             "fall does not end the attempt: you are down while your pelvis is below {down_z_m} m, you may get up "
             "and go on, but {down_limit_s} s down in a row end it. You fail when down for {down_limit_s} s, or "
             "after {time_limit_s} s.")
    venue = ("You stand facing the far line (+x), the front ends of your feet {toe_gap_m} m behind the start line "
             "(your pelvis 0.13 m behind it). Both lines are white, 5 cm wide and 6 m long, on a level sports floor "
             "that goes on for 10 m beyond each line; a cone stands at each end of each line.")
    difficulty = ("Forty metres with three reversals in {time_limit_s} s: the walking gait covers 19 m in that time, "
                  "and the running gait turns slowly, needs metres to stop, and falls when it is handed over to "
                  "another gait at speed, so every leg has to be braked and reversed without losing seconds.")

    def build(self, sc):
        D = self.p["distance_m"]
        sc.box("court", (D / 2, 0, 0.0003), (D / 2 + 10.0, 4.0, 0.0003), rgba=(0.76, 0.60, 0.42, 1))
        sc.line("start_line", (-0.025, -3.0), (-0.025, 3.0), z=0.0009)
        sc.line("far_line", (D + 0.025, -3.0), (D + 0.025, 3.0), z=0.0009)
        for s, tag in ((1, "L"), (-1, "R")):
            for x, n in ((-0.025, "start"), (D + 0.025, "far")):
                sc.geom(sc.wb, f"{n}_cone{tag}", type="cylinder", pos=(x, s * 3.15, 0.115), size=(0.07, 0.115),
                        rgba=(0.98, 0.45, 0.05, 1), contype="0", conaffinity="0")
        sc.camera("venue", (D / 2, -11.5, 6.0), (D / 2, 0.0, 0.3), fovy=58)

    def referee_reset(self, w, ref):
        m = w.m
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.foot_ids = {s: np.flatnonzero(self.sole[s]) for s in SIDES}
        self.torso_geom = next(g for g in range(m.ngeom) if m.body(int(m.geom_bodyid[g])).name == "torso_link"
                               and m.geom_contype[g] and int(m.geom_dataid[g]) >= 0
                               and m.mesh(int(m.geom_dataid[g])).name.endswith("torso_link"))
        self.torso_pts = hull_points(m, self.torso_geom)
        # leg: the turns made (0 to 3); back: the torso's rearmost x one physics step ago; down_k: down since when
        self.trackers = {"leg": 0, "back": None, "down_k": None}

    def torso_low_x(self, w) -> float:
        """The torso's leading point on the way back: the smallest x of the torso link's mesh."""
        g = self.torso_geom
        R = w.d.geom_xmat[g].reshape(3, 3)
        return float(w.d.geom_xpos[g][0] + np.min(self.torso_pts @ R[0]))

    def substep(self, w, ref):
        tr, D = self.trackers, self.p["distance_m"]
        b0, b1 = tr["back"], self.torso_low_x(w)         # MuJoCo's positions after a step are one physics step old
        tr["back"] = b1
        if tr["leg"] < 3:
            far = tr["leg"] % 2 == 0
            for s in SIDES:
                if not ref.touching(self.sole[s], ref.ground):
                    continue
                lo, hi = span(w, self.foot_ids[s], (1.0, 0.0, 0.0))
                if (lo > D) if far else (hi < 0.0):
                    tr["leg"] += 1
                    ref.stage(f"turn {tr['leg']}", foot=s, t=round(ref.time, 3))
                    ref.metrics["turns"] = tr["leg"]
                    break
        elif b0 is not None and b0 > 0.0 >= b1:
            dt = w.m.opt.timestep
            t = ref.time - 2 * dt + b0 / (b0 - b1) * dt
            ref.metrics["time_s"] = round(t, 3)
            if ref.stage("finish", time_s=round(t, 3)):
                ref.succeed()

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
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "turns_made": tr["leg"],
                "next": self.stages[min(tr["leg"], 3)], "far_line_x": self.p["distance_m"]}
