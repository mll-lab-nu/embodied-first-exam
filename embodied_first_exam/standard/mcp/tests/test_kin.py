"""Kinematics in the adapter (owner decision D142), without a service (CPU, a few seconds): the two robot models the
manifests ship, robocasa365's PandaOmron and the Embodied Safety Exam's TidyBot, against values MuJoCo computed in their
simulator images; inverse kinematics round trips within the joint limits; and the adapter on stand-in robots: a pose goal
solved to the Panda's absolute joint targets (and ee rows of execute_trajectory), a pose goal and joint positions sent to
the TidyBot as per-step changes and corrected, the model's hand pose in the state, and a model the robot does not confirm
switched off (describe_robot says so, pose goals are refused). A joint-only part says it takes no pose.

    python3 embodied_first_exam/standard/mcp/tests/test_kin.py
"""
import json, os, pathlib, sys, tempfile
import numpy as np
MCP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP))
os.environ.setdefault("EFE_MCP_WORKSPACE", tempfile.mkdtemp(prefix="efe_mcp_kin_"))
import geom, kin, manifest  # noqa: E402
from rcb_adapter import RcbAdapter, ToolError  # noqa: E402

PANDA_START = [-14.6013, -5.13406, 0.0, 0.0, 0.0022, -1.06485, -0.01253, -2.24003, 0.03108, 1.50735, 0.70419]
TIDY_HOME = [0.0, -0.5239, np.pi, -2.0743, 0.0, -1.0677, np.pi / 2]


def resolved(suite, task):
    return manifest.resolve(json.loads((MCP / "manifests" / f"{suite}.json").read_text()), task)


def T_of(p, q):
    T = np.eye(4); T[:3, :3] = geom.q_to_mat(q); T[:3, 3] = p
    return T


class Res:
    def __init__(self, layout, now, extra=None):
        self.last, self.last_depth, self.depth = {}, {}, {}
        self.meta = {"proprio": {"layout": layout, "now": list(map(float, now))}, "time_left_s": 100.0,
                     "sim_time_s": 0.0, **(extra or {})}


class RC:
    class EpisodeOver(Exception):
        pass


def models():
    """The manifests' chains against MuJoCo, and inverse kinematics round trips."""
    P = resolved("robocasa365", "robocasa365-assemble-cooking-array-i00")["parts"]["arm"]["kin"]
    C = kin.Chain(P)
    T = C.fk(PANDA_START)
    # MuJoCo in the robocasa365 image, this scene's start: the grip site at (-4.89841, -14.59886, 1.31888) in the frame of
    # robot0_base, which stands at (10, 10, 0) turned as the base frame
    assert np.allclose(T[:3, 3], [-4.89841, -14.59886, 1.31888], atol=2e-5), T[:3, 3]
    B = resolved("embodied-safety-exam", "ese-a33-i01")["parts"]["arm"]["kin"]
    Ct = kin.Chain(B)
    # MuJoCo in the ESE image at the TidyBot's rest: the pinch point 0.26 m ahead of the base, 0.72 m up
    assert np.allclose(Ct.fk(TIDY_HOME)[:3, 3], [0.25999, 0.00135, 0.71997], atol=2e-5), Ct.fk(TIDY_HOME)[:3, 3]
    g = np.random.default_rng(7)
    for C_, home in ((C, PANDA_START), (Ct, TIDY_HOME)):
        for _ in range(25):
            q = np.array(home, float)
            qt = q.copy()
            qt[C_.idx] = np.clip(q[C_.idx] + g.normal(0, 0.4, len(C_.idx)), C_.lo[C_.idx], C_.hi[C_.idx])
            r = C_.ik(C_.fk(qt), q)
            assert r["ok"] and r["pos_err_m"] < 3e-4 and r["rot_err_rad"] < 3e-3, r
            assert np.all(r["q"][C_.idx] >= C_.lo[C_.idx] - 1e-9) and np.all(r["q"][C_.idx] <= C_.hi[C_.idx] + 1e-9)
            assert np.allclose(r["q"][~C_.solve], q[~C_.solve]), "the measured joints moved"
    far = C.fk(PANDA_START); far[:3, 3] += [3.0, 0, 0]
    assert not C.ik(far, PANDA_START, starts=2)["ok"]
    return C, Ct


def panda(C):
    m = resolved("robocasa365", "robocasa365-assemble-cooking-array-i00")
    names = [f"{n}_pos" for n in C.names] + ["gripper0_right_finger_joint1_pos", "gripper0_right_finger_joint2_pos"]
    acts = ["arm_joint1", "arm_joint2", "arm_joint3", "arm_joint4", "arm_joint5", "arm_joint6", "arm_joint7", "grip",
            "base_x", "base_y", "base_yaw", "torso", "hybrid_mode"]
    layout = names + ["eef_right_x", "eef_right_y", "eef_right_z"] + [f"cmd_{a}" for a in acts]
    root = geom.Frame([10.0, 10.0, 0.0], m["frame"]["base"]["fixed"][3:])
    sent = []

    class Robot:
        def __init__(self, eef_offset=0.0):
            self.q = np.array(PANDA_START, float)
            self.cmd = np.concatenate([self.q[4:], [-1.0, 0, 0, 0, 0, -1.0]])
            self.off = eef_offset

        def now(self):
            p = root.to_parent(C.fk(self.q)[:3, 3])[0] + [self.off, 0, 0]
            return np.concatenate([self.q, [0.02, -0.02], p, self.cmd])

        def get_obs(self, cameras=None, seconds=0.0, video="none", depth=None, include_depth=False):
            return Res(layout, self.now())

        def submit(self, typ, A, dt=None, interpolate="linear", cameras=None, video="none", note=""):
            assert typ == "joint_position" and A.shape[1] == 13, (typ, A.shape)
            sent.append(np.asarray(A))
            self.q[4:] = A[-1, :7]
            self.cmd = A[-1].copy()
            return Res(layout, self.now(), {"executed_rows": len(A)})

    def adapter(robot):
        a = RcbAdapter(json.loads(json.dumps(m)))
        a.r, a.rc, a.connect = robot, RC, (lambda: None)
        a.spec = {"control_dt": 0.05, "proprio_layout": layout, "cameras": {},
                  "action_types": {"joint_position": {"dim": 13, "layout": acts}}}
        return a

    a = adapter(Robot())
    d, _ = a.describe_robot()
    arm = d["parts"]["arm"]
    assert "inverse kinematics in these tools" in arm["end_effector"]["control"], arm
    assert "quaternion_wxyz" in d["state_now"]["parts"]["arm"]["ee"], d["state_now"]   # the model's orientation
    F = geom.Frame(m["frame"]["base"]["fixed"][:3], m["frame"]["base"]["fixed"][3:])
    qt = np.array(PANDA_START); qt[4:] += [0.3, 0.2, -0.2, 0.3, 0.1, -0.2, 0.4]
    ps, qs = root.to_parent(C.fk(qt)[:3, 3], geom.mat_to_q(C.fk(qt)[:3, :3]))
    p, q = F.from_parent(ps, qs)
    out, _ = a.move_robot(goals=[{"target": "arm", "position": list(p), "quaternion_wxyz": list(q)}])
    r = out["reached"][0]
    assert r["ok"] and r["position_error_m"] < 1e-3 and r["rotation_error_rad"] < 5e-3, out["reached"]
    assert sent and np.allclose(sent[-1][-1, 8:12], 0) and sent[-1][-1, 12] == -1.0, sent[-1][-1]   # the base holds
    # execute_trajectory space ee: a 6 cm line down, each row solved from the one before
    p0 = np.asarray(out["parts"]["arm"]["ee"]["position"]); q0 = out["parts"]["arm"]["ee"]["quaternion_wxyz"]
    rows = [{"arm": {"position": list(p0 + [0, 0, -0.01 * k]), "quaternion_wxyz": q0}} for k in range(1, 7)]
    out, _ = a.execute_trajectory(space="ee", rows=rows, dt=0.1)
    assert out["executed_rows"] == 6 and abs(out["parts"]["arm"]["ee"]["position"][2] - (p0[2] - 0.06)) < 1e-3, out["parts"]
    try:
        a.move_robot(goals=[{"target": "arm", "position": [3.0, 0.0, 0.5]}])
        raise AssertionError("an unreachable pose was accepted")
    except ToolError as e:
        assert e.category == "out_of_reach" and "no joint solution" in str(e), e
    # a model 2 cm from where the robot measures its hand: off, and said so
    b = adapter(Robot(eef_offset=0.02))
    d, _ = b.describe_robot()
    assert "off: the model puts the hand 20.0 mm" in d["parts"]["arm"]["pose_goals"], d["parts"]["arm"]
    try:
        b.move_robot(goals=[{"target": "arm", "position": list(p)}])
        raise AssertionError("a pose goal was accepted with the model off")
    except ToolError as e:
        assert "off for this part" in str(e), e
    return len(sent)


def tidybot(Ct):
    m = resolved("embodied-safety-exam", "ese-a33-i01")
    K = m["parts"]["arm"]["kin"]
    layout = ["base_x", "base_y", "base_yaw", "base_vx", "base_vy", "base_yaw_rate", *(f"arm_{i}" for i in range(1, 8)),
              *(f"arm_{i}_vel" for i in range(1, 8)), "gripper", "gripper_vel"]
    rows_sent = []

    class Robot:
        def __init__(self):
            self.base = np.array([0.4, -0.3, 0.6])
            self.q = np.array(TIDY_HOME, float)
            self.g = 0.0

        def now(self):
            return np.concatenate([self.base, [0, 0, 0], self.q, np.zeros(7), [self.g, 0.0]])

        def get_obs(self, cameras=None, seconds=0.0, video="none", include_depth=False):
            return Res(layout, self.now())

        def submit(self, typ, A, dt=None, interpolate="linear", cameras=None, video="none", note=""):
            assert typ == "delta" and A.shape[1] == 11, (typ, A.shape)
            for row in A:
                rows_sent.append(row.copy())
                assert np.all(np.abs(row[:10]) <= 0.1 + 1e-12), row
                self.q += 0.9 * row[3:10]          # each step's target is reached short: the lag the correction takes up
                self.g = row[10]
            return Res(layout, self.now(), {"executed_rows": len(A)})

    def adapter(spec_axis=None):
        a = RcbAdapter(json.loads(json.dumps(m)))
        a.r, a.rc, a.connect = Robot(), RC, (lambda: None)
        sol = [j for j in K["joints"] if j["solve"]]
        a.spec = {"control_dt": 0.1, "proprio_layout": layout, "cameras": {},
                  "action_types": {"delta": {"dim": 11, "layout": ["base_x", "base_y", "base_yaw",
                                                                   *(f"arm_{i}" for i in range(1, 8)), "gripper"]}},
                  "control": {"arm": {"axis": spec_axis or [j["axis"] for j in sol],
                                      "position_m": [j["point"] for j in sol], "tcp_at_zero_m": K["tcp"]["position"]}}}
        return a

    a = adapter()
    d, _ = a.describe_robot()
    arm = d["parts"]["arm"]
    assert "inverse kinematics in these tools" in arm["end_effector"]["control"] and arm["joints"]["count"] == 7, arm
    assert arm["joints"]["limits"][1] == [-2.24, 2.24] and "per-step changes" in arm["joints"]["command"], arm["joints"]
    ee0 = d["state_now"]["parts"]["arm"]["ee"]
    assert np.allclose(ee0["position"], [0.25999, 0.00135, 0.71997], atol=1e-4), ee0     # the base frame moves with the base
    qt = np.array(TIDY_HOME); qt += [0.4, 0.3, -0.2, 0.5, 0.2, 0.3, -0.3]
    Tt = Ct.fk(qt)
    out, _ = a.move_robot(goals=[{"target": "arm", "position": list(Tt[:3, 3]),
                                  "quaternion_wxyz": list(geom.mat_to_q(Tt[:3, :3])), "gripper": 1.0}])
    r = out["reached"][0]
    assert r["ok"] and r["position_error_m"] <= 0.01 and r["rotation_error_rad"] <= 0.05, out["reached"]
    assert rows_sent[-1][10] == 1.0 and np.allclose(np.asarray(rows_sent)[:, :3], 0), "the base moved or the grip was lost"
    n_pose = len(rows_sent)
    out, _ = a.move_robot(goals=[{"target": "arm", "joint_positions": TIDY_HOME}], duration_s=2.0)
    assert out["reached"][0]["ok"] and out["reached"][0]["joint_error_max"] <= 0.01, out["reached"]
    try:
        a.execute_trajectory(space="joint", rows=[{"arm": {"joint_positions": TIDY_HOME}}])
        raise AssertionError("absolute joint rows accepted for per-step joints")
    except ToolError as e:
        assert "per-step changes" in str(e), e
    # a spec whose arm is not the model's: the model is off
    bad = [j["axis"] for j in K["joints"]]; bad[1] = [0.0, -1.0, 0.0]
    b = adapter(spec_axis=bad)
    d, _ = b.describe_robot()
    assert "off: joint joint_2" in d["parts"]["arm"]["pose_goals"] and "ee" not in d["state_now"]["parts"]["arm"], d["parts"]
    return n_pose, len(rows_sent) - n_pose


def joint_only():
    m = resolved("vlabench", "vlabench-example")
    a = RcbAdapter(m)
    layout = ["j"]
    a.r, a.rc, a.connect = None, RC, (lambda: None)
    a.spec = {}
    a.obs = lambda *x, **k: Res(layout, [0.0])
    a.meta_now = lambda res: np.zeros(64)
    a.ref = lambda ref, now, meta=None: np.array([0.0, 0.0, 0.0, 1.0] + [0.0] * 60)
    d, _ = a.describe_robot()
    pg = {n: P.get("pose_goals") for n, P in d["parts"].items()}
    assert pg.get("arm") == "none: this part takes joint positions only (no inverse kinematics here)", d["parts"]
    import schema
    assert "no end-effector pose" in schema.part_lines(m), schema.part_lines(m)


def main():
    C, Ct = models()
    n = panda(C)
    tp, tj = tidybot(Ct)
    joint_only()
    print(f"ok kinematics: both models match MuJoCo, IK round trips within limits; PandaOmron pose goal and ee rows "
          f"({n} submits); TidyBot pose goal in {tp} and joint goal in {tj} per-step rows with correction; mismatched "
          "models off; joint-only parts say so")


if __name__ == "__main__":
    main()
