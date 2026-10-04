"""Tests for the deduplicated raw log (rawlog.py): every request body and response comes back byte for byte.

    python -m unittest discover -s scripts/usage_gateway/tests     # stdlib only
"""
from __future__ import annotations

import gzip
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import rawlog  # noqa: E402

BIG = "x" * 2000


def rec(body: str, how: str = "text", resp: str = "event: done\ndata: {}\n\n") -> dict:
    return {"request": {"method": "POST", "host": "api.example.com", "path": "/v1/responses",
                        "headers": {"content-type": "application/json"}, "body": body, "body_as": how},
            "response": {"status": 200, "headers": {"content-type": "text/event-stream"}, "body": resp}}


def conversation() -> list[dict]:
    """An OpenAI Responses and an Anthropic Messages conversation, interleaved, each request resending the history."""
    out, inp, msgs = [], [], []
    for i in range(6):
        inp.append({"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"{BIG} {i}"}]})
        out.append(rec(json.dumps({"model": "gpt-x", "instructions": BIG, "input": inp, "stream": True},
                                  separators=(",", ":"), ensure_ascii=False)))
        # Claude Code moves cache_control to the newest message, so the previous last message changes every request
        msgs = [{k: v for k, v in m.items() if k != "cache_control"} for m in msgs]
        msgs.append({"role": "user", "content": f"é {BIG} {i}", "cache_control": {"type": "ephemeral"}})
        out.append(rec(json.dumps({"model": "claude-x", "system": [{"type": "text", "text": BIG}], "messages": msgs,
                                   "tools": [{"name": "bash", "description": BIG}], "max_tokens": 32000},
                                  separators=(",", ":"), ensure_ascii=False), resp=f"event: message\ndata: {i}\n\n"))
    return out


class RawLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, recs: list[dict]) -> rawlog.Writer:
        w = rawlog.Writer(self.d / rawlog.NAME)
        for r in recs:
            w.append(r)
        return w

    def check(self, recs: list[dict], path: pathlib.Path | None = None) -> None:
        got = list(rawlog.read(path or self.d / rawlog.NAME))
        self.assertEqual([g["n"] for g in got], list(range(1, len(recs) + 1)))
        for g, r in zip(got, recs, strict=True):
            self.assertEqual(g["request"], r["request"])
            self.assertEqual(g["response"], r["response"])

    def test_round_trip_and_dedup(self):
        recs = conversation()
        self.write(recs)
        self.check(recs)
        full = sum(len(json.dumps(r)) for r in recs)
        stored = len(gzip.decompress((self.d / rawlog.NAME).read_bytes()))
        self.assertLess(stored, full / 2)     # the history is stored once, not once per request

    def test_bodies_kept_as_text(self):
        recs = [rec('{"a": 1}'),                                    # spaced JSON: does not re-serialize exactly
                rec(json.dumps({"t": "é" + BIG}, separators=(",", ":"))),   # é escapes: ascii serialization
                rec('{"t":"\\ud800' + BIG + '"}'),                  # lone surrogate
                rec("not json"), rec("[1,2,3]"), rec("AAEC", how="base64"), rec("")]
        self.write(recs)
        self.check(recs)

    def test_resume_after_restart(self):
        recs = conversation()
        self.write(recs[:5])
        w = self.write(recs[5:])                 # a new gateway process picks up the item table and n
        self.assertEqual(w.n, len(recs))
        self.check(recs)

    def test_truncated_last_append(self):
        recs = conversation()
        self.write(recs)
        path = self.d / rawlog.NAME
        path.write_bytes(path.read_bytes()[:-20])
        got = list(rawlog.read(path))
        self.assertEqual(len(got), len(recs) - 1)

    def test_restart_after_crash_mid_write(self):
        recs = conversation()
        self.write(recs[:5])
        path = self.d / rawlog.NAME
        path.write_bytes(path.read_bytes()[:-20])     # the gateway died writing request 5
        w = self.write(recs[5:])                       # the restarted gateway cuts the partial member, then appends
        self.assertEqual(w.n, len(recs) - 1)
        got = list(rawlog.read(path))
        self.assertEqual([g["n"] for g in got], list(range(1, len(recs))))
        for g, r in zip(got, recs[:4] + recs[5:], strict=True):
            self.assertEqual(g["request"], r["request"])
            self.assertEqual(g["response"], r["response"])
        self.assertIn("->", rawlog.compact(self.d))
        self.assertEqual(len(list(rawlog.read(self.d / rawlog.PACKED))), len(recs) - 1)

    def test_damaged_member_stops_reading(self):
        recs = conversation()
        self.write(recs[:3])
        path = self.d / rawlog.NAME
        path.write_bytes(path.read_bytes() + gzip.compress(b"x" * 5000)[:-30] + gzip.compress(b'{"n": 99}\n'))
        self.assertEqual(len(list(rawlog.read(path))), 3)   # no exception; nothing behind the broken member

    def test_compact(self):
        recs = conversation()
        self.write(recs)
        self.assertIn("->", rawlog.compact(self.d))
        self.assertFalse((self.d / rawlog.NAME).exists())
        self.check(recs, self.d / rawlog.PACKED)

    def test_pack_legacy_cli(self):
        recs = conversation()
        (self.d / "raw").mkdir()
        for i, r in enumerate(recs, 1):
            (self.d / "raw" / f"{i:06d}.json.gz").write_bytes(gzip.compress(json.dumps(r).encode()))
        tool = [sys.executable, str(HERE / "rawlog.py")]
        out = subprocess.run(tool + ["pack", str(self.d)], capture_output=True, text=True, check=True).stdout
        self.assertIn(f"{len(recs)} requests", out)
        out = subprocess.run(tool + ["verify", str(self.d)], capture_output=True, text=True, check=True).stdout
        self.assertIn("identical to raw/", out)
        subprocess.run(tool + ["pack", "--delete", str(self.d)], check=True, capture_output=True)  # verifies, removes
        self.assertFalse((self.d / "raw").exists())
        last = json.loads(subprocess.run(tool + ["cat", str(self.d), "-n", str(len(recs))], capture_output=True,
                                         text=True, check=True).stdout)
        self.assertEqual(last["request"], recs[-1]["request"])


if __name__ == "__main__":
    unittest.main()
