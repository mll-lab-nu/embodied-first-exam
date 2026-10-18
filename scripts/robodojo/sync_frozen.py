#!/usr/bin/env python3
"""Copy the determinism test's frozen instances into scripts/robodojo/frozen/<task>-i00/instance.json, adding the per-task
fields of instance_overrides.json. A task is copied when its test passed (fresh-process resets and replays bit-identical),
or when its override says how it is graded instead (determinism 'verdict', or physics it was frozen with: <task>_ed).
Only a new instance, or one that differs from its committed copy in tasks/ (mk_tasks.frozen_file), is written; run
mk_tasks.py next and then delete frozen/ (the task dirs keep the only committed copy).
    python3 scripts/robodojo/sync_frozen.py <determinism test dir>"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mk_tasks import frozen_file  # noqa: E402
det = pathlib.Path(sys.argv[1]); fz = HERE / "frozen"
ov = {k: v for k, v in json.loads((HERE / "instance_overrides.json").read_text()).items() if not k.startswith("_")}
res = {}
for f in ("all.jsonl", "ed.jsonl"):
    p = det / f
    if p.exists():
        for l in p.read_text().splitlines():
            if l.strip():
                d = json.loads(l); res[d["task"]] = d
n = 0
for task, d in sorted(res.items()):
    base = task.removesuffix("_ed"); o = ov.get(base, {})
    if base != task and not o.get("physics"):
        continue                                   # an enhanced-determinism retest of a task frozen without it
    if base == task and o.get("physics"):
        continue                                   # frozen with its physics settings: the _ed run is the one
    exact = d.get("ok") and d.get("deterministic") and all(d.get("reset_exact") or [False])
    if not d.get("ok") or not (exact or o.get("determinism") == "verdict"):
        continue
    inst = json.loads((det / task / "instance.json").read_text())
    if o.get("physics") and inst.get("physics") != o["physics"]:
        raise SystemExit(f"{task}: frozen with physics {inst.get('physics')} != override {o['physics']}")
    for k in ("determinism", "determinism_why", "physics_why"):
        if k in o:
            inst[k] = o[k]
    out = fz / f"{base}-i00" / "instance.json"
    data = json.dumps(inst, indent=1).encode()
    try:
        same = frozen_file(base, 0)[1] == data
    except FileNotFoundError:
        same = False                               # a new instance
    if not same:
        out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(data); n += 1
print(f"written {n} new or changed instance(s) to {fz}")
