"""The agent's own skill server (core 0.2.34: `game skill serve`, skillhost.serve --tcp --live) and the simulator's
side (inloop: RCB_SKILL_INLOOP_<seat> = "tcp:127.0.0.1:PORT"): calls over the loopback, a change of the skill's
files plays from the next call (its version logged), a missing server is the player's error ("noserver").
Standard library only:

    python3 skilleval/tests/test_skill_server.py     # also as root (the skill then runs as nobody)
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from skilleval.inloop import InLoop  # noqa: E402
from skilleval.sandbox import SkillError  # noqa: E402
from skilleval.skillhost import RemoteHost, serve  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write(d: Path, value: int):
    tmp = d / "skill.py.tmp"
    tmp.write_text(f"def act(x, *, state, spec):\n    return {{'v': {value}, 'x': x}}\n")
    tmp.replace(d / "skill.py")


def test_live_server_reloads_and_logs_versions():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "skill"
        d.mkdir()
        write(d, 1)
        port = free_port()
        threading.Thread(target=serve, args=(f"tcp:127.0.0.1:{port}", str(d)), kwargs={"live": True},
                         daemon=True).start()
        time.sleep(0.5)
        log = Path(tmp) / "inloop_A.jsonl"
        loop = InLoop(f"tcp:127.0.0.1:{port}", "skill", {}, timeouts={"act": 5}, log_path=log)
        loop.refresh(0)
        assert loop.call("act", 7, state={}, k=10) == {"v": 1, "x": 7}
        sha1 = loop.last["sha256"]
        write(d, 2)                                       # mid-unit: plays from the next call
        assert loop.call("act", 8, state={}, k=11) == {"v": 2, "x": 8}
        assert loop.last["sha256"] and loop.last["sha256"] != sha1
        loads = [json.loads(x) for x in log.read_text().splitlines() if json.loads(x).get("op") == "load"]
        assert any(r.get("live") and r["sha256"] == loop.last["sha256"] for r in loads), loads
        loop.close()


def test_no_server_is_the_players_error():
    host = RemoteHost(f"tcp:127.0.0.1:{free_port()}", live=True)
    host.configure("skill", {}, {"act": 5})
    try:
        host.call("act", [1], {})
    except SkillError as e:
        assert e.kind == "noserver", e.kind
    else:
        raise AssertionError("a call without a server must fail")


def main():
    bad = 0
    for n, f in [(n, f) for n, f in globals().items() if n.startswith("test_")]:
        try:
            f()
            print("ok  ", n)
        except Exception:  # noqa: BLE001
            bad += 1
            import traceback
            traceback.print_exc()
            print("FAIL", n)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
