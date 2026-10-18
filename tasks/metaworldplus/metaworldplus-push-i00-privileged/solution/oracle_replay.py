"""Oracle (privileged): Meta-World's scripted expert for this environment, recorded offline on this frozen instance
(scripts/metaworldplus/freeze.py) up to its first success, replayed with the task's tooling and handed in."""

from pathlib import Path

import mw_tool
import numpy as np

actions = np.load(Path(__file__).with_name("oracle.npz"))["actions"]
s = mw_tool.Session("/app/instance.npz")
print(s.replay(actions))
print(s.save_trajectory(actions, meta={"source": "oracle: Meta-World scripted policy, recorded offline"}))
