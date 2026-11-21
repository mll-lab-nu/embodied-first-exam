"""The eo-match tool kind (suites.py) against a small fake seat service (lockstep and turn-based), and the oracle's
seat client through the tools (oracle/ro_client_mcp.py over a task's own ro_client.py). CPU, ~15 s.

    python3 embodied_first_exam/standard/mcp/tests/test_eo_match.py
"""
import base64, io, json, os, pathlib, socket, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
REPO = MCP.parents[2]
sys.path.insert(0, str(MCP))
from mcp_client import McpClient, McpToolError  # noqa: E402


def png(w, h, color):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class Fake:
    """Lockstep: 1 s units, a review after each; the match ends after 3 units. Turn: 3 turns, a review after each."""

    def __init__(self, turn):
        self.turn, self.k, self.phase, self.ready, self.acts, self.units = turn, 0, "prepare", False, [], 0
        self.lock = threading.Lock()

    def state(self):
        if self.turn:
            return {"done": self.units >= 3, "your_turn": self.phase == "turn", "awaiting_review": self.phase == "review",
                    "score": [self.units, 0]}
        return {"phase": self.phase, "done": self.phase == "over", "world": "running" if self.phase == "running" else "frozen",
                "ready": {"A": self.ready}, "step": self.k, "t_sim": self.k * 0.1}

    def handle(self, ep, body):
        with self.lock:
            if ep == "spec":
                return 200, {"protocol": "eai-standard-turn/1" if self.turn else "eai-standard/2.2",
                             "actions": {"hit": {"x": [0, 1]}}, "big": "x" * 30000}
            if ep == "status":
                return 200, self.state()
            if ep == "start":
                self.phase = "turn" if self.turn else "running"
                return 200, self.state()
            if ep == "observe":
                img = png(40, 20, (200, 10, 10))
                return 200, {("state" if self.turn else "now"): self.state(),
                             "observation": {"image_png_b64": img, "tiles": [
                                 {"camera": "side", "x": 0, "y": 0, "width": 20, "height": 20},
                                 {"camera": "top", "x": 20, "y": 0, "width": 20, "height": 20, "frame": 1}]}}
            if ep == "act":
                if body.get("type") != "hit":
                    return 400, {"error": "unknown action type"}
                if (self.turn and self.phase != "turn") or (not self.turn and self.phase != "running"):
                    return 409, {"error": "not now", ("state" if self.turn else "now"): self.state()}
                self.acts.append(body)
                if self.turn:
                    self.phase = "review"
                return 200, {"took_effect": True, ("state" if self.turn else "now"): self.state()}
            if ep == "wait":
                if self.turn:
                    return 200, {"state": self.state()}
                d = float(body.get("dt", 0))
                if not 0 < d <= 1:
                    return 400, {"error": "dt must be 0..1 game seconds"}
                if self.phase == "running":
                    self.k += int(round(d / 0.1))
                    if self.k >= 10 * (self.units + 1):
                        self.units += 1
                        self.phase, self.ready = ("over" if self.units >= 3 else "review"), False
                return 200, {"now": self.state()}
            if ep == "ready":
                if self.turn:
                    if self.phase != "review":
                        return 409, {"error": "no review is due"}
                    self.units += 1
                    self.phase = "turn"
                    return 200, {"state": self.state()}
                if self.phase != "review":
                    return 409, {"error": "not awaiting ready"}
                self.phase, self.ready = "running", False
                return 200, {"now": self.state()}
            return 404, {"error": "no such endpoint"}


def serve(fake):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _do(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            code, out = fake.handle(self.path.rstrip("/").split("/")[-1], body)
            raw = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        do_GET = do_POST = _do
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def manifest(tmp, turn):
    m = {"manifest": "efe-mcp-manifest/0", "kind": "eo-match", "suite": "embodied-olympics-match", "seat": "A",
         "max_wait_s": 10, **({"turn": True} if turn else {})}
    p = tmp / f"m_{int(turn)}.json"
    p.write_text(json.dumps(m))
    return p


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_eo_"))
    # lockstep, through the tools
    fake = Fake(turn=False)
    srv = serve(fake)
    env = {"SIM_URL": f"http://127.0.0.1:{srv.server_address[1]}", "SEAT": "A", "EFE_MCP_WORKSPACE": str(tmp / "app"),
           "EFE_MCP_MANIFEST": str(manifest(tmp, False)), "EFE_MCP_LOG": str(tmp / "calls.jsonl")}
    c = McpClient(cmd=[sys.executable, str(MCP / "server.py")], env=env)
    assert sorted(c.tools) == ["act", "observe", "ready", "spec", "start", "status", "wait"], sorted(c.tools)
    sp = c.call("spec")
    assert "spec" not in sp and pathlib.Path(sp["spec_file"]).is_file() and sp["keys"], sp
    c.call("start")
    r = c.call_raw("observe", inline_tiles=[1])
    o = json.loads(r["content"][0]["text"])
    tiles = o["observation"]["tiles"]
    assert pathlib.Path(o["observation"]["image_file"]).is_file() and all(pathlib.Path(t["file"]).is_file() for t in tiles), o
    assert len(r["content"]) == 2 and r["content"][1]["mimeType"] == "image/png", r["content"][1:]
    from PIL import Image
    assert Image.open(tiles[1]["file"]).size == (20, 20)
    try:
        c.call("act", action={"type": "fly"})
        raise AssertionError("invalid action accepted")
    except McpToolError as e:
        assert "HTTP 400" in str(e), e
    a = c.call("act", action={"type": "hit", "x": 0.5})
    assert a["took_effect"] and not a["review_due"], a
    w = c.call("wait", seconds=3.0)
    assert w["review_due"] and w["waited_game_s"] == 1.0 and w["now"]["world"] == "frozen", w   # stopped at the freeze
    c.call("ready", why="w", plan="p")
    w = c.call("wait", seconds=1.0)
    c.call("ready", why="w", plan="p")
    w = c.call("wait", seconds=5.0)
    assert w["match_over"], w
    c.close()
    # turn-based, through the oracle's seat client (the task's own ro_client.py on the tools)
    fake2 = Fake(turn=True)
    srv2 = serve(fake2)
    ro = next((REPO / "tasks" / "embodied-olympics-match").glob("*fencing-bout*-standard/solution/ro_client.py"))
    player = tmp / "player"
    player.mkdir()
    (player / "ro_client.py").write_bytes(ro.read_bytes())
    (player / "p.py").write_text("class P:\n    def __init__(self, spec, seat, seed):\n        pass\n"
                                 "    def act(self, view):\n        return {'type': 'hit', 'x': 0.5}\n")
    prog = "import ro_client; ro_client.main(['p:P'])"
    env2 = {**os.environ, "SIM_URL": f"http://127.0.0.1:{srv2.server_address[1]}", "SEAT": "A",
            "EFE_MCP_WORKSPACE": str(tmp / "app2"), "EFE_MCP_MANIFEST": str(manifest(tmp, True)),
            "EFE_MCP_LOG": str(tmp / "calls2.jsonl"), "EFE_MCP_ORACLE": "1", "EFE_MCP_SERVER": str(MCP / "server.py"),
            "PYTHONPATH": str(MCP / "oracle")}
    out = subprocess.run([sys.executable, "-c", prog], cwd=player, env=env2, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and '"final_state"' in out.stdout, out.stdout + out.stderr
    calls = [json.loads(x)["tool"] for x in (tmp / "calls2.jsonl").read_text().splitlines()]
    assert len(fake2.acts) == 3 and calls.count("act") == 3 and calls.count("ready") == 3, (fake2.acts, calls)
    print("ok eo-match tools (lockstep) and the oracle's seat client through them (turn):", calls)
    srv.shutdown()
    srv2.shutdown()


if __name__ == "__main__":
    main()
