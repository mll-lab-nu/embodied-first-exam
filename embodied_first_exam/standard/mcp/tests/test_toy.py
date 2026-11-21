"""End-to-end test of the efe-robot MCP server against the toy eai-standard/2.2 service (CPU, ~20 s).

    python3 embodied_first_exam/standard/mcp/tests/test_toy.py
"""
import json, os, pathlib, socket, subprocess, sys, tempfile, time
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
    env = {**os.environ, "RCB_DATA": str(tmp / "data"), "RCB_TOY_PORT": str(port), "PYTHONPATH": str(STD)}
    sim = subprocess.Popen([sys.executable, str(STD / "toy_server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(HERE / "toy_manifest.json"), "--max-block-s", "20"],
                      env={"SIM_URL": f"http://127.0.0.1:{port}", "EFE_MCP_TOOLS_DIR": str(STD), "EFE_MCP_WORKSPACE": str(tmp / "app")})
        names = sorted(c.tools)
        assert "locomote" not in names and "move_robot" in names, names
        t = c.tools["move_robot"]["inputSchema"]
        assert t["$schema"].endswith("2020-12/schema")
        assert t["properties"]["goals"]["items"]["properties"]["target"]["enum"] == ["arm"]
        try:
            import jsonschema
            for tool in c.tools.values():
                jsonschema.Draft202012Validator.check_schema(tool["inputSchema"])
        except ImportError:
            pass
        d = c.call("describe_robot")
        assert d["parts"]["arm"]["joints"]["count"] == 3, d
        o = c.call("observe", inline_cameras=["top"])
        img = o["cameras"]["top"]["image"]
        assert pathlib.Path(img).is_file() and img.startswith(str(tmp / "app" / "obs")), img
        r = c.call("move_robot", goals=[{"target": "arm", "joint_positions": [0.3, 0.2, 0.1]}], duration_s=1.0)
        assert r["moved"] and r["reached"][0]["ok"], r
        q = r["parts"]["arm"]["joint_positions"]
        assert max(abs(a - b) for a, b in zip(q, [0.3, 0.2, 0.1])) < 1e-3, q
        # the ee pose is reported in the base frame: base at x=0.1 yawed +90 deg, tip at world (0.3, 0.2, 0.1)
        p = r["parts"]["arm"]["ee"]["position"]
        assert abs(p[0] - 0.2) < 1e-3 and abs(p[1] + 0.2) < 1e-3 and abs(p[2] - 0.1) < 1e-3, p
        r = c.call("execute_trajectory", space="joint", rows=[{"arm": {"joint_positions": [0.5 + 0.05 * k, 0, 0]}} for k in range(10)], dt=0.1)
        assert r["executed_rows"] >= 1 and r.get("done") and r.get("reason") == "success", r   # the tip pushed the block past x = 0.9
        r = c.call("execute_trajectory", space="native", action_type="joint_position", native_rows=[[1.0, 0, 0]] * 20, dt=0.05)
        assert r.get("episode_over"), r
        try:
            c.call("move_robot", goals=[{"target": "leg", "joint_positions": [0, 0, 0]}])
            raise AssertionError("unknown target accepted")
        except McpToolError as e:
            assert "enum" in str(e) or "one of" in str(e) or "unknown" in str(e), e
        ep = [json.loads(l) for l in (tmp / "data" / "episode.jsonl").read_text().splitlines()]
        notes = [e.get("note") for e in ep if e.get("ev") == "submit"]
        c.close()
        print("ok efe-robot MCP server against the toy service:", len(names), "tools,", sum(1 for e in ep if e.get('ev') == 'submit'), "submits")
    finally:
        sim.terminate(); sim.wait(10)


if __name__ == "__main__":
    main()
