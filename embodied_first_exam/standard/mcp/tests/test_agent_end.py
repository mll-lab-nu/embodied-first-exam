"""finish through the efe-robot tools in an agent-ended episode (CPU, ~20 s): the toy eai-standard/2.2 service made an
agent-ended adapter (agent_end/agent_end_selftest.py's patch, RCB_AGENT_END=1; /spec success_signal is the sentence
SUCCESS_SIGNAL_NOTE, which starts with "hidden"):

1. the tools: `finish` sends POST /finish and the episode ends ("finished"; final.json ended_by "finish"); a submit after
   it comes back as episode_over;
2. the oracle shim (oracle/rcb_client_mcp.py): an oracle that ends its episode with Robot.finish() runs once over HTTP and
   once through the tools and leaves the same record (tests/equivalence.py), ended by finish in both.

    python3 embodied_first_exam/standard/mcp/tests/test_agent_end.py
"""
import json, os, pathlib, subprocess, sys, tempfile, textwrap
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent
sys.path.insert(0, str(MCP))
sys.path.insert(0, str(STD / "agent_end"))
from mcp_client import McpClient  # noqa: E402
import agent_end_selftest as AES  # noqa: E402

ORACLE = textwrap.dedent('''
    from rcb_client import Robot, EpisodeOver
    import numpy as np
    r = Robot(); spec = r.spec()
    assert spec["success_signal"].startswith("hidden"), spec.get("success_signal")
    q = np.asarray(r.get_obs(cameras=[]).meta["proprio"]["now"][:3])
    for k in range(12):                        # to the block and stay there: the success is hidden, nothing ends
        tgt = q + np.clip(np.array([0.95, 0, 0]) - q, -0.1, 0.1)
        res = r.submit("joint_position", np.linspace(q, tgt, 4), dt=0.05, cameras=[], video="none")
        q = np.asarray(res.meta["proprio"]["now"][:3])
        print("step", k, np.round(q, 6).tolist(), res.meta["done"], res.meta["reason"])
    print("finish", sorted(r.finish()))
    try:
        r.submit("joint_position", np.linspace(q, q, 2), dt=0.05, cameras=[], video="none")
        print("after finish: accepted")
    except EpisodeOver as e:
        print("after finish: over")
''')


def tools_direct(src: str, tmp: pathlib.Path):
    toy = AES.Toy(src, {"RCB_AGENT_END": "1", "PYTHONPATH": src})
    try:
        c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(HERE / "toy_manifest.json")],
                      env={"SIM_URL": f"http://127.0.0.1:{toy.port}", "EFE_MCP_TOOLS_DIR": str(STD),
                           "EFE_MCP_WORKSPACE": str(tmp / "app"), "EFE_MCP_LOG": str(tmp / "efe-mcp.jsonl")})
        sp = c.call("spec")
        sig = json.loads(pathlib.Path(sp["spec_file"]).read_text())["success_signal"]
        assert sig != "hidden" and sig.startswith("hidden"), sig        # the sentence, as every agent-ended service
        r = c.call("submit", type="joint_position", actions=[[0.1, 0, 0], [0.2, 0, 0]], dt=0.05, video="none")
        assert not r["meta"]["done"], r["meta"]
        f = c.call("finish")
        assert not f.get("episode_over") and "error" not in f, f
        st = toy.call("GET", "/status")["json"]
        assert st.get("done") and st.get("reason") == "finished", st
        r = c.call("submit", type="joint_position", actions=[[0.2, 0, 0]], dt=0.05, video="none")
        assert r.get("episode_over") and r.get("http_status") == 409, r
        log = [json.loads(l) for l in (tmp / "efe-mcp.jsonl").read_text().splitlines()]
        assert any(x.get("sim") == "/finish" for x in log), "finish sent no /finish"
        c.close()
    finally:
        fin = toy.end()
    assert fin.get("ended_by") == "finish", fin
    return fin


def oracle_shim(src: str, tmp: pathlib.Path):
    (tmp / "oracle.py").write_text(ORACLE)
    cmd = [sys.executable, str(HERE / "equivalence.py"), "--service", f"{sys.executable} {src}/toy_server.py",
           "--port-env", "RCB_TOY_PORT", "--service-env", f"PYTHONPATH={src}", "--service-env", "RCB_AGENT_END=1",
           "--tools", str(STD), "--manifest", str(HERE / "toy_manifest.json"),
           "--oracle", f"{sys.executable} {tmp / 'oracle.py'}", "--out", str(tmp / "equiv"),
           "--compare", "journal.f64,final.json"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    s = json.loads(p.stdout.strip().splitlines()[-1])
    assert p.returncode == 0, p.stdout + p.stderr
    assert {"journal.f64", "final.json"} <= set(s["same"]) and "finish" in s["mcp_tools_called"], s
    for mode in ("api", "mcp"):
        out = (pathlib.Path(s["out"]) / mode / "oracle.out").read_text()
        assert "after finish: over" in out, out
        fin = json.loads((pathlib.Path(s["out"]) / mode / "data" / "final.json").read_text())
        assert fin.get("ended_by") == "finish" and fin.get("success") is True, (mode, fin)
    return s


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_ae_"))
    src = AES.adapter(True)
    fin = tools_direct(src, tmp)
    print("ok finish through the tools ends an agent-ended episode: ended_by", fin["ended_by"])
    s = oracle_shim(src, tmp)
    print("ok agent-ended oracle: API path = MCP path:", ", ".join(s["same"]), "identical; tools", s["mcp_tools_called"],
          "; evidence", s["out"])


if __name__ == "__main__":
    main()
