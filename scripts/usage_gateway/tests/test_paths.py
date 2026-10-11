"""Tests for the gateway's model-API path filter (gateway.py, api_paths.json): default deny, per provider.

    python3 scripts/usage_gateway/tests/test_paths.py     # stdlib only; the end-to-end part starts gateway.py on loopback
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
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402

gateway.PROVIDERS[:] = gateway.load_paths()


def ok(host: str, method: str, path: str, plain: bool = False) -> bool:
    return gateway.path_allowed(gateway.provider_of(host, plain), method, path)


class Rules(unittest.TestCase):
    def test_model_calls_of_recorded_runs(self):
        """Every (host, method, path) the gateway recorded in official runs up to 2026-10-10."""
        for host, method, path in [
                ("chatgpt.com", "POST", "/backend-api/codex/responses"),
                ("chatgpt.com", "GET", "/backend-api/codex/models?client_version=0.160.1"),
                ("api.openai.com", "POST", "/v1/responses"),
                ("res-1.cognitiveservices.azure.com", "POST", "/openai/v1/responses"),
                ("res-1.openai.azure.com", "POST", "/openai/v1/responses?api-version=preview"),
                ("res-1.services.ai.azure.com", "POST", "/openai/v1/responses"),
                ("api.anthropic.com", "POST", "/v1/messages?beta=true"),
                ("api.anthropic.com", "POST", "/v1/messages/count_tokens?beta=true")]:
            self.assertTrue(ok(host, method, path), (host, method, path))
        for path in ("/v1/messages", "/v1/messages/count_tokens", "/v1/chat/completions"):
            self.assertTrue(ok("10.0.0.5:8080", "POST", path, plain=True), path)
        self.assertTrue(ok("res-1.openai.azure.com", "POST", "/openai/deployments/gpt-6/chat/completions"))

    def test_everything_else_is_refused(self):
        for host, method, path in [
                ("chatgpt.com", "POST", "/backend-api/wham/apps"),                  # account connectors (apps)
                ("chatgpt.com", "GET", "/backend-api/wham/usage"),
                ("chatgpt.com", "GET", "/backend-api/wham/settings/user"),
                ("chatgpt.com", "GET", "/backend-api/wham/accounts/check"),
                ("chatgpt.com", "POST", "/backend-api/codex/analytics-events/events"),
                ("chatgpt.com", "POST", "/backend-api/wham/tasks"),
                ("chatgpt.com", "GET", "/backend-api/plugins/list"),
                ("chatgpt.com", "POST", "/backend-api/codex/alpha/search"),         # Codex's own web search
                ("chatgpt.com", "POST", "/backend-api/conversation"),
                ("chatgpt.com", "POST", "/backend-api/files"),
                ("chatgpt.com", "GET", "/backend-api/codex/responses"),             # a listed path, another method
                ("chatgpt.com", "POST", "/backend-api/codex/models"),
                ("api.openai.com", "POST", "/v1/files"),
                ("api.openai.com", "POST", "/v1/images/generations"),
                ("api.openai.com", "GET", "/v1/responses/resp_123"),
                ("api.openai.com", "POST", "/v1/conversations"),
                ("api.openai.com", "POST", "/v1/vector_stores"),
                ("api.anthropic.com", "POST", "/v1/files"),
                ("api.anthropic.com", "POST", "/v1/messages/batches"),
                ("api.anthropic.com", "GET", "/api/oauth/profile"),
                ("api.anthropic.com", "POST", "/v1/mcp_servers"),
                ("auth.openai.com", "POST", "/oauth/token"),                        # an allowlisted host without a list
                ("ab.chatgpt.com", "POST", "/backend-api/codex/responses"),
                ("mcp.anthropic.com", "POST", "/v1/messages"),
                ("unknown.example.com", "POST", "/v1/responses")]:
            self.assertFalse(ok(host, method, path), (host, method, path))

    def test_no_way_around_a_listed_path(self):
        for path in ("/backend-api/codex/responses/../../wham/apps", "/backend-api/codex/responses/%2e%2e/apps",
                     "/backend-api/codex//responses", "/backend-api/codex/responses/", "/backend-api/codex/./responses",
                     "/backend-api/codex/responses;x=1", "/backend-api/codex/responses\\..\\apps",
                     "/BACKEND-API/codex/responses", "/backend-api/codex/responses/compact/more", "", "/",
                     "/backend-api/codex/responses%3Fx", "/backend-api/codex/*"):
            self.assertFalse(ok("chatgpt.com", "POST", path), path)
        self.assertFalse(ok("res-1.openai.azure.com", "POST", "/openai/deployments/a/b/chat/completions"))
        self.assertFalse(ok("res-1.openai.azure.com", "POST", "/openai/deployments/../chat/completions"))
        self.assertFalse(ok("10.0.0.5:8080", "POST", "/v1/messages"))        # an HTTPS host without a provider
        self.assertFalse(ok("chatgpt.com", "POST", "/backend-api/codex/responses", plain=True))   # http: its own list only

    def test_bad_rule_files_do_not_load(self):
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "p.json"
            for allow in ([["PUT", "/v1/x"]], [["POST", "v1/x"]], [["POST", "/v1/x?y"]], [["POST", "/v1//x"]], [["POST"]]):
                f.write_text(json.dumps({"providers": [{"name": "x", "hosts": ["h"], "allow": allow}]}))
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    gateway.load_paths(f)
            f.write_text("{}")
            with self.assertRaises(KeyError):
                gateway.load_paths(f)

    def test_server_tools(self):
        st = gateway.server_tools
        self.assertEqual(st(json.dumps({"tools": [{"name": "Bash", "input_schema": {}}, {"type": "function", "name": "x"},
                                                  {"type": "custom", "name": "apply_patch"}]})), [])
        self.assertEqual(st(json.dumps({"tools": [{"type": "web_search"}, {"type": "function"}, {"type": "mcp"},
                                                  {"type": "web_search_20250305", "name": "web_search"}]})),
                         ["mcp", "web_search", "web_search_20250305"])
        self.assertEqual(st(json.dumps({"tools": [], "mcp_servers": [{"url": "https://x"}]})), ["mcp_servers"])
        for body in (None, "", "not json", "[1]", json.dumps({"input": "the word \"tools\" in a message"})):
            self.assertEqual(st(body), [])


class Stub(BaseHTTPRequestHandler):
    seen: list[tuple[str, str]] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Stub.seen.append((self.command, self.path))
        body = json.dumps({"type": "message", "model": "stub", "usage": {"input_tokens": 3, "output_tokens": 2,
                                                                          "cache_read_input_tokens": 1}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    do_GET = do_POST


class EndToEnd(unittest.TestCase):
    """gateway.py as the runner starts it, in front of a stub model server on loopback (an --http-host upstream)."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.jobs = pathlib.Path(cls.td.name)
        cls.stub = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.stub.serve_forever, daemon=True).start()
        cls.up = f"127.0.0.1:{cls.stub.server_address[1]}"
        ready = cls.jobs / "ready"
        cls.proc = subprocess.Popen([sys.executable, str(HERE / "gateway.py"), "--jobs", str(cls.jobs), "--bind", "127.0.0.1",
                                     "--ready-file", str(ready), "--http-host", cls.up],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            if ready.exists() and ready.read_text():
                break
            if cls.proc.poll() is not None:
                raise RuntimeError(cls.proc.stderr.read().decode()[-2000:])
            time.sleep(0.1)
        cls.port = int(ready.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate(); cls.proc.wait(10); cls.proc.stderr.close()
        cls.stub.shutdown(); cls.stub.server_close(); cls.td.cleanup()

    def call(self, method: str, path: str, body: dict | None = None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        data = json.dumps(body).encode() if body is not None else None
        c.request(method, path, body=data, headers={"Content-Type": "application/json", "Authorization": "Bearer SECRET-KEY"})
        r = c.getresponse(); out = r.read(); c.close()
        return r.status, out

    def records(self) -> list[dict]:
        f = self.jobs / ".gateway" / "unattributed.jsonl"       # no trial owns loopback
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []

    def test_forwards_model_calls_and_refuses_the_rest(self):
        Stub.seen.clear()
        st, out = self.call("POST", f"/h/{self.up}/v1/messages?beta=true",
                            {"model": "m", "messages": [], "tools": [{"name": "Bash", "input_schema": {}},
                                                                     {"type": "bash_20250124", "name": "bash"}]})
        self.assertEqual(st, 200, out)
        self.assertEqual(Stub.seen, [("POST", "/v1/messages?beta=true")])
        # a tool the provider would run for the agent: refused in the provider's error format, nothing forwarded
        for tools in ([{"type": "web_search_20250305", "name": "web_search"}], [{"type": "function", "name": "f"}, {"type": "mcp"}],
                      [{"type": "image_generation"}], [{"type": "web_search"}]):
            st, out = self.call("POST", f"/h/{self.up}/v1/messages", {"model": "m", "messages": [], "tools": tools})
            self.assertEqual(st, 403, out)
            self.assertIn("runs at the model provider", json.loads(out)["error"]["message"])
        self.assertEqual(len(Stub.seen), 1, Stub.seen)
        for method, path in (("POST", "/v1/files"), ("GET", "/v1/messages"), ("POST", "/v1/messages/../files"),
                             ("POST", "/backend-api/wham/apps"), ("POST", "/v1/messages/batches")):
            st, out = self.call(method, f"/h/{self.up}{path}", {"secret": "BODY-NOT-LOGGED"} if method == "POST" else None)
            self.assertEqual(st, 403, (method, path, out))
            self.assertIn("not a model API call", json.loads(out)["error"]["message"])
        self.assertEqual(len(Stub.seen), 1, Stub.seen)            # nothing refused reached the upstream
        st, _ = self.call("POST", "/u/chatgpt.com/backend-api/wham/apps", {})      # refused before any connection
        self.assertEqual(st, 403)
        st, _ = self.call("POST", "/u/github.com/v1/responses", {})                # not a model API host at all
        self.assertEqual(st, 403)
        recs = self.records()
        refused = [r for r in recs if r.get("refused") == "path_not_allowed"]
        self.assertEqual([(r["method"], r["path"]) for r in refused],
                         [("POST", "/v1/files"), ("GET", "/v1/messages"), ("POST", "/v1/messages/../files"),
                          ("POST", "/backend-api/wham/apps"), ("POST", "/v1/messages/batches"), ("POST", "/backend-api/wham/apps")])
        self.assertTrue(all(r["status"] == 403 for r in refused))
        tool = [r for r in recs if r.get("refused") == "server_tool"]
        self.assertEqual([r["server_tools"] for r in tool], [["web_search_20250305"], ["mcp"], ["image_generation"], ["web_search"]])
        fwd = [r for r in recs if not r.get("refused")]
        self.assertEqual(len(fwd), 1)
        self.assertEqual(fwd[0]["server_tools"], ["bash_20250124"])      # recorded: a typed tool the agent runs itself
        self.assertEqual(fwd[0]["usage"], {"input": 4, "cached": 1, "output": 2})
        everything = "".join(p.read_text() for p in (self.jobs / ".gateway").iterdir() if p.is_file())
        self.assertNotIn("SECRET-KEY", everything)
        self.assertNotIn("BODY-NOT-LOGGED", everything)


if __name__ == "__main__":
    unittest.main()
