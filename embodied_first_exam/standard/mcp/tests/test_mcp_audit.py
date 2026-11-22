"""The standard-mcp audit (scripts/mcp_only.py audit, owner decision D145): the efe-robot server's call log against the
service's episode log. Against the toy eai-standard/2.2 service (CPU, ~15 s): a trial whose robot requests all came
through the harness's server passes; a direct client request without the server's mark is flagged; then the log rules
on hand-made records (an unmarked or forged submit note, a server a script started, agent code that reaches the
simulator, the no-code and shell variants).

    python3 embodied_first_exam/standard/mcp/tests/test_mcp_audit.py
"""
import json, os, pathlib, shutil, socket, subprocess, sys, tempfile, time
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent
REPO = STD.parents[1]
sys.path.insert(0, str(MCP))
sys.path.insert(0, str(REPO / "scripts"))
from mcp_client import McpClient  # noqa: E402
import mcp_only  # noqa: E402


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def kinds(r):
    return sorted({v["kind"] for v in r["violations"]})


def claude_log(path: pathlib.Path, calls):
    """A Claude Code stream-json log with these (tool, input) calls."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ev = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": n, "input": i}]}} for n, i in calls]
    path.write_text("".join(json.dumps(e) + "\n" for e in ev))


def as_harness(log: pathlib.Path, comm="claude"):
    """The server line of the call log as the harness would have started the server (here: the test's Python did)."""
    out = []
    for ln in log.read_text().splitlines():
        r = json.loads(ln)
        if "server" in r:
            r["parent"] = {"pid": 1, "comm": comm, "cmd": comm}
        out.append(json.dumps(r))
    log.write_text("\n".join(out) + "\n")


def toy_trial(tmp: pathlib.Path):
    """A trial dir: three robot tool calls through the server, then the episode log; returns (trial, port, data)."""
    port = free_port()
    data = tmp / "data"
    env = {**os.environ, "RCB_DATA": str(data), "RCB_TOY_PORT": str(port), "PYTHONPATH": str(STD)}
    sim = subprocess.Popen([sys.executable, str(STD / "toy_server.py")], env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    trial = tmp / "job" / "toy__abc"
    (trial / "agent").mkdir(parents=True)
    c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(HERE / "toy_manifest.json"),
                       "--max-block-s", "20"],
                  env={"SIM_URL": f"http://127.0.0.1:{port}", "EFE_MCP_TOOLS_DIR": str(STD),
                       "EFE_MCP_WORKSPACE": str(tmp / "app"), "EFE_MCP_LOG": str(trial / "agent" / "efe-mcp.jsonl")})
    c.call("describe_robot")
    c.call("observe")
    c.call("move_robot", goals=[{"target": "arm", "joint_positions": [0.2, 0.1, 0.0]}], duration_s=0.5)
    c.close()
    claude_log(trial / "agent" / "claude-code.txt", [("mcp__efe-robot__describe_robot", {}),
                                                     ("mcp__efe-robot__observe", {}),
                                                     ("mcp__efe-robot__move_robot", {"goals": []}),
                                                     ("Bash", {"command": "python3 -c 'import numpy; print(1)'"})])
    as_harness(trial / "agent" / "efe-mcp.jsonl")
    return trial, port, data, sim


def collect(trial, data):
    (trial / "artifacts").mkdir(exist_ok=True)
    shutil.copy(data / "episode.jsonl", trial / "artifacts" / "episode.jsonl")


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_audit_"))
    trial, port, data, sim = toy_trial(tmp)
    try:
        collect(trial, data)
        r = mcp_only.audit(trial)
        assert r["ok"] and not r["violations"], r
        assert r["robot_calls"] == 3 and r["requests"]["via_server"]["/submit"] >= 1, r
        assert r["requests"]["service"] == {p: n for p, n in r["requests"]["via_server"].items()
                                            if p in r["requests"]["service"]}, r
        # the same trial under no-code: its Bash call is a tool outside the MCP-only set
        assert kinds(mcp_only.audit(trial, no_code=True)) == ["tool_not_allowed"]
        # code that reaches the simulator directly, through the task's client: a submit without the server's mark
        sys.path.insert(0, str(STD))
        import rcb_client
        rb = rcb_client.Robot(base=f"http://127.0.0.1:{port}", timeout=30)
        rb.submit("joint_position", [[0.2, 0.1, 0.0]], dt=0.05, cameras=[], video="none")
        rb.get_obs(cameras=[], video="none")
        collect(trial, data)
        r = mcp_only.audit(trial)
        assert not r["ok"] and "untraced_request" in kinds(r), r
        assert r["requests"]["service"]["/submit"] == r["requests"]["via_server"]["/submit"] + 1, r
        # the shell variant has no rule on routes: the request is counted as direct
        s = mcp_only.audit(trial, mode="standard-mcp-shell")
        assert s["ok"] and s["requests"]["direct"].get("/submit") == 1, s
        # the runner's per-job verdict
        assert mcp_only.main(["audit-job", str(trial.parent), "--mode", "standard-mcp"]) == 0
        v = json.loads((trial.parent / "mcp_audit.json").read_text())
        assert v["ok"] is False and v["violations"][0]["trial"] == trial.name and "kind" in v["violations"][0], v
    finally:
        sim.terminate()
        try:
            sim.wait(10)
        except subprocess.TimeoutExpired:
            sim.kill()

    # hand-made records: services that log the note of each submit
    t2 = tmp / "job2" / "x__1"
    (t2 / "agent").mkdir(parents=True)
    (t2 / "artifacts").mkdir()
    claude_log(t2 / "agent" / "claude-code.txt", [("mcp__efe-robot__move_robot", {})])
    hdr = {"ts": 1, "server": "0.2.0", "pid": 7, "parent": {"pid": 3, "comm": "codex", "cmd": "codex exec"}}
    lines = [hdr, {"ts": 2, "sim": "/submit", "note": "efe-mcp:move_robot#1", "pid": 7, "tool": "move_robot"},
             {"ts": 2, "sim": "/submit", "note": "help, the cup is cracked", "pid": 7, "tool": "signal"},
             {"ts": 3, "tool": "move_robot", "args": {}, "pid": 7}]
    (t2 / "agent" / "efe-mcp.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))

    def episode(*notes):
        (t2 / "artifacts" / "episode.jsonl").write_text("".join(
            json.dumps({"ev": "submit", "call": i + 1, "rows": 1, "note": n}) + "\n" for i, n in enumerate(notes)))
    episode("efe-mcp:move_robot#1", "help, the cup is cracked")
    assert mcp_only.audit(t2)["ok"], mcp_only.audit(t2)              # the server's mark; a signal's note it sent
    episode("efe-mcp:move_robot#1", "")                              # a direct submit (the client's default note)
    assert kinds(mcp_only.audit(t2)) == ["unmarked_request", "untraced_request"] or \
        kinds(mcp_only.audit(t2)) == ["unmarked_request"], mcp_only.audit(t2)
    episode("efe-mcp:move_robot#1", "help, the cup is cracked", "efe-mcp:move_robot#1")
    assert "forged_mark" in kinds(mcp_only.audit(t2)), mcp_only.audit(t2)
    # a server a script started (the shell's python), next to the harness's
    episode("efe-mcp:move_robot#1", "help, the cup is cracked")
    with open(t2 / "agent" / "efe-mcp.jsonl", "a") as f:
        f.write(json.dumps({"ts": 5, "server": "0.2.0", "pid": 9, "parent": {"pid": 8, "comm": "python3",
                                                                            "cmd": "python3 drive.py"}}) + "\n")
    assert kinds(mcp_only.audit(t2)) == ["script_server"], mcp_only.audit(t2)
    assert mcp_only.audit(t2, mode="standard-mcp-shell")["ok"]       # the shell variant's client starts its own

    # agent code that reaches the simulator; reading the client's source is not that
    t3 = tmp / "job3" / "y__1"
    claude_log(t3 / "agent" / "claude-code.txt", [
        ("Bash", {"command": "grep -n 'import rcb_client' /opt/tools/efe_mcp/rcb_adapter.py | head"}),
        ("Bash", {"command": "cat /opt/tools/efe_mcp/server.py"}),
        ("Write", {"file_path": "/app/ik.py", "content": "import numpy as np\ndef ik(p):\n    return p\n"})])
    r = mcp_only.audit(t3)
    assert r["ok"], r
    claude_log(t3 / "agent" / "claude-code.txt", [
        ("Write", {"file_path": "/app/go.py", "content": "import requests\nrequests.post('http://localhost:8000/submit')\n"}),
        ("Bash", {"command": "cd /app && python3 - <<'EOF'\nimport rcb_client\nr = rcb_client.Robot()\nEOF"}),
        ("Bash", {"command": "python3 /opt/tools/efe_mcp/server.py < cmds.jsonl"}),
        ("WebSearch", {"query": "x"})])
    r = mcp_only.audit(t3)
    assert kinds(r) == ["agent_code", "web_tool"] and len(r["violations"]) == 4, r
    # Codex: a command that posts to the simulator
    t4 = tmp / "job4" / "z__1"
    (t4 / "agent").mkdir(parents=True)
    (t4 / "agent" / "codex.txt").write_text(json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "command": "bash -lc 'curl -s -X POST http://sim:8000/observe'"}}) + "\n")
    assert kinds(mcp_only.audit(t4)) == ["agent_code"], mcp_only.audit(t4)
    assert kinds(mcp_only.audit(t4, no_code=True)) == ["agent_code", "tool_not_allowed"]
    # no call log at all: the robot was driven, and the agent made no efe-robot tool call
    t5 = tmp / "job5" / "w__1"
    claude_log(t5 / "agent" / "claude-code.txt", [("Bash", {"command": "python3 /app/drive.py"})])
    (t5 / "artifacts").mkdir()
    (t5 / "artifacts" / "episode.jsonl").write_text(json.dumps({"ev": "submit", "call": 1, "rows": 5}) + "\n")
    assert kinds(mcp_only.audit(t5)) == ["untraced_request"], mcp_only.audit(t5)
    shutil.rmtree(tmp, ignore_errors=True)
    print("ok standard-mcp audit: direct request flagged, marks, script servers, agent code, no-code and shell variants")


if __name__ == "__main__":
    main()
