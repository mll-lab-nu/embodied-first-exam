"""Local generated-package integration test. NOT a Harbor/container isolation test.

Uses separate service, reference learner and verifier processes, no repository runtime imports.
An optional previously frozen oracle cache is validated by the real service before reuse.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--residual", type=Path, required=True)
    parser.add_argument("--instance", type=int, choices=(0, 1), default=0)
    parser.add_argument("--mode", choices=("reference", "nop"), default="reference")
    parser.add_argument("--oracle-cache", type=Path, help="Prior session root; only frozen oracle evidence is reused")
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    task = ROOT / f"tasks/roboengineer-landing-random-pad-i{args.instance:02d}-standard"
    data = args.out / "data"
    data.mkdir()
    if args.oracle_cache:
        state = json.loads((args.oracle_cache / "state.json").read_text())
        instance = json.loads((task / "tests/instance.json").read_text())
        if state["bank"] != instance["bank"]:
            raise ValueError("Cache is for another case bank")
        session = data / "session"
        session.mkdir()
        shutil.copytree(args.oracle_cache / "oracle", session / "oracle")
        state.update(
            rounds=[],
            sealed=False,
            infrastructure_error=False,
            deadline=time.time() + 3600,
            native_started_at=None,
            render=True,
            render_style="flight-studio/1-cpu"
            if os.environ.get("LANDING_RENDER_QUALITY") == "cpu"
            else "flight-studio/1",
        )
        for key in ("selected", "summary"):
            state.pop(key, None)
        (session / "state.json").write_text(json.dumps(state))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "RCB_DATA": str(data),
        "RCB_INSTANCE": str(task / "environment/sim/instance.json"),
        "RCB_RESIDUAL": str(args.residual.resolve()),
        "RCB_WALL_CLOCK_S": "3600",
        "RCB_PORT": str(port),
        "PYTHONPATH": str(task / "environment/sim"),
    }
    begin = time.monotonic()
    with (args.out / "service.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "scripts.quadrotor_landing.native.service"],
            env=env,
            cwd=args.out,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            while time.monotonic() - begin < 1800:
                if process.poll() is not None:
                    raise RuntimeError("Service exited; see service.log")
                try:
                    with urlopen(url + "/health", timeout=2) as response:
                        if json.load(response).get("ready"):
                            break
                except OSError:
                    time.sleep(0.5)
            else:
                raise TimeoutError("Startup")
            print("Service ready; oracle references validated.", flush=True)
            if args.mode == "reference":
                client_env = {**env, "PYTHONPATH": str(task / "environment/public")}
                subprocess.run(
                    [sys.executable, str(task / "solution/iterate.py"), "--out", str(args.out / "agent"), "--url", url],
                    env=client_env,
                    cwd=args.out,
                    check=True,
                    timeout=3600,
                )
                print("Three public-feedback adaptation rounds sealed.", flush=True)
            subprocess.run(
                [sys.executable, "-m", "scripts.quadrotor_landing.native.collect"],
                env=env,
                cwd=args.out,
                check=True,
                timeout=900,
            )
            # The actual generated no-network verifier logic, in another process and with no public output input.
            code = (
                "import importlib.util,json,sys; s=importlib.util.spec_from_file_location('v',sys.argv[1]); "
                "v=importlib.util.module_from_spec(s); s.loader.exec_module(v); "
                "print(json.dumps(v.verdict(sys.argv[2],sys.argv[3])))"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(task / "tests/grade.py"),
                    str(data),
                    str(task / "tests/instance.json"),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=args.out,
                timeout=30,
            )
            report = {
                "kind": "local_generated_package_smoke",
                "container_isolation_tested": False,
                "mode": args.mode,
                "instance": args.instance,
                "graphics": env.get("MUJOCO_GL", "default"),
                "oracle_cache_reused": bool(args.oracle_cache),
                "elapsed_s": time.monotonic() - begin,
                "reward": json.loads(result.stdout),
            }
            (args.out / "verification.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
            if report["reward"]["infra_error"]:
                raise RuntimeError("Trusted evaluation failed")
            if args.mode == "nop" and report["reward"]["success"]:
                raise RuntimeError("Nop incorrectly succeeded")
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
