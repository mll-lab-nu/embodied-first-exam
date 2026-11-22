"""The reference-solution client (oracle/rcb_client_mcp.py) against the toy eai-standard/2.2 service: an oracle written
for rcb_client runs unchanged through the efe-robot MCP server (CPU, ~20 s).

    python3 embodied_first_exam/standard/mcp/tests/test_oracle_shim.py
"""
import json, os, pathlib, socket, subprocess, sys, tempfile, textwrap
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent

ORACLE = textwrap.dedent('''
    import sys
    sys.path.insert(0, "/opt/tools")
    from rcb_client import Robot, EpisodeOver
    r = Robot(); spec = r.spec()
    assert spec["protocol"].startswith("eai-standard/2."), spec["protocol"]
    obs = r.get_obs(cameras=["top"])
    assert obs.last["top"].ndim == 3 and len(obs.meta["proprio"]["now"]) >= 3
    import numpy as np
    A = np.array([[0.5 + 0.05 * k, 0, 0] for k in range(10)])
    try:
        res = r.submit("joint_position", A, dt=0.1, cameras=["top"], video="none", note="oracle")
        print("rows", res.meta["executed_rows"], "done", res.meta["done"], res.meta["reason"])
        assert res.meta["done"] and res.meta["reason"] == "success", dict(res.meta)
    except EpisodeOver as e:
        print("over", e)
    print("status", r.status().get("done"))
''')


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_oracle_"))
    port = free_port()
    env = {**os.environ, "RCB_DATA": str(tmp / "data"), "RCB_TOY_PORT": str(port), "PYTHONPATH": str(STD)}
    sim = subprocess.Popen([sys.executable, str(STD / "toy_server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        (tmp / "oracle.py").write_text(ORACLE)
        oenv = {**os.environ, "SIM_URL": f"http://127.0.0.1:{port}", "EFE_MCP_TOOLS_DIR": str(STD),
                "EFE_MCP_WORKSPACE": str(tmp / "app"), "EFE_MCP_SERVER": str(MCP / "server.py"),
                "EFE_MCP_MANIFEST": str(HERE / "toy_manifest.json"), "EFE_MCP_ORACLE": "1",
                "EFE_MCP_LOG": str(tmp / "efe-mcp.jsonl"),
                "PYTHONPATH": os.pathsep.join([str(MCP / "oracle"), str(STD)])}
        out = subprocess.run([sys.executable, str(tmp / "oracle.py")], env=oenv, capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "done True success" in out.stdout, out.stdout
        log = [json.loads(l) for l in (tmp / "efe-mcp.jsonl").read_text().splitlines()]
        calls = [c for c in log if "tool" in c and "sim" not in c]     # the tool calls (not the request records)
        tools = [c["tool"] for c in calls]
        assert any(c.get("server") and c.get("via") == "oracle" for c in log), log[:2]   # the oracle's server, labelled
        assert any(c.get("sim") == "/submit" and c.get("note", "").startswith("efe-mcp:") for c in log), log[:5]
        assert "execute_trajectory" in tools and "describe_robot" in tools, tools
        print("ok oracle through the efe-robot MCP server:", out.stdout.strip().replace("\n", "; "), "| tool calls:", tools)
    finally:
        sim.terminate(); sim.wait(10)


if __name__ == "__main__":
    main()
