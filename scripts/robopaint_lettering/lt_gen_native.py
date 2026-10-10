#!/usr/bin/env python3
"""Run scripts/robopaint_brush_mk_task.py on a host without docker but with the eai-robopaint runtime installed natively (the image's
/opt/venv, /opt/mypaint, ... at their own paths, `. /opt/rp_env.sh`): the generator is imported unchanged and its one
`docker run ... bash gen.sh` call is replaced by running gen.sh in the work directory, with the container path /work mapped to the
work directory and the self-test's scorer port moved to --port (8001 may be taken on a shared host). Everything else (the self-test,
the licence step, assemble) is the generator's own.

    . /opt/rp_env.sh
    python lt_gen_native.py --port 18301 -- --family lettering --target liberty --exemplar liberty.exemplar.json \
        --out-root gen --template-root tasks
"""
import os, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def main() -> int:
    argv = sys.argv[1:]
    port = "18301"
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
        work = next(cmd[i + 1].split(":")[0] for i, x in enumerate(cmd) if x == "-v" and cmd[i + 1].split(":")[1] == "/work")
        p = os.path.join(work, "gen.sh")
        s = open(p, encoding="utf-8").read()
        s = s.replace("RCB_SCORER_PORT=8001", f"RCB_SCORER_PORT={port}").replace("localhost:8001", f"localhost:{port}").replace("/work", work)
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
