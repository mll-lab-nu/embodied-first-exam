"""Oracle (privileged): the reference outcome for this scene, recorded offline (solution/oracle.npz): for a request to
carry out, HazardArena's own scripted expert for it as control steps on this frozen scene up to the goal; for one not
to carry out, a decline with its note. Replayed with the task's tooling and handed in."""

import os
from pathlib import Path

import ha_tool

ref = ha_tool.load_npz(Path(__file__).with_name("oracle.npz"))
s = ha_tool.Session("/app/instance.json")
print(s.replay(ref["actions"]), flush=True)
note = str(ref["note"]) if int(ref["decline"]) else None
print(s.save_trajectory(ref["actions"], decline=note), flush=True)
os._exit(0)  # dm_control's render threads otherwise race the interpreter's teardown
