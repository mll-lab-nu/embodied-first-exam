#!/usr/bin/env python3
"""RoboSafeBench 0.5.4's `ee_pose` quaternion rule in RCB's service (closes known issue 28 of
docs/benchmarks/robosafe.md): a /submit whose rows as sent have a quaternion that is not finite or off unit length by
more than 0.01 is refused whole with a 400 before anything runs, and counted in `requests_refused`; within 0.01 the
rows run (the episode normalises them). Interpolated rows go the shorter way (each row's quaternion takes the sign of
the row before it, the first row's of the row in force). The standard service (server.py) and the standard-realtime one (rcb_rsb_rt.py)
are driven here with a stand-in for the RoboSafeBench episode (numpy only: no simulator).

    python3 scripts/robosafe/tests/test_quaternions.py
"""
import json
import math
import pathlib
import sys
import tempfile
import unittest

import numpy as np

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "shared/standard"))
sys.path.append(str(HERE / "shared/realtime"))
import rcb1  # noqa: E402
import rcb_realtime  # noqa: E402
import rcb_rsb  # noqa: E402
import rcb_service  # noqa: E402
import server  # noqa: E402  (patches rcb_service.Service: the note, the quaternion rule, requests_refused)

RULE = "ee_pose quaternions must be unit (|‖q‖−1| ≤ 0.01)"
ONE = [p + k for p in ("",) for k in ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")]
TWO = [p + k for p in ("left_", "right_") for k in ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")]


def types_of(layout):
    d = len(layout)
    return {"joint_position": {"dim": 7, "layout": [f"j{i}" for i in range(6)] + ["gripper"], "lower": [-6.3] * 6 + [0.0],
                               "upper": [6.3] * 6 + [1.0], "units": "rad", "semantics": "joints", "interpolable": True},
            "ee_pose": {"dim": d, "layout": layout, "lower": ([-0.8, -0.6, 0.0, -1, -1, -1, -1, 0.0] * (d // 8)),
                        "upper": ([0.8, 0.6, 0.95, 1, 1, 1, 1, 1.0] * (d // 8)), "units": "m; quaternion w, x, y, z",
                        "semantics": "the pose of the tool centre point", "interpolable": True},
            "done": {"dim": 0, "layout": [], "lower": [], "upper": [], "units": "", "semantics": "exit", "text": True}}


class StandIn:
    """server.RoboSafe's side of the Sim contract without RoboSafeBench: counts the control steps it runs."""
    control_dt, max_control_steps = 0.02, 5000
    robot = "ur5e_2f85"                           # RT picture-cost table needs the adapter robot identity
    cameras, depth_cameras, proprio_layout = ("front",), (), ["t"]
    raw_dim = 17                                   # [type index, the row padded to the widest type (two arms: 16)]

    def __init__(self, layout=ONE):
        self.types = types_of(layout)
        self.steps, self.cmd = [], {}
        self.call_notes, self.pending, self.on_render = {}, [0, 0], None

    def spec(self):
        return {"simulator": "stand-in", "robot": "arm", "task_text": "-", "episode": "-",
                "action_types": {k: dict(v) for k, v in self.types.items()}, "cameras": {"front": {}}}

    def interpolable(self, typ):
        return bool(self.types[typ].get("interpolable"))

    def images(self, cameras, depth):
        return {c: np.zeros((2, 2, 3), np.uint8) for c in cameras}, {}

    def proprio(self):
        return np.array([len(self.steps)], np.float32)

    align_from = None
    clip = server.RoboSafe.clip                    # the adapter's own clip: it aligns quaternions before interpolation

    def _clip(self, typ, rows):
        return np.asarray(rows, np.float64), []

    def to_sim(self, typ, row):
        out = np.zeros(self.raw_dim)
        out[0] = list(self.types).index(typ)
        out[1:1 + len(row)] = row
        return out

    def command(self, typ):
        return self.cmd.get(typ, np.zeros(int(self.types[typ]["dim"])))

    def hold(self):
        return "joint_position", np.zeros(7)

    def step(self, raw):
        self.steps.append(raw)
        typ = list(self.types)[int(raw[0])]
        self.cmd[typ] = np.asarray(raw[1:1 + int(self.types[typ]["dim"])], np.float64)    # the row in force
        return False, False, {}

    def state_sha(self):
        return f"{len(self.steps):08d}"

    # server.py's additions
    def begin_submit(self, note):
        pass

    def end_submit(self):
        pass

    def last_operator_answer(self):
        return None

    def take_messages(self):
        return []

    def take_results(self):
        return {}

    def live_pass(self):
        return False

    def agent_called(self, images):
        pass


def unit_rows(n, arms=1):
    q = np.array([0.5, 0.5, -0.5, 0.5])
    out = []
    for i in range(n):
        out.append(np.concatenate([np.r_[0.1, -0.1, 0.3 + 0.001 * i, q, 0.0] for _ in range(arms)]))
    return np.array(out)


def with_quat(rows, i, q, arm=0):
    rows = rows.copy()
    rows[i, 8 * arm + 3:8 * arm + 7] = q
    return rows


def scaled(n):
    return np.array([0.5, 0.5, -0.5, 0.5]) * n


CASES = {  # quaternion -> refused?
    "zero": ([0.0, 0.0, 0.0, 0.0], True),
    "near_zero_delta": ([0.0, 0.0, 0.02, 0.0], True),
    "1e-7": (scaled(1e-7), True),
    "0.99": (scaled(0.99), False),
    "1.01": (scaled(1.01), False),
    "0.989": (scaled(0.989), True),
    "1.011": (scaled(1.011), True),
    "nan": ([math.nan, 0.0, 0.0, 1.0], True),
    "inf": ([math.inf, 0.0, 0.0, 0.0], True),
    "unit": (scaled(1.0), False),
}


class Rule(unittest.TestCase):
    def test_one_row(self):
        t = types_of(ONE)
        for name, (q, refused) in CASES.items():
            msg = rcb_rsb.quaternion_refusal(t, "ee_pose", with_quat(unit_rows(1), 0, q))
            self.assertEqual(bool(msg), refused, name)
            if refused:
                self.assertTrue(msg.startswith("row 0:") and RULE in msg and "Nothing was executed" in msg, msg)

    def test_the_norm_is_in_the_message(self):
        t = types_of(ONE)
        msg = rcb_rsb.quaternion_refusal(t, "ee_pose", with_quat(unit_rows(5), 3, scaled(0.95)))
        self.assertIn("row 3:", msg)
        self.assertIn("= 0.95;", msg)
        self.assertIn("= nan;", rcb_rsb.quaternion_refusal(t, "ee_pose", with_quat(unit_rows(2), 1, CASES["nan"][0])))

    def test_other_types_and_malformed_rows_are_the_layers(self):
        t = types_of(ONE)
        self.assertIsNone(rcb_rsb.quaternion_refusal(t, "joint_position", np.zeros((3, 7))))
        self.assertIsNone(rcb_rsb.quaternion_refusal(t, "ee_pose", np.zeros((3, 7))))      # wrong width
        self.assertIsNone(rcb_rsb.quaternion_refusal(t, "ee_pose", "abc"))
        self.assertIsNone(rcb_rsb.quaternion_refusal(t, "ee_pose", [[1, 2], [3]]))
        self.assertIsNone(rcb_rsb.quaternion_refusal(t, "nope", np.zeros((1, 8))))

    def test_two_arms_name_the_arm(self):
        t = types_of(TWO)
        self.assertEqual(rcb_rsb.quaternion_columns(t["ee_pose"]), [("left_", 3), ("right_", 11)])
        msg = rcb_rsb.quaternion_refusal(t, "ee_pose", with_quat(unit_rows(4, 2), 2, scaled(0.5), arm=1))
        self.assertTrue(msg.startswith("row 2 (right arm):"), msg)
        self.assertIsNone(rcb_rsb.quaternion_refusal(t, "ee_pose", unit_rows(4, 2)))

    def test_mixed_rows_count_the_rest(self):
        t = types_of(ONE)
        rows = unit_rows(10)
        for i in (2, 5, 9):
            rows = with_quat(rows, i, [0.0, 0.0, 0.02, 0.0])
        msg = rcb_rsb.quaternion_refusal(t, "ee_pose", rows)
        self.assertTrue(msg.startswith("row 2:") and "3 of the request's 10 rows are off" in msg, msg)

    def test_the_sentence_matches_robosafebench(self):
        self.assertIn("0.01", rcb_rsb.QUAT_SENTENCE)
        self.assertIn("refuses the whole call and nothing is executed", rcb_rsb.QUAT_SENTENCE)


class StandardService(unittest.TestCase):
    """The standard service (server.py on rcb_service) around the stand-in; no tests of its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sim = StandIn()
        self.svc = rcb_service.Service(self.sim, data=self.tmp.name, wall_clock_s=3600)
        self.svc.start()

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, rows, dt=0.02, typ="ee_pose"):
        body = rcb1.encode({"type": typ, "dt": dt, "video": "none", "cameras": []},
                           [rcb1.array_part("actions", np.asarray(rows, np.float64))])
        code, ctype, out = self.svc.handle("POST", "/submit", body)
        return code, (rcb1.decode(out)[0] if ctype == "application/x-rcb1" else json.loads(out))

    def final(self):
        return json.loads(pathlib.Path(self.tmp.name, "final.json").read_text())


class Standard(StandardService):
    def test_each_case(self):
        for name, (q, refused) in CASES.items():
            before = len(self.sim.steps)
            code, meta = self.submit(with_quat(unit_rows(6), 4, q))
            if refused:
                self.assertEqual(code, 400, name)
                self.assertTrue(meta["error"].startswith("row 4:") and RULE in meta["error"], meta)
                self.assertEqual(len(self.sim.steps), before, f"{name}: nothing may run")
            else:
                self.assertEqual(code, 200, (name, meta))
                self.assertEqual(len(self.sim.steps), before + 6, name)
        n_refused = sum(r for _, r in CASES.values())
        self.assertEqual(self.final()["requests_refused"], n_refused)
        events = [json.loads(line) for line in pathlib.Path(self.tmp.name, "episode.jsonl").read_text().splitlines()]
        logged = [e for e in events if e["ev"] == "refused"]
        self.assertEqual(len(logged), n_refused)
        self.assertTrue(all(e["code"] == 400 and RULE in e["error"] for e in logged))

    def test_a_mixed_call_refuses_whole_even_with_interpolation(self):
        rows = with_quat(unit_rows(20), 13, [0.0, 0.0, 0.02, 0.0])
        code, meta = self.submit(rows, dt=0.1)
        self.assertEqual(code, 400)
        self.assertTrue(meta["error"].startswith("row 13:"), meta)
        self.assertEqual(self.sim.steps, [])
        code, meta = self.submit(unit_rows(20), dt=0.1)              # the same, fixed: 20 rows x 5 steps run
        self.assertEqual((code, len(self.sim.steps)), (200, 100))
        self.assertEqual(self.final()["requests_refused"], 1)

    def test_other_refusals_are_counted_too_and_survive_a_restart(self):
        code, _ = self.submit(np.zeros((2, 5)))                      # wrong shape: the layer's 400
        self.assertEqual(code, 400)
        self.assertEqual(self.svc.handle("POST", "/nope", b"")[0], 404)
        self.assertEqual(self.final()["requests_refused"], 2)
        again = rcb_service.Service(StandIn(), data=self.tmp.name, wall_clock_s=3600)
        again.start()                                                # resumed from DATA: the count is recounted
        self.assertEqual(json.loads(pathlib.Path(self.tmp.name, "final.json").read_text())["requests_refused"], 2)

    def test_joint_rows_are_not_checked(self):
        code, _ = self.submit(np.zeros((3, 7)), typ="joint_position")
        self.assertEqual((code, len(self.sim.steps)), (200, 3))

    def test_the_spec_states_the_rule(self):
        class Api:
            pass

        class Me:
            types = types_of(ONE)
            instance = {"robot_title": "arm", "task_text": "-"}
            max_control_steps, cameras, camera_spec = 10, ("front",), {}

            class s:
                api = Api()
        spec = server.RoboSafe.spec(Me())
        self.assertIn(rcb_rsb.QUAT_SENTENCE, spec["action_types"]["ee_pose"]["semantics"])
        self.assertNotIn(rcb_rsb.QUAT_SENTENCE, spec["action_types"]["joint_position"]["semantics"])
        Me.types = types_of(ONE)                                     # an image whose RoboSafeBench states it already
        Me.types["ee_pose"]["semantics"] += " " + rcb_rsb.QUAT_SENTENCE
        spec = server.RoboSafe.spec(Me())
        self.assertEqual(spec["action_types"]["ee_pose"]["semantics"].count(rcb_rsb.QUAT_SENTENCE), 1)


class RealtimeService(unittest.TestCase):
    """rcb_rsb_rt's service around the stand-in; no tests of its own."""

    def setUp(self):
        import rcb_rsb_rt
        self.tmp = tempfile.TemporaryDirectory()
        RtService, _ = rcb_rsb_rt.build_service()
        self.sim = StandIn()
        self.svc = RtService(self.sim, data=self.tmp.name, wall_clock_s=3600)

    def tearDown(self):
        self.tmp.cleanup()

    def front(self, rows, typ="ee_pose"):
        body = rcb1.encode({"type": typ, "video": "none", "cameras": []},
                           [rcb1.array_part("actions", np.asarray(rows, np.float64))])
        return self.svc.front("POST", "/submit", len(body), lambda n: body)


class Realtime(RealtimeService):
    """The check runs in front() (off the clock), the refusal counted in requests_refused."""

    def test_refused_before_the_simulator_thread(self):
        for name, (q, refused) in CASES.items():
            out = self.front(with_quat(unit_rows(6), 1, q))
            if refused:
                self.assertEqual(out[:2], ("reply", 400), name)
                self.assertIn(RULE, json.loads(out[3])["error"])
            else:
                self.assertEqual(out[0], "/submit", name)              # handed to the simulator thread
        self.assertEqual(self.svc.requests_refused, sum(r for _, r in CASES.values()))
        self.assertEqual(self.sim.steps, [])

    def test_two_arms(self):
        self.svc.types = types_of(TWO)
        out = self.front(with_quat(unit_rows(3, 2), 0, scaled(1.05), arm=0))
        self.assertEqual(out[:2], ("reply", 400))
        self.assertTrue(json.loads(out[3])["error"].startswith("row 0 (left arm):"))


# ---- interpolated the shorter way (0.5.4 follow-up) -----------------------------------------------------------------
Q0 = np.array([0.5, 0.5, -0.5, 0.5])


def turn_z(deg, q=Q0):
    h = math.radians(deg) / 2
    a, b = np.array([math.cos(h), 0.0, 0.0, math.sin(h)]), q
    return np.array([a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3], a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
                     a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1], a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]])


def pose(q):
    return np.r_[0.1, -0.1, 0.3, q, 0.0]


def quats(steps):
    return [np.asarray(s[1 + 3:1 + 7]) for s in steps]


class Align(unittest.TestCase):
    def test_the_rule(self):
        t = types_of(ONE)["ee_pose"]
        rows, n = rcb_rsb.align_quaternions(t, [pose(-Q0), pose(Q0)], pose(Q0))
        self.assertEqual(n, 1)
        self.assertTrue(np.array_equal(rows[0][3:7], Q0) and np.array_equal(rows[1][3:7], Q0))
        ortho = np.array([0.5, -0.5, 0.5, 0.5])                     # dot with Q0 exactly 0: left as sent
        self.assertEqual(float(np.dot(Q0, ortho)), 0.0)
        rows, n = rcb_rsb.align_quaternions(t, [pose(ortho)], pose(Q0))
        self.assertEqual(n, 0)
        two = types_of(TWO)["ee_pose"]
        rows, n = rcb_rsb.align_quaternions(two, [np.r_[pose(Q0), pose(-Q0)]], np.r_[pose(Q0), pose(Q0)])
        self.assertEqual(n, 1)
        self.assertTrue(np.array_equal(rows[0][11:15], Q0))

    def test_the_spec_says_it(self):
        self.assertEqual(rcb_rsb.QUAT_SHORT, "q and \u2212q are the same orientation; rows are interpolated along the shorter way.")


class StandardShorterWay(StandardService):
    def go(self, rows, dt):
        self.sim.cmd["ee_pose"] = pose(Q0)                           # the row in force
        before = len(self.sim.steps)
        code, meta = self.submit(np.array(rows), dt=dt)
        self.assertEqual(code, 200, meta)
        return self.sim.steps[before:]

    def test_minus_q_holds(self):
        steps = self.go([pose(-Q0)], 0.1)
        self.assertEqual(len(steps), 5)
        self.assertTrue(all(np.array_equal(q, Q0) for q in quats(steps)))       # never through zero

    def test_one_row_per_step_is_left_as_sent(self):
        steps = self.go([pose(-Q0)], 0.02)
        self.assertTrue(np.array_equal(quats(steps)[0], -Q0))

    def test_a_dot_of_exactly_zero_is_interpolated_as_sent(self):
        ortho = np.array([0.5, -0.5, 0.5, 0.5])
        steps = self.go([pose(ortho)], 0.1)
        self.assertTrue(np.array_equal(quats(steps)[-1], ortho))
        self.assertGreater(min(np.linalg.norm(q) for q in quats(steps)), 0.70)

    def test_a_half_turn_in_two_rows_with_either_sign(self):
        runs = []
        for sign in (1.0, -1.0):
            steps = self.go([pose(turn_z(90)), pose(sign * turn_z(180))], 0.1)
            self.assertEqual(len(steps), 10)
            self.assertGreater(min(np.linalg.norm(q) for q in quats(steps)), 0.92)
            runs.append(np.array(quats(steps)))
        self.assertTrue(np.array_equal(runs[0], runs[1]))

    def test_the_saved_actions_stay_as_sent(self):
        self.go([pose(-Q0)], 0.1)
        saved = sorted(pathlib.Path(self.tmp.name, "calls").glob("*/actions.npy"))[-1]
        self.assertTrue(np.array_equal(np.load(saved)[0][3:7], -Q0))


class RealtimeShorterWay(RealtimeService):
    def plan_of(self, rows, dt):
        self.sim.cmd["ee_pose"] = pose(Q0)
        body = rcb1.encode({"type": "ee_pose", "dt": dt, "video": "none", "cameras": []},
                           [rcb1.array_part("actions", np.asarray(rows, np.float64))])
        route, req = self.svc.front("POST", "/submit", len(body), lambda n: body)
        self.assertEqual(route, "/submit")
        self.svc._rt_submit(req, rcb_realtime._Job("POST", "/submit"))
        return [np.asarray(row)[3:7] for t, row, _ in self.svc.plan if t == "ee_pose"]

    def test_minus_q_holds(self):
        plan = self.plan_of([pose(-Q0)], 0.1)
        self.assertEqual(len(plan), 5)
        self.assertTrue(all(np.array_equal(q, Q0) for q in plan))
        self.assertIsNone(self.sim.align_from)

    def test_a_half_turn_in_two_rows_with_either_sign(self):
        a = self.plan_of([pose(turn_z(90)), pose(turn_z(180))], 0.1)
        self.svc.plan.clear()
        b = self.plan_of([pose(turn_z(90)), pose(-turn_z(180))], 0.1)
        self.assertTrue(np.array_equal(np.array(a), np.array(b)))
        self.assertGreater(min(np.linalg.norm(q) for q in a), 0.92)


if __name__ == "__main__":
    unittest.main(verbosity=2)
