"""Render a completed baseline while its independent physics recheck continues."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time


@contextmanager
def render_lock(baseline):
    with (baseline/".render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline",type=Path)
    parser.add_argument("--force",action="store_true",help="Re-render saved physics; preserve existing formal archives")
    args=parser.parse_args()
    baseline=args.baseline.resolve()
    while not (baseline/"report.json").exists():
        time.sleep(5)
    report=json.loads((baseline/"report.json").read_text())
    if not report["full_threading_verified"]:
        print("Incomplete physical trial: no full-demo rendering",flush=True)
        return
    status=dict(scope="rendering only; publication still requires the independent complete recheck",
        status="waiting",started_at_utc=datetime.now(timezone.utc).isoformat())
    status_path=baseline.parent/"early_render_status.json"
    try:
        with render_lock(baseline):
            if args.force or not (baseline/"render_report.json").exists():
                if args.force:
                    previous=baseline.parent/"render_before_lighting_fix"
                    if not previous.exists():
                        previous.mkdir()
                        for name in ("render_report.json","render_config.yaml","initial.png","final.png"):
                            if (baseline/name).exists():
                                shutil.copy2(baseline/name,previous/name)
                status["status"]="rendering"
                status_path.write_text(json.dumps(status,indent=2)+"\n")
                command=[sys.executable,"-m","topogym.tasks.fiber_bundling.render_robot_sequence",
                    str(baseline),"--backend","cpu","--renderer","rasterizer","--clean"]
                env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",PYOPENGL_PLATFORM="egl")
                subprocess.run(command,env=env,check=True)
        status["status"]="rendered"
    except Exception as error:
        status.update(status="failed",failure=str(error))
        raise
    finally:
        status_path.write_text(json.dumps(status,indent=2)+"\n")


if __name__=="__main__":
    main()
