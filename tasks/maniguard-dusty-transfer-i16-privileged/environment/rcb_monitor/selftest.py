#!/usr/bin/env python3
"""What the resource monitor can measure where it runs (capabilities(), written into its record), and a self-test of
the shared violation rule and the verifier step (no containers needed; ci_checks/check-monitor.py runs it):

    python3 scripts/rcb_monitor/selftest.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _rl(p):
    try:
        return os.readlink(p)
    except OSError:
        return None


def capabilities():
    """Facts the verifier and the results footnotes need: does the monitor see the host's processes (pid: host), the
    host's cgroup tree (cgroup: host; per-container memory and OOM counts), """
    c = {}
    try:
        pids = [d for d in os.listdir("/proc") if d.isdigit()]
    except OSError:
        pids = []
    try:
        c["pid_host"] = int(len(pids) > 1 and open("/proc/1/comm").read().strip() != open("/proc/self/comm").read().strip())
    except OSError:
        c["pid_host"] = 0
    own = ""
    try:
        own = [ln[3:].strip() for ln in open("/proc/self/cgroup") if ln.startswith("0::")][0]
    except (OSError, IndexError):
        pass
    c["cgroup_v2"] = int(os.path.exists("/sys/fs/cgroup/cgroup.controllers"))
    c["cgroup_host"] = int(bool(own) and own != "/" and os.path.isdir("/sys/fs/cgroup" + own))
    return c


# --------------------------------------------------------------------------------------------------- self-test
def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_rule():
    sys.path.insert(0, HERE)
    import rcb_limits as r
    tick = 5.0
    over = [(i * tick, 10.0 if 20 <= i < 33 else 1.0) for i in range(60)]          # 65 s over the limit
    _check(abs(r.sustained(over, 5, 60, 120, tick) - 160.0) < 0.01, "65 s over: confirmed at 60 s")
    short = [(i * tick, 10.0 if 20 <= i < 31 else 1.0) for i in range(60)]         # 55 s
    _check(r.sustained(short, 5, 60, 120, tick) is None, "55 s over: no violation")
    flap = [(i * tick, 10.0 if (i % 2 == 0 and i >= 20) else 1.0) for i in range(80)]  # half the time, never 60 s straight
    _check(r.sustained(flap, 5, 60, 120, tick) is not None, "59 s on / 1 s off does not escape: 60 s in any 120 s")
    sparse = [(i * 25.0, 10.0) for i in range(4)]                                   # 25 s gaps count 15 s each
    _check(r.sustained(sparse, 5, 60, 120, tick) is None, "gaps never count against the agent")
    _check(r.sustained(over, 0, 60, 120, tick) is None, "limit 0 = not limited")
    disk = [(0, 1.0), (60, 30.0), (120, 1.0), (180, 30.0), (240, 31.0)]
    _check(r.consecutive(disk, 20) == 240, "disk: two consecutive measurements over")


def test_verify():
    sys.path.insert(0, HERE)
    import rcb_limits as r
    lim = {"max_gpu_memory_gb": 4.0, "max_memory_gb": 8.0, "max_processes": 100, "max_disk_gb": 10.0,
           "sustain_sec": 60, "window_sec": 120, "tick_sec": 5}
    for enforce, gpu, want in ((1, 6.0, "fail"), (0, 6.0, "observe"), (1, 3.0, "pass")):
        with tempfile.TemporaryDirectory() as d:
            rec, tests, logs = (os.path.join(d, x) for x in ("rec", "tests", "logs"))
            for x in (rec, tests, logs):
                os.makedirs(x)
            json.dump(lim, open(os.path.join(tests, "rcb_limits.json"), "w"))
            with open(os.path.join(rec, "samples.jsonl"), "w") as f:
                for i in range(40):
                    f.write(json.dumps({"t": 1000 + 5 * i, "scope": {"gpu_memory_gb": gpu if i > 5 else 0.5,
                                                                    "memory_gb": 2.0, "processes": 10,
                                                                    "disk_gb": 0.1 if i % 12 == 0 else None}}) + "\n")
            open(os.path.join(rec, "events.jsonl"), "w").close()
            json.dump({"format": r.FORMAT, "sealed": True, "enforce": enforce, "scope_seen": True},
                      open(os.path.join(rec, "summary.json"), "w"))
            json.dump({"success": 1, "infra_error": 0}, open(os.path.join(logs, "reward.json"), "w"))
            open(os.path.join(logs, "reward.txt"), "w").write("1\n")
            import shutil
            shutil.copy(os.path.join(HERE, "rcb_limits.py"), tests)
            env = dict(os.environ, RCB_MONITOR_RECORD=rec, RCB_VERIFIER_LOGS=logs)
            import subprocess
            subprocess.run([sys.executable, os.path.join(tests, "rcb_limits.py"), "verify"], env=env, check=True,
                           capture_output=True)
            out = json.load(open(os.path.join(logs, "reward.json")))
            txt = open(os.path.join(logs, "reward.txt")).read().strip()
            if want == "fail":
                _check(out["success"] == 0 and out["resource_limit_exceeded"] == 1 and out["success_before_limits"] == 1
                       and txt == "0" and out["over_gpu_memory_gb"] == 1, f"enforced violation fails: {out}")
            elif want == "observe":
                _check(out["success"] == 1 and out["limits_violation_observed"] == 1 and txt == "1"
                       and "resource_limit_exceeded" not in out, f"observe mode only records: {out}")
            else:
                _check(out["success"] == 1 and out["limits_violation_observed"] == 0 and out["resource_monitor_missing"] == 0,
                       f"within limits: {out}")
            _check(out["peak_gpu_memory_gb"] == gpu, "peak recorded")
    # no record at all: enforced = infra, observed = flagged only
    for enforce in (1, 0):
        with tempfile.TemporaryDirectory() as d:
            logs, tests = os.path.join(d, "logs"), os.path.join(d, "tests")
            os.makedirs(logs)
            os.makedirs(tests)
            json.dump(lim, open(os.path.join(tests, "rcb_limits.json"), "w"))
            json.dump({"success": 1}, open(os.path.join(logs, "reward.json"), "w"))
            import shutil
            import subprocess
            shutil.copy(os.path.join(HERE, "rcb_limits.py"), tests)
            env = dict(os.environ, RCB_MONITOR_RECORD=os.path.join(d, "none"), RCB_VERIFIER_LOGS=logs,
                       RCB_LIMITS_ENFORCE=str(enforce))
            subprocess.run([sys.executable, os.path.join(tests, "rcb_limits.py"), "verify"], env=env, check=True,
                           capture_output=True)
            out = json.load(open(os.path.join(logs, "reward.json")))
            _check(out["resource_monitor_missing"] == 1 and out.get("infra_error", 0) == enforce,
                   f"missing record (enforce={enforce}): {out}")


def main():
    if sys.argv[1:2] == ["caps"]:
        print(json.dumps(capabilities()))
        return 0
    test_rule()
    test_verify()
    print("rcb_monitor selftest: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
