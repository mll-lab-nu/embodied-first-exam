#!/usr/bin/env python3
"""The API path and the MCP path of one oracle on one service: the same episode?

Runs the oracle twice against a fresh service each time (the same command, a new record directory):
  api  the oracle as it is, on the task's own client (TOOLS_DIR/rcb_client.py) over HTTP;
  mcp  the same oracle with that client's HTTP sent through the efe-robot MCP server's endpoint tools
       (oracle/rcb_client_mcp.py: EFE_MCP_ORACLE=1, sitecustomize.py), the server started from SERVER with MANIFEST.
Then compares the services' records: every file of the record directory whose name is in --compare (default: the
trajectory and the verdict files the shared layers write) byte for byte, after dropping wall-clock fields from JSON
(--ignore-keys), and the oracle's output lines that do not carry times.

    equivalence.py --service "python3 toy_server.py" --data-env RCB_DATA --port-env RCB_TOY_PORT \
        --tools DIR --manifest M.json --oracle "python3 oracle.py" [--server .../server.py] [--out DIR]

Exit 0 and a JSON summary when both runs leave the same record; 1 with the differences otherwise. CPU only; nothing
here starts a container."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, re, shlex, signal, socket, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
WALL = {"elapsed_s", "wall_s", "t", "ts", "time", "time_s", "t_wall", "wall", "started", "ended", "finished_at",
        "started_at", "time_left_s", "lag_s", "max_lag_s", "clock_s", "request_busy_s", "max_queue_wait_s", "request_mb",
        "busy_s", "dur_s", "startup_s", "build_s", "replay_s", "pid", "unix_s", "wall_clock_s", "elapsed", "deadline",
        "note", "operation_id", "request_deadline_unix_s", "host", "hostname", "stalled_s", "stalled_share", "stalls",
        "sim_wall_s", "real_time_factor", "rtf", "mem_mb", "rss_mb", "call_wall_s", "wall_time_s", "t0", "t1"}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def scrub(o, ignore):
    if isinstance(o, dict):
        return {k: scrub(v, ignore) for k, v in o.items() if k not in ignore}
    if isinstance(o, list):
        return [scrub(v, ignore) for v in o]
    return o


def digest(p: pathlib.Path, ignore) -> str:
    b = p.read_bytes()
    if p.suffix in (".json", ".jsonl"):
        try:
            lines = [json.loads(l) for l in b.decode().splitlines() if l.strip()] if p.suffix == ".jsonl" else [json.loads(b)]
            b = json.dumps([scrub(x, ignore) for x in lines], sort_keys=True).encode()
        except ValueError:
            pass
    return hashlib.sha256(b).hexdigest()


def run(mode, a, out: pathlib.Path):
    data = out / mode / "data"
    data.mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = {**os.environ, a.data_env: str(data), **({a.port_env: str(port)} if a.port_env else {})}
    for kv in a.service_env:
        k, v = kv.split("=", 1)
        env[k] = v.replace("{port}", str(port)).replace("{data}", str(data))
    log = open(out / mode / "service.log", "w")
    svc = subprocess.Popen(shlex.split(a.service.replace("{port}", str(port)).replace("{data}", str(data))),
                           env=env, stdout=log, stderr=subprocess.STDOUT, cwd=a.service_cwd or None,
                           start_new_session=True)
    url = (a.url or "http://127.0.0.1:{port}").replace("{port}", str(port))
    oenv = {**os.environ, "SIM_URL": url, "PYTHONPATH": a.tools, "EFE_MCP_TOOLS_DIR": a.tools}
    for kv in a.oracle_env:
        k, v = kv.split("=", 1)
        oenv[k] = v.replace("{port}", str(port)).replace("{data}", str(data))
    if mode == "mcp":
        app = out / mode / "app"
        oenv.update({"EFE_MCP_ORACLE": "1", "EFE_MCP_SERVER": a.server, "EFE_MCP_MANIFEST": a.manifest,
                     "EFE_MCP_WORKSPACE": str(app), "EFE_MCP_LOG": str(out / mode / "efe-mcp.jsonl"),
                     "PYTHONPATH": os.pathsep.join([str(MCP / "oracle"), a.tools])})
    t0 = time.time()
    try:
        o = subprocess.run(shlex.split(a.oracle), env=oenv, capture_output=True, text=True, timeout=a.timeout,
                           cwd=a.oracle_cwd or None)
        (out / mode / "oracle.out").write_text(o.stdout + "\n--- stderr\n" + o.stderr)
        rc = o.returncode
        if a.after:                    # e.g. the collect hook that ends the episode and writes the verdict
            subprocess.run(shlex.split(a.after.replace("{port}", str(port)).replace("{data}", str(data))),
                           env=oenv, capture_output=True, timeout=600)
        time.sleep(a.settle)
    finally:
        try:
            os.killpg(svc.pid, signal.SIGTERM)
            svc.wait(30)
        except Exception:
            os.killpg(svc.pid, signal.SIGKILL)
        log.close()
    return {"rc": rc, "s": round(time.time() - t0, 1), "data": data, "stdout": o.stdout}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--service", required=True); ap.add_argument("--service-cwd"); ap.add_argument("--service-env", action="append", default=[])
    ap.add_argument("--data-env", default="RCB_DATA"); ap.add_argument("--port-env", default="")
    ap.add_argument("--url"); ap.add_argument("--tools", required=True); ap.add_argument("--manifest", required=True)
    ap.add_argument("--server", default=str(MCP / "server.py"))
    ap.add_argument("--oracle", required=True); ap.add_argument("--oracle-cwd"); ap.add_argument("--oracle-env", action="append", default=[])
    ap.add_argument("--after", default=""); ap.add_argument("--settle", type=float, default=1.0)
    ap.add_argument("--compare", default="trajectory.npz,journal.f64,trajectory_live.f64,final.json,submitted.f64")
    ap.add_argument("--ignore-keys", default="")
    ap.add_argument("--out", default=""); ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out or os.environ.get("TMPDIR", "/tmp")) / f"equiv_{int(time.time())}"
    out.mkdir(parents=True, exist_ok=True)
    ignore = WALL | set(filter(None, a.ignore_keys.split(",")))
    res = {m: run(m, a, out) for m in ("api", "mcp")}
    diffs, same = [], []
    names = [n.strip() for n in a.compare.split(",") if n.strip()]
    for n in names:
        pa, pm = res["api"]["data"] / n, res["mcp"]["data"] / n
        if not pa.exists() and not pm.exists():
            continue
        if not (pa.exists() and pm.exists()):
            diffs.append(f"{n}: only in {'api' if pa.exists() else 'mcp'}")
        elif digest(pa, ignore) != digest(pm, ignore):
            diffs.append(f"{n}: differs")
        else:
            same.append(n)
    strip = lambda s: [l for l in s.splitlines() if not re.search(r"\d+\.\d+ ?s\b|time|elapsed|lag", l)]
    if strip(res["api"]["stdout"]) != strip(res["mcp"]["stdout"]):
        diffs.append("oracle output differs (see api/oracle.out, mcp/oracle.out)")
    for m in ("api", "mcp"):
        if res[m]["rc"] != 0:
            diffs.append(f"{m}: the oracle exited {res[m]['rc']}")
    verdict = {}
    for m in ("api", "mcp"):
        f = res[m]["data"] / "final.json"
        if f.exists():
            d = json.loads(f.read_text())
            verdict[m] = {k: d.get(k) for k in ("success", "reason", "done", "steps", "control_steps", "rows", "calls")
                          if k in d}
    tools = []
    lp = out / "mcp" / "efe-mcp.jsonl"
    if lp.exists():
        tools = sorted({json.loads(l).get("tool") for l in lp.read_text().splitlines() if '"tool"' in l} - {None, ""})
    summary = {"out": str(out), "same": same, "diffs": diffs, "verdict": verdict, "mcp_tools_called": tools,
               "seconds": {m: res[m]["s"] for m in res}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 1 if diffs or not same else 0


if __name__ == "__main__":
    sys.exit(main())
