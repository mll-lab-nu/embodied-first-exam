"""Optional replay video (evidence only, never part of the grade), run in its own process with a bounded wait:
re-plays the logged decisions (trajectory.json) through bb.Game and renders bb.render_video.

    python3 render_video.py trajectory.json out.mp4
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bb  # noqa: E402

if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        tr = json.load(f)
    g = bb.Game(tr["level"], {"seed": tr["seed"]})
    g.replay(tr["decisions"])
    bb.render_video(g, sys.argv[2])
