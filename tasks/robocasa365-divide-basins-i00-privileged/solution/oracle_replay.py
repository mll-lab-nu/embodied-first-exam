"""Oracle (privileged): the reference trajectory recorded offline on this frozen instance from the benchmark's
official demonstration (scripts/<benchmark>/import_references.py), replayed with the task's tooling and handed in."""

from pathlib import Path

import casa_tool
import numpy as np

actions = np.load(Path(__file__).with_name("oracle.npz"))["actions"]
s = casa_tool.Session("/app/instance.npz")
print(s.replay(actions))
print(s.save_trajectory(actions, meta={"source": "oracle: official demonstration, replayed on the frozen instance"}))
