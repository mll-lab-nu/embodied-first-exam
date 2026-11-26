"""The efe-robot tools when the service fails (CPU, ~5 s), against a scripted stand-in for a 2.4 service:

1. a 5xx is the service's answer, not a lost reply: the tool returns the status and the error at once (failure category
   "service") and never polls GET /operations/<id>;
2. a reply that never comes (the connection closed): the tool re-queries /operations/<id> and says the reply was lost;
   through the oracle shim (oracle/rcb_client_mcp.py) the 2.4 client sees the ConnectionError the request would have
   raised (no fabricated empty reply), and its GET /operations/<id> answers with the record the tool server fetched;
3. GET /spec answered 409 (the service gave up): the tools say the episode is over (episode_over), not an internal error.

    python3 embodied_first_exam/standard/mcp/tests/test_failures.py
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile, textwrap, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent
sys.path.insert(0, str(MCP))
from mcp_client import McpClient, McpToolError  # noqa: E402

SPEC = {"protocol": "eai-standard/2.4", "standard": "eai-standard/3.0", "max_call_wall_s": 30,
        "action_types": {"joint_position": {"dim": 3}}, "cameras": {}, "budget": {}}


class Fake(BaseHTTPRequestHandler):
    """GET /spec: SPEC (or 409 when `gave_up`); POST /submit: 500; POST /observe: the connection closed, no reply;
    GET /operations/<id>: the record of a completed call. `seen` counts the requests per path."""
    gave_up = False
    seen: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        key = "/operations/" if self.path.startswith("/operations/") else self.path
        Fake.seen[key] = Fake.seen.get(key, 0) + 1
        if self.path == "/spec":
            return self._send(409, {"error": "the service gave up", "reason": "error"}) if Fake.gave_up \
                else self._send(200, SPEC)
        if key == "/operations/":
            return self._send(200, {"operation_id": self.path.rsplit("/", 1)[1], "status": "completed",
                                    "rows_before": 0, "committed_rows": 0})
        self._send(404, {"error": "no such endpoint"})

    def do_POST(self):
        Fake.seen[self.path] = Fake.seen.get(self.path, 0) + 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/submit":
            return self._send(500, {"error": "boom: the adapter raised"})
        if self.path == "/observe":
            self.close_connection = True          # no reply at all: a lost reply
            return
        self._send(404, {"error": "no such endpoint"})


SHIM_ORACLE = textwrap.dedent('''
    import requests
    from rcb_client import Robot
    r = Robot()
    try:
        r.get_obs(cameras=[])
        print("observe: a reply")
    except requests.exceptions.ConnectionError as e:
        print("observe: ConnectionError")
    print("operation:", r.operation_status(r.last_operation_id)["status"])
''')


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_fail_"))
    tools = tmp / "tools"; tools.mkdir()
    shutil.copy(STD / "rcb1.py", tools / "rcb1.py"); shutil.copy(STD / "v2_4/rcb_client.py", tools / "rcb_client.py")
    man = tmp / "manifest.json"
    man.write_text(json.dumps({"manifest": "efe-mcp-manifest/1", "kind": "rcb", "suite": "toy", "task": "toy-2.4",
                               "protocol": "eai-standard/2.4", "realtime": False,
                               "tools": ["spec", "observe", "submit", "finish"]}))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    env = {"SIM_URL": url, "EFE_MCP_TOOLS_DIR": str(tools), "EFE_MCP_WORKSPACE": str(tmp / "app"),
           "EFE_MCP_LOG": str(tmp / "efe-mcp.jsonl")}
    try:
        c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(man), "--max-block-s", "20"], env=env)
        c.call("spec")
        # 1. a 5xx: the service's error, at once; /operations never asked
        try:
            c.call("submit", type="joint_position", actions=[[0.0, 0.0, 0.0]], dt=0.05)
            raise AssertionError("a 500 came back as a result")
        except McpToolError as e:
            assert str(e).startswith("500 /submit") and "boom" in str(e) \
                and e.payload["failure"]["category"] == "service", e.payload
        assert Fake.seen.get("/operations/", 0) == 0, Fake.seen
        # 2. a lost reply: the record from /operations/<id>
        ob = c.call("observe", cameras=[])
        assert ob.get("reply_lost") and ob["operation"]["status"] == "completed", ob
        assert Fake.seen.get("/operations/", 0) == 1, Fake.seen
        c.close()
        (tmp / "oracle.py").write_text(SHIM_ORACLE)
        o = subprocess.run([sys.executable, str(tmp / "oracle.py")], capture_output=True, text=True, timeout=120,
                           env={**os.environ, **env, "EFE_MCP_ORACLE": "1", "EFE_MCP_SERVER": str(MCP / "server.py"),
                                "EFE_MCP_MANIFEST": str(man),
                                "PYTHONPATH": os.pathsep.join([str(MCP / "oracle"), str(tools)])})
        assert "observe: ConnectionError" in o.stdout and "operation: completed" in o.stdout, o.stdout + o.stderr
        # 3. GET /spec 409: the episode is over
        Fake.gave_up = True
        c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(man)], env=env)
        for name, args in (("observe", {"cameras": []}), ("spec", {})):
            r = c.call_raw(name, **args)
            out = json.loads(r["content"][0]["text"])
            assert not r["isError"] and out.get("episode_over"), (name, r)
        c.close()
    finally:
        httpd.shutdown()
    print("ok failures: a 5xx is the service's error (no /operations poll); a lost reply re-queries /operations and "
          "reaches the shimmed client as a ConnectionError; /spec 409 is episode_over")


if __name__ == "__main__":
    main()
