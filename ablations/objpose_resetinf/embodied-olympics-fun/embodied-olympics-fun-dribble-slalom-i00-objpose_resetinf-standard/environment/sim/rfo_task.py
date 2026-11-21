"""Slalom dribble: take a size-5 football through six cones 2 m apart, round the last one and back through them, the
ball always close and no cone touched."""
import numpy as np

from rfo.referee import Crossing
from rfo.scene import OFFICIAL
from rfo.task import TaskBase
# A rigid cone (PVC; its shell's flex not modelled)'s contact with the robot, the venue's fixtures and the other props
# (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py
# SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the
# robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its own bounce.
# With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 68 mm into the palm pad and 43 mm into
# the floor (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
ARMS = {"left_upper_arm", "left_forearm", "left_hand", "right_upper_arm", "right_forearm", "right_hand"}
N = 6


class Task(TaskBase):
    name = "dribble-slalom"
    title = "Football: slalom dribble"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("The slalom dribble of football skill tests (a line of cones, out through them, round the last and back "
                "through them, against the clock); it is a drill, not an event of the Laws: the course is six cones "
                "2 m apart with 90 s allowed. IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm "
                "round, 410-450 g) and for handling (Law 12: the hand or the arm)")
    deviations = [
        "The line the ball and the player must weave is made exact: the ball's centre and the robot's pelvis must "
        "each pass every cone on the prescribed side, judged where they cross the line through that cone square to "
        "the course; a tester's eye is replaced by these planes.",
        "The pitch is level and uniform (the official ball's rolling resistance), no wind.",
    ]
    time_limit_s = 90.0
    start = (0.0, 0.0, 0.0)
    stages = ([f"out {i + 1}" for i in range(N)] + [f"back {i + 1}" for i in reversed(range(N))] + ["finish"])
    fall_z = 0.35
    params = dict(cones=6, cone_spacing_m=2.0, first_cone_m=2.0, start_line_m=1.0, ball_ahead_m=0.5, control_m=2.0,
                  cone_height_m=0.30, cone_base_radius_m=0.11, fall_z_m=0.35)

    sentence = ("Dribble the football through the slalom: out through the six cones, round the last one and back "
                "through them over the start line, keeping the ball within 2 m and touching no cone.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg) lies {ball_ahead_m} m ahead of you, behind the start line, "
             "which is {start_line_m} m ahead of you and square to the way you face. Six cones ({cone_height_m} m "
             "high, base radius {cone_base_radius_m} m, free-standing) stand on the line you face along, the first "
             "{first_cone_m} m beyond the start line and then every {cone_spacing_m} m. Each cone has a plane "
             "through it, square to the course. On the way out the ball's centre and your pelvis must each cross "
             "the plane of cone 1 to its left (your left at the start), of cone 2 to its right, and so on in turn, "
             "cone 6 to its right; then round cone 6 and back: the plane of cone 6 to its other side (the left as "
             "seen from the start), of cone 5 to the right as seen from the start, and so on in turn, cone 1 to the "
             "right as seen from the start; and finally back over the start line, the whole ball and your pelvis. "
             "For each plane the first crossing in the direction of travel after the plane before it decides, for "
             "the ball and for you separately. You succeed when the whole ball and your pelvis are back over the "
             "start line after all twelve planes. You fail if the ball or you cross a plane on the wrong side, if "
             "the ball's centre is ever more than {control_m} m from your pelvis (measured along the ground), if "
             "you or the ball touch a cone, if a hand or an arm touches the ball (handball; any other part of you "
             "may play it), if you fall (your pelvis lower than {fall_z_m} m above the ground, or any part of you "
             "other than the feet on the ground), or after {time_limit_s} s.")
    venue = ("You face +x, down the line of cones, on level grass; the ball lies on the ground straight ahead of your "
             "pelvis and the start line is just beyond it. The last cone is {last_cone_m} m ahead of you. A yellow "
             "mark beside each cone shows the side to pass it on the way out.")
    difficulty = ("About 30 m of path with a tight turn in 90 s leaves little slack for a robot that walks at 0.6 m/s, "
                  "and its running policy does not know the ball. Every step that meets the ball kicks it, a 0.43 kg "
                  "ball kicked at walking speed rolls metres, and it has to be steered through gaps of 2 m without "
                  "the feet or the ball touching a cone.")

    def __init__(self):
        super().__init__()
        self._texts()

    def configure(self, params):
        super().configure(params)
        if int(self.p["cones"]) != N:
            raise ValueError("the slalom has six cones")
        self.fall_z = self.p["fall_z_m"]
        self._texts()

    def _texts(self):
        p = self.p
        last = p["start_line_m"] + p["first_cone_m"] + (N - 1) * p["cone_spacing_m"]
        self.venue = type(self).venue.replace("{last_cone_m}", f"{last:g}")

    # ------------------------------------------------------------------ the course
    def cones(self):
        """(x, the side to pass on the way out: +1 = y > 0, the left as seen from the start)."""
        p = self.p
        x0 = p["start_line_m"] + p["first_cone_m"]
        return [(x0 + i * p["cone_spacing_m"], 1 if i % 2 == 0 else -1) for i in range(N)]

    def gates(self):
        """The twelve planes in order: (stage, x, direction of travel, side)."""
        c = self.cones()
        out = [(f"out {i + 1}", x, 1, s) for i, (x, s) in enumerate(c)]
        back = [(f"back {i + 1}", c[i][0], -1, -c[i][1]) for i in reversed(range(N))]
        return out + back

    def build(self, sc):
        p = self.p
        c = self.cones()
        L = c[-1][0]
        sc.box("pitch", (L / 2, 0, 0.0003), (L / 2 + 4.0, 5.0, 0.0003), rgba=GRASS)
        sc.line("start_line", (p["start_line_m"], -2.0), (p["start_line_m"], 2.0))
        for i, (x, s) in enumerate(c):
            sc.cone(f"cone{i + 1}", x, 0.0, radius=p["cone_base_radius_m"], height=p["cone_height_m"], mass=0.4)
            sc.zone(f"side{i + 1}", (x, s * 0.6), (0.04, 0.25), rgba=(0.95, 0.85, 0.2, 0.7))
        for g in sc.wb.iter("geom"):                         # the cones: rigid PVC at a contact (RIGID)
            if (g.get("name") or "").startswith("cone") and g.get("contype", "0") != "0":
                g.attrib.update(RIGID)
        sc.ball("ball", "football", (p["ball_ahead_m"], 0.0, BALL["radius"]))
        sc.camera("venue", (L / 2, -9.5, 6.5), (L / 2, 0.0, 0.0), fovy=62)

    def reset(self, w):
        p = self.p
        w.put("ball", (p["ball_ahead_m"], 0.0, BALL["radius"]))
        for i, (x, _) in enumerate(self.cones()):
            w.put(f"cone{i + 1}", (x, 0.0, 0.0))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.arms = ref.part("arms")
        self.cone_geoms = [ref.geoms(body=f"cone{i + 1}") for i in range(N)]
        self.G = self.gates()
        line = p["start_line_m"]
        self.trackers = {
            "ball_planes": [Crossing((1, 0, 0), x, direction=d) for _, x, d, _ in self.G],
            "robot_planes": [Crossing((1, 0, 0), x, direction=d) for _, x, d, _ in self.G],
            "ball_home": Crossing((1, 0, 0), line - BALL["radius"], direction=-1),
            "robot_home": Crossing((1, 0, 0), line, direction=-1),
            "ball_i": 0, "robot_i": 0, "ball_done": False, "robot_done": False, "far": 0.0, "touches": 0, "on": False,
        }

    def digest(self):
        out = []
        for k, v in sorted(self.trackers.items()):
            out.append([k, [c.state() for c in v] if isinstance(v, list) else v.state() if hasattr(v, "state") else v])
        return out

    def _advance(self, ref, who: str, planes, i: int, pos):
        """Update one mover's plane crossings; returns its new index, or None after a failure."""
        for k, cr in enumerate(planes):
            x = cr.update(pos)
            if x is None or k != i:
                continue                              # only the next plane's first crossing decides
            name, _, _, side = self.G[k]
            if side * x[1] > 0:
                i += 1
            else:
                ref.fail(f"{who} passed a cone on the wrong side", plane=name, y=round(float(x[1]), 3))
                return None
        return i

    def substep(self, w, ref):
        tr = self.trackers
        on = ref.touching(self.ball, ref.robot_mask)
        if on and ref.touching(self.ball, self.arms):
            return ref.fail("handball", parts=sorted(ref.parts_touching(self.ball) & ARMS))
        if on and not tr["on"]:
            tr["touches"] += 1
        tr["on"] = on
        for i, cg in enumerate(self.cone_geoms):
            if ref.touching(cg, ref.robot_mask):
                return ref.fail(f"cone {i + 1} was touched", by=sorted(ref.parts_touching(cg)))
            if ref.touching(cg, self.ball):
                return ref.fail(f"cone {i + 1} was touched", by=["ball"])
        b, pel = w.pos("ball"), w.d.qpos[w.robot.fq:w.robot.fq + 3]
        bi = self._advance(ref, "the ball", tr["ball_planes"], tr["ball_i"], b)
        if bi is None:
            return
        ri = self._advance(ref, "the robot", tr["robot_planes"], tr["robot_i"], pel)
        if ri is None:
            return
        tr["ball_i"], tr["robot_i"] = bi, ri
        for k in range(len(ref.stages), min(bi, ri)):
            ref.stage(self.G[k][0])
        hb, hr = tr["ball_home"].update(b), tr["robot_home"].update(pel)
        n = len(self.G)
        if bi == n and hb is not None:
            tr["ball_done"] = True
        if ri == n and hr is not None:
            tr["robot_done"] = True
        if tr["ball_done"] and tr["robot_done"]:
            if ref.stage("finish"):
                ref.succeed()

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        b, pel = w.pos("ball"), w.pelvis()
        gap = float(np.hypot(b[0] - pel[0], b[1] - pel[1]))
        tr["far"] = max(tr["far"], gap)
        ref.metrics["planes_ball"], ref.metrics["planes_robot"] = tr["ball_i"], tr["robot_i"]
        ref.metrics["max_ball_distance_m"] = round(tr["far"], 3)
        ref.metrics["touches"] = tr["touches"]
        if gap > p["control_m"]:
            ref.fail("the ball got away from the robot", distance_m=round(gap, 3))

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "start_line_x": self.p["start_line_m"],
                "cones": [{"x": x, "y": 0.0, "out_side": "left (y > 0)" if s > 0 else "right (y < 0)"}
                          for x, s in self.cones()],
                "planes": [{"stage": n, "x": x, "direction": d, "side": "y > 0" if s > 0 else "y < 0"}
                           for n, x, d, s in self.G],
                "planes_passed_ball": int(tr.get("ball_i", 0)), "planes_passed_robot": int(tr.get("robot_i", 0))}
