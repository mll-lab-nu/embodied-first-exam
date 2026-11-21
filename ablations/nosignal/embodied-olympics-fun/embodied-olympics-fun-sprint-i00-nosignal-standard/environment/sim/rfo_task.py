"""50 m: the straight sprint of the World Athletics rules, from the starter's commands to the torso on the finish line
(the short indoor distance: the benchmark shows what a robot can do, it does not stage the Olympic
programme, and 100 m was half a minute of the same thing).

The start procedure, the false-start rule, the lane rule, the "down" rule and the timing are Embodied Olympics' athletics
referee (sports/athletics/track.py, branch athletics-v3, MIT), ported: "on your marks" at t = 0, "set" 2.0 s later, the
gun 1.2-2.2 s after "set" (this instance's fixed draw); a start movement earlier than 0.100 s after the gun is a false
start; the finish is the torso's leading point on the line, interpolated between two physics steps."""
import math

import numpy as np

from rfo.task import TaskBase

SIDES = ("left", "right")
TRACK = (0.72, 0.25, 0.18, 1)
LAMP = {"on_your_marks": (0.90, 0.10, 0.10, 1.0), "set": (0.98, 0.85, 0.10, 1.0), "running": (0.10, 0.85, 0.20, 1.0)}
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
    """The vertices of mesh geom g (geom frame) that are extreme along n fixed directions (a Fibonacci sphere): the
    convex hull's support points, of which the torso's leading point is the maximum at every physics step."""
    mid = int(m.geom_dataid[g])
    v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]].astype(float)
    i = np.arange(n) + 0.5
    phi, th = np.arccos(1 - 2 * i / n), math.pi * (1 + 5 ** 0.5) * i
    dirs = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]
    return v[np.unique(np.argmax(v @ dirs.T, axis=0))]


class Task(TaskBase):
    name = "sprint"
    title = "50 m"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 16 (the start: 16.5 the line, "
                "16.6-16.8 false starts), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish, timing); the distance is the "
                "50 m of indoor athletics")
    deviations = [
        "the distance: {distance_m} m, the short sprint of indoor athletics, on an outdoor straight; not the 100 m",
        "TR 16.3-16.4 (starting blocks, crouch start): a standing start without blocks, the feet {toe_gap_m} m behind "
        "the start line; a robot of this build has no crouch start",
        "TR 16.6-16.8 (start information system): the start movement is measured on the robot instead of the blocks: "
        "the pelvis more than {start_move_m} m from its place at \"set\", or a foot reaching the start line; a false "
        "start disqualifies at once, there is no recall",
        "TR 16 (the starter's voice and gun): the robot has no hearing; the commands are shown by a start lamp beside "
        "the lane (red, yellow at \"set\", green at the gun)",
        "TR 17.3 (lanes): the lane is judged by the pelvis: its centre more than half a lane width from the lane's "
        "centre line disqualifies at once; feet on the lines are not judged",
        "TR 17 (a fallen athlete): a robot whose pelvis is below {down_z_m} m is down; it may get up and run on, but "
        "{down_limit_s} s down in a row end the race (did not finish)",
        "TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh reaches "
        "the plane of the finish line's near edge, interpolated between 1 ms physics steps",
        "TR 14 (the track): a flat straight of three 1.22 m lanes, the robot alone in the middle one; no wind",
        "a race has no time to beat; here the run counts only if it finishes within {finish_limit_s} s of robot time after the gun "
        "(this benchmark's qualifying time: a mean of about 1.7 m/s, beyond the walking gait)",
    ]
    time_limit_s = 34.2              # "set" at 2.0 s, the gun at most 2.2 s later, 30 s to finish
    start = (-(0.05 + 0.02 + G1_FOOT_FRONT), 0.0, 0.0)
    stages = ["start", "finish"]
    fall_rule = False                # the race's own: a fallen runner may get up (the "down" rule)
    params = dict(distance_m=50.0, lane_width_m=1.22, start_line_m=0.05, toe_gap_m=0.02, set_at_s=2.0,
                  gun_min_s=1.2, gun_max_s=2.2, gun_after_set_s=1.74, reaction_min_s=0.100, start_move_m=0.05,
                  finish_limit_s=30.0, down_z_m=0.40, down_limit_s=10.0)

    sentence = ("Run the 50 m: wait for the starter's gun, then sprint down your lane until your torso reaches the "
                "finish line.")
    rules = ("World Athletics rules for the straight sprint. The lane runs along +x, {lane_width_m} m wide, centred "
             "on y = 0. The start line is {start_line_m} m wide; its far edge is x = 0 and the finish line's near "
             "edge is x = {distance_m} m. The start: \"on your marks\" at t = 0, \"set\" {set_at_s} s later, the gun "
             "between {gun_min_s} and {gun_max_s} s after \"set\" (fixed for this task, not announced). Your start "
             "movement is the first moment your pelvis is more than {start_move_m} m from where it was at \"set\", or "
             "the front end of a foot reaches the start line (x > -{start_line_m} m, on the ground or in the air). A "
             "start movement before the gun, or earlier than {reaction_min_s} s after it, is a false start; so is a "
             "foot reaching the start line before \"set\". From the gun on you must keep your lane: your pelvis may "
             "not be more than half the lane's width from y = 0. You finish at the moment the leading point of your "
             "torso (not the head, arms, legs or feet) reaches the finish line; the time counts from the gun. You "
             "succeed with a valid finish within {finish_limit_s} s of robot time after the gun. A fall does not end the race: you "
             "are down while your pelvis is below {down_z_m} m, you may get up and run on, but {down_limit_s} s down "
             "in a row end it. You fail on a false start, on leaving the lane, when down for {down_limit_s} s, or "
             "when {finish_limit_s} s after the gun have passed.")
    venue = ("You stand in your lane facing the finish (+x), the front ends of your feet {toe_gap_m} m behind the "
             "start line, your pelvis 0.18 m behind it. The lane lines are white on a red track; there are two "
             "white finish posts beside the track at {distance_m} m. You cannot hear the starter: a start lamp on a "
             "post 4 m ahead of the start line, 1.0 m to the left of your lane's centre and 0.8 m above the track, "
             "shows the commands: red from \"on your marks\", yellow from \"set\", green from the gun.")
    difficulty = ("The gun has to be seen, not guessed: moving early disqualifies and waiting costs time. Then 50 m "
                  "in a 1.22 m lane: the walking gait covers 20 m in the time, the running gait has to be held "
                  "straight for a quarter of a minute at a speed close to where it falls.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        D, W, S = p["distance_m"], p["lane_width_m"], p["start_line_m"]
        floor = next(g for g in sc.wb.iter("geom") if g.get("name") == "floor")
        floor.set("pos", f"{D / 2:g} 0 0")                   # the grass is drawn around the whole straight
        floor.set("size", f"{D / 2 + 40:g} 30 0.05")
        x0, x1 = -12.0, D + 25.0
        sc.box("track", ((x0 + x1) / 2, 0, 0.0003), ((x1 - x0) / 2, W * 1.5 + 0.3, 0.0003), rgba=TRACK)
        for i, y in enumerate((-1.5 * W, -0.5 * W, 0.5 * W, 1.5 * W)):
            sc.line(f"lane{i}", (x0, y), (x1, y))
        sc.line("start_line", (-S / 2, -1.5 * W), (-S / 2, 1.5 * W), width=S, z=0.0009)
        sc.line("finish_line", (D + S / 2, -1.5 * W), (D + S / 2, 1.5 * W), width=S, z=0.0009)
        for s, tag in ((1, "L"), (-1, "R")):
            sc.box(f"finish_post{tag}", (D, s * (1.5 * W + 0.5), 1.0), (0.05, 0.05, 1.0))
        for k in range(10, int(D), 10):                      # distance boards beside the track every 10 m
            sc.box(f"board{k}", (k, -(1.5 * W + 0.9), 0.3), (0.02, 0.3, 0.3), rgba=(0.12, 0.12, 0.14, 1))
        sc.box("lamp_post", (4.0, 1.0, 0.35), (0.02, 0.02, 0.35), rgba=(0.2, 0.2, 0.22, 1))
        sc.geom(sc.wb, "start_lamp", type="sphere", pos=(4.0, 1.0, 0.8), size=(0.12,), rgba=LAMP["on_your_marks"],
                contype="0", conaffinity="0")
        sc.camera("venue", (D / 2, -(6.0 + 0.36 * D), 3.0 + 0.14 * D), (D / 2, 0.0, 0.0), fovy=62)
        sc.camera("start", (-4.5, -3.2, 1.9), (3.0, 0.2, 0.6), fovy=55)

    # ------------------------------------------------------------------ the starter
    def _ks(self, w):
        p = self.p
        set_k = int(round(p["set_at_s"] / w.CONTROL_DT))
        return set_k, set_k + int(round(p["gun_after_set_s"] / w.CONTROL_DT))

    def phase(self, w) -> str:
        set_k, gun_k = self._ks(w)
        return "on_your_marks" if w.k < set_k else "set" if w.k < gun_k else "running"

    def _lamp(self, w):
        w.m.geom_rgba[self.lamp] = LAMP[self.phase(w)]

    def reset(self, w):
        p = self.p
        if not p["gun_min_s"] <= p["gun_after_set_s"] <= p["gun_max_s"]:
            raise ValueError("sprint: the gun must come gun_min_s to gun_max_s after \"set\"")
        self.lamp = w.m.geom("start_lamp").id
        self._lamp(w)

    def before_step(self, w):
        self._lamp(w)

    def referee_reset(self, w, ref):
        m = w.m
        self.foot_ids = {s: np.flatnonzero(ref.part(f"{s}_foot")) for s in SIDES}
        self.torso_geom = next(g for g in range(m.ngeom) if m.body(int(m.geom_bodyid[g])).name == "torso_link"
                               and m.geom_contype[g] and int(m.geom_dataid[g]) >= 0
                               and m.mesh(int(m.geom_dataid[g])).name.endswith("torso_link"))
        self.torso_pts = hull_points(m, self.torso_geom)
        # status: marks -> running -> finished; set_xy: the pelvis at "set"; start_k: the control step of the start
        # movement; front: the torso's leading x one physics step ago; down_k: since when the robot is down
        self.trackers = {"status": "marks", "set_xy": None, "start_k": None, "front": None, "down_k": None}
        ref.event("on_your_marks")

    def torso_front(self, w) -> float:
        """TR 19.1: the torso, not the head, neck, arms, legs, hands or feet: the leading x of the torso link's mesh."""
        g = self.torso_geom
        R = w.d.geom_xmat[g].reshape(3, 3)
        return float(w.d.geom_xpos[g][0] + np.max(self.torso_pts @ R[0]))

    def foot_front(self, w) -> float:
        return max(span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1] for s in SIDES)

    # ------------------------------------------------------------------ the referee
    def substep(self, w, ref):
        tr, D = self.trackers, self.p["distance_m"]
        f0, f1 = tr["front"], self.torso_front(w)        # the positions MuJoCo reports after a step are those before
        tr["front"] = f1                                 # its integration: one physics step old
        if tr["status"] != "running" or f0 is None or not f0 < D <= f1:
            return
        dt = w.m.opt.timestep
        _, gun_k = self._ks(w)
        t = ref.time - 2 * dt + (D - f0) / (f1 - f0) * dt - gun_k * w.CONTROL_DT
        tr["status"] = "finished"
        ref.metrics["time_s"] = round(t, 3)
        ref.metrics["distance_m"] = D
        if ref.stage("finish", time_s=round(t, 3)):
            ref.succeed()

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        self._lamp(w)                                    # the lamp an observation of this instant shows
        set_k, gun_k = self._ks(w)
        k = w.k
        x, y, z, _ = (float(v) for v in w.pelvis())
        if k == set_k:
            ref.event("set")
            tr["set_xy"] = [x, y]
        if k == gun_k:
            ref.event("gun")
        if tr["status"] == "marks" and k >= gun_k:
            tr["status"] = "running"
        on_line = self.foot_front(w) > -p["start_line_m"]
        if tr["start_k"] is None:
            moved = tr["set_xy"] is not None and math.hypot(x - tr["set_xy"][0], y - tr["set_xy"][1]) > p["start_move_m"]
            if moved or on_line:
                react = (k - gun_k) * w.CONTROL_DT
                if react < p["reaction_min_s"] - 1e-9:
                    return ref.fail("false start", reaction_s=round(react, 3),
                                    what="a foot on the start line" if on_line else "start movement")
                tr["start_k"] = k
                ref.metrics["reaction_s"] = round(react, 3)
                ref.stage("start", reaction_s=round(react, 3))
        if tr["status"] != "running":                    # before the gun only the start rules apply (TR 16)
            return
        ref.metrics["distance_m"] = round(max(ref.metrics.get("distance_m", 0.0), min(tr["front"], p["distance_m"])), 3)
        if abs(y) > p["lane_width_m"] / 2:
            return ref.fail("left the lane", y=round(y, 3))
        if z < p["down_z_m"]:
            if tr["down_k"] is None:
                tr["down_k"] = k
                ref.event("down")
            elif (k - tr["down_k"]) * w.CONTROL_DT >= p["down_limit_s"]:
                return ref.fail("did not finish: down for too long", down_s=p["down_limit_s"])
        elif tr["down_k"] is not None:
            tr["down_k"] = None
            ref.event("up")
        if (k - gun_k) * w.CONTROL_DT >= p["finish_limit_s"] - 1e-9:
            ref.fail("time")

    def privileged(self, w):
        set_k, gun_k = self._ks(w)
        return {"pelvis": w.pelvis().tolist(), "phase": self.phase(w), "lamp_rgba": list(LAMP[self.phase(w)]),
                "clock_s": None if w.k < gun_k else round((w.k - gun_k) * w.CONTROL_DT, 3),
                "torso_front_x": self.torso_front(w), "foot_front_x": self.foot_front(w)}
