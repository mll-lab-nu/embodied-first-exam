"""Oracle (privileged): VLABench's own expert for this task (its scripted skill sequence), recorded as control steps on
this frozen instance up to the task's success, replayed with the task's tooling and handed in."""

import os
from pathlib import Path

import numpy as np
import vlb_tool

actions = np.load(Path(__file__).with_name("oracle.npy"))
s = vlb_tool.Session("/app/instance.json")
print(s.replay(actions), flush=True)
print(s.save_trajectory(actions), flush=True)
os._exit(0)  # dm_control's render threads otherwise race the interpreter's teardown
