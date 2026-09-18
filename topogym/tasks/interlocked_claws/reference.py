"""Pinned recorded source motion; poses follow the original viewer semantics."""
import hashlib
import json
from pathlib import Path

import numpy as np

from .geometry import ASSET_ROOT, load_reference, reference_body_poses

ROOT = Path(__file__).resolve().parents[3]
MOTION_PATH = ASSET_ROOT / "recorded_motion.json"
MOTION_SHA256 = "81a29452b8eaba16bdd9515c5f36731e33e50ef36b7640d6e53bff977038e727"


class ReferenceMotion:
    def __init__(self, path=MOTION_PATH):
        self.path = Path(path)
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != MOTION_SHA256:
            raise ValueError("Pinned motion bytes do not match the verified source")
        self.source = json.loads(self.path.read_text())
        self.reference = load_reference()
        self.times = np.asarray(self.source["time_s"])
        self.qpos = np.asarray(self.source["qpos"])
        if (self.source["source_manifest_sha256"] != self.reference["source_manifest_sha256"]
                or len(self.times) != len(self.qpos) or self.qpos.shape[1] != 16
                or not np.isfinite(self.qpos).all() or not np.all(np.diff(self.times) > 0)):
            raise ValueError("Invalid or mismatched pinned reference motion")
        self.duration = float(self.times[-1])
        self.grasps = [np.asarray(p["inverse_grasp_column_major"]).reshape(4, 4, order="F")
                       for p in self.reference["pieces"]]
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def control(self, seconds):
        t = float(np.clip(seconds, 0, self.duration))
        i = min(int(np.searchsorted(self.times, t, side="right"))-1, len(self.times)-2)
        i = max(0, i)
        u = (t-self.times[i]) / (self.times[i+1]-self.times[i])
        q = (1-u)*self.qpos[i]+u*self.qpos[i+1]
        v = (self.qpos[i+1]-self.qpos[i])/(self.times[i+1]-self.times[i])
        if seconds < 0 or seconds >= self.duration:
            v = np.zeros(16)
        sample = min(int(np.searchsorted(self.times, t, side="right"))-1, len(self.times)-1)
        held = self.source["held_mask"][sample]
        phase = next(p["name"] for p in reversed(self.source["timeline"]) if t >= p["start_s"])
        return q, v, list(held), phase

    def sample(self, seconds):
        q, v, held, phase = self.control(seconds)
        t = float(np.clip(seconds, 0, self.duration))
        sample = min(int(np.searchsorted(self.times, t, side="right"))-1, len(self.times)-1)
        frames = reference_body_poses(self.reference, q)
        poses = [frames[p["gripper_body"]]@grasp if held[k]
                 else np.asarray(self.source["released_piece_poses"][sample][k])
                 for k, (p, grasp) in enumerate(zip(self.reference["pieces"], self.grasps))]
        return q, v, poses, list(held), phase
