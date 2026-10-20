#!/usr/bin/env python3
"""CPU-only self-test of the eai-standard/2.2 shared layer's crash recovery (rcb_limited.Episode, run.sh, the client).

Runs toy_server.py under run.sh the way a task's `sim` sidecar runs, with a small supervisor in place of compose's
`restart: on-failure:6` (it restarts run.sh when it exits non-zero, keeping the record dir), and drives it with the
shipped client. Needs numpy + requests; no simulator, no GPU, no Docker. About 1-2 minutes.

    python3 scripts/eai_standard/selftest.py            # every case
    python3 scripts/eai_standard/selftest.py watchdog   # the cases whose name contains "watchdog"
"""
from __future__ import annotations
import contextlib, io, json, os, signal, socket, subprocess, sys, tempfile, threading, time, traceback

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rcb_client  # noqa: E402
import rcb_limited as L  # noqa: E402

ROOT = tempfile.mkdtemp(prefix="eai_standard_selftest_")
# A directory whose `python` is this interpreter (a wrapper, not a link: a virtual environment's interpreter finds its
# packages by where it is started from). Without it the selftest fails wherever the first `python` on PATH has no numpy.
PYBIN = os.path.join(ROOT, "bin"); os.makedirs(PYBIN)
with open(os.path.join(PYBIN, "python"), "w") as _f:
    _f.write(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
os.chmod(os.path.join(PYBIN, "python"), 0o755)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class Compose:
    """run.sh as a `sim` container with `restart: on-failure:N`: rerun it while it exits non-zero, at most N times."""

    def __init__(self, name: str, restarts: int = 6, **env):
        self.data = os.path.join(ROOT, name); os.makedirs(self.data)
        self.port = free_port(); self.max = restarts; self.restarts = 0; self.stopped = False; self.rc = None
        # run.sh starts `python`: the interpreter that runs this selftest (which has numpy), whatever PATH says first
        self.env = {**os.environ, "RCB_DATA": self.data, "RCB_SERVER": os.path.join(HERE, "toy_server.py"), "RCB_TOY_PORT": str(self.port),
                    "RCB_PORT": str(self.port),   # where a service that gave up answers (rcb_limited.refuse_forever)
                    "PATH": PYBIN + os.pathsep + os.environ.get("PATH", ""), **{k: str(v) for k, v in env.items()}}
        self.out = open(os.path.join(self.data, "container.log"), "ab")
        self.p = None; self._t = threading.Thread(target=self._loop, daemon=True); self._t.start()
        self.url = f"http://127.0.0.1:{self.port}"

    def _loop(self):
        while not self.stopped:
            self.p = subprocess.Popen(["sh", os.path.join(HERE, "run.sh")], env=self.env, stdout=self.out, stderr=self.out, start_new_session=True)
            rc = self.p.wait()
            if self.stopped or rc == 0 or self.restarts >= self.max:
                self.rc = rc; return
            self.restarts += 1

    def robot(self, timeout: float = 60) -> rcb_client.Robot:
        return rcb_client.Robot(base=self.url, timeout=timeout)

    def pid(self) -> int:
        for _ in range(300):
            try:
                return int(open(os.path.join(self.data, "server.pid")).read())
            except (OSError, ValueError):
                time.sleep(0.1)
        raise RuntimeError("no server.pid")

    def kill_service(self) -> None:
        """kill -9 of the service inside the container (the fix plan's acceptance test: kill the sidecar's service)."""
        os.kill(self.pid(), signal.SIGKILL)
        time.sleep(0.3)

    def events(self) -> list:
        return L.Episode(self.data, dim=3).events()

    def final(self) -> dict:
        return json.load(open(os.path.join(self.data, "final.json")))

    def end(self, timeout: float = 60, wait_key: str | None = None) -> int:
        """The collect hook's first half, as a task's hook runs it."""
        cmd = [sys.executable, os.path.join(HERE, "rcb_limited.py"), "end", self.data, "--timeout", str(timeout)] + (["--wait-key", wait_key] if wait_key else [])
        return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": HERE}).returncode

    def down(self) -> None:
        self.stopped = True
        if self.p and self.p.poll() is None:
            os.killpg(self.p.pid, signal.SIGKILL)
        self._t.join(10)


def chunk(n: int, x: float, dim: int = 3) -> np.ndarray:
    return np.tile(np.array([x, 0.0, 0.0][:dim], np.float32), (n, 1))


CASES = []


def case(fn):
    CASES.append(fn); return fn


def expect(cond, what):
    if not cond:
        raise AssertionError(what)


@case
def exact_resume_between_calls():
    c = Compose("exact_between")
    try:
        r = c.robot()
        expect(r.spec()["protocol"] == "eai-standard/2.2", "spec.protocol")
        expect("on_service_error" in r.spec() and r.spec().get("max_call_wall_s") == 900.0, "spec crash-recovery fields")
        for i, x in enumerate((0.2, 0.3, 0.4)):
            res = r.submit("joint_position", chunk(5, x), dt=0.05, video="none", note=f"c{i}")
            expect(res.meta.get("stopped") is None and res.meta["executed_rows"] == 5, "plain chunk")
        st0 = r.status()
        c.kill_service()
        st1 = r.wait_ready(60)
        expect((st1["calls"], st1["control_steps"], st1["resumes"], st1["last_note"]) == (st0["calls"], st0["control_steps"], 1, "c2"),
               f"resumed state {st1} vs {st0}")
        r.submit("joint_position", chunk(5, 0.45), dt=0.05, video="none", note="after")
        expect(c.end() == 2, "in-process verdict")
        fin = c.final()
        expect(fin.get("graded_by") == "live" and fin["finalized"] and fin["resumes"] == 1 and fin["resume_state_mismatch"] == 0, f"final {fin}")
        expect(fin["n_actions"] == st0["control_steps"] + 5 and fin["sim_startups"] == 2, f"trajectory complete {fin}")
        ev = c.events(); rs = [e for e in ev if e["ev"] == "resumed"]
        expect(len(rs) == 1 and rs[0]["exact"] is True and rs[0]["crashed_in_call"] is False, f"resumed event {rs}")
        # a restart after the verdict keeps the verdict
        c.kill_service(); time.sleep(3)
        fin2 = c.final()
        expect(fin2.get("graded_by") == "live" and not fin2.get("gave_up"), f"verdict kept {fin2}")
        expect(any(e["ev"] == "restart_refused" and e["reason"] == "restarted after finalize" for e in c.events()), "restart after finalize")
    finally:
        c.down()


@case
def crash_inside_a_call_loses_the_call():
    c = Compose("in_call", RCB_TOY_STEP_S=0.02)
    try:
        r = c.robot()
        r.submit("joint_position", chunk(4, 0.2), dt=0.05, video="none")
        before = r.status()
        err = {}
        t = threading.Thread(target=lambda: err.setdefault("e", _try(lambda: r.submit("joint_position", chunk(200, 0.6), dt=0.05, video="none"))))
        t.start(); time.sleep(1.0); c.kill_service(); t.join(30)
        expect(isinstance(err.get("e"), requests.exceptions.RequestException), f"the caller got a connection error, not a result: {err}")
        st = r.wait_ready(60)
        expect(st["control_steps"] == before["control_steps"] and st["calls"] == before["calls"], f"the call in flight is lost as a whole {st} {before}")
        rs = [e for e in c.events() if e["ev"] == "resumed"]
        expect(rs and rs[-1]["crashed_in_call"] is True and rs[-1]["exact"] is True, f"crashed_in_call {rs}")
        res = r.submit("joint_position", chunk(3, 0.25), dt=0.05, video="none")
        expect(res.meta["control_steps"] == before["control_steps"] + 3, "the episode continues")
    finally:
        c.down()


def _try(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return e


@case
def exact_class_mismatch_gives_up():
    c = Compose("exact_mismatch", RCB_TOY_PERTURB=1e-9)
    try:
        r = c.robot()
        r.submit("joint_position", chunk(6, 0.3), dt=0.05, video="none")
        c.kill_service(); time.sleep(3)
        expect(c.end(timeout=30) == 2, "the collect hook keeps the give-up verdict")
        fin = c.final()
        expect(fin["gave_up"] and fin["infra_error"] == 1 and fin["reason"].startswith("resume_failed: replayed state differs"), f"final {fin}")
        expect(fin["success"] is False and fin["finalized"] is True, "no verdict but failure")
        expect(fin["resumes"] == 1 and fin["resume_state_mismatch"] == 1 and fin["sim_startups"] == 2, f"give-up counters {fin}")
    finally:
        c.down()


@case
def approx_class_mismatch_continues():
    c = Compose("approx_small", RCB_TOY_RESUME="approx", RCB_TOY_PERTURB=1e-6)
    try:
        r = c.robot()
        r.submit("joint_position", chunk(6, 0.3), dt=0.05, video="none")
        c.kill_service()
        st = r.wait_ready(60)
        expect(st["resumes"] == 1 and not st["done"], f"continues {st}")
        rs = [e for e in c.events() if e["ev"] == "resumed"][-1]
        expect(rs["exact"] is False and 0 < rs["tcp_dev_m"] < 0.05, f"flagged {rs}")
        r.submit("joint_position", chunk(3, 0.35), dt=0.05, video="none")
        expect(c.end() == 2, "verdict")
        fin = c.final()
        expect(fin["resume_state_mismatch"] == 1 and 0 < fin["resume_max_tcp_dev_m"] < 0.05 and not fin.get("gave_up"), f"final {fin}")
    finally:
        c.down()


@case
def approx_class_gross_divergence_gives_up():
    c = Compose("approx_big", RCB_TOY_RESUME="approx", RCB_TOY_PERTURB=0.1)
    try:
        r = c.robot()
        r.submit("joint_position", chunk(20, 0.3), dt=0.05, video="none")
        c.kill_service(); time.sleep(3)
        expect(c.end(timeout=30) == 2, "give-up verdict kept")
        fin = c.final()
        expect(fin["gave_up"] and fin["infra_error"] == 1 and "TCP" in fin["reason"], f"final {fin}")
        expect(fin["resumes"] == 1 and fin["resume_state_mismatch"] == 1 and fin["resume_max_tcp_dev_m"] > 0.05, f"give-up counters {fin}")
    finally:
        c.down()


@case
def third_crash_ends_the_episode():
    c = Compose("third_crash")
    try:
        r = c.robot()
        for _ in range(3):                               # crashes between calls: infrastructure
            r.submit("joint_position", chunk(2, 0.3), dt=0.05, video="none")
            c.kill_service()
            if _try(lambda: r.wait_ready(20)) is None:
                break
        time.sleep(2)
        fin = c.final()
        expect(fin["reason"] == "sim_crashed" and fin["infra_error"] == 1 and fin["gave_up"], f"final {fin}")
        expect(fin["resumes"] == 2 and fin["sim_startups"] == 4, f"the give-up reports the earlier resumes {fin}")
        expect(c.end(timeout=30) == 2, "verdict kept")
    finally:
        c.down()
    c = Compose("third_crash_in_calls", RCB_TOY_STEP_S=0.02)
    try:
        r = c.robot()
        for _ in range(3):                               # every crash inside a call: the agent's
            t = threading.Thread(target=lambda: _try(lambda: r.submit("joint_position", chunk(300, 0.5), dt=0.05, video="none")))
            t.start(); time.sleep(0.8); c.kill_service(); t.join(30)
            if isinstance(_try(lambda: r.wait_ready(20)), Exception):
                break
        time.sleep(2)
        fin = c.final()
        expect(fin["reason"] == "sim_crashed_on_call" and "infra_error" not in fin and fin["gave_up"], f"final {fin}")
        expect(fin["resumes"] == 2 and fin["sim_startups"] == 4, f"the give-up reports the earlier resumes {fin}")
    finally:
        c.down()


@case
def give_up_reports_earlier_resumes():
    c = Compose("give_up_counts")
    try:
        r = c.robot()
        r.submit("joint_position", chunk(4, 0.3), dt=0.05, video="none")
        c.kill_service(); r.wait_ready(60)                # resume 1: exact
        r.submit("joint_position", chunk(4, 0.35), dt=0.05, video="none")
        with open(os.path.join(c.data, "journal.f64"), "r+b") as f:
            f.truncate(8 * 3 * 2)                         # the journal loses rows the log counts
        c.kill_service(); time.sleep(3)                   # resume 2 fails: journal shorter than the log
        fin = c.final()
        expect(fin["gave_up"] and fin["reason"] == "resume_failed: journal shorter than the log" and fin["infra_error"] == 1, f"final {fin}")
        expect(fin["resumes"] == 2 and fin["sim_startups"] == 3 and fin["resume_state_mismatch"] == 0, f"counters {fin}")
    finally:
        c.down()


@case
def a_give_up_is_answered_at_once():
    """A service that gave up answers 409 to every request and the client raises EpisodeOver at once. Before, nothing
    listened: Robot() and wait_ready() waited out their timeout (an hour by default) for a simulator that was gone."""
    c = Compose("refused_at_start", RCB_TOY_REFUSE="too_few_cpus")
    try:
        t = time.time()
        e = _try(lambda: c.robot(timeout=120))
        expect(isinstance(e, rcb_client.EpisodeOver) and "too_few_cpus" in str(e) and "infrastructure" in str(e), f"Robot() raises the refusal: {e!r}")
        expect(time.time() - t < 30, f"at once, not after its timeout ({time.time() - t:.0f} s)")
        fin = c.final()
        expect(fin["reason"] == "too_few_cpus" and fin["infra_error"] == 1 and fin["gave_up"] and fin["success"] is False, f"final {fin}")
        expect(c.restarts == 0 and c.p.poll() is None, "the container stays up for the collect hook, never restarted")
        expect(c.end(timeout=30) == 2, "the collect hook keeps the give-up verdict")
        expect(c.final() == fin, "and nothing a client sends changes it")
    finally:
        c.down()
    c = Compose("gave_up_after_crashes")
    try:
        r = c.robot()
        for _ in range(3):                               # the third crash ends the episode: sim_crashed
            r.submit("joint_position", chunk(2, 0.3), dt=0.05, video="none")
            c.kill_service()
            if isinstance(_try(lambda: r.wait_ready(60)), Exception):
                break
        t = time.time()
        for what, fn in (("wait_ready()", lambda: r.wait_ready(120)), ("status()", r.status), ("Robot()", lambda: c.robot(timeout=120)),
                         ("submit()", lambda: r.submit("joint_position", chunk(2, 0.3), dt=0.05, video="none")),
                         ("get_obs()", r.get_obs)):
            e = _try(fn)
            expect(isinstance(e, rcb_client.EpisodeOver) and "sim_crashed" in str(e), f"{what} raises EpisodeOver with the reason: {e!r}")
        expect(time.time() - t < 30, f"all at once ({time.time() - t:.0f} s)")
        e = _try(lambda: r.fk([0.0, 0.0, 0.0]))
        expect(isinstance(e, ValueError) and "409" in str(e), f"kinematics: an error, no hang: {e!r}")
        with socket.create_connection(("127.0.0.1", c.port), timeout=10) as k:   # a malformed request cannot stop the answer
            k.sendall(b"POST /submit HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n")
            k.settimeout(10)
            expect(b" 409 " in k.recv(4096), "409 whatever the request")
        fin = c.final()
        expect(fin["reason"] == "sim_crashed" and fin["infra_error"] == 1 and fin["gave_up"], f"final {fin}")
    finally:
        c.down()


@case
def startup_watchdog_and_backoff():
    c = Compose("watchdog", RCB_TOY_HANG_S=30, RCB_STARTUP_TIMEOUT_S=2)
    try:
        t0 = time.time(); r = c.robot(timeout=90); dt = time.time() - t0
        st = [json.loads(x) for x in open(os.path.join(c.data, "startups.jsonl"))]
        start = [e for e in c.events() if e["ev"] == "start"]
        expect(len(st) == 2 and len(start) == 1 and start[0]["ts"] - st[1]["ts"] >= 20, f"one hung start, then a back-off of 20 s: {st} {start}")
        log = open(os.path.join(c.data, "server.log")).read()
        expect("Timeout" in log and "service exited (1)" in log, "the watchdog dumped the traceback and exited 1")
        expect(r.status()["calls"] == 0 and dt < 90, "the second start serves a fresh episode")
        expect(not any(e["ev"] == "resumed" for e in c.events()), "a start that never began an episode is not a resume")
    finally:
        c.down()


@case
def client_disconnect_abandons_the_call():
    c = Compose("disconnect", RCB_TOY_STEP_S=0.05)
    try:
        r = c.robot()
        body = rcb_client.rcb1.encode({"type": "joint_position", "dt": 0.05, "video": "none"}, [rcb_client.rcb1.array_part("actions", chunk(400, 0.4))])
        e = _try(lambda: requests.post(c.url + "/submit", data=body, timeout=(5, 1.0)))
        expect(isinstance(e, requests.exceptions.ReadTimeout), "the client gave up")
        st = r.status()                                 # answers once the service noticed the hang-up
        expect(0 < st["control_steps"] < 100 and st["calls"] == 1 and not st["done"], f"stopped early, prefix kept: {st}")
        ends = [x for x in c.events() if x["ev"] == "call_end" and x.get("path") == "/submit"]
        cps = [x for x in c.events() if x["ev"] == "checkpoint"]
        expect(ends[-1].get("stopped") == "client_disconnected" and cps[-1]["control_steps"] == st["control_steps"], "journaled and checkpointed")
    finally:
        c.down()


@case
def max_call_wall_s_stops_a_long_call():
    c = Compose("wall_cap", RCB_TOY_STEP_S=0.05, RCB_MAX_CALL_WALL_S=1)
    try:
        r = c.robot()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            res = r.submit("joint_position", chunk(400, 0.4), dt=0.05, video="none")
        expect(res.meta["stopped"] == "max_call_wall_s" and 0 < res.meta["executed_rows"] < 400 and res.stopped == "max_call_wall_s", f"meta {res.meta}")
        expect("stopped this call early" in err.getvalue(), "the client warns")
        expect(r.status()["control_steps"] == res.meta["control_steps"], "status agrees")
    finally:
        c.down()


@case
def dump_mode_collect_hook():
    c = Compose("dump", RCB_TOY_MODE="dump")
    try:
        r = c.robot()
        r.submit("joint_position", chunk(5, 0.3), dt=0.05, video="none")
        c.kill_service(); r.wait_ready(60)
        expect(c.end() == 0, "dumped and exited: the hook merges the live verdict next")
        ep = json.load(open(os.path.join(c.data, "episode.json")))
        expect(ep["n_actions"] == 5 and ep["resumes"] == 1, f"episode.json {ep}")
        time.sleep(0.5)
        expect(c.p.poll() is None, "run.sh holds the container after a clean exit")
    finally:
        c.down()


@case
def usr1_during_resume_is_kept():
    c = Compose("usr1_resume", RCB_TOY_STEP_S=0.02)
    try:
        r = c.robot()
        r.submit("joint_position", chunk(150, 0.3), dt=0.05, video="none")   # 150 steps: a 3 s resume replay
        c.kill_service()
        f = os.path.join(c.data, "startups.jsonl")
        while sum(1 for _ in open(f)) < 2:
            time.sleep(0.05)
        time.sleep(0.5)                                  # the new process is replaying the journal now
        os.kill(json.loads(open(f).readlines()[-1])["pid"], signal.SIGUSR1)
        expect(not os.path.exists(os.path.join(c.data, "server.pid")), "no stale PID file while it resumes")
        rc = c.end(timeout=60)
        expect(rc == 2, f"verdict after the resume (rc {rc})")
        fin = c.final()
        expect(fin["n_actions"] == 150 and fin.get("graded_by") == "live" and fin["reason"] == "timeout", f"final {fin}")
    finally:
        c.down()


@case
def simulator_error_ends_the_episode():
    c = Compose("error")
    try:
        r = c.robot()
        x = requests.post(c.url + "/observe", json={"note": "raise"}, timeout=10)
        expect(x.status_code == 500, "500")
        st = r.status()
        expect(st["done"] and st["reason"] == "error", f"the episode ended: {st}")
        expect(requests.post(c.url + "/submit", data=b"", timeout=10).status_code == 409, "409 afterwards")
    finally:
        c.down()


@case
def malformed_requests_are_400_and_change_nothing():
    """PROTOCOL §4.6: a request the service cannot read is the caller's mistake (400): no physics, the episode goes on.
    Raw JSON bodies, as an agent without the shipped client may send them."""
    c = Compose("malformed")
    try:
        r = c.robot()
        r.submit("joint_position", chunk(3, 0.1), note="before")
        st0 = r.status()
        big = "[[" + "9" * 400 + ", 0, 0]]"                                   # an integer too large for a float
        bad = [
            ("/submit", {"type": "joint_position", "actions": {"a": 1}}),      # TypeError in numpy, not ValueError
            ("/submit", {"type": "joint_position", "actions": None}),
            ("/submit", {"type": "joint_position", "actions": "abc"}),
            ("/submit", {"type": "joint_position", "actions": [[0, 0, {"x": 1}]]}),
            ("/submit", {"type": "joint_position", "actions": [[0, 0], [0, 0, 0]]}),
            ("/submit", '{"type": "joint_position", "actions": ' + big + "}"),
            ("/submit", '{"type": "joint_position", "actions": [[NaN, 0, 0]]}'),
            ("/submit", '{"type": "joint_position", "actions": [[1e999, 0, 0]]}'),
            ("/submit", {"type": "joint_position", "actions": [[0, 0, 0]], "dt": [0.05]}),
            ("/submit", {"type": "joint_position", "actions": [[0, 0, 0]], "dt": "soon"}),
            ("/submit", '{"type": "joint_position", "actions": [[0, 0, 0]], "dt": Infinity}'),
            ("/submit", {"type": ["joint_position"], "actions": [[0, 0, 0]]}),
            ("/submit", {"type": "joint_position", "actions": [[0, 0, 0]], "cameras": 5}),
            ("/submit", {"type": "joint_position", "actions": [[0, 0, 0]], "video_fps": {"fps": 10}}),
            ("/submit", [1, 2, 3]),
            ("/observe", {"seconds": [1]}),
            ("/observe", {"seconds": {"s": 1}}),
            ("/observe", '{"seconds": NaN}'),
            ("/observe", {"cameras": "top", "seconds": 0, "video": 3}),
        ]
        for path, body in bad:
            data = body if isinstance(body, str) else json.dumps(body)
            x = requests.post(c.url + path, data=data, headers={"Content-Type": "application/json"}, timeout=10)
            expect(x.status_code == 400, f"400 for {path} {data[:60]} (got {x.status_code}: {x.text[:120]})")
            st = r.status()
            expect(not st["done"] and st["step"] == st0["step"] and st["control_steps"] == st0["control_steps"],
                   f"nothing ran and the episode goes on after {data[:60]}: {st}")
        expect(r.status()["calls"] == st0["calls"], "a refused request is not a call of the episode")
        res = r.submit("joint_position", chunk(2, 0.2), note="after")
        expect(res.meta["executed_rows"] == 2 and r.status()["step"] == st0["step"] + 2, "a good request still runs")
        expect(not [e for e in c.events() if e.get("ev") == "error"], "no simulator error was logged")
    finally:
        c.down()


@case
def busy_port_is_waited_for_not_a_crash():
    """Under Harbor's egress control the agent's container shares the sidecar's network namespace: a process of the
    agent may listen on the service's port while the scene is built. The service waits for the port; it does not exit
    (an exit is a crash, and three of them end the episode)."""
    with socket.socket() as held:
        held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        held.bind(("0.0.0.0", 0)); held.listen(1)
        port = held.getsockname()[1]
        c = Compose("busy_port", RCB_TOY_PORT=port)
        c.port, c.url = port, f"http://127.0.0.1:{port}"
        try:
            c.pid()                                              # the episode began (the PID file is the service's)
            time.sleep(3.0)
            expect(c.restarts == 0 and c.p.poll() is None, f"the service is still up while the port is taken (restarts {c.restarts})")
            expect("waiting for it to be free" in open(os.path.join(c.data, "server.log")).read(), "and says what it waits for")
            held.close()
            r = c.robot()
            res = r.submit("joint_position", chunk(2, 0.1))
            expect(res.meta["executed_rows"] == 2 and c.restarts == 0, "once the port is free the service serves, never restarted")
            expect(not [e for e in c.events() if e.get("ev") == "resuming"], "no crash, no resume")
        finally:
            c.down()


@case
def negative_content_length_is_refused_at_once():
    """A negative Content-Length must not make the service read until the client hangs up (an unbounded read)."""
    c = Compose("neg_content_length")
    try:
        r = c.robot()
        st0 = r.status()
        with socket.create_connection(("127.0.0.1", c.port), timeout=10) as k:
            k.sendall(b"POST /submit HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: -1\r\n\r\n")
            k.sendall(b"x" * 65536)                               # and keep the connection open: no EOF for the service
            k.settimeout(5)
            reply = k.recv(4096)
        expect(reply.startswith(b"HTTP/1.0 400") or reply.startswith(b"HTTP/1.1 400"), f"400 within 5 s, got {reply[:60]!r}")
        st = r.status()
        expect(not st["done"] and st["calls"] == st0["calls"], f"the episode goes on: {st}")
    finally:
        c.down()


@case
def a_repeated_camera_is_one_camera():
    """N copies of one camera name were rendered into one list N times and returned N times (N * N images), while the
    adapters' budgets counted N: a request of a few hundred bytes could exhaust the service's memory."""
    meta = {"cameras": ["top", "side", "top", "top"]}
    L.parse_request("/observe", meta, {})
    expect(meta["cameras"] == ["top", "side"], f"the adapter gets each name once, in the order asked for: {meta}")
    grabs = []

    def grab(cams, want):
        grabs.append(list(cams)); return {c: np.zeros((2, 2, 3), np.uint8) for c in cams}, {}
    rec = L.Recorder(["top"] * 40, 1, grab, lambda: np.zeros(1), lambda cams: {}, lambda: 0)
    rec.tick(force=True); rec.tick(force=True)
    shapes = [p[3]["shape"] for p in rec.parts("frames", 10) if p[0] == "frames/top"]
    expect(grabs == [["top"]] * 2 and shapes == [[2, 2, 2, 3]], f"the recorder too: grabs {grabs[:1]}, frames/top {shapes}")


@case
def client_accepts_both_names():
    for p, ok in (("eai-standard/2.2", True), ("eai-standard/2.1", True), ("rcb-limited/2.1", True), ("rcb-limited/1.0", False), ("x/2.2", False)):
        expect(p.startswith(rcb_client.ACCEPTED) == ok, p)


@case
def agent_clock_starts_at_the_first_request_and_survives_a_resume():
    """meta time_s / time_left_s (rcb_limited.agent_time): not started by the service's start or by a probe that only
    connects to the port, started by the agent's first request (any endpoint), and not set back by a resume."""
    c = Compose("agent_clock")
    try:
        c.pid()                                   # the service is ready (the PID file is written just before it serves)
        idle = 3.0; t_ready = time.time()
        while time.time() - t_ready < idle:       # what a healthcheck may do: connect to the port, send nothing
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", c.port), timeout=2):
                pass
            time.sleep(0.5)
        expect(not any(e["ev"] == "first_request" for e in c.events()), "a connect without a request started the clock")
        t_req = time.time()
        r = c.robot()                             # GET /spec: the agent's first request
        expect("first request" in r.spec()["budget"].get("clock", ""), f"spec.budget.clock {r.spec()['budget']}")
        m0 = r.get_obs(cameras=[]).meta; lag = time.time() - t_req
        expect(0.0 <= m0["time_s"] <= lag + 0.1, f"time_s {m0['time_s']} counts from the first request ({lag:.2f} s ago), "
                                                 f"not from the service's start ({time.time() - t_ready:.1f} s ago)")
        expect(m0["time_left_s"] >= 3600.0 - lag - 0.2, f"time_left_s {m0['time_left_s']} is short by the idle time")
        first = [e for e in c.events() if e["ev"] == "first_request"]
        expect(len(first) == 1 and abs(first[0]["t_first"] - t_req) <= lag + 0.1, f"first_request logged once: {first}")
        time.sleep(2.0)
        c.kill_service()
        st = r.wait_ready(60)
        expect(st["resumes"] == 1, f"resumed {st}")
        m1 = r.get_obs(cameras=[]).meta; since = time.time() - t_req
        expect(since - lag - 0.3 <= m1["time_s"] <= since + 0.1 and m1["time_s"] >= m0["time_s"] + 2.0,
               f"time_s after the resume {m1['time_s']} (first request {since:.2f} s ago): the clock was set back")
        expect(m1["time_left_s"] <= m0["time_left_s"] - 2.0, f"time_left_s went back up: {m0['time_left_s']} -> {m1['time_left_s']}")
        expect(len([e for e in c.events() if e["ev"] == "first_request"]) == 1, "a resume logged a second first_request")
    finally:
        c.down()


@case
def every_adapter_reports_the_agents_clock():
    """Each eai-standard/2.2 adapter (tasks/<benchmark>/<task>/environment/sim/server.py next to a copy of this layer) computes meta
    time_s and time_left_s from the agent's first request: from rcb_limited.agent_time (or the first-request time the
    layer keeps in E["t_first"]), never from the service's start or the episode's own t0."""
    import glob, hashlib, re
    tasks = os.path.join(os.path.dirname(os.path.dirname(HERE)), "tasks")
    # a copy of this layer: the same PROTOCOL line (not the same bytes: a layer change reaches the tasks through each
    # benchmark's own regeneration, and the adapters' clock does not depend on it)
    proto = next(x for x in open(os.path.join(HERE, "rcb_limited.py"), encoding="utf-8") if x.startswith("PROTOCOL ="))
    seen, bad = {}, []
    for f in sorted(glob.glob(os.path.join(tasks, "*", "*", "environment", "sim", "server.py"))):
        lay = os.path.join(os.path.dirname(f), "rcb_limited.py")
        if not os.path.isfile(lay) or proto not in open(lay, encoding="utf-8").read().splitlines(keepends=True):
            continue                               # another protocol's service
        src = open(f, encoding="utf-8").read(); h = hashlib.sha256(src.encode()).hexdigest()
        if h in seen:
            continue
        seen[h] = f
        for key in ("time_s", "time_left_s"):
            lines = [x for x in src.splitlines() if re.search(rf'"{key}":', x)]
            if not lines or not all(re.search(r"agent_time\(", x) for x in lines) or any('E["t0"]' in x or "T_FIRST" in x or "T_BOOT" in x for x in lines):
                bad.append(f"{os.path.relpath(f, tasks)}: {key} {[x.strip()[:120] for x in lines]}")
    expect(os.path.isdir(tasks) and len(seen) >= 10, f"found only {len(seen)} eai-standard/2.2 adapters under {tasks}")
    expect(not bad, "adapters whose clock does not start at the agent's first request:\n  " + "\n  ".join(bad))


def main() -> int:
    sel = sys.argv[1:]
    todo = [f for f in CASES if not sel or any(s in f.__name__ for s in sel)]
    bad = 0
    for f in todo:
        t = time.time()
        try:
            f(); print(f"ok   {f.__name__} ({time.time() - t:.1f} s)", flush=True)
        except Exception:  # noqa: BLE001
            bad += 1; print(f"FAIL {f.__name__} ({time.time() - t:.1f} s)", flush=True); traceback.print_exc()
    print(f"{len(todo) - bad}/{len(todo)} passed; records in {ROOT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
