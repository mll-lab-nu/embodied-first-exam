"""Adapter details without a service (CPU, < 1 s): intrinsics from a MuJoCo-style camera's vertical field of view, and
observe(depth=True) on cameras the spec says have no depth (the request goes without depth, the result names them).

    python3 embodied_first_exam/standard/mcp/tests/test_adapter_units.py
"""
import pathlib, sys
import numpy as np
MCP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP))
import geom  # noqa: E402
from rcb_adapter import RcbAdapter  # noqa: E402


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


if __name__ == "__main__":
    main()
