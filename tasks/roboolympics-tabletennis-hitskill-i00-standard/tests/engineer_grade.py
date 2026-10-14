#!/usr/bin/env python3
"""reward.json of an Engineer task (tools/export_fexam.py): skilleval's report -> success = a valid evaluation whose
API-test success rate is at least the line. Numbers only.

    engineer_grade.py LINE N_EXPECTED [REPORT]      (REPORT: default /var/lib/skilleval/report.json)

The skill ran as `nobody` in this container, and /logs/verifier is writable by others (Harbor makes it 777), so before
anything is read (robot coding bench, board 0111): every process of `nobody` still alive in this container is killed
(skilleval's sandbox already ended the skill's whole process tree; this is the second line), every entry of
/logs/verifier that root did not create is removed, the report is read from a directory only root can write, and the
reward files are written fresh (no file or link left there is followed). The report is copied to /logs/verifier after."""
import json
import os
import signal
import sys
import time
from pathlib import Path

LOG = Path("/logs/verifier")
NOBODY = 65534


def end_nobody(within_s: float = 10.0) -> int:
    """SIGKILL every process of `nobody` in this container until none is left. Skipped where this is not a container
    of its own (PID 1 is the host's init): the sweep must not reach other processes of the host."""
    try:
        if Path("/proc/1/comm").read_text().strip() in ("systemd", "init"):
            return 0
    except OSError:
        return 0
    sent, end = 0, time.monotonic() + within_s
    while time.monotonic() < end:
        victims = []
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    with open(f"/proc/{d}/status") as f:
                        if next(int(x.split()[1]) for x in f if x.startswith("Uid:")) == NOBODY:
                            victims.append(int(d))
                except (OSError, ValueError, StopIteration):
                    pass
        if not victims:
            return sent
        for p in victims:
            try:
                os.kill(p, signal.SIGKILL)
                sent += 1
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(0.01)
    raise SystemExit("processes of nobody survived SIGKILL: no grade")


def clean_log_dir() -> list[str]:
    """Remove what anyone but root put into /logs/verifier (a planted reward, a link, a directory in a file's place)."""
    gone = []
    for p in LOG.iterdir():
        st = p.lstat()
        if st.st_uid != 0 or p.name in ("reward.json", "reward.txt", "report.json"):
            if p.is_dir() and not p.is_symlink():
                for q in sorted(p.rglob("*"), key=lambda q: -len(q.parts)):
                    q.unlink() if (q.is_symlink() or not q.is_dir()) else q.rmdir()
                p.rmdir()
            else:
                p.unlink()
            gone.append(p.name)
    return gone


def write_new(path: Path, text: str):
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(text)


line, n_expected = float(sys.argv[1]), int(sys.argv[2])
report = Path(sys.argv[3] if len(sys.argv) > 3 else "/var/lib/skilleval/report.json")
killed = end_nobody()
removed = clean_log_dir()
try:
    if report.parent.stat().st_mode & 0o022 or report.parent.stat().st_uid != 0:
        raise ValueError(f"{report.parent} is writable by others: its report is not trusted")
    rep = json.loads(report.read_text())
except (OSError, ValueError) as e:
    print(f"engineer_grade: {e}", file=sys.stderr)
    rep = None
out = {"success": 0, "infra_error": 0, "grader_error": 0, "line": line,
       "sandbox_processes_killed": killed, "log_entries_removed": len(removed)}
if rep is None:
    out["grader_error"] = 1
else:
    api = rep.get("api_test") or {}
    n = int(api.get("n") or api.get("cases") or len(rep.get("api_rows") or []))
    rate = float(api.get("success_rate") or 0.0)
    det = bool((rep.get("determinism") or {}).get("deterministic", True))
    # skilleval: valid = false with a reason = the deliverable's own problem (missing, does not load, no function):
    # a valid 0 for the player, not a grader error
    deliverable_ok = bool(rep.get("valid", True))
    out.update(api_success_rate=rate, api_cases=n, api_successes=int(round(rate * n)), deterministic=int(det),
               deliverable_ok=int(deliverable_ok),
               eval_wall_s=float(rep.get("seconds") or rep.get("wall_s") or 0.0))
    for k, v in api.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in out:
            out["api_" + k] = v
    out["grader_error"] = int(deliverable_ok and n != n_expected)
    out["success"] = int(deliverable_ok and n == n_expected and rate >= line and det)
    write_new(LOG / "report.json", json.dumps(rep, sort_keys=True))
write_new(LOG / "reward.json", json.dumps(out))
write_new(LOG / "reward.txt", str(out["success"]) + "\n")
