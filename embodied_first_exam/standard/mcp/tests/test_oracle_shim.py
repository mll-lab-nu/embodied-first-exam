"""API path vs MCP path on the toy service on the shared and the operations layers (CPU, ~40 s): an oracle written for rcb_client runs once
on the client over HTTP and once with the client's HTTP sent through the efe-robot endpoint tools
(oracle/rcb_client_mcp.py); both leave the same record (trajectory, journal, verdict) bit for bit (tests/equivalence.py).

    python3 embodied_first_exam/standard/mcp/tests/test_oracle_shim.py
"""
import json, pathlib, shutil, subprocess, sys, tempfile, textwrap
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent

ORACLE = textwrap.dedent('''
    from rcb_client import Robot, EpisodeOver
    import numpy as np
    r = Robot(); spec = r.spec()
    assert spec["protocol"] == "eai-standard/3.0", spec["protocol"]
    obs = r.get_obs(cameras=["top"])
    q = np.asarray(obs.meta["proprio"]["now"][:3])
    img = obs.last["top"]
    print("img", img.shape, int(img.sum()))
    h = r.hold(0.1, cameras=["top"], video="frames")        # a hold chunk: no rows, the same path through the tools
    print("hold", h.meta.get("hold"), h.meta.get("executed_rows"), h.meta.get("duration_s"), sorted(h.frames), h.last["top"].shape)
    # closed loop on what the robot reports: move towards the block in steps, each from the measured joints
    for k in range(12):
        tgt = q + np.clip(np.array([0.95, 0, 0]) - q, -0.1, 0.1)
        try:
            res = r.submit("joint_position", np.linspace(q, tgt, 4), dt=0.05, cameras=["top"], video="frames")
        except EpisodeOver as e:
            print("over", str(e)[:60]); break
        q = np.asarray(res.meta["proprio"]["now"][:3])
        print("step", k, np.round(q, 6).tolist(), res.meta["done"], res.meta["reason"],
              {c: f.shape for c, f in res.frames.items()}, int(res.last["top"].sum()))
        if res.meta["done"]:
            break
    f = r.finish()                                            # agent-ended: the episode ends here, its state is judged
    print("finish", f.get("done"), f.get("reason"))
    print("status", r.status().get("done"))
''')


def layer(tmp, name):
    """The service's and the agent's file sets of one layer: "shared" = embodied_first_exam/standard/, "operations" = its
    operations/ layer and client with the shared rcb1.py (as a task on the operations layer has them)."""
    if name == "shared":
        return STD, STD, HERE / "toy_manifest.json"
    d = tmp / "operations"; d.mkdir()
    shutil.copy(STD / "rcb1.py", d / "rcb1.py")
    # the toy adapter is written for the shared layer; its one shared-only call (the agent's clock in meta) gets a stand-in
    src = (STD / "toy_server.py").read_text().replace(
        "import rcb_limited as L  # noqa: E402",
        "import rcb_limited as L  # noqa: E402\nL.agent_time = getattr(L, 'agent_time', lambda E: 0.0)", 1)
    (d / "toy_server.py").write_text(src)
    shutil.copy(STD / "operations/rcb_limited.py", d / "rcb_limited.py"); shutil.copy(STD / "operations/rcb_client.py", d / "rcb_client.py")
    shutil.copy(STD / "agent_end/rcb_agent_end.py", d / "rcb_agent_end.py")   # the toy is an agent-ended adapter
    shutil.copy(HERE / "toy_manifest.json", d / "manifest.json")
    return d, d, d / "manifest.json"


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_equiv_"))
    (tmp / "oracle.py").write_text(ORACLE)
    for version in ("shared", "operations"):
        srv, tools, man = layer(tmp, version)
        cmd = [sys.executable, str(HERE / "equivalence.py"), "--service", f"{sys.executable} {srv / 'toy_server.py'}",
               "--port-env", "RCB_TOY_PORT", "--service-env", f"PYTHONPATH={srv}", "--tools", str(tools),
               "--manifest", str(man), "--oracle", f"{sys.executable} {tmp / 'oracle.py'}",
               "--out", str(tmp / version), "--compare", "trajectory.npz,journal.f64,final.json"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        s = json.loads(p.stdout.strip().splitlines()[-1])
        assert p.returncode == 0, p.stdout + p.stderr
        assert "journal.f64" in s["same"] and {"observe", "spec", "submit", "finish"} <= set(s["mcp_tools_called"]), s
        out = (pathlib.Path(s["out"]) / "api" / "oracle.out").read_text()
        assert "finish True finished" in out and "status True" in out, out
        final = json.loads((pathlib.Path(s["out"]) / "api" / "data" / "final.json").read_text())
        assert final.get("success") is True and final.get("reason") == "finished", final
        print(f"ok {version} layer: API path = MCP path on the toy service:", ", ".join(s["same"]),
              "identical; tools", s["mcp_tools_called"], "; evidence", s["out"])


if __name__ == "__main__":
    main()
