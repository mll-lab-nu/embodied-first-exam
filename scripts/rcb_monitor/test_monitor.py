#!/usr/bin/env python3
"""Tests of the resource monitor's own logic (monitor.py) and of the verifier step's edge cases (rcb_limits.py), on a
fake /proc tree and temporary directories: no containers, no GPU, no root. ci_checks/check-monitor.py runs it after
selftest.py. Not copied into tasks.

    python3 scripts/rcb_monitor/test_monitor.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("RCB_MONITOR_RECORD", tempfile.mkdtemp(prefix="rcb-monitor-test-"))
import monitor  # noqa: E402
import rcb_limits  # noqa: E402

GIB = float(2 ** 30)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# --------------------------------------------------------------------------------------------------- a fake /proc
class Fake:
    """A /proc tree, container roots and a beacon volume under one temporary directory."""

    def __init__(self):
        self.d = tempfile.mkdtemp(prefix="rcb-monitor-fake-")
        self.proc = os.path.join(self.d, "proc")
        self.volume = os.path.join(self.d, "volume")          # the trial's beacon volume
        self.host = os.path.join(self.d, "hostroot")          # the host's root: no beacon
        self.rec = os.path.join(self.d, "rec")
        for x in (self.proc, self.volume, self.host, self.rec):
            os.makedirs(x)
        self.proc_self()

    def proc_self(self):
        os.makedirs(os.path.join(self.proc, "self", "ns"))
        os.symlink("mnt:[1]", os.path.join(self.proc, "self", "ns", "mnt"))

    def root(self, name, beacon=True, main=True):
        """A container's root directory: the beacon volume at /run/rcb-limits, /logs/agent in the agent's container."""
        r = os.path.join(self.d, name)
        os.makedirs(os.path.join(r, "run"), exist_ok=True)
        if beacon and not os.path.exists(os.path.join(r, "run", "rcb-limits")):
            os.symlink(self.volume, os.path.join(r, "run", "rcb-limits"))
        if main:
            os.makedirs(os.path.join(r, "logs", "agent"), exist_ok=True)
        return r

    def _entry(self, base, mnt, root, start, state="S", ppid=1, nspid=None, threads=1):
        os.makedirs(os.path.join(base, "ns"), exist_ok=True)
        for link, target in ((os.path.join(base, "ns", "mnt"), mnt), (os.path.join(base, "root"), root)):
            if os.path.lexists(link):
                os.remove(link)
            if target is not None:
                os.symlink(target, link)
        pid = os.path.basename(base)
        fields = [state, str(ppid)] + ["0"] * 9 + ["5", "5"] + ["0"] * 6 + [str(start)] + ["0"] * 10
        with open(os.path.join(base, "stat"), "w") as f:
            f.write(f"{pid} (x) " + " ".join(fields) + "\n")
        with open(os.path.join(base, "status"), "w") as f:
            f.write(f"State:\t{state} ({'zombie' if state == 'Z' else 'sleeping'})\nPPid:\t{ppid}\n"
                    f"NSpid:\t{pid} {nspid if nspid is not None else pid}\nThreads:\t{threads}\nVmRSS:\t1024 kB\n")

    def pid(self, pid, mnt, root, start=1000, **kw):
        self._entry(os.path.join(self.proc, str(pid)), mnt, root, start, **kw)

    def thread(self, pid, tid, mnt, root, start=1000):
        self._entry(os.path.join(self.proc, str(pid), "task", str(tid)), mnt, root, start)

    def gone(self, pid):
        shutil.rmtree(os.path.join(self.proc, str(pid)))

    def monitor(self, limits=None, enforce="0"):
        monitor.PROC, monitor.REC = self.proc, self.rec
        monitor.CGROUP = os.path.join(self.d, "cgroup")

        class NoNvml:
            def __init__(self):
                raise RuntimeError("no NVML in the test")

        monitor.Nvml = NoNvml
        os.environ["RCB_LIMITS_ENFORCE"] = enforce
        m = monitor.Monitor()
        m.lim = dict(limits or {})
        m.beacon = {"scope": monitor.stat_id(self.volume), "observe": None}
        return m

    def events(self, kind=None):
        ev = rcb_limits.read_jsonl(os.path.join(self.rec, "events.jsonl"))
        return [e for e in ev if kind is None or e.get("event") == kind]

    def close(self):
        shutil.rmtree(self.d, ignore_errors=True)


# --------------------------------------------------------------------------------------------------- scope discovery
def test_classify_race():
    """M2: a container seen before its pivot_root (new mount namespace, still the host's root) is found at a later tick."""
    f = Fake()
    try:
        m = f.monitor()
        croot = f.root("main")
        f.pid(100, "mnt:[111]", f.host)                       # runc init before pivot_root
        f.pid(50, "mnt:[2]", f.host)                          # some host service with its own mount namespace
        check(m.groups() == {}, "nothing is watched before the container's root is in place")
        check(not m.cls, "a namespace that does not show the beacon is not remembered")
        f.pid(100, "mnt:[111]", croot, nspid=1)               # pivot_root done
        f.pid(101, "mnt:[111]", croot, start=1100, ppid=100, nspid=7)
        g = m.groups()
        check(set(g) == {"mnt:[111]"} and g["mnt:[111]"]["kind"] == "scope" and g["mnt:[111]"]["role"] == "main"
              and sorted(g["mnt:[111]"]["pids"]) == [100, 101], f"the container is found after its pivot_root: {g}")
        check(m.groups() == g, "and stays found")
        # the witness of the namespace ends, another of its processes proves it again
        f.gone(100)
        g = m.groups()
        check(g["mnt:[111]"]["pids"] == [101], f"still watched through another process: {g}")
        # the namespace ends and its number is given to a container of another trial: not watched
        f.gone(101)
        other = f.root("other", beacon=False)
        f.pid(200, "mnt:[111]", other, start=2000)
        check(m.groups() == {} and not m.cls, "a reused namespace number is asked again, not trusted")
    finally:
        f.close()


def test_dead_leader_and_zombies():
    """m4: a process whose first thread has exited is still found (through a living thread); zombies count."""
    f = Fake()
    try:
        m = f.monitor()
        croot = f.root("main")
        f.pid(100, "mnt:[111]", croot, nspid=1)
        f.pid(300, None, None, start=1300, state="Z", ppid=100, threads=2)     # leader gone, thread 301 runs on
        f.thread(300, 300, None, None, start=1300)
        f.thread(300, 301, "mnt:[111]", croot, start=1301)
        f.pid(400, None, None, start=1400, state="Z", ppid=100)                # a zombie child of the container's init
        f.thread(400, 400, None, None, start=1400)
        f.pid(500, None, None, start=1500, state="Z", ppid=50)                 # a zombie of a host process
        f.pid(50, "mnt:[2]", f.host)
        g = m.groups()["mnt:[111]"]
        check(sorted(g["pids"]) == [100, 300] and g["zombies"] == 1, f"dead leader counted as a process, zombie counted: {g}")
        check(m.base(300).endswith("/300/task/301"), "the process is read through its living thread")
        ms = m.measure(g, {300: 2048}, 10.0)
        check(ms["processes"] == 3 and ms["zombies"] == 1 and ms["gpu_memory_gb"] == 2.0,
              f"its GPU memory is the scope's, zombies count as processes: {ms}")
    finally:
        f.close()


# --------------------------------------------------------------------------------------------------- disk
def _fill(path, mib):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(os.urandom(1024) * (1024 * mib))


def test_disk_walk():
    f = Fake()
    try:
        croot = f.root("main")
        _fill(os.path.join(croot, "app", "a.bin"), 2)
        _fill(os.path.join(croot, "app", "sub", "deep", "b.bin"), 1)
        os.link(os.path.join(croot, "app", "a.bin"), os.path.join(croot, "app", "sub", "a-again.bin"))
        _fill(os.path.join(croot, "app", "skip", "c.bin"), 4)
        _fill(os.path.join(croot, "opt", "d.bin"), 4)                          # not under disk_paths
        w = monitor.DiskWalk(croot, ["/app", "/tmp"], ["/app/skip"])
        check(w.step(60) and w.done and w.why is None, "a small tree is walked in one step")
        mib = w.bytes / 2 ** 20
        check(3.0 <= mib < 3.5, f"2 + 1 MiB: the hard link once, the excluded and the other paths not at all ({mib:.2f})")
        w = monitor.DiskWalk(croot, ["/app"], [])
        check(not w.step(0) and not w.done, "a walk out of budget is not done")
        check(w.step(60) and w.done and 7.0 <= w.bytes / 2 ** 20 < 7.5, "and goes on where it stopped")
    finally:
        f.close()


def test_disk_baseline():
    """M5: only a complete walk sets the baseline or counts as a measurement; a restart keeps the baseline."""
    f = Fake()
    keep = (monitor.DISK_SLICE_SEC, monitor.DISK_WALK_MAX_SEC)
    try:
        lim = {"disk_paths": ["/app"], "max_disk_gb": 0.004, "disk_tick_sec": 60, "tick_sec": 5}
        m = f.monitor(lim)
        m.disk_tick = 60.0
        croot = f.root("main")
        f.pid(100, "mnt:[111]", croot, nspid=1)
        _fill(os.path.join(croot, "app", "sub", "base.bin"), 2)
        groups = m.groups()
        # 1. the first walk does not finish: no baseline, no value, an event
        monitor.DISK_SLICE_SEC, monitor.DISK_WALK_MAX_SEC = 0.0, -1.0
        check(m.disk_step(1000.0, groups) is None and m.disk_base is None, "a partial walk never becomes the baseline")
        check(len(f.events("disk_partial")) == 1, "and is recorded as a gap")
        check(m.disk_step(1005.0, groups) is None and len(f.events("disk_partial")) == 1, "the next walk waits for the disk tick")
        # 2. a complete walk: the baseline
        monitor.DISK_SLICE_SEC, monitor.DISK_WALK_MAX_SEC = keep
        check(m.disk_step(1060.0, groups) == 0.0 and abs(m.disk_base * 1024 - 2.0) < 0.3, f"baseline {m.disk_base}")
        check(len(f.events("disk_baseline")) == 1, "the baseline is recorded")
        # 3. growth is measured against it
        _fill(os.path.join(croot, "app", "sub", "new.bin"), 3)
        v = m.disk_step(1120.0, groups)
        check(v is not None and abs(v * 1024 - 3.0) < 0.3, f"3 MiB of growth: {v}")
        # 4. a walk that does not finish and has seen less than the limit: a gap (None), never "under"
        monitor.DISK_SLICE_SEC, monitor.DISK_WALK_MAX_SEC = 0.0, -1.0
        check(m.disk_step(1180.0, groups) is None, "a partial walk below the limit is not a measurement")
        # 5. ... but one that has already seen more than baseline + limit proves the violation
        _fill(os.path.join(croot, "app", "big.bin"), 8)                        # in the first directory read
        v = m.disk_step(1240.0, groups)
        check(v is not None and v > lim["max_disk_gb"], f"a lower bound over the limit counts: {v}")
        # 6. the container's process ends during the walk: nothing is measured
        monitor.DISK_SLICE_SEC, monitor.DISK_WALK_MAX_SEC = keep
        f.pid(100, "mnt:[111]", croot, start=9999, nspid=1)                    # another process under the same PID
        m.walk = (monitor.DiskWalk(croot, ["/app"], []), "mnt:[111]", f"{f.proc}/100", 1000)
        n = len(f.events("disk_partial"))
        check(m.disk_step(1300.0, groups) is None and len(f.events("disk_partial")) == n + 1, "a vanished container: a gap")
        # 7. a restarted monitor keeps the baseline (and the kills, the confirmed violations)
        base = m.disk_base
        monitor.event("violation", metric="memory_gb", limit=1.0, at=1.0, peak=2.0)
        monitor.event("kill", why="memory_gb", processes=3)
        m2 = f.monitor(lim)
        check(m2.disk_base is None, "a fresh monitor has no baseline")
        m2.restore()
        check(m2.disk_base == base and m2.killed == 3 and "memory_gb" in m2.confirmed, "restore() brings the state back")
    finally:
        monitor.DISK_SLICE_SEC, monitor.DISK_WALK_MAX_SEC = keep
        f.close()


# --------------------------------------------------------------------------------------------------- emergency kills
def test_emergency():
    """M3: host protection is the trial's own use against its own limits, only when enforced, and never a violation."""
    f = Fake()
    killed = []
    real_kill = os.kill
    try:
        os.kill = lambda pid, sig: killed.append(pid)
        lim = {"scope": "trial", "max_gpu_memory_gb": 4.0, "max_memory_gb": 21.0, "max_processes": 512,
               "sustain_sec": 60, "window_sec": 120, "tick_sec": 5,
               "caps": {"main": {"cpus": 8, "memory_gb": 20.0, "pids": 8192}, "extra": {"cpus": 2, "memory_gb": 7.0, "pids": 8192},
                        "scorer": {"cpus": 2, "memory_gb": 7.0, "pids": 8192}},
               "scope_services": ["main", "extra"]}      # a benchmark-owned service (scorer) is not in the scope
        croot = f.root("main")
        f.pid(100, "mnt:[111]", croot, nspid=1)
        f.pid(101, "mnt:[111]", croot, start=5000, ppid=77, nspid=9)           # exec'd into the container: the agent's
        f.pid(102, "mnt:[111]", croot, start=5001, ppid=101, nspid=10)

        def run(enforce, gpu, mem, kernel_cap):
            del killed[:]
            m = f.monitor(lim, enforce=enforce)
            groups = m.groups()
            m._gpu_per = {101: int(gpu * 1024 * 0.25), 102: int(gpu * 1024 * 0.75)}
            m._last_measures = [{"kind": "scope", "role": "main", "memory_cap_gb": kernel_cap}]
            m.check(100.0, {"gpu_memory_gb": gpu, "memory_gb": mem, "processes": 3, "disk_gb": None}, groups)
            return list(killed), m

        check(run("1", 5.9, 1.0, 20.0)[0] == [], "over the limit but under 1.5 x it: the sustained rule's business only")
        k, m = run("1", 6.1, 1.0, 20.0)
        check(k == [102] and len(m.emergency) == 1, f"over 1.5 x the limit: the process holding the most GPU memory: {k}")
        check(run("0", 60.0, 100.0, None)[0] == [], "not enforced: nothing is ever killed")
        check(run("1", 1.0, 26.9, None)[0] == [], "memory under the scope's caps (20 + 7)")
        check(len(run("1", 1.0, 27.5, None)[0]) == 1, "memory over the scope's caps where no kernel cap holds: stand in")
        check(run("1", 1.0, 27.5, 20.0)[0] == [], "the kernel's cap holds: its OOM killer acts, not the monitor")
        ev = f.events()
        check(any(e["event"] == "emergency_kill" for e in ev), "emergency kills are recorded")
        samples = [{"t": 100.0 + 5 * i, "scope": {"gpu_memory_gb": 6.1 if i == 3 else 1.0, "memory_gb": 1.0,
                                                 "processes": 3, "disk_gb": None}} for i in range(30)]
        check(rcb_limits.violations(samples, lim, ev) == [], "an emergency kill is not a violation")
        ev.append({"t": 150.0, "event": "oom", "scope": True, "role": "main", "count": 1})
        check([v["metric"] for v in rcb_limits.violations(samples, lim, ev)] == ["oom"], "a kernel OOM kill is one")
    finally:
        os.kill = real_kill
        f.close()


# --------------------------------------------------------------------------------------------------- the switch, the verifier step
def test_switch():
    for v, want in (("0", 0), ("1", 1), ("true", 1), ("False", 0), ("TRUE", 1), ("", 0), (None, 0), (1, 1), (0, 0), (True, 1)):
        check(rcb_limits.parse_switch(v) == (want, None), f"RCB_LIMITS_ENFORCE={v!r} -> {want}")
    for v in ("yes", "on", "2", "enforce", "-1"):
        e, why = rcb_limits.parse_switch(v)
        check(e == 0 and why and repr(v) in why, f"RCB_LIMITS_ENFORCE={v!r} is an error, not a silent off")
    f = Fake()
    try:
        m = f.monitor(enforce="yes")
        check(m.enforce == 0 and m.switch_error, "the monitor does not guess")
    finally:
        f.close()


def _verify(samples=None, events=(), summary=None, env=None, limits=None, reward=None):
    """Run the verifier step on a made-up record; returns (reward.json, reward.txt, resource_limits.json)."""
    lim = limits if limits is not None else {"max_gpu_memory_gb": 4.0, "max_memory_gb": 8.0, "max_processes": 100,
                                             "max_disk_gb": 10.0, "sustain_sec": 60, "window_sec": 120, "tick_sec": 5}
    with tempfile.TemporaryDirectory() as d:
        rec, tests, logs = (os.path.join(d, x) for x in ("rec", "tests", "logs"))
        for x in (tests, logs):
            os.makedirs(x)
        json.dump(lim, open(os.path.join(tests, "rcb_limits.json"), "w"))
        if samples is not None:
            os.makedirs(rec)
            with open(os.path.join(rec, "samples.jsonl"), "w") as fh:
                for s in samples:
                    fh.write(json.dumps(s) + "\n")
            with open(os.path.join(rec, "events.jsonl"), "w") as fh:
                for e in events:
                    fh.write(json.dumps(e) + "\n")
            if summary is not None:
                json.dump(summary, open(os.path.join(rec, "summary.json"), "w"))
        json.dump(reward if reward is not None else {"success": 1, "infra_error": 0}, open(os.path.join(logs, "reward.json"), "w"))
        open(os.path.join(logs, "reward.txt"), "w").write("1\n")
        shutil.copy(os.path.join(HERE, "rcb_limits.py"), tests)
        e = dict(os.environ, RCB_MONITOR_RECORD=rec, RCB_VERIFIER_LOGS=logs)
        e.pop("RCB_LIMITS_ENFORCE", None)
        e.update(env or {})
        r = subprocess.run([sys.executable, os.path.join(tests, "rcb_limits.py"), "verify"], env=e, capture_output=True, text=True)
        check(r.returncode == 0, f"the step never changes the verifier's exit status: {r.stderr}")
        det = os.path.join(logs, "resource_limits.json")
        return (json.load(open(os.path.join(logs, "reward.json"))), open(os.path.join(logs, "reward.txt")).read().strip(),
                json.load(open(det)) if os.path.exists(det) else None)


def _samples(n=40, gpu=1.0, **scope):
    return [{"t": 1000 + 5 * i, "scope": dict({"gpu_memory_gb": gpu, "memory_gb": 2.0, "processes": 10, "disk_gb": None},
                                              **scope)} for i in range(n)]


def test_verify_edges():
    ok = {"format": rcb_limits.FORMAT, "sealed": True, "scope_seen": True}
    # an emergency kill without a sustained violation: recorded, the grader's verdict stands (enforced)
    ev = [{"t": 1010, "event": "emergency_kill", "why": "gpu_memory", "limit": 4.0, "observed": 9.0, "processes": 1}]
    out, txt, det = _verify(_samples(), ev, dict(ok, enforce=1))
    check(out["success"] == 1 and txt == "1" and out["resource_emergency_kills"] == 1 and out["limits_violation_observed"] == 0
          and "resource_limit_exceeded" not in out and out.get("infra_error", 0) == 0, f"emergency kill alone: {out}")
    check(len(det["emergency_kills"]) == 1, "and listed in resource_limits.json")
    # the switch: unreadable -> not a result, in the record or in the verifier's own environment
    out, txt, det = _verify(_samples(), (), dict(ok, enforce=0, switch_error="RCB_LIMITS_ENFORCE='yes' is not one of 0, 1, true, false"))
    check(out["infra_error"] == 1 and out["resource_switch_error"] == 1 and out["success"] == 1 and txt == "1",
          f"switch error in the record: {out}")
    out, _, _ = _verify(None, env={"RCB_LIMITS_ENFORCE": "yes"})
    check(out["infra_error"] == 1 and out["resource_switch_error"] == 1 and out["resource_monitor_missing"] == 1,
          f"switch error, no record: {out}")
    for v, want in (("true", 1), ("false", 0), ("1", 1), ("0", 0)):
        out, _, _ = _verify(None, env={"RCB_LIMITS_ENFORCE": v})
        check(out["resource_enforced"] == want and out.get("infra_error", 0) == want and out["resource_monitor_missing"] == 1,
              f"no record, RCB_LIMITS_ENFORCE={v}: infra only when enforced: {out}")
    # a record that is there but not usable, enforcement off: reported only
    out, txt, det = _verify(_samples(), [{"t": 1001, "event": "fatal", "why": "x"}], dict(ok, enforce=0))
    check(out["resource_monitor_missing"] == 1 and out.get("infra_error", 0) == 0 and out["success"] == 1, f"observe only: {out}")
    # NVML does not tell the scope's GPU memory: the GPU limit was not measured
    blind = _samples(gpu=0.0, gpu_unmeasured=1)
    out, _, det = _verify(blind, (), dict(ok, enforce=1))
    check(out["infra_error"] == 1 and out["resource_monitor_missing"] == 1 and "NVML" in " ".join(det["record_problems"]),
          f"GPU memory not measured, enforced: {out}")
    out, _, _ = _verify(blind, (), dict(ok, enforce=0))
    check(out.get("infra_error", 0) == 0 and out["resource_monitor_missing"] == 1, f"GPU memory not measured, observed: {out}")
    nogpu = {"max_gpu_memory_gb": 0.0, "max_memory_gb": 8.0, "max_processes": 100, "max_disk_gb": 10.0}
    out, _, _ = _verify(blind, (), dict(ok, enforce=1), limits=nogpu)
    check(out["resource_monitor_missing"] == 0, "no GPU limit: nothing was missed")
    # the step itself fails (a broken limits file): reported in reward.json, as infra only when enforcement was asked for
    out, txt, det = _verify(_samples(), (), dict(ok, enforce=0), limits=["broken"], env={"RCB_LIMITS_ENFORCE": "1"})
    check(out["resource_step_error"] == 1 and out["infra_error"] == 1 and out["success"] == 1 and txt == "1", f"step failed: {out}")
    out, _, _ = _verify(_samples(), (), dict(ok, enforce=0), limits=["broken"])
    check(out["resource_step_error"] == 1 and out.get("infra_error", 0) == 0, f"step failed, not enforced: {out}")


def main():
    for t in (test_classify_race, test_dead_leader_and_zombies, test_disk_walk, test_disk_baseline, test_emergency,
              test_switch, test_verify_edges):
        t()
    shutil.rmtree(os.environ["RCB_MONITOR_RECORD"], ignore_errors=True)
    print("rcb_monitor test_monitor: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
