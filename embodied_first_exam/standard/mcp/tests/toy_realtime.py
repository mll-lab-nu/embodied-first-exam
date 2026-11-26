"""Toy services for the MCP tests around a two-number toy robot (x moves by each row's first number; success when x
reaches 1): eai-standard/2.3 (realtime; realtime/rcb_realtime.py over a 2.1 rcb_service.py copy) or, with --standard,
eai-standard/2.1 (that rcb_service.py itself, a benchmark's own 2.1 service).

    RCB_DATA=/tmp/d python3 toy_realtime.py 8000 [--standard]
"""
import hashlib, importlib.util, pathlib, sys
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[4]
STD = ROOT / "embodied_first_exam/standard"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Toy:
    raw_dim = 2
    control_dt = 0.02
    max_control_steps = 10_000
    proprio_layout = ["x", "v"]
    cameras = ["top"]
    depth_cameras = []

    def __init__(self):
        self.x = 0.0
        self.v = 0.0

    def spec(self):
        return {"cameras": {"top": {"shape": [8, 8, 3]}},
                "action_types": {"joint_position": {"dim": 2, "layout": ["dx", "unused"]}}}

    def interpolable(self, t):
        return True

    def images(self, cams, depth):
        img = np.zeros((8, 8, 3), np.uint8)
        img[..., 0] = int(min(255, max(0, self.x * 200)))
        return {c: img.copy() for c in cams}, {}

    def proprio(self):
        return np.array([self.x, self.v], np.float32)

    def clip(self, t, rows):
        return np.clip(rows, -0.05, 0.05), []

    def to_sim(self, t, row):
        return np.asarray(row, float)

    def command(self, t):
        return np.zeros(2)

    def hold(self):
        return "joint_position", np.zeros(2)

    def step(self, row):
        self.v = float(row[0])
        self.x += self.v
        return self.x >= 1.0, self.x >= 1.0, {}

    def reset(self):
        self.x = self.v = 0.0

    def state_sha(self):
        return hashlib.sha256(np.array([self.x, self.v]).tobytes()).hexdigest()[:12]

    def save_trajectory(self, rows, path, meta):
        np.savez(path, actions=np.asarray(rows))

    def render_video(self, rows, path):
        open(path, "wb").write(b"mp4")


if __name__ == "__main__":
    sys.path.insert(0, str(STD))
    S = load(ROOT / "embodied_first_exam/benchmarks/humanoidbench/sim/rcb_service.py", "rcb_service")
    if "--standard" in sys.argv[2:]:
        S.main(Toy, int(sys.argv[1]))
    else:
        load(STD / "realtime/rcb_realtime.py", "rcb_realtime").main(Toy, int(sys.argv[1]))
