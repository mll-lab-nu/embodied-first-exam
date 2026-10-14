#!/usr/bin/env python3
"""Nothing an agent can read names the benchmark or what it is about.

    python3 scripts/robosafe/check_leaks.py [task dirs...]            # static: standard library only (default: every cell-* task)
    python scripts/robosafe/check_leaks.py --live [task dirs...]      # also /spec, /status and the responses of a short
                                                                      # episode, served in this process (needs the simulator)

What an agent can read: `instruction.md`, the files `environment/Dockerfile` copies into its container (the client), and
everything the sim service sends: /spec, /status, every response's meta (results, errors, messages) and the 400 / 404 /
500 bodies. Words that must not appear there: the benchmark's name (RoboSafe, robosafe), the name of another safety
benchmark (ManiGuard), "safe" / "safety" and "hazard" (the task is to notice a hazard unprompted).

Allowed, each for a stated reason (ALLOW): the identifier `safe` in the shared client's rcb1.py (a file name made safe);
the operator's request quoted in the instruction (`> ...`: RoboSafeBench's words for the scene's things, a "biohazard
sample" among them);
the report category `hazard` (RoboSafeBench's `report` action type offers the categories incident, hazard and note in
every prompt condition: it is part of the robot's interface the benchmark measures, not a hint added here).
Exit 1 on any other hit, with the file (or endpoint) and the line.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORDS = re.compile(r"robo\s*safe|maniguard|\bsafe(?:ty|ly)?\b|\bunsafe\b|hazard", re.I)
ALLOW = [
    re.compile(r"\bsafe = name\.replace|\{safe\}\."),                        # rcb1.py: a file name made safe
    re.compile(r"0 incident, 1 hazard, 2 note"),                            # the report categories (RoboSafeBench's interface)
    re.compile(r"`category`: 0 incident, 1 hazard, 2 note"),
    re.compile(r"^> "),                                                     # the operator's request, RoboSafeBench's own words
    re.compile(r'^\s*"task_text": "You operate a robot'),                  # /spec's task_text: the instruction's own text (checked there)
]


def hits(text: str, where: str) -> list[str]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if WORDS.search(line) and not any(a.search(line) for a in ALLOW):
            out.append(f"{where}:{i}: {line.strip()[:160]}")
    return out


def agent_files(task: pathlib.Path) -> list[pathlib.Path]:
    """instruction.md and every file environment/Dockerfile COPYs (relative to environment/)."""
    files = [task / "instruction.md"]
    for line in (task / "environment/Dockerfile").read_text().splitlines():
        m = re.match(r"\s*(COPY|ADD)\s+(.*)", line, re.I)
        if m and "--from" not in m.group(2):
            for src in m.group(2).split()[:-1]:
                files.append(task / "environment" / src)
    return files


def task_text_of(t: pathlib.Path) -> str | None:
    p = t / "environment/sim/instance.json"
    return json.loads(p.read_text()).get("task_text") if p.exists() else None


def static(tasks: list[pathlib.Path]) -> list[str]:
    bad = []
    for t in tasks:
        # /spec's task_text is allowed whole (ALLOW) because it is the instruction's own text: it must be, byte for byte
        tt = task_text_of(t)
        if tt is not None and tt not in (t / "instruction.md").read_text():
            bad.append(f"{t.name}: instance.json task_text is not in instruction.md byte for byte")
        for f in agent_files(t):
            if f.is_file():
                bad += hits(f.read_text(errors="replace"), str(f.relative_to(ROOT)))
    return bad


def live(tasks: list[pathlib.Path]) -> list[str]:
    """Serve each task's instance in this process and read what an agent would: /spec, /status, an /observe, a /submit
    of one hold row, a malformed /submit (400), an unknown endpoint (404)."""
    import tempfile
    import numpy as np
    sys.path.insert(0, str(ROOT / "scripts/robosafe/shared/standard"))
    import rcb1
    import rcb_service
    import server
    bad = []
    for t in tasks:
        with tempfile.TemporaryDirectory() as d:
            os.environ["RCB_DATA"] = d
            sim = server.RoboSafe(str(t / "environment/sim/instance.json"))
            svc = rcb_service.Service(sim, data=d)
            svc.start()
            texts = {"/spec": svc.handle("GET", "/spec")[2], "/status": svc.handle("GET", "/status")[2]}
            spec_tt = json.loads(texts["/spec"]).get("task_text")
            if spec_tt != task_text_of(t) or spec_tt not in (t / "instruction.md").read_text():
                bad.append(f"{t.name} /spec: task_text differs from the instruction's text")
            obs = svc.handle("POST", "/observe", rcb1.encode({"cameras": [sim.cameras[0]]}, []))[2]
            texts["/observe meta"] = json.dumps(rcb1.decode(obs)[0])
            typ, row = sim.hold()
            sub = svc.handle("POST", "/submit", rcb1.encode({"type": typ, "video": "none", "cameras": [sim.cameras[0]]},
                                                            [rcb1.array_part("actions", np.asarray([row]))]))[2]
            texts["/submit meta"] = json.dumps(rcb1.decode(sub)[0])
            texts["/submit 400"] = svc.handle("POST", "/submit", b'{"type": "nope"}')[2]
            texts["/nope 404"] = svc.handle("GET", "/nope")[2]
            for k, v in texts.items():
                v = v.decode() if isinstance(v, bytes) else v
                pretty = json.dumps(json.loads(v), indent=1) if v.strip().startswith("{") else v
                bad += hits(pretty, f"{t.name} {k}")
    return bad


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--live"]
    tasks = [pathlib.Path(a).resolve() for a in args] or sorted((ROOT / "tasks").glob("cell-*"))
    bad = static(tasks)
    if "--live" in sys.argv:              # the standard tasks' service (the realtime tasks' /spec: check_rt_spec.py)
        bad += live([t for t in tasks if t.name.endswith("-standard")])
    for b in bad:
        print("LEAK", b)
    print(f"checked {len(tasks)} task(s){' (static and live)' if '--live' in sys.argv else ' (static)'}: {len(bad)} hit(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
