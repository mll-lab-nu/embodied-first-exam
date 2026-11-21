"""Triple jump (World Athletics TR 31): hop, step and jump: the hop lands on the take-off foot, the step on the other
foot, the jump in the sand pit; the take-off line 7 m before the pit."""
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


# The sand, from granular physics. A plate pushed into dry silica sand (Quikrete medium sand: 0.3-0.8 mm grains,
# packing 0.6) meets a pressure that grows in proportion to its depth, 2.02 N/cm^2 per cm (the resistive-force constant
# measured by plate penetration: Agarwal, Senatore, Zhang, Kingsbury, Iagnemma, Goldman and Kamrin, "Modeling of the
# interaction of rigid wheels with dry granular media", Journal of Terramechanics 85, 1-14 (2019), Table 1), and its
# angle of internal friction is 34 degrees (friction tan 34 deg = 0.67, the same table). For the G1's two soles (each
# 0.18 m x 0.07 m: the feet's sole spheres) that law sinks the standing robot (33.3 kg) 6.4 mm and stops it 71 mm deep
# when it lands feet first at 2.5 m/s; sand is plastic and does not push back. MuJoCo's contact is a spring-damper
# normalised by the bodies' masses, not a pressure law, so its numbers are fitted to those two depths on the G1 itself
# (measured): time constant 0.15 s, damping ratio 2 (overdamped: no bounce), an impedance that falls
# from 0.95 at the surface to 0.40 at 5 cm (stiff at first, then yielding, as sand ahead of a sinking foot does);
# measured: 7.4 mm standing, 75 mm for the 2.5 m/s landing, 0.10 m/s of rebound. Sand keeps no imprint here.
SAND_CONTACT = dict(sand_timeconst_s=0.15, sand_dampratio=2.0, sand_imp0=0.95, sand_imp1=0.40, sand_give_m=0.05,
            sand_friction=0.67)


def sand_venue(sc, p, x_back=-45.0, x_front_margin=6.0, half_y=8.0):
    """The level ground with a sand pit let into it (the same construction as long_jump.py's). The core's floor
    plane cannot have a hole, so it is lowered out of the way and the ground is built of slabs whose tops are z = 0,
    around a box of sand whose top is z = 0 too (TR 29.6: the sand level with the take-off board). The sand's contact
    (SAND_CONTACT above) wins every contact it is in."""
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
           friction=(p["sand_friction"], 0.02, 0.002), solref=(p["sand_timeconst_s"], p["sand_dampratio"]),
           solimp=(p["sand_imp0"], p["sand_imp1"], p["sand_give_m"], 0.5, 2), priority=1, condim=4)
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
    name = "triple-jump"
    title = "Triple jump"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 31 (31.1 the hop, step and jump "
                "in that order; 31.2 the hop lands on the take-off foot, the step on the other foot; the rules of the "
                "long jump apply: TR 29 the runway, the board, the landing area; TR 30.1.1, 30.1.2, 30.1.5 failures; "
                "TR 30.3 the measurement), TR 25.17 (one minute for a trial)")
    deviations = [
        "TR 31.3 (the take-off line at least 13 m from the pit for men, 11 m for women in international "
        "competition; nearer boards for other levels): the board is {board_to_pit_m} m before the pit, a school "
        "competition's board (FAMILIES.md)",
        "TR 31.2, note (a touch of the ground by the 'sleeping' leg is no failure): not applied: between the hop's "
        "landing and the step's take-off, and between the step's landing and the jump's take-off, only the foot the "
        "phase landed on may touch the ground; a referee without eyes cannot tell a scrape from a supporting step",
        "TR 31.1 (the event is one hop, one step and one jump): between a phase's landing and the next take-off the "
        "landing foot is on one place: a touch of it more than {foot_move_m} m from where it landed is a failure "
        "(hops too short to be flights, or a slide, would otherwise cover the distance)",
        "the take-off of the hop from one foot (implied by TR 31.2) is judged by a number: the other foot must have "
        "left the ground at least {single_support_s} s before the take-off foot does",
        "TR 30.1.3 (somersaulting) and TR 30.1.6 / 30.2 (how the athlete leaves the landing area) are not judged; "
        "the landing is judged for {mark_window_s} s from the first contact with the sand",
        "TR 29.3 (the plasticine indicator board): no imprint; the take-off line is judged geometrically: a foot on "
        "the ground with any part of it (also a part in the air) on or over the line's plane is a failure",
        "TR 29.6 (the sand): the pit is a box whose contact follows the sinking of a plate into dry silica sand (a "
        "resistance growing in proportion to depth, Agarwal et al. 2019; friction {sand_friction}, the sand's internal "
        "friction; MuJoCo's contact fitted to that law on this robot: a time constant of {sand_timeconst_s} s, damping "
        "ratio {sand_dampratio}, an impedance falling from {sand_imp0} to {sand_imp1} over {sand_give_m} m): it gives "
        "7 mm under the standing robot and about 7 cm under a landing at 2.5 m/s and does not push back; it is not "
        "loose damp sand that flows, it is not raked, and it keeps no imprint, so the mark is the contact with the "
        "sand nearest the take-off line",
        "TR 31 does not define a hop; here each phase is a flight of at least {min_air_s} s, and the hop must raise "
        "the pelvis at least {rise_min_m} m above its height at lift-off; no wind; one trial",
    ]
    time_limit_s = 60.0
    start = (-20.0, 0.0, 0.0)
    stages = ["hop", "step", "jump", "landing"]
    fall_rule = False                # no rule of the event says a fall is a failure; the contacts below judge it
    params = dict(runway_m=40.0, runway_width_m=1.22, board_length_m=0.20, board_to_pit_m=7.0, pit_length_m=9.0,
                  pit_width_m=2.75, **SAND_CONTACT, min_air_s=0.05,
                  rise_min_m=0.05, single_support_s=0.05, foot_move_m=0.30, mark_window_s=2.0)

    sentence = ("Do a triple jump: run up, hop from behind the take-off line and land on the same foot, step onto "
                "the other foot, and jump from it into the sand pit.")
    rules = ("World Athletics rules for the triple jump. The runway is {runway_m} m long and {runway_width_m} m "
             "wide along +x and goes on to the pit. The take-off line is x = 0, the edge of the white take-off "
             "board ({board_length_m} m long) that is nearer the pit. The landing area is a pit of sand, level with "
             "the runway, that begins {board_to_pit_m} m beyond the take-off line and is {pit_length_m} m long and "
             "{pit_width_m} m wide, centred on y = 0. A flight is a time of at least {min_air_s} s in which nothing "
             "of you touches anything. Until the hop: no foot that is on the ground may have any part of it on or "
             "over the take-off line's plane (the whole foot counts, also the parts of it that are in the air), and "
             "nothing of you may touch the ground at x >= 0. (1) The hop is the flight that ends with your first "
             "contact beyond the line. It must be taken off from one foot within the runway's width: the other foot "
             "has left the ground at least {single_support_s} s before the take-off foot; your pelvis must rise at "
             "least {rise_min_m} m above its height at lift-off; and its first contact must be the take-off foot "
             "alone, on the runway. (2) The step is the next flight: until it starts only the foot you landed on "
             "may touch the ground, and its first contact must be the other foot alone, on the runway. (3) The "
             "jump is the next flight: until it starts only the foot the step landed on may touch the ground, and "
             "its first contact must be with the sand (any part of your body). Between the landing of the hop or "
             "of the step and the next flight the landing foot stays where it came down: it fails to touch the "
             "ground with its centre more than {foot_move_m} m from where it was at the landing (no sliding along "
             "and no travelling in hops shorter than a flight). On the runway means: every point of "
             "that contact within the runway's width and before the pit. The mark is the point nearest the "
             "take-off line at which any part of you touches the sand in the first {mark_window_s} s after the "
             "jump's first contact; in that time you may not touch the ground outside the pit nearer the take-off "
             "line than the mark. You succeed when that time has passed after a valid hop, step and jump: the mark "
             "is then at least {board_to_pit_m} m. A fall is not a failure by itself. You fail on any of the faults "
             "above, if you leave the venue (the level ground ends 8 m to each side of the runway's axis, 45 m "
             "behind the take-off line and 6 m beyond the pit) or after {time_limit_s} s (the time allowed for a trial).")
    venue = ("You stand on the runway facing the pit (+x), your pelvis 20 m before the take-off line, in the middle "
             "of the runway; the runway goes on 20 m behind you. The runway is red with white edge lines, the "
             "board white, the sand yellow, the ground around it grass. Everything is level.")
    difficulty = ("Seven metres in three flights, each from one foot: every phase has to be more than twice this "
                  "robot's best published two-foot jump, taken from a single leg, and landed on a single leg with "
                  "enough balance and speed left to take off again. Nothing built in hops on one foot at all.")

    def build(self, sc):
        p = self.p
        self.slabs = sand_venue(sc, p)
        x0 = p["board_to_pit_m"]
        for k in range(1, int(x0) + 1):                  # a tick every metre beside the runway
            sc.line(f"tick{k}", (float(k), -p["runway_width_m"] / 2 - 0.30), (float(k), -p["runway_width_m"] / 2 - 0.10),
                    width=0.03, z=0.0009)
        sc.camera("venue", (4.0, -11.0, 4.5), (5.0, 0.0, 0.3), fovy=58)
        sc.camera("runway", (-24.0, -5.0, 3.0), (-8.0, 0.0, 0.5), fovy=55)

    def referee_reset(self, w, ref):
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.foot_ids = {s: np.flatnonzero(self.sole[s]) for s in SIDES}
        self.robot = ref.part("robot")
        self.sand = ref.geoms(names=["sand"])
        self.hard = ref.geoms(names=self.slabs)
        self.below = ref.geoms(names=["floor"])              # the lowered plane under the slabs: off the venue
        # phases: how many of hop, step, jump have landed; foot: the foot the last phase landed on
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "phases": 0, "foot": None,
                         "last_on": {"left": -1.0, "right": -1.0}, "at_t0": None, "anchor": None, "landed_at": None,
                         "mark": None}

    def _on_runway(self, pts) -> bool:
        p = self.p
        return bool(len(pts)) and bool(np.all((np.abs(pts[:, 1]) <= p["runway_width_m"] / 2)
                                              & (pts[:, 0] < p["board_to_pit_m"])))

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        if ref.touching(self.robot, self.below):
            return ref.fail("left the venue")
        hard = ref.contact_points(self.robot, self.hard)
        in_sand = ref.touching(self.robot, self.sand)
        n = tr["phases"]
        if n < 3:
            was_air = fl.air
            done = fl.update()                           # a flight of at least min_air_s that lands now, or None
            if fl.air and not was_air:
                tr["at_t0"] = dict(tr["last_on"])
            for s in SIDES:
                if ref.touching(self.sole[s], ref.ground):
                    tr["last_on"][s] = ref.time
            parts = ref.parts_touching(ref.ground)
        if n == 0:
            beyond = in_sand or (len(hard) and float(hard[:, 0].max()) >= 0.0)
            if not beyond:
                for s in SIDES:                          # TR 30.1.1: the take-off line
                    if ref.touching(self.sole[s], self.hard):
                        front = span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1]
                        if front >= 0.0:
                            return ref.fail("a foot on or over the take-off line", foot=s, front_x=round(front, 3))
                return
            if done is None:
                return ref.fail("touched the ground beyond the take-off line without a hop", parts=sorted(parts))
            t0 = tr["at_t0"]
            foot = max(SIDES, key=lambda s: t0[s])       # the foot that left the ground last
            other = "right" if foot == "left" else "left"
            sup = np.array(done["takeoff"].get("points") or [[0.0, 9.0, 0.0]])
            rise = done["apex_z"] - done["pelvis0"][2]
            ref.metrics["hop_air_s"], ref.metrics["hop_rise_m"] = done["air_s"], round(rise, 3)
            if t0[foot] - t0[other] < p["single_support_s"]:
                return ref.fail("the hop was taken off from both feet", feet_left_apart_s=round(t0[foot] - t0[other], 3))
            if float(np.abs(sup[:, 1]).max()) > p["runway_width_m"] / 2:
                return ref.fail("took off outside the board's ends", y=round(float(sup[np.abs(sup[:, 1]).argmax(), 1]), 3))
            if rise < p["rise_min_m"]:
                return ref.fail("the hop was not a jump", rise_m=round(rise, 3))
            if done["landing_parts"] != [f"{foot}_foot"] or in_sand or not self._on_runway(hard):
                return ref.fail("the hop did not land on the take-off foot on the runway", take_off_foot=foot,
                                landed_on=done["landing_parts"], in_the_sand=bool(in_sand))
            tr["phases"], tr["foot"] = 1, foot
            ref.metrics["hop_m"] = round(float(hard[:, 0].min()), 3)
            return ref.stage("hop", foot=foot, air_s=done["air_s"])
        if n in (1, 2):
            foot = tr["foot"]
            name = "step" if n == 1 else "jump"
            if done is None:                             # on the ground between two phases (or in the air)
                if parts - {f"{foot}_foot"}:
                    return ref.fail(f"another part than the landing foot touched the ground before the {name}",
                                    landing_foot=foot, parts=sorted(parts))
                if parts:                                # the landing foot is down: on the place it landed on
                    at = w.d.geom_xpos[self.foot_ids[foot]].mean(axis=0)[:2]
                    if tr["anchor"] is None:
                        tr["anchor"] = at.tolist()
                    moved = float(np.linalg.norm(at - tr["anchor"]))
                    if moved > p["foot_move_m"]:
                        return ref.fail(f"the landing foot moved along the ground before the {name}",
                                        landing_foot=foot, moved_m=round(moved, 3))
                return
            ref.metrics[f"{name}_air_s"] = done["air_s"]
            if n == 1:
                other = "right" if foot == "left" else "left"
                if done["landing_parts"] != [f"{other}_foot"] or in_sand or not self._on_runway(hard):
                    return ref.fail("the step did not land on the other foot on the runway", hop_foot=foot,
                                    landed_on=done["landing_parts"], in_the_sand=bool(in_sand))
                tr["phases"], tr["foot"], tr["anchor"] = 2, other, None
                ref.metrics["step_m"] = round(float(hard[:, 0].min()), 3)
                return ref.stage("step", foot=other, air_s=done["air_s"])
            if len(hard) or not in_sand:
                return ref.fail("the jump did not come down in the sand", landed_on=done["landing_parts"],
                                at=[round(float(x), 3) for x in hard[0][:2]] if len(hard) else None)
            tr["phases"] = 3
            tr["landed_at"] = ref.time
            ref.stage("jump", air_s=done["air_s"], parts=done["landing_parts"])
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
        p, tr = self.p, self.trackers
        return {"pelvis": w.pelvis().tolist(), "takeoff_line_x": 0.0,
                "pit_x": [p["board_to_pit_m"], p["board_to_pit_m"] + p["pit_length_m"]],
                "pit_half_width": p["pit_width_m"] / 2, "phases_landed": tr["phases"], "landing_foot": tr["foot"],
                "mark_m": tr["mark"],
                "feet_front_x": max(span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1] for s in SIDES)}
