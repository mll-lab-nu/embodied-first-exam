"""Tests for the gateway's one resend of an HTTP 400 (gateway.py module doc "One resend", RETRY_400): a zstd body goes
again uncompressed (the exact JSON), anything else (and a zstd body that does not decode) as it was sent.

    python3 scripts/usage_gateway/tests/test_retry_400.py     # stdlib only; starts gateway.py on loopback (the zstd
                                                              # cases need the zstandard module or the zstd program)
"""
from __future__ import annotations

import http.client
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402

def raw_zstd(data: bytes) -> bytes:
    """A zstd frame of raw (stored) blocks of at most 128 KiB, the block limit Codex's bodies cross: any decoder reads it
    (the zstandard module or the zstd program), and no compressor is needed to make it."""
    out = bytearray(b"\x28\xb5\x2f\xfd\x00\x38")           # magic; no checksum, no content size; window 128 KiB
    blocks = [data[i:i + (128 << 10)] for i in range(0, len(data), 128 << 10)] or [b""]
    for i, b in enumerate(blocks):
        out += (int(i == len(blocks) - 1) | len(b) << 3).to_bytes(3, "little") + b   # last flag, type 0 = raw, size
    return bytes(out)


HAVE_ZSTD = gateway.decode_request(raw_zstd(b"{}"), "zstd") == ("{}", "text")
# a JSON body just over one 128 KiB block, as the requests the backend answers 400
BIG = json.dumps({"model": "m", "input": [{"role": "user", "content": "x" * ((128 << 10) + 600)}], "x": 1.846597},
                 separators=(",", ":")).encode()

OK = json.dumps({"type": "response.completed", "response": {"model": "stub", "usage": {"input_tokens": 3,
                 "output_tokens": 2}}}).encode()


class Flaky(BaseHTTPRequestHandler):
    """Answers the n-th request (counted per path) by the plan for that path: "400" ({"detail": "Bad Request"}),
    "400b" (another 400 body), "drop" (closes the connection without an answer) or "200"."""
    plan: dict[str, list[str]] = {}
    seen: list[tuple[str, bytes, dict]] = []
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        hdrs = {k.lower(): v for k, v in self.headers.items() if k.lower() not in ("connection",)}
        Flaky.seen.append((self.path, body, hdrs))
        n = sum(1 for p, _, _ in Flaky.seen if p == self.path) - 1
        steps = Flaky.plan.get(self.path, ["200"])
        what = steps[min(n, len(steps) - 1)]
        if what == "drop":
            self.close_connection = True
            return
        out = {"400": b'{"detail":"Bad Request"}', "400b": b'{"detail":"Bad Request","n":2}'}.get(what, OK)
        self.send_response(400 if what.startswith("400") else 200)
        self.send_header("Content-Type", "application/json"); self.send_header("X-Upstream-Try", str(n + 1))
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


class Resend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = ThreadingHTTPServer(("127.0.0.1", 0), Flaky)
        threading.Thread(target=cls.stub.serve_forever, daemon=True).start()
        cls.up = f"127.0.0.1:{cls.stub.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.stub.shutdown(); cls.stub.server_close()

    def gateway(self, *extra):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        jobs = pathlib.Path(td.name)
        ready = jobs / "ready"
        proc = subprocess.Popen([sys.executable, str(HERE / "gateway.py"), "--jobs", str(jobs), "--bind", "127.0.0.1",
                                 "--ready-file", str(ready), "--http-host", self.up, *extra],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(lambda: (proc.terminate(), proc.wait(10), proc.stderr.close()))
        for _ in range(100):
            if ready.exists() and ready.read_text():
                break
            if proc.poll() is not None:
                raise RuntimeError(proc.stderr.read().decode()[-2000:])
            time.sleep(0.1)
        return jobs, int(ready.read_text())

    @staticmethod
    def call(port, path, body=b'{"model": "m", "input": [{"role": "user", "content": "hi"}], "x": 1.846597}', encoding=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("POST", path, body=body, headers={"Content-Type": "application/json", "Authorization": "Bearer K",
                                                    "Session-Id": "s-1", **({"Content-Encoding": encoding} if encoding else {})})
        r = c.getresponse(); out = r.read(); hdr = r.getheader("X-Upstream-Try"); c.close()
        return r.status, out, hdr

    @staticmethod
    def records(jobs, n=2):
        """The gateway's records, once there are n (it writes a request's record after the answer has gone out)."""
        f = jobs / ".gateway" / "unattributed.jsonl"
        for _ in range(100):
            recs = [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []
            if len(recs) >= n:
                break
            time.sleep(0.05)
        return recs

    def setUp(self):
        Flaky.seen.clear(); Flaky.plan.clear()

    def test_a_400_goes_once_more_unchanged_and_the_second_answer_reaches_the_agent(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses")
        Flaky.plan["/v1/responses"] = ["400", "200"]
        st, out, tr = self.call(port, f"/h/{self.up}/v1/responses")
        self.assertEqual((st, tr), (200, "2"))
        self.assertEqual(json.loads(out)["type"], "response.completed")
        self.assertEqual(len(Flaky.seen), 2)
        self.assertEqual(Flaky.seen[0][1], Flaky.seen[1][1])         # the same bytes
        self.assertEqual(Flaky.seen[0][2], Flaky.seen[1][2])         # the same headers
        recs = self.records(jobs)
        self.assertEqual([(r["status"], r.get("retried"), r.get("attempt")) for r in recs], [(400, True, 1), (200, None, 2)])
        self.assertEqual(recs[1]["retry_of_status"], 400)
        self.assertEqual([r["retry_mode"] for r in recs], ["identical", "identical"])   # not compressed: as it was
        self.assertNotIn("decompressed_bytes", recs[1])
        self.assertEqual(recs[0]["response_bytes"], 24)
        self.assertEqual(recs[1]["usage"], {"input": 3, "cached": 0, "output": 2})
        self.assertLessEqual(recs[0]["ts"], recs[1]["ts"])

    @unittest.skipUnless(HAVE_ZSTD, "no zstd decoder here (the zstandard module or the zstd program)")
    def test_a_zstd_body_goes_again_uncompressed_with_the_exact_json(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses", "--raw")
        Flaky.plan["/v1/responses"] = ["400", "200"]
        z = raw_zstd(BIG)
        st, out, tr = self.call(port, f"/h/{self.up}/v1/responses", body=z, encoding="zstd")
        self.assertEqual((st, tr), (200, "2"))
        (_, b1, h1), (_, b2, h2) = Flaky.seen
        self.assertEqual((b1, h1["content-encoding"], h1["content-length"]), (z, "zstd", str(len(z))))   # as Codex sent it
        self.assertEqual(b2, BIG)                                                  # the JSON, byte for byte
        self.assertNotIn("content-encoding", h2)
        self.assertEqual(h2["content-length"], str(len(BIG)))
        drop = ("content-encoding", "content-length")
        self.assertEqual({k: v for k, v in h1.items() if k not in drop}, {k: v for k, v in h2.items() if k not in drop})
        recs = self.records(jobs)
        self.assertEqual([(r["status"], r.get("attempt"), r["retry_mode"]) for r in recs],
                         [(400, 1, "uncompressed"), (200, 2, "uncompressed")])
        self.assertEqual((recs[0]["request_bytes"], recs[1]["request_bytes"], recs[1]["decompressed_bytes"]),
                         (len(z), len(BIG), len(BIG)))
        self.assertEqual(Flaky.seen[1][2]["authorization"], "Bearer K")           # the agent's own credentials, passed on

    @unittest.skipUnless(HAVE_ZSTD, "no zstd decoder here (the zstandard module or the zstd program)")
    def test_an_uncompressed_resend_that_gets_400_again_is_passed_on(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses")
        Flaky.plan["/v1/responses"] = ["400", "400b", "200"]
        st, out, _ = self.call(port, f"/h/{self.up}/v1/responses", body=raw_zstd(BIG), encoding="zstd")
        self.assertEqual((st, out, len(Flaky.seen)), (400, b'{"detail":"Bad Request","n":2}', 2))
        self.assertEqual([(r["status"], r["retry_mode"]) for r in self.records(jobs)], [(400, "uncompressed")] * 2)

    def test_a_zstd_body_that_does_not_decode_goes_again_as_it_was(self):
        # forwarded unread (--server-tools record lets an unreadable body through): the resend is the identical bytes
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses", "--server-tools", "record")
        Flaky.plan["/v1/responses"] = ["400", "200"]
        bad = b"\x28\xb5\x2f\xfd" + b"\xff" * 40
        self.assertEqual(self.call(port, f"/h/{self.up}/v1/responses", body=bad, encoding="zstd")[0], 200)
        (_, b1, h1), (_, b2, h2) = Flaky.seen
        self.assertEqual((b1, b2), (bad, bad))
        self.assertEqual(h1, h2)
        self.assertEqual(h2["content-encoding"], "zstd")
        self.assertEqual([r["retry_mode"] for r in self.records(jobs)], ["identical", "identical"])

    def test_a_second_400_is_passed_on_unchanged_and_there_is_no_third_try(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses")
        Flaky.plan["/v1/responses"] = ["400", "400b", "200"]
        st, out, tr = self.call(port, f"/h/{self.up}/v1/responses")
        self.assertEqual((st, out, tr), (400, b'{"detail":"Bad Request","n":2}', "2"))
        self.assertEqual(len(Flaky.seen), 2)
        recs = self.records(jobs)
        self.assertEqual([(r["status"], r.get("attempt")) for r in recs], [(400, 1), (400, 2)])
        self.assertNotIn("retried", recs[1])

    def test_a_resend_that_gets_no_answer_passes_the_first_400_on(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses")
        Flaky.plan["/v1/responses"] = ["400", "drop"]
        st, out, tr = self.call(port, f"/h/{self.up}/v1/responses")
        self.assertEqual((st, out, tr), (400, b'{"detail":"Bad Request"}', "1"))
        recs = self.records(jobs)
        self.assertEqual([(r["status"], r.get("attempt")) for r in recs], [(400, 1), (502, 2)])
        self.assertIs(recs[1]["forwarded"], False)
        self.assertEqual(recs[1]["passed_on"], "attempt 1")

    def test_other_paths_and_statuses_are_not_resent(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses")
        Flaky.plan["/v1/messages"] = ["400", "200"]
        self.assertEqual(self.call(port, f"/h/{self.up}/v1/messages")[0], 400)        # not listed
        self.assertEqual(len(Flaky.seen), 1)
        self.assertEqual(self.call(port, f"/h/{self.up}/v1/responses")[0], 200)      # a 200 goes once
        self.assertEqual(len(Flaky.seen), 2)
        self.assertEqual([r.get("attempt") for r in self.records(jobs)], [None, None])

    def test_no_retry_400(self):
        jobs, port = self.gateway("--retry-400", f"{self.up}/v1/responses", "--no-retry-400")
        Flaky.plan["/v1/responses"] = ["400", "200"]
        self.assertEqual(self.call(port, f"/h/{self.up}/v1/responses")[0], 400)
        self.assertEqual(len(Flaky.seen), 1)

    def test_the_default_is_codex_responses_at_chatgpt_only(self):
        self.assertEqual(gateway.RETRY_400, {("chatgpt.com", "/backend-api/codex/responses")})


class ResendBody(unittest.TestCase):
    HDRS = {"Content-Type": "application/json", "Content-Encoding": "zstd", "Session-Id": "s", "Host": "h",
            "Content-Length": "9"}

    def test_decoded_zstd_goes_uncompressed(self):
        if not HAVE_ZSTD:
            self.skipTest("no zstd decoder here")
        z = raw_zstd(BIG)
        b, h, mode = gateway.resend_body(z, ["zstd"], BIG.decode(), dict(self.HDRS, **{"Content-Length": str(len(z))}))
        self.assertEqual((b, mode), (BIG, "uncompressed"))
        self.assertEqual(h, {"Content-Type": "application/json", "Session-Id": "s", "Host": "h",
                             "Content-Length": str(len(BIG))})

    def test_a_decoder_failure_at_resend_falls_back_to_identical(self):
        saved = gateway._unzstd
        gateway._unzstd = lambda body: (_ for _ in ()).throw(ValueError("zstd"))
        try:
            z = raw_zstd(b"{}")
            self.assertEqual(gateway.resend_body(z, ["zstd"], "{}", dict(self.HDRS)), (z, self.HDRS, "identical"))
        finally:
            gateway._unzstd = saved

    def test_not_zstd_or_not_decoded_goes_identical(self):
        for enc, text in (([], "{}"), (["gzip"], "{}"), (["zstd"], None)):
            self.assertEqual(gateway.resend_body(b"B", enc, text, dict(self.HDRS)), (b"B", self.HDRS, "identical"))


class Tally(unittest.TestCase):
    def test_retried_400_is_counted(self):
        saved = getattr(gateway, "ARGS", None)
        gateway.ARGS = types.SimpleNamespace(budget_input=0, budget_output=0)
        try:
            tot = {"requests": 0, "input": 0, "cached": 0, "output": 0, "no_usage": 0}
            gateway.tally(tot, {"ts": 1, "status": 400, "usage": {}, "retried": True, "attempt": 1})
            gateway.tally(tot, {"ts": 2, "status": 200, "usage": {"input": 5, "cached": 0, "output": 1}, "attempt": 2})
            self.assertEqual((tot["requests"], tot["retried_400"], tot["input"], tot["failures_in_a_row"]), (2, 1, 5, 0))
            self.assertNotIn("retried_400_uncompressed", tot)
            gateway.tally(tot, {"ts": 3, "status": 400, "usage": {}, "retried": True, "attempt": 1, "retry_mode": "uncompressed"})
            self.assertEqual((tot["retried_400"], tot["retried_400_uncompressed"]), (2, 1))
        finally:
            gateway.ARGS = saved


if __name__ == "__main__":
    unittest.main()
