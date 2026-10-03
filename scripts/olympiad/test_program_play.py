"""Offline checks of a program-play task's sim code: the act rule (think_clock.py) and the Azure failover (think_proxy.py).

    python3 scripts/olympiad/test_program_play.py tasks/<task>

1. act rule: with a fake meter file, RCB_ACT_RULE=program accepts every act, per_response refuses without a new
   response, and a missing meter raises MeterError.
2. failover: the task's think_proxy.py runs against a fake Azure upstream whose first deployment fails inside the
   stream (rate_limit_exceeded), the second answers 429 and the third succeeds. Expected: both requests end on the
   third, 2 recorded switches, 0 failed calls, 0 rate-limit retries; the second request goes straight to the third.
3. API errors (api_errors.py, the model-API validity rule): a recovered stream error is transient (valid), 6
   transient errors fail the trial (> MAX_TRANSIENT_API_ERRORS), trailing 429s are unrecovered (invalid); the
   incremental reader waits for a whole line; the failover log of check 2 has no errors; the task's copy is identical
   to scripts/olympiad/api_errors.py.
Exit status 0 when every check passes. Needs only the standard library and curl-free HTTP (urllib).
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def check_clock(sim):
    sys.path.insert(0, sim)
    os.environ["RCB_PLAYER_MODE"] = "model"
    os.environ["WALLCLOCK_RULE_WAIT_S"] = "0.05"
    import think_clock
    f = tempfile.mktemp()
    json.dump({"epoch": "e1", "model_calls_completed": 3, "act_calls_completed": 0, "requests": 3, "in_flight": 0}, open(f, "w"))
    ok = True
    for rule, expect in (("program", [True] * 3), ("per_response", [False] * 3)):
        os.environ["RCB_ACT_RULE"] = rule
        c = think_clock.ThinkClock(usage_file=f)
        c.rebase()
        got = [c.decided_by_model() for _ in range(3)]
        print(f"  act rule {rule}: {got}", "OK" if got == expect else "FAIL"); ok &= got == expect
    os.environ["RCB_ACT_RULE"] = "program"
    try:
        think_clock.ThinkClock(usage_file=tempfile.mktemp()).decided_by_model()
        print("  missing meter: accepted FAIL"); ok = False
    except think_clock.MeterError:
        print("  missing meter: refused OK")
    return ok


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hits = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        m = body["model"]; Upstream.hits.append(m)
        if m == "dep-b":
            self.send_response(429); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}"); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Connection", "close"); self.end_headers()

        def ev(d):
            self.wfile.write(b"event: " + d["type"].encode() + b"\ndata: " + json.dumps(d).encode() + b"\n\n")
        ev({"type": "response.created", "response": {"id": "r1"}})
        if m == "dep-a":
            ev({"type": "response.failed", "response": {"id": "r1", "status": "failed",
                                                         "error": {"code": "rate_limit_exceeded", "message": "Rate limit"}}})
            return
        ev({"type": "response.output_text.delta", "delta": "hi"})
        ev({"type": "response.completed", "response": {"id": "r1", "status": "completed", "output": [],
                                                       "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}})


def check_api_errors(sim, calls_file=None):
    sys.path.insert(0, sim)
    import api_errors as ae
    t = [0.0]

    def call(status=200, completed=True, stream_error=False, model_call=True, **kw):
        t[0] += 10
        return dict(t0=t[0] - 5, t1=t[0], status=status, completed=completed, stream_error=stream_error,
                    model_call=model_call, **kw)
    ok_ = call
    recovered = [ok_(), ok_(), call(200, False, True), ok_(), ok_()]
    six = [ok_()] + [x for _ in range(6) for x in (call(502, False, True), ok_())]
    five = [ok_()] + [x for _ in range(5) for x in (call(502, False, True), ok_())]
    trailing = [ok_(), ok_(), call(429, False, True), call(429, False, True), call(429, False, True)]
    retried = [ok_(retries=[{"status": 429, "at": t[0] - 7, "wait_s": 1}])]
    not_model = [ok_(), call(404, False, True, model_call=False)]
    cases = {
        "recovered stream error -> transient, valid": (recovered, None, (1, 0, False)),
        "5 transient -> valid": (five, None, (5, 0, False)),
        "6 transient -> invalid": (six, None, (6, 0, True)),
        "trailing 429s -> unrecovered, invalid": (trailing, None, (0, 3, True)),
        "429 retried inside the proxy, call completed -> transient": (retried, None, (1, 0, False)),
        "non-model request failing -> no error": (not_model, None, (0, 0, False)),
        "usage counts a failure not in the log -> unrecovered": (recovered, {"failed_model_calls": 2}, (1, 1, True)),
    }
    good = True
    for name, (recs, usage, want) in cases.items():
        r = ae.classify_calls(recs, usage)
        got = (r["transient_api_errors"], r["unrecovered_api_errors"], r["api_failure"])
        print(f"  api errors: {name}: {got}", "OK" if got == want else f"FAIL (want {want})"); good &= got == want
    # incremental reading as the services do it (a line still being written is not read yet)
    tmp = tempfile.mkdtemp()
    usage_file = os.path.join(tmp, "think_usage_A.json")
    path = ae.calls_file_for(usage_file)
    with open(path, "w") as f:
        f.write("".join(json.dumps(r) + "\n" for r in trailing[:3]) + json.dumps(ok_())[:20])
    first = ae.seat_api_errors(usage_file)
    with open(path, "a") as f:
        f.write(json.dumps(ok_())[20:] + "\n")
    second = ae.seat_api_errors(usage_file)
    inc = (path.endswith("think_calls_A.jsonl") and (first["unrecovered_api_errors"], first["api_failure"]) == (1, True)
           and (second["transient_api_errors"], second["api_failure"]) == (1, False))
    print("  api errors: incremental reader (partial line, then recovery):", "OK" if inc else f"FAIL {first} {second}")
    good &= inc
    if calls_file:
        r = ae.classify_file(calls_file)
        clean = (r["transient_api_errors"], r["unrecovered_api_errors"], r["api_failure"]) == (0, 0, False)
        print("  api errors: Azure failover log has no errors:", "OK" if clean else f"FAIL {r}"); good &= clean
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_errors.py")
    same = open(here, "rb").read() == open(os.path.join(sim, "api_errors.py"), "rb").read()
    print("  api errors: task copy identical to scripts/olympiad/api_errors.py:", "OK" if same else "FAIL"); good &= same
    return good


def check_failover(sim):
    up, px = free_port(), free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", up), Upstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, THINK_OPENAI_ROUTE="azure", AZURE_AI_ENDPOINT=f"http://127.0.0.1:{up}", AZURE_AI_API_KEY="dummy",
               AZURE_DEPLOYMENTS="dep-a,dep-b,dep-c", THINK_USAGE_FILE=f"{tmp}/usage.json", THINK_CALLS_FILE=f"{tmp}/calls.jsonl")
    proc = subprocess.Popen([sys.executable, os.path.join(sim, "think_proxy.py"), str(px)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{px}/think/usage", timeout=1); break
            except Exception:  # noqa: BLE001
                time.sleep(.1)
        texts = []
        for _ in range(2):
            req = urllib.request.Request(f"http://127.0.0.1:{px}/v1/responses", method="POST",
                                         data=json.dumps({"model": "openai/dep-a", "stream": True, "input": "hi"}).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
            texts.append(urllib.request.urlopen(req, timeout=30).read().decode())
    finally:
        proc.terminate(); proc.wait(); srv.shutdown()
    u = json.load(open(f"{tmp}/usage.json"))
    calls = [json.loads(l) for l in open(f"{tmp}/calls.jsonl")]
    checks = {
        "agent saw only completed streams": all("response.completed" in t and "rate_limit" not in t for t in texts),
        "upstream order a, b, c, c": Upstream.hits == ["dep-a", "dep-b", "dep-c", "dep-c"],
        "2 switches recorded": u.get("azure_failovers") == 2,
        "0 failed calls, 0 rate-limit retries": u.get("failed_model_calls") == 0 and u.get("rate_limit_retries") == 0,
        "both calls completed on dep-c": [c.get("azure_deployment") for c in calls] == ["dep-c", "dep-c"] and all(c.get("completed") for c in calls),
    }
    for k, v in checks.items():
        print(f"  failover: {k}:", "OK" if v else "FAIL")
    api_ok = check_api_errors(sim, f"{tmp}/calls.jsonl")
    return all(checks.values()) and api_ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sim = os.path.abspath(os.path.join(sys.argv[1], "environment", "sim"))
    ok = check_clock(sim)
    ok &= check_failover(sim)       # then check_api_errors on the failover's own call log
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)
