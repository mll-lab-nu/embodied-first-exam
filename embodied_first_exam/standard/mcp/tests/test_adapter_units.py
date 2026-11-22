"""Adapter details without a service (CPU, < 1 s): intrinsics from a MuJoCo-style camera's vertical field of view,
observe(depth=True) on cameras the spec says have no depth (the request goes without depth, the result names them), and
locate (D141): pixels of a depth camera back-projected into the robot base frame against a ray-cast plane, with its
errors for a camera without depth, without a pose, a pixel outside the image and one without a reading.

    python3 embodied_first_exam/standard/mcp/tests/test_adapter_units.py
"""
import os, pathlib, sys, tempfile
import numpy as np
MCP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP))
os.environ.setdefault("EFE_MCP_WORKSPACE", tempfile.mkdtemp(prefix="efe_mcp_units_"))
import geom  # noqa: E402
from rcb_adapter import RcbAdapter, ToolError  # noqa: E402


class Res:
    def __init__(self):
        self.meta = {}


class Sent(Exception):
    pass


def main():
    a = RcbAdapter({"manifest": "efe-mcp-manifest/0", "suite": "t", "kind": "rcb", "parts": {}, "cameras": ["head", "rgbd"]})
    a.spec = {"cameras": {"head": {"rgb": True, "depth": False, "mounted": "head", "hw": [84, 84], "fovy_deg": 60.0},
                          "rgbd": {"rgb": True, "depth": True, "mounted": "static", "resolution": [8, 8],
                                   "intrinsic_cv": [[8, 0, 4], [0, 8, 4], [0, 0, 1]]}}}
    F = geom.Frame()
    K = a.cam_meta(Res(), "head", F)["K"]
    f = 42.0 / np.tan(np.radians(30.0))
    assert abs(K[0][0] - f) < 1e-3 and abs(K[1][1] - f) < 1e-3 and K[0][2] == 42.0 and K[1][2] == 42.0, K
    assert "T_base_cam_cv" not in a.cam_meta(Res(), "head", F)         # a camera on a link: no fixed pose
    sent = []

    class Robot:
        def get_obs(self, cameras=None, seconds=0.0, video="none", include_depth=False):
            sent.append({"cameras": cameras, "include_depth": include_depth})
            raise Sent()

    class RC:
        class EpisodeOver(Exception):
            pass

    a.r, a.rc, a.connect, a.cams_all = Robot(), RC, (lambda: None), (lambda: ["head", "rgbd"])
    for cams, want in ((["head"], False), (["head", "rgbd"], True), (["rgbd"], True)):
        try:
            a.observe(cameras=cams, depth=True)
        except Sent:
            pass
        assert sent[-1]["include_depth"] is want, (cams, sent[-1])
    print("ok adapter units: K from fovy", [round(x, 3) for x in K[0]], "| depth requests", [s["include_depth"] for s in sent])
    locate_units()


def locate_units():
    """A camera 1.2 m above the suite's floor, tilted 30 degrees, looking at the plane z = 0; the base frame is the
    suite frame moved and turned (yaw 90 degrees), so each located point is the ray's hit expressed in the base frame."""
    W, H = 64, 48
    K = np.array([[50.0, 0, 31.5], [0, 50.0, 23.5], [0, 0, 1]])
    th = np.radians(30.0)                                   # the camera's z (forward) down and ahead, OpenCV axes
    R = np.column_stack([[1, 0, 0], [0, -np.sin(th), -np.cos(th)], [0, np.cos(th), -np.sin(th)]])
    c = np.array([0.3, -0.4, 1.2])
    T_sc = np.eye(4); T_sc[:3, :3] = R; T_sc[:3, 3] = c
    E = np.linalg.inv(T_sc)[:3]                             # extrinsic_cv: suite -> camera
    uu, vv = np.meshgrid(np.arange(W, dtype=float), np.arange(H, dtype=float))
    rays = np.linalg.inv(K) @ np.stack([uu.ravel(), vv.ravel(), np.ones(W * H)])
    ds = R @ rays
    t = -c[2] / ds[2]                                       # the ray's cam-z component is 1: t is the z-depth
    depth = t.reshape(H, W).astype(np.float32)
    depth[10, 20] = 0.0                                     # a dropout, with neighbours
    depth[30:35, 40:45] = 0.0                               # a hole wider than the window
    base = [0.5, 0.2, 0.0] + list(geom.yaw_q(np.pi / 2))

    def hit(u, v):
        r = np.linalg.inv(K) @ np.array([u, v, 1.0])
        p = c + (-c[2] / (R @ r)[2]) * (R @ r)
        return geom.Frame(base[:3], base[3:]).from_parent(p)[0]

    class Res:
        def __init__(self, d, cams_meta):
            self.last = {"rgbd": np.zeros((H, W, 3), np.uint8), "head": np.zeros((H, W, 3), np.uint8)}
            self.last_depth = {"rgbd": d} if d is not None else {}
            self.meta = {"cameras": cams_meta, "proprio": {"now": []}, "time_left_s": 100.0, "sim_time_s": 1.0}

    calls = []

    def adapter(d=depth, meta=None, spec_depth=True):
        a = RcbAdapter({"manifest": "efe-mcp-manifest/0", "suite": "t", "kind": "rcb", "parts": {},
                        "cameras": ["rgbd", "head", "wrist"], "frame": {"base": {"fixed": base}}})
        a.spec = {"cameras": {"rgbd": {"rgb": True, "depth": spec_depth}, "head": {"rgb": True, "depth": False},
                              "wrist": {"rgb": True, "depth": True}}}

        class Robot:
            def get_obs(self, cameras=None, seconds=0.0, video="none", depth=False):
                calls.append({"cameras": cameras, "depth": depth, "seconds": seconds})
                return Res(d, meta if meta is not None else {"rgbd": {"intrinsic_cv": K.tolist(), "extrinsic_cv": E.tolist()}})

        class RC:
            class EpisodeOver(Exception):
                pass
        a.r, a.rc, a.connect = Robot(), RC, (lambda: None)
        return a

    a = adapter()
    out, _ = a.locate(camera="rgbd", u=12.0, v=40.0)
    assert calls[-1] == {"cameras": ["rgbd"], "depth": True, "seconds": 0.0}, calls[-1]
    assert np.allclose(out["position"], hit(12.0, 40.0), atol=2e-4), (out["position"], hit(12.0, 40.0))
    assert np.allclose(out["camera_position"], geom.Frame(base[:3], base[3:]).from_parent(c)[0], atol=1e-4), out
    assert out["image"].endswith(".jpg") and out["image_size"] == [W, H] and "time_left_s" in out, out
    px = [[20.0, 10.0], [42.0, 32.0], [63.0, 47.0], [64.0, 3.0], [0.0, 0.0]]
    out, _ = a.locate(camera="rgbd", pixels=px)
    P = out["points"]
    assert np.allclose(P[0]["position"], hit(20.0, 10.0), atol=2e-4) and P[0]["readings"] == 8, P[0]   # the window
    assert "no depth reading" in P[1]["error"] and "outside the image" in P[3]["error"], P
    for k in (2, 4):                                        # at the border: the pixel alone (a centred window)
        assert np.allclose(P[k]["position"], hit(*px[k]), atol=2e-4) and P[k]["readings"] == 1, (k, P[k])
    out, _ = a.locate(camera="rgbd", pixels=[[33.0, 21.0]], window_px=0)
    assert np.allclose(out["points"][0]["position"], hit(33.0, 21.0), atol=2e-4), out
    # depth at half the image's size: sampled at the scaled pixel, back-projected with the image's K
    half = depth[::2, ::2].copy()
    out, _ = adapter(d=half).locate(camera="rgbd", u=30.0, v=20.0, window_px=0)
    assert np.allclose(out["position"], hit(30.0, 20.0), atol=1e-6 + 2e-2), out
    errs = []
    for kw, a2 in ((dict(camera="head", u=1, v=1), adapter()),                       # the spec: no depth
                   (dict(camera="rgbd", u=1, v=1), adapter(d=None)),                 # the service sent none
                   (dict(camera="rgbd", u=1, v=1), adapter(meta={"rgbd": {"intrinsic_cv": K.tolist()}})),   # no pose
                   (dict(camera="rgbd", u=42, v=32), adapter()),                     # no reading there
                   (dict(camera="rgbd", u=1), adapter()),
                   (dict(camera="nope", u=1, v=1), adapter())):
        try:
            a2.locate(**kw)
            raise AssertionError(f"no error for {kw}")
        except ToolError as e:
            errs.append((e.category, str(e)))
    assert errs[0][0] == "no_depth" and "has no depth" in errs[0][1] and "rgbd" in errs[0][1], errs[0]
    assert errs[1][0] == "no_depth" and errs[2][0] == "no_calibration" and "pose" in errs[2][1], errs[1:3]
    assert errs[3][0] == "no_depth" and "u and v" in errs[4][1] and "unknown camera" in errs[5][1], errs[3:]
    print("ok locate: points on the plane within 0.2 mm, window median over a dropout, half-size depth;",
          "errors:", ", ".join(e[0] for e in errs))


if __name__ == "__main__":
    main()
