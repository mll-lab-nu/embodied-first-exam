"""Optional video render, isolated from grading readiness and bounded by the parent's timeout."""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        trajectory = json.load(f)
    os.environ["MATCH_SEED"] = str(trajectory["seed"])
    import tn
    acts = np.asarray(trajectory["actions"], float)
    temporary = sys.argv[2] + ".tmp.mp4"
    # at most ~4000 video steps: a long match (15-20k control steps) at every 2nd step takes many minutes
    tn.render_video(acts, trajectory["level"], temporary, every=max(2, math.ceil(len(acts) / 4000)))
    os.replace(temporary, sys.argv[2])
