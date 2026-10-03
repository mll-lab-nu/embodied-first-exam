"""Fresh-process verification of a tennis duel from both robots' recorded joint targets (no HTTP, no wall clock).

    python3 replay.py DATA_DIR [--video]

Re-runs the match from trajectory.json (seed, first receiver, the source fingerprint must match) and writes
replay_check.json: the final state hash, score, points, steps and the hash of every joint target, which the service
compares with the live match.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np


def main(directory, video=False):
    path = Path(directory)
    raw = json.loads((path / "trajectory.json").read_text())
    os.environ["DUEL_SEED"] = str(raw["seed"])
    os.environ["FIRST_RECEIVER"] = raw["first_receiver"]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import duel
    from server_fingerprint import fingerprint
    if raw["source_sha"] != fingerprint() or raw["revision"] != duel.REVISION:
        raise ValueError("simulator fingerprint mismatch")
    arrays = {s: np.asarray(raw[s], dtype=float).reshape(-1, 9) for s in duel.SIDES}
    if not all(np.isfinite(a).all() for a in arrays.values()):
        raise ValueError("nonfinite joint target")
    if video:
        duel.render_video(arrays["A"], arrays["B"], str(path / "replay.mp4.tmp.mp4"))
        os.replace(path / "replay.mp4.tmp.mp4", path / "replay.mp4")
        return
    g = duel.Duel()
    g.replay(arrays["A"], arrays["B"])
    targets = {s: [q.tolist() for q in g.actions[s]] for s in duel.SIDES}
    sha = hashlib.sha256(json.dumps(targets, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    out = dict(state_sha=g.state_sha(), score=g.score, points=g.points, steps=g.k, done=g.done, targets_sha=sha,
               seed=duel.SEED, first_receiver=duel.FIRST_RECEIVER, source_sha=raw["source_sha"], revision=duel.REVISION)
    (path / "replay_check.json").write_text(json.dumps(out))
    print(json.dumps({k: out[k] for k in ("score", "steps", "done")}))


if __name__ == "__main__":
    main(sys.argv[1], "--video" in sys.argv[2:])
