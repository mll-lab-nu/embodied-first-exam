"""Sidecar lifecycle: live process exits before either replay starts."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
from .evidence import write_json


def run(instance, output="/data", *, host="0.0.0.0", port=8000, stay=False):
    from .replay import verify_twice
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output/"final.json").exists():
        raise FileExistsError("Existing final evidence; use a new output directory")
    command = [sys.executable,"-m","topogym.benchmark","serve-child",str(instance),str(output),"--host",host,"--port",str(port)]
    config = json.loads(Path(instance).read_text())
    try:
        with (output/"server.log").open("wb") as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            (output/"server.pid").write_text(str(child.pid))
            requested = False
            deadline = time.monotonic() + float(config.get("startup_timeout_s",900))
            ready = False
            while child.poll() is None:
                if not ready and (output/"ready.json").exists():
                    ready = True
                    deadline = time.monotonic()+float(config.get("wall_clock_s",5400))+30
                if not ready and time.monotonic() > deadline:
                    child.kill()
                    child.wait()
                    raise TimeoutError("Simulator did not become ready within startup_timeout_s")
                if ready and not requested and ((output/"finish").exists() or time.monotonic() > deadline):
                    child.send_signal(signal.SIGUSR1)
                    requested = True
                    deadline = time.monotonic()+120
                elif requested and time.monotonic() > deadline:
                    child.kill()
                    child.wait()
                    raise TimeoutError("Live simulator did not terminate for finalization")
                time.sleep(.2)
            if child.returncode != 0:
                raise RuntimeError(f"Live simulator exited {child.returncode}")
        live = json.loads((output/"live.json").read_text())
        verify_twice(instance,output/"trajectory.npz",output,live=live)
    except Exception as error:
        traceback.print_exc()
        write_json(output/"final.json", dict(finalized=True, success=False, deterministic=False, grader_error=1,
                                            error=f"{type(error).__name__}: {error}"))
    if stay:
        # Keep the trusted sidecar available for Harbor's artifact download.
        while True:
            signal.pause()


def collect(output="/data", timeout=7500):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    (output/"finish").touch(exist_ok=True)
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        path = output/"final.json"
        if path.is_file():
            final = json.loads(path.read_text())
            if final.get("finalized") is True:
                print(json.dumps(final))
                return
        time.sleep(1)
    raise TimeoutError("Trusted sidecar finalization timed out")
