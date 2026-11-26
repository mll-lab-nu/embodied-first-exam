"""End-to-end test of the efe-robot MCP server against the toy eai-standard/2.2 service (CPU, ~10 s): the endpoint
tools' request and reply, a hold chunk (no rows), a refusal, the end of the episode, finish refused where the success is not hidden, a tool
added from /spec (kinematics), and a pending call collected with observe(operation=...).

    python3 embodied_first_exam/standard/mcp/tests/test_toy.py
"""
import json, os, pathlib, socket, subprocess, sys, tempfile
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent
sys.path.insert(0, str(MCP))
from mcp_client import McpClient, McpToolError  # noqa: E402


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_toy_"))
    port = free_port()
    env = {**os.environ, "RCB_DATA": str(tmp / "data"), "RCB_TOY_PORT": str(port), "PYTHONPATH": str(STD),
           "RCB_TOY_STEP_S": "0.02"}
    sim = subprocess.Popen([sys.executable, str(STD / "toy_server.py")], env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(HERE / "toy_manifest.json"),
                           "--max-block-s", "1"],
                      env={"SIM_URL": f"http://127.0.0.1:{port}", "EFE_MCP_TOOLS_DIR": str(STD),
                           "EFE_MCP_WORKSPACE": str(tmp / "app"), "EFE_MCP_LOG": str(tmp / "efe-mcp.jsonl")})
        names = sorted(c.tools)
        assert names == ["finish", "observe", "spec", "submit"], names
        assert "at" not in c.tools["submit"]["inputSchema"]["properties"]          # standard mode
        assert "seconds" not in c.tools["observe"]["inputSchema"]["properties"]    # a read of the recorder
        assert "last_s" in c.tools["observe"]["inputSchema"]["properties"]
        assert "frozen between submits" in c.tools["observe"]["description"]
        try:
            import jsonschema
            for tool in c.tools.values():
                jsonschema.Draft202012Validator.check_schema(tool["inputSchema"])
        except ImportError:
            pass
        sp = c.call("spec")
        spec = json.loads(pathlib.Path(sp["spec_file"]).read_text())
        assert spec["protocol"].startswith("eai-standard/2."), spec
        try:
            c.call("observe", fields={"seconds": 1.0})
            raise AssertionError("an observe with a forward window (seconds > 0) must be refused")
        except McpToolError as e:
            assert "last_s" in str(e), e
        ob = c.call("observe", cameras=["top"])
        assert ob["meta"]["proprio"]["now"] is not None and ob["parts"]["last/top"]["image"].endswith(".png"), ob
        a = np.load(ob["parts"]["last/top"]["file"])
        assert a.dtype == np.uint8 and a.ndim == 3, a.shape
        assert ob["tool_s"] >= 0
        assert "seconds" in c.tools["submit"]["inputSchema"]["properties"]         # the hold chunk
        h = c.call("submit", type="joint_position", interpolate="hold", seconds=0.2, cameras=["top"], video="none")
        assert h["meta"].get("hold") and h["meta"].get("executed_rows") == 0, h["meta"]
        assert abs(float(h["step"]["duration_s"]) - 0.2) < 1e-6, h["step"]          # the result repeats duration_s
        try:                                                     # rows and seconds: refused before anything is sent
            c.call("submit", type="joint_position", actions=[[0.0, 0.0, 0.0]], interpolate="hold", seconds=0.2)
            raise AssertionError("rows together with seconds were accepted")
        except McpToolError as e:
            assert "hold chunk" in str(e), e
        try:                                                     # a refusal: the service's status and error
            c.call("submit", type="joint_position", actions=[[0.1, 0.2]], dt=0.05)
            raise AssertionError("a row of the wrong width was accepted")
        except McpToolError as e:
            assert str(e).startswith("400 /submit"), e
        # a long chunk: pending after 1 s, collected with observe(operation=...)
        raw = c.call_raw("submit", type="joint_position", actions=[[0.3 * k / 100, 0, 0] for k in range(1, 101)],
                         dt=0.05, cameras=["top"], video="none")
        out = json.loads(raw["content"][0]["text"])
        assert out.get("pending") and "observe(operation=" in out["note"], out
        while out.get("pending"):
            out = json.loads(c.call_raw("observe", operation=out["operation"])["content"][0]["text"])
        assert out["meta"]["executed_rows"] == 100, out["meta"]
        np.save(tmp / "app" / "rows.npy", np.array([[0.5 + 0.05 * k, 0, 0] for k in range(10)], dtype=np.float32))
        r = c.call("submit", type="joint_position", actions_file="rows.npy", dt=0.1, cameras=["top"], video="none")
        assert r["meta"]["done"] and r["meta"]["reason"] == "success", r["meta"]
        r = c.call("submit", type="joint_position", actions=[[1.0, 0, 0]], dt=0.05)
        assert r.get("episode_over") and r.get("http_status") == 409, r
        try:
            c.call("finish")
            raise AssertionError("finish sent in a task whose success is not hidden")
        except McpToolError as e:
            assert "nothing sent" in str(e), e
        ep = [json.loads(l) for l in (tmp / "data" / "episode.jsonl").read_text().splitlines()]
        n_sub = sum(1 for e in ep if e.get("ev") == "submit")
        log = [json.loads(l) for l in (tmp / "efe-mcp.jsonl").read_text().splitlines()]
        assert any(x.get("sim") == "/submit" for x in log), log[:4]
        c.close()
        print(f"ok efe-robot MCP server against the toy service: tools {names}, {n_sub} submits, a pending call "
              "collected, the refusal's status kept")
    finally:
        sim.terminate(); sim.wait(10)


if __name__ == "__main__":
    main()
