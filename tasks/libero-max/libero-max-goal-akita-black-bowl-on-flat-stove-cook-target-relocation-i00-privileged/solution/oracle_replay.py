"""Oracle (privileged): a scripted reference controller with privileged state (scripts/libero-max/shared/reference.py,
not in the image), recorded as control steps on this frozen instance up to LIBERO's success, replayed with the task's
tooling and handed in."""

from pathlib import Path

import lmx_tool
import numpy as np

actions = np.load(Path(__file__).with_name("oracle.npy"))
s = lmx_tool.Session("/app/instance.json")
print(s.replay(actions), flush=True)
print(s.save_trajectory(actions), flush=True)
