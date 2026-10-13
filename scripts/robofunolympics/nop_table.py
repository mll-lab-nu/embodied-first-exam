#!/usr/bin/env python3
"""What the referee says to an agent that does nothing (holds the starting command to the end of the episode), per
family: scripts/robofunolympics/nop.json. In the simulator image:

    RFO_RW=1 scripts/robofunolympics/dev.sh /rfo/nop_table.py"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
from rfo.testing import hold, make  # noqa: E402

out = {}
for fam in json.loads((HERE / "families.json").read_text())["families"]:
    w, A = make(fam)
    hold(w, A)
    out[fam] = {"success": bool(w.ref.success), "failed": w.ref.failed, "time_s": round(w.t, 2), "stages": list(w.ref.stages)}
    print(fam, out[fam], flush=True)
    w.close()
(HERE / "nop.json").write_text(json.dumps(out, indent=1) + "\n")
sys.exit(1 if any(v["success"] for v in out.values()) else 0)
