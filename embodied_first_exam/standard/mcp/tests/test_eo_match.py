"""The eo-match tool kind (suites.py) against a small fake of a match's eai-standard service with the match extension
(eai_std/: /spec, /observe, /submit, /start, /ready; lockstep and turn-based), and the oracle's seat client through
the tools (oracle/ro_client_mcp.py over a task's own ro_client.py). CPU, ~15 s.

    python3 embodied_first_exam/standard/mcp/tests/test_eo_match.py
"""
import base64, io, json, os, pathlib, socket, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
REPO = MCP.parents[2]
STD = REPO / "embodied_first_exam" / "standard"
sys.path.insert(0, str(MCP))
sys.path.insert(0, str(STD))
import rcb1  # noqa: E402
from mcp_client import McpClient, McpToolError  # noqa: E402


def png(w, h, color):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


class Fake:
    """eai_std's answers in miniature. Lockstep: 1 s units of 10 control steps, a review after each; the match ends
    after 3 units. Turn: 3 turns, a review after each."""

    def __init__(self, turn):
        self.turn, self.k, self.phase, self.units = turn, 0, "prepare", 0
        self.acts, self.holds = [], []
        self.lock = threading.Lock()

    def state(self):
        if self.turn:
            return {"done": self.phase == "over", "your_turn": self.phase in ("turn", "review"),
                    "awaiting_review": self.phase == "review",
                    "score": [self.units, 0]}
        return {"phase": self.phase, "done": self.phase == "over", "world": "running" if self.phase == "running" else "frozen",
                "step": self.k, "t_sim": round(self.k * 0.1, 3)}

    def meta(self, **extra):
        return {"protocol": "eai-standard/3.0", "step": self.k, "done": self.phase == "over",
                "score": [self.units, 0], "review_due": self.phase == "review", "match_over": self.phase == "over",
                "phase": self.phase, "state": self.state(), **extra}

    def view(self):
        tiles = [{"camera": "side", "x": 0, "y": 0, "width": 20, "height": 20},
                 {"camera": "top", "x": 20, "y": 0, "width": 20, "height": 20, "frame": 1}]
        parts = [("view", "bytes", png(40, 20, (200, 10, 10)), {"format": "png"}),
                 rcb1.array_part("last/side", np.full((20, 20, 3), 200, np.uint8)),
                 rcb1.array_part("last/top", np.full((20, 20, 3), 100, np.uint8))]
        return parts, {"observation": {"tiles": tiles}}

    def unit_over(self):
        self.units += 1
        self.phase = "over" if self.units >= 3 else "review"

    def handle(self, ep, hdr, rows):
        """-> (code, meta or JSON, parts or None: None answers JSON)"""
        with self.lock:
            if ep == "spec":
                return 200, {"protocol": "eai-standard/3.0",
                             "action_types": {"hit": {"kind": "command", "fields": {"x": [0, 1]}}, "not_yet": []},
                             "timing": {"realtime": False}, "finish": "not offered (404)",
                             "match": {"protocol": "eai-standard/3.0", "turn_based": self.turn,
                                       "actions": {"hit": {"x": [0, 1]}}, "big": "x" * 30000}}, None
            if ep in ("finish", "reset", "kinematics"):
                return 404, {"error": f"unknown endpoint /{ep}"}, None
            if ep == "start":
                self.phase = "turn" if self.turn else "running"
                return 200, {"accepted": True, "ok": True, "meta": self.meta()}, None
            if ep == "ready":
                if self.phase != "review":
                    return 409, {"error": "no review is due"}, None
                if self.turn:
                    self.units += 1
                    self.phase = "over" if self.units >= 3 else "turn"
                else:
                    self.phase = "running"
                return 200, {"accepted": True, "ok": True, "meta": self.meta()}, None
            if ep == "observe":
                if float(hdr.get("seconds") or 0) > 0:
                    return 400, {"error": "observe never lets time pass: a hold chunk"}, None
                parts, info = self.view()
                if hdr.get("cameras") == []:
                    parts = []
                return 200, self.meta(**info), parts
            if ep == "submit":
                if self.phase == "over":
                    return 409, {"error": "the match is over", "done": True}, None
                if rows is None:                                    # a hold chunk
                    if hdr.get("interpolate") != "hold" or hdr.get("type") != "hit":
                        return 400, {"error": "a hold chunk: {type, interpolate: hold, seconds}"}, None
                    self.holds.append(float(hdr["seconds"]))
                    if not self.turn and self.phase == "running":
                        n = int(round(float(hdr["seconds"]) / 0.1))
                        for _ in range(n):
                            self.k += 1
                            if self.k % 10 == 0:
                                self.unit_over()
                                break
                    return 200, self.meta(hold=True, ok=True, executed_rows=0, duration_s=0.0), []
                if len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get("type") != "hit":
                    return 400, {"error": "unknown action type"}, None
                if (self.turn and self.phase != "turn") or (not self.turn and self.phase != "running"):
                    return 200, self.meta(ok=False, not_now="not now", executed_rows=0), []
                self.acts.append(rows[0])
                if self.turn:
                    self.phase = "review"
                else:
                    self.k += 1
                return 200, self.meta(ok=True, executed_rows=1, effects=[{"row": 0, "step": self.k}],
                                      duration_s=0.1), []
            return 404, {"error": "no such endpoint"}, None


def serve(fake):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _do(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            rows = None
            if self.headers.get("Content-Type", "").startswith("application/x-rcb1"):
                hdr, parts = rcb1.decode(raw)
                if "actions" in parts:
                    rows = parts["actions"]["data"]
            else:
                hdr = json.loads(raw or b"{}")
                rows = hdr.get("rows")
            code, out, parts = fake.handle(self.path.strip("/").split("/")[-1], hdr, rows)
            if parts is None:
                body, ctype = json.dumps(out).encode(), "application/json"
            else:
                body, ctype = rcb1.encode(out, parts), "application/x-rcb1"
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = _do
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def manifest(tmp, turn):
    m = {"manifest": "efe-mcp-manifest/0", "kind": "eo-match", "suite": "embodied-olympics-match", "seat": "A",
         **({"turn": True} if turn else {})}
    p = tmp / f"m_{int(turn)}.json"
    p.write_text(json.dumps(m))
    return p


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_eo_"))
    # lockstep, through the tools
    fake = Fake(turn=False)
    srv = serve(fake)
    env = {"SIM_URL": f"http://127.0.0.1:{srv.server_address[1]}", "SEAT": "A", "EFE_MCP_WORKSPACE": str(tmp / "app"),
           "EFE_MCP_TOOLS_DIR": str(STD), "EFE_MCP_MANIFEST": str(manifest(tmp, False)),
           "EFE_MCP_LOG": str(tmp / "calls.jsonl")}
    c = McpClient(cmd=[sys.executable, str(MCP / "server.py")], env=env)
    assert list(c.tools) == ["spec", "observe", "submit", "start", "ready"], list(c.tools)
    assert "finish" not in c.tools and "at" not in c.tools["submit"]["inputSchema"]["properties"], c.tools["submit"]
    import importlib.util                     # the tool list normalize writes into a match's manifest (inject.EO_TOOLS)
    spec_ = importlib.util.spec_from_file_location("efe_mcp_inject", MCP / "inject.py")
    inj = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(inj)
    assert list(inj.EO_TOOLS) == list(c.tools), (inj.EO_TOOLS, list(c.tools))
    sp = c.call("spec")
    assert "spec" not in sp and pathlib.Path(sp["spec_file"]).is_file() and sp["keys"], sp
    c.call("start")
    r = c.call_raw("observe", inline_cameras=["top"])
    o = json.loads(r["content"][0]["text"])
    assert o["meta"]["state"]["world"] == "running" and o["meta"]["observation"]["tiles"], o
    assert o["parts"]["view"]["file"].endswith(".png") and pathlib.Path(o["parts"]["view"]["file"]).is_file(), o
    assert len(r["content"]) == 2 and r["content"][1]["mimeType"] == "image/jpeg", r["content"][1:]
    from PIL import Image
    assert Image.open(o["parts"]["last/top"]["image"]).size == (20, 20)
    try:
        c.call("observe", last_s=0, fields={"seconds": 1.0})
        raise AssertionError("observe with seconds > 0 sent")
    except McpToolError as e:
        assert "time passes only through submit" in str(e), e
    try:
        c.call("submit", type="fly", actions=[{"type": "fly"}])
        raise AssertionError("invalid action accepted")
    except McpToolError as e:
        assert str(e).startswith("400 /submit"), e
    a = c.call("submit", type="hit", actions=[{"type": "hit", "x": 0.5}])
    assert a["meta"]["ok"] and not a["meta"]["review_due"] and a["step"]["duration_s"] == 0.1, a
    w = c.call("submit", type="hit", interpolate="hold", seconds=3.0)
    assert w["meta"]["review_due"] and w["meta"]["state"]["world"] == "frozen" and w["meta"]["hold"], w
    n = c.call("submit", type="hit", actions=[{"type": "hit", "x": 0.1}])
    assert n["meta"]["ok"] is False and n["meta"]["not_now"], n                     # frozen: nothing runs
    c.call("ready", why="w", plan="p")
    c.call("submit", type="hit", interpolate="hold", seconds=1.0)
    c.call("ready", why="w", plan="p")
    w = c.call("submit", type="hit", interpolate="hold", seconds=5.0)
    assert w["meta"]["match_over"], w
    over = c.call("submit", type="hit", interpolate="hold", seconds=1.0)
    assert over.get("episode_over") and over["http_status"] == 409, over
    try:
        c.call("finish")
        raise AssertionError("a finish tool in a match")
    except McpToolError as e:
        assert "unknown tool" in str(e), e
    c.close()
    # turn-based, through the oracle's seat client (the task's own ro_client.py on the tools)
    fake2 = Fake(turn=True)
    srv2 = serve(fake2)
    ro = next((REPO / "tasks" / "embodied-olympics-match").glob("*fencing-bout*-standard/solution/ro_client.py"))
    player = tmp / "player"
    player.mkdir()
    (player / "ro_client.py").write_bytes(ro.read_bytes())
    (player / "p.py").write_text("class P:\n    def __init__(self, spec, seat, seed):\n        pass\n"
                                 "    def act(self, view):\n        assert view['observation'].get('image_png_b64')\n"
                                 "        return {'type': 'hit', 'x': 0.5}\n")
    prog = "import ro_client; ro_client.main(['p:P'])"
    env2 = {**os.environ, "SIM_URL": f"http://127.0.0.1:{srv2.server_address[1]}", "SEAT": "A",
            "EFE_MCP_WORKSPACE": str(tmp / "app2"), "EFE_MCP_MANIFEST": str(manifest(tmp, True)),
            "EFE_MCP_TOOLS_DIR": str(STD), "EFE_MCP_LOG": str(tmp / "calls2.jsonl"), "EFE_MCP_ORACLE": "1",
            "EFE_MCP_SERVER": str(MCP / "server.py"), "PYTHONPATH": str(MCP / "oracle")}
    out = subprocess.run([sys.executable, "-c", prog], cwd=player, env=env2, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and '"final_state"' in out.stdout, out.stdout + out.stderr
    calls = [r["tool"] for r in map(json.loads, (tmp / "calls2.jsonl").read_text().splitlines())
             if "tool" in r and "sim" not in r]                   # the tool calls (not the request records)
    assert len(fake2.acts) == 3 and calls.count("ready") == 3 and fake2.holds, (fake2.acts, fake2.holds, calls)
    print("ok eo-match tools (lockstep) and the oracle's seat client through them (turn):", calls)
    srv.shutdown()
    srv2.shutdown()


if __name__ == "__main__":
    main()
