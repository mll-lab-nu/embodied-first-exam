"""The generated Python client (client_gen.py -> efe_robot.py, mode standard-mcp-shell) against the toy eai-standard/2.2
service: same tools, same results, errors raise ToolError, the call log tags its calls (CPU, ~20 s).

    python3 embodied_first_exam/standard/mcp/tests/test_client_gen.py
"""
import json, os, pathlib, socket, subprocess, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_client_"))
    port = free_port()
    sim = subprocess.Popen([sys.executable, str(STD / "toy_server.py")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={**os.environ, "RCB_DATA": str(tmp / "data"), "RCB_TOY_PORT": str(port), "PYTHONPATH": str(STD)})
    try:
        subprocess.run([sys.executable, str(MCP / "client_gen.py"), str(HERE / "toy_manifest.json"), str(tmp / "efe_robot.py")],
                       check=True)
        env = {**os.environ, "SIM_URL": f"http://127.0.0.1:{port}", "EFE_MCP_TOOLS_DIR": str(STD),
               "EFE_MCP_WORKSPACE": str(tmp / "app"), "EFE_MCP_MANIFEST": str(HERE / "toy_manifest.json"),
               "EFE_MCP_SERVER": str(MCP / "server.py"), "EFE_MCP_LOG": str(tmp / "calls.jsonl")}
        prog = """
import json, pathlib, sys
import efe_robot as R
d = R.describe_robot(); assert d["parts"]["arm"]["joints"]["count"] == 3, d
o = R.observe(cameras=["top"]); img = o["cameras"]["top"]["image"]
assert pathlib.Path(img).is_file() and "_py_" in pathlib.Path(img).name, img
r = R.move_robot([{"target": "arm", "joint_positions": [0.3, 0.2, 0.1]}], duration_s=1.0)
assert r["moved"] and r["reached"][0]["ok"], r
try:
    R.move_robot([{"target": "leg", "joint_positions": [0, 0, 0]}]); raise AssertionError("unknown target accepted")
except R.ToolError as e:
    assert e.payload.get("error"), e.payload
assert "locomote" not in R.TOOLS and not hasattr(R, "locomote")
R.close(); print("client ok")
"""
        out = subprocess.run([sys.executable, "-c", prog], env={**env, "PYTHONPATH": str(tmp)}, cwd=tmp,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0 and "client ok" in out.stdout, out.stdout + out.stderr
        cli = subprocess.run([sys.executable, str(tmp / "efe_robot.py"), "wait", '{"seconds": 0.2}'], env=env,
                             capture_output=True, text=True, timeout=60)
        assert cli.returncode == 0 and "time_left_s" in json.loads(cli.stdout), cli.stdout + cli.stderr
        calls = [json.loads(x) for x in (tmp / "calls.jsonl").read_text().splitlines()]
        assert calls and all(c.get("via") == "python" for c in calls), calls
        print("ok generated Python client against the toy service:", [c["tool"] for c in calls])
    finally:
        sim.terminate()
        sim.wait(10)


if __name__ == "__main__":
    main()
