#!/usr/bin/env python3
"""Tests of the resource monitor's own logic (monitor.py) and of the verifier step's edge cases (rcb_limits.py), on a
fake /proc tree and temporary directories: no containers, no GPU, no root. ci_checks/check-monitor.py runs it after
selftest.py. Not copied into tasks.

    python3 images/monitor/rcb_monitor/test_monitor.py
"""
import importlib.util
import itertools
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
        self.observe = os.path.join(self.d, "volume-observe")  # the beacon of the benchmark's own services (recorded only)
        for x in (self.proc, self.volume, self.host, self.rec, self.observe):
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

    def sidecar_root(self, name):
        """The root of a benchmark-owned service (the sim sidecar of standard modes): the observe beacon, no /logs/agent."""
        r = self.root(name, beacon=False, main=False)
        if not os.path.exists(os.path.join(r, "run", "rcb-observe")):
            os.symlink(self.observe, os.path.join(r, "run", "rcb-observe"))
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

    def cgroup(self, name, pids=None, anon_gb=None, max_gb=None, **events):
        """A container's own cgroup v2 directory (under the fake host tree) and its processes' /proc/<pid>/cgroup.
        Only what is given is (re)written; events: the counters of memory.events (oom=, oom_kill=, max=)."""
        d = os.path.join(self.d, "cgroup", name)
        os.makedirs(d, exist_ok=True)
        if pids is not None:
            for pid in pids:
                with open(os.path.join(self.proc, str(pid), "cgroup"), "w") as fh:
                    fh.write(f"0::/{name}\n")
            with open(os.path.join(d, "cgroup.procs"), "w") as fh:
                fh.write("".join(f"{pid}\n" for pid in pids))
        if anon_gb is not None:
            with open(os.path.join(d, "memory.stat"), "w") as fh:
                fh.write(f"anon {int(anon_gb * GIB)}\nshmem 0\n")
            with open(os.path.join(d, "memory.current"), "w") as fh:
                fh.write(f"{int(anon_gb * GIB)}\n")
        if max_gb is not None:
            with open(os.path.join(d, "memory.max"), "w") as fh:
                fh.write("max\n" if max_gb == "max" else f"{int(max_gb * GIB)}\n")
        if events:
            ev = dict({"low": 0, "high": 0, "max": 0, "oom": 0, "oom_kill": 0, "oom_group_kill": 0}, **events)
            with open(os.path.join(d, "memory.events"), "r+" if os.path.exists(os.path.join(d, "memory.events")) else "w") as fh:
                fh.truncate(0)                       # in place: the monitor keeps the file open, as on a real cgroup
                fh.write("".join(f"{k} {v}\n" for k, v in ev.items()))
        return d

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
        m.beacon = {"scope": monitor.stat_id(self.volume), "observe": monitor.stat_id(self.observe)}
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
        # R2 m2: every process that holds GPU memory is one that must outlive a kill (PID 1): nobody is killed, and in
        # particular not a process that holds none of it (before: the first one found, the agent's)
        del killed[:]
        m = f.monitor(lim, enforce="1")
        groups = m.groups()
        m._gpu_per = {100: 9 * 1024}
        m._last_measures = [{"kind": "scope", "role": "main", "memory_cap_gb": 20.0}]
        m.check(100.0, {"gpu_memory_gb": 9.0, "memory_gb": 1.0, "processes": 3, "disk_gb": None}, groups)
        check(killed == [] and not m.emergency, f"no victim that holds no GPU memory: {killed}")
        check(run("1", 1.0, 26.9, None)[0] == [], "memory under the scope's caps (20 + 7)")
        check(len(run("1", 1.0, 27.5, None)[0]) == 1, "memory over the scope's caps where no kernel cap holds: stand in")
        check(run("1", 1.0, 27.5, 20.0)[0] == [], "the kernel's cap holds: its OOM killer acts, not the monitor")
        ev = f.events()
        check(any(e["event"] == "emergency_kill" for e in ev), "emergency kills are recorded")
        samples = [{"t": 100.0 + 5 * i, "scope": {"gpu_memory_gb": 6.1 if i == 3 else 1.0, "memory_gb": 1.0,
                                                 "processes": 3, "disk_gb": None}} for i in range(30)]
        check(rcb_limits.violations(samples, lim, ev) == [], "an emergency kill is not a violation")
        ev.append({"t": 140.0, "event": "oom", "scope": True, "role": "main", "count": 1, "cause": "host"})
        ev.append({"t": 141.0, "event": "oom", "scope": True, "role": "main", "count": 1})          # does not say why
        ev.append({"t": 142.0, "event": "oom", "scope": False, "role": "sidecar", "count": 2, "cause": "cap"})
        check(rcb_limits.violations(samples, lim, ev) == [],
              "an OOM kill by the host's killer, one of unknown cause, one in a benchmark-owned service: not violations")
        check(rcb_limits.oom_kills(ev) == {"cap": 0, "host": 2, "service": 2}, f"but counted: {rcb_limits.oom_kills(ev)}")
        ev.append({"t": 150.0, "event": "oom", "scope": True, "role": "main", "count": 1, "cause": "cap"})
        check([v["metric"] for v in rcb_limits.violations(samples, lim, ev)] == ["oom"],
              "a kernel OOM kill in the scope at the container's own memory cap is one")
    finally:
        os.kill = real_kill
        f.close()


# --------------------------------------------------------------------------------------------------- the kill at a confirmed violation
def test_kill_path():
    """R3 M7: the kill itself. A violation is confirmed only after sustain_sec over a limit, so a test that feeds one
    sample (test_emergency) never reaches Monitor.check's kill: this one feeds whole records. Not enforced: a confirmed
    violation is recorded and nothing is killed. Enforced: the agent's processes of the scope are killed at the
    confirmation, and never the container's PID 1, its keepalive, or a process of a benchmark-owned service. Spikes
    that never add up to sustain_sec inside one window_sec confirm nothing, however long the record."""
    f = Fake()
    killed = []
    real_kill = os.kill
    try:
        os.kill = lambda pid, sig: killed.append(pid)
        lim = {"scope": "agent", "max_gpu_memory_gb": 0.0, "max_memory_gb": 21.0, "max_processes": 512,
               "sustain_sec": 60, "window_sec": 120, "tick_sec": 5,
               "caps": {"main": {"cpus": 8, "memory_gb": 29.0, "pids": 8192}, "sim": {"cpus": 8, "memory_gb": 16.0, "pids": 8192}},
               "scope_services": ["main"]}
        croot, sroot = f.root("main"), f.sidecar_root("sim")
        f.pid(100, "mnt:[111]", croot, start=1000, nspid=1)                    # the agent container's PID 1
        f.pid(103, "mnt:[111]", croot, start=1001, ppid=100, nspid=7)          # its keepalive, started with it
        f.pid(101, "mnt:[111]", croot, start=5000, ppid=77, nspid=9)           # exec'd into the container: the agent's
        f.pid(102, "mnt:[111]", croot, start=5001, ppid=101, nspid=10)
        f.pid(104, "mnt:[111]", croot, start=6000, ppid=100, nspid=11)         # an orphan PID 1 adopted later: the agent's
        f.pid(200, "mnt:[222]", sroot, start=1000, nspid=1)                    # the benchmark's own service (the sim)
        f.pid(201, "mnt:[222]", sroot, start=5000, ppid=200, nspid=5)
        agent, never = {101, 102, 104}, {100, 103, 200, 201}

        def feed(enforce, values, step=5.0):
            """Monitor.check on one sample per value (GiB of memory, `step` seconds apart): (monitor, {sample index: pids killed})."""
            del killed[:]
            shutil.rmtree(f.rec)
            os.makedirs(f.rec)
            m = f.monitor(lim, enforce=enforce)
            groups = m.groups()
            check(sorted((g["kind"], g["role"], sorted(g["pids"])) for g in groups.values())
                  == [("observe", "sidecar", [200, 201]), ("scope", "main", [100, 101, 102, 103, 104])], f"the two containers: {groups}")
            m._gpu_per = {}
            m._last_measures = [{"kind": "scope", "role": "main", "memory_cap_gb": 29.0}]   # the kernel's cap holds: no stand-in kill
            at = {}
            for i, v in enumerate(values):
                n = len(killed)
                m.check(100.0 + step * i, {"gpu_memory_gb": 0.0, "memory_gb": v, "processes": 5, "disk_gb": None}, groups)
                if len(killed) > n:
                    at[i] = sorted(killed[n:])
            return m, at

        over = [25.0] * 30                                    # 150 s over the 21 GiB limit, under the 29 GiB cap
        m, at = feed("0", over)
        check(list(m.confirmed) == ["memory_gb"] and len(f.events("violation")) == 1, f"not enforced: confirmed and recorded: {m.confirmed}")
        check(at == {} and killed == [] and m.killed == 0 and not f.events("kill") and not f.events("emergency_kill"),
              f"not enforced: a confirmed violation kills nothing: {at}")
        m, at = feed("1", over)
        check(list(m.confirmed) == ["memory_gb"] and len(f.events("violation")) == 1, f"enforced: confirmed once: {m.confirmed}")
        # sample i lasts until sample i + 1: 60 s over the limit are reached with the 13th sample (index 12), not before
        check(at and min(at) == 12, f"enforced: the first kill is at the confirmation, not before: {sorted(at)}")
        check(set(at[12]) == agent and len(at[12]) == len(agent), f"enforced: every agent process of the scope, once: {at[12]}")
        check(not (set(killed) & never), f"never PID 1, its keepalive or the benchmark's service: {sorted(set(killed) & never)}")
        check(set(killed) == agent and m.killed == len(killed) and len(f.events("kill")) == len(at),
              f"the kills are counted and recorded: {m.killed}, {len(killed)}, {len(f.events('kill'))}")
        # at the limit is not over it; a record with gaps of under-limit samples that stays below sustain_sec per window
        m, at = feed("1", [21.0] * 60)
        check(not m.confirmed and killed == [], f"at the limit: no violation: {m.confirmed}")
        spikes = ([25.0] * 5 + [1.0] * 12) * 12               # 25 s over, 60 s under, for 17 minutes: 300 s over in all,
        m, at = feed("1", spikes)                             # at most 50 s of it inside any 120 s
        check(not m.confirmed and killed == [] and not f.events("violation"), f"spikes spread over more than window_sec: {m.confirmed} {at}")
        rec = [{"t": 100.0 + 5 * i, "scope": {"gpu_memory_gb": 0.0, "memory_gb": v, "processes": 5, "disk_gb": None}}
               for i, v in enumerate(spikes)]
        check(rcb_limits.violations(rec, lim) == [], "the verifier's rule on the whole record agrees: no violation")
        dense = ([25.0] * 7 + [1.0] * 4) * 6                  # 35 s over, 20 s under: 70 s over inside 120 s
        m, at = feed("1", dense)
        check(list(m.confirmed) == ["memory_gb"] and at and set(killed) == agent,
              f"going under for a moment does not reset the time: {m.confirmed} {sorted(set(killed))}")
        m, at = feed("0", dense)
        check(list(m.confirmed) == ["memory_gb"] and killed == [], "... and not enforced, nothing is killed")
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


def _verify(samples=None, events=(), summary=None, env=None, limits=None, reward=None, no_limits=False, txt="1"):
    """Run the verifier step on a made-up record; returns (reward.json, reward.txt, resource_limits.json)."""
    lim = limits if limits is not None else {"max_gpu_memory_gb": 4.0, "max_memory_gb": 8.0, "max_processes": 100,
                                             "max_disk_gb": 10.0, "sustain_sec": 60, "window_sec": 120, "tick_sec": 5}
    with tempfile.TemporaryDirectory() as d:
        rec, tests, logs = (os.path.join(d, x) for x in ("rec", "tests", "logs"))
        for x in (tests, logs):
            os.makedirs(x)
        if not no_limits:
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
        open(os.path.join(logs, "reward.txt"), "w").write(txt + "\n")
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
    check(out["infra_error"] == 1 and out["resource_switch_error"] == 1 and out["success"] == 0 and txt == "0"
          and out["success_before_limits"] == 1, f"switch error in the record: not a result, and no success beside it: {out}")
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
    check(out["resource_step_error"] == 1 and out["infra_error"] == 1 and out["success"] == 0 and txt == "0"
          and out["success_before_limits"] == 1, f"step failed, enforcement asked for: not a result: {out}")
    out, txt, _ = _verify(_samples(), (), dict(ok, enforce=0), limits=["broken"])
    check(out["resource_step_error"] == 1 and out.get("infra_error", 0) == 0 and out["success"] == 1 and txt == "1",
          f"step failed, not enforced: {out}")
    # R2 m1: an unusable record with enforcement on is not a result, and leaves no success beside the infra flag
    out, txt, _ = _verify(_samples(), [{"t": 1001, "event": "fatal", "why": "x"}], dict(ok, enforce=1))
    check(out["infra_error"] == 1 and out["success"] == 0 and out["success_before_limits"] == 1 and txt == "0"
          and "resource_limit_exceeded" not in out, f"unusable record, enforced: {out}")
    out, txt, _ = _verify(_samples(), [{"t": 1001, "event": "fatal", "why": "x"}], dict(ok, enforce=1),
                          reward={"success": 1, "reward": 1.0, "infra_error": 0})
    check(out["reward"] == 0 and out["success"] == 0 and out["infra_error"] == 1, f"... the reward field too: {out}")
    # the verifier's copy of the limits is missing: reported (before: "within limits")
    out, txt, det = _verify(_samples(), (), dict(ok, enforce=0), limits=None, no_limits=True)
    check(out["resource_monitor_missing"] == 1 and out["success"] == 1 and txt == "1" and out.get("infra_error", 0) == 0
          and "rcb_limits.json" in " ".join(det["record_problems"]), f"no limits file, not enforced: {out}")
    out, txt, _ = _verify(_samples(), (), dict(ok, enforce=1), limits=None, no_limits=True)
    check(out["infra_error"] == 1 and out["success"] == 0 and txt == "0", f"no limits file, enforced: not a result: {out}")


# --------------------------------------------------------------------------------------------------- OOM kills
def test_oom_watch():
    """R2 M3 / M2: an OOM kill is the container's own cap's only when its cgroup's `oom` counter rose with it; the
    host's OOM killer leaves `oom` alone. A benchmark-owned service's kills are recorded as such. Counters that start
    again (the container was restarted) are compared with 0."""
    f = Fake()
    keep = monitor.OOM_CAP_WINDOW_SEC
    try:
        m = f.monitor({"max_memory_gb": 24.0, "tick_sec": 5})
        f.pid(100, "mnt:[111]", f.root("main"), nspid=1)
        f.pid(101, "mnt:[111]", f.root("main"), start=5000, ppid=77, nspid=9)
        f.pid(200, "mnt:[222]", f.sidecar_root("sim"), nspid=1)
        cg = f.cgroup("docker-main.scope", pids=[100, 101], anon_gb=3.0, max_gb=29.0, oom=0, oom_kill=0)
        f.cgroup("docker-sim.scope", pids=[200], anon_gb=20.0, max_gb=24.0, oom=4, oom_kill=2)   # before it was watched
        m.tick_once(1000.0)
        g = m.groups()
        check(sorted((x["kind"], x["role"]) for x in g.values()) == [("observe", "sidecar"), ("scope", "main")], f"both watched: {g}")
        check(f.events("oom") == [], "the first reading is the baseline: nothing from before the container was watched")
        # 1. the reviewer's case: the trial uses 3 of 29 GiB, the host runs out of memory (other trials) and its OOM
        #    killer takes a process of this container: oom_kill rises, oom (the cgroup's own limit) does not
        f.cgroup("docker-main.scope", oom=0, oom_kill=1)
        m.tick_once(1005.0)
        ev = f.events("oom")
        check(len(ev) == 1 and ev[0]["cause"] == "host" and ev[0]["scope"] is True and ev[0]["role"] == "main"
              and ev[0]["count"] == 1 and ev[0]["memory_cap_gb"] == 29.0 and ev[0]["memory_current_gb"] == 3.0,
              f"a kill without the cgroup's own oom event is the host's: {ev}")
        check(rcb_limits.violations([], m.lim, ev) == [], "and not a violation")
        # 2. the container reaches its own cap: oom and oom_kill rise together
        f.cgroup("docker-main.scope", max=7, oom=1, oom_kill=2)
        check(m.oomw.scan() is True, "a change is reported (the watch then reads faster)")
        ev = f.events("oom")
        check(len(ev) == 2 and ev[1]["cause"] == "cap" and ev[1]["cap_hits"] == 1, f"at its own cap: {ev}")
        check([v["metric"] for v in rcb_limits.violations([], m.lim, ev)] == ["oom"], "which is the violation")
        check(m.oomw.scan() is False and len(f.events("oom")) == 2, "nothing new: no event, no change")
        # 3. the oom event is read first, the kill a moment later: still the cap's; long after: the host's
        f.cgroup("docker-main.scope", max=9, oom=2, oom_kill=2)
        m.oomw.scan()
        f.cgroup("docker-main.scope", max=9, oom=2, oom_kill=3)
        m.oomw.scan()
        check(f.events("oom")[-1]["cause"] == "cap", "the kill that follows the cgroup's oom event is the cap's")
        m.oomw.w[cg]["cap_t"] -= monitor.OOM_CAP_WINDOW_SEC + 1
        f.cgroup("docker-main.scope", max=9, oom=2, oom_kill=4)
        m.oomw.scan()
        check(f.events("oom")[-1]["cause"] == "host", "a kill long after the last oom event is not")
        # 4. the benchmark's own service is killed at its cap: recorded as the service's (scope false)
        f.cgroup("docker-sim.scope", oom=5, oom_kill=3)
        m.oomw.scan()
        e = f.events("oom")[-1]
        check(e["scope"] is False and e["role"] == "sidecar" and e["cause"] == "cap" and e["count"] == 1, f"the sidecar's: {e}")
        # 5. the container was restarted: a new cgroup under the same path, its counters start at 0 and are all the trial's
        n = len(f.events("oom"))
        f.cgroup("docker-sim.scope", oom=0, oom_kill=0)
        m.oomw.scan()
        check(len(f.events("oom")) == n, "counters that went back: no event")
        f.cgroup("docker-sim.scope", oom=1, oom_kill=1)
        m.oomw.scan()
        check(len(f.events("oom")) == n + 1 and f.events("oom")[-1]["count"] == 1, "then counted from 0")
        # ... also when the old cgroup's file stopped answering (ENODEV on a real cgroup) and the path is there again:
        # another directory under the same name
        sim_cg = os.path.join(f.d, "cgroup", "docker-sim.scope")
        os.close(m.oomw.w[sim_cg]["fd"])
        shutil.rmtree(sim_cg)
        import time
        time.sleep(0.02)                                       # (a new creation time, whatever inode it gets)
        f.cgroup("docker-sim.scope", pids=[200], anon_gb=20.0, max_gb=24.0, oom=1, oom_kill=1)   # already lost a process
        m.oomw.scan()
        e = f.events("oom")
        check(len(e) == n + 2 and e[-1]["count"] == 1 and e[-1]["cause"] == "cap" and e[-1]["scope"] is False,
              f"a new cgroup under the same path is compared with 0: {e[-2:]}")
        # ... but the same cgroup opened again (its file descriptor was lost, the cgroup was not) counts nothing twice
        os.close(m.oomw.w[sim_cg]["fd"])
        check(m.oomw.scan() is False and len(f.events("oom")) == n + 2, "the same cgroup reopened: no kill counted twice")
        f.cgroup("docker-sim.scope", oom=2, oom_kill=2)
        m.oomw.scan()
        check(len(f.events("oom")) == n + 3 and f.events("oom")[-1]["count"] == 1, "and goes on counting from where it was")
        # 6. a cgroup without a memory cap cannot be at its cap; a file that is gone or unreadable stops nothing
        f.cgroup("docker-main.scope", max_gb="max", oom=2, oom_kill=5)
        m.oomw.scan()
        e = f.events("oom")[-1]
        check(e["cause"] == "host" and "memory_cap_gb" not in e, f"no cap: {e}")
        os.remove(os.path.join(f.d, "cgroup", "docker-sim.scope", "memory.events"))
        os.close(m.oomw.w[os.path.join(f.d, "cgroup", "docker-sim.scope")]["fd"])
        n = len(f.events("oom"))
        check(m.oomw.scan() is False and len(f.events("oom")) == n, "a cgroup that is gone: nothing")
        with open(os.path.join(f.d, "cgroup", "docker-main.scope", "memory.events"), "w") as fh:
            fh.write("garbage\noom_kill x\n")
        check(m.oomw.scan() is False and len(f.events("oom")) == n, "unreadable counters: nothing")
        # 7. the watch thread reads on its own, between the samples
        f.cgroup("docker-main.scope", max_gb=29.0, oom=2, oom_kill=5)
        m.oomw.scan()
        monitor.OOM_CAP_WINDOW_SEC = keep
        m.oomw.start()
        f.cgroup("docker-main.scope", oom=3, oom_kill=6)
        end = time.time() + 5
        while time.time() < end and len(f.events("oom")) == n:
            time.sleep(0.01)
        check(len(f.events("oom")) == n + 1 and f.events("oom")[-1]["cause"] == "cap", "the thread records a kill by itself")
        # the seal closes the record: the counters are read once more, then the thread ends (what happens to a sidecar
        # in the collect hooks after it is the grader's to judge)
        f.cgroup("docker-main.scope", oom=4, oom_kill=7)
        m.seal()
        check(len(f.events("oom")) == n + 2 and m.oomw.stopped, "a kill just before the seal is in the sealed record")
        m.oomw.thread.join(5)
        check(not m.oomw.thread.is_alive(), "the watch thread ends with the seal")
        f.cgroup("docker-main.scope", oom=5, oom_kill=8)
        time.sleep(0.2)
        check(len(f.events("oom")) == n + 2, "nothing is recorded after the seal")
        summary = rcb_limits.read_json(os.path.join(f.rec, "summary.json"))
        check(summary["sealed"] and any(v["metric"] == "oom" for v in summary["violations"]), f"the summary has the cap kills: {summary['violations']}")
    finally:
        monitor.OOM_CAP_WINDOW_SEC = keep
        f.close()


def test_oom_verdicts():
    """R2 M2 / M3: what the verifier step makes of the kernel's OOM kills."""
    ok = {"format": rcb_limits.FORMAT, "sealed": True, "scope_seen": True}
    agent0 = {"success": 0, "infra_error": 0, "finalized": 1}        # e.g. a standard grader on reason = sim_crashed_on_call
    side = [{"t": t, "event": "oom", "role": "sidecar", "scope": False, "count": 1, "cause": "cap"} for t in (1100, 1150, 1190)]
    for enforce in (0, 1):
        # M2: the simulator sidecar was OOM-killed at its docker cap and the episode ended without success: not the agent's 0
        out, txt, det = _verify(_samples(), side, dict(ok, enforce=enforce), reward=agent0, txt="0")
        check(out["infra_error"] == 1 and out["resource_service_oom"] == 1 and out["resource_service_oom_kills"] == 3
              and out["success"] == 0 and txt == "0" and "resource_limit_exceeded" not in out
              and out["limits_violation_observed"] == 0 and "benchmark-owned service" in det["verdict"],
              f"sidecar OOM, no success, enforce={enforce}: infrastructure, not the agent's failure: {out}")
        check(len(det["oom_kills"]) == 3, "the events are in resource_limits.json")
        # ... the same when the host's killer took it
        host_side = [dict(e, cause="host") for e in side]
        out, _, _ = _verify(_samples(), host_side, dict(ok, enforce=enforce), reward=agent0, txt="0")
        check(out["infra_error"] == 1 and out["resource_service_oom"] == 1, f"sidecar killed by the host: {out}")
        # ... but a success stands: the service recovered and the grader accepted the episode
        out, txt, _ = _verify(_samples(), side, dict(ok, enforce=enforce))
        check(out["success"] == 1 and txt == "1" and out.get("infra_error", 0) == 0 and out["resource_service_oom_kills"] == 3
              and "resource_service_oom" not in out, f"sidecar OOM, success, enforce={enforce}: the verdict stands: {out}")
        # no kill in the record: nothing changes
        out, txt, _ = _verify(_samples(), (), dict(ok, enforce=enforce), reward=agent0, txt="0")
        check(out["infra_error"] == 0 and out["resource_service_oom_kills"] == 0 and txt == "0", f"no OOM: the agent's 0: {out}")
    # no record at all (a host that cannot run the monitor): the step stays a no-op, as before
    out, txt, _ = _verify(None, reward=agent0, txt="0")
    check(out["infra_error"] == 0 and out["resource_monitor_missing"] == 1 and out["resource_service_oom_kills"] == 0,
          f"no record, not enforced: reported only: {out}")
    # M3: a process in the scope killed by the host's OOM killer (not at its container's cap)
    host = [{"t": 1100, "event": "oom", "role": "main", "scope": True, "count": 1, "cause": "host"}]
    out, txt, det = _verify(_samples(), host, dict(ok, enforce=1))
    check(out["infra_error"] == 1 and out["resource_host_oom"] == 1 and out["resource_host_oom_kills"] == 1
          and "resource_limit_exceeded" not in out and "over_oom" not in out and out["limits_violation_observed"] == 0
          and out["success"] == 0 and out["success_before_limits"] == 1 and txt == "0",
          f"host OOM kill, enforced: not a result, never the agent's violation: {out}")
    out, txt, _ = _verify(_samples(), host, dict(ok, enforce=0))
    check(out["success"] == 1 and txt == "1" and out.get("infra_error", 0) == 0 and out["resource_host_oom_kills"] == 1
          and "resource_host_oom" not in out, f"host OOM kill, observed only: reported: {out}")
    # ... at its own cap: the violation, as before
    cap = [dict(host[0], cause="cap")]
    out, txt, _ = _verify(_samples(), cap, dict(ok, enforce=1))
    check(out["resource_limit_exceeded"] == 1 and out["over_oom"] == 1 and out["success"] == 0 and txt == "0"
          and out.get("infra_error", 0) == 0 and out["resource_oom_kills"] == 1, f"OOM at the cap, enforced: fails: {out}")
    out, txt, _ = _verify(_samples(), cap, dict(ok, enforce=0))
    check(out["success"] == 1 and txt == "1" and out["limits_violation_observed"] == 1 and out["over_oom"] == 1,
          f"OOM at the cap, observed only: {out}")
    # a violation wins over the sidecar's OOM (the agent's own breach), enforced
    out, _, _ = _verify(_samples(), cap + side, dict(ok, enforce=1), reward=agent0, txt="0")
    check(out["resource_limit_exceeded"] == 1 and out.get("infra_error", 0) == 0, f"violation and sidecar OOM: {out}")


# --------------------------------------------------------------------------------------------------- the agent's files, before the grader
def test_sanitize():
    """R2 m6: what the agent left in /app/output is untrusted input. A link out of it (rcb_session_log.jsonl ->
    /dev/zero made a grader read without end), a FIFO (opening it blocks) and an endless session log are dealt with
    before the grader runs; everything a grader could read safely stays byte for byte."""
    d = tempfile.mkdtemp(prefix="rcb-sanitize-")
    try:
        out = os.path.join(d, "app", "output")
        os.makedirs(os.path.join(out, "sub"))
        outside = os.path.join(d, "secret.txt")
        open(outside, "w").write("the verifier's own file\n")
        open(os.path.join(out, "trajectory.npz"), "wb").write(b"PK\x03\x04 deliverable")
        open(os.path.join(out, "sub", "notes.txt"), "w").write("notes\n")
        os.symlink("/dev/zero", os.path.join(out, "rcb_session_log.jsonl"))            # the reviewer's case
        os.symlink(outside, os.path.join(out, "sub", "peek.txt"))                       # a link out of the directory
        os.symlink("trajectory.npz", os.path.join(out, "latest.npz"))                   # a link to the agent's own file: stays
        os.symlink(os.path.join(d, "app"), os.path.join(out, "up"))                     # a link to a directory (a loop)
        os.symlink("nowhere", os.path.join(out, "dangling"))
        os.mkfifo(os.path.join(out, "pipe.jsonl"))
        done = rcb_limits.sanitize([out])
        left = sorted(os.path.relpath(os.path.join(dp, n), out) for dp, dn, fn in os.walk(out) for n in dn + fn)
        check(left == ["latest.npz", "sub", "sub/notes.txt", "trajectory.npz"], f"what is left: {left}")
        check(len(done) == 5, f"five things removed: {done}")
        check(open(os.path.join(out, "latest.npz"), "rb").read() == b"PK\x03\x04 deliverable"
              and open(outside).read() == "the verifier's own file\n", "the deliverable and the link's target are untouched")
        check(rcb_limits.sanitize([out]) == [], "nothing more to do the second time")
        # an endless session log is cut; a normal one is not touched
        log = os.path.join(out, "rcb_session_log.jsonl")
        open(log, "w").write('{"ev": "session_start"}\n' * 10)
        check(rcb_limits.sanitize([out], max_log=4096) == [] and os.path.getsize(log) == 240, "a normal log stays")
        open(log, "w").write("x" * 10000)
        done = rcb_limits.sanitize([out], max_log=4096)
        check(os.path.getsize(log) == 4096 and len(done) == 1, f"a log over the cap is cut: {done}")
        # the grader's reading loop (as in the privileged graders) now ends on the reviewer's input
        os.remove(log)
        os.symlink("/dev/zero", log)
        rcb_limits.sanitize([out])
        n = 0
        try:
            with open(log) as fh:
                for n, _line in enumerate(fh):
                    pass
        except OSError:
            pass
        check(n == 0 and not os.path.lexists(log), "the session log that pointed to /dev/zero is gone")
        # a root that is missing or itself a link, and the command line the generated test.sh line runs: never an error
        check(rcb_limits.sanitize([os.path.join(d, "missing")]) == [], "no directory: nothing")
        os.symlink("/", os.path.join(d, "rootlink"))
        check(len(rcb_limits.sanitize([os.path.join(d, "rootlink")])) == 1 and os.path.isdir("/tmp"), "a root that is a link is removed, not walked")
        os.mkfifo(os.path.join(out, "again"))
        r = subprocess.run([sys.executable, os.path.join(HERE, "rcb_limits.py"), "sanitize", out, os.path.join(d, "missing")],
                           capture_output=True, text=True)
        check(r.returncode == 0 and "again" in r.stderr and not os.path.lexists(os.path.join(out, "again")), f"the command: {r.stderr}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------------------------------- the default changes no verdict
def _step_in_process(reward_json, reward_txt, record, switch):
    """The verifier step (run_step) in this process, on a temporary /tests, record and /logs/verifier."""
    d = tempfile.mkdtemp(prefix="rcb-verify-")
    try:
        rec, tests, logs = (os.path.join(d, x) for x in ("rec", "tests", "logs"))
        for x in (tests, logs):
            os.makedirs(x)
        json.dump({"max_gpu_memory_gb": 4.0, "max_memory_gb": 8.0, "max_processes": 100, "max_disk_gb": 10.0,
                   "sustain_sec": 60, "window_sec": 120, "tick_sec": 5}, open(os.path.join(tests, "rcb_limits.json"), "w"))
        shutil.copy(os.path.join(HERE, "rcb_limits.py"), tests)
        if reward_json is not None:
            open(os.path.join(logs, "reward.json"), "w").write(reward_json)
        if reward_txt is not None:
            open(os.path.join(logs, "reward.txt"), "w").write(reward_txt)
        if record is not None:
            os.makedirs(rec)
            samples, events, summary = record
            with open(os.path.join(rec, "samples.jsonl"), "w") as fh:
                for x in samples:
                    fh.write((x if isinstance(x, str) else json.dumps(x)) + "\n")
            with open(os.path.join(rec, "events.jsonl"), "w") as fh:
                for x in events:
                    fh.write((x if isinstance(x, str) else json.dumps(x)) + "\n")
            if summary is not None:
                json.dump(summary, open(os.path.join(rec, "summary.json"), "w"))
        keep = {k: os.environ.get(k) for k in ("RCB_MONITOR_RECORD", "RCB_VERIFIER_LOGS", "RCB_LIMITS_ENFORCE")}
        os.environ.update(RCB_MONITOR_RECORD=rec, RCB_VERIFIER_LOGS=logs)
        os.environ.pop("RCB_LIMITS_ENFORCE", None)
        if switch is not None:
            os.environ["RCB_LIMITS_ENFORCE"] = switch
        err = sys.stderr
        try:
            sys.stderr = open(os.devnull, "w")
            spec = importlib.util.spec_from_file_location("rcb_limits_under_test", os.path.join(tests, "rcb_limits.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            rc = mod.run_step()
        finally:
            sys.stderr.close()
            sys.stderr = err
            for k, v in keep.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

        def rd(name):
            try:
                return open(os.path.join(logs, name)).read()
            except OSError:
                return None
        return rc, rd("reward.json"), rd("reward.txt")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_default_is_neutral():
    """With the default (RCB_LIMITS_ENFORCE unset / 0 / false / empty) the step never changes the grader's verdict:
    reward.txt, success and reward stay what they were for every grader output x every record x every spelling of
    "off", and it never creates a reward.json. infra_error changes in exactly one case, in both modes (R2 M2): a
    benchmark-owned service was OOM-killed and the grader's verdict is not a success. (The reviewer's battery of round
    2, 1320 combinations, extended by the records with OOM kills.)"""
    def samples(gpu=6.0, n=40):
        return [{"t": 1000 + 5 * i, "scope": {"gpu_memory_gb": gpu if i > 5 else 0.5, "memory_gb": 2.0, "processes": 10,
                                               "disk_gb": None}} for i in range(n)]
    ok = {"format": rcb_limits.FORMAT, "sealed": True, "enforce": 0, "scope_seen": True}
    oom = {"event": "oom", "t": 1010, "count": 1}
    rewards = {"ok1": '{"success": 1, "infra_error": 0}', "ok0": '{"success": 0}', "nosuccess": '{"reward": 1}',
               "list": "[1]", "invalid": '{"success": 1', "empty": "", "none": None, "nan": '{"success": 1, "x": NaN}',
               "infra": '{"success": 0, "infra_error": 1}', "str": '{"success": 1, "note": "abc"}',
               "fail_reward": '{"success": 0, "reward": 0.0, "infra_error": 0}', "false": '{"success": false, "infra_error": 0}'}
    records = {
        "norecord": None,
        "violating_obs": (samples(), [], ok),
        "oom_obs": (samples(1), [dict(oom, scope=True, role="main", cause="cap")], ok),
        "oom_old_format": (samples(1), [dict(oom, scope=True, role="main")], ok),
        "oom_host": (samples(1), [dict(oom, scope=True, role="main", cause="host")], ok),
        "fatal_obs": (samples(1), [{"event": "fatal", "why": "x"}], ok),
        "unsealed": (samples(), [], None),
        "garbage_samples": (['{"t": "abc", "scope": 5}', '{"scope": {}}', "[]", "5", '{"t": 3}'], [], ok),
        "garbage_events": (samples(1), ["[]", "5", '"oom"', '{"event": "oom", "count": "x", "scope": "yes"}', "{"], ok),
        "weird_values": ([{"t": 1000 + 5 * i, "scope": {"gpu_memory_gb": "9", "memory_gb": None, "processes": [1],
                                                        "disk_gb": {}}} for i in range(30)], [], ok),
        "summary_list": (samples(), [], []),
        "enforce_str0": (samples(), [], dict(ok, enforce="0")),
        "enforce_false": (samples(), [], dict(ok, enforce=False)),
        "enforce_null": (samples(), [], dict(ok, enforce=None)),
        # a benchmark-owned service OOM-killed: the one case that sets infra_error (when there is no success)
        "service_oom_cap": (samples(1), [dict(oom, scope=False, role="sidecar", cause="cap")], ok),
        "service_oom_host": (samples(1), [dict(oom, scope=False, role="sidecar", cause="host")] * 3, ok),
        "service_oom_norecordsummary": (samples(1), [dict(oom, scope=False, role="sidecar")], None),
    }
    n = bad = 0
    for (rn, rj), (cn, rec), sw, txt in itertools.product(rewards.items(), records.items(), (None, "0", "false", ""),
                                                          ("1\n", "0\n", None)):
        n += 1
        rc, rj2, rt2 = _step_in_process(rj, txt, rec, sw)
        problems = []
        if rc != 0:
            problems.append(f"rc={rc}")
        if rt2 != txt:
            problems.append(f"reward.txt {txt!r} -> {rt2!r}")
        try:
            before = json.loads(rj) if rj else None
        except ValueError:
            before = None
        try:
            after = json.loads(rj2) if rj2 else None
        except ValueError:
            after = "INVALID"
        if isinstance(before, dict):
            if not isinstance(after, dict):
                problems.append(f"reward.json broke: {rj2!r}")
            else:
                service_oom = cn.startswith("service_oom") and not before.get("success")
                for k in ("success", "infra_error", "reward"):
                    want = 1 if (k == "infra_error" and service_oom) else before.get(k)
                    if after.get(k) != want and not (k == "success" and k not in before and after.get(k) == 0):
                        problems.append(f"{k}: {before.get(k)} -> {after.get(k)}")
                if after.get("resource_service_oom", 0) != int(service_oom):
                    problems.append(f"resource_service_oom = {after.get('resource_service_oom')}")
                nonnum = [k for k, v in after.items() if k not in before and (isinstance(v, bool) or not isinstance(v, (int, float)))]
                if nonnum:
                    problems.append(f"non-numeric fields added: {nonnum}")
        elif rj2 != rj:
            problems.append(f"reward.json created or changed from a non-object: {rj!r} -> {rj2!r}")
        if problems:
            bad += 1
            print("NOT NEUTRAL", rn, cn, repr(sw), repr(txt), problems)
    check(n == len(rewards) * len(records) * 12 and n >= 1320, f"the battery ran ({n} combinations)")
    check(bad == 0, f"{bad} of {n} combinations changed a verdict with enforcement off")


def test_clock_and_beacon():
    """usage.json carries the agent's clock (from the monitor's start, never more time than the agent has),
    after a failed tick too, and `monitor.py beacon` writes it with `"measured": false` where no monitor can run."""
    c = monitor.clock(1000.0, 400.0, 3600)
    check(c["elapsed_s"] == 600.0 and c["time_left_s"] == 3000.0 and c["time_limit_s"] == 3600, f"clock: {c}")
    check(c["deadline_utc"] == "1970-01-01T01:06:40Z", f"deadline: {c}")
    check(monitor.clock(5000.0, 400.0, 3600)["time_left_s"] == 0.0, "time left never negative")
    check("time_left_s" not in monitor.clock(1000.0, 400.0, 0), "no time limit: elapsed only")
    beacon_dir = tempfile.mkdtemp(prefix="rcb-beacon-test-")
    real = (monitor.SCOPE_BEACON, monitor.LIMITS, monitor.REC)
    try:
        monitor.SCOPE_BEACON, monitor.REC = beacon_dir, os.path.join(beacon_dir, "rec")
        monitor.LIMITS = os.path.join(beacon_dir, "limits.json")
        with open(monitor.LIMITS, "w") as fh:
            json.dump({"max_memory_gb": 8.0, "tick_sec": 5, "agent_timeout_sec": 600}, fh)
        monitor.beacon(rounds=1)
        u = rcb_limits.read_json(os.path.join(beacon_dir, "usage.json"))
        check(u["measured"] is False and u["enforced"] == 0 and u["limits"]["max_memory_gb"] == 8.0, f"beacon: {u}")
        check(u["time_limit_s"] == 600 and 590 <= u["time_left_s"] <= 600, f"beacon clock: {u}")
        started = rcb_limits.read_json(os.path.join(monitor.REC, "beacon.json"))["started"]
        monitor.beacon(rounds=1)                       # a restarted beacon keeps the first start
        check(rcb_limits.read_json(os.path.join(monitor.REC, "beacon.json"))["started"] == started, "beacon restart")
        m = Fake().monitor({"max_memory_gb": 8.0, "tick_sec": 5, "agent_timeout_sec": 600})
        m.clock_t0 = monitor.now() - 100
        m.write_usage(monitor.now())                   # before any sample (or after a failed tick): the clock still runs
        u = rcb_limits.read_json(os.path.join(beacon_dir, "usage.json"))
        check(u["measured"] is False and u["memory_gb"] is None and 495 <= u["time_left_s"] <= 500, f"usage: {u}")
        m._usage_vals = {"gpu_memory_gb": 0.0, "memory_gb": 1.5, "processes": 3, "disk_gb": None}
        m.write_usage(monitor.now())
        u = rcb_limits.read_json(os.path.join(beacon_dir, "usage.json"))
        check(u["measured"] is True and u["memory_gb"] == 1.5 and u["processes"] == 3, f"usage: {u}")
    finally:
        monitor.SCOPE_BEACON, monitor.LIMITS, monitor.REC = real
        shutil.rmtree(beacon_dir, ignore_errors=True)


def test_session_log_copy():
    """The monitor copies the agent's session log append-only; the verifier gives the grader that copy when the
    agent's file is gone or rewritten, and the agent's own file when it is what was written (plus a last tick)."""
    d = tempfile.mkdtemp(prefix="rcb-slog-test-")
    real_rec = monitor.REC
    try:
        rec, root = os.path.join(d, "rec"), os.path.join(d, "root")
        os.makedirs(rec)
        os.makedirs(os.path.join(root, "app", "output"))
        monitor.REC = rec
        log = os.path.join(root, "app", "output", "rcb_session_log.jsonl")
        c = monitor.SessionLogCopy()
        c.step(root)
        check(not os.path.exists(os.path.join(rec, "session_log")), "no log yet: nothing copied")
        with open(log, "w") as f:
            f.write('{"e":"session","n":1}\n')
        c.step(root)
        with open(log, "a") as f:
            f.write('{"e":"reset","n":2}\n')
        c.step(root)
        out = os.path.join(d, "out")
        os.makedirs(out)
        vlogs = os.path.join(d, "vlogs")
        os.environ["RCB_VERIFIER_LOGS"] = vlogs
        agent = os.path.join(out, "rcb_session_log.jsonl")
        with open(agent, "w") as f:                    # the agent's file: what was written, and one line more
            f.write('{"e":"session","n":1}\n{"e":"reset","n":2}\n{"e":"step","n":3}\n')
        check(rcb_limits.session_log_source(agent, record=rec) is None, "an untouched log stays the grader's input")
        st = rcb_limits.read_json(os.path.join(vlogs, "session_log.json"))
        check(st["tampered"] == 0 and st["from_monitor"] == 0, f"status: {st}")
        with open(log, "w") as f:                      # the agent rewrites it: one line left, one forged
            f.write('{"e":"session","n":1}\n{"e":"forged"}\n')
        c.step(root)
        os.unlink(log)
        c.step(root)
        ev = [e["event"] for e in rcb_limits.read_jsonl(os.path.join(rec, "events.jsonl"))]
        check("session_log_rewritten" in ev and "session_log_removed" in ev, f"events: {ev}")
        os.unlink(agent)
        msg = rcb_limits.session_log_source(agent, record=rec)
        got = open(agent).read().splitlines()
        check(msg and got == ['{"e":"session","n":1}', '{"e":"reset","n":2}', '{"e":"forged"}'], f"merged: {got}")
        st = rcb_limits.read_json(os.path.join(vlogs, "session_log.json"))
        check(st["tampered"] == 1 and st["from_monitor"] == 1, f"status: {st}")
        os.symlink("/etc/hostname", log)               # a link is never followed (it would resolve in the monitor)
        c2 = monitor.SessionLogCopy()
        c2.step(root)
        check(c2.s["ino"] is None, "a symbolic link is not copied")
    finally:
        monitor.REC = real_rec
        os.environ.pop("RCB_VERIFIER_LOGS", None)
        shutil.rmtree(d, ignore_errors=True)


def test_stop_without_cgroup():
    """A container without a cgroup of its own (rootless podman, the user's cgroup not delegated) shares its parent's
    (conmon's), and its runtime cannot stop it (`pid: host`: podman signals the cgroup's processes, which are none):
    the monitor then ends itself after the seal, once the seal hook has read the summary (seal.done), or after the wait."""
    d = tempfile.mkdtemp(prefix="rcb-stop-test-")
    real = (monitor.PROC, monitor.REC)
    try:
        monitor.PROC, monitor.REC = os.path.join(d, "proc"), os.path.join(d, "rec")
        os.makedirs(monitor.REC)
        for who in ("self", str(os.getppid())):
            os.makedirs(os.path.join(monitor.PROC, who))

        def cg(who, text):
            with open(os.path.join(monitor.PROC, who, "cgroup"), "w") as f:
                f.write(text)
        cg("self", "0::/user/libpod-1234\n")
        cg(str(os.getppid()), "0::/user/session\n")
        check(monitor.own_cgroup(), "a cgroup of its own (docker, podman with a delegated cgroup)")
        cg("self", "0::/user/session\n")
        check(not monitor.own_cgroup(), "the parent's cgroup: none of its own")
        os.unlink(os.path.join(monitor.PROC, "self", "cgroup"))
        check(monitor.own_cgroup(), "unreadable: the runtime's stop is trusted")
        m = Fake().monitor({"max_memory_gb": 8.0, "tick_sec": 5})
        t = monitor.now()
        m.linger(0.6)
        check(0.5 <= monitor.now() - t < 5, "no seal hook: it ends after the wait")
        with open(os.path.join(monitor.REC, "summary.json"), "w") as f:
            json.dump({"sealed": True, "n_samples": 1}, f)
        check(monitor.seal_cmd(1) == 0 and os.path.exists(os.path.join(monitor.REC, "seal.done")),
              "the seal hook marks that it has read the summary")
        t = monitor.now()
        m.linger(30)
        check(monitor.now() - t < 2, "after the seal hook: it ends at once")
    finally:
        monitor.PROC, monitor.REC = real
        shutil.rmtree(d, ignore_errors=True)


def main():
    for t in (test_classify_race, test_dead_leader_and_zombies, test_disk_walk, test_disk_baseline, test_emergency,
              test_kill_path, test_switch, test_verify_edges, test_oom_watch, test_oom_verdicts, test_sanitize, test_default_is_neutral,
              test_clock_and_beacon, test_session_log_copy, test_stop_without_cgroup):
        t()
    shutil.rmtree(os.environ["RCB_MONITOR_RECORD"], ignore_errors=True)
    print("rcb_monitor test_monitor: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
