"""Launcher for test_server_requests.py: RoboTangle's real standard server.py on the real eai-standard/2.4 layer, with a
stub Session instead of the simulator (numpy only; no Genesis, no GPU).
usage: fake_service.py <sim dir> <data dir> <port> <gripper space: native | width>"""
import hashlib, json, os, runpy, sys, types
import numpy as np
SIM, DATA, PORT, SPACE = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
sys.path.insert(0, SIM)
os.environ.update(RCB_DATA=DATA, RCB_TASK="hedgehog_in_cage", RCB_INSTANCE=os.path.join(DATA, "instance.json"), RCB_SESSION_LOG="")
os.makedirs(DATA, exist_ok=True)
json.dump({"action_dim": 8}, open(os.environ["RCB_INSTANCE"], "w"))
import rcb_limited as L, rcb_topogym as M  # noqa: E402
_serve = L.serve
L.serve = lambda svc, port=PORT: _serve(svc, PORT)
NATIVE = SPACE == "native"
LAY = [f"joint{i}" for i in range(1, 8)] + ["arm_native_gripper" if NATIVE else "arm_gripper"]
WIDTH_OPEN = 0.085                      # the stub's pad gap: 0.085 m at the open drive target 0 rad, 0 at the closed target 0.8


class Frame:
    def __init__(s, depth):
        s.rgb = {"agentview": np.zeros((4, 6, 3), np.uint8)}; s.depth = {"agentview": np.ones((4, 6), np.float32)}
        s.camera_metadata = {"agentview": {"T_camera_cv_from_world": np.eye(4)}}


class Fake:
    def __init__(s, task, instance=None, strict=True, max_steps=None):
        s.task = task; s.control_hz = 40.0; s.physics_substeps = 10; s.VIDEO_CAMERAS = ("agentview",); s.gripper_space = SPACE
        s.runtime_binding = {"binding_id": "x"}; s.spec = {"text": "do it"}; s.max_steps = 100000; s.eval_index = 0
        s.instance_exact = True; s.instance_sha = "s0"
        s.robot = types.SimpleNamespace(arms=["arm"], arm_slice={"arm": slice(0, 7)}, grip_index={"arm": 7},
                                        limits=[(-2.9, 2.9)] * 7 + [(0.0, 0.8) if NATIVE else (0.0, WIDTH_OPEN)])
        s.action_layout = LAY; s.env = types.SimpleNamespace(sensor_frame=lambda depth=False: Frame(depth))
        s.monitor = types.SimpleNamespace(review=lambda: None, forcing=lambda: None)
        s._t = np.zeros(8); s.n_steps = 0; s.physics_steps = 0; s.sim_time_s = 0.0; s.last_step_ticks = 0; s.last_guard = None
        s.episode_end = None; s.episode_done = False; s._recording = None; s.instability = None

    def camera_info(s, cams=None):
        return {c: dict(intrinsic_cv=np.eye(3).tolist(), extrinsic_cv=np.eye(4)[:3].tolist(), cam2world_gl=np.eye(4).tolist(),
                        image_size=[6, 4], mount={"type": "static"}, depth_range_m=[0.1, 10]) for c in (cams or s.VIDEO_CAMERAS)}

    def robot_spec(s):
        g = {"opening_m": [0.0, WIDTH_OPEN]}
        if NATIVE:
            g.update(command_space="native", command_unit="rad", command_limits=[0.0, 0.8], open_target=0.0, closed_target=0.8)
        return {"name": "fake", "base": {"pose": [0, 0, 0, 1, 0, 0, 0]}, "grippers": {"arm": g}}

    def kinematics_spec(s):
        return dict(endpoint="/kinematics", joint_names=LAY[:7], frame="world", quaternion_order="wxyz", links=["arm_tcp"],
                    tcp_frames=["arm_tcp"], ee_frames=["arm_tcp"], ik_targets=["arm_tcp"])

    def joint_positions(s): return s._t.copy()       # the gripper entry in the instance's command space, as rcb_topogym
    def gripper_width(s, arm): return float(WIDTH_OPEN * (1 - s._t[7] / 0.8)) if NATIVE else float(s._t[7])
    def ee_pose(s, a): return np.zeros(3), np.array([1., 0, 0, 0])
    def hold_action(s): return s._t.copy()
    def joint_velocities(s): return np.zeros(8)
    def joint_efforts(s): return np.zeros(8)
    def safety(s, episode=False): return {}

    def step(s, action, _physics_steps=None):
        a = np.asarray(action, np.float32).reshape(-1)
        if s.episode_done: raise M.PrimitiveError("guard")
        if s.episode_end is not None: return True
        s._t = a.astype(np.float64); s.n_steps += 1; s.last_step_ticks = int(_physics_steps or 10)
        s.physics_steps += s.last_step_ticks; s.sim_time_s += 1 / 40
        if s._recording is not None: s._recording.append(a.copy())
        if s.n_steps >= s.max_steps: s.episode_done = True
        return s.episode_done

    def success(s): return False
    def state_sha(s): return hashlib.sha1(s._t.tobytes() + str(s.n_steps).encode()).hexdigest()[:16]
    def record_start(s): s._recording = []

    def record_stop(s):
        a = np.stack(s._recording) if s._recording else np.zeros((0, 8), np.float32); s._recording = None; return a

    def save_trajectory(s, acts, path, meta=None): np.savez(path, actions=acts, task=s.task, meta=json.dumps(meta or {}))
    def ik(s, arm, pos, q): return np.zeros(7), 0.0, 0.0
    def ik_jump(s, arm, qa): return 0.0, "joint1"
    def kinematics(s, req): return {"ok": True}


M.Session = Fake
sys.argv = [os.path.join(SIM, "server.py")]
runpy.run_path(os.path.join(SIM, "server.py"), run_name="__main__")
