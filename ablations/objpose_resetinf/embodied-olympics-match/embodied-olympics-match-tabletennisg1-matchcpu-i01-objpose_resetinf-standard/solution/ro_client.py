"""Contract ①, the player's side: a stdlib client of the match service and the loop that lets a built-in player (the
sport's reference player, scripted opponents, check policies) play over HTTP exactly as a model's program would. In a
task it is the seat's `ro_client` module (the `game` command imports it).

A built-in player is an object made by factory(spec, seat, seed) with
    act(view) -> body | None     view = {"state": <the seat's state>, "observation": <the /observe observation>}
                                 (body = the /act request; None = nothing now, realtime only)
    review(reply) -> (why, plan) optional; called after each own action (turn) or at each review (realtime)
    message(view) -> text | None optional (realtime, core 0.2.21): a team-channel message to the seat's teammates
                                 (POST /say; refused messages, e.g. faster than the channel allows, are dropped)
    every_s                      optional attribute (realtime): the game seconds the loop waits after each decision
                                 (default 0.05); a player that controls at a faster rate declares it (e.g. 0.01)
    play(seat) -> final state    optional (realtime): the player's own loop over the Seat client (main opens the
                                 session and sends start first), for a controller that acts every control step

    python3 -m core.client MODULE:FACTORY        (SIM_URL, SEAT; e.g. the task's solution/oracle_play.py)
    python3 -m ro_client --session               (core 0.3.0) open this seat's session: the harness adapter runs it
                                                 before it starts the harness; returns once the match has opened (the
                                                 start barrier t0, core/phases.py), exit 1 if the service never said so

Acts (core 0.3.0): Seat.call("act", body) adds a request_id (core/acts.py) and, when the connection drops before the
reply, sends the act again with the same id (the service applies it at most once); Seat.act([act, ...]) sends a batch
(one act per entity of the seat, all taking effect at the same control step).

Act timing (core 0.4.5). In real time the reply to an act comes once the act has taken effect: at the control-step
boundary e = r + L after its receipt step r (/spec action; core 0.5.0: no reaction delay), i.e. after up to L + 1
control steps, at most (L + 1) x timing.period_s wall seconds. A loop that waits for each reply therefore acts at most
once every L + 1 control steps (e.g. L = 3: every 4th step), and one that also waits for an image (an observation with
images returns when its newest frame is delivered, after the camera latency) less often still. To act at every control
step, send acts without waiting for their replies, up to /spec action.in_flight_per_robot per robot:
Seat.act(cmd, wait=False) returns at once a concurrent.futures.Future of the reply (its request_id as .request_id);
the act is sent from the Seat's own sender threads, with the same request id and resend rule as a blocking act, so it
still takes effect at most once. The effect step is the same either way (e = r + L);
only the loop's rate changes. `status` returns the seat's state at once (no image).

A real-time loop (core 0.5.4; measured at x1, review doc realtime1): keep one Seat per thread in ONE long-running
process (a `game` command per call costs ~0.3 s of interpreter start; the Seats of a seat in a process share its
request budget). Control thread: send the batch of every robot's act (Seat.act([...])) and take the next state from
its reply (`now`: the state at the step it took effect), so one request per control step; `status` only when there is
nothing to send. Camera thread: observe once per new frame (an every-step camera returns at once the frame of k - L;
asking again within the same step returns the same frame and spends the budget: after a new frame wait about 0.8
control periods, /spec timing.period_s, before the next observe). A request costs ~1-2 ms on the
host (p99 ~6 ms).
"""
from __future__ import annotations

import hashlib
import http.client
import importlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

try:                                    # the seat: tools/generate.py ships core/taskspec.py as ro_taskspec next to us
    import ro_taskspec as _taskspec
except ImportError:                     # the repository, the sim, the practice sandbox
    from core import taskspec as _taskspec


def settings() -> dict:
    """The seat's settings, read now (core/taskspec.py seat_settings: the one reader of the environment)."""
    return _taskspec.seat_settings()


# ---------------------------------------------------------------- the persistent disk's use (core 0.4.3)
def _matches(path: str, patterns) -> bool:
    """= framework/run/carry.py excluded(): the path itself, a directory above it, or an fnmatch glob."""
    import fnmatch  # noqa: PLC0415
    for pat in patterns or []:
        p = pat.rstrip("/")
        if path == p or path.startswith(p + "/") or fnmatch.fnmatchcase(path, p):
            return True
    return False


def disk_use(counts: dict, home: str | None, budget_s: float = 20.0) -> tuple[int, bool]:
    """(bytes, complete) of a persistent seat's carried state, counted as the snapshot counts it (framework/run/
    carry.py build): the regular files under the include paths, without the exclude paths (credentials) and the skip
    paths (what the harness reinstalls); $HOME and ~ are the agent user's home. complete is False when the walk ran
    out of its time budget (the count is then a lower bound)."""
    def expand(xs):
        out = []
        for x in xs or []:
            x = str(x)
            if home:
                x = x.replace("$HOME", home.rstrip("/") or "/")
                if x == "~" or x.startswith("~/"):
                    x = home.rstrip("/") + x[1:]
            out.append(os.path.normpath(x) if x.startswith("/") else x)
        return out
    inc, exc, skip = expand(counts.get("include")), expand(counts.get("exclude")), expand(counts.get("skip"))
    total, seen, end = 0, set(), time.monotonic() + budget_s
    stack = [p for p in inc if p.startswith("/")]
    while stack:
        if time.monotonic() > end:
            return total, False
        p = stack.pop()
        if p in seen or _matches(p, exc) or _matches(p, skip):
            continue
        seen.add(p)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        import stat as _stat  # noqa: PLC0415
        if _stat.S_ISREG(st.st_mode):
            total += st.st_size
        elif _stat.S_ISDIR(st.st_mode):
            try:
                stack.extend(e.path for e in os.scandir(p))
            except OSError:
                continue
    return total, True


def user_home() -> str | None:
    """The seat user's home as the backend finds it for the snapshot ($HOME: the passwd entry), never the
    environment."""
    import pwd  # noqa: PLC0415
    try:
        return pwd.getpwuid(os.getuid()).pw_dir
    except (KeyError, OSError):
        return None


def disk_status(disk: dict, home: str | None) -> dict:
    """GET status `disk` from the Host (cap_bytes, warn_at, counts) -> what `game status` shows: used_bytes, cap_bytes,
    warn (at warn_at of the cap), over, and a note (decided 10-21: a soft cap; over it at the end of the match this
    match's state is not carried, the next match starts from your last carried state)."""
    cap, warn_at = int(disk.get("cap_bytes") or 0), float(disk.get("warn_at") or 0.8)
    used, complete = disk_use(disk.get("counts") or {}, home)
    out = {"used_bytes": used, "cap_bytes": cap, "warn": bool(cap) and used >= warn_at * cap,
           "over": bool(cap) and used > cap}
    if not complete:
        out["complete"] = False
    gib = 1 << 30
    if out["over"]:
        out["note"] = (f"over the cap ({used / gib:.2f} of {cap / gib:g} GiB): if you are still over it when the match "
                       "ends, this match's state is not carried; your next match starts from your last carried state")
    elif out["warn"]:
        out["note"] = (f"{used / gib:.2f} of {cap / gib:g} GiB used ({warn_at:.0%} reached): over the cap at the end "
                       "of the match, this match's state is not carried")
    return out


# ---------------------------------------------------------------- D3: the identity of the program sending an act
# (core/deploys.py; the same code in core/game.py): request headers, record only (never scored, never replayed).
PROG_EXT = ("py", "sh", "bash", "js", "mjs", "ts", "toml", "yaml", "yml", "cfg", "ini", "c", "cc", "cpp", "h", "hpp",
            "rs", "go", "jl", "r", "lua", "m")            # = tools/snapshot_watch.py PROG_EXT
PROG_NAMES = ("Makefile",)
PROG_SKIP = ("views", "frames", "snapshots", "__pycache__", ".git", "node_modules", ".cache")
MAX_FILES, MAX_HASH_BYTES = 4000, 32 << 20
WRAPPERS = ("sh", "bash", "dash", "zsh", "ash", "env", "timeout", "nohup", "setsid", "stdbuf", "nice", "time",
            "xargs", "flock", "taskset", "chrt", "ionice")
GENERIC_SHELLS = ("tmux", "tmux: server", "script", "sshd", "tini", "dumb-init", "docker-init")   # exact names
# core 0.3.0: the harness's own process names come from the seat (players/adapters.toml shell_markers -> the runner's
# RO_AGENT_SHELLS_<seat> -> RO_AGENT_SHELLS in the seat container): prefixes, e.g. a harness binary with a platform suffix
SHELL_MARKERS = settings()["agent_shells"]
AGENT_SHELLS = GENERIC_SHELLS + SHELL_MARKERS                 # for the record (tools)


def agent_shell(base: str) -> bool:
    """Is a process with this name the agent's own shell or harness (the end of the program-process walk)?"""
    return base in GENERIC_SHELLS or (bool(SHELL_MARKERS) and base.startswith(SHELL_MARKERS))


def program_sha(root=None, cache=None):
    """(sha256[:16] of the seat's program files under root, how many): paths + contents, cached by mtime / size."""
    root = root or settings()["program_dir"]
    cache = {} if cache is None else cache
    rows, budget, n = [], MAX_HASH_BYTES, 0
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in PROG_SKIP)
        for f in sorted(files):
            if (f.rpartition(".")[2].lower() if "." in f else "") not in PROG_EXT and f not in PROG_NAMES:
                continue
            n += 1
            if n > MAX_FILES:
                break
            p = os.path.join(d, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            key = [st.st_mtime_ns, st.st_size]
            got = cache.get(p)
            if got and got[:2] == key:
                dig = got[2]
            elif st.st_size <= budget:
                try:
                    with open(p, "rb") as fh:
                        dig = hashlib.sha256(fh.read()).hexdigest()[:16]
                except OSError:
                    continue
                budget -= st.st_size
                cache[p] = key + [dig]
            else:
                dig = f"size{st.st_size}-mtime{st.st_mtime_ns}"
            rows.append(f"{os.path.relpath(p, root)}\0{dig}\n")
        if n > MAX_FILES:
            break
    seen = {os.path.join(root, r.partition("\0")[0]) for r in rows}
    for p in [p for p in cache if p not in seen]:
        del cache[p]
    return hashlib.sha256("".join(rows).encode()).hexdigest()[:16], min(n, MAX_FILES)


def _proc(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        with open(f"/proc/{pid}/stat") as f:
            rest = f.read().rpartition(")")[2].split()
        return argv, int(rest[1]), int(rest[19])        # argv, ppid, starttime
    except (OSError, ValueError, IndexError):
        return None


def proc_ident(via, pid=None):
    """The program process: the nearest process from pid (default: this one) up that is not a command wrapper."""
    pid = pid or os.getpid()
    for _ in range(16):
        got = _proc(pid)
        if got is None:
            return None
        argv, ppid, start = got
        base = os.path.basename(argv[0]) if argv else ""
        wrapper = base in WRAPPERS and (base not in ("sh", "bash", "dash", "zsh", "ash") or len(argv) == 1 or
                                        argv[1].startswith("-"))
        if not wrapper or ppid <= 1:
            return {"pid": pid, "start": start, "argv": [a[:200] for a in argv[:8]], "via": via,
                    "interactive": agent_shell(base) or wrapper}
        pid = ppid
    return None


class Ident:
    """The headers of this process's acts (the program sha recomputed at most every `every_s` seconds)."""

    def __init__(self, via="client", pid=None, every_s=1.0, cache=None):
        self.via, self.pid, self.every_s, self.t, self.sha = via, pid, every_s, -1e9, None
        self.cache = {} if cache is None else cache
        self.proc = None

    def headers(self) -> dict:
        try:
            if time.monotonic() - self.t >= self.every_s:
                self.sha, self.t = program_sha(cache=self.cache), time.monotonic()
            if self.proc is None:
                self.proc = proc_ident(self.via, self.pid) or {}
                launch = settings()["program_launch"]   # started by `game program` (core 0.4.8): its launch row
                if launch and self.proc:
                    self.proc["program"], self.proc["launch"] = launch
            return {"X-RO-Program-Sha": self.sha[0], "X-RO-Program-Files": str(self.sha[1]),
                    "X-RO-Proc": json.dumps(self.proc, separators=(",", ":"))[:4000]}
        except Exception:  # noqa: BLE001  (a record only: never stop an act)
            return {}
# ---------------------------------------------------------------- end D3


# ---------------------------------------------------------------- programs: start, stop, replace (core 0.4.8)
# `game program start | restart | stop | status` (core/game.py) and the same calls here (ro_client.program_restart(...)).
# Replacing a program by hand went wrong (10-23, three matches): `pkill -f runner.py` also matches the agent's own shell
# (its command line holds the pattern) and killed the session. Here a program runs in a session and process group of
# its own (setsid: out of reach of a harness that stops its process groups when it exits, docs harness_exit_1022), its
# pid, process group and start time are kept in <program dir>/.ro_program/<name>.json, and a stop signals that process
# group only (TERM, then KILL after grace_s), never a group that holds the caller or one of its ancestors (the agent's
# shell). Each start appends a launch row to .ro_program/launches.jsonl {n, name, t, cmd, cwd, log, pid, start,
# program_sha, program_files, replaced}; the program's acts carry {"program": name, "launch": n} in X-RO-Proc, so the
# match's deploy rows (final.json `deploys`, core/deploys.py) name the launch. Several programs run side by side under
# different names (default "main").
PROGRAM_STATE_DIR = ".ro_program"
PROGRAM_NAME_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


def _state_dir() -> str:
    return os.path.join(settings()["program_dir"], PROGRAM_STATE_DIR)


def _check_name(name: str) -> str:
    if not name or len(name) > 40 or not set(name) <= PROGRAM_NAME_OK or name.startswith("."):
        raise ValueError(f"program name {name!r}: 1-40 characters of [A-Za-z0-9_.-], not starting with '.'")
    return name


def _stat(pid: int):
    """(state, ppid, pgid, sid, starttime) of a process, None if it is gone."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            rest = f.read().rpartition(")")[2].split()
        return rest[0], int(rest[1]), int(rest[2]), int(rest[3]), int(rest[19])
    except (OSError, ValueError, IndexError):
        return None


def _alive(pid: int, start: int | None = None) -> bool:
    st = _stat(pid)
    return st is not None and st[0] not in ("Z", "X") and (start is None or st[4] == start)


def _protected() -> set[int]:
    """This process and its ancestors (the agent's shell, the harness): never signalled."""
    out, pid = set(), os.getpid()
    for _ in range(64):
        out.add(pid)
        st = _stat(pid)
        if st is None or st[1] <= 0:
            break
        pid = st[1]
    return out


def _all_pids() -> list[int]:
    try:
        return [int(x) for x in os.listdir("/proc") if x.isdigit()]
    except OSError:
        return []


def _targets(pid: int, pgid: int | None) -> tuple[list[int], str]:
    """The processes a stop signals: the program's process group when no protected process is in it, else the
    program and its descendants (a program started without a session of its own shares the agent shell's group)."""
    prot, stats = _protected(), {}
    for p in _all_pids():
        st = _stat(p)
        if st is not None and st[0] not in ("Z", "X"):
            stats[p] = st
    if pgid is not None and pgid > 1:
        group = [p for p, st in stats.items() if st[2] == pgid]
        if group and not prot.intersection(group):
            return sorted(group), "process_group"
    tree, frontier = {pid}, [pid]
    while frontier:
        parent = frontier.pop()
        for p, st in stats.items():
            if st[1] == parent and p not in tree:
                tree.add(p)
                frontier.append(p)
    return sorted(p for p in tree if p not in prot and p in stats), "process_tree"


def _signal(pids, sig, group: int | None):
    if group is not None:
        try:
            os.killpg(group, sig)
            return
        except OSError:
            pass
    for p in pids:
        try:
            os.kill(p, sig)
        except OSError:
            pass


def _stop_pid(pid: int, start: int | None, grace_s: float) -> dict:
    import signal as sg  # noqa: PLC0415
    if pid in _protected():
        return {"pid": pid, "stopped": False, "error": "refused: that is this command or one of its parents "
                                                       "(your own shell)"}
    st = _stat(pid)
    if st is None or st[0] in ("Z", "X") or (start is not None and st[4] != start):
        return {"pid": pid, "stopped": True, "how": "not running"}
    pids, how = _targets(pid, st[2])
    if not pids:
        return {"pid": pid, "stopped": False, "error": "refused: nothing to stop outside your own shell"}
    group = st[2] if how == "process_group" else None
    starts = {p: (_stat(p) or (0, 0, 0, 0, None))[4] for p in pids}
    _signal(pids, sg.SIGTERM, group)
    end = time.monotonic() + max(0.0, grace_s)
    left = pids
    while time.monotonic() < end:
        left = [p for p in pids if _alive(p, starts[p])]
        if not left:
            break
        time.sleep(0.05)
    else:
        left = [p for p in pids if _alive(p, starts[p])]
    killed = bool(left)
    if left:
        _signal(left, sg.SIGKILL, group)
        end = time.monotonic() + 2.0
        while time.monotonic() < end and any(_alive(p, starts[p]) for p in left):
            time.sleep(0.05)
    still = [p for p in pids if _alive(p, starts[p])]
    return {"pid": pid, "stopped": not still, "how": how, "processes": len(pids),
            "signal": "KILL" if killed else "TERM", **({"still_running": still} if still else {})}


def _read_state(name: str) -> dict | None:
    try:
        with open(os.path.join(_state_dir(), f"{_check_name(name)}.json")) as f:
            got = json.load(f)
        return got if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def program_status(name: str = "main") -> dict:
    """The named program as the last start recorded it, and whether it still runs."""
    st = _read_state(name)
    if st is None:
        return {"name": name, "running": False, "note": "no program was started under this name"}
    return {**st, "running": _alive(int(st.get("pid") or 0), st.get("start"))}


def program_stop(name: str = "main", pid: int | None = None, grace_s: float = 5.0) -> dict:
    """Stop the named program (or the process `pid`, e.g. one started by hand): TERM to its process group, KILL after
    grace_s. Never signals the caller or its parents."""
    if pid is not None:
        return _stop_pid(int(pid), None, grace_s)
    st = _read_state(name)
    if st is None or not st.get("pid"):
        return {"name": name, "stopped": True, "how": "none started"}
    return {"name": name, **_stop_pid(int(st["pid"]), st.get("start"), grace_s)}


def program_start(cmd, name: str = "main", log: str | None = None, cwd: str | None = None,
                  check_s: float = 1.0) -> dict:
    """Start `cmd` (a shell command line, or an argv list) detached: a session of its own (setsid), stdin from
    /dev/null, stdout and stderr appended to `log` (default <program dir>/program.log for "main", else <name>.log).
    Refused if a program of that name still runs (program_restart replaces it). Returns the launch row, with
    `exited` and the log's tail if the program ended within check_s seconds."""
    _check_name(name)
    cur = program_status(name)
    if cur.get("running"):
        raise RuntimeError(f"program {name!r} is still running (pid {cur.get('pid')}): use restart, or stop it first")
    row = _launch(cmd, name, log, cwd)
    _append_launch(row)
    if check_s > 0:
        row.update(_early_exit(row, check_s))
    return row


def _launch(cmd, name, log, cwd) -> dict:
    import subprocess  # noqa: PLC0415
    d = _state_dir()
    os.makedirs(d, exist_ok=True)
    pdir = settings()["program_dir"]
    log = log or os.path.join(pdir, "program.log" if name == "main" else f"{name}.log")
    cwd = cwd or os.getcwd()
    n = 1
    try:
        with open(os.path.join(d, "launches.jsonl")) as f:
            n = 1 + sum(1 for _ in f)
    except OSError:
        pass
    env = _taskspec.process_environ()
    env["RO_PROGRAM_NAME"], env["RO_PROGRAM_LAUNCH"] = name, str(n)
    shell = isinstance(cmd, str)
    text = cmd if shell else " ".join(str(a) for a in cmd)
    with open(log, "ab") as out:
        out.write(f"\n=== program {name} launch {n} at {time.strftime('%Y-%m-%dT%H:%M:%S')}: {text}\n".encode())
        out.flush()
        child = subprocess.Popen(cmd, shell=shell, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                 stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    _CHILDREN.append(child)             # reaped by _early_exit / at exit (never a zombie of a long-lived caller)
    st = _stat(child.pid)
    try:
        sha, files = program_sha(root=pdir)
    except Exception:  # noqa: BLE001  (a record only)
        sha, files = None, None
    row = {"n": n, "name": name, "t": round(time.time(), 3), "cmd": text[:2000], "cwd": cwd, "log": log,
           "pid": child.pid, "pgid": st[2] if st else child.pid, "start": st[4] if st else None,
           "program_sha": sha, "program_files": files}
    tmp = os.path.join(d, f"{name}.json.tmp")
    with open(tmp, "w") as f:
        json.dump(row, f)
    os.replace(tmp, os.path.join(d, f"{name}.json"))
    return row


_CHILDREN: list = []


def program_restart(cmd, name: str = "main", log: str | None = None, cwd: str | None = None, grace_s: float = 5.0,
                    pid: int | None = None, check_s: float = 1.0) -> dict:
    """Replace the named program: stop it (and the process `pid` too, when given: a program started by hand), then
    start `cmd` as program_start does. The launch row's `replaced` says what was stopped."""
    replaced = [program_stop(name, grace_s=grace_s)]
    if pid is not None:
        replaced.append(program_stop(name, pid=pid, grace_s=grace_s))
    bad = [r for r in replaced if not r.get("stopped")]
    if bad:
        raise RuntimeError(f"could not stop the previous program: {bad}")
    row = _launch(cmd, _check_name(name), log, cwd)
    row["replaced"] = [r for r in replaced if r.get("how") not in ("none started", "not running")]
    _append_launch(row)
    if check_s > 0:
        row.update(_early_exit(row, check_s))
    return row


def _append_launch(row: dict):
    with open(os.path.join(_state_dir(), "launches.jsonl"), "a") as f:
        f.write(json.dumps({k: v for k, v in row.items() if k not in ("exited", "log_tail")}) + "\n")


def _early_exit(row: dict, check_s: float) -> dict:
    end = time.monotonic() + check_s
    while time.monotonic() < end:
        for c in _CHILDREN:
            c.poll()                    # our own child: reap it so that an ended program reads as ended
        if not _alive(row["pid"], row.get("start")):
            break
        time.sleep(0.05)
    if _alive(row["pid"], row.get("start")):
        return {}
    code = next((c.returncode for c in _CHILDREN if c.pid == row["pid"]), None)
    out = {"exited": code if code is not None else True}
    try:
        with open(row["log"], "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 1500))
            out["log_tail"] = f.read().decode(errors="replace")
    except OSError:
        pass
    return out
# ---------------------------------------------------------------- end programs


def new_request_id() -> str:
    """A request id for an act (core/acts.py: 1-64 characters of [A-Za-z0-9_-])."""
    return uuid.uuid4().hex


class _Pace:
    """core 0.5.4: the request pacing of one seat in this process, shared by every Seat of it (a program's control and
    camera threads each with their own Seat used to pace apart and together exceed the seat's rate). The service
    counts a seat's requests in the last second (core/http.py); so does this: a call waits only when `cap` calls were
    made in the last second (cap = 90 % of the seat's request_limits.rate_per_s from /spec, read once; 18 until
    known). Up to core 0.4.9 every call waited MIN_GAP_S (0.06 s) after the previous one of the same Seat, which held a
    real-time loop to about 16 calls per second and added up to 60 ms to each call."""
    _all: dict = {}
    _lock = threading.Lock()

    def __init__(self, gap):
        import collections  # noqa: PLC0415
        self.gap, self.lock, self.known = gap, threading.Lock(), False
        self.cap = max(1, int(0.9 / gap))
        self.sent = collections.deque()

    @classmethod
    def of(cls, base, seat, gap):
        with cls._lock:
            p = cls._all.get((base, seat))
            if p is None:
                p = cls._all[base, seat] = cls(gap)
            return p

    def set_rate(self, rate: float):
        self.gap = 1.0 / float(rate)
        self.cap = max(1, int(0.9 * float(rate)))

    def slot(self) -> float:
        """The time this call may go (now, unless `cap` calls went in the last second)."""
        with self.lock:
            now = time.monotonic()
            while self.sent and now - self.sent[0] >= 1.0:
                self.sent.popleft()
            t = now if len(self.sent) < self.cap else self.sent[len(self.sent) - self.cap] + 1.0
            self.sent.append(t)
            return t


class Seat:
    """One seat's calls. The service allows at least 20 requests per second and 4 open requests per seat (core 0.3.0:
    more for a seat with several robots or a short control step, /spec `request_limits`): the client paces its calls
    at the seat's own rate (core 0.5.4: /spec request_limits.rate_per_s, read at the first call, shared by every Seat of
    the seat in this process; MIN_GAP_S, under the floor of 20 per second, until then; up to core 0.4.9 always
    MIN_GAP_S, which held a real-time loop to about 16 calls per second) and retries a request the HTTP layer refused
    before reading it (a bare 429 or a reset connection), which never reached the match. A connection that drops before its reply (core 0.2.35:
    http.client.RemoteDisconnected, ConnectionResetError or BrokenPipeError raised while the reply is read, which
    urllib does not wrap) is retried the same way. An act carries a request_id (core 0.3.0), so it is sent again
    with the same id and takes effect at most once; `say` (NOT_REPEATED) may have reached the match and is never sent
    twice: it returns {"error", "http_status": -1}, and the loop goes on as after a refused call."""
    MIN_GAP_S = 0.06
    NOT_REPEATED = ("say",)
    MAX_SENDERS = 64                     # wait=False: at most this many sender threads per Seat

    def __init__(self, base: str, seat: str, timeout: float = 600, ident: "Ident | None" = None,
                 learn_limits: bool = True):
        self.base, self.seat, self.timeout, self.last = base.rstrip("/"), seat, timeout, 0.0
        self.learn_limits = learn_limits         # False: a one-call process (the `game` command) asks no /spec first
        self.ident = ident or Ident("client")    # D3: the act's program (headers; core/deploys.py)
        self._pace = _Pace.of(self.base, seat, self.MIN_GAP_S)    # the seat's pacing in this process (core 0.5.4)
        self._pool = None                        # wait=False: the sender threads (made at the first such act)
        self._limits = None                      # /spec request_limits (read once)

    def limits(self) -> dict:
        """/spec request_limits of this seat (read once; {} when the service does not say); sets the shared pacing."""
        if self._limits is None:
            lim = {}
            try:
                lim = self.call("spec").get("request_limits") or {}
            except (OSError, ValueError, RuntimeError):
                pass
            self._limits = lim if isinstance(lim, dict) else {}
            rate = self._limits.get("rate_per_s")
            if rate:
                self._pace.set_rate(float(rate))
            self._pace.known = True
        return self._limits

    def act(self, action, request_id: str | None = None, wait: bool = True):
        """One act (a dict) or a batch (a list of acts, each naming its entity). wait=True: the reply as call()
        returns it, once the act took effect. wait=False (core 0.4.5): a concurrent.futures.Future of that reply,
        returned at once (.request_id: the act's id); see the module text, Act timing."""
        body = {"acts": list(action)} if isinstance(action, list) else dict(action)
        body["request_id"] = request_id if request_id is not None else new_request_id()
        if wait:
            return self.call("act", body)
        fut = self.senders().submit(self.call, "act", body)
        fut.request_id = body["request_id"]
        return fut

    def senders(self):
        """The sender threads of wait=False acts (made once): as many as the seat may have open requests (/spec
        request_limits.open_requests, less one for the caller's own calls), and MIN_GAP_S lowered to the seat's
        request rate (1 / request_limits.rate_per_s) when that is faster."""
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
            lim = self.limits()
            n = max(1, min(self.MAX_SENDERS, int(lim.get("open_requests") or 5) - 1))
            self._pool = ThreadPoolExecutor(n, thread_name_prefix=f"ro-act-{self.seat}")
        return self._pool

    def close(self):
        """Wait for the wait=False acts still under way and stop the sender threads."""
        if self._pool is not None:
            self._pool.shutdown(wait=True)
            self._pool = None

    def session(self, deadline_s: float | None = None) -> dict:
        """POST /session until the match has opened (the start barrier t0, core/phases.py): the reply with "t0".
        Each call blocks at most 30 s on the service; a service without the endpoint (an older core: 404) or one
        that refuses it ends the loop with that reply. deadline_s (default RO_SESSION_WAIT_S, 900 s): give up."""
        end = time.monotonic() + float(deadline_s if deadline_s is not None else settings()["session_wait_s"])
        while True:
            out = self.call("session", {})
            if out.get("phase") != "init" or out.get("http_status") or time.monotonic() > end:
                return out

    def call(self, ep: str, body: dict | None = None, tries: int = 20) -> dict:
        if ep == "act" and isinstance(body, dict) and "request_id" not in body:
            body = {**body, "request_id": new_request_id()}      # resent with the same id after a dropped reply
        if ep != "spec" and self.learn_limits and not self._pace.known:   # the seat's own rate (core 0.5.4)
            self.limits()
        for i in range(tries):
            slot = self._pace.slot()         # each call takes the seat's next free slot (every Seat of it here)
            self.last = slot
            time.sleep(max(0.0, slot - time.monotonic()))
            req = urllib.request.Request(f"{self.base}/{self.seat}/{ep}",
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json",
                                                  **(self.ident.headers() if ep in ("act", "ready", "start", "resign")
                                                     else {})})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.code == 429 and not raw and i + 1 < tries:          # the HTTP layer's limit, not the match's
                    time.sleep(self.backoff(i))
                    continue
                try:
                    out = json.loads(raw)
                except ValueError:
                    out = {"error": str(e)}
                out["http_status"] = e.code
                return out
            except urllib.error.URLError as e:
                if isinstance(e.reason, (BrokenPipeError, ConnectionResetError, ConnectionRefusedError)) and \
                        i + 1 < tries:
                    time.sleep(self.backoff(i))
                    continue
                raise
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError) as e:
                if ep in self.NOT_REPEATED:     # it may have reached the match: report it, never send it twice
                    return {"error": f"the connection dropped before the reply ({type(e).__name__})",
                            "http_status": -1}
                if i + 1 < tries:
                    time.sleep(self.backoff(i))
                    continue
                raise
        raise RuntimeError("the match service kept refusing")

    def backoff(self, i: int) -> float:
        """The wait before retry i + 1 of a refused request (core 0.5.4: from one pacing gap, doubling, at most
        0.25 * (i + 1) s, the wait up to core 0.4.9; a real-time loop no longer loses 12 control steps to one 429)."""
        return min(0.25 * (i + 1), max(0.01, self._pace.gap) * (2 ** i))


def wait_for(base: str, seat: str, deadline_s: float = 300) -> dict:
    t = time.time()
    while time.time() - t < deadline_s:
        try:
            out = Seat(base, seat, 10).call("spec")
            if "error" not in out:
                return out
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("the match service did not answer")


def review_of(player, reply) -> tuple[str, str]:
    f = getattr(player, "review", None)
    return f(reply) if f else ("played as planned", "go on with the same plan")


REPLY_IMAGES = [0]                      # acts whose reply carried images of their result (core 0.2.8)


def open_session(c: Seat) -> dict:
    """The built-in loop's first call (core 0.3.0): open the seat's session, wait for the start barrier."""
    f = getattr(c, "session", None)
    if f is not None:
        return f()
    out = {}
    while True:                                  # a Seat-like object with call() only
        out = c.call("session", {}) or {}
        if out.get("phase") != "init" or out.get("http_status"):
            return out


def play_turn(c: Seat, player) -> dict:
    open_session(c)
    c.call("start", {})
    while True:
        st = c.call("wait", {"timeout_s": 60}).get("state") or {}
        if st.get("done"):
            return st
        if not st.get("your_turn"):
            continue
        if st.get("awaiting_review"):
            why, plan = review_of(player, st)
            c.call("ready", {"why": why, "plan": plan})
            continue
        view = c.call("observe", {})
        body = player.act({"state": view.get("state") or {}, "observation": view.get("observation") or {}})
        reply = c.call("act", body)
        REPLY_IMAGES[0] += bool((reply.get("observation") or {}).get("image_png_b64"))
        if (reply.get("state") or {}).get("done"):
            return reply["state"]
        if reply.get("http_status"):
            print("refused:", json.dumps(reply)[:300], file=sys.stderr)
            continue
        why, plan = review_of(player, reply)
        c.call("ready", {"why": why, "plan": plan})


def play_realtime(c: Seat, player, every_s: float = 0.05) -> dict:
    every_s = float(getattr(player, "every_s", every_s))   # the player's declared decision cadence (game seconds)
    open_session(c)
    c.call("start", {})
    while True:
        view = c.call("observe", {})
        now = view.get("now") or {}
        if now.get("done"):
            return now
        if now.get("world") == "frozen" and now.get("phase") == "review" and not now.get("ready", {}).get(c.seat):
            why, plan = review_of(player, now)
            c.call("ready", {"why": why, "plan": plan})
            c.call("wait", {"dt": every_s})      # D2: ready returns at once; a frozen wait returns when play resumes
            continue
        if now.get("world") == "running":
            v = {"state": now, "observation": view.get("observation") or {}}
            body = player.act(v)
            if body is not None:
                c.call("act", body)
            say = getattr(player, "message", None)
            text = say(v) if say is not None else None
            if text:
                c.call("say", {"text": text})
        c.call("wait", {"dt": every_s})


def session_main() -> int:
    """python3 -m ro_client --session: open this seat's session (SIM_URL, SEAT) and wait for the start barrier.
    Exit 0 once the match has opened, 1 otherwise (the adapter logs it and starts the harness all the same)."""
    cf = settings()
    base, seat = cf["sim_url"], cf["seat"]
    t = time.monotonic()
    try:
        wait_for(base, seat, cf["session_connect_s"])
        out = Seat(base, seat, timeout=120).session()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"session": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}), flush=True)
        return 1
    ok = out.get("t0") is not None
    print(json.dumps({"session": ok, "seat": seat, "waited_s": round(time.monotonic() - t, 1),
                      **{k: out.get(k) for k in ("t0", "source", "phase", "error", "http_status") if k in out}}),
          flush=True)
    return 0 if ok else 1


def main(argv):
    if argv[:1] == ["--session"]:
        sys.exit(session_main())
    mod, _, name = argv[0].partition(":")
    sys.path.insert(0, os.getcwd())
    factory = getattr(importlib.import_module(mod), name or "Reference")
    cf = settings()
    base, seat = cf["sim_url"], cf["seat"]
    spec = wait_for(base, seat)
    player = factory(spec, seat, cf["player_seed"])
    c = Seat(base, seat)
    proto = spec.get("protocol", "")
    lockstep = (spec.get("timing") or {}).get("clock") == "lockstep"   # EFE standard twin: observe, act, wait
    if callable(getattr(player, "play", None)) and not proto.startswith("eai-standard-turn") and not lockstep:
        open_session(c)                     # a player with its own realtime loop (e.g. a joint-level controller that
        c.call("start", {})                 # reads `status` every control step and observes the cameras apart)
        end = player.play(c)
    else:
        end = play_turn(c, player) if proto.startswith("eai-standard-turn") else play_realtime(c, player)
    print(json.dumps({"final_state": {k: end.get(k) for k in ("reason", "won", "winner", "scores") if k in end},
                      "replies_with_images": REPLY_IMAGES[0]}))


if __name__ == "__main__":
    main(sys.argv[1:])
