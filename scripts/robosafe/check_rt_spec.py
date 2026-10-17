#!/usr/bin/env python3
"""The served /spec of every rendered standard-realtime task (needs the simulator: run it in the release image after
gen_realtime.py render; check_leaks.py checks the same texts statically).

    python scripts/robosafe/check_rt_spec.py [task dirs...]      # default: every tasks/rsb-*-standard-realtime

Each task's own environment/sim/ is started in a fresh process (its rcb_rsb_rt.py service on its instance.json) and
its /spec read: protocol eai-standard/2.3, `task_text` equal to instance.json's and found byte for byte in
instruction.md, `max_control_steps` equal to the one the instruction states, the picture charge and limits in
`timing`. Exit 1 on any difference.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]

CHILD = r"""
import json, os, sys
sim = sys.argv[1]
sys.path.insert(0, sim)
import rcb_rsb_rt, rcb_realtime, rcb_service
svc_cls, build = rcb_rsb_rt.build_service()
rcb_service.PROTOCOL = rcb_realtime.PROTOCOL
svc = svc_cls(build(), data=os.environ["RCB_DATA"])
print(json.dumps(svc.spec))
"""


def one(t: pathlib.Path) -> list[str]:
    sim = t / "environment/sim"
    inst = json.loads((sim / "instance.json").read_text())
    instr = (t / "instruction.md").read_text()
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "RCB_INSTANCE": str(sim / "instance.json"), "RCB_DATA": d}
        p = subprocess.run([sys.executable, "-c", CHILD, str(sim)], capture_output=True, text=True, env=env)
    if p.returncode:
        return [f"{t.name}: the service did not start: {p.stderr.strip()[-300:]}"]
    spec = json.loads(p.stdout.strip().splitlines()[-1])
    bad = []
    if spec.get("protocol") != "eai-standard/2.3":
        bad.append(f"{t.name}: /spec protocol {spec.get('protocol')!r}")
    if spec.get("task_text") != inst.get("task_text") or spec.get("task_text") not in instr:
        bad.append(f"{t.name}: /spec task_text differs from instance.json's or is not in instruction.md byte for byte")
    m = re.search(r'`spec\(\)\["max_control_steps"\]` control steps of its clock \((\d+)', instr)
    if not m or int(m.group(1)) != spec.get("max_control_steps"):
        bad.append(f"{t.name}: max_control_steps {spec.get('max_control_steps')} is not the instruction's")
    timing = spec.get("timing") or {}
    for k in ("realtime", "picture_cost_steps", "max_cameras_while_running", "max_watch_images_per_s"):
        if k not in timing:
            bad.append(f"{t.name}: /spec timing has no {k}")
    if "stop" not in spec.get("action_types", {}):
        bad.append(f"{t.name}: /spec offers no stop")
    return bad


def main() -> int:
    tasks = [pathlib.Path(a) for a in sys.argv[1:]] or sorted((ROOT / "tasks").glob("rsb-*-standard-realtime"))
    with ThreadPoolExecutor(int(os.environ.get("JOBS", "8"))) as ex:
        bad = [b for res in ex.map(one, tasks) for b in res]
    for b in bad:
        print("FAIL", b)
    print(f"{len(tasks) - len({b.split(':')[0] for b in bad})} of {len(tasks)} realtime tasks: /spec as rendered")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
