#!/usr/bin/env python3
"""Run scripts/robopaint_brush_mk_task.py on a host without docker but with the eai-robopaint runtime installed natively (the
image's /opt/venv, /opt/mypaint, ... at their own paths, `. /opt/rp_env.sh`): the generator is imported unchanged and its one
`docker run ... bash gen.sh` call is replaced by running gen.sh in the work directory, with the container paths it uses mapped
to the host's (/work -> the work directory, /mmah/graphics.txt -> the exemplar file) and the self-test's scorer port moved to
--port (8001 may be taken on a shared host). Everything else (the self-test, the licence step, assemble) is the generator's own.

    . /opt/rp_env.sh
    python cs_gen_native.py --port 18001 -- --family caoshu --target shan --graphics shan.graphics.txt --max-strokes 3 \
        --plans plans.json --out-root gen --template-root tasks
"""
import os, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def main() -> int:
    argv = sys.argv[1:]
    port = "18001"
    if argv[:1] == ["--port"]:
        port, argv = argv[1], argv[2:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import robopaint_brush_mk_task as M
    real_run = subprocess.run

    def run(cmd, *a, **kw):
        if not (isinstance(cmd, list) and cmd[:2] == ["docker", "run"]):
            return real_run(cmd, *a, **kw)
        mounts = {}
        for i, x in enumerate(cmd):
            if x == "-v":
                src, dst = cmd[i + 1].split(":")[:2]
                mounts[dst] = src
        work = mounts["/work"]
        for f in ("gen.sh", "spec.json"):
            p = os.path.join(work, f)
            s = open(p, encoding="utf-8").read()
            if "/mmah/graphics.txt" in mounts:
                s = s.replace("/mmah/graphics.txt", mounts["/mmah/graphics.txt"])
            if f == "gen.sh":
                s = s.replace("RCB_SCORER_PORT=8001", f"RCB_SCORER_PORT={port}").replace("localhost:8001", f"localhost:{port}")
                s = s.replace("/work", work)
            open(p, "w", encoding="utf-8").write(s)
        env = {**os.environ, "RCB_SESSION_LOG": "", "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "4"),
               "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "4"), "RCB_TORCH_THREADS": os.environ.get("RCB_TORCH_THREADS", "4")}
        print("+ native: bash gen.sh in", work, flush=True)
        return real_run(["bash", "gen.sh"], cwd=work, env=env, check=kw.get("check", False))

    M.subprocess.run = run
    sys.argv = [os.path.join(ROOT, "scripts", "robopaint_brush_mk_task.py")] + argv
    return M.main()


if __name__ == "__main__":
    sys.exit(main())
