"""Operator launcher and persistent, socket-free file transport for any task."""
import argparse
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import unquote

from .registry import TASKS, factory_for
from .client import Client
from .session import Session, write_json


def dispatch(session, path, payload, raw=False):
    if payload is None:
        if path == "/v1/session":
            return session.snapshot()
        if path == "/v1/prompt":
            return dict(prompt=session.prompt())
        if path.startswith("/artifacts/"):
            data = session.artifact(unquote(path[len("/artifacts/"):])).read_bytes()
            return data if raw else json.loads(data)
    elif isinstance(payload, dict):
        if path == "/v1/segments":
            return session.submit(**payload)
        if path.startswith("/v1/usage/"):
            return session.usage(path.rsplit("/", 1)[-1], **payload)
        if path in ("/v1/finish", "/v1/shutdown"):
            return session.finish(**payload)
    raise ValueError("Unknown local request")


def heartbeat_worker(root):
    """A separate interpreter stays responsive during native GIL-held builds."""
    owner = json.loads((root/"owner.json").read_text())
    while True:
        try:
            fields = Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(")", 1)[1].split()
            alive = fields[19] == owner["starttime"] and fields[0] not in ("Z", "X")
        except OSError:
            alive = False
        write_json(root/"heartbeat.json", dict(pid=owner["pid"], starttime=owner["starttime"],
            heartbeat=time.time(), alive=alive))
        if not alive:
            return
        time.sleep(1)


def worker(root):
    config = json.loads((root/"launch.json").read_text())
    pid = os.getpid()
    owner = dict(pid=pid, starttime=Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19], state="starting")
    lock = threading.Lock()

    def publish(state=None):
        with lock:
            if state:
                owner["state"] = state
            owner["heartbeat"] = time.time()
            write_json(root/"owner.json", owner)

    publish()
    monitor = subprocess.Popen([sys.executable, "-m", "topogym.agent_bridge.local", "--heartbeat", str(root)])
    session = None

    def interrupted(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        session = Session(factory_for(config["task"], config["backend"], config["renderer"], config["factory"]),
            config["output"], mode=config["mode"], token_limit=config["token_limit"],
            max_steps=config["max_steps"], allow_internet=config["allow_internet"])
        publish("ready")
        while True:
            pending = sorted((root/"inbox").glob("*.json"))
            for path in pending:
                shutdown = False
                try:
                    if path.stat().st_size > 2_000_000:
                        raise ValueError("Local request exceeds 2 MB")
                    request = json.loads(path.read_text())
                    result = dispatch(session, **request)
                    response = (dict(bytes=base64.b64encode(result).decode()) if request.get("raw")
                                else dict(result=result))
                    shutdown = request["path"] == "/v1/shutdown"
                except Exception as exc:
                    response = dict(error=f"{type(exc).__name__}: {exc}")
                write_json(root/"outbox"/path.name, response)
                path.unlink()
                if shutdown:
                    return
            time.sleep(.025)
    finally:
        monitor.terminate()
        monitor.wait(timeout=5)
        publish("stopped")
        if session is not None:
            if session.state == "executing":
                session.state, session.reason = "failed", "Local owner interrupted during irreversible execution"
                session._persist()
            else:
                session.finish("Local simulator process stopped; this episode cannot be resumed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--task", choices=TASKS, default="horseshoe_ring")
    parser.add_argument("--factory")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--renderer", choices=("rasterizer", "nyx"), default="rasterizer")
    parser.add_argument("--mode", choices=("manual", "metered"), default="manual")
    parser.add_argument("--token-limit", type=int, default=2_000_000)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--allow-internet", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--stop", type=Path, help="Stop the local owner using the solver package directory")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--heartbeat", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.heartbeat:
        heartbeat_worker(args.heartbeat)
        return
    if args.worker:
        worker(args.worker)
        return
    if args.stop:
        config = json.loads((args.stop/"bridge_config.json").read_text())
        print(json.dumps(Client(config["url"]).request("/v1/shutdown", dict(reason="Operator stopped local owner"))))
        return
    if not args.output or not args.package:
        parser.error("--output and --package are required")
    if args.output.exists() or args.package.exists():
        parser.error("Use NEW episode and package directories; restart/resume is forbidden")
    root = Path(str(args.output.resolve())+".ipc")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    (root/"inbox").mkdir()
    (root/"outbox").mkdir()
    config = {k: getattr(args, k) for k in ("task", "backend", "renderer", "factory", "mode",
                                          "token_limit", "max_steps", "allow_internet")}
    config["output"] = str(args.output.resolve())
    write_json(root/"launch.json", config)
    with (root/"worker.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "topogym.agent_bridge.local", "--worker", str(root)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        while not (root/"owner.json").exists():
            if process.poll() is not None:
                raise RuntimeError(f"Local owner failed; see {root/'worker.log'}")
            time.sleep(.05)
        from .package import export_package
        client = Client("local://"+str(root))
        output = export_package(client, args.package, args.run_id or args.package.name)
        print(f"Local task ready. Solver package: {output}\nOperator log: {root/'worker.log'}", flush=True)
    except BaseException:
        process.terminate()
        raise


if __name__ == "__main__":
    main()
