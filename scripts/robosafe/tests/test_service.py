#!/usr/bin/env python3
"""The RoboSafeBench sim service end to end, in this process (no HTTP, no container): the frozen instance is built,
the reference solution is sent through Service.handle() as an agent would send it (rows, notes in the header), the
episode is finalized (two fresh-process replays) and graded by tests/grade.py. Also: doing nothing, exiting at once, a
note in a malformed request, a crash in mid-episode resumed from the journal and the notes.

Needs the simulator (RoboSafeBench importable, MuJoCo); run by hand (docs/benchmarks/robosafe.md):
    MUJOCO_GL=egl python scripts/robosafe/tests/test_service.py [--dev] [a03-i00 ...]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parents[1]
STD = HERE / "shared/standard"


def load(name: str):
    inst = json.loads((HERE / "instances" / f"{name}.json").read_text())
    orc = json.loads((HERE / "oracles" / f"{name}.json").read_text())
    npz = HERE / "oracles" / f"{name}.npz"
    arrays = dict(np.load(npz)) if npz.exists() else {}
    rows = []
    for it in orc["plan"]:
        if "rows" in it:
            rows += [[it["type"], arrays[it["type"]][k].tolist(), ""] for k in range(*it["rows"])]
        else:
            rows.append([it["type"], it["row"], it.get("text") or ""])
    orc["rows"] = rows
    return inst, orc


def service(work: pathlib.Path, inst_path: pathlib.Path):
    os.environ["RCB_DATA"] = str(work)
    os.environ["RCB_INSTANCE"] = str(inst_path)
    import rcb_service
    import server
    sim = server.build()
    svc = rcb_service.Service(sim, data=str(work), wall_clock_s=3600)
    svc.start()
    return svc


def submit(svc, typ: str, rows, note: str = "") -> tuple[int, dict]:
    import rcb1
    a = np.asarray(rows, dtype=np.float64).reshape(len(rows), -1)
    body = rcb1.encode({"type": typ, "interpolate": "hold", "video": "none", "cameras": [svc.sim.cameras[0]], "note": note},
                       [rcb1.array_part("actions", a)])
    code, ctype, out = svc.handle("POST", "/submit", body)
    meta = rcb1.decode(out)[0] if ctype == "application/x-rcb1" else json.loads(out)
    return code, meta


def drive(svc, rows) -> dict:
    """Rows as the oracle sends them: runs of one type without a text in chunks of at most 500, the others alone."""
    meta, i = {}, 0
    while i < len(rows):
        typ, row, text = rows[i]
        j = i + 1
        while not text and j < len(rows) and j - i < 500 and rows[j][0] == typ and not rows[j][2]:
            j += 1
        dim = int(svc.sim.types[typ]["dim"])
        code, meta = submit(svc, typ, [r[1] for r in rows[i:j]] if dim else [[]], text)
        assert code == 200, (code, meta)
        if meta.get("done"):
            break
        i = j
    return meta


def finish_and_grade(svc, work: pathlib.Path) -> dict:
    svc.on_sigusr1()
    svc.poll()
    logs = work / "logs"
    logs.mkdir(exist_ok=True)
    env = {**os.environ, "RCB_DATA": str(work), "RCB_VERIFIER_LOG_DIR": str(logs)}
    subprocess.run([sys.executable, str(STD / "grade.py")], env=env, check=True, capture_output=True)
    return json.loads((logs / "reward.json").read_text())


def case(name: str, rows, expect: int, crash_after: int | None = None) -> dict:
    inst, _ = load(name)
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"rsb-{name}-"))
    ipath = work / "instance.json"
    shutil.copy(HERE / "instances" / f"{name}.json", ipath)
    data = work / "data"
    data.mkdir()
    svc = service(data, ipath)
    if crash_after is not None:
        drive(svc, rows[:crash_after])
        svc = service(data, ipath)            # a new process would do the same: replay the journal with the notes
        drive(svc, rows[crash_after:])
    else:
        drive(svc, rows)
    r = finish_and_grade(svc, data)
    v = json.loads((data / "verdict.json").read_text())
    ok = r["success"] == expect and r["deterministic"] == 1 and r["infra_error"] == 0
    print(("ok  " if ok else "FAIL") + f" {name} {len(rows)} rows: success {r['success']} (expected {expect}), outcome "
          f"{v['outcome']}, replays {v['replays']['state_sha'][0][:12]} {v['replays']['state_sha'][1][:12]}")
    shutil.rmtree(work, ignore_errors=True)
    return {"ok": ok, "reward": r, "hashes": v["replays"]["state_sha"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", default=["a03-i00", "a03-i01"])
    ap.add_argument("--dev", action="store_true", help="the development stand-in API")
    a = ap.parse_args()
    extra = [str(STD)] + ([str(HERE / "dev")] if a.dev else [])
    sys.path[:0] = extra
    os.environ["PYTHONPATH"] = os.pathsep.join(extra + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p])
    bad = 0
    for name in a.names:
        _, orc = load(name)
        rows = orc["rows"]
        bad += not case(name, rows, 1)["ok"]
        bad += not case(name, [], 0)["ok"]
        bad += not case(name, [["done", [], ""]], 0)["ok"]
        if len(rows) > 2:
            bad += not case(name, rows, 1, crash_after=len(rows) // 2)["ok"]
    # a note that is not a string is refused before anything runs
    name = a.names[0]
    work = pathlib.Path(tempfile.mkdtemp(prefix="rsb-note-"))
    shutil.copy(HERE / "instances" / f"{name}.json", work / "instance.json")
    (work / "data").mkdir()
    svc = service(work / "data", work / "instance.json")
    import rcb1
    body = rcb1.encode({"type": "done", "note": 5}, [rcb1.array_part("actions", np.zeros((1, 0), np.float32))])
    code = svc.handle("POST", "/submit", body)[0]
    st = json.loads(svc.handle("GET", "/status")[2])
    good = code == 400 and not st["done"] and "last_operator_answer" in st
    print(("ok  " if good else "FAIL") + f" malformed note: {code}, episode still open: {not st['done']}")
    bad += not good
    shutil.rmtree(work, ignore_errors=True)
    print("all passed" if not bad else f"{bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
