#!/usr/bin/env python3
"""RoboOlympics' low-level matches (#300, core 0.2.34): the simulator calls the agent's OWN skill server in the agent's
container (tcp:127.0.0.1:8765), so every answer it reads is the agent's. No answer may raise anything but SkillError in
the simulator's RemoteHost (an exception in the control step would end the match as a technical error, before the
agent's first act a free retry), and no answer may put a non-string version into the call log (tests/fexam_reward.py
counts the versions in a set). Standard library only: a fake server on the loopback answers each request with a
malformed reply; the grader's reward script runs on a call log with such rows.

    python3 scripts/roboolympics/tests/test_matchlow_skill_server.py
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASKS = sorted(ROOT.glob("tasks/roboolympics-*-matchlow-i*-standard-realtime"))
BAD = [
    [1, 2, 3],                                                           # not an object
    "a string",
    {"ok": True, "ret": None, "status": [1]},                            # status not an object
    {"ok": True, "ret": None, "status": {"loaded": True, "functions": 5, "sha256": [1]}},
    {"ok": True, "ret": None, "status": {"loaded": "yes", "functions": ["hit", 7, None], "sha256": {"a": 1}}},
    {"ok": False, "kind": ["x"], "error": {"why": 1}, "status": {"sha256": "x" * 4000}},
    {"ok": True, "load": [1], "status": "nope"},
    {"ok": True, "load": {"op": "call", "sha256": [1], "ok": "yes", "extra": [1]}, "status": {"loaded": True}},
]


def fake_server(answers):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def run():
        i = 0
        while i < len(answers) * 4:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            f = conn.makefile("rwb")
            try:
                while f.readline():
                    f.write((json.dumps(answers[i % len(answers)]) + "\n").encode())
                    f.flush()
                    i += 1
            except OSError:
                pass
            conn.close()
    threading.Thread(target=run, daemon=True).start()
    return srv, srv.getsockname()[1]


def check_status(st, where):
    assert isinstance(st, dict), (where, st)
    assert st.get("sha256") is None or isinstance(st["sha256"], str), (where, st)
    assert isinstance(st.get("loaded"), bool), (where, st)
    assert isinstance(st.get("functions"), list) and all(isinstance(f, str) for f in st["functions"]), (where, st)


def test_remote_host(task: Path):
    sim = task / "environment" / "sim"
    for k in [k for k in sys.modules if k == "skilleval" or k.startswith("skilleval.")]:
        del sys.modules[k]
    sys.path.insert(0, str(sim))
    try:
        from skilleval.sandbox import SkillError
        from skilleval.skillhost import RemoteHost
    finally:
        sys.path.remove(str(sim))
    for n, bad in enumerate(BAD):
        srv, port = fake_server([bad])
        try:
            h = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
            h.configure("hit", {}, {"hit": 1.0}, 1.0)
            for op in ("refresh", "call", "call", "refresh"):
                try:
                    out = h.refresh(n) if op == "refresh" else h.call("hit", [], {})
                    if op == "refresh" and out is not None:
                        assert isinstance(out, dict) and (out.get("sha256") is None or isinstance(out["sha256"], str)), out
                        json.dumps({"op": "load", **out})
                except SkillError:
                    pass                                 # the player's error: lowered to the no-op by InLoop
                check_status(h.status(), f"{task.name} answer {n} after {op}")
                h.has("step")                            # what the control step asks (InLoopLayer.tick)
            h.close()
        finally:
            srv.close()


def test_fexam_reward(task: Path):
    with tempfile.TemporaryDirectory() as tmp:
        log, data = Path(tmp, "logs"), Path(tmp, "data")
        log.mkdir()
        data.mkdir()
        (log / "reward.json").write_text(json.dumps({"success": 1, "technical_failure": 0}))
        (data / "final.json").write_text(json.dumps({"slowdown": 10, "cfg": {"level": 1}, "steps": 5}))
        rows = [{"op": "call", "fn": "hit", "sha256": [1], "ok": True}, [1, 2], "x",
                {"op": "call", "fn": "act", "sha256": "abc", "ok": False}, {"op": "load", "ok": True, "sha256": {"a": 1}}]
        (data / "inloop_A.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        src = (task / "tests" / "fexam_reward.py").read_text()
        src = src.replace('Path("/logs/verifier"), Path("/data")', f'Path({str(log)!r}), Path({str(data)!r})')
        p = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, (task.name, p.stderr[-600:])
        r = json.loads((log / "reward.json").read_text())
        assert r["infra_error"] == 0 and r["success"] == 1 and r["skill_versions_played"] == 1, (task.name, r)
        assert r["skill_calls"] == 2, (task.name, r)


def main() -> int:
    if not TASKS:
        print("ok roboolympics matchlow skill server: no matchlow task")
        return 0
    failed = 0
    for t in TASKS:
        for fn in (test_remote_host, test_fexam_reward):
            try:
                fn(t)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {fn.__name__} {t.name}: {type(exc).__name__}: {exc}")
    print(f"{'ok' if not failed else 'FAIL'} roboolympics matchlow skill server: {len(TASKS)} task(s), {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main())
