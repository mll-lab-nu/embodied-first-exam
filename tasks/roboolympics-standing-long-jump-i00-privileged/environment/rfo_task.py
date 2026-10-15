"""Standing long jump (the school fitness test): from a standstill behind the line, a two-foot take-off without a
step, the mark at the rearmost landing contact; land and stand."""
import numpy as np

from rfo.referee import Flights
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


class Task(TaskBase):
    name = "standing-long-jump"
    title = "Standing long jump"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("The standing long jump (standing broad jump) of school and club fitness test batteries (Eurofit, "
                "ALPHA-Fitness, the Chinese National Student Physical Health Standard): the feet side by side behind "
                "the take-off line, a two-foot take-off with no step or preliminary hop, a landing on the feet; the "
                "jump is measured from the take-off line to the nearest point of contact at the landing")
    deviations = [
        "the athlete cannot walk up to the line: any step before the take-off is a foul, so the robot is placed with "
        "the front ends of its feet {toe_gap_m} m behind the line (a rigid foot that pivots on its toes at the push-"
        "off swings up to 3 cm forward of where they stood)",
        "the measurement: the mark is the contact nearest the line of any part of the robot from the landing until "
        "it has stood for {stand_s} s (a step or a hand put back shortens the jump; a fall voids it), where the test "
        "measures the heels at the landing",
        "a jump is told from a loss of contact by two numbers the test does not have: a flight of at least "
        "{min_air_s} s in which the pelvis rises at least {rise_min_m} m above its height at lift-off",
        "the qualifying mark, {qualifying_mark_m} m, is the robot's own standing height (FAMILIES.md); the school "
        "standards scale with the athlete: adolescent pass marks are roughly 1.0 to 1.3 times body height",
    ]
    time_limit_s = 20.0
    start = (-(0.05 + G1_FOOT_FRONT), 0.0, 0.0)
    stages = ["take-off", "landing", "stand"]
    params = dict(qualifying_mark_m=1.32, toe_gap_m=0.05, two_foot_window_s=0.05, foot_shift_m=0.03, min_air_s=0.10,
                  rise_min_m=0.05, stand_s=1.0, fall_z_m=0.35)

    sentence = ("Do a standing long jump: from a standstill behind the take-off line, take off from both feet "
                "without a step, land on your feet at least your own height beyond the line, and stand.")
    rules = ("The take-off line is x = 0; you jump towards +x. Your jump is your first flight (nothing of you touches "
             "the ground) of at least {min_air_s} s. Until then: no part of a foot that is on the ground may be on or "
             "over the line (the whole foot counts, also the parts of it that are in the air); no run-up and no "
             "step: every point where a foot touches the ground must lie within {foot_shift_m} m of the place where "
             "that foot's sole stood at t = 0, and neither foot may be off the ground for more than "
             "{two_foot_window_s} s while the other is on it (so both feet leave the ground within "
             "{two_foot_window_s} s of each other: a two-foot take-off). Rising on the toes is allowed. The flight "
             "must be a jump: your pelvis has to rise at least {rise_min_m} m above its height at lift-off. The "
             "first contact after the flight must be with your feet only. The mark is the point nearest the "
             "take-off line at which any part of you touches the ground from that landing until you have stood; it "
             "must be at least {qualifying_mark_m} m beyond the line. After the landing you may step; you succeed "
             "once you stand for {stand_s} s without a break: only your feet on the ground, your torso within about 20 degrees "
             "of vertical, your pelvis slower than 0.35 m/s. A fall fails the attempt at any time: your pelvis "
             "lower than {fall_z_m} m, or any part of you other than your feet on the ground. You fail on a foot on "
             "or over the line, a step or shuffle before the take-off, a foot that leaves the ground before the "
             "other, a flight that is not a jump, a landing that is not on the feet, a mark short of {qualifying_mark_m} m, a "
             "fall, or after {time_limit_s} s.")
    venue = ("You stand facing +x with your feet side by side, their front ends {toe_gap_m} m behind the take-off "
             "line (white); your pelvis is 0.164 m behind the line. The floor is level and firm; a yellow line is "
             "painted across it at the qualifying mark.")
    difficulty = ("Neither built-in gait can jump. The take-off needs both legs' full power in one coordinated "
                  "push with the body leaning well ahead of the feet, and a jump of the robot's own height comes "
                  "down at more than 3 m/s: the legs have to absorb it without a hand or the pelvis going down.")

    def build(self, sc):
        p = self.p
        Q = p["qualifying_mark_m"]
        sc.box("runway", (Q / 2 + 0.2, 0, 0.0003), (Q / 2 + 1.5, 1.0, 0.0003), rgba=(0.72, 0.25, 0.18, 1))
        sc.line("takeoff_line", (-0.025, -1.0), (-0.025, 1.0), z=0.0009)
        sc.line("mark_line", (Q + 0.015, -1.0), (Q + 0.015, 1.0), width=0.03, rgba=(0.95, 0.85, 0.2, 1), z=0.0009)
        for k in range(1, int(Q / 0.5) + 3):                # a tick every half metre beside the landing area
            sc.line(f"tick{k}", (0.5 * k, -1.0), (0.5 * k, -0.85), width=0.02, z=0.0009)
        sc.camera("venue", (Q / 2, -3.6, 1.4), (Q / 2, 0.0, 0.5), fovy=55)

    def referee_reset(self, w, ref):
        m = w.m
        self.fall_z = self.p["fall_z_m"]
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.foot_ids = {s: np.flatnonzero(self.sole[s]) for s in SIDES}
        self.robot = ref.part("robot")
        box = {}
        for s in SIDES:                                  # where each sole stands at t = 0 (its contact geoms)
            g = [i for i in self.foot_ids[s] if m.geom_contype[i] & 1]
            xy = w.d.geom_xpos[g][:, :2]
            box[s] = [float(xy[:, 0].min()), float(xy[:, 0].max()), float(xy[:, 1].min()), float(xy[:, 1].max())]
        # last_on: when each foot last touched the ground; at_t0: last_on at the start of the current flight
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "footprint": box, "jumped": False,
                         "last_on": {"left": 0.0, "right": 0.0}, "at_t0": None, "mark": None}

    def _before_takeoff(self, w, ref, on) -> bool:
        """The standing start's rules, at every physics step until the jump. False: the attempt has failed."""
        tr, p = self.trackers, self.p
        for s in SIDES:
            other = "right" if s == "left" else "left"
            if on[s]:
                front = span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1]
                if front >= 0.0:
                    ref.fail("a foot on or over the take-off line", foot=s, front_x=round(front, 3))
                    return False
                x0, x1, y0, y1 = tr["footprint"][s]
                pts = ref.contact_points(self.sole[s], ref.ground)
                d = np.maximum.reduce([x0 - pts[:, 0], pts[:, 0] - x1, y0 - pts[:, 1], pts[:, 1] - y1])
                if len(pts) and float(d.max()) > p["foot_shift_m"]:
                    ref.fail("a step or shuffle before the take-off", foot=s, moved_m=round(float(d.max()), 3))
                    return False
            elif on[other] and ref.time - tr["last_on"][s] > p["two_foot_window_s"]:
                ref.fail("a foot left the ground before the take-off", foot=s,
                         for_s=round(ref.time - tr["last_on"][s], 3))
                return False
        return True

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        on = {s: ref.touching(self.sole[s], ref.ground) for s in SIDES}
        was_air = fl.air
        done = fl.update()
        if fl.air and not was_air:
            tr["at_t0"] = dict(tr["last_on"])
        for s in SIDES:
            if on[s]:
                tr["last_on"][s] = ref.time
        if not tr["jumped"]:
            if done is None:
                if not fl.air:
                    self._before_takeoff(w, ref, on)
                return
            tr["jumped"] = True                          # the first flight of at least min_air_s has landed
            apart = abs(tr["at_t0"]["left"] - tr["at_t0"]["right"])
            rise = done["apex_z"] - done["pelvis0"][2]
            ref.metrics["air_s"], ref.metrics["rise_m"] = done["air_s"], round(rise, 3)
            if apart > p["two_foot_window_s"]:
                return ref.fail("a foot left the ground before the take-off", feet_left_apart_s=round(apart, 3))
            if rise < p["rise_min_m"]:
                return ref.fail("the flight was not a jump", rise_m=round(rise, 3))
            ref.stage("take-off", air_s=done["air_s"], rise_m=round(rise, 3))
            if not set(done["landing_parts"]) <= {"left_foot", "right_foot"}:
                return ref.fail("the landing was not on the feet", parts=done["landing_parts"])
            ref.stage("landing")
        if ref.has("stand") or ref.failed:
            return
        pts = ref.contact_points(self.robot, ref.ground)
        if len(pts):
            x = float(pts[:, 0].min())
            tr["mark"] = x if tr["mark"] is None else min(tr["mark"], x)
            ref.metrics["mark_m"] = round(tr["mark"], 3)
            if tr["mark"] < p["qualifying_mark_m"]:
                ref.fail("the jump is too short", mark_m=round(tr["mark"], 3))

    def step(self, w, ref):
        if ref.has("landing") and ref.hold("stand", ref.standing(), self.p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "takeoff_line_x": 0.0, "qualifying_mark_x": self.p["qualifying_mark_m"],
                "feet_front_x": max(span(w, self.foot_ids[s], (1.0, 0.0, 0.0))[1] for s in SIDES),
                "jumped": tr["jumped"], "mark_m": tr["mark"]}
