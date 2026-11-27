"""End-to-end test of the efe-robot MCP server against the toy eai-standard/2.2 service (CPU, ~10 s), run without
RCB_AGENT_END (the toy is an agent-ended adapter; without the feature a success ends its episode): the endpoint
tools' request and reply, a hold chunk (no rows), a refusal, the end of the episode, finish refused where the success is not hidden (and sent where it is: test_agent_end.py, run at the end), a tool added from /spec (kinematics: tools/list after the first call), a pending call collected with
observe(operation=...), one deadline per call (the wait for an earlier call included) and a call that finds an earlier
one still running not sent (`sent` false).

    python3 embodied_first_exam/standard/mcp/tests/test_toy.py
"""
import json, os, pathlib, socket, subprocess, sys, tempfile, time
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent
sys.path.insert(0, str(MCP))
sys.path.insert(0, str(HERE))
from mcp_client import McpClient, McpToolError  # noqa: E402


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_toy_"))
    port = free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("RCB_AGENT_END", "RCB_STEP_LIMIT")}
    env.update({"RCB_DATA": str(tmp / "data"), "RCB_TOY_PORT": str(port), "PYTHONPATH": str(STD), "RCB_TOY_STEP_S": "0.02"})
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
        # a tool added from /spec: the toy serves /kinematics (spec `kinematics`), the manifest does not list it
        listed = {t["name"] for t in c.request("tools/list")["tools"]}
        assert "kinematics" in listed and "kinematics" in spec, listed
        k = c.call("kinematics", body={"op": "fk", "q": [0.0, 0.0, 0.0]})
        assert k.get("ok") and k.get("op") == "fk", k
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
        # a long chunk (100 rows, 2 s): pending after 1 s, collected with observe(operation=...)
        raw = c.call_raw("submit", type="joint_position", actions=[[0.3 * k / 100, 0, 0] for k in range(1, 101)],
                         dt=0.05, cameras=["top"], video="none")
        out = json.loads(raw["content"][0]["text"])
        assert out.get("pending") and "observe(operation=" in out["note"], out
        while out.get("pending"):
            out = json.loads(c.call_raw("observe", operation=out["operation"])["content"][0]["text"])
        assert out["meta"]["executed_rows"] == 100, out["meta"]
        # one deadline per call, the wait for an earlier call included; a call that finds one still running is not sent
        def timed(name, **a):
            t = time.monotonic(); r = c.call_raw(name, **a)
            return r, json.loads(r["content"][0]["text"]), time.monotonic() - t
        _, p1, dt1 = timed("submit", type="joint_position", actions=[[0.3 - 0.1 * k / 200, 0, 0] for k in range(1, 201)],
                           dt=0.05, video="none")                                  # 200 rows: 4 s
        assert p1.get("pending") and dt1 < 1.6, (p1, dt1)
        r2, p2, dt2 = timed("observe", cameras=[])
        assert r2["isError"] and p2.get("sent") is False and p2["operation"] == p1["operation"] \
            and p2["failure"]["category"] == "busy" and dt2 < 1.6, (p2, dt2)       # not the earlier call's result
        _, p3, dt3 = timed("observe", operation=p1["operation"])                    # still running: pending again
        out = c._collect(p3)
        assert out["meta"]["executed_rows"] == 200, out["meta"]
        _, p4, _ = timed("submit", type="joint_position", actions=[[0.2 + 0.1 * k / 70, 0, 0] for k in range(1, 71)],
                         dt=0.05, video="none")                                    # 70 rows: 1.4 s
        _, p5, dt5 = timed("submit", type="joint_position", actions=[[0.3 - 0.1 * k / 100, 0, 0] for k in range(1, 101)],
                           dt=0.05, video="none")    # waits ~0.4 s for p4, then runs: pending at 1 s from its arrival
        assert p4.get("pending") and p5.get("pending") and p5["operation"] != p4["operation"] and dt5 < 1.6, (p4, p5, dt5)
        assert c._collect(p4)["meta"]["executed_rows"] == 70 and c._collect(p5)["meta"]["executed_rows"] == 100
        # McpClient.call: a call not sent is sent again once the running one is collected
        _, p6, _ = timed("submit", type="joint_position", actions=[[0.2, 0, 0]] * 100, dt=0.05, video="none")
        ob = c.call("observe", cameras=[])
        assert p6.get("pending") and "meta" in ob and not ob.get("sent") is False, (p6, ob)
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
    import test_agent_end                  # finish where it is the agent's: an agent-ended toy (ci runs this file)
    test_agent_end.main()
    import test_failures                   # a 5xx, a lost reply, /spec 409
    test_failures.main()


if __name__ == "__main__":
    main()
