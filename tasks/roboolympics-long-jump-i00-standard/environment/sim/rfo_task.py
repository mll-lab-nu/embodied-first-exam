"""Long jump (World Athletics TR 29-30): the 40 m runway, the take-off board 1 m before a 2.75 m x 9 m sand pit, the
take-off line at the board's far edge; the mark is the break in the sand nearest the take-off line."""
import numpy as np

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")
TRACK = (0.72, 0.25, 0.18, 1)
GRASS = (0.22, 0.48, 0.24, 1)
SAND = (0.86, 0.76, 0.52, 1)
SLAB = 0.30                      # m: the thickness of the ground slabs and the depth of the sand


def span(w, ids, axis):
    """The extent of the geoms `ids` along a unit vector (their oriented bounding boxes)."""
    m, d = w.m, w.d
    ax = np.asarray(axis, float)
    R = d.geom_xmat[ids].reshape(-1, 3, 3)
    c = d.geom_xpos[ids] + np.einsum("gij,gj->gi", R, m.geom_aabb[ids, :3])
    half = np.sum(np.abs(np.einsum("i,gij->gj", ax, R)) * m.geom_aabb[ids, 3:], axis=1)
    p = c @ ax
    return float(np.min(p - half)), float(np.max(p + half))


def sand_venue(sc, p, x_back=-45.0, x_front_margin=6.0, half_y=8.0):
    """The level ground with a sand pit let into it. The core's floor plane cannot have a hole, so it is lowered out
    of the way and the ground is built of slabs whose tops are z = 0, around a box of sand whose top is z = 0 too
    (TR 29.6: the sand level with the take-off board). The sand's contact is soft and overdamped (a time constant
    of sand_timeconst_s, an impedance that rises from 0.5 to 0.9 over sand_give_m of penetration: it gives a centimetre
    or two under a standing G1 and does not bounce) with high friction, and wins every contact it is in."""
    floor = next(g for g in sc.wb.iter("geom") if g.get("name") == "floor")
    floor.set("pos", "0 0 -1")
    x0, x1, hw = p["board_to_pit_m"], p["board_to_pit_m"] + p["pit_length_m"], p["pit_width_m"] / 2
    xe = x1 + x_front_margin
    slabs = {"ground_runway": ((x_back, x0), (-half_y, half_y)), "ground_left": ((x0, x1), (hw, half_y)),
             "ground_right": ((x0, x1), (-half_y, -hw)), "ground_far": ((x1, xe), (-half_y, half_y))}
    for name, ((a, b), (c, d)) in slabs.items():
        sc.box(name, ((a + b) / 2, (c + d) / 2, -SLAB / 2), ((b - a) / 2, (d - c) / 2, SLAB / 2), rgba=GRASS,
               solid="stand", friction=(1.0, 0.005, 0.0001))
    sc.box("sand", ((x0 + x1) / 2, 0.0, -SLAB / 2), ((x1 - x0) / 2, hw, SLAB / 2), rgba=SAND, solid="stand",
           friction=(p["sand_friction"], 0.02, 0.002), solref=(p["sand_timeconst_s"], 1.0),
           solimp=(0.5, 0.9, p["sand_give_m"], 0.5, 2), priority=1, condim=4)
    sc.ground += list(slabs) + ["sand"]
    rw = p["runway_width_m"] / 2
    sc.box("runway", ((x0 - p["runway_m"]) / 2, 0, 0.0003), ((x0 + p["runway_m"]) / 2, rw, 0.0003), rgba=TRACK)
    for s in (1, -1):
        sc.line(f"runway_edge{s}", (-p["runway_m"], s * (rw + 0.025)), (x0, s * (rw + 0.025)), z=0.0009)
    L = p["board_length_m"]
    sc.box("board", (-L / 2, 0, 0.0006), (L / 2, rw, 0.0006), rgba=(0.97, 0.97, 0.97, 1))
    sc.box("indicator", (0.05, 0, 0.0006), (0.05, rw, 0.0006), rgba=(0.25, 0.55, 0.30, 1))   # the plasticine strip's place
    return list(slabs)


class Task(TaskBase):
    name = "long-jump"
    title = "Long jump"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 29 (the runway, the take-off "
                "board, the landing area), TR 30.1 (failures: 30.1.1 the take-off line, 30.1.2 the board's ends, "
                "30.1.4 the ground between the line and the landing area, 30.1.5 the ground outside the landing "
                "area), TR 30.3 (the measurement), TR 25.17 (one minute for a trial)")
    deviations = [
        "TR 30.1.3 (somersaulting) and TR 30.1.6 / 30.2 (how the athlete leaves the landing area) are not judged; "
        "the landing is judged for {mark_window_s} s from the first contact with the sand",
        "TR 29.3 (the plasticine indicator board): no imprint; the take-off line is judged geometrically: a foot on "
        "the ground with any part of it (also a part in the air) on or over the line's plane is a failure",
        "TR 29.6 (the sand): the pit is a box with a soft, overdamped, high-friction contact (time constant "
        "{sand_timeconst_s} s, full stiffness only {sand_give_m} m deep, friction {sand_friction}); it gives under "
        "the feet but keeps no imprint, so the mark is the contact with the sand nearest the take-off line",
        "TR 30 does not define a jump; here the flight into the pit must raise the pelvis at least {rise_min_m} m "
        "above its height at lift-off (pulling the feet up and falling into the pit is no jump)",
        "the rule book's wind gauge: there is no wind; the athlete alone, one trial",
    ]
    time_limit_s = 60.0
    start = (-20.0, 0.0, 0.0)
    stages = ["take-off", "landing"]
    fall_rule = False                # no rule of the event says a fall is a failure; the contacts below judge it
    params = dict(runway_m=40.0, runway_width_m=1.22, board_length_m=0.20, board_to_pit_m=1.0, pit_length_m=9.0,
                  pit_width_m=2.75, sand_timeconst_s=0.05, sand_give_m=0.04, sand_friction=1.5, min_air_s=0.05, rise_min_m=0.05,
                  mark_window_s=2.0)

    sentence = ("Do a long jump: run up, take off behind the take-off line, fly over the metre of runway beyond it "
                "and land in the sand pit.")
    rules = ("World Athletics rules for the long jump. The runway is {runway_m} m long and {runway_width_m} m wide "
             "along +x. The take-off line is x = 0, the edge of the white take-off board ({board_length_m} m long, "
             "level with the runway) that is nearer the pit. The landing area is a pit of sand, level with the "
             "runway, that begins {board_to_pit_m} m beyond the take-off line and is {pit_length_m} m long and "
             "{pit_width_m} m wide, centred on y = 0. Before your landing in the sand: no foot that is on the ground may have any "
             "part of it on or over the take-off line's plane (TR 30.1.1; the whole foot counts, also the parts of "
             "it that are in the air), and nothing of you may touch the ground at x >= 0 outside the sand "
             "(TR 30.1.4: the runway beyond the line and the ground beside the pit). Your jump is the flight "
             "(nothing of you touches anything, for at least {min_air_s} s) that ends with your first contact with "
             "the sand: its last ground contact before lift-off must have been within the runway's width "
             "(TR 30.1.2), and during it your pelvis must rise at least {rise_min_m} m above its height at "
             "lift-off. Taking off before the board is allowed; the jump is measured from the take-off line all "
             "the same. You may land on any part of your body. The mark is the point nearest the take-off line at "
             "which any part of you touches the sand in the first {mark_window_s} s after the first contact; in "
             "that time you may not touch the ground outside the pit nearer the take-off line than the mark "
             "(TR 30.1.5). You succeed when that time has passed after a valid jump: the mark is then at least "
             "{board_to_pit_m} m. A fall is not a failure by itself. You fail on any of the faults above, when "
             "you touch the sand without such a flight, if you leave the venue (the level ground ends 8 m to each "
             "side of the runway's axis, 45 m behind the take-off line and 6 m beyond the pit), or after "
             "{time_limit_s} s (the time allowed for a trial).")
    venue = ("You stand on the runway facing the pit (+x), your pelvis 20 m before the take-off line, in the middle "
             "of the runway; the runway goes on 20 m behind you. The runway is red with white edge lines, the "
             "board white, the sand yellow, the ground around it grass. Everything is level.")
    difficulty = ("The sand begins a metre beyond the line: with the foot kept behind the line the robot has to fly "
                  "about 1.2 m. Its running strides are in the air for less than 0.1 s and 0.4 m, its best "
                  "published standing jump is 0.9 m, and no controller is known that jumps out of a run.")

    def build(self, sc):
        p = self.p
        self.slabs = sand_venue(sc, p)
        x1 = p["board_to_pit_m"] + p["pit_length_m"]
        for k in range(1, int(x1) + 1):                  # a tick every metre beside the pit
            sc.line(f"tick{k}", (float(k), -p["pit_width_m"] / 2 - 0.25), (float(k), -p["pit_width_m"] / 2 - 0.05),
                    width=0.03, z=0.0009)
        sc.camera("venue", (1.5, -7.5, 3.2), (2.5, 0.0, 0.3), fovy=58)
        sc.camera("runway", (-24.0, -5.0, 3.0), (-8.0, 0.0, 0.5), fovy=55)

    def referee_reset(self, w, ref):
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.foot_ids = {s: np.flatnonzero(self.sole[s]) for s in SIDES}
        self.robot = ref.part("robot")
        self.sand = ref.geoms(names=["sand"])
        self.hard = ref.geoms(names=self.slabs)
        self.below = ref.geoms(names=["floor"])              # the lowered plane under the slabs: off the venue
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "landed_at": None, "mark": None}

    def in_pit(self, pts) -> np.ndarray:
        p = self.p
        return ((pts[:, 0] >= p["board_to_pit_m"]) & (pts[:, 0] <= p["board_to_pit_m"] + p["pit_length_m"])
                & (np.abs(pts[:, 1]) <= p["pit_width_m"] / 2))

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if ref.touching(self.robot, self.below):
            return ref.fail("left the venue")
        hard = ref.contact_points(self.robot, self.hard)
        if tr["landed_at"] is None:
            done = tr["flights"].update()                # a flight of at least min_air_s that lands now, or None
            if len(hard) and float(hard[:, 0].max()) >= 0.0:     # TR 30.1.4
                q = hard[hard[:, 0].argmax()]
                return ref.fail("touched the ground beyond the take-off line outside the sand",
                                at=[round(float(q[0]), 3), round(float(q[1]), 3)],
                                parts=sorted(ref.parts_touching(self.hard)))
            for s in SIDES:                              # TR 30.1.1: the take-off line
                if ref.touching(self.sole[s], self.hard):
                    front = span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1]
                    if front >= 0.0:
                        return ref.fail("a foot on or over the take-off line", foot=s, front_x=round(front, 3))
            if not ref.touching(self.robot, self.sand):
                return
            if done is None:
                return ref.fail("into the sand without a flight", parts=sorted(ref.parts_touching(self.sand)))
            sup = np.array(done["takeoff"].get("points") or [[0.0, 9.0, 0.0]])
            if float(np.abs(sup[:, 1]).max()) > p["runway_width_m"] / 2:
                return ref.fail("took off outside the board's ends", y=round(float(sup[np.abs(sup[:, 1]).argmax(), 1]), 3))
            rise = done["apex_z"] - done["pelvis0"][2]
            ref.metrics["air_s"], ref.metrics["rise_m"] = done["air_s"], round(rise, 3)
            ref.metrics["takeoff_x_m"] = round(float(sup[:, 0].max()), 3)
            if rise < p["rise_min_m"]:
                return ref.fail("the flight was not a jump", rise_m=round(rise, 3))
            ref.stage("take-off", air_s=done["air_s"], rise_m=round(rise, 3), parts=done["landing_parts"])
            tr["landed_at"] = ref.time
        if ref.has("landing") or ref.failed:
            return
        sand = ref.contact_points(self.robot, self.sand)
        if len(sand):
            x = float(sand[:, 0].min())
            tr["mark"] = x if tr["mark"] is None else min(tr["mark"], x)
        if len(hard) and float(hard[:, 0].min()) < tr["mark"]:   # TR 30.1.5
            q = hard[hard[:, 0].argmin()]
            return ref.fail("touched the ground outside the pit nearer the take-off line than the mark",
                            at=[round(float(q[0]), 3), round(float(q[1]), 3)], mark_m=round(tr["mark"], 3))
        if ref.time - tr["landed_at"] >= p["mark_window_s"]:
            ref.metrics["mark_m"] = round(tr["mark"], 3)
            if ref.stage("landing", mark_m=round(tr["mark"], 3)):
                ref.succeed()

    def privileged(self, w):
        p = self.p
        return {"pelvis": w.pelvis().tolist(), "takeoff_line_x": 0.0,
                "pit_x": [p["board_to_pit_m"], p["board_to_pit_m"] + p["pit_length_m"]],
                "pit_half_width": p["pit_width_m"] / 2, "mark_m": self.trackers["mark"],
                "feet_front_x": max(span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1] for s in SIDES)}
