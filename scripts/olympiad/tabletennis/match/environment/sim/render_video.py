"""Optional video render, isolated from grading readiness and bounded by the parent's timeout."""
import json
import os
import sys
import numpy as np
import match

if __name__ == '__main__':
    with open(sys.argv[1]) as f:
        trajectory = json.load(f)
    os.environ['MATCH_SEED'] = str(trajectory['seed'])
    temporary = sys.argv[2] + '.tmp.mp4'
    match.render_video(np.asarray(trajectory['actions']), trajectory['level'], temporary)
    os.replace(temporary, sys.argv[2])
